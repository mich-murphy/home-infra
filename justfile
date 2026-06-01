#!/usr/bin/env -S just --justfile
# ^ A shebang isn't required, but allows a justfile to be executed
#   like a script, with `./justfile test`, for example.

## terraform
init:
  cd terraform && terraform init

apply:
  cd terraform && terraform apply

destroy:
  cd terraform && terraform destroy

# UniFi controller LXC lives in its own root (bpg provider; see terraform/unifi/versions.tf)
unifi-init:
  cd terraform/unifi && terraform init

unifi-apply:
  cd terraform/unifi && terraform apply

## ansible
run HOST:
  cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit {{HOST}}

edit:
  cd ansible && ansible-vault edit group_vars/secrets.yaml --vault-password-file .vaultpass

reqs:
  cd ansible && ansible-galaxy install -r requirements.yaml
