# Required 1Password items (auth inherited via direnv):
#   unifi_controller - Limited Admin (local-only) username/password
#   unifi_wlan_psks  - section "WLAN", PSK fields: dflt, kds, gst, mgmt (mgmt: 24+ char random)
data "onepassword_item" "unifi_controller" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "unifi_controller"
}

data "onepassword_item" "unifi_wlan_psks" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "unifi_wlan_psks"
}

locals {
  psk = data.onepassword_item.unifi_wlan_psks.section_map["WLAN"].field_map
}

provider "unifi" {
  username       = data.onepassword_item.unifi_controller.username
  password       = data.onepassword_item.unifi_controller.password
  api_url        = var.unifi_api_url
  allow_insecure = true # self-signed controller cert on the LAN
}
