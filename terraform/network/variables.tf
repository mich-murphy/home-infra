variable "unifi_api_url" {
  type        = string
  description = "UniFi Network controller API URL (LAN). Do NOT include the /api path; the SDK discovers it."
  default     = "https://10.77.1.10:8443"
}

# Wireless VLANs only. MGMT (1), SRV (20), and DMZ (physical NIC2) carry no SSID, so
# they are not declared here — they live in the RouterOS Ansible role. The router owns
# L3/DHCP for every VLAN; these UniFi networks exist purely to tag the SSID traffic
# (third_party_gateway = true). `subnet` is the router-side gateway CIDR, required by
# the schema but not served by the controller.
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
