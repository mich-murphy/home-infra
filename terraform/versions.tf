terraform {
  required_version = ">= 1.6.0"
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.109.0"
    }
    onepassword = {
      source  = "1password/onepassword"
      version = "3.3.1"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.9.0"
    }
  }
}

