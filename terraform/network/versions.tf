# UniFi network objects (VLANs + WLANs). Own root/state, apart from terraform/unifi/
# (the controller LXC). Provider: ubiquiti-community/unifi (paultyng archived, filipowm stale).
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
