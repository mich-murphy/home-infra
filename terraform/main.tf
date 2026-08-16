data "onepassword_item" "proxmox" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "proxmox_creds"
}

locals {
  network       = yamldecode(file("${path.module}/../network/inventory.yaml")).network
  network_vlans = { for vlan in local.network.vlans : vlan.name => vlan }
  proxmox_node  = "proxmox"
  srv_vlan_id   = local.network_vlans.srv.id
  scp           = data.onepassword_item.proxmox.section_map["Terraform SCP"].field_map
  proxmox_creds = {
    username = local.scp["scp username"].value
    password = local.scp["scp password"].value
    # use an ephemeral/tagged single-use key; the previous shared key leaked into
    # cloud-init logs and must be rotated in the Tailscale admin console
    tailscale_auth_key = local.scp["tailscale authkey"].value
  }
}

provider "proxmox" {
  endpoint  = "https://${var.proxmox_host}:8006"
  api_token = "${data.onepassword_item.proxmox.username}=${data.onepassword_item.proxmox.password}"
  insecure  = true
  ssh {
    agent    = false
    username = local.proxmox_creds.username
    password = local.proxmox_creds.password
    node {
      name    = local.proxmox_node
      address = var.proxmox_host
    }
  }
}

# Manually provisioned (no cloud-init); HBA passed through for ZFS.
# prevent_destroy blocks accidental replacement while still allowing drift detection.
resource "proxmox_virtual_environment_vm" "truenas" {
  vm_id           = 101
  name            = "truenas"
  node_name       = local.proxmox_node
  tags            = ["truenas"]
  bios            = "seabios"
  keyboard_layout = "en-us"
  machine         = "q35"
  boot_order      = ["scsi0", "net0"]
  scsi_hardware   = "virtio-scsi-single"
  on_boot         = true
  agent {
    enabled = false
    type    = "virtio"
  }
  operating_system {
    type = "l26"
  }
  startup {
    order    = 1
    up_delay = 60
  }
  cpu {
    cores   = 2
    sockets = 1
    type    = "host"
  }
  memory {
    dedicated = 10240
    floating  = 10240
  }
  disk {
    datastore_id = "local-zfs"
    discard      = "on"
    file_format  = "raw"
    interface    = "scsi0"
    replicate    = true
    size         = 32
  }
  network_device {
    bridge      = "vmbr0"
    firewall    = true
    mac_address = var.truenas_macaddr
    model       = "virtio"
    vlan_id     = local.srv_vlan_id
  }
  hostpci {
    device = "hostpci1"
    id     = "0000:02:00"
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
  }))
  filename        = "${path.module}/files/agents.cfg"
  file_permission = "0600"
}

resource "proxmox_virtual_environment_file" "cloud_init_agents" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = local.proxmox_node
  overwrite    = true
  source_file {
    path      = local_sensitive_file.cloud_init_agents.filename
    file_name = "agents.yml"
    checksum  = local_sensitive_file.cloud_init_agents.content_sha256
  }
}

resource "proxmox_virtual_environment_vm" "cloud_init_docker_host" {
  depends_on = [
    proxmox_virtual_environment_file.cloud_init_agents,
  ]
  vm_id               = 102
  name                = "docker-host"
  description         = "Managed by Terraform."
  node_name           = local.proxmox_node
  tags                = ["ubuntu"]
  bios                = "seabios"
  keyboard_layout     = "en-us"
  boot_order          = ["scsi0"]
  on_boot             = true
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
  startup {
    order = 2
  }
  clone {
    full      = false
    node_name = local.proxmox_node
    vm_id     = var.ubuntu_server_24_04_template_vmid
  }
  cpu {
    cores   = 6
    sockets = 1
    type    = "host"
  }
  memory {
    dedicated = 8192
    floating  = 8192
  }
  initialization {
    datastore_id        = "local-zfs"
    interface           = "ide1"
    vendor_data_file_id = "local:snippets/agents.yml"
    ip_config {
      ipv4 {
        address = "dhcp"
      }
      ipv6 {
        address = "dhcp"
      }
    }
    user_account {
      keys     = [var.docker_host_ssh_public_key]
      username = "ansible"
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
    iothread     = false
    replicate    = false
    size         = 128
  }
  network_device {
    bridge      = "vmbr0"
    mac_address = var.docker_host_macaddr
    model       = "virtio"
    vlan_id     = local.srv_vlan_id
  }
  # Intel iGPU passed through for Plex/Jellyfin hardware transcoding.
  hostpci {
    device = "hostpci0"
    id     = "0000:00:02.0"
    rombar = true
  }
  # Zigbee/Z-Wave dongle pinned by host port (survives reboots better than vendor id).
  usb {
    host = "1-3"
    usb3 = true
  }
  lifecycle {
    ignore_changes  = [clone]
    prevent_destroy = true
  }
}

resource "proxmox_virtual_environment_vm" "unifi_controller" {
  vm_id               = 111
  name                = "unifi-controller"
  description         = "UniFi OS Server (managed by Terraform and Ansible)."
  node_name           = local.proxmox_node
  tags                = ["ubuntu", "unifi"]
  bios                = "seabios"
  keyboard_layout     = "en-us"
  boot_order          = ["scsi0"]
  on_boot             = false
  reboot_after_update = true
  scsi_hardware       = "virtio-scsi-single"
  started             = false
  agent {
    enabled = true
    type    = "virtio"
  }
  operating_system {
    type = "l26"
  }
  startup {
    order = 3
  }
  clone {
    full      = false
    node_name = local.proxmox_node
    vm_id     = var.ubuntu_server_24_04_template_vmid
  }
  cpu {
    cores   = 2
    sockets = 1
    type    = "host"
  }
  memory {
    dedicated = 4096
    floating  = 2048
  }
  initialization {
    datastore_id = "local-zfs"
    interface    = "ide1"
    ip_config {
      ipv4 {
        address = "${local.network.mgmt.unifi_controller}/${split("/", local.network.mgmt.subnet)[1]}"
        gateway = local.network.mgmt.gateway
      }
    }
    dns {
      servers = [local.network.mgmt.gateway]
    }
    user_account {
      keys     = [var.unifi_ssh_public_key]
      username = "mm"
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
    iothread     = false
    replicate    = false
    size         = 40
  }
  network_device {
    bridge = "vmbr0"
    model  = "virtio"
  }
  lifecycle {
    ignore_changes  = [clone]
    prevent_destroy = true
  }
}

moved {
  from = module.ai_dev["ai-dev-bgd"]
  to   = module.ai_dev
}

resource "local_sensitive_file" "cloud_init_ai_dev" {
  content = sensitive(templatefile("cloud_init.tftpl", {
    hostname           = "ai-dev"
    os_family          = "arch"
    tailscale_auth_key = local.proxmox_creds.tailscale_auth_key
  }))
  filename        = "${path.module}/files/ai-dev.cfg"
  file_permission = "0600"
}

resource "proxmox_virtual_environment_file" "cloud_init_ai_dev" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = local.proxmox_node
  overwrite    = true
  source_file {
    path      = local_sensitive_file.cloud_init_ai_dev.filename
    file_name = "ai-dev.yml"
    checksum  = local_sensitive_file.cloud_init_ai_dev.content_sha256
  }
}

resource "proxmox_virtual_environment_vm" "ai_dev" {
  depends_on          = [proxmox_virtual_environment_file.cloud_init_ai_dev]
  vm_id               = 110
  name                = "ai-dev"
  description         = "Managed by Terraform."
  node_name           = local.proxmox_node
  tags                = ["arch", "ai-dev"]
  bios                = "seabios"
  keyboard_layout     = "en-us"
  boot_order          = ["scsi0"]
  on_boot             = true
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
    node_name = local.proxmox_node
    vm_id     = var.arch_cloud_template_vmid
  }
  cpu {
    cores   = 4
    sockets = 1
    type    = "host"
  }
  memory {
    dedicated = 5120
    floating  = 5120
  }
  initialization {
    datastore_id        = "local-zfs"
    interface           = "ide1"
    vendor_data_file_id = "local:snippets/ai-dev.yml"
    user_account {
      keys     = [var.ai_dev_ssh_public_key]
      username = "michael"
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
    # iothread on a local-zfs zvol can hang the host under bursty guest I/O.
    iothread  = false
    replicate = false
    size      = 150
  }
  network_device {
    bridge = "vmbr1"
    model  = "virtio"
  }
  lifecycle {
    ignore_changes  = [clone]
    prevent_destroy = true
  }
}

moved {
  from = module.ai_dev.local_sensitive_file.cloud_init
  to   = local_sensitive_file.cloud_init_ai_dev
}

moved {
  from = module.ai_dev.proxmox_virtual_environment_file.cloud_init
  to   = proxmox_virtual_environment_file.cloud_init_ai_dev
}

moved {
  from = module.ai_dev.proxmox_virtual_environment_vm.this
  to   = proxmox_virtual_environment_vm.ai_dev
}
