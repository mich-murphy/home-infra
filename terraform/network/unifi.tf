# Default AP group + user group (client QoS rate) the WLANs attach to. The WLAN
# resource requires user_group_id; ubiquiti-community exposes the default user group
# via the unifi_client_qos_rate data source.
data "unifi_ap_group" "default" {}

data "unifi_client_qos_rate" "default" {}

# VLAN-only networks: third_party_gateway=true tells the controller the RB5009 is the
# gateway/DHCP, so only the VLAN tag + basic settings are pushed. network_isolation is
# left off because inter-VLAN policy is enforced on the router, not the AP.
resource "unifi_network" "vlan" {
  for_each = var.wireless_vlans

  name                = upper(each.key)
  subnet              = each.value.subnet
  vlan                = each.value.vlan
  third_party_gateway = true
}

# --- WLANs (SSID -> VLAN tag) -------------------------------------------------
# Main SSID -> DFLT VLAN. WPA3 transition so WPA3-capable clients negotiate WPA3 while
# an older Sonos can still fall back to WPA2 on the same subnet (keeps AirPlay/Sonos
# mDNS native — no reflector). If the Sonos refuses to join, add a second SSID below
# (commented) on the SAME DFLT network_id.
resource "unifi_wlan" "main" {
  name            = "Skynet"
  security        = "wpapsk"
  passphrase      = local.psk["dflt"].value
  wpa3_support    = true
  wpa3_transition = true
  pmf_mode        = "optional"
  network_id      = unifi_network.vlan["dflt"].id
  ap_group_ids    = [data.unifi_ap_group.default.id]
  user_group_id   = data.unifi_client_qos_rate.default.id
}

# Kids SSID -> KDS VLAN. WPA3-only (modern, controlled devices).
resource "unifi_wlan" "kids" {
  name            = "Skynet-Jnr"
  security        = "wpapsk"
  passphrase      = local.psk["kids"].value
  wpa3_support    = true
  wpa3_transition = false
  pmf_mode        = "required"
  network_id      = unifi_network.vlan["kds"].id
  ap_group_ids    = [data.unifi_ap_group.default.id]
  user_group_id   = data.unifi_client_qos_rate.default.id
}

# Guest SSID -> GST VLAN. WPA2/WPA3 transition (arbitrary guest devices) + L2 isolation.
resource "unifi_wlan" "guest" {
  name            = "Skynet-Guest"
  security        = "wpapsk"
  passphrase      = local.psk["guest"].value
  wpa3_support    = true
  wpa3_transition = true
  pmf_mode        = "optional"
  is_guest        = true
  l2_isolation    = true
  network_id      = unifi_network.vlan["gst"].id
  ap_group_ids    = [data.unifi_ap_group.default.id]
  user_group_id   = data.unifi_client_qos_rate.default.id
}

# Fallback only if an older Sonos won't join the WPA3-transition main SSID. Same DFLT
# network_id => same subnet => mDNS stays native. Uncomment + add a `sonos` PSK field.
#
# resource "unifi_wlan" "sonos" {
#   name            = "Skynet-Sonos"
#   security        = "wpapsk"
#   passphrase      = local.psk["sonos"].value
#   wpa3_support    = false           # WPA2 only for legacy Sonos
#   wpa3_transition = false
#   pmf_mode        = "disabled"
#   wlan_band       = "2g"            # older Sonos is 2.4GHz
#   network_id      = unifi_network.vlan["dflt"].id
#   ap_group_ids    = [data.unifi_ap_group.default.id]
#   user_group_id   = data.unifi_client_qos_rate.default.id
# }
