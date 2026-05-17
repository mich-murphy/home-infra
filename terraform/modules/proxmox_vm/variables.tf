variable "name" {
  type = string
}

variable "vmid" {
  type = number
}

variable "clone_template" {
  type = string
}

variable "tags" {
  type = string
}

variable "cores" {
  type    = number
  default = 4
}

variable "memory_mib" {
  type    = number
  default = 8192
}

variable "disk_size" {
  type    = string
  default = "100G"
}

variable "bridge" {
  type    = string
  default = "vmbr0"
}

variable "cloud_init_content" {
  type      = string
  sensitive = true
}

variable "proxmox_host" {
  type      = string
  sensitive = true
}

variable "proxmox_user" {
  type      = string
  sensitive = true
}

variable "proxmox_password" {
  type      = string
  sensitive = true
}
