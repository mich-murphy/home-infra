# TrueNAS storage

TrueNAS is not managed by IaC. Changes are applied through the UI or API and
recorded here; this file is the system of record for storage configuration.
State below was verified live on 2026-06-13 (TrueNAS SCALE 25.04).

## Verified current state

### Pool

| Item | Value |
| --- | --- |
| Pool | `slow`, ONLINE, no alerts, 0 errors |
| Data vdev | mirror, 2x 10TB HDD |
| Special vdev | mirror, 2x 960GB SSD |
| Capacity | 52% used (5.2T of 10.9T), 8% fragmentation |
| Last scrub | 2026-05-16, clean; schedule Sun 01:00, threshold 35d |
| SMART | weekly SHORT tests, all passing; no LONG tests |

The special vdev is pool-critical: losing it loses the pool. Its mirror
redundancy matches the data vdev, which is the required configuration. The
special-vdev SSDs have power-loss protection.

### Known hardware fault

The special-vdev SSD on HBA PHY 3 has a suspect SATA link: that PHY logs
invalid-dword and CRC errors where its siblings log none, and the drive has
dropped off the bus and resilvered clean. The drive itself passes SMART.
Reseat or replace the cable lane feeding PHY 3, then scrub and confirm the
PHY counters stop climbing.

`special_small_blocks=64K` is inherited pool-wide, but the vdev holds only
~2GB of 953GB: allocation classes apply to newly written blocks only, and
the bulk data predates the vdev. Existing data migrates only when rewritten.
OpenZFS 2.4 adds `zfs rewrite` for exactly this; TrueNAS 25.04 ships an
older OpenZFS, so targeted migration waits for a TrueNAS upgrade. New
datasets (including the backup datasets below) benefit immediately.

### Datasets

| Dataset | Used | recordsize | sync | Notes |
| --- | --- | --- | --- | --- |
| `slow/media` | 5.1T | 1M | disabled | refquota 7T |
| `slow/media/music` | 210G | 1M | disabled | |
| `slow/media/audiobooks` | 31G | 1M | disabled | |
| `slow/photos` | 104G | 1M | disabled | refquota 512G, immich |
| `slow/owncloud` | 1.2G | 128K | disabled | SMB, case-insensitive |
| `slow/backups` | - | 1M | standard | backup parent (added 2026-09-06) |
| `slow/backups/proxmox` | - | 1M | standard | refquota 1.5T, vzdump target |

All datasets: LZ4, `atime=off`, POSIX ACLs except `slow/owncloud` (NFSv4
ACLs + case-insensitive, correct for its SMB use).

Measured file-size distributions confirm 1M recordsize is right for `media`,
`photos`, `music` and `audiobooks`; the small thumbnails under `photos` are
the special-vdev opportunity.

### Shares and services

- NFS exports: `media`, `photos`, `media/music`, `media/audiobooks`,
  `owncloud`, and `backups/proxmox` (restricted to the hypervisor, `mapall` to
  the `backups` user). The `owncloud` dataset export is named "Nextcloud data
  storage", restricted to docker-host, and maps all requests to the dedicated
  `nextcloud` user.
- The only active NFS client is docker-host, NFSv4.2 with
  1M rsize/wsize — matching the 1M recordsize, as recommended. The
  Compose services use the same hard NFSv4.2 mount policy.
- NFS server threads: **2**; revisit only if concurrent application I/O
  saturates them.
- SMB: the `nextcloud` share backed by `slow/owncloud` is disabled. Nextcloud's
  primary data directory is the only active writer; direct SMB changes would
  bypass its file cache.

### Protection

- ZFS snapshot tasks: daily, 7d retention, on `photos`, `owncloud`,
  `media/music`, `media/audiobooks`. Daily 06:00, 14d, recursive on
  `slow/backups` (added 2026-09-06).
- Cloud sync: daily Backblaze B2 push for `photos`, `owncloud`, `music`.
  Task-level encryption is off; turn it on before any dataset holding plaintext
  dumps is added to the task.
- No ZFS replication tasks or dedicated application-backup datasets exist yet.

## Open items

- `special_small_blocks` must stay strictly below `recordsize`. At `ssb=1M` on
  a 1M-recordsize dataset every block qualifies and the whole dataset lands on
  the SSD, starving metadata.
- The media and photo NFS exports still have empty host lists, leaving their
  export ACLs as the only same-VLAN access control. Host-restrict them to
  docker-host one share at a time, verifying I/O after each.
