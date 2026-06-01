# WLANs require an AP group + user group id; look these up from the controller defaults.
data "unifi_ap_group" "default" {
  name = var.unifi_ap_group_name
}

data "unifi_client_qos_rate" "default" {
  name = var.unifi_user_group_name
}

# Native/untagged LAN (VLAN 1 = MGMT). MGMT SSID attaches here so clients land untagged
# on VLAN 1 alongside the router, IPMI/BMC and controller. No RouterOS change needed.
data "unifi_network" "mgmt" {
  name = var.unifi_default_network_name
}

# third_party_gateway = the RB5009 owns L3/DHCP; the controller only tags the VLAN.
resource "unifi_network" "vlan" {
  for_each = var.wireless_vlans

  name                = upper(each.key)
  subnet              = each.value.subnet
  vlan                = each.value.vlan
  third_party_gateway = true
}

# DFLT — WPA3 transition (Sonos/AppleTV share this subnet; mDNS stays native).
resource "unifi_wlan" "dflt" {
  name            = "madviLANy"
  security        = "wpapsk"
  passphrase      = local.psk["dflt"].value
  wpa3_support    = true
  wpa3_transition = true
  pmf_mode        = "optional"
  network_id      = unifi_network.vlan["dflt"].id
  ap_group_ids    = [data.unifi_ap_group.default.id]
  user_group_id   = data.unifi_client_qos_rate.default.id
}

# KDS — WPA3-only.
resource "unifi_wlan" "kds" {
  name            = "madviLANy-kds"
  security        = "wpapsk"
  passphrase      = local.psk["kds"].value
  wpa3_support    = true
  wpa3_transition = false
  pmf_mode        = "required"
  network_id      = unifi_network.vlan["kds"].id
  ap_group_ids    = [data.unifi_ap_group.default.id]
  user_group_id   = data.unifi_client_qos_rate.default.id
}

# GST — WPA3 transition + L2 isolation.
resource "unifi_wlan" "gst" {
  name            = "madviLANy-gst"
  security        = "wpapsk"
  passphrase      = local.psk["gst"].value
  wpa3_support    = true
  wpa3_transition = true
  pmf_mode        = "optional"
  is_guest        = true
  l2_isolation    = true
  network_id      = unifi_network.vlan["gst"].id
  ap_group_ids    = [data.unifi_ap_group.default.id]
  user_group_id   = data.unifi_client_qos_rate.default.id
}

# MGMT — WPA3-only, hidden admin SSID on native VLAN 1 (router, IPMI/BMC, controller).
# No l2_isolation: those are peer hosts on VLAN 1, isolation would block IPMI + controller.
# wpa3_transition=false: no WPA2 downgrade path; security rests on WPA3-SAE + long PSK.
resource "unifi_wlan" "mgmt" {
  name            = "madviLANy-mgmt"
  security        = "wpapsk"
  passphrase      = local.psk["mgmt"].value
  wpa3_support    = true
  wpa3_transition = false
  pmf_mode        = "required"
  hide_ssid       = true
  network_id      = data.unifi_network.mgmt.id
  ap_group_ids    = [data.unifi_ap_group.default.id]
  user_group_id   = data.unifi_client_qos_rate.default.id
}

# Fallback if a legacy Sonos won't join WPA3: uncomment, add a `sonos` PSK field (DFLT keeps mDNS native).
# resource "unifi_wlan" "sonos" {
#   name            = "madviLANy-sonos"
#   security        = "wpapsk"
#   passphrase      = local.psk["sonos"].value
#   wpa3_support    = false
#   wpa3_transition = false
#   pmf_mode        = "disabled"
#   wlan_band       = "2g"
#   network_id      = unifi_network.vlan["dflt"].id
#   ap_group_ids    = [data.unifi_ap_group.default.id]
#   user_group_id   = data.unifi_client_qos_rate.default.id
# }
