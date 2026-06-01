# Auth mirrors terraform/unifi/: the OP_SERVICE_ACCOUNT_TOKEN from terraform/.envrc
# is inherited here via direnv. Create these 1Password items in the same vault before
# `terraform apply`:
#
#   unifi_controller   - username/password of a controller "Limited Admin, Local Access
#                        Only" user (NOT your personal account; 2FA is unsupported).
#   unifi_wlan_psks    - a section "WLAN" with one field per SSID PSK: dflt, kids, guest
#                        (and `sonos` if the fallback SSID is needed).
data "onepassword_item" "unifi_controller" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "unifi_controller"
}

data "onepassword_item" "unifi_wlan_psks" {
  vault = "5v7zjyz2kanfxgsui2jx735vum"
  title = "unifi_wlan_psks"
}

locals {
  # 3.x exposes custom fields via section_map (section label -> field label -> value).
  psk = data.onepassword_item.unifi_wlan_psks.section_map["WLAN"].field_map
}

provider "unifi" {
  username       = data.onepassword_item.unifi_controller.username
  password       = data.onepassword_item.unifi_controller.password
  api_url        = var.unifi_api_url
  allow_insecure = true # self-signed controller cert on the LAN
}
