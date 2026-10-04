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

## Guest name resolution

When a VM leaves its cloud-init nameserver or search domain unset, Proxmox
fills that setting from the host's own `/etc/resolv.conf`, each one
independently. Tailscale owns that file on this host, so an unset nameserver
hands the guest MagicDNS (`100.100.100.100`) and an unset search domain hands
it the tailnet domain. MagicDNS answers SERVFAIL for public names on a guest's
physical interface.

Every cloud-init guest therefore sets both from `local.guest_dns` in
`terraform/main.tf`: the router, `network.mgmt.gateway`, which RouterOS DHCP
also hands SRV and the DMZ, and `home.arpa`, the special-use home network
domain (RFC 8375). Proxmox appends the search domain to the VM name to form the
FQDN that cloud-init writes to `/etc/hosts`, so guests built from now on are
`<name>.home.arpa`. Both template scripts set the same values for clones that
Terraform does not configure. `tests/terraform-cloud-init.sh`, part of the
Terraform quality gate, fails any `initialization` block that lacks either
setting, and any DMZ guest that requests IPv6.

A completed template is a no-op, so templates built before this keep their old
settings. Align them by hand on the Proxmox host:

```sh
qm set 9002 --nameserver 10.77.1.1 --searchdomain home.arpa
qm set 9003 --searchdomain home.arpa
```

## Changing a running guest's cloud-init settings

The provider applies a change to a VM's `initialization` block (DNS, IP
configuration, user account) in place. It updates the VM configuration and
regenerates the cloud-init drive. Because `reboot_after_update = true`, it then
shuts a running guest down and starts it again within the same apply. The VM
and its disks are not replaced. A guest that Terraform keeps stopped (VM 111)
stays stopped and picks up the new drive at its next start.

Proxmox derives the NoCloud `instance-id` from a hash of the generated
user-data and network configuration, so any such change gives the guest a new
instance ID. Cloud-init then treats the next boot as a new instance's first
boot and re-runs its per-instance modules:

- SSH host keys are deleted and regenerated.
- The cloud-init user is set up again: missing keys and sudo rules return, and
  a Proxmox-held password is set again where one exists (VM 111).
- `package_upgrade` upgrades every package during boot.
- The vendor-data runs again: it writes `/etc/tailscale/authkey` from the
  snippet, repeats the package and Tailscale installs and calls `tailscale up`
  with that key.

This is not hypothetical. docker-host and ai-dev each carry four instance
directories under `/var/lib/cloud/instances`, and their SSH host keys date from
the most recent one, which coincides with an earlier Terraform apply.

Pinning the instance ID is not an option for an existing guest: it needs a
custom meta-data snippet, and the provider replaces the VM when
`meta_data_file_id` changes. Before applying an `initialization` change to a
running guest, make cloud-init trust its cached instance instead:

```sh
echo 'manual_cache_clean: true' | sudo tee /etc/cloud/cloud.cfg.d/99-manual-cache-clean.cfg
```

Cloud-init then does not compare instance IDs, so the reboot re-runs nothing
and the guest keeps the network configuration it rendered at first boot. The
new settings take effect in the guest only when it is re-provisioned. That
loses nothing on the live guests: ai-dev's Ansible drop-in already pins its
resolver and IPv6 policy, and docker-host takes the router's resolver from
DHCP. Leave the setting in place: Proxmox regenerates the drive at every start,
and a Proxmox upgrade that changes the generated user-data would otherwise
cause the same re-run. To re-provision a guest deliberately, run
`cloud-init clean`.

VM 111 can only take the setting while it runs. Start it as for any controller
work, add the file, then apply; the provider stops it again.

After the apply, confirm on the guest that `/var/lib/cloud/data/instance-id`
and `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` are unchanged, and on the
Proxmox host that `qm config <vmid>` shows the new `nameserver` and
`searchdomain`.

## References

- [Proxmox `Cloudinit.pm`](https://git.proxmox.com/?p=qemu-server.git;a=blob;f=src/PVE/QemuServer/Cloudinit.pm):
  `get_dns_conf` (host fallback) and `nocloud_gen_metadata` (instance ID)
- [bpg/proxmox v0.114.0 `vm.go`](https://github.com/bpg/terraform-provider-proxmox/blob/v0.114.0/proxmoxtf/resource/vm/vm.go):
  `vmUpdate` (cloud-init rebuild and reboot) and the `initialization` schema
- [cloud-init first boot determination](https://docs.cloud-init.io/en/latest/explanation/first_boot.html)
