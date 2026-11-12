# Binding-only observation — stopped, Bound, empty read-only

**No Nextcloud functional PASS, native installation or cron execution.**

Original transaction: `34a6bc9c-7a6a-46b3-ac59-528c84233bca`.
New binding-only authorization: `b808f115-af83-421b-9091-01bc2e56a9a9`.
Starting HEAD: `db029fdb3c22a7d5986552cd7ff06c9591b54309`, with reviewed
initializer implementation `b4c99169`. Exactly **one** `bind-created` invocation
ran **2026-11-12 03:05:35–03:06:18 UTC**, returning exit0. No retry, active-scope
code change, declaration create/replacement/deletion, Secret write, credential
operation, backend/web/CODE start, VM start, host change or media operation
occurred. Parent-owned root docs/platform/gates remain outside this evidence.

## Authority and fresh runtime admission

Before launch, exact new receipt/private0600 mode, initializer/supervisor source
hashes, original issued-receipt hash and all36 original journal hashes matched.
Explicit `KUBECONFIG=$HOME/.local/state/home-infra/talos-proof/config/kubeconfig`
selected `admin@talos-proof`, TLS-verified `https://127.0.0.1:64120`, and the sole
Ready Node UID `4845bfd5-3bdb-453d-8503-83b43edb7a1e`.
Namespace UID `52497afe-f428-4b0e-aa52-cc92e9f2bf6a` and Secret UID
`81144bf1-7ec2-42e3-90ba-564d787eed4f` were rechecked after binding. Independent
postbinding Secret inspection projected **UID only**, never values.

The runner consumed one new authorization event before API admission, without
adding another pending event. Fresh independent runtime memory admission:

| Observation | Available MiB |
| --- | ---: |
| Kubelet | 1175.7578125 |
| Explicit-endpoint Talos MemAvailable | 1169.328125 |

Both exceed the unchanged **832MiB** gate. Actual bounded binding envelope
remains64 + at most3×32 + reserve192 = **352MiB**, without gate/limit reduction.
Target, storage/provisioner, stopped identities, Pending/unassigned PVCs and
PV-claimRef absence were checked by the receipt-bound runner before its helper.

## One helper and native read-only evidence

Job: `proof-nextcloud/nc-binding-34a6bc9c-7a6a-46b3-ac59-528c84233bca`.
Observed create UID: `33ea3216-82c4-4ec6-b40d-ed141c124df5`.

The exact pre-exported generated Job and actual Pod envelope were independently
revalidated from retained journal evidence. It used only the reviewed pinned
BusyBox image,64MiB ceiling, no token/init/sidecar/fsGroup and three read-only
PVC volumes/mounts. Its native command checked, for **each** of the three mounts:

- mountinfo device ID **8:17**, XFS source **`/dev/sdb1`**, exact deterministic
  root `/pvc-<original-PVC-UID>_proof-nextcloud_<claim>` and read-only options;
- an actual nonsymlink directory and emptiness including hidden entries.

Native current logs contain `PROOF_BINDING_EMPTY_READONLY`; the single container
terminated exit0, restartCount0. This is evidence of successful command
assertions, **not a separate raw per-mount mountinfo dump**. The pre-exported
command, actual Pod specification, raw state and raw logs are retained privately.
Native cgroup measurements:

| Field | Observed bytes / count |
| --- | ---: |
| memory.current | 1900544 |
| memory.peak | 3973120 (about3.79MiB) |
| memory.events oom | 0 |
| memory.events oom_kill | 0 |

`memory.stat` and remaining `memory.events` fields were captured too. Applicable
previous logs were not needed because the container had no restart. Raw Pod
state/current logs were journaled **before** exact Job-UID-precondition deletion.
The runner confirmed both Job and Pod absence; independent final all-namespace
reads confirmed absence again. No `stop` invocation was necessary.

## Bound storage and final stopped state

All original eleven declaration UIDs are unchanged. All three PVCs are Bound to
`proof-local`; independent postbinding replay verified exact claimRef namespace,
name and original PVC UID, PV UID, Retain, RWO, requested capacity and exact
`talos-proof` node affinity.

| Claim | Original PVC UID | Observed PV UID |
| --- | --- | --- |
| nextcloud-data | a8243a0f-baab-4fb3-a1d4-441274a27efc | a763daa6-9882-4664-897a-3cbdb32fcba2 |
| postgres-data | f8d5b400-5256-4565-942e-633c7dd4546e | d80233d3-2793-4ba1-aa90-867636231807 |
| redis-data | 169af8e3-4a76-4821-83b6-e6f19815f48f | 4a2d31be-8af9-4a08-b27d-d7d489b312ad |

Each PV name is `pvc-<PVC-UID>`, with exact backing path
`/var/mnt/proof/pvc-<PVC-UID>_proof-nextcloud_<claim>`. Both live web and suspended
CronJob HTML mappings remain explicitly `nextcloud-data`. The private handoff
contains complete PVC/PV names, UIDs, paths, claimRefs, capacities, all declaration
and Secret identities, backend images and source hashes.

Fresh independent final API capture confirmed **zero proof Pods, Jobs and
DaemonSets**, including terminal helpers; all proof application controllers are
replicas0 and all proof schedules suspended. Only the reviewed local-path
provisioner controller Pod remains in `local-path-storage`, validated through its
ReplicaSet/Deployment UID chain and full approved envelope. No automatic storage
helper remains. All PVCs/PVs and eleven declarations are retained.

## Explicit provisioner forensic limitation and journal outcome

The capture phase saw only the surviving provisioner controller Pod. Automatic
helper deletion can precede observation: **complete automatic-provisioner
lifetime logs and cgroup measurements were not captured and are not claimed**.
The runner explicitly records this gap and
`provisioner_forensics_complete: false`; binding-helper state/log/cgroup coverage
is distinct and was present. No acceptance relies on hiding this limitation.

All36 original journal files are byte-for-byte unchanged, including the original
failed-initialization event. New append-only events include one continuation,
one helper intent/create, three Bound observations and **one clean event** for
the original transaction. There are51 journal files total, and no unresolved
pending transaction after the successful final stopped/absence checks. Original
failed history was neither rewritten nor deleted.

## Private handoff and authority retirement

Private base: `$HOME/.local/state/home-infra/talos-proof/diagnostics/`.
All new capture/finalization files are O_EXCL-created0600; shared journal root
remains0700 with append-only UUID0600 files.

- `bind-created-invocation-b808f115-af83-421b-9091-01bc2e56a9a9.json` indexes
  private stdout/stderr, timestamps, exit0 and unchanged receipt bytes.
  Stdout110bytes; stderr0bytes. No raw account data or environment dump was emitted.
- `bind-created-postbinding-snapshot-84d38f46-9308-48e9-93be-37912dde631d.json`
  preserves independent final objects, Node/namespace identities, Secret UID,
  all proof controller/Pod state, PVs and reviewed storage/provisioner chain.
- `bind-created-postbinding-handoff-5cbf1139-4c60-4a6c-a011-b12a62523051.json`
  contains postbinding identities, backend images, intended-document/source
  hashes, exact journal path/hash/event index and explicit forensic gaps.
  SHA256: `d5ba56ae014d28831b03cff7dc91e719c40c3da9e13cb5074fe1865505372b23`.
- `bind-created-final-receipt-b808f115-af83-421b-9091-01bc2e56a9a9.json` preserves
  exact final receipt bytes, fsynced0600/O_EXCL before active-path removal.
  Receipt SHA256:
  `1884f19ebe005980361d17bb8c7bf68903608452eb820d46e7f34f7543e7a4be`.
- `bind-created-finalization-b808f115-af83-421b-9091-01bc2e56a9a9.json` records
  archive/removal, evidence links/hashes and unchanged original history.

The active binding receipt was removed only after archive-byte verification and
fsync. Both original and new immutable issued copies remain untouched. No expiry
was refreshed, receipt edited, credential copied or new native authority issued.

**Next action belongs to the parent:** independently review this stopped Bound
handoff, the explicit automatic-provisioner forensic gap and fresh runtime
conditions before issuing any **separate NEW native authority**. This result is
limited to stopped storage binding and empty read-only observations, not
Nextcloud installation, backend credential validity, cron execution, HTTP,
WebDAV, WOPI, functional readiness, capacity or durability.
