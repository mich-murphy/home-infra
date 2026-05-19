---
name: terraform-plan
description: Validate and plan Terraform changes for Proxmox VM provisioning. Use before applying any infrastructure changes.
---

# Terraform Plan

Review and plan Terraform infrastructure changes.

## Steps

1. Read `terraform/main.tf`, `terraform/variables.tf`, and `terraform/versions.tf` to understand the current state
2. Validate the configuration:
   ```
   cd terraform && terraform validate
   ```
3. Generate a plan:
   ```
   cd terraform && terraform plan
   ```
4. Review the plan output and highlight:
   - Resources being created, modified, or destroyed
   - Any changes to VM resources (CPU, RAM, disk) that could affect running workloads
   - Changes to cloud-init that require VM reprovisioning
   - Any security-sensitive changes (SSH keys, network config)
5. Never run `terraform apply` without explicit user confirmation
6. Never commit `.tfstate` files or provider credentials
