variable "docker_host_ssh_public_key" {
  type        = string
  description = "SSH public key for the ansible user on the docker-host VM."
  default     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIH1TgAtlovn+B5ojfw7JRFDi8UxcTkHym30wEg6jekF"
}
