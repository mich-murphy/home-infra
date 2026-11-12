# Host swap stop: investigation and proposed maintenance

**Status: investigation incomplete; mitigation proposed, NOT applied. VM120 stays off.**

The user requires the underlying cause to be identified and resolved before further
proof work. A restart, a quieter current snapshot, or a relaxed guard is not resolution.
This plan does not authorize production changes, a host reboot, or VM120 startup.

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
