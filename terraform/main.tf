data "onepassword_item" "proxmox" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "proxmox_creds"
}

provider "proxmox" {
  pm_api_url          = "https://proxmox.local.elmurphy.com/api2/json"
  pm_api_token_id     = data.onepassword_item.proxmox.username
  pm_api_token_secret = data.onepassword_item.proxmox.password
  pm_tls_insecure     = false
}

locals {
  proxmox_creds = {
    username           = data.onepassword_item.proxmox.section[0].field[0].value
    password           = data.onepassword_item.proxmox.section[0].field[1].value
    host               = data.onepassword_item.proxmox.section[0].field[2].value
    tailscale_auth_key = data.onepassword_item.proxmox.section[0].field[3].value
  }
}

# Manually provisioned (no cloud-init); HBA passed through for ZFS.
# prevent_destroy blocks accidental replacement while still allowing drift detection.
resource "proxmox_vm_qemu" "truenas" {
  vmid        = 101
  name        = "truenas"
  target_node = "proxmox"
  tags        = "truenas"
  bios        = "seabios"
  machine     = "q35"
  boot        = "order=scsi0;net0"
  scsihw      = "virtio-scsi-single"
  agent       = 0

  start_at_node_boot = true
  startup_shutdown {
    order = 1
  }

  cpu {
    cores   = 2
    sockets = 1
    type    = "host"
  }
  memory = 12288

  disks {
    scsi {
      scsi0 {
        disk {
          storage = "local-zfs"
          size    = "32G"
          discard = true
        }
      }
    }
  }

  network {
    id       = 0
    bridge   = "vmbr0"
    model    = "virtio"
    macaddr  = "BC:24:11:AF:30:C0"
    firewall = true
  }

  pci {
    id     = 1
    raw_id = "0000:02:00"
    pcie   = true
    rombar = false
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "local_sensitive_file" "cloud_init_agents" {
  content = sensitive(templatefile("cloud_init.tftpl", {
    hostname           = "docker-host"
    os_family          = "debian"
    tailscale_auth_key = local.proxmox_creds.tailscale_auth_key
    ssh_public_key     = var.docker_host_ssh_public_key
  }))
  filename        = "${path.module}/files/agents.cfg"
  file_permission = "0600"
}

resource "terraform_data" "cloud_init_config" {
  triggers_replace = [local_sensitive_file.cloud_init_agents.content]
  connection {
    type     = "ssh"
    user     = local.proxmox_creds.username
    password = local.proxmox_creds.password
    host     = local.proxmox_creds.host
  }
  provisioner "remote-exec" {
    inline = ["mkdir -p /var/lib/vz/snippets"]
  }
  provisioner "file" {
    source      = local_sensitive_file.cloud_init_agents.filename
    destination = "/var/lib/vz/snippets/agents.yml"
  }
  provisioner "remote-exec" {
    inline = ["chmod 0600 /var/lib/vz/snippets/agents.yml"]
  }
}


# Cloud-init template setup: https://registry.terraform.io/providers/Telmate/proxmox/latest/docs/guides/cloud-init%2520getting%2520started#creating-a-cloud-init-template
resource "proxmox_vm_qemu" "cloud_init_docker_host" {
  depends_on = [
    terraform_data.cloud_init_config,
  ]
  vmid        = 102
  name        = "docker-host"
  target_node = "proxmox"
  tags        = "ubuntu"
  agent       = 1
  cpu {
    cores   = 6
    sockets = 1
    type    = "host"
  }
  memory             = 10240
  start_at_node_boot = true
  startup_shutdown {
    order = 2
  }
  bios             = "seabios"
  boot             = "order=scsi0"         # has to be the same as the OS disk of the template
  clone            = "ubuntu-server-24-04" # name of the template
  scsihw           = "virtio-scsi-single"
  vm_state         = "running"
  automatic_reboot = true
  cicustom         = "vendor=local:snippets/agents.yml" # path under /var/lib/vz/snippets
  ciupgrade        = true
  ciuser           = "ansible"
  sshkeys          = var.docker_host_ssh_public_key
  ipconfig0        = "ip=dhcp,ip6=dhcp"
  skip_ipv6        = true
  serial {
    id = 0
  }
  disks {
    scsi {
      scsi0 {
        disk {
          discard   = true
          storage   = "local-zfs"
          size      = "128G"
          iothread  = false
          replicate = false
        }
      }
    }
    ide {
      ide1 {
        cloudinit {
          storage = "local-zfs"
        }
      }
    }
  }
  network {
    id      = 0
    bridge  = "vmbr0"
    model   = "virtio"
    macaddr = "BC:24:11:13:C4:53"
  }

  # Intel iGPU passed through for Plex/Jellyfin hardware transcoding.
  pci {
    id     = 0
    raw_id = "0000:00:02.0"
  }

  # Zigbee/Z-Wave dongle pinned by host port (survives reboots better than vendor id).
  # 3.0.2-rc07 only ships the deprecated string form; newer providers have port/mapping blocks.
  usb {
    id   = 0
    host = "1-3"
    usb3 = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Blueprint for the planned K8s migration (docs/PRD.md); gated by enable_talos until then.
resource "proxmox_vm_qemu" "talos_control_plane" {
  count       = var.enable_talos ? 1 : 0
  vmid        = "20${count.index}"
  name        = "talos-prod-${count.index + 1}"
  description = "Siderolabs install image v1.12.2"
  target_node = "proxmox"
  tags        = "kubernetes"
  agent       = 1
  cpu {
    cores = 6
    type  = "host"
  }
  memory             = 10240
  start_at_node_boot = true
  bios               = "ovmf"
  machine            = "q35"
  boot               = "order=scsi0;ide1"
  scsihw             = "virtio-scsi-pci"
  vm_state           = "running"
  automatic_reboot   = true
  ipconfig0          = "ip=dhcp,ip6=dhcp"
  skip_ipv6          = true
  serial {
    id = 0
  }
  disks {
    scsi {
      scsi0 {
        disk {
          cache   = "writethrough"
          discard = true
          format  = "raw"
          storage = "local-zfs"
          size    = "100G"
        }
      }
      scsi1 {
        disk {
          cache   = "writethrough"
          discard = true
          format  = "raw"
          storage = "local-zfs"
          size    = "128G"
        }
      }
    }
    ide {
      ide1 {
        cdrom {
          iso = "local:iso/metal-amd64.iso"
        }
      }
    }
  }
  efidisk {
    efitype = "4m"
    storage = "local-zfs"
  }
  network {
    id     = 0
    bridge = "vmbr0"
    model  = "virtio"
  }
}

module "ai_dev" {
  for_each       = var.ai_devs
  source         = "./modules/proxmox_vm"
  name           = each.key
  vmid           = each.value.vmid
  clone_template = "arch-cloud"
  tags           = "arch;ai-dev"
  cores          = 2
  memory_mib     = 3072
  disk_size      = "150G"
  bridge         = "vmbr1"
  ciuser         = "michael"
  ssh_public_key = var.ai_dev_ssh_public_key
  cloud_init_content = templatefile("cloud_init.tftpl", {
    hostname           = each.key
    os_family          = "arch"
    ssh_public_key     = var.ai_dev_ssh_public_key
    tailscale_auth_key = local.proxmox_creds.tailscale_auth_key
  })
  proxmox_host     = local.proxmox_creds.host
  proxmox_user     = local.proxmox_creds.username
  proxmox_password = local.proxmox_creds.password
}
