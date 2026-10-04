terraform {
  required_version = ">= 1.7.0"
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.115.0"
    }
    onepassword = {
      source  = "1password/onepassword"
      version = "3.3.1"
    }
  }
}

