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
run HOST *TAGS:
  cd ansible && ansible-playbook -b run.yaml --limit {{HOST}} {{TAGS}}
