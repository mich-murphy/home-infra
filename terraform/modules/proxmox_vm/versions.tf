terraform {
  required_version = ">= 1.6.0"
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
    local = {
      source = "hashicorp/local"
    }
  }
}
