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
