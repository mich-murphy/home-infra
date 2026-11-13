# Single authorized initialization — BLOCKED / PENDING before binding

Run UUID: `34a6bc9c-7a6a-46b3-ac59-528c84233bca`. Starting HEAD:
`c1e2ec6365691fc0c454ff41ec04c459973d7cf9`. Exactly **one** scoped
initializer `initialize` invocation ran on 2026-11-12, 02:27:23–02:28:26 UTC,
returning exit1. No retry, code repair, existing-object replacement, PVC reset,
legacy data CLI, credential generation/copy or native execution occurred.

## Authorized boundary and observed result

The new private parent receipt authorized only eleven hash-bound create-only
stopped declarations and one read-only binding Job. Before launch, all eleven
canonical document hashes matched; the canonical shared0700 journal root was
empty. Explicit KUBECONFIG/current context `admin@talos-proof`, TLS endpoint
`https://127.0.0.1:64120` and sole exact Ready Node UID were verified.
The supervisor sets the lifecycle group/stage/state globals; its memory reader
uses the explicit private Talos binary/config and endpoint/node specified by the
parent. No legacy prepare/credentials entry point was invoked.

All eleven authorized objects were created and their returned UIDs journaled.
Twelve fresh independent dual memory admissions were recorded; observed minima
were kubelet **1146.83MiB**, Talos **1136.27MiB**, above the unchanged **832MiB**
gate. The intended binding envelope remains64 + 3×32 +192 =352MiB; no gate or
resource limit was reduced.

The runner then failed during post-create validation, **before any binding
intent or binding-create journal event**. The journal contains pending1,
initialization-create-intent11, initialization-created11, memory12 and
initialization-blocked-pending1; no clean event. No binding Job was created,
no PVC was mounted and no emptiness/device/path acceptance was earned.

## Concrete validator blockers (read-only forensic replay)

Pure `validate_present()` replay against privately captured actual post-failure
API objects found:

| Object | Field | Actual API | Approved declaration |
| --- | --- | --- | --- |
| deployment/redis | `/containers/0/env` within PodSpec | absent | `[]` |
| cronjob/nextcloud-cron | `/jobTemplate/metadata` within CronJobSpec | `{}` | absent |

The CLI exports only exception type (`RuntimeError`), not its exact message or
traceback. Its stdout/stderr were captured privately O_EXCL0600; stderr was
empty. The **first runtime blocker is inferred** to be Redis from the unchanged
verification order; both concrete mismatches were independently reproduced by
the actual pure validators against retained snapshots. This is not a claim that
a full original exception trace was captured. No validator was changed and no
repair/reinitialization was attempted while this grant was active.

## Fresh post-failure state

Read-only API capture confirmed:

- Zero proof Pods, Jobs and DaemonSets, including terminal/helper objects.
- All proof application Deployments replicas0; new Nextcloud CronJob suspended.
- All three new Nextcloud PVCs Pending, with no `volumeName`; zero PV claimRefs
  for namespace `proof-nextcloud`. All eleven created objects are retained.
- Only the existing reviewed local-path provisioner controller Pod in
  `local-path-storage`; no automatic storage helper observed.
- Namespace and existing Secret UIDs rechecked unchanged, with Secret UID-only
  projection (no values emitted). Sole Ready Node identity matched before launch
  and remains present in the private post-failure snapshot.

No owned binding UID exists, so no `stop` invocation or deletion was needed or
performed. No provisioner-forensics phase was reached. There is **no complete
provisioner lifetime log/cgroup coverage claim**. No helper log/cgroup evidence,
Bound PVC/PV identities, read-only mount emptiness, device-ID or exact backing
path runtime acceptance exists. No Nextcloud functional PASS follows.

## Private evidence and authority retirement

Private base: `$HOME/.local/state/home-infra/talos-proof/diagnostics/`.
All new files were O_EXCL0600; canonical UUID journals remain in
`$HOME/.local/state/talos-data-proof/`0700. Historical files, issued receipt copy,
credentials, old `STATE/data`, retained Pinchflat STOP and WOPI failures were not
changed.

- `nextcloud-initialize-invocation-34a6bc9c-7a6a-46b3-ac59-528c84233bca.json`
  indexes exact private stdout/stderr paths, timestamps, return code and unchanged
  receipt hash.
- `initialization-failure-snapshot-b30cf1c5-30b0-4d22-b215-471e010b68a2.json`
  preserves post-failure objects, all Pods/controllers, PVs and Node observations.
- `initialization-pure-blockers-28d19c93-fd82-4ca3-8e10-fd2007e9e433.json`
  preserves independently reproduced validator exceptions.
- `nextcloud-initialize-failure-handoff-34a6bc9c-7a6a-46b3-ac59-528c84233bca.json`
  contains all eleven created UIDs, namespace/Secret/Node identities, journal
  path/hash/event index and explicit forensic gaps.
- `nextcloud-initialize-final-receipt-34a6bc9c-7a6a-46b3-ac59-528c84233bca.json`
  is the fsynced final immutable-byte receipt archive. SHA256:
  `1c24079e526107787aa8db686abcce70653fdc54166cb2021dd8f5637db559b7`.
  Only after verifying this archive against the original active bytes was the
  active lease path removed; issued history was not edited or refreshed.

**PENDING remains**, deliberately blocking ordinary activation and a fresh
initializer from adopting this partial state. Parent must separately review
these concrete serialization blockers and any narrowly scoped future recovery.
This failed run is **not eligible for a post-binding native grant**: PVC/PV
binding identities and empty read-only observations do not exist. No grant was
issued here. PG/Redis/web/CODE/native install/cron remain unrun. No host changes,
VM start, production calls or media changes were made. Parent-owned root docs,
platform/gates and dirty `docs/talos-proof-delivery.md` are excluded from this
bounded evidence-only commit.
