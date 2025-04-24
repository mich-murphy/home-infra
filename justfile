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

## ansible
run:
  cd ansible && ansible-playbook run.yml --vault-password-file .vaultpass

reqs:
  cd ansible && ansible-galaxy install -r requirements.yml
