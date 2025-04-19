terraform {
  required_version = ">= 1.6.0"
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.1-rc8"
    }
    onepassword = {
      source  = "1password/onepassword"
      version = "2.1.2"
    }
  }
}

provider "onepassword" {
  account = "xportal.1password.com"
}

data "onepassword_item" "proxmox" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "proxmox_creds"
}

provider "proxmox" {
  pm_api_url          = data.onepassword_item.proxmox.url
  pm_api_token_id     = data.onepassword_item.proxmox.username
  pm_api_token_secret = data.onepassword_item.proxmox.password
  pm_tls_insecure     = true # Set to false in production
}

# create template prior to applying
# reference: https://registry.terraform.io/providers/Telmate/proxmox/latest/docs/guides/cloud-init%2520getting%2520started#creating-a-cloud-init-template
resource "proxmox_vm_qemu" "cloudinit-docker-host" {
  vmid             = 102
  name             = "docker-host"
  target_node      = "proxmox"
  agent            = 1
  cores            = 4
  memory           = 8192
  boot             = "order=scsi0"        # has to be the same as the OS disk of the template
  clone            = "ubuntu-server-2404" # The name of the template
  scsihw           = "virtio-scsi-single"
  vm_state         = "running"
  automatic_reboot = true

  # Cloud-Init configuration
  cicustom   = "vendor=local:snippets/qemu-guest-agent.yml" # /var/lib/vz/snippets/qemu-guest-agent.yml
  ciupgrade  = true
  ipconfig0  = "ip=dhcp,ip6=dhcp"
  skip_ipv6  = true
  ciuser     = "mm"
  cipassword = data.onepassword_item.proxmox.section[0].field[0].value
  sshkeys    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIH1TgAtlovn+B5ojfw7JRFDi8UxcTkHym30wEg6jekF"

  # Most cloud-init images require a serial device for their display
  serial {
    id = 0
  }

  disks {
    scsi {
      scsi0 {
        # We have to specify the disk from our template, else Terraform will think it's not supposed to be there
        disk {
          storage = "local-zfs"
          # The size of the disk should be at least as big as the disk in the template. If it's smaller, the disk will be recreated
          size = "128G"
        }
      }
    }
    ide {
      # Some images require a cloud-init disk on the IDE controller, others on the SCSI or SATA controller
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
