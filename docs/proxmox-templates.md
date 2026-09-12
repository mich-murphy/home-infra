# Proxmox cloud templates

The scripts in `terraform/scripts/` are host-local Proxmox administration
tools. Run them as root on the Proxmox host, not from a workstation. They
require `qm`, `pvesm`, `wget`, and `sha256sum`, plus available `local` and
`local-zfs` storage.

Both scripts require a versioned image URL and its published SHA256 so a
template build is reproducible. Moving `latest` or `current` URLs are not an
accepted build input.

Each script prints its own invocation and required variables when run without
them. The default template VMIDs are 9002 for Arch and 9003 for Ubuntu. `VMID` and
`NAME` may be overridden. Ubuntu first boot is bounded to 900 seconds by
default; override `FIRST_BOOT_TIMEOUT` only after checking the VM console and
cloud-init logs.

An existing completed template is a no-op. An existing non-template VM with the
target VMID is treated as a partial or conflicting build and stops execution.
The scripts never destroy it automatically; their failure output names the
exact inspection and recovery commands for the conflicting VMID.

Downloaded images are written to a `.partial` file, verified, and then renamed
into the Proxmox ISO cache. A failed build after `qm create` prints the relevant
inspection and cleanup commands.
