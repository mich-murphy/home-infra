resource "local_sensitive_file" "cloud_init" {
  content         = var.cloud_init_content
  filename        = "${path.root}/files/${var.name}.cfg"
  file_permission = "0600"
}

resource "proxmox_virtual_environment_file" "cloud_init" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = var.node_name
  overwrite    = true
  source_file {
    path      = local_sensitive_file.cloud_init.filename
    file_name = "${var.name}.yml"
    checksum  = local_sensitive_file.cloud_init.content_sha256
  }
}

resource "proxmox_virtual_environment_vm" "this" {
  depends_on          = [proxmox_virtual_environment_file.cloud_init]
  vm_id               = var.vmid
  name                = var.name
  description         = "Managed by Terraform."
  node_name           = var.node_name
  tags                = var.tags
  bios                = "seabios"
  keyboard_layout     = "en-us"
  boot_order          = ["scsi0"]
  on_boot             = false
  reboot_after_update = true
  scsi_hardware       = "virtio-scsi-single"
  started             = true
  agent {
    enabled = true
    type    = "virtio"
  }
  operating_system {
    type = "l26"
  }
  clone {
    full      = false
    node_name = var.node_name
    vm_id     = var.clone_template_vmid
  }
  cpu {
    cores   = var.cores
    sockets = 1
    type    = "host"
  }
  memory {
    dedicated = var.memory_mib
  }
  initialization {
    datastore_id        = "local-zfs"
    interface           = "ide1"
    vendor_data_file_id = "local:snippets/${var.name}.yml"
    # ciuser/sshkeys required: Proxmox user-data carries `users: - default`,
    # which would otherwise create the distro default user (e.g. `arch`).
    user_account {
      keys     = [var.ssh_public_key]
      username = var.ciuser
    }
    ip_config {
      ipv4 {
        address = "dhcp"
      }
      ipv6 {
        address = "dhcp"
      }
    }
  }
  serial_device {
    device = "socket"
  }
  disk {
    datastore_id = "local-zfs"
    discard      = "on"
    file_format  = "raw"
    interface    = "scsi0"
    # Disabled: iothread on a virtio-scsi disk over a local-zfs zvol can
    # silently hang the host under bursty guest I/O (e.g. `pacman -Syu`).
    iothread  = false
    replicate = false
    size      = var.disk_size
  }
  network_device {
    bridge = var.bridge
    model  = "virtio"
  }
  lifecycle {
    ignore_changes  = [clone]
    prevent_destroy = true
  }
}
