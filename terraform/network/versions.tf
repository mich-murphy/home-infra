# Separate Terraform root for UniFi *network objects* (VLAN-only networks + WLANs),
# kept apart from terraform/unifi/ (which owns the controller LXC lifecycle via the
# bpg/proxmox provider). Splitting the state means a WLAN/network typo can never
# affect the plan for the controller container itself.
#
# Provider choice (verified June 2026): ubiquiti-community/unifi is the actively
# maintained fork (community-governed, 35+ contributors, releases through 2026).
# paultyng/unifi is archived; filipowm/unifi is ~14 months stale.
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    unifi = {
      source  = "ubiquiti-community/unifi"
      version = "~> 0.41"
    }
    onepassword = {
      source  = "1password/onepassword"
      version = "3.3.1"
    }
  }
}
