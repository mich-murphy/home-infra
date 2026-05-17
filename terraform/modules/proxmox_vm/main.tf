resource "local_sensitive_file" "cloud_init" {
  content         = var.cloud_init_content
  filename        = "${path.root}/files/${var.name}.cfg"
  file_permission = "0600"
}

resource "terraform_data" "cloud_init_upload" {
  triggers_replace = [local_sensitive_file.cloud_init.content]

  connection {
    type     = "ssh"
    user     = var.proxmox_user
    password = var.proxmox_password
    host     = var.proxmox_host
  }

  provisioner "file" {
    source      = local_sensitive_file.cloud_init.filename
    destination = "/var/lib/vz/snippets/${var.name}.yml"
  }

  provisioner "remote-exec" {
    inline = ["chmod 0600 /var/lib/vz/snippets/${var.name}.yml"]
  }
}

resource "proxmox_vm_qemu" "this" {
  depends_on = [terraform_data.cloud_init_upload]

  vmid        = var.vmid
  name        = var.name
  target_node = "proxmox"
  tags        = var.tags
  agent       = 1
  cpu {
    cores = var.cores
  }
  memory             = var.memory_mib
  bios               = "seabios"
  boot               = "order=scsi0"
  clone              = var.clone_template
  scsihw             = "virtio-scsi-single"
  vm_state           = "running"
  automatic_reboot   = true
  start_at_node_boot = true

  # Cloud-Init configuration. ciuser/sshkeys are required (not duplicative)
  # because Proxmox's auto-generated user-data carries `users: - default`,
  # which would otherwise shadow any `users:` block in the vendor snippet and
  # create the distro's default user (e.g. `arch` on the Arch cloud image).
  ciuser    = var.ciuser
  sshkeys   = var.ssh_public_key
  cicustom  = "vendor=local:snippets/${var.name}.yml"
  ciupgrade = true
  ipconfig0 = "ip=dhcp,ip6=dhcp"
  skip_ipv6 = true

  serial {
    id = 0
  }

  disks {
    scsi {
      scsi0 {
        disk {
          discard = true
          storage = "local-zfs"
          size    = var.disk_size
          # iothread is intentionally disabled: iothread on a virtio-scsi disk
          # backed by a local-zfs zvol has been observed to silently hang the
          # Proxmox host under bursty guest I/O (e.g. `pacman -Syu` extracting
          # many packages). Without iothread, I/O runs on the main QEMU thread
          # and the ZFS reclaim/ARC path stays stable.
          iothread = false
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
    id     = 0
    bridge = var.bridge
    model  = "virtio"
  }
}
