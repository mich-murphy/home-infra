# TrueNAS Storage: State and Change Plan

TrueNAS is not managed by IaC. Changes are applied through the UI or API and
recorded here; this file is the system of record for storage configuration.
State below was verified live on 2026-06-13 (TrueNAS SCALE 25.04.2.6).

## Verified current state

### Pool

| Item | Value |
| --- | --- |
| Pool | `slow`, ONLINE, no alerts, 0 errors |
| Data vdev | mirror, 2x Seagate IronWolf 10TB |
| Special vdev | mirror, 2x Kingston DC600M 960GB |
| Capacity | 52% used (5.2T of 10.9T), 8% fragmentation |
| Last scrub | 2026-05-16, clean; schedule Sun 01:00, threshold 35d |
| SMART | weekly SHORT tests, all passing; no LONG tests |

The special vdev is pool-critical: losing it loses the pool. Its mirror
redundancy matches the data vdev, which is the required configuration. The
DC600M drives have power-loss protection.

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

All datasets: LZ4, `atime=off`, POSIX ACLs except `slow/owncloud` (NFSv4
ACLs + case-insensitive, correct for its SMB use).

Measured file-size distributions (drives the tuning below):

- `media`: 45.7K files; 88% are tiny sidecars (.nfo/.srt/posters), 3K files
  over 16M carry the 5.2T. 1M recordsize is right.
- `photos`: 34.9K files; ~11K thumbs under 64K, ~11.5K previews 64K-1M,
  ~12K originals over 1M. 1M recordsize is right; thumbs are the
  special-vdev opportunity.
- `music`/`audiobooks`: nearly all files over 1M. 1M recordsize is right.

### Shares and services

- NFS exports: `media`, `photos`, `media/music`, `media/audiobooks`, and
  `owncloud`. The `owncloud` dataset export is named "Nextcloud data storage",
  restricted to docker-host (`10.77.20.246`), and maps all requests to the
  dedicated `nextcloud` user. The older media and photo exports have empty host
  lists, so their export ACLs remain the only same-VLAN access control.
- The only active NFS client is docker-host (`10.77.20.246`), NFSv4.2 with
  1M rsize/wsize — matching the 1M recordsize, as recommended. The
  Compose services use the same hard NFSv4.2 mount policy.
- NFS server threads: **2**; revisit only if concurrent application I/O
  saturates them.
- SMB: single `nextcloud` share backed by `slow/owncloud` (desktop use), Apple
  extensions disabled.

### Protection

- ZFS snapshot tasks: daily, 7d retention, on `photos`, `owncloud`,
  `media/music`, `media/audiobooks` only.
- Cloud sync: daily Backblaze B2 push for `photos`, `owncloud`, `music`
  (task-level encryption off; acceptable for these, not for SQL dumps).
- No ZFS replication tasks or dedicated application-backup datasets exist yet.

## Change plan

Tuning was cross-checked against Klara Systems' OpenZFS articles and
Lucas/Jude (*FreeBSD Mastery: ZFS* / OpenZFS docs). The one correction that
produced: `special_small_blocks` must stay strictly below `recordsize` —
at `ssb=1M` on a 1M-recordsize dataset every block qualifies and the whole
dataset lands on the SSD, starving metadata. Hence 512K below.

### Phase 1 — additive, safe while docker-host is live

1. Datasets for application backups, with snapshots layered over restic's
   own retention (tamper-resistant, point-in-time recovery of repo state):

   | Dataset | Settings |
   | --- | --- |
   | `slow/backups` | parent; `recordsize=1M`, `sync=standard` |
   | `slow/backups/volsync` | inherits; restic repos, ~16M pack files |
   | `slow/backups/dumps` | inherits; gzipped SQL dumps |

   Inherit LZ4, `atime=off`, `special_small_blocks=64K` (catches restic
   index/config files; backup data blocks stay on HDD by design).
   `sync=standard` because backup artifacts are the one workload here
   where lying about durability defeats the purpose; writes happen
   02:30-04:30 so latency is invisible.

2. Daily ZFS snapshot task on `slow/backups`, recursive, 14d retention.
3. NFS exports for `slow/backups/volsync` and `slow/backups/dumps`,
   host-restricted to docker-host (`10.77.20.246`), `mapall` to a dedicated
   `backups` user.
4. NFS server threads 2 -> 8 (proportionate to a 2-vCPU NAS; revisit if
   application concurrency saturates it).
5. `special_small_blocks=512K` on `slow/photos`: new thumbs/previews under
   512K land on SSD (est. <5GB). Existing thumbs migrate as immich
   regenerates them, or via `zfs rewrite` after a TrueNAS upgrade.
6. Encrypted B2 cloud sync task for `slow/backups/dumps` (dumps are
   plaintext SQL, unlike the already-encrypted restic repos).
7. Monthly LONG SMART test for all four pool disks; keep weekly SHORT.
8. Scrub threshold 35d -> 28d (monthly cadence for home gear).

### Phase 2 — quiet window (touches live docker-host mounts)

1. Host-restrict the existing NFS exports to `10.77.20.246`, one share at a
   time, verifying docker-host I/O after each.
2. Optional: enable SMB Apple extensions (service restart; benefits macOS
   clients of the `owncloud` share).

### Considered and rejected

- `sync=standard` on live media/photos/owncloud: without a SLOG every
  sync write commits to the HDD mirror — this caused real slowness here
  in the past. The crash window (~1 txg of acknowledged writes) is an
  accepted trade-off, mitigated by daily snapshots + B2 for the datasets
  that matter. Revisit only with a SLOG device.
- SLOG: no spare device; workload is read-heavy outside the backup
  window. Not justified.
- Pool-wide rebalance to populate the special vdev: a 5.2T rewrite with
  5.25T free is too tight for a safe maintenance operation.
- `special_small_blocks=1M` on photos: rejected per the rule above.
- Raising `special_small_blocks` on `slow/backups`: Klara's backup-case
  guidance found metadata-on-SSD gives the gains for backup workloads;
  small data blocks add little and consume metadata headroom.
