provider "onepassword" {
  account = "xportal.1password.com"
}

provider "proxmox" {
  pm_api_url          = data.onepassword_item.proxmox.url
  pm_api_token_id     = data.onepassword_item.proxmox.username
  pm_api_token_secret = data.onepassword_item.proxmox.password
  pm_tls_insecure     = true # Set to false in production
}


