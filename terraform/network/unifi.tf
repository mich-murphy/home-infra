# WLANs require an AP group + user group id; look these up from the controller defaults.
data "unifi_ap_group" "default" {
  name = var.unifi_ap_group_name
}

data "unifi_client_qos_rate" "default" {
  name = var.unifi_user_group_name
}

resource "unifi_setting" "mgmt" {
  mgmt = {
    auto_upgrade = true
    ssh_enabled  = false
  }
}

# third_party_gateway = the RB5009 owns L3/DHCP; the controller only tags the VLAN.
resource "unifi_network" "vlan" {
  for_each            = var.wireless_vlans
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
  bss_transition  = true
  iapp_enabled    = true
  group_rekey     = 0
  dtim_6e         = 3
  dtim_na         = 3
  dtim_ng         = 1

  minimum_data_rate_2g_kbps = 1000
  minimum_data_rate_5g_kbps = 6000

  mac_filter = {
    enabled = false
    policy  = "allow"
  }

  network_id    = unifi_network.vlan["dflt"].id
  ap_group_ids  = [data.unifi_ap_group.default.id]
  user_group_id = data.unifi_client_qos_rate.default.id
}

# KDS — WPA3-only.
resource "unifi_wlan" "kds" {
  name            = "madviLANy-kds"
  security        = "wpapsk"
  passphrase      = local.psk["kds"].value
  wpa3_support    = true
  wpa3_transition = false
  pmf_mode        = "required"
  bss_transition  = true
  iapp_enabled    = true
  group_rekey     = 0
  dtim_6e         = 3
  dtim_na         = 3
  dtim_ng         = 1

  minimum_data_rate_2g_kbps = 1000
  minimum_data_rate_5g_kbps = 6000

  mac_filter = {
    enabled = false
    policy  = "allow"
  }

  network_id    = unifi_network.vlan["kds"].id
  ap_group_ids  = [data.unifi_ap_group.default.id]
  user_group_id = data.unifi_client_qos_rate.default.id
}

# GST — WPA3 transition on a plain VLAN; RouterOS enforces guest routing policy.
resource "unifi_wlan" "gst" {
  name            = "madviLANy-gst"
  security        = "wpapsk"
  passphrase      = local.psk["gst"].value
  wpa3_support    = true
  wpa3_transition = true
  pmf_mode        = "optional"
  bss_transition  = true
  iapp_enabled    = true
  group_rekey     = 0
  dtim_6e         = 3
  dtim_na         = 3
  dtim_ng         = 1

  minimum_data_rate_2g_kbps = 1000
  minimum_data_rate_5g_kbps = 6000

  mac_filter = {
    enabled = false
    policy  = "allow"
  }

  is_guest      = false
  l2_isolation  = true
  network_id    = unifi_network.vlan["gst"].id
  ap_group_ids  = [data.unifi_ap_group.default.id]
  user_group_id = data.unifi_client_qos_rate.default.id
}

# Sonos legacy compatibility. Stays on DFLT so discovery/mDNS remains native.
resource "unifi_wlan" "sonos" {
  name                       = "madviLANy-sonos"
  security                   = "wpapsk"
  passphrase                 = local.psk[var.sonos_wlan_psk_field].value
  wpa3_support               = false
  wpa3_transition            = false
  pmf_mode                   = "disabled"
  iapp_enabled               = true
  group_rekey                = 3600
  dtim_6e                    = 3
  dtim_na                    = 3
  dtim_ng                    = 1
  wlan_band                  = "both"
  wlan_bands                 = ["2g", "5g"]
  no2ghz_oui                 = false
  minrate_setting_preference = "auto"
  minimum_data_rate_2g_kbps  = 1000
  minimum_data_rate_5g_kbps  = 6000

  mac_filter = {
    enabled = false
    policy  = "allow"
  }

  network_id    = unifi_network.vlan["dflt"].id
  ap_group_ids  = [data.unifi_ap_group.default.id]
  user_group_id = data.unifi_client_qos_rate.default.id
}
