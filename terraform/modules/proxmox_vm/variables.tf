variable "name" {
  type        = string
  description = "VM name; also used for the cloud-init snippet filename."
}

variable "vmid" {
  type        = number
  description = "Proxmox VMID for the VM."
}

variable "clone_template_vmid" {
  type        = number
  description = "VMID of the cloud-init template to clone from."
}

variable "tags" {
  type        = list(string)
  description = "Proxmox tags applied to the VM."
}

variable "cores" {
  type        = number
  description = "Number of CPU cores."
  default     = 4
}

variable "memory_mib" {
  type        = number
  description = "Dedicated memory in MiB."
  default     = 8192
}

variable "disk_size" {
  type        = number
  description = "Root disk size in GiB."
  default     = 100
}

variable "bridge" {
  type        = string
  description = "Host bridge for the VM network device."
  default     = "vmbr0"
}

variable "cloud_init_content" {
  type        = string
  description = "Rendered cloud-init vendor-data uploaded as a Proxmox snippet."
  sensitive   = true
}

# Setting ciuser/ssh_public_key makes Proxmox emit `user: <ciuser>`, which renames the
# distro default user (vs. its `users: - default` creating a second `arch` account).
# Result: one account = ciuser, with the distro's default groups and the supplied key.
variable "ciuser" {
  type        = string
  description = "Cloud-init username; replaces the distro default user."
  default     = ""
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key authorized for the ciuser account."
  default     = ""
}

variable "node_name" {
  type        = string
  description = "Proxmox node to place the VM on."
  default     = "proxmox"
}
