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

# Proxmox auto-generates a user-data document that includes `users: - default`,
# which on the Arch cloud image creates the `arch` user and shadows any
# `users:` block in our vendor-data snippet. Setting ciuser/ssh_public_key here
# makes Proxmox emit `user: <ciuser>` in its user-data, which renames the
# default user — so we end up with a single account named `ciuser` that has
# the distro's default groups (wheel + sudo NOPASSWD on Arch) and the supplied
# SSH key.
variable "ciuser" {
  type    = string
  default = ""
}

variable "ssh_public_key" {
  type    = string
  default = ""
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
