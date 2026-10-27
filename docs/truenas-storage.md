# TrueNAS storage

TrueNAS is not managed by IaC. Changes are applied through the UI or API and
recorded here; this file is the system of record for storage configuration.
TrueNAS export and service endpoint state was verified live on 2026-09-13
(TrueNAS 25.04.2.6). Storage health, capacity, datasets, protection schedules
and native notification state were rechecked on 2026-10-07. Authorized remote
maintenance restored personal-data write durability and native email delivery,
verified SSD self-tests, and started the guarded full scrub recorded below.
Exports were not re-audited during this maintenance.

## Verified current state

### Pool

| Item | Value |
| --- | --- |
| Pool | `slow`, ONLINE, all current device error counts zero and no native pool/disk/SMART alerts returned (2026-10-09, after reboot/cable replacement); historical fault preserved below, full verification still pending |
| Data vdev | mirror, 2x 10TB HDD |
| Special vdev | mirror, 2x 960GB SSD |
| Capacity | 57% used (5.70 TiB of 9.95 TiB), 10% fragmentation (2026-10-07) |
| Scrubs | Prior completion 2026-09-20 reported 4.23M repaired and 0 scan errors; scrub 67305 canceled after fresh PHY errors on 2026-10-07; post-cable guarded full scrub job 142 RUNNING since 2026-10-09 05:27 UTC (not yet accepted); eligibility Sun 01:00, threshold 28d |
| SMART | Existing weekly SHORT on Saturday 01:00; existing monthly LONG staggered at 06:00 on days 2/9 for HDDs and 16/23 for SSDs; fresh SSD LONG tests passed 2026-10-07 |

The special vdev is pool-critical: losing it loses the pool. Its mirror
redundancy matches the data vdev, which is the required configuration. The
special-vdev SSDs have power-loss protection.

### Known hardware fault

The special-vdev SSD on HBA PHY 3 has a suspect SATA link. The initial
read-only check on 2026-10-07 found:

- `/dev/sde1` remained ONLINE with 3 read, 106 write and 379 checksum errors;
  its mirror sibling `/dev/sdd1` reported zero.
- PHY 3 reported 28,551 invalid dwords and 28,540 disparity errors; every
  other PHY reported zero for those counters.
- Both Kingston DC600M SSDs passed SMART, with zero reported uncorrectable or
  reallocated events. The affected SSD recorded 18 interface CRC errors and
  14 ICRC command failures; its sibling had none.
- Counters stayed unchanged across observations approximately eight minutes
  apart, and the last seven days of kernel logs contained no matching storage
  errors. This does not prove the physical fault is resolved.
- TrueNAS still had an undismissed CRITICAL VolumeStatus alert. Native E-Mail
  and SNMP Trap alert services were enabled at WARNING level; delivery was not
  tested by this read-only check.

The affected drive is Kingston DC600M 960GB, serial **50026B7687168A10**
(WWN `0x50026b7687168a10`), currently `/dev/sde`; its sibling ends `3440`.
Device letters can change after reboot: identify it by serial/WWN, not letter.

### Authorized remote maintenance, 2026-10-07

- Changed only `slow/photos` and `slow/owncloud` from `sync=disabled` to
  `sync=standard` through the middleware API, with property readback verified.
  Standard honors clients' synchronous-write requests; it does not force every
  asynchronous write synchronous. Media and backup policies were unchanged.
- Temporary write/fsync/delete probes passed in Immich's application context
  and Nextcloud's `www-data` context through their actual NFS bind mounts.
  Both applications remained healthy. Existing user files were not edited.
- Native E-Mail was enabled but had no SMTP server/sender, and neither local
  administrator had an email address configured. Configured authenticated
  STARTTLS on port 587 using the existing working Beszel SMTP relay credential,
  and an explicit native alert recipient matching its existing notification
  owner. WARNING threshold was retained. No secret values are recorded here.
  Native test mail job **67264 succeeded**; native-test inbox receipt has not
  yet been confirmed. Beszel's earlier test receipt **was** confirmed by the user.
- Both SSDs completed fresh background LONG self-tests without error (jobs
  67269/67270). Monthly LONG schedules already existed; they were not created
  or changed in this maintenance.
- Started full scrub **67305** at **05:41 UTC**. The guard stopped it at
  **06:01 UTC**, at approximately 4% issued, after fresh PHY 3 errors. A subsequent
  direct sysfs read confirmed invalid-dword/disparity counters **28,552 / 28,541**,
  up by one each. Device counts stayed 3/106/379 and ZFS reported no known data
  errors. `zpool status` confirmed **scrub canceled**. This is NOT a completed
  integrity verification; fresh link-layer errors require physical-path review.
  The middleware job's SUCCESS reflects completed cancellation, not a clean scan.

A bounded transient root unit `home-infra-truenas-scrub-20261007.service`
checks every 30 seconds and requests scrub STOP on changed device health,
device error counters, PHY 3 counters, known data errors or a 24-hour deadline.
It never clears counters, dismisses alerts or replaces a disk. Its record is
`/var/lib/home-infra-maintenance/truenas-scrub-20261007.json`; the pre-change
baseline is `truenas-storage-before-20261007.json` in the same directory.
The separate bounded unit `home-infra-truenas-scrub-notify-67305.service` sent
one genuine review-required email: mail job **67350**, receipt **SMTP_ACCEPTED**
in `truenas-scrub-notification-67305.json`; inbox receipt remains unconfirmed.
The guard is now failed/STOPPED_FOR_REVIEW and the notifier finished. Their
transient units do not restart on reboot. Do not restart blindly: first inspect
saved evidence and the actual pool. The guard record's `latest` field is the
last good sample, not the triggering sample; direct sysfs established the increase.

**Physical work update, 2026-10-09:** the user reports replacing the cable.
The host and guests have rebooted; post-replacement observations are recorded
below. This is a repair receipt, not yet full verification under scrub load.
Independent backup safety remains unconfirmed. Preserve the historical baseline
and explicitly schedule a new guarded full scrub after confirming backup safety
and the maintenance window. If errors recur, investigate the remaining connector,
HBA-lane and drive-interface possibilities; SMART alone does not isolate them.
Do not hot-unplug a pool-critical mirror member. No counters were explicitly
cleared or alerts dismissed by this assistant; current zero ZFS/PHY counts after
reboot must not erase the earlier failure evidence.

`special_small_blocks=64K` is inherited pool-wide, but the vdev holds only
~2GB of 953GB: allocation classes apply to newly written blocks only, and
the bulk data predates the vdev. Existing data migrates only when rewritten.
OpenZFS 2.4 adds `zfs rewrite` for exactly this; TrueNAS 25.04 ships an
older OpenZFS, so targeted migration waits for a TrueNAS upgrade. New
datasets (including the backup datasets below) benefit immediately.

### Read-only roadmap resume, 2026-10-07 06:28 UTC

- Rechecked `slow`: ONLINE, scrub still canceled, affected `/dev/sde1`
  counters still **3 READ / 106 WRITE / 379 CKSUM**, and no known data errors.
  PHY 3 remains **28,552 invalid dwords / 28,541 disparity errors**; all
  other inspected PHY counters are zero. No increase since the post-stop
  sample was observed in this check; this is not repair or full-scrub evidence.
- `slow/photos` and `slow/owncloud` still read back `sync=standard`.
  The guard remains failed with `STOPPED_FOR_REVIEW`; saved scrub job 67305
  records `stop_requested=true`. Saved notifier receipt remains
  `SMTP_ACCEPTED`, mail job 67350. Inbox receipt and current native alert
  state were not established by this check.
- Copied the original baseline, guard and notifier JSON records together with
  current pool, PHY, property and guard-unit/journal observations off the NAS
  into a private operator-local evidence file:
  `~/.local/state/home-infra/roadmap-evidence/20261007T062832Z/truenas-readonly.json`
  (mode 0600; capture directory mode 0700). SHA-256:
  `3e6fdecc4f3aa2d55a653a1093a7b30b373697d2e648944d2caf339b5ab45ef9`.
  This preserves diagnostic evidence, not an independent backup of user data.
- No scrub, error clearing, alert dismissal, storage-property change or
  application recreation was performed. Phase 0 remains blocked on physical
  path history/access, independent backup verification and native email receipt.
  Next action: confirm those operator inputs before scheduling physical work.

### Post-cable read-only verification, 2026-10-09 05:10–05:13 UTC

- User reports a new cable installed. Proxmox booted at approximately 04:47 UTC;
  Docker and TrueNAS guests booted shortly afterward. Re-identified affected
  Kingston SSD **50026B7687168A10**, still `/dev/sde`, on sysfs `port-1:3`.
  PHY 3 negotiates **6.0 Gbit/s**.
- `slow` is ONLINE; all current ZFS device READ/WRITE/CKSUM counts are zero and
  there are no known data errors. PHY invalid-dword/disparity/sync-loss/reset-
  problem counters are zero on all eight inspected PHYs, unchanged over samples
  at 05:10:27, 05:11:28 and 05:12:39 UTC. These are post-reboot baselines, not
  comparable lifetime totals or a completed load test. No explicit clearing
  was performed. The previous canceled scrub remains the latest scan.
- Both special-vdev SSDs report SMART health passed, zero reported uncorrectable
  errors, and the previously completed LONG self-tests passed. No new self-test
  was started. Affected-drive lifetime SATA CRC count remains **18**; sibling
  count is **0**. Current drive-side ICRC failure counters are zero. Targeted
  health/attribute/self-test/PHY reads returned exit 0; initial extended `-x`
  JSON reads returned exit 4, so the extended query alone is not a clean gate.
- Native `alert.list` returned no pool/volume/disk/SMART-class alerts at the
  observation time. This does not establish delivered recovery email or full
  integrity acceptance. Filtered current-boot kernel logs showed no matching
  storage I/O failure/reset errors beyond normal controller initialization.
- `photos`/`owncloud` still use `sync=standard`. Running Docker containers are
  up (those with configured health checks report healthy). Verified actual
  NFSv4.2 mounts inside Immich, Nextcloud and Jellyfin; host-level automounts
  were idle, so host `findmnt -t nfs,nfs4` alone was insufficient evidence.
  Bounded reads of Immich and Nextcloud data markers and Jellyfin media/music
  directory listings passed in their running container contexts. No user-file
  writes, playback/transcode or full application restore test was performed.
- Private off-NAS evidence directory:
  `~/.local/state/home-infra/roadmap-evidence/20261009T051129Z/`.
  Main capture `truenas-post-cable-readonly.json` SHA-256:
  `7c056307f3d493924ea7c6b860b77cef53915b3334d15f7ce9a2347d2a6e70c6`.
  Supplemental `ssd-followup.json` SHA-256:
  `583f41fb7860c6a2dd2f7d533832595dee34c6cd424cf0f2d9d6e083ea0af532`.
  `application-read-checks.json` records the bounded container checks. Files
  are mode 0600 in the mode-0700 capture directory.
- Next: confirm independent backup safety and approval/window for a new guarded
  full scrub. Do not reuse the old transient guard blindly; its pre-reboot
  baseline and historical result must remain preserved. Phase 0 is not complete.

### Authorized guarded post-cable scrub, started 2026-10-09 05:27 UTC

- User answered **yes** to the combined request to start now and confirm an
  accessible independent backup. This is operator confirmation, not a dated
  independent restore drill or verified version-history/retention evidence.
  Phase 3 recovery acceptance remains outstanding.
- Installed a new, separate guard; the October 7 helper/result were not reused
  or overwritten. Sixteen offline workflow tests passed, including fresh PHY,
  device and lifetime CRC errors, identity changes, canceled/stale scan rejection,
  abrupt-exit finalization, safe direct cancellation when middleware is down,
  and prevention of duplicate notification attempts. Guard SHA-256:
  `dcb58f56d68d7cddd9f2b325d71011620b09d1582b770f0a15cb8d27903d2c3c`.
- Initial read-only preflight exited by SIGKILL (exit -9); no scrub was started
  by that attempt. No matching kernel OOM evidence or failed services were found.
  A traced preflight and the identical normal CLI preflight subsequently passed;
  the initial termination cause is unknown and its evidence is retained.
- Actual guard preconditions passed: four ONLINE pool members, expected SSD
  serials/PHY mapping, zero current device/HBA errors, lifetime SSD CRC counts
  18/0, no active SMART self-tests or native jobs. PVE active-task inventory
  was empty. No additional SMART self-test or backup was started.
- Full scrub **142** started at **05:27:52 UTC**, explicitly observed as a new
  `SCRUB/SCANNING` scan. At **05:29:03 UTC**, direct `zpool status` reported
  **0.27% issued**, 0B repaired, no known data errors, all device counts zero,
  and approximately **7h 10m remaining**. Guard sample at 05:28:52 UTC still
  matched baseline for all HBA PHY and both SSD link/SMART counters. This is
  a running scan, NOT completed full-scrub acceptance; estimates can change.
- Unit: `home-infra-truenas-scrub-post-cable-20261009.service`, active/running.
  Script and result:
  `/var/lib/home-infra-maintenance/truenas-scrub-post-cable-20261009.py` and
  `truenas-scrub-post-cable-20261009.json`. Poll interval 30 seconds plus sample
  time, deadline 24 hours, `Restart=no`, outer runtime cap 25 hours. Independent
  `ExecStopPost` finalization identifies and stops this scan if the guard exits
  unexpectedly; it refuses to stop an unrelated scan. The unit is transient
  and does not automatically resume after reboot.
- The guard stops for changed device/PHY/SSD counters, degraded health, identity
  change, scan errors, paused/canceled/failed scan, observation failure or the
  deadline. It preserves the triggering sample when available, records stop
  confirmation, and attempts one native result email to the existing configured
  recipient. Notification intent/job/SMTP receipt is stored in the result;
  no terminal email has yet been sent or inbox receipt established. Successful
  cancellation is never classified as successful verification.
- No counters explicitly cleared, alerts dismissed, schedules changed or pool
  devices modified. PVE next backup is 15:30 UTC; usual cloud sync begins at
  13:00 UTC and weekly SHORT eligibility is 14:00 UTC. The initial scrub estimate
  finished before these; the later progress observation below predicts a possible
  cloud-sync overlap. Reassess rather than casually overlapping heavy verification/
  backup jobs. Existing schedules were not disabled.
- Local private evidence remains in
  `~/.local/state/home-infra/roadmap-evidence/20261009T051129Z/`, including
  `scrub-launch.json` (failed preflight), preflight diagnostics/trace/repeat,
  `scrub-start-observed.json` (actual start, baseline and two observations),
  new guard source/tests and `scrub-guard-offline-tests.txt`.
- Next action: read the saved result, actual scan, pre/post counters and native
  mail receipt after termination; confirm application I/O remains healthy.
  Phase 0 remains open until the full acceptance evidence exists. To abandon
  this authorized run, stop the named systemd unit and verify actual scrub stop;
  do not clear errors or blindly restart its result-bearing helper.

### Scrub progress, 2026-10-09 11:41 UTC

- Direct ZFS read: scrub **78.31% issued**, **0B repaired**, approximately
  **1h 42m 46s remaining**; `slow` ONLINE, every device READ/WRITE/CKSUM count
  zero, no known data errors. Job 142 and guard unit both remain running.
- All current HBA PHY error counters remain zero. Guard sample at 11:40:55 UTC
  preserves unchanged SSD counters: affected-drive lifetime CRC **18**, sibling
  **0**, no reported uncorrectable errors and no new drive-side PHY events.
  No terminal result/notification yet; full acceptance remains pending.
- Read-only evidence saved off-NAS as
  `~/.local/state/home-infra/roadmap-evidence/20261009T051129Z/scrub-progress-20261009T114124Z.json`.
  No scan/schedule/error-counter/alert mutation performed by this check.
- Variable ETA now projects completion around 13:24 UTC, potentially overlapping
  usual 13:00 UTC B2 cloud sync. Check live schedules and agree on any bounded
  deferral before changing backup scheduling; no deferral has been authorized.

### Datasets

| Dataset | Used | recordsize | sync | Notes |
| --- | --- | --- | --- | --- |
| `slow/media` | 3.72 TiB | 1M | disabled | refquota 7T; includes child datasets |
| `slow/media/music` | 288 GiB | 1M | disabled | |
| `slow/media/audiobooks` | 29.1 GiB | 1M | disabled | |
| `slow/photos` | 105.7 GiB | 1M | standard | refquota 512G, Immich |
| `slow/owncloud` | 2.74 GiB | 128K | standard | Nextcloud data; case-insensitive; SMB disabled |
| `slow/backups` | 1.87 TiB | 1M | standard | backup parent; includes child dataset |
| `slow/backups/proxmox` | 1.87 TiB | 1M | standard | refquota 1.5T, vzdump target |

Used values include snapshots/children. Proxmox backups currently account for
about 0.94 TiB of live data plus 0.94 TiB of snapshots. `refquota=1.5T` limits
live referenced data, not snapshot usage; the total can legitimately exceed it.
No backup or snapshot retention was reduced during this maintenance.

All datasets: LZ4, `atime=off`, POSIX ACLs except `slow/owncloud` (legacy NFSv4
ACLs and case-insensitive semantics retained from its former SMB use).

Measured file-size distributions confirm 1M recordsize is right for `media`,
`photos`, `music` and `audiobooks`; the small thumbnails under `photos` are
the special-vdev opportunity.

### Shares and services

- NFS is v4-only, with `allow_nonroot=true` and **2** server threads. The
  effective export options are `sec=sys,rw,root_squash,all_squash`, mapping
  media to UID/GID 1215, photos to 1210, Nextcloud data (`owncloud`) to 1205,
  and backups to 1225. The `owncloud` dataset export is named "Nextcloud data
  storage" and maps all requests to the dedicated `nextcloud` user.
- Export host restrictions currently set `hosts=[10.77.20.246]` for media,
  photos, music, audiobooks, and `owncloud`; `backups/proxmox` is restricted to
  `hosts=[10.77.1.100]`. Export `networks` fields are empty. Removal of the
  authorized legacy Talos host `10.77.20.20` was completed for export IDs
  1 (media), 4 (photos), 7 (music), and 8 (audiobooks).
- Active NFS client sessions remained for docker-host (`10.77.20.246`) and
  Proxmox (`10.77.1.100`). Photos and Nextcloud application-context I/O was
  subsequently verified in the 2026-10-07 maintenance; other shares were not
  exercised. The Compose services use the same hard NFSv4.2 mount policy.
- SMB: the `nextcloud` share backed by `slow/owncloud` is disabled. Nextcloud's
  primary data directory is the only active writer; direct SMB changes would
  bypass its file cache.

### Protection

- ZFS snapshot tasks: daily, 7d retention, on `photos`, `owncloud`,
  `media/music`, `media/audiobooks`. Daily 06:00, 14d, recursive on
  `slow/backups` (added 2026-09-06).
- Cloud sync: daily 00:00 Backblaze B2 PUSH/SYNC for `photos`, `owncloud`,
  `music`; all three latest jobs reported SUCCESS on 2026-10-07. This verifies
  job completion, not independent versioned recovery or a restore drill.
  Task-level encryption is off; turn it on before any dataset holding plaintext
  dumps is added to the task.
- No ZFS replication tasks or dedicated application-backup datasets exist yet.

## Open items

- `special_small_blocks` must stay strictly below `recordsize`. At `ssb=1M` on
  a 1M-recordsize dataset every block qualifies and the whole dataset lands on
  the SSD, starving metadata.
- Cable replacement reported 2026-10-09; authorized post-replacement guarded
  full scrub job 142 is running, with completion/unchanged counters and terminal
  notification acceptance still pending. Do not interpret ONLINE, post-reboot
  zero counts, passing SMART or a canceled scrub's API SUCCESS as full
  verification. The scheduler uses scrub-start history, so a canceled start
  can defer the next eligible periodic scan.
- Follow the phased plan in [roadmap handover](homelab-roadmap-handover.md).
- Verify inbox receipt of the separate native TrueNAS test/result messages.
- Photos and Nextcloud application-context NFS I/O passed on 2026-10-07;
  application I/O for the other shares was not exercised in this maintenance.
- Independent, versioned application-consistent backup and restore testing
  remains separate work; same-pool snapshots and successful B2 sync do not
  establish that acceptance.
