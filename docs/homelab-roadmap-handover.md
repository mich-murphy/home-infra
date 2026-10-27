# Homelab roadmap and session handover

<!-- markdownlint-disable MD013 -->

**Recorded:** 2026-10-07. This is the agreed remaining plan and a point-in-time
handover, not a claim that the roadmap is implemented. Refresh live evidence
before acting. Infrastructure changes require bounded deployment and rollback;
this document is not permission to perform every destructive operation unattended.

## Latest update — cable replaced; guarded scrub running

**2026-10-09:** user reports installing a new cable. After host/guest reboot,
read-only checks re-identified SSD `50026B7687168A10` on PHY 3 at 6.0 Gbit/s.
`slow` is ONLINE with zero current device error counts and no known data errors;
all inspected PHY error counters stayed zero over three samples spanning about
two minutes. Affected-drive lifetime CRC count remains 18. Both SSDs report SMART
health passed, and no native pool/disk/SMART alerts were returned. Containers
are up and bounded application-context NFS read checks passed.

These zero ZFS/PHY counts are a **post-reboot baseline**, not proof that a full
scrub passed. The user answered yes to starting a guarded scrub now and the
combined independent-backup confirmation prompt; no restore drill is thereby
established. A new guarded full scrub **job 142** started **05:27:52 UTC**.
At **05:29:03 UTC** the scan and guard were actually running, 0.27% issued,
zero device/scan errors, unchanged PHY/SSD counters and approximately 7h 10m
remaining (variable estimate). No explicit counter clearing or alert dismissal
was performed. Historical failure evidence below remains relevant.

Unit: `home-infra-truenas-scrub-post-cable-20261009.service`; result:
`/var/lib/home-infra-maintenance/truenas-scrub-post-cable-20261009.json`.
The new guard samples every 30 seconds plus sample time, stops on new faults or
a 24-hour deadline, has independent exit-stop finalization, and attempts one
native terminal-result email. It does not restart automatically or resume after
reboot. Sixteen offline guard tests passed. An initial preflight was SIGKILLed
without starting a scrub; no OOM evidence was found, two subsequent preflights
passed, and the unexplained failure evidence is preserved. Details and private
off-NAS evidence locations are in [TrueNAS storage](truenas-storage.md).

**Next action:** observe the terminal result and actual ZFS scan, compare pre/post
counters, verify application health and confirm native email receipt. If the scan
slows into overnight cloud sync/SMART/backup windows, reassess overlap. Do not
blindly restart either result-bearing helper. Phase 0 remains incomplete until
the full scrub acceptance exists; recovery/version-history acceptance is separate.

## Historical stop — 2026-10-07

The latest SSH check supersedes the earlier "scrub running, no new errors"
reports:

- Full scrub **67305** began at 05:41 UTC and was canceled by its guard at
  **06:01 UTC**, after approximately 4% of data had been issued for verification.
- HBA PHY 3 invalid-dword/disparity counters increased from **28,551 / 28,540**
  to **28,552 / 28,541**, confirmed directly from sysfs after the stop.
- ZFS device counts remained **3 READ / 106 WRITE / 379 CKSUM** on the affected
  special-vdev SSD. Pool `slow` remains ONLINE with **no known data errors**,
  but the critical VolumeStatus alert remains unresolved. Proxmox's clean NVMe
  `rpool` is a different pool and is not evidence of TrueNAS `slow` health.
- This is fresh link-layer error evidence under scrub load, not just historical
  counters. Cable/connector/HBA-lane/drive-interface investigation is required;
  passing SMART does not identify which component is responsible.
- **Do not restart the scrub, clear counters, dismiss the alert or replace/remove
  pool devices merely to obtain a green status.** Preserve evidence and arrange
  physical inspection. Losing both special-vdev mirror members loses the pool.
- The affected Kingston DC600M 960GB is serial **50026B7687168A10**, WWN
  `0x50026b7687168a10`, currently `/dev/sde`. Its mirror sibling ends `3440`.
  Identify physical drives by serial/WWN; Linux letters can change.
- The review-required notification was accepted by SMTP: mail job **67350**,
  notifier receipt **SMTP_ACCEPTED**. User inbox receipt remains unconfirmed.

The scrub API job reports **SUCCESS because its stop completed**. That is NOT
successful full-scrub acceptance. `zpool status` reports **scrub canceled**.

## Decisions that remain fixed

- Keep production on **Compose, one Docker VM, Ansible bootstrap and Portainer
  application ownership**. Group workloads logically/by network; do not add
  multiple VMs just to create categories. Keep databases separately owned by
  their applications rather than consolidating their lifecycle.
- Do not migrate to Kubernetes for RAM savings. A single physical host cannot
  gain physical HA by running more nodes on itself. Talos/Flux remains a future
  operational choice if reconciliation/API-managed hosts justify its cost.
- Keep **Portainer's direct Docker socket** intentionally: a permissive
  management proxy does not remove its root-equivalent power. Protect admin
  access instead. Keep Traefik's restricted discovery socket proxy.
- RAM is healthy per the user. TrueNAS/Docker remain **10 GiB each**, UniFi
  **3 GiB cold**, host ARC ceiling **3 GiB**. No automatic Docker RAM increase.
  Earlier host available memory was about 5.6 GiB; this was not a peak benchmark.
  The nominal 9 GiB remainder is before overhead/reserved memory/safety margin.
- Use **Beszel for resource notifications**, plus native TrueNAS and PVE
  operational alerts. Resource monitoring is not backup-job or complete
  storage-health coverage.
- Preserve data and recovery material. No broad Terraform apply, pool topology
  change, backup purge, NAS upgrade or router cutover is bundled into publishing
  this cleanup. Do not diagnose the remaining RAM again without new evidence.

## Completed work and its evidence

| Area | Completed | Qualification |
| --- | --- | --- |
| Retirement | Destroyed ai-dev VM 110 and unused Arch template 9002; configs/zvols absent; AI snippet removed | Existing VM backups retained; Ubuntu templates 9001/9003 retained |
| Source/state | Removed AI/CLIProxy provisioning, observer/backend and media-broker source, obsolete roles/tests/workflows/Renovate hooks | Repository remains uncommitted; no broad Terraform apply |
| Terraform retirement | Forgot exactly `proxmox_virtual_environment_vm.ai_dev` and `proxmox_virtual_environment_file.cloud_init_ai_dev` | Other state retained; state/backups are secret-bearing and ignored |
| Live services | Deleted media-broker Portainer stack 40 on endpoint 3; removed observer containers/networks/source and agent-only init environment keys | Four remaining init services were verified running; other stacks not recreated |
| Secrets | Removed unused vault proxy-management/controller-token entries, GitHub `CLIPROXY_CONTROLLER_RELEASES_TOKEN`, dedicated broker credential copies | Shared application API credentials/Tailscale auth key retained; not blanket-revoked |
| Jellyfin | Persisted encoding path `/cache/transcodes` on existing local disk cache; app-user write check and healthy service | Old unused `/transcode` tmpfs is still mounted until managed recreation; no actual playback/transcode test yet |
| Beszel | Docker connectivity restored; Docker and Proxmox up; resource/down-status rules configured | Email receipt confirmed by user; agents/firewall/alert reconciliation not yet repository-owned |
| TrueNAS durability | `slow/photos` and `slow/owncloud` now `sync=standard`; readback and actual application-context write/fsync/delete checks passed | Media policies unchanged; standard honors synchronous requests, not every asynchronous write |
| TrueNAS notifications | Native SMTP authenticated STARTTLS 587 and explicit Mail-alert recipient configured; WARNING threshold retained | Earlier enabled Mail service had no SMTP setup; test job 67264 succeeded, native inbox receipt pending |
| SSD diagnostics | Fresh LONG tests on both SSDs passed, jobs 67269/67270 | Monthly LONG schedules already existed; SMART pass is not a link-health certificate |
| Integrity verification | Guard detected fresh PHY errors and stopped full scrub; genuine review-required email sent | Full scrub NOT completed; no counters cleared or alerts dismissed |

Retirement source had independent review with no blocking findings. Terraform
validation/formatting, Compose hardening including six Jellyfin negative
fixtures, cloud-init tests, Ansible syntax/tests/lint, ShellCheck and Actionlint
passed before this handover. Vault values other than the two removed keys were
verified unchanged during encryption. These are historical checks: rerun the
relevant gates for the exact snapshot being published. Live maintenance was
verified operationally, not delivered through a merged PR.

## Prioritized execution plan

Do one bounded task at a time. Store baseline, change, acceptance evidence and
rollback/next action in the owning documentation. Read-only discovery and
passive measurement can proceed in parallel; intrusive storage tests, application
recreation and firewall cutovers must not overlap casually.

### Phase 0 — Contain and close the storage fault (first)

**Owner:** operator for evidence/backups; user or technician for physical work.

1. Read actual pool/device state, PHY counters, saved guard result and mail
   receipt. Preserve the baseline and failing evidence outside the affected pool.
2. Verify accessible independent copies of irreplaceable personal data and
   configuration before physical work. Existing B2 jobs succeeded but have NOT
   demonstrated version history or restoreability. Avoid a new heavy stress
   test just to obtain another error while the link is suspect.
3. Ask whether this cable path was already repaired. If not, arrange powered-down
   inspection/reseating/replacement of the PHY 3 path. Coordinate safe shutdown
   of NFS-consuming applications/guests and the server as needed; do not hot-unplug
   a pool-critical member. Do not replace the SSD solely because of old counters.
4. After physical work, re-identify by serial/WWN and run a deliberately scheduled,
   guarded full scrub plus appropriate SMART/link checks. Preserve pre/post
   counters and validate representative application I/O.
5. Only after cause/verification closure, consider clearing historical ZFS errors
   and verify native alert recovery. SMART/PHY lifetime counters need not become
   zero; the criterion is no new errors from a documented baseline.

**Acceptance:** physical repair/inspection receipt recorded; complete full scrub
with zero unresolved scan errors; no new link/device errors during verification;
applications healthy; native notification receipt confirmed; alert state explained.
A partial/canceled scrub or an API job's SUCCESS alone does not meet acceptance.

**Scheduling trap:** TrueNAS's inspected scrub scheduler derives its threshold
from scrub-start history, not necessarily the last successful full scan. The
canceled manual start may delay the next eligible scheduled scrub. Explicitly
verify/start the post-repair full scan; do not just wait for Sunday.

### Phase 1 — Publish cleanup and close controller/deployment drift

**Depends on:** storage safety assessment; suitable maintenance window for any
recreation. Preparing/reviewing a branch does not require waiting for physical work.

- Review the existing dirty tree rather than resetting or redoing retirement.
  Create coherent commits/PRs without unrelated `.entire/` or local state/secrets.
- Audit actual Portainer Git references, polling/webhooks and affected Compose
  changes before merging to `main`. Publishing can deploy automatically; it is
  not a documentation-only operation.
- Confirm Ansible-owned `/srv/init` stays limited to Traefik, discovery proxy,
  Portainer and Pocket ID. Do not run stale pre-cleanup source against the host.
- Recreate Jellyfin through its owning Portainer stack, without unrelated image
  upgrades. Verify persisted disk scratch path, absence of old tmpfs, QSV device
  access and an actual hardware-transcode/playback test. Add appropriate disk
  free-space alerting and application-safe scratch cleanup/limit policy.
- Reconcile `jellyplex-watched`: running project was absent from Portainer's
  controller inventory. Adopt/redeploy through the intended owner only after
  capturing existing settings/secrets; do not delete a working service blindly.
- Run source and live ownership/drift checks. Inventory membership alone is not
  evidence of actual Portainer ownership.

**Acceptance:** intended changes reviewed/published; no retired resource recreated;
Jellyfin real transcode works on disk; live/controller/source inventory agrees;
credentials and relative-path Git volumes survive recreation; deployment rollback
is documented without restoring retired workloads unintentionally.

### Phase 2 — Make monitoring reproducible and operationally complete

**Depends on:** Phase 1 controller facts. Start native PVE delivery/coverage discovery
and passive metrics collection early; do not delay visibility until every role exists.

- Record/manage agent binaries, versions, services, users, key/token lifecycle,
  connection mode, non-secret desired alert rules and restore procedure in the
  owning layer. Proxmox is currently manually managed, not blanket-Ansible-owned.
- Replace Docker's dynamic bridge/container-IP UFW exception with a durable
  restricted connection. Prefer supported outbound agent connectivity where
  appropriate; test host identity/duplicate-system handling before switching.
  Otherwise reconcile a stable source-pinned rule. Do not open 45876 to the LAN.
- Reconcile alerts idempotently through supported Beszel APIs; do not mutate its
  database directly or overwrite recipient/controller settings indiscriminately.
- Cover guest/host memory, disk capacity, down state, pool/SMART/link faults and
  backup/job failures through the appropriate Beszel/native mechanism. Confirm
  actual supported capabilities on installed versions rather than assuming them.
- Enable and test PVE native backup/job notifications (currently disabled).
  TrueNAS now has working native SMTP; retain it for storage events and account
  for SMTP credential rotation in both TrueNAS and Beszel.
- Add independent external heartbeat/outage detection: a Beszel hub on this same
  server cannot email about its own complete host/power failure.

**Acceptance:** configuration can be re-established on rebuild/recreation without
one-off rules; agents have correct identities and bounded access; rules and native
job coverage verified; test receipts recorded; external outage detection demonstrated
with a safe test, not a fabricated production incident.

### Phase 3 — Establish independent, tested recovery before disruptive cutovers

**Depends on:** storage closure for heavy backup/restore exercises; inventory and
recovery-target selection can happen earlier. This precedes Phase 4 network cutover.

- Inventory application data, databases, controller settings, keys and dependencies.
  Define prioritized RPO/RTO with the user, especially photos, Nextcloud, databases,
  NAS config, PVE/VM recovery and Portainer/Pocket ID.
- Produce application-consistent database dumps and paired application-data/config
  backups; do not treat live database-file copies or VM snapshots as sufficient.
- Choose independently retained/versioned off-host storage and protect deletion
  authority/encryption keys. Verify B2 bucket retention/versioning and actual restore
  behavior; current PUSH/SYNC success is not proof of historical recovery.
- Encrypt secret-bearing archives/dumps before uploading. Do not turn on cloud-sync
  encryption in place without a planned migration and recovery-key verification.
- Test restoration into isolated targets. Do not restore over production or enroll
  a restored guest with the production IP/MAC/Tailscale identity by accident.
- Budget retained backups AND dataset snapshots. `refquota=1.5T` limits live
  referenced data only; Proxmox backups currently total about 1.87 TiB, split
  approximately 0.94 TiB live plus 0.94 TiB snapshots. Do not purge retention to
  "fix" this expected accounting or silently delete retained ai-dev backups.

**Acceptance:** dated restore drill proves readable data and usable application
state; independent loss/deletion protection and keys verified; RPO/RTO and retention
capacity recorded; recovery works without the original server/production pool.

### Phase 4 — Harden management access and split logical workload networks

**Depends on:** rollback access, tested recovery and monitoring. Keep one Docker VM.

- Define access matrix for infrastructure/admin, personal-data, media, download/
  indexer and monitoring workloads; preserve existing family/media client access.
- Restrict privileged routes (Portainer, Traefik dashboard, TrueNAS/admin) to
  approved management identities/networks and appropriate authentication.
  `kds-media-only` is NOT management-only: its DFLT/Tailnet/proxy allowance is
  broader, and the dashboard lacks explicit auth middleware in the reviewed source.
- Reduce universal shared `proxy` network lateral reachability in staged changes;
  retain isolated per-application databases, explicit dependencies/egress and
  only necessary ingress paths. Audit backend data export restrictions too.
- Tighten router source/ingress anti-spoofing with explicit VPN/management exceptions.
  Preserve OOB and recovery posture. Check real Docker/UFW behavior, not only
  Compose network declarations or source-IP assumptions behind proxies.
- Keep Portainer direct socket access and Traefik's restricted discovery proxy.

**Acceptance:** positive and negative access tests from MGMT/DFLT/KDS/GST and
approved/unapproved Tailnet identities; unauthorized admin/lateral access denied;
SSO, DNS/TLS, NFS, backups and intended media access remain working; OOB rollback
verified. Deploy one boundary at a time, not a router/host/all-app rewrite together.

### Phase 5 — Bound heavy jobs using measured peaks

**Depends on:** healthy storage and reliable monitoring; collect baseline metrics
in Phase 2 before changing limits. Apply the established access matrix.

- Inventory actual triggers and peak overlaps for Immich ML/indexing, Plex/Jellyfin
  analysis/transcoding, Kometa, download/unpack/import, Recyclarr, snapshots,
  cloud sync, vzdump, SMART and scrubs.
- Provide admission/concurrency control across job families, not merely different
  cron start times. Give interactive playback appropriate CPU/GPU/I/O priority.
  GPU sharing is not GPU isolation, and separate per-job locks do not enforce a
  shared global limit unless explicitly designed to do so.
- Use measured memory/CPU/I/O budgets and conservative recoverable limits;
  account for application workers, DB shared memory, caches and host headroom.
  Do not blindly cap databases or remove ML if the user needs the feature.
- Measure representative peaks and sustained swap/PSI/OOM behavior over complete
  busy cycles. Retained swap alone is not proof of current memory pressure.
- Increase Docker RAM only if measurements justify it and the host/UniFi/backup
  safety budget still holds. Do not start cold UniFi in the nightly vzdump window.

**Acceptance:** overlapping heavy work respects shared admission rules; resource
budgets demonstrated in representative busy cycles; no unacceptable playback/job
regression or sustained memory pressure; scheduled-job success and retries monitored.

### Phase 6 — Close out and maintain

- Perform a controlled configuration/recovery rehearsal, reconcile ownership drift,
  retire only this work's obsolete transient helpers after preserving evidence,
  and update system-of-record docs with final observed state.
- Ensure security/monitoring/job controls survive recreation/reboot and routine
  GitOps updates. Record maintenance cadence, alert owner and next restore drill.
- Mark phases complete only when their acceptance evidence exists; distinguish
  code merged, live deployed, and human/operational acceptance.

## User decisions and physical inputs still needed

- Physical-path inspection/repair access and maintenance window; whether any
  earlier cable work has already occurred. Software cannot reseat a connector.
- Receipt of native TrueNAS test/review-required messages (Beszel is confirmed).
- Recovery RPO/RTO, off-host retention/budget, key custody and isolated restore
  target. Preserve existing backups until an explicit replacement/deletion plan.
- Authorized management identities and acceptable access changes for other
  household clients; an independent heartbeat target/provider if one is needed.
- Deployment window and publication/merge approval as required by the chosen
  workflow. Do not interpret this plan as blanket destructive-change authority.

## Repository and workflow custody

- Path: `/Users/mm/dev/home-infra`; remote `mich-murphy/home-infra`;
  branch **main**, observed HEAD **085e7634621f28f37a1fc9da9284209217102866**.
- Broad retirement/Jellyfin/docs/vault changes and six new fixture JSON files
  remain dirty/uncommitted. `docs/architecture-review.md` was also created here.
  No commit/push/PR/merge or full Terraform apply was performed in this work.
- `.entire/` is pre-existing unrelated content: leave untouched. `.envrc`, vault
  password, Terraform state/backups, maintenance artifacts and private identities
  must not be printed or committed. Review encrypted vault changes by metadata
  and secure semantic verification, not dumping ciphertext or decrypted values.
- Default GitHub account `michaelmbc` had only READ access. The authenticated
  `mich-murphy` identity had the permissions used to remove the unused CI secret.
  Confirm publishing identity/permissions without exposing tokens.
- Previous optional autonomous-controller preflight was blocked on macOS by a
  Linux `/proc` process-identity dependency. No governed ledger/task/PR authority
  was initialized. Ignored `.no-mistakes/` holds preflight artifacts, not proof
  of delivery. Do not bypass rejected controller actions or claim a merged run;
  use a supported setup if electing governed delivery in the next session.

Relevant checks to refresh: Terraform fmt/validate in both roots;
`tests/terraform-cloud-init.sh`; `tests/docker-hardening.sh` using workflow
placeholder environment; `scripts/check-portainer-drift.sh --source-only` plus
live drift/controller verification; Ansible syntax, local RouterOS/storage tests
and lint; ShellCheck; Actionlint; `git diff --check`. These checks do not authorize
an infrastructure apply. Syntax checks involving the vault need secure decryption
access; lint previously warned that it could not decrypt that file.

## Access and safe live resume

- Proxmox: **`ssh root@proxmox`** through Tailscale. Default `mm@proxmox` was
  denied by tailnet SSH policy; do not weaken policy just to use the wrong user.
- Docker: **`ssh docker-host`** as `mm`, with `sudo -n` available.
  LAN address `10.77.20.246`.
- TrueNAS: **`truenas_admin@10.77.20.101` through `-J docker-host`**. Direct
  laptop routing timed out. Use xportal personal 1Password, `Private` vault:
  the `truenas` SSH_KEY item (`4dmistkodbf4myyhuht6j7ze7m`) and LOGIN item
  (`sxujwkzvsyxpm26k53pgq5oeha`). Sudo needs the login password.
- Private-vault access uses desktop approval with the explicit
  `xportal.1password.com` account, without the restricted `OP_SERVICE_ACCOUNT_TOKEN`
  overriding it. Fetch only needed fields; use a temporary mode-0600 OpenSSH
  identity, strict known-host checking and cleanup. Keep passwords out of command
  arguments, logs and files; use secure stdin/local API calls. Earlier local
  `~/.ssh/services`/`media` files were not usable; do not "repair" them speculatively.
- Beszel: `https://beszel.local.elmurphy.com`, `Private / Beszel` login.
  In this session the item username and password read via `op read` worked for
  `_superusers` API auth. Do not assume the separate Email field is its login
  identity or that a concealed `op item get` value is the actual password.
- Portainer: obtain its existing credentials/controller settings securely from
  1Password. Endpoint/stack IDs are snapshots, not immutable restore identifiers.

Read-only TrueNAS checks once securely connected (use sudo where needed):

```sh
sudo zpool status -LPv slow
sudo zfs get -H -o name,property,value,source sync slow/photos slow/owncloud
sudo systemctl show home-infra-truenas-scrub-20261007 \
  --property=ActiveState,SubState,ExecMainStatus
sudo journalctl -u home-infra-truenas-scrub-20261007 -n 25 --no-pager
```

Read the JSON records under `/var/lib/home-infra-maintenance/` securely:

- `truenas-storage-before-20261007.json`: original properties/error baseline.
- `truenas-scrub-20261007.json`: **STOPPED_FOR_REVIEW**, stop requested.
- `truenas-scrub-notification-67305.json`: SMTP_ACCEPTED, mail job 67350.
- `truenas-scrub-watch-20261007.py` and `truenas-scrub-notify-67305.py`: one-off
  operational helpers; do not blindly restart them. The guard's `latest` field
  is the last good sample, not the triggering sample; current sysfs counters
  established the +1/+1 increase separately.

These units are transient and do not restart after reboot. Their failed/dead
state now reflects the deliberate guard stop/completed notification, not a
request to retry automatically. Laptop `/tmp/home-infra-nas-*` helpers may still
exist but are disposable, not the durable handover or a credential store.

Beszel Docker/Proxmox system IDs were `s2915p5o7846g6q` / `bwma6wgz1e3f6f2`.
Desired current rules: Docker CPU 80%/10 min, memory 90%/5 min, disk 80%/10 min;
Proxmox CPU 90%/10 min, memory 90%/5 min, disk 80%/10 min; Status enabled with
stored value 0/min field 2 for both. Do not promise exact status delay without
checking the installed engine's semantics. Runtime Docker connectivity uses
hub `172.20.1.8`, bridge `br-6e5e47ea39f2`, agent `100.96.174.126:45876/tcp`;
these dynamic identifiers must be refreshed before any rule/recreation change.

## Reference map and next-session brief

- [TrueNAS storage](truenas-storage.md): storage policies, schedules and evidence.
- [Docker deployment](docker-deployment.md): controller seam, Git settings,
  Jellyfin transition and monitoring snapshot.
- [Proxmox host](proxmox-host.md): memory, backup, thermal/swap policy.
- [Docker hardening](docker-hardening.md): security exceptions and contracts.
- [Architecture snapshot](architecture-review.md): retirement history, not a
  completed future architecture.
- `network/inventory.yaml`, `ansible/roles/routeros/`,
  `docker/init/traefik-dynamic.yml`: actual network and ingress intent.
- `docker/portainer-stacks.yaml`, `tests/`, `.github/workflows/`: desired
  application inventory and validation gates.

Suggested next-session opening:

> Read docs/homelab-roadmap-handover.md and the owning policy docs. Preserve the
> dirty tree and unrelated .entire/. First verify the canceled TrueNAS scrub,
> fresh PHY 3 errors and notification receipt; do not rerun/clear anything to
> silence the fault. Establish backup safety and coordinate physical-path
> closure. Prepare the retirement publication/controller plan without automatic
> rollout. Keep Compose, one Docker VM and Portainer's direct socket; implement
> remaining phases sequentially with measured acceptance and rollback. Report
> which steps need physical access or user decisions, and distinguish code,
> deployment and human acceptance.
