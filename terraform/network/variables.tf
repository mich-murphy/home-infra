variable "unifi_api_url" {
  type        = string
  description = "UniFi OS Server URL (LAN). Do NOT include the /api path; the SDK discovers the Network API path."
  default     = "https://10.77.1.10:11443"
}

# Controller defaults the SSIDs attach to; override if labelled differently (Settings -> WiFi).
variable "unifi_ap_group_name" {
  type    = string
  default = "All APs"
}

variable "unifi_user_group_name" {
  type    = string
  default = "Default"
}

variable "sonos_wlan_psk_field" {
  type        = string
  description = "1Password WLAN field used for the Sonos SSID PSK. Defaults to dflt until a dedicated sonos field exists."
  default     = "dflt"
}

# Wireless VLANs only (MGMT/SRV/DMZ are wired — see the routeros role). `subnet` (gateway
# CIDR on the RB5009) is required by the schema but not served by the controller.
variable "wireless_vlans" {
  type = map(object({
    vlan   = number
    subnet = string
  }))
  default = {
    dflt = { vlan = 30, subnet = "10.77.30.1/24" }
    kds  = { vlan = 50, subnet = "10.77.50.1/24" }
    gst  = { vlan = 60, subnet = "10.77.60.1/24" }
  }
}
