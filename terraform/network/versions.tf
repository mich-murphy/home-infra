# UniFi network objects (VLANs + WLANs); own root/state, separate from VM lifecycle.
# Provider ubiquiti-community/unifi: paultyng is archived, filipowm is stale.
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    unifi = {
      source  = "ubiquiti-community/unifi"
      version = "~> 0.49"
    }
    onepassword = {
      source  = "1password/onepassword"
      version = "3.3.1"
    }
  }
}
