variable "unifi_ssh_public_key" {
  type        = string
  description = "SSH public key authorised for root on the unifi-controller LXC (used by Ansible over the LAN)."
  default     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIH1TgAtlovn+B5ojfw7JRFDi8UxcTkHym30wEg6jekF"
}

variable "template_url" {
  type        = string
  description = "URL of the Debian 12 LXC template fetched to the `local` datastore. Verify the version is still published before apply (pveam available --section system)."
  default     = "http://download.proxmox.com/images/system/debian-12-standard_12.12-1_amd64.tar.zst"
}
