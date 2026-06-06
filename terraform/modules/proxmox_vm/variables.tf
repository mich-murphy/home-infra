variable "name" {
  type = string
}

variable "vmid" {
  type = number
}

variable "clone_template_vmid" {
  type = number
}

variable "tags" {
  type = list(string)
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
  type    = number
  default = 100
}

variable "bridge" {
  type    = string
  default = "vmbr0"
}

variable "cloud_init_content" {
  type      = string
  sensitive = true
}

# Setting ciuser/ssh_public_key makes Proxmox emit `user: <ciuser>`, which renames the
# distro default user (vs. its `users: - default` creating a second `arch` account).
# Result: one account = ciuser, with the distro's default groups and the supplied key.
variable "ciuser" {
  type    = string
  default = ""
}

variable "ssh_public_key" {
  type    = string
  default = ""
}

variable "node_name" {
  type    = string
  default = "proxmox"
}
