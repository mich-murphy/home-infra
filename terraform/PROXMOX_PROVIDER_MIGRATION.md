# Proxmox Provider State Migration

Run these once from `terraform/` before the first init/plan/apply of the
bpg/proxmox migration in an existing worktree. They remove legacy
Telmate-managed objects from state without destroying the real VMs. The
`import` blocks in `main.tf` then import the same VMs under bpg resource
addresses during apply.

```sh
terraform state rm \
  proxmox_vm_qemu.truenas \
  proxmox_vm_qemu.cloud_init_docker_host \
  'module.ai_dev["ai-dev-bgd"].proxmox_vm_qemu.this' \
  'module.ai_dev["ai-dev-bc"].proxmox_vm_qemu.this'
```

These cleanup entries remove no-longer-used upload helpers from state. They are
safe to omit, but keeping state tidy avoids no-op destroy steps during the
migration plan.

```sh
terraform state rm \
  terraform_data.cloud_init_config \
  local_file.cloud_init_agents \
  'module.ai_dev["ai-dev-bgd"].terraform_data.cloud_init_upload' \
  'module.ai_dev["ai-dev-bc"].terraform_data.cloud_init_upload'
```

After the migration apply succeeds, remove the `import` blocks from `main.tf`.
