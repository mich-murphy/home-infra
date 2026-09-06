# Proxmox host policy

<!-- markdownlint-disable MD013 -->

The Proxmox node (`proxmox`, Supermicro board, i7-14700, mirrored NVMe `rpool`)
is not under Ansible. Terraform owns the guests; host-level policy is applied by
hand and recorded here so it can be re-applied after a reinstall.

## Access

- SSH accepts public keys only (`PasswordAuthentication no`); root login stays
  enabled for Terraform's SCP path and for recovery.
- `en_AU.UTF-8` is generated so forwarded client locales do not trip Perl
  warnings in the PVE tooling.

## Thermal and fan policy

Two oneshot units in `/etc/systemd/system`, both `WantedBy=multi-user.target`:

| Unit | Script | Purpose |
| --- | --- | --- |
| `supermicro-fan-thresholds.service` | `/usr/local/sbin/set-supermicro-fan-thresholds` | Sets the BMC Lower Critical threshold to 140 RPM on `CPU_FAN1/2` and `SYS_FAN1/2` so the low-RPM Noctua fans do not raise SEL alarms. Only `lcr` is settable on this BMC, so the script sets that field alone and retries while the BMC finishes booting. |
| `cpu-thermal-policy.service` | `/usr/local/sbin/set-cpu-thermal-policy` | Keeps RAPL PL1 at 65 W and caps PL2 at 125 W (stock 219 W) so turbo bursts no longer reach 100 °C, and sets the BMC fan mode to Standard (`ipmitool raw 0x30 0x45 0x01 0x00`) instead of Optimal. |

Check state with `systemctl --failed`, `ipmitool sdr type fan`, `ipmitool sel elist | tail`,
and `cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw`.

## Guest memory budget

| Guest | RAM | Notes |
| --- | --- | --- |
| truenas (101) | 10 GiB | ZFS ARC inside the guest; keep as is. |
| docker-host (102) | 8 GiB | Swap-backed; Collabora prespawn limited in Compose. |
| ai-dev (110) | 7 GiB | Raised from 5 GiB after repeated OOM kills; applies on the next stop/start. |
| host ZFS ARC | 3 GiB max | `zfs_arc_max` in `/etc/modprobe.d/zfs.conf`. |

That leaves roughly 2 GiB for the hypervisor itself on the 32 GiB board. Do not
grow a guest without shrinking another.

## Backups

Guest backups are not yet configured: there is no vzdump job and no backup
storage. The intended target is an NFS export on TrueNAS registered as a PVE
storage with `content backup`, with a daily snapshot-mode vzdump job for VMIDs
102, 110 and 111 and a `keep-daily=7,keep-weekly=4,keep-monthly=3` retention.

The hypervisor sits on the MGMT VLAN and TrueNAS on SRV, so the RouterOS role
carries a narrow forward rule (`Proxmox -> TrueNAS NFS`, tcp 111/2049 and
udp 111 from `network.mgmt.proxmox` to `network.infrastructure.truenas`).
Applying it from a non-MGMT station needs the API tunnelled through the
hypervisor: `ssh -L 18729:10.77.1.1:8729 root@proxmox` then
`-e routeros_api_host=127.0.0.1 -e routeros_api_port=18729`.

TrueNAS-side dataset, export and the vzdump job are still to be created; the
`truenas_admin` SSH key in 1Password gives a shell but not sudo.

## Known gaps

- Notifications route to `root@pam` via a postfix instance with no relayhost,
  so ZFS and PVE alerts are currently dropped.
- The TrueNAS guest runs without the QEMU guest agent by design.
- `unifi-controller` (111) is intentionally stopped and not started on boot.
