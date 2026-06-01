# Pull the same Proxmox credentials the root config uses. The OP_SERVICE_ACCOUNT_TOKEN
# from terraform/.envrc is inherited here via direnv (parent .envrc applies to subdirs).
data "onepassword_item" "proxmox" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "proxmox_creds"
}

locals {
  # 3.x exposes custom fields via section_map (section label -> field label ->
  # value); the nested section[].field[] blocks come back empty. Top-level
  # .username/.password are the API token id/secret.
  scp = data.onepassword_item.proxmox.section_map["Terraform SCP"].field_map
}

provider "proxmox" {
  # Hit the node API on 443 (the reverse-proxied path the telmate root uses);
  # :8006 directly resolves to a Tailscale addr that refuses the connection.
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

# Debian 12 LXC template, fetched to the `local` datastore so the container build
# is self-contained (no manual `pveam download` needed).
resource "proxmox_download_file" "debian12" {
  content_type = "vztmpl"
  datastore_id = "local"
  node_name    = "proxmox"
  url          = var.template_url
}

# Isolated UniFi Network controller. Network management plane kept off docker-host.
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

  # Flat LAN for now (10.77.1.0/24). Static IP below the DHCP pool (.150-.250) so
  # the controller's inform URL is stable. Add `vlan_id` here once VLANs land.
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
