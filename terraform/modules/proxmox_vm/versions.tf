terraform {
  required_version = ">= 1.6.0"
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc07"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.8.0"
    }
  }
}
