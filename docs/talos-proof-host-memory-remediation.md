# Host swap stop: investigation and proposed maintenance

**Status: approved maintenance COMPLETED on2026-11-13; production recovered.
KHO restriction removed; exact original swap-event causation remains unproved.
VM120 stays off.**

The user subsequently selected the **newest installed kernel** instead of the
proposed one-boot old-kernel selection and explicitly approved the temporary Docker
service/socket holds. Those instructions supersede the earlier pending decisions
below. One host reboot was performed; no kernel pin was applied.

### Verified outcome

- Running kernel **7.0.14-24-pve**, effective `kho=off`, new boot ID; KHO debugfs
  output absent and CmaTotal/CmaFree both0. Kernel plus parameter is a two-variable
  mitigation, not an isolated causal experiment.
- Host and NAS pools healthy. All **36original containers** running,31healthy and
 5without health checks. IDs/images/creation times/mounts unchanged; restart/start
  observations are recorded as approved maintenance, not an unchanged-uptime claim.
  These are runtime/health/storage-continuity checks, not an application-level data
  integrity or end-to-end functionality audit.
- All five exact NFS exports verified before Docker startup. Original Docker
  service/socket enabled/active states restored and owned masks removed.
- VM102 onboot1 restored; all four captured VM configuration hashes match their
  originals. Host backup storage properties/mount and backup job/exclusions restored.
  PVE reordered only `local.content`'s four-item set during storage serialization:
  raw storage.cfg hash differs, but every configuration field has the same meaning.
  The original bytes and failed raw/string comparisons are retained, not overwritten.
- Original swappiness60, ARC cap3GiB, lz4 zram priority100 and proof24KiB swap baseline
  retained. New-boot120-second observation: minimum available6215.44MiB, swap usage0,
  swap-in/out delta0. This is not representative soak/capacity or a no-recurrence proof.
- VM101/102 running; VM111/120 off.111canonical proof files unchanged; no application
  grant/invocation or native Nextcloud acceptance. Temporary NAS key removed.
- Shutdown-request to full container-health verification was approximately22.93min;
  this is an observation interval, not exact per-service downtime.

**Retained failures:** VM102's shutdown command timed out after301.26s; the guest
subsequently stopped without another request or force. Host journal identifies a
QGA `guest-shutdown` timeout, not the underlying delay's cause. Postboot1Password
read timed out and SSH agent signing failed; authenticated read-only NAS checks then
used the existing temporary key directly, strict host checking intact, and no sudo.
An unprivileged PATH failure was corrected with absolute ZFS paths. Initial `stat`
on an idle automount did not activate NFS; explicit directory traversal succeeded
and all sources were verified before unmasking. No failures are erased by recovery.

Evidence: [maintenance completion](evidence/talos-acceptance/kho-maintenance-completed-f7a723ea8a0d4640a2e586022501ce5a.json).
The initial completion manifest freezes301private artifacts, including35host
rollback/mutation records and7guest hold records. A subsequent read-only confirmation
also verified debugfs was mounted and the new kernel still compiles KHO/default-enable;
its unknown-parameter warning did not name `kho`. The output absence is not merely
an unmounted debugfs observation. Follow-up remains in the same private capture. Original guard-stop/RCA evidence remains immutable.
The prior Talos CI failure for MariaDB image-contract drift is separate and unfixed;
no image pin or test was changed during maintenance.

### Earlier scope decisions and preflight (historical)


After confirming BMC is currently unavailable, the user explicitly directed execution
and accepted recovery waiting until they are on-site. That waives the immediate-console
gate for this window; it does not establish remote recovery capability. Do not ask for
that same waiver again. Read-only preflight then found the boot-selection and NAS
management dependencies below. They require explicit scope review, not a new console
approval. No boot settings, VM startup flags, backup-storage settings or production
workloads have been changed. Nothing is queued to run automatically.

The user requires the underlying cause to be identified and resolved before further
proof work. A restart, a quieter current snapshot, or a relaxed guard is not resolution.
The user authorized the documented production maintenance and subsequent adjustments.
That execution is now complete; it is not standing authority for another reboot or
unrelated changes. VM120 startup remains excluded.

## Earlier execution preflight and requested adjustments

Capture: `diagnostics/host-maintenance-execution-8ecc697f-c493-4cc9-bfc8-f85bdae041dd`.

- Production baseline:36running containers,31healthy/5without health checks.
  Host and NAS pools report healthy; NFS is active. Two established NAS client
  rows were captured. No active Proxmox tasks were observed.
- Both managed ESPs were inspected read-only in a private mount namespace. Their
  current7.0.14-17 kernel/initrd hashes match `/boot`. Both loaders use default
  `proxmox-*`; newer7.0.14-24 is already installed and present on both ESPs.
  No permanent/next-boot pin was present. An ordinary default reboot would not
  preserve the intended same-kernel comparison.
- The five production NFS automount units are active and ordered before
  local-fs→sysinit→basic→Docker. Docker's service/socket are both enabled/active.
  This establishes existing ordering rather than relying only on repository defaults.
- NAS administration succeeded through the established Docker SSH jump host.
  The attempted Proxmox jump timed out and is preserved. Thus Docker's guest OS
  is needed for full NAS pool-health verification after reboot, but application
  workloads should not start before that verification.
- Only the documented NAS SSH key/login were used privately. The first key-format
  assertion failed before any key file was created; explicit OpenSSH-format retrieval
  succeeded. The temporary0600key was removed after preflight. No credential values
  were logged or published. The local recorder helper was editor-created then made
 0600 rather than O_EXCL-created; it contains code only. Capture records use O_EXCL.

**Requested additional scope, not applied:**

1. **One-boot selection of7.0.14-17-pve** using the supported next-boot selection,
   with both ESP entries verified and the permanent default unchanged. This avoids
   mixing a kernel upgrade with `kho=off`. Verify the one-shot selection is consumed
   after boot; retain original/default selection metadata for rollback.
2. **Temporary persistent startup masks for Docker service and socket on VM102**,
   without stopping them merely to stage the masks. Preserve original unit state and
   reject pre-existing/conflicting mask paths. Gracefully shut down the guest as
   planned. After host/NAS recovery, start102's OS with both Docker units held,
   use it as the SSH jump host to verify NAS pool/export health, verify all expected
   NFS sources, then remove only the owned masks, restore the original enabled
   states, and start Docker. No container configuration/data/credential changes.

This changes the recovery sequence from “NAS fully verified before102 boots” to
“NAS exports available,102OS boots with Docker held, NAS fully verified, then Docker
workloads start”. If either unit starts unexpectedly or NAS verification fails,
keep workloads held and preserve diagnostics; do not silently widen the procedure.
These adjustments are not yet approved merely by accepting delayed BMC recovery.

## What is established

1. At **2026-11-12 07:18:58 UTC**, the guard reported `sustained host swap IO` and
   its stop handler confirmed the original QEMU process exited. This condition
   means `pswpin + pswpout` increased on three successive comparisons. There is
   no minimum transfer size or PSI prerequisite. The guard acted consistently
   with its conservative policy; low PSI does not demonstrate a false positive.
2. The running host kernel is **7.0.14-17-pve**. It enables
   `CONFIG_KEXEC_HANDOVER_ENABLE_DEFAULT=y`; the captured command line has no
   `kho=` override. Existing debugfs exposes KHO output, with `finalize=0`.
   Three nonoverlapping scratch regions are **296 + 1242 + 1312 = 2850 MiB**.
   The captured boot ID matches the incident journal's boot ID.
3. After the stop, the host reported **CmaTotal=0**, but **CmaFree≈1446 MiB**.
   Linux documents that KHO scratch regions are marked CMA/movable-only.
   Proxmox documents this exact accounting signature and its restriction on
   nonmovable/pinned allocations. Both production VMs101 and102 have a configured
   PCI-passthrough entry; VM120 has none. These were read-only observations.
4. Historical minute-resolution Proxmox RRD data shows VM101+102 host memory
   charges near20.41GiB and VM120 near2.77–2.78GiB, without a sudden growth near
   the stop. ARC fell from approximately2718MiB at07:11 to2288MiB at07:13;
   swap occupancy subsequently grew. This is consistent with reclaim activity,
   but does not identify its initiator. RRD values are consolidated observations,
   not exact event timestamps or proof of absent short pressure spikes.
5. Later process/cgroup observations place most current swapped residency in
   VM102's QEMU process. **A swapped victim is not necessarily the allocation
   that initiated reclaim.** No production guest or application was modified.
6. Follow-up planning verified the sole swap device is **RAM-backed zram**, lz4,
   priority100, approximately3.73GiB. No disk swap is configured. The guard's
   swap-page counters remain a valid policy trigger, but are **not evidence of
   physical-disk thrashing**. No zram, swappiness or swap-baseline change is proposed.

## What is not established

**The exact allocation/reclaim path responsible for the three triggering intervals
is not recoverable from the evidence collected so far.** The guard omitted the
failing sample and separate swap counters/deltas. No existing sysstat/atop history
was found at the usual locations. Existing kernel journal records did not identify
an OOM or KHO allocation failure for this incident.

KHO is a **confirmed allocator restriction and credible contributor**, not a proven
sole cause of this particular event. The current free-CMA quantity is not its
incident-time quantity. Stable VM charges do not exclude allocation churn.

Do not call `MemAvailable - CmaFree` corrected capacity: allocation eligibility
also depends on zone, order, watermarks, migratability and pinning. Nor is2850MiB
universally wasted memory: movable allocations can use scratch. Disabling KHO
need not increase aggregate MemAvailable by that amount.

## Recommended cause-directed mitigation — approval required

Address the confirmed, default-enabled KHO restriction before considering a new
proof window. The Proxmox maintainer's documented mitigation is **`kho=off` on the
host kernel command line, effective after reboot**. A replacement kernel is an
alternative only after verifying its actual configuration/fix; a proposed mailing
list patch is not proof that an installed or available kernel includes it.

This changes the **production Proxmox host** and requires coordinated downtime for
existing guests, including TrueNAS and Docker. It is outside the proof's current
no-production-change authority. No bootloader update, package installation,
guest stop/restart, host reboot, kexec or debugfs write has been performed.

Approval request and review location:
https://github.com/mich-murphy/home-infra/blob/feat/talos-live-proof/docs/talos-proof-host-memory-remediation.md

An approved maintenance window must specify the operator, production shutdown and
startup order, data-safety checks, rollback and acceptable outage. Before execution:

- Identify the **active** boot mechanism; do not assume GRUB or systemd-boot from
  the mere existence of configuration files. Preserve exact original boot config
  privately. Select the supported mechanism for adding only `kho=off` while
  preserving all other flags and GPU/IOMMU settings.
- Record production health/guest identities, host kernel/boot ID, current boot
  selection, VM configuration and original proof swap baseline. Do not reset the
  baseline or overwrite earlier observations. Coordinate NAS/client shutdown
  rather than treating a host reboot as isolated to VM120.
- Keep VM120 `onboot=0` and off. This maintenance approval would **not** authorize
  application activation, direct `qm start`, guard changes or etcd reset/recovery.
- Keep rollback boot selection/configuration available. If the change affects
  boot, storage or passthrough behavior, stop and use the approved rollback;
  rollback itself may require another production outage.

## Concrete window plan — awaiting time and execution approval

### Verified planning facts

Read-only capture: `diagnostics/host-maintenance-plan-f055d402-4bfb-4a8c-b730-1ec2b7869c0f`.

- Active EFI entry and `bootctl status` identify **systemd-boot257.13-1~deb13u1**,
  `/EFI/systemd/systemd-bootx64.efi`; Secure Boot is disabled. There are two
  configured managed ESP UUIDs. Their present contents/health have not yet been
  independently checked; configuration count is not a synchronization guarantee.
- The appropriate command-line file is **`/etc/kernel/cmdline`**. Its original
  bytes/hash were captured privately. It currently contains two tokens and no
  `kho=` argument. The supported propagation operation is
  **`proxmox-boot-tool refresh`**, not `update-grub`. Neither was run.
- VM101: onboot1, order1, up60, no guest agent. VM102: onboot1, order2, guest
  agent enabled. Both are running; VM111 andVM120 are stopped. A configured
  60-second delay does not establish NAS/export readiness.
- Docker uses TrueNAS NFS exports according to the maintained storage role.
  Proxmox also has a mounted NFSv4 backup-only storage at
  `/mnt/pve/truenas-backups`, enabled by default (no explicit disable property).
  NAS shutdown therefore affects both Docker and the host's backup client.
- Backup job remains02:30 **Australia/Melbourne**, enabled/repeat-missed, with
  exclusions9001,9003,120 unchanged. At this date02:30AEDT corresponds to15:30UTC
  on the preceding UTC date. Recompute the offset for the actual window date.
- The corrected read-only active-task query returned zero tasks. The initial
  unsupported `--running` query failed and is preserved. Neither observation is
  a future execution-time clearance.

### Proposed authorization envelope

Reserve **90 minutes**, with rollback time included; this is a planning allowance,
not a guaranteed outage duration or permission to force shutdown. Select a window
well away from02:30 local backups and confirm no running/pending backup, scrub,
replication, migration or other conflicting maintenance immediately beforehand.
The operator must confirm working BMC/physical console access independent of these
VMs and the production outage notice. Do not collect console credentials in Git.

Execution approval must explicitly cover:

1. Adding only `kho=off` to the host's existing kernel command line and refreshing
   both configured ESPs, retaining kernel7.0.14-17-pve for the comparison. If boot
   selection would change kernel version, stop for review rather than silently
   pinning/upgrading or testing two changes together.
2. Temporarily setting **VM102 onboot=0**, then restoring its original value1
   after NAS readiness and controlled Docker recovery. VM101's startup settings
   stay unchanged; VM111 andVM120 remain off. This extra temporary change prevents
   the existing automatic60-second sequence from racing NAS readiness.
3. Temporarily disabling only **`truenas-backups`** storage activation and cleanly
   unmounting its host NFS mount before NAS shutdown, then restoring the exact
   original storage configuration and mount after NAS recovery. This is a scoped
   host-storage configuration/mount exception, not data deletion or export change.
   No forced/lazy unmount; if busy or reacquired, abort and investigate. Preserve
   the backup job, retention, server/export/options and VM120 exclusion unchanged.
4. Graceful shutdown of **Docker102, then TrueNAS101**, one host reboot, and
   controlled recovery in the opposite dependency order. TrueNAS has no guest
   agent: use its supported graceful shutdown/ACPI path and verify it actually
   stops. No force-stop, reset, power cut or automatic timeout escalation.
5. Restoring the saved boot configuration and temporary settings if rollback is
   required; a second production reboot is allowed only if explicitly included
   in the approved window. No proof-VM start is part of this authorization.

### Execution sequence after approval — not performed

1. **Go/no-go:** confirm date/time, named operator, outage and console availability;
   refresh task/backup state, production health, NAS pool/export health and client
   inventory. Starting102 may automatically start Docker: the operator must first
   verify the guest's current NFS/automount and Docker startup interlocks prevent
   writes to bare local mountpoint directories. Repository declarations alone are
   insufficient. If that gate cannot be established, stop planning execution and
   obtain a separately reviewed guest-side service-hold strategy; no such service
   change is implicitly authorized here. Preserve original boot/VM102/storage configuration bytes and hashes
   outside Git. Verify managed ESP state, retained kernel/initrd and recovery path.
   If any baseline is unhealthy or a required check is unavailable, do not start.
2. **Prepare reversibly:** set VM102's temporary no-autostart state. Stage only
   `kho=off`, refresh managed ESPs and verify the generated entries on both. Compare
   all other options and boot selection against the saved baseline. On refresh
   failure or partial synchronization, restore/reconcile before any reboot.
3. **Drain clients:** gracefully stop Docker102 and verify stopped, with its NFS
   clients quiesced. Quiesce any other NAS clients through the operator. With no
   active backup/storage users, disable only the host backup storage activation
   and cleanly unmount its NFS mount. If shutdown or unmount fails, do not force
   it and do not stop NAS; restore the safe pre-window state or pause for review.
4. **Stop NAS, then reboot:** gracefully stop101, verify stopped, then perform the
   approved host reboot. Do not use kexec, KHO finalization, disk wipes, pool
   imports with force, or automatic reboot retries.
5. **Restore dependencies:** via console verify the same kernel plus `kho=off`,
   host boot/storage/network/passthrough health and no unexpected VM startup.
   VM101 may start automatically with its unchanged onboot1: verify NAS pool and
   actual export readiness, not merely VM running state. VM102 must still be off.
   Restore the host backup-storage original activation setting and verify its
   mount/source; then start102, check the expected NFS sources before accepting
   application recovery, and restore its original onboot1 after successful recovery.
6. **Verify and close:** check the approved production services, expected
   maintenance-related restarts, backup accessibility and exclusions. Capture new
   boot/KHO/CMA/reclaim/swap/PSI observations with VM120 still off. Apply the
   acceptance gates below. No Nextcloud or other proof activation follows automatically.

### Rollback and abort

- Before reboot: restore exact saved command-line bytes and refresh/verify both
  ESPs. Restore temporary storage/onboot state only in a dependency-safe sequence.
- If the host fails to boot: use the confirmed console/recovery route. A one-boot
  removal of `kho=off` is possible only if the boot-entry editor is available and
  verified beforehand; otherwise use the approved recovery medium/procedure.
  Do not assume an SSH connection will be available.
- **Selecting an older kernel alone does not undo this parameter:** refresh
  propagates the command line to managed entries. Restore the saved persistent
  command line and refresh, or perform a verified one-boot option edit.
- If the host boots but production recovery fails, keep Docker off until its
  storage dependencies are safe; preserve diagnostics and use the approved
  rollback. Do not mount empty local directories as substitutes for NFS, recreate
  credentials/data, or force a guest through a failed shutdown to meet the90-minute
  allowance.
- If timing, recovery access, synchronization or health is uncertain, abort or
  escalate. Do not convert the maintenance plan into permission for unrelated fixes.

**Decision outcome:** user chose the newest installed kernel, approved the Docker
startup holds, and accepted delayed console recovery. Maintenance has completed as
recorded above. No additional reboot or proof activation is queued. Further proof
work requires its own fresh identity/resource/authority and acceptance checks.

## Verification and acceptance gates

1. **Mitigation installed:** independently verify the new boot ID, running kernel,
   effective `kho=off` (or verified disabled-default kernel with no enabling
   override), expected KHO scratch absence and CMA accounting. Do not write to
   KHO debugfs or finalize/execute a handover as a test.
2. **Production recovered:** perform the approved guest/storage/network and
   service checks; record expected maintenance-related starts separately from
   historical unchanged-source evidence. Confirm original GPU/IOMMU settings and
   proof backup exclusion. Do not claim production was untouched by maintenance.
3. **Host baseline:** retain bounded comparable allocator, zone, reclaim, separate
   swap counters and PSI observations while VM120 remains off. Treat counter
   resets across boot IDs correctly; preserve the original24KiB proof baseline.
   A single quiet sample is not acceptance or historical causal proof.
4. **Diagnostic visibility:** any proposed change to capture failing guard samples
   and separate counter deltas requires its own reviewed implementation/tests and
   deployment authority. Existing thresholds, cleanup, process identity and
   baseline protection must remain intact. No such change is included here.
5. **Controlled proof verification:** only after mitigation verification and an
   explicitly approved bounded guarded-start window, evaluate the idle proof
   under unchanged startup/running limits. Preserve evidence if it stops again;
   do not retry automatically. This is a verification experiment, not permission
   to resume Nextcloud or other application work.
6. **Resolution decision:** removing KHO's restriction verifies that mitigation,
   not retroactive attribution of the original swap event. If the comparable
   observation still swaps, or attribution/visibility remains insufficient,
   retain the unresolved root-cause finding and keep application work blocked.
   No representative capacity, production readiness or no-recurrence guarantee
   follows from a short successful window.

## Sources

- Proxmox bootloader identification and systemd-boot command-line propagation:
  https://pve.proxmox.com/wiki/Host%5FBootloader
- Maintained local dependencies: [host policy](proxmox-host.md) and
  [Docker NFS declarations](../ansible/roles/docker-host/defaults/main.yaml).
- Proxmox primary discussion, exact signature and `kho=off` mitigation:
  https://lore.proxmox.com/pve-devel/20260714124456.347992-1-d.csapak@proxmox.com/t/
- Linux7.0 KHO scratch-region allocation semantics:
  https://docs.kernel.org/7.0/core-api/kho/index.html
- Linux7.0 KHO administration and read-only debugfs interface descriptions:
  https://docs.kernel.org/7.0/admin-guide/mm/kho.html

The original stop evidence remains immutable. New read-only investigation artifacts
are private under `diagnostics/guard-root-cause-0826b615-0fbf-474b-bf3f-117e4a67ab6d`.
The parent owns acceptance; the independent offline reviewer agrees that exact
incident causation remains unproved. No lifecycle, policy, memory limit, ARC,
swappiness, production configuration or workload mutation is a substitute for
closing that gap.
