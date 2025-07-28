provider "onepassword" {
  account = "xportal.1password.com"
}

data "onepassword_item" "proxmox" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "proxmox_creds"
}

provider "proxmox" {
  pm_api_url          = "https://proxmox.local.elmurphy.com/api2/json"
  pm_api_token_id     = data.onepassword_item.proxmox.username
  pm_api_token_secret = data.onepassword_item.proxmox.password
  pm_tls_insecure     = false # Set to false in production
}

# create cloud-init configuration
resource "local_file" "cloud_init_agents" {
  content  = templatefile("cloud_init.tftpl", { tailscale_auth_key = data.onepassword_item.proxmox.section[0].field[0].value })
  filename = "${path.module}/files/agents.cfg"
}

resource "terraform_data" "cloud_init_config" {
  connection {
    type     = "ssh"
    user     = data.onepassword_item.proxmox.section[1].field[0].value
    password = data.onepassword_item.proxmox.section[1].field[1].value
    host     = data.onepassword_item.proxmox.section[1].field[2].value
  }
  provisioner "remote-exec" {
    inline = ["mkdir -p /var/lib/vz/snippets"]
  }
  provisioner "file" {
    source      = local_file.cloud_init_agents.filename
    destination = "/var/lib/vz/snippets/agents.yml"
  }
}


# create template prior to applying
# reference: https://registry.terraform.io/providers/Telmate/proxmox/latest/docs/guides/cloud-init%2520getting%2520started#creating-a-cloud-init-template
resource "proxmox_vm_qemu" "cloud_init_docker_host" {
  depends_on = [
    terraform_data.cloud_init_config,
  ]
  vmid             = 102
  name             = "docker-host"
  target_node      = "proxmox"
  tags             = null
  agent            = 1
  cpu {
    cores = 2
  }
  memory           = 8192
  onboot           = true
  startup          = "order=2,up=60"
  bios             = "seabios"
  boot             = "order=scsi0"        # has to be the same as the OS disk of the template
  clone            = "ubuntu-server-2404" # name of the template
  scsihw           = "virtio-scsi-single"
  vm_state         = "running"
  automatic_reboot = true
  # Cloud-Init configuration
  cicustom  = "vendor=local:snippets/agents.yml" # /var/lib/vz/snippets
  ciupgrade = true
  ipconfig0 = "ip=dhcp,ip6=dhcp"
  skip_ipv6 = true
  ciuser    = "ansible"
  sshkeys   = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIH1TgAtlovn+B5ojfw7JRFDi8UxcTkHym30wEg6jekF"
  # set serial device for display
  serial {
    id = 0
  }
  disks {
    scsi {
      scsi0 {
        disk {
          discard  = true
          storage  = "local-zfs"
          size     = "128G"
          iothread = true
        }
      }
    }
    # attach cloud-init drive
    ide {
      ide1 {
        cloudinit {
          storage = "local-zfs"
        }
      }
    }
  }
  network {
    id     = 0
    bridge = "vmbr0"
    model  = "virtio"
  }
}

resource "proxmox_vm_qemu" "talos_control_plane" {
  count       = 3
  vmid        = "20${count.index + 1}"
  name        = "talos-prod-${count.index + 1}"
  desc        = "Talos image: factory.talos.dev/installer/3db570bedf4342804e5b4a418ec1dc4ac61ed0338f36ce4778e02dd8320b8457:v1.10.5"
  target_node = "proxmox"
  tags        = "kubernetes"
  agent       = 1
  cpu {
    cores = 6
  }
  memory           = 10240
  onboot           = true
  bios             = "seabios"
  boot             = "order=scsi0;ide1"
  scsihw           = "virtio-scsi-single"
  vm_state         = "running"
  automatic_reboot = true
  ipconfig0        = "ip=dhcp,ip6=dhcp"
  skip_ipv6        = true
  # set serial device for display
  serial {
    id = 0
  }
  disks {
    scsi {
      scsi0 {
        disk {
          discard  = true
          storage  = "local-zfs"
          size     = "100G"
          iothread = true
        }
      }
    }
    # install media
    ide {
      ide1 {
        cdrom {
          iso = "local:iso/metal-amd64.iso"
        }
      }
    }
  }
  network {
    id     = 0
    bridge = "vmbr0"
    model  = "virtio"
  }
}
