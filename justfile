#!/usr/bin/env -S just --justfile
# ^ A shebang isn't required, but allows a justfile to be executed
#   like a script, with `./justfile test`, for example.

## terraform
init:
  umask 077; cd terraform && terraform init

apply:
  umask 077; cd terraform && terraform apply

destroy:
  umask 077; cd terraform && terraform destroy

# UniFi network objects (VLAN-only networks + WLANs) via ubiquiti-community/unifi
network-init:
  umask 077; cd terraform/network && terraform init

network-plan:
  umask 077; cd terraform/network && terraform plan

network-apply:
  # The UniFi provider can crash when creating multiple network resources concurrently.
  umask 077; cd terraform/network && terraform apply -parallelism=1

## ansible
run HOST:
  cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit {{HOST}}

edit:
  cd ansible && ansible-vault edit group_vars/secrets.yaml --vault-password-file .vaultpass

reqs:
  cd ansible && ansible-galaxy install -r requirements.yaml

routeros-scaffold:
  cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit routeros

routeros-verify-scaffold:
  cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit routeros --tags verify

routeros-verify:
  cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit routeros --tags verify -e routeros_enable_vlan_filtering=true -e routeros_enable_default_drop=true

routeros:
  cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit routeros --tags services,oob,vlans,dmz,dhcp,firewall,bridge,vlan-filtering,default-drop,verify -e routeros_enable_vlan_filtering=true -e routeros_enable_default_drop=true
