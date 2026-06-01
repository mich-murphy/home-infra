variable "unifi_api_url" {
  type        = string
  description = "UniFi Network controller API URL (LAN). Do NOT include the /api path; the SDK discovers it."
  default     = "https://10.77.1.10:8443"
}

# Controller defaults the SSIDs attach to. Override if your controller labels them
# differently (Settings -> WiFi -> AP Groups, and the user group / QoS rate name).
variable "unifi_ap_group_name" {
  type    = string
  default = "Default"
}

variable "unifi_user_group_name" {
  type    = string
  default = "Default"
}

# Wireless VLANs only (MGMT/SRV/DMZ are wired — see the routeros role). `subnet` is
# the router-side gateway CIDR; required by the schema but not served by the controller.
variable "wireless_vlans" {
  type = map(object({
    vlan   = number
    subnet = string # gateway CIDR on the RB5009
  }))
  default = {
    dflt = { vlan = 30, subnet = "10.77.30.1/24" }
    kds  = { vlan = 50, subnet = "10.77.50.1/24" }
    gst  = { vlan = 60, subnet = "10.77.60.1/24" }
  }
}
