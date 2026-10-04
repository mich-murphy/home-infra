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
`meta_data_file_id` changes. Instead, the common role makes every cloud-init
guest trust its cached instance: it writes
`/etc/cloud/cloud.cfg.d/99-manual-cache-clean.cfg` with
`manual_cache_clean: true`. Before applying an `initialization` change to a
running guest, make sure the guest has it:

```sh
cd ansible
ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit <host> --tags cloud-init --check --diff
ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit <host> --tags cloud-init
```

VM 111 can only take the setting while it runs. Start it as for any controller
work, run the commands above with `--limit unifi-controller --tags
cloud-init,dns`, then apply; the provider stops it again.

After the apply, confirm on the guest that `/var/lib/cloud/data/instance-id`
and `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` are unchanged, and on the
Proxmox host that `qm config <vmid>` shows the new `nameserver` and
`searchdomain`.

### What a trusted cache keeps

Without the setting, cloud-init's local stage checks its cache at every boot.
NoCloud cannot confirm a cached instance ID without reading the drive, so the
check always fails (`cache invalid in datasource` in
`/var/log/cloud-init.log`), cloud-init reads the drive and compares the
instance ID it finds with `/var/lib/cloud/data/instance-id`. With
`manual_cache_clean: true` the local stage trusts the cache instead: it
restores the pickled datasource, `obj.pkl`, without reading the drive, so the
instance ID stays the same and the reboot re-runs no per-instance module.

The guest also keeps the network configuration it rendered at first boot.
Cloud-init applies network configuration only to a new instance, NoCloud's
default `boot-new-instance` update event, so a new nameserver, search domain
or IP setting reaches the guest only when it is re-provisioned. That loses
nothing on the live guests:

- ai-dev's networkd drop-in pins its resolver, drops the tailnet search domain
  and disables IPv6 on the physical interface, so the removed `ip6` setting
  needs no re-render either.
- docker-host's netplan names no nameserver; it takes the router's resolver
  from DHCP.
- unifi-controller's static configuration has named the router since it was
  built. Its physical interface keeps the tailnet search domain until it is
  re-provisioned, which does not change the resolver it uses. The unifi role
  asserts that resolver and a public lookup.

Leave the setting in place: Proxmox regenerates the drive at every start, and
anything that changes the generated user-data or network configuration, such
as a Proxmox upgrade, would otherwise cause the same re-run.

One case still re-provisions. When the guest's Python minor version changes,
cloud-init discards its cache at the next boot whatever the setting says,
reads the drive, and treats a different instance ID as a new instance.
Ubuntu 24.04 stays on Python 3.12, but ai-dev's Arch Linux takes each new
Python release. Once an `initialization` change has been applied to ai-dev,
treat the first reboot after a Python minor upgrade as a re-provision.

### Re-provisioning a guest deliberately

To make cloud-init run again as on a first boot, remove its cache and reboot:

```sh
sudo cloud-init clean --logs --reboot
```

With no cache to trust, the next boot reads the drive and runs every
per-instance module again: new SSH host keys, the cloud-init user, the drive's
current network configuration and the vendor-data with its Tailscale key.
Before that, put a fresh auth key in the 1Password `tailscale authkey` field
and apply Terraform so the snippet carries it. Afterwards, replace the guest's
host key in `known_hosts` and rerun the common role, which writes the setting
again and redacts the new key. Leave out `--machine-id`, which only the
template build needs: a live guest keeps its machine ID.

### Cached Tailscale auth keys

Cloud-init keeps the vendor-data's Tailscale auth key in every instance
directory under `/var/lib/cloud` (`vendor-data.txt`, the rendered
`vendor-cloud-config.txt` and `scripts/runcmd`, and `obj.pkl`) and in the
current boot's `/run/cloud-init`, all root-only. The same `cloud-init` tasks
run `ansible/roles/common/files/redact-cloud-init-tailscale-keys`, which
overwrites each key in place with filler of the same length, so the pickles and
JSON stay loadable, prints only counts, and fails the play if any key remains.
Check mode only counts. Redaction does not revoke a key. The root-only (`0600`)
Proxmox snippets under `/var/lib/vz/snippets`, the cloud-init drive and the
local Terraform state still hold the key Terraform last uploaded; Terraform
renders the snippets in memory and writes no copy to local disk.
`tests/terraform-cloud-init.sh` fails any local file resource, any snippet not
uploaded from `source_raw` with a root-only `file_mode`, and any VM that names
a snippet by anything but its literal volume ID. A reference to the snippet
resource's ID is unknown while the snippet is replaced, so the provider would
update and reboot the VM.

## References

- [Proxmox `Cloudinit.pm`](https://git.proxmox.com/?p=qemu-server.git;a=blob;f=src/PVE/QemuServer/Cloudinit.pm):
  `get_dns_conf` (host fallback) and `nocloud_gen_metadata` (instance ID)
- [bpg/proxmox v0.114.0 `vm.go`](https://github.com/bpg/terraform-provider-proxmox/blob/v0.114.0/proxmoxtf/resource/vm/vm.go):
  `vmUpdate` (cloud-init rebuild and reboot) and the `initialization` schema
- [cloud-init first boot determination](https://docs.cloud-init.io/en/latest/explanation/first_boot.html)
  and the [`manual_cache_clean` key](https://docs.cloud-init.io/en/latest/reference/base_config_reference.html)
- [cloud-init 26.1 `cmd/main.py`](https://github.com/canonical/cloud-init/blob/26.1/cloudinit/cmd/main.py):
  `main_init` (`manual_cache_clean` selects `trust`) and
  `purge_cache_on_python_version_change`
- [cloud-init 26.1 `stages.py`](https://github.com/canonical/cloud-init/blob/26.1/cloudinit/stages.py):
  `_restore_from_checked_cache` and `apply_network_config`, and
  [`sources/__init__.py`](https://github.com/canonical/cloud-init/blob/26.1/cloudinit/sources/__init__.py):
  `default_update_events`
