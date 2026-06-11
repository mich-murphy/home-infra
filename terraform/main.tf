data "onepassword_item" "proxmox" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "proxmox_creds"
}

locals {
  proxmox_node  = "proxmox"
  srv_vlan_id   = 20
  talos_version = "v1.13.3"
  # Factory schematic must match talos/schematic.yaml (i915, intel-ucode,
  # qemu-guest-agent, util-linux-tools).
  talos_schematic_id = "97349bd8a02320e952ef34bdc1369278958bf77fb1b1cbddb62ec6719777a7b6"
  scp                = data.onepassword_item.proxmox.section_map["Terraform SCP"].field_map
  proxmox_creds = {
    username = local.scp["scp username"].value
    password = local.scp["scp password"].value
    host     = local.scp["hostname"].value
    # use an ephemeral/tagged single-use key; the previous shared key leaked into
    # cloud-init logs and must be rotated in the Tailscale admin console
    tailscale_auth_key = local.scp["tailscale authkey"].value
  }
}

provider "proxmox" {
  endpoint  = "https://${local.proxmox_creds.host}:8006"
  api_token = "${data.onepassword_item.proxmox.username}=${data.onepassword_item.proxmox.password}"
  insecure  = true
  ssh {
    agent    = false
    username = local.proxmox_creds.username
    password = local.proxmox_creds.password
    node {
      name    = local.proxmox_node
      address = local.proxmox_creds.host
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
  on_boot             = !var.enable_talos
  reboot_after_update = true
  scsi_hardware       = "virtio-scsi-single"
  # The Talos VM replaces docker-host: the same apply that creates it stops
  # this VM (and takes the iGPU below). Disks are kept for rollback.
  started = !var.enable_talos
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
    dedicated = 10240
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
  # Intel iGPU passed through for Plex/Jellyfin hardware transcoding. A PCI
  # device can only attach to one VM; enable_talos hands it to the Talos VM.
  dynamic "hostpci" {
    for_each = var.enable_talos ? [] : [1]
    content {
      device = "hostpci0"
      id     = "0000:00:02.0"
      rombar = true
    }
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
  }
  initialization {
    datastore_id = "local-zfs"
    interface    = "ide1"
    ip_config {
      ipv4 {
        address = "10.77.1.10/24"
        gateway = "10.77.1.1"
      }
    }
    dns {
      servers = ["10.77.1.1"]
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

# Install media matching talos/schematic.yaml; refreshed when the schematic
# or version locals change.
resource "proxmox_download_file" "talos_iso" {
  count        = var.enable_talos ? 1 : 0
  content_type = "iso"
  datastore_id = "local"
  node_name    = local.proxmox_node
  file_name    = "talos-${local.talos_version}-metal-amd64.iso"
  url          = "https://factory.talos.dev/image/${local.talos_schematic_id}/${local.talos_version}/metal-amd64.iso"
}

# Single-node K8s cluster (control plane + worker); gated by enable_talos
# until cutover. Sized to absorb the docker-host workload within the 31GiB
# RAM ceiling of the Proxmox host.
resource "proxmox_virtual_environment_vm" "talos_control_plane" {
  count               = var.enable_talos ? 1 : 0
  vm_id               = 200 + count.index
  name                = "talos-prod-${count.index + 1}"
  description         = "Talos ${local.talos_version} (factory schematic ${substr(local.talos_schematic_id, 0, 12)})"
  node_name           = local.proxmox_node
  tags                = ["kubernetes"]
  bios                = "ovmf"
  boot_order          = ["scsi0", "ide1"]
  machine             = "q35"
  on_boot             = true
  reboot_after_update = true
  scsi_hardware       = "virtio-scsi-pci"
  started             = true
  agent {
    enabled = true
  }
  operating_system {
    type = "l26"
  }
  startup {
    order = 2
  }
  cpu {
    cores = 8
    type  = "host"
  }
  memory {
    dedicated = 12288
  }
  serial_device {
    device = "socket"
  }
  # Talos install disk.
  disk {
    cache        = "writethrough"
    datastore_id = "local-zfs"
    discard      = "on"
    file_format  = "raw"
    interface    = "scsi0"
    size         = 100
  }
  # OpenEBS LocalPV hostpath volume (UserVolumeConfig in the machine config).
  disk {
    cache        = "writethrough"
    datastore_id = "local-zfs"
    discard      = "on"
    file_format  = "raw"
    interface    = "scsi1"
    size         = 128
  }
  cdrom {
    file_id   = proxmox_download_file.talos_iso[0].id
    interface = "ide1"
  }
  efi_disk {
    datastore_id = "local-zfs"
    type         = "4m"
  }
  network_device {
    bridge  = "vmbr0"
    model   = "virtio"
    vlan_id = local.srv_vlan_id
  }
  # iGPU for Plex/Jellyfin/Immich transcoding; handed over from docker-host
  # by the same enable_talos gate (a PCI device attaches to one VM only).
  dynamic "hostpci" {
    for_each = var.enable_talos ? [1] : []
    content {
      device = "hostpci0"
      id     = "0000:00:02.0"
      pcie   = true
      rombar = false
    }
  }
  # Pairs with the WatchdogTimerConfig machine config document: the node
  # hard-resets if Talos stops feeding the timer.
  watchdog {
    model  = "i6300esb"
    action = "reset"
  }
}

module "ai_dev" {
  for_each            = var.ai_devs
  source              = "./modules/proxmox_vm"
  name                = each.key
  vmid                = each.value.vmid
  clone_template_vmid = var.arch_cloud_template_vmid
  tags                = ["arch", "ai-dev"]
  cores               = 2
  memory_mib          = 4096
  disk_size           = 150
  bridge              = "vmbr1"
  ciuser              = "michael"
  ssh_public_key      = var.ai_dev_ssh_public_key
  cloud_init_content = templatefile("cloud_init.tftpl", {
    hostname           = each.key
    os_family          = "arch"
    tailscale_auth_key = local.proxmox_creds.tailscale_auth_key
  })
  node_name = local.proxmox_node
}
