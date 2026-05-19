---
name: ansible-run
description: Validate and run Ansible playbooks against homelab hosts. Use when making changes to host configuration.
disable-model-invocation: true
argument-hint: [host-name]
---

# Ansible Run

Validate and run Ansible configuration against $ARGUMENTS.

## Steps

1. Read `ansible/run.yaml` and relevant roles in `ansible/roles/` to understand what will be applied
2. Read `ansible/hosts.ini` to confirm `$ARGUMENTS` is a valid host
3. Syntax check:
   ```
   cd ansible && ansible-playbook run.yaml --syntax-check
   ```
4. Dry run to preview changes:
   ```
   cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit $ARGUMENTS --check --diff
   ```
5. Review the diff output and summarise changes for the user
6. Only run the actual playbook after explicit user confirmation:
   ```
   cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit $ARGUMENTS
   ```
7. Never decrypt or display vault secrets in output
