terraform {
  required_version = ">= 1.6.0"
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc06"
    }
    onepassword = {
      source  = "1password/onepassword"
      version = "3.0.1"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.6.1"
    }
  }
}



