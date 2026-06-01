# OP_SERVICE_ACCOUNT_TOKEN inherited from terraform/.envrc via direnv (parent applies to subdirs).
data "onepassword_item" "proxmox" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "proxmox_creds"
}

locals {
  # 3.x exposes custom fields via section_map; nested section[].field[] come back empty.
  # Top-level .username/.password are the API token id/secret.
  scp = data.onepassword_item.proxmox.section_map["Terraform SCP"].field_map
}

provider "proxmox" {
  # 443 via the reverse proxy; :8006 resolves to a Tailscale addr that refuses the connection.
  endpoint  = "https://proxmox.local.elmurphy.com"
  api_token = "${data.onepassword_item.proxmox.username}=${data.onepassword_item.proxmox.password}"
  insecure  = false

  ssh {
    agent    = false
    username = local.scp["scp username"].value
    password = local.scp["scp password"].value
    node {
      name    = "proxmox"
      address = local.scp["hostname"].value
    }
  }
}

# Fetched to `local` so the build is self-contained (no manual `pveam download`).
resource "proxmox_download_file" "debian12" {
  content_type = "vztmpl"
  datastore_id = "local"
  node_name    = "proxmox"
  url          = var.template_url
}

# Isolated controller LXC: keeps the network management plane off docker-host.
resource "proxmox_virtual_environment_container" "unifi" {
  node_name     = "proxmox"
  vm_id         = 103
  description   = "UniFi Network controller (managed by ansible roles/unifi)"
  tags          = ["lxc", "unifi"]
  unprivileged  = true
  start_on_boot = true

  cpu {
    cores = 2
  }

  memory {
    dedicated = 2048
  }

  disk {
    datastore_id = "local-zfs"
    size         = 12
  }

  operating_system {
    template_file_id = proxmox_download_file.debian12.id
    type             = "debian"
  }

  # Static IP below the DHCP pool (.150-.250) for a stable inform URL. Add `vlan_id` once VLANs land.
  initialization {
    hostname = "unifi-controller"

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
      keys = [var.unifi_ssh_public_key]
    }
  }

  network_interface {
    name   = "eth0"
    bridge = "vmbr0"
  }

  startup {
    order = 3
  }
}
