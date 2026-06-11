variable "docker_host_ssh_public_key" {
  type        = string
  description = "SSH public key for the ansible user on the docker-host VM."
  default     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIH1TgAtlovn+B5ojfw7JRFDi8UxcTkHym30wEg6jekF"
}

variable "unifi_ssh_public_key" {
  type        = string
  description = "SSH public key for the mm user on the UniFi OS Server VM."
  default     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJB/6HGQa6B3kSZqVosObsWeiRSI5UsKkeBkLsxPlWqQ"
}

variable "ai_dev_ssh_public_key" {
  type        = string
  description = "SSH public key for the michael user on ai-dev VMs (the laptop key)."
  default     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIH1TgAtlovn+B5ojfw7JRFDi8UxcTkHym30wEg6jekF"
}

variable "truenas_macaddr" {
  type        = string
  description = "Pinned TrueNAS VM NIC MAC address. Provide via TF_VAR_truenas_macaddr in the ignored root .envrc."
  sensitive   = true
}

variable "docker_host_macaddr" {
  type        = string
  description = "Pinned docker-host VM NIC MAC address. Provide via TF_VAR_docker_host_macaddr in the ignored root .envrc."
  sensitive   = true
}

variable "ubuntu_server_24_04_template_vmid" {
  type        = number
  description = "Proxmox VMID for the ubuntu-server-24-04 cloud-init template."
  default     = 9003
}

variable "arch_cloud_template_vmid" {
  type        = number
  description = "Proxmox VMID for the arch-cloud cloud-init template."
  default     = 9002
}

variable "ai_devs" {
  type = map(object({
    vmid = number
  }))
  description = "AI dev VMs to provision, keyed by hostname."
  default = {
    "ai-dev-bgd" = { vmid = 110 }
  }
}

variable "enable_talos" {
  type        = bool
  description = "Provision the Talos control plane VM(s). Off until the K8s migration starts; the resource block is kept as a blueprint."
  default     = false
}
