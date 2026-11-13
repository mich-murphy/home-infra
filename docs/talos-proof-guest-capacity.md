# Guest capacity decision — offline plan, not activation authority

**Parent-reviewed offline analysis, not capacity approval. VM120 remains OFF;
the one authorized start is consumed.** This track permits capacity planning only:
no restart, resize, tuning,
lower limits, guard extension, production memory reallocation or relaxation of the
832 MiB gate. Only 2560/3072 MiB profiles are currently approved. Delivery,
readiness and acceptance remain parent-owned. This document changes none of them.

## Evidence boundary

The quantitative baseline uses existing memory/summary captures in diagnostic capture
`guarded-platform-recovery-201099d8-0301-4c6b-8b14-512b51cf5d05`; interpretation also
uses its correction record, the public parent review and cited operations history.
Artifact names and SHA-256 references below identify private originals without
publishing their contents, addresses, identities or credentials. No runtime/API,
SSH, credential or image execution was performed; no public research was needed.
Captured source: `754a6476be7a026f1b1b8f931dc647094e3cfb35`; analysis HEAD:
`0c0b8d97947cf6947f693678eb6fcf3f9cbfd042`. This track is capacity planning only;
the parent's separate offline verifier work is not excluded or authorized by this
plan. These are historical observations, **not fresh admission receipts**.

The host ran kernel **7.0.14-24-pve, `kho=off`** after approved maintenance.
The guest node reports Talos v1.14.5, kernel6.18.58-talos and kubelet v1.36.5.
Host and guest kernels/accounting must not be confused. **Correction acknowledged:**
the raw follow-up's claimed Flux suspension failure was verifier overreach, not an
approved failed barrier. The [parent review](evidence/talos-acceptance/guarded-platform-parent-review-8954422ca5934f0d9fda169a62f7a71d.json)
and private `correction-summary.json` establish that GitRepository `spec.suspend`
was absent as expected for retained fetch intent, inert with Flux controllers
absent. It was not required to be suspended. Requiring suspension on every Flux
custom resource was the rejected blanket predicate and must not be reused.
VM120's stop was authorized proof-only administrative containment caused by that
verifier overreach, **not a host resource-guard/swap failure**. Current Kustomization
and later Flux state were not collected; do not infer them from historical cleanup.
That inspection gap remains unresolved independently of the real memory gate
failure. Raw failure/stop artifacts remain preserved, not rewritten.

## Quantified guest baseline

MiB = bytes / 1048576; captured Linux meminfo kB and Kubernetes Ki are divided by
1024. Values below are rounded only for display. `window300` node memory timestamps
are 02:20:40Z and 02:25:50Z on2026-11-13; the paired Talos reads are nearby rather
than atomic. Pair metadata records both fresh within120seconds at capture time.

| Quantity | Initial | Final | Meaning |
| --- | ---: | ---: | --- |
| Configured fixed VM RAM | 3072 | 3072 | Host configuration envelope, not guest available memory |
| Guest MemTotal / node capacity | 2823.27 | 2823.27 | 2891024 KiB; 248.73 below configured RAM |
| Node allocatable (`exact-nodes`) | 2211.27 | 2211.27 | 2264336 KiB; scheduling budget, not free memory |
| Talos MemFree | 252.07 | 241.49 | Already-unused pages only |
| Talos MemAvailable | 1370.60 | 1363.70 | Kernel estimate including potential reclaim |
| Kubelet node usage | 2336.21 | 2331.57 | Node memory charge/usage accounting |
| Kubelet node working set | 2162.34 | 2153.99 | Distinct from RSS and usage |
| Kubelet node RSS | 919.52 | 911.15 | Not the whole node footprint |
| Kubelet node available | 660.93 | 669.27 | Governing lower side of dual gate |
| Pods aggregate working set | 1546.11 | 1541.99 | Parent pods accounting, not extra memory to add |
| Pods aggregate available | 765.16 | 769.27 | Not node available or an admission substitute |
| Kubelet system working set | 106.95 | 107.08 | Included within node accounting |
| Misc system working set | 153.79 | 152.34 | Included within node accounting |

`exact-nodes.stdout` supplies the capacity/allocatable snapshot, not a second
independent measurement at both window endpoints. The physical-to-allocatable
difference is **612 MiB**. It is not spare capacity. The captures do not establish
the cause of the248.73 MiB configured-to-MemTotal gap or independently expose all
reservation settings, so neither gap is labeled reclaimable.

Observed accounting relationships (final values):

- Node workingSetBytes2258624512 + availableBytes701784064 =2960408576 bytes,
  exactly guest physical2823.265625 MiB. The initial pair has the same identity.
  Thus the final admission value is2823.265625 −2153.9921875 =669.2734375 MiB,
  **not** allocatable minus node working set (57.27 MiB).
- Node usage − working set =177.58 MiB (initial173.88). This is consistent with
  working-set accounting excluding inactive file pages; final meminfo Inactive(file)
  is177.58 MiB. It is not permission to subtract more cached memory from the gate.
- Pods aggregate working set1541.9921875 + available769.2734375 =2311.265625 MiB,
  512 below physical and100 above reported allocatable. This is an observed
  effective accounting basis, **not independently captured proof of `memory.max`**
  or of the exact reservation/eviction configuration. The summary does not expose
  the full cgroup hierarchy, memory.stat, memory.max/high or event counters.
- Node working set minus pods aggregate =612.00 MiB at the final point. Subtracting
  kubelet107.08 and misc152.34 leaves352.58 MiB unattributed by those summary
  categories. This is a numerical residual, not proof that a named Talos daemon,
  etcd, cache or kernel allocation owns it.

### Major Pod point working sets

The follow-up summary preserves an earlier component point sample; its values
must not be silently presented as the window-final sample. Both are shown to make
the provenance clear. Names are component roles rather than private Pod UIDs.

| Pod role | Earlier follow-up summary MiB | Window-final Pod MiB |
| --- | ---: | ---: |
| Cilium agent Pod | 481.72 | 481.55 |
| API server | 431.77 | 450.70 |
| Cilium operator | 155.77 | 156.06 |
| Controller manager | 131.05 | 130.63 |
| Cilium Envoy | 97.12 | 97.20 |
| Scheduler | 66.49 | 67.04 |
| Local-path provisioner | 60.81 | 60.90 |
| CoreDNS replica A | 50.65 | 50.72 |
| CoreDNS replica B | 47.01 | 47.05 |

Window-final Pod working sets sum to1541.86 MiB, versus the pods-parent1541.99.
Individual samples have different timestamps (final Pod readings span roughly
02:25:36–49Z). Pod parents include more than their displayed main containers:
for example final Cilium Pod481.55 versus agent container367.06 MiB. These are
nested, time-skewed cgroup/accounting scopes, not additive process RSS or an exact
host ledger. Do not add Pod values to the pods aggregate, node total or host QEMU
charge. Nor does a container's availableBytes mean spare physical node memory;
it can reflect its own limit/accounting boundary. Limits are ceilings, requests
are scheduling inputs, and neither is a measured steady-state working set or peak.

### Cache/slab attribution and uncertainty

Final meminfo: Cached1419.83 MiB, Buffers0.57, Shmem112.47, Slab71.76,
SReclaimable21.14 (also KReclaimable21.14), SUnreclaim50.62, AnonPages911.13,
KernelStack7.11 and PageTables9.14 MiB. These fields overlap or describe different
accounting dimensions: KReclaimable and SReclaimable are not two separate savings;
Cached includes memory that is not an immediately free application budget.
Talos MemAvailable already estimates reclaimability. Working set can retain
active file cache and is not a pure irreclaimable-memory measure, but **neither
cached nor slab may be subtracted again to manufacture admission**. Even the
entire observed21.14 MiB reclaimable slab would not numerically cover162.73 MiB;
this is not a proposal to reclaim it.

Across the window Talos available fell6.90 MiB while kubelet available rose8.34;
node working set and RSS fell8.34 and8.37 MiB respectively. These two endpoints
and the earlier point samples neither prove a leak nor rule out growth under
other loads or longer uptime. Attribution would require separately approved,
time-aligned cgroup/kernel detail and repeated controlled workload observations.
No fabricated historical baseline or causal before/after comparison is used.

## Admission and host accounting

The unchanged Nextcloud **diagnostic** budget is PG384 + Redis64 + one CLI192 +
reserve192 = **832 MiB**. Final min(Talos1363.703125, kubelet669.2734375)
=669.2734375, a **162.7265625 MiB (~163 MiB) shortfall**. Initial shortfall was
171.07 MiB. Talos alone exceeds832 by531.70 but cannot admit: the required test
is both metrics, equivalently their minimum, not their maximum, average or sum.
This is an observed point-in-time gate failure, **not proof of permanent3 GiB
impossibility, physical exhaustion or OOM**.

832 is not full Nextcloud capacity, a512 MiB PHP profile, Apache/frontend/Office,
Immich/ML or an all-heavy-apps budget. Replacing CLI192 by512 alone would make
384+64+512+192 =1152 MiB before any other work; that arithmetic is not a proposed
profile or authority. The36 source containers' approximately3.6 GiB idle footprint
is larger than the entire3 GiB VM and excludes this Talos platform baseline and
proof peaks. Source idle memory cannot establish a3 GiB full-stack capacity claim.

Host startup admission for3072 is3072+1536 margin+384 QEMU allowance =**4992 MiB**.
Captured prestart minimum6062 exceeded that by1070. During the300.01second
observation,31 host samples had minimum available2731 MiB; swap-used range0–0 KiB,
pswpin/out deltas0. The2731 minimum was1195 above the1536 guard floor, but is
**not** a new prestart admission value. Host available and guest available are
not interchangeable or additive; guest pages, host/QEMU overhead and other host
workload changes have different accounting.6062−2731 =3331 MiB is an observed
cross-window difference, not a measured QEMU overhead or causal allocation proof.

For narrow historical context, [operations notes](talos-proof-operations.md)
(lines130–153 at the analysis HEAD) record earlier Flux refusals at kubelet710/
642.2 MiB versus Talos1421 MiB, then later kubelet admission1394.6/1184.4 and final
cleanup1107.7 MiB after ordinary prior media-associated accounting variation.
That separate history used no cache dropping, pressure injection or host/VM tuning.
It illustrates accounting variability, not a controlled causal comparison with
this capture or proof that waiting/induced work would admit. No such experiment
or retry is proposed here.

This short clean window does not prove safe peaks, long soak or no recurrence.
The host kernel+`kho=off` mitigation changed two variables; exact historical swap
causation remains unproved. Do not infer that guest cache caused the old host
incident, or that this capture exonerates every other cause.

## Bounded capacity decision for parent review

**Recommend 3584 MiB (+512) for one separately approved platform-only experiment,
not 4096 MiB (+1024). Keep VM120 OFF pending approval.** Both larger profiles
remain **UNAPPROVED**. This is a bounded measurement proposal, not a claim that
3584 will pass832 or that3072 can never pass. No demonstrated structural change
recovers the observed162.7265625 MiB deficit plus variability headroom without
changing required platform semantics; no tuning/reclaim experiment is proposed.

| Fixed RAM MiB | Increase from current | Analogous startup floor (RAM+1536+384) | Historical6062 minus floor, illustration only |
| --- | ---: | ---: | ---: |
| 3072 (current approved profile) | 0 | 4992 | 1070 |
| 3584 (unapproved candidate) | 512 | 5504 | 558 |
| 4096 (unapproved alternative) | 1024 | 6016 | 46 |

3584 is the least-risk credible **measurement candidate** of these increases: it
commits512 MiB less shared-host RAM than4096, with a smaller analogous admission
floor, while testing additional capacity against a measured ~163 MiB deficit.
Neither the512 increment nor these historical margins predict guest availability.
4096 is not selected: no measurement demonstrates that its extra512 is needed,
and the stale46 MiB arithmetic margin is especially weak evidence for a shared-host
experiment. **None of1070/558/46 is fresh admission or a safety margin.** If fresh
host evidence cannot justify3584 without production reallocation, stop this proposal;
separate non-production capacity needs its own design/approval, not an automatic
4096 fallback. No linear extrapolation guarantees either candidate's guest budget.

### Source-tied change surface — review before implementation

Paths below were inspected at `0862d3b518f1279b76e02989d46dd42b0d1eafe1`.
This document does not extend any allowlist or authorize deployment/enrollment.

- `infrastructure/proxmox-proof/host_lifecycle.py`: `validate_config()` accepts
  only2560/3072 and rejects3584/4096. `parse_config()` overlays permitted pending
  memory/args, then validation still applies. `enroll()` validates the full effective
  configuration, saves its exact `config_sha256` in private `identity.json`, and
  retains the original `swap-baseline-kib` (**24 KiB**, never reset to current use).
  `approved_config()` revalidates and checks that digest on startup and guard entry;
  `start()` rechecks before resume. Merely setting VM RAM fails closed. A future
  reviewed extension should add only3584, leaving4096 and all unrelated settings
  rejected; re-enrollment is required after the authorized RAM-only change.
- The same file's `MARGIN_MIB=1536`, `OVERHEAD_MIB=384` and `start()` implement
  host admission; `ResourceCheck` retains the existing running thresholds. **384
  is a fixed additive QEMU overhead allowance**, not guest reserve, measured QEMU
  RSS/peak, or a proven upper bound. Review its adequacy for unchanged QEMU devices
  before approval;5504 is only the analogous floor with that allowance. If review
  requires a different allowance, return for a revised plan/approval, not an ad-hoc
  threshold edit. Record actual QEMU/cgroup usage/peak during the experiment.
- `infrastructure/proxmox-proof/create.sh` independently rejects RAM outside
  2560/3072 and applies RAM+1536+384. Keep that policy aligned in any approved
  profile patch; **do not run create.sh** for existing VM120 (it requires no config).
  `infrastructure/proxmox-proof/validate.sh` validates generated Talos machine
  configuration, not Proxmox RAM enrollment; it is not a larger-profile approval.
- `tests/talos-proof-host_test.py`: `ConfigTests.test_approved_profiles_and_dynamic_ports`,
  `test_unsafe_fields` (explicit3584/4096 rejections),
  `test_approved_pending_overlay_validated`, and
  `ResourceTests.test_fresh_admission_profiles` need reviewed candidate coverage:
  approved3584/pending3584, continued4096 rejection, digest drift rejection and
  exact5504 admission versus5503 refusal. Existing baseline/PSI/swap/identity/
  startup-cleanup tests must remain unchanged in strength.
- `infrastructure/proxmox-proof/install-supervisor.sh` installs `host_lifecycle.py`,
  `resource-guard.py`, `isolation.sh`, `start.sh` and the two proof-only systemd
  units, refusing active units. Scripts go to
  `/root/.local/state/home-infra/talos-proof/`; units go to `/etc/systemd/system/`.
  `talos-proof-start.service` and `talos-proof-guard.service` execute that private
  state copy, **not this checkout**. Review exact deployed/source hashes and unit
  contents before enrollment/start; no unit/wrapper/isolation behavior change is
  proposed. Use the approved install path only while stopped, never a live guard
  replacement. `start.sh` must remain the sole supervised start entry point.
- Parent-owned `docs/talos-proof-host-lifecycle.md` must describe the newly approved
  profile/admission/enrollment contract if approved; parent also owns delivery/root
  docs and gate scheduling. This capacity document is the only change now. No
  profile/guard implementation or private artifact change precedes human approval.

### Minimum new human approval and bounded execution contract

Offline analysis and the saved-evidence Flux classifier were already approved;
**RAM/profile extension, deployment, enrollment and a new start were not**. Parent
must first review this proposal. The next human request must explicitly authorize
only the following scope (with named executor/reviewer and an absolute expiry):

> Existing proof VM120, UUID `555e8603-58e6-4fb6-a190-378a3f11c257`:
> increase fixed RAM only3072→3584 while OFF; implement/review the3584-only profile
> extension and tests/docs; deploy only reviewed matching lifecycle files through
> the proof-only install procedure and enroll the exact new configuration digest,
> preserving disks, devices, isolation, all guard thresholds and original24 KiB
> swap baseline. Permit **one** existing supervised guarded start, conditional on
> fresh passing gates and parent release of the reviewed patch/deployment plan.
> Permit owned management access for read-only node/platform, complete kind-specific
> Flux, storage/mount/binding and production continuity checks, plus one bounded
> passive observation. End OFF, close owned access, and verify production health.
> Authorize proof-only RAM/configuration-enrollment rollback to the captured3072
> baseline **while OFF** if desired; otherwise leave3584 OFF for parent disposition.
> No second start is included, including after rollback.

The approval must include a bounded lease: proposed maximum30 minutes for stopped
preflight/configuration/deployment, then maximum20 minutes from wrapper invocation
to OFF, with one fixed300-second passive platform window after identity/barrier
checks. These are proposed operational timeboxes, not measured capacity thresholds.
If review/implementation cannot fit, finish it offline and obtain a fresh scheduled
execution lease; do not extend runtime or renew authority implicitly.

1. **Review gate, still OFF:** after the human grant, prepare the minimal profile
   patch/tests and parent-owned contract updates. Parent schedules the full offline
   gate and reviews exact source/deployment hashes, rollback config/receipt capture,
   owner/lease and recovery access before any host change. No unrelated profile,
   device, host tuning, reboot or production allocation change. Preserve original
   evidence and baseline privately; public docs expose no full config/credentials.
2. **Fresh prestart gate:** verify kernel/`kho=off`, boot identity, production
   health/storage/VM and36-container continuity against an owned fresh baseline;
   exact VM120 OFF identity/config/disks, VM111 OFF, no competing proof lease or
   effective pending application operation, and recovery access. Verify the reviewed
   canonical Nextcloud111-file manifest unchanged. Recheck VM120 backup exclusion,
   backup-job configuration and active/scheduled backup or migration conflicts;
   no backup trigger, exclusion expansion or schedule change is authorized.
   Observe host memory, swap/page-I/O, PSI and competing load for120seconds;
   require the observed minimum and immediate wrapper sample to meet at least5504,
   plus parent justification of variability/overhead adequacy without inventing a
   new numeric safety threshold here. Keep the original24 KiB baseline. Historical
   6062 and one near-floor sample cannot clear this gate. Recheck after resize/
   install/enrollment; drift or insufficient headroom means no start.
3. **One platform-only start:** use reviewed deployed matching lifecycle files and
   the existing wrapper. Verify guard READY/isolation and exact incarnation before
   proceeding. Preserve available1536 floor, swap growth65536 KiB, sustained swap
   I/O and PSI/deadline criteria from the lifecycle contract. No automatic retry or
   direct `qm start`/resume bypass. A failure or unknown timeout consumes this attempt
   pending parent review, not permission to invoke it again.
4. **Read-only verification and one300s passive window:** check sole node identity,
   exact platform Pod/controller ownership, zero native app controllers, suspended
   native CronJobs, no app/helper Pods (including terminal, terminating and
   unlabelled objects), mounts and retained storage bindings.
   Collect complete authorized Flux inventory; use resource-specific saved-evidence
   classification and explicit controller identity/ownership review. Current
   Kustomization remains **unobserved until collected**: historic cleanup is not
   evidence. GitRepository absent `spec.suspend` with controllers absent is **not
   a stop trigger**. Do not reconcile controllers to inspect them. Repeat timestamped
   paired Talos/node available, capacity/allocatable, working set/RSS/component
   readings at window endpoints alongside host/QEMU observations and production
   continuity checks. No apps, helpers, pressure/reclaim/tuning or PVC repair.
5. **Failure, endpoint and rollback:** host guard breach, new OOM or unexpected
   restart, unexpected workload/controller, failed identity/storage/native or
   approved kind-specific policy gate, incomplete mandatory evidence, lost access,
   or lease expiry ends the experiment. Evidence gaps are incomplete, not invented
   violations. Distinguish authorized boot recreation and retained historical
   counters from new failures; no blanket lifetime-zero restart counter. Use the
   existing exact-incarnation proof stop; verify OFF/cleanup and production health,
   close only owned access, preserve successful/failed evidence. End OFF even on
   success. Only if explicitly authorized, restore captured proof-only3072 RAM and
   matching enrollment while stopped, verify digest/OFF, with no start or data
   rollback. If safe restoration cannot be verified, remain OFF and escalate.
6. **Parent review, not activation:** compare observed candidate results to this
   historical3072 baseline with accounting/time-skew caveats; report every failed
   or missing gate. A passing platform window establishes neither long soak nor
   application capacity. Only a separately scoped/approved future diagnostic could
   use fresh independent dual832 admission (kubelet at most30seconds old), rechecked
   immediately before each authorized create. Passing could enable PG384+Redis64+
   one serial CLI192+reserve192 diagnostic work—not full Nextcloud, PHP512/frontend/
   Office, Immich/ML or all36 source containers. No application grant follows from
   this experiment; parent retains receipts, delivery and acceptance ownership.

No host tuning/reboot, production mutation, cache pressure/reclaim, controller
reconciliation, app/helper activation, PVC repair or automatic retry is included.
The genuine next escalation is this exact new human approval after parent review;
no runtime action is authorized by the already-approved offline preparation.

## Evidence references (SHA-256)

These hashes bind this analysis to named existing captures; they do not publish
raw evidence or confer acceptance. No original capture/history was modified.

| Artifact | SHA-256 |
| --- | --- |
| `window300-final-memory-pair.json` | `e0108fc7318f05a954358f796fc947ebead890488b96458104b94fb7833d44cf` |
| `window300-final-talos-meminfo.stdout` | `34696b9c34eb37e0c140e323110c193602fc0926884245c27d59f17adf16aebb` |
| `window300-final-kubelet-summary.stdout` | `f5b6729ffd78503ab44608e25b68945ef5c7deaa4148fe5eba4a16edb650c40b` |
| `window300-result.json` | `42fdcf42dd383dc5fda830c71f25918dd4dae6af19327461b494e65291c485fb` |
| `exact-nodes.stdout` | `e9287e083b8805a49be296a213ace0ea486fc2bf092549528c4e77ad2e947a8d` |
| `followup-final-summary.json` | `e34fe6c85ee93c924c6fc58cdbca38f7dc962c0526457d0f586d93f39e823294` |
| `window300-initial-memory-pair.json` | `3a4907034436286431dd152227031827cef1c8d68c89a74d02b63e95bbb91591` |
| `window300-initial-talos-meminfo.stdout` | `b323defd22ca5f9d7ea67a7ff0d122f516c5317d4124c576d722ef5fa207a65a` |
| `window300-initial-kubelet-summary.stdout` | `0ce99a8629bd47bdc83d28cd30059778effa10ce7af2902dac90c2ed5bb5e64f` |
| `fresh-prestart-gates.json` | `c0a82910051bfe7b0e1d659424312bbe1ad73db116698013c51039b9131d23a1` |
| `correction-summary.json` (same private capture) | `0df3396bbcbe2c8a3fc3351405785aa7a821bbb7ec6d6d8508dd004ce104051f` |
| `docs/evidence/talos-acceptance/guarded-platform-parent-review-8954422ca5934f0d9fda169a62f7a71d.json` (public) | `528045e89cad2d559ab6bf5f461094459c6ccba230a368c7bcd54f6e08d369d1` |

Related contracts: [host lifecycle](talos-proof-host-lifecycle.md),
[host mitigation and causal limits](talos-proof-host-memory-remediation.md),
[Nextcloud diagnostic plan](talos-proof-nextcloud-preflight-plan.md).
