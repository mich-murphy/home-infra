# UniFi network objects (VLANs + WLANs); own root/state, separate from terraform/unifi/ (the LXC).
# Provider ubiquiti-community/unifi: paultyng is archived, filipowm is stale.
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
