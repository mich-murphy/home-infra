# TrueNAS Storage: State and Change Plan

TrueNAS is not managed by IaC. Changes are applied through the UI or API and
recorded here; this file is the system of record for storage configuration.
State below was verified live on 2026-06-13 (TrueNAS SCALE 25.04.2.6) ahead
of the Kubernetes migration in [k8s-migration.md](k8s-migration.md).

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
| `slow/media/emulators` | 98G | 128K | disabled | to be removed |
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

- NFS exports: `media`, `photos`, `media/music`, `media/audiobooks`,
  `media/emulators`. All have empty host lists (any client that can reach
  NFS may mount; same-VLAN traffic does not traverse the router firewall,
  so export ACLs are the only control). `mapall` to `media`/`photos` users.
- The only active NFS client is docker-host (`10.77.20.246`), NFSv4.2 with
  1M rsize/wsize — matching the 1M recordsize, as recommended. The
  Kubernetes PVs pin `nfsvers=4.2,hard`, so behaviour is identical after
  cutover.
- NFS server threads: **2** (low for concurrent k8s + media workloads).
- SMB: single `owncloud` share (desktop use), Apple extensions disabled.

### Protection

- ZFS snapshot tasks: daily, 7d retention, on `photos`, `owncloud`,
  `media/music`, `media/audiobooks` only.
- Cloud sync: daily Backblaze B2 push for `photos`, `owncloud`, `music`
  (task-level encryption off; acceptable for these, not for SQL dumps).
- No ZFS replication tasks. No backup datasets exist yet; the k8s backup
  plan (VolSync restic repos + DB dump CronJobs) lands on this box.

## Change plan

Tuning was cross-checked against Klara Systems' OpenZFS articles and
Lucas/Jude (*FreeBSD Mastery: ZFS* / OpenZFS docs). The one correction that
produced: `special_small_blocks` must stay strictly below `recordsize` —
at `ssb=1M` on a 1M-recordsize dataset every block qualifies and the whole
dataset lands on the SSD, starving metadata. Hence 512K below.

### Phase 1 — additive, safe while docker-host is live

1. Datasets for the k8s backup plan, with snapshots layered over restic's
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
   host-restricted to `10.77.20.20` (talos) and `10.77.20.246`
   (docker-host, until decommission), `mapall` to a dedicated `backups`
   user.
4. NFS server threads 2 -> 8 (proportionate to a 2-vCPU NAS; revisit if
   k8s concurrency saturates it).
5. `special_small_blocks=512K` on `slow/photos`: new thumbs/previews under
   512K land on SSD (est. <5GB). Existing thumbs migrate as immich
   regenerates them, or via `zfs rewrite` after a TrueNAS upgrade.
6. Encrypted B2 cloud sync task for `slow/backups/dumps` (dumps are
   plaintext SQL, unlike the already-encrypted restic repos).
7. Monthly LONG SMART test for all four pool disks; keep weekly SHORT.
8. Scrub threshold 35d -> 28d (monthly cadence for home gear).

### Phase 2 — quiet window (touches live docker-host mounts)

1. Host-restrict the five existing NFS exports to `10.77.20.246` and
   `10.77.20.20`, one share at a time, verifying docker-host I/O after
   each. Drop `.246` from all export ACLs at docker-host decommission.
2. Remove the `media/emulators` NFS export and **delete
   `slow/media/emulators`** (98G, no longer needed — destructive, confirm
   before deletion).
3. Optional: enable SMB Apple extensions (service restart; benefits macOS
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
  5.25T free is too tight, and mid-migration is the wrong time.
- `special_small_blocks=1M` on photos: rejected per the rule above.
- Raising `special_small_blocks` on `slow/backups`: Klara's backup-case
  guidance found metadata-on-SSD gives the gains for backup workloads;
  small data blocks add little and consume metadata headroom.

## Relationship to the k8s migration

The migration runbook ([k8s-migration.md](k8s-migration.md)) leans on this
box at four points:

1. Phase 1 above replaces the runbook's old "create backup directories"
   preflight step — the targets are now proper datasets.
2. Cutover artifacts (dumps + volume tars) stage onto
   `slow/backups/dumps`; a manual ZFS snapshot of `slow/backups` is taken
   after the freeze completes, before any restore touches the export.
3. Named pre-cutover snapshots of `slow/photos`, `slow/owncloud` and
   `slow/media` guard the NFS data that k8s apps write to on first boot.
4. VolSync restic repos and weekday-rotated DB dumps land here long-term;
   ZFS snapshots + (for dumps) encrypted B2 give the off-host layers.
