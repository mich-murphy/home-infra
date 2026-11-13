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

## Bounded choices for parent review

| Choice | Evidence and bound | Decision implication |
| --- | --- | --- |
| Preserve3 GiB, no change | Known final dual minimum669.27 <832 | Least operational risk now: leave OFF and diagnostic blocked. No retry justified by this analysis. |
| Reviewed structural capacity/profile work | Cilium+API server dominate the Pod point samples; RSS/working-set differences justify investigation, not savings promises | Only a separately reviewed design preserving required networking, isolation, DNS, storage and control-plane semantics is credible. No demonstrated change here recovers163 MiB plus variability headroom. Do not pad receipts, drop caches, kill essential components, reduce replica/limit/reserve contracts or reinterpret accounting to fit. |
| Larger proof VM or separate capacity | More physical capacity could address the constraint, but no larger profile was measured or approved | Requires a new capacity/host admission design, explicit profile enrollment and new human approval/start authority. Prefer separately provisioned non-production capacity if shared-host headroom cannot be established without taking production memory. |

A4 GiB candidate's analogous startup floor is4096+1536+384 =**6016 MiB**.
The stale6062 prestart observation is only46 MiB above that arithmetic floor:
**it cannot establish4 GiB safety or current admission**. The384 allowance must be
reviewed for the actual QEMU configuration and observed overhead; it is not an
independently proven upper bound. Genuine fresh host headroom, competing workload
variation, startup/transient peaks and rollback capability matter in addition to
meeting a minimum. No linear extrapolation of final guest available guarantees a
larger VM's budget. A4 GiB candidate is not established capacity for full Nextcloud,
ML/heavy applications or all36 source containers. No production ARC, zram,
swappiness, workload allocation or
service configuration change is proposed.

## Recommended next decision and future gates

**Accept the blocked3 GiB result; keep VM120 OFF.** Ask the parent to review this
analysis and select whether to fund a separately approved larger/disposable proof
capacity assessment (prefer separate capacity if the shared host lacks genuine
margin), or stop this proof scope. There is no evidence-backed low-risk tuning
change to recommend now. Parent review precedes any human request. This plan is
not an approval and must not be used as a startup receipt.

If the parent later elects a capacity experiment, its separate reviewed plan must:

1. Specify exact capacity/location, changed configuration digest, permitted
   actions, timebox, owner and **new** human resize/start approval. Existing
   2560/3072 enrollment and the consumed start do not cover larger RAM. Any guard
   implementation/enrollment extension requires its own reviewed change; none is
   performed or authorized here.
2. Before any start, freshly verify host kernel/`kho=off`, boot identity, production
   health/storage and memory configuration; exact VM OFF identity/config/disks and
   rollback baseline; no competing proof/lease; and usable recovery access. Measure
   MemAvailable minimum, swap usage/baseline and pswpin/out deltas, PSI and competing
   load over the reviewed prestart observation. Apply at least candidate RAM+1536+
   reviewed QEMU overhead and separately justify extra variability/headroom. Stale
   6062 or a single near-threshold value cannot substitute.
3. Use only the newly reviewed guarded lifecycle, preserving fail-closed host
   thresholds (available1536, swap growth65536 KiB, sustained swap I/O and PSI
   criteria per the existing host lifecycle contract). Record QEMU/cgroup actual
   usage/peak and overhead alongside host samples. Stop/contain on gate failure;
   no automatic retry, guard bypass or memory borrowing from production.
4. Start **platform-only**, no apps/helpers or Flux reconciliation. Verify exact
   required Pod/controller ownership and inventory, native application controllers
   at zero and native CronJobs suspended, node identity, mounts and storage
   bindings. Inspect retained Flux resources kind-specifically: report GitRepository
   fetch intent and controller absence without requiring source suspension; inspect
   Kustomization against the reviewed apply/suspension policy and report later Flux
   resource state/gaps. Do not generalize a kind's policy to every CRD, infer
   uncollected state or reconcile to inspect it. Preserve failures instead of
   editing historical evidence.
   Repeat paired Talos MemAvailable and kubelet node available with raw timestamps,
   capacity/allocatable, working set/RSS and per-component data. Require a new
   reviewed observation window at least matching300seconds; it still would not
   establish application peaks or long-term capacity.
5. Keep application authority absent even if platform-only memory improves.
   Before any separately approved diagnostic phase, obtain new parent-owned
   receipts and independent dual832 checks under that phase's freshness rule
   (kubelet at most30seconds old, not merely this capture's120second pairing).
   Recheck immediately before each authorized create. No512 PHP/full-app or native
   acceptance can be inferred from a passing diagnostic gate.
6. Predetermine stop/rollback triggers: host guard breach, OOM/restart, unexpected
   controller/app, failed approved kind-specific apply/scheduling, storage or
   identity gate, or expired authority. An absent GitRepository suspension field
   alone is not a stop trigger.
   Contain the exact proof VM, close owned access, verify OFF and production health,
   preserve evidence, and restore only explicitly authorized proof configuration
   to its captured baseline while OFF. No production reallocation, data rollback,
   destructive guest recovery or further start is implicit. End OFF with no leases
   or application activation grant unless separately and explicitly approved.

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
