# Separate Terraform root for the UniFi controller LXC.
#
# Why its own root (and state) rather than living in ../: the existing config
# uses telmate/proxmox and bpg/proxmox BOTH register provider type `proxmox`.
# Terraform rejects two different source addresses for the same provider type
# anywhere in a module tree, so the only clean way to run bpg alongside the
# telmate VMs is an isolated root. When the telmate->bpg migration happens, this
# folds back into ../ and this directory goes away.
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
