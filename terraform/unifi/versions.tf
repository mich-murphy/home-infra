# Separate root (and state): bpg/proxmox and telmate/proxmox both register provider type
# `proxmox`, which Terraform forbids in one module tree. Folds back into ../ after the
# telmate->bpg migration.
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.107.0"
    }
    onepassword = {
      source  = "1password/onepassword"
      version = "3.3.1"
    }
  }
}
