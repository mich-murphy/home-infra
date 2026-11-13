# Initialization read-only preflight — BLOCKED, no grant

Source: clean starting HEAD `11bda18dd3d14fbdcea76ae81415016a70bb60c6`, including
initializer repair `0420ea1b` and legacy CLI closure `11bda18d`. Reviewed initializer,
supervisor, data lifecycle/journal helpers, cron compiler, storage declarations,
cron plan and initialization review `32ea0653d7cf496695548ac8e6f2641d`.
Observations: **2026-11-12 02:01:54–02:04:20 UTC**. Parent owns acceptance,
canonical-state disposition, alias choice and any future grants.

## Actionable blocker: actual API-default mismatch

`Initializer.storage()` rejects the **actual** `local-path-storage/Deployment/
local-path-provisioner` PodTemplate through the current pure envelope validator:

| Field | Expected by current normalized declaration | Actual normalized API object |
| --- | --- | --- |
| `/spec/template/spec/serviceAccount` | absent | `local-path-provisioner-service-account` |

`serviceAccountName` is already the same explicit service account on both sides.
This is the sole normalized Deployment difference, not a mock-only failure.
The normalizer removes `serviceAccount: default`, but not this explicit-account
legacy API alias. The actual provisioner **Pod passes** `provisioner_pod()`:
its existing narrow alias handling, SA projection and ReplicaSet→Deployment UID
chain pass against cached real API snapshots. No constructor, authorize method,
initializer/supervisor entry point or mutating operation was invoked.

**Next scoped code step:** transfer repair ownership to normalize only a proven
matching explicit `serviceAccount`/`serviceAccountName` alias (reject conflicts
and unknown drift), add a regression for this real API shape, then independently
repeat the read-only storage envelope check. No existing file was repaired here.
Stopped further compatibility work on this concrete finding; the subsequent PV
metadata query was the explicitly requested read-only reconciliation.

## Verified target and quiescence

Before other API queries: explicit `KUBECONFIG=$HOME/.local/state/home-infra/
talos-proof/config/kubeconfig`, current and explicitly selected context
`admin@talos-proof`, TLS-verified endpoint `https://127.0.0.1:64120`, sole Node
`talos-proof`, hostname label `talos-proof`, UID
`4845bfd5-3bdb-453d-8503-83b43edb7a1e` all matched.

- Namespace `proof-nextcloud` UID: `52497afe-f428-4b0e-aa52-cc92e9f2bf6a`.
- All **23 proof Deployments** have replicas0. No proof StatefulSets, DaemonSets,
  CronJobs or Jobs exist; consequently no unsuspended schedule or terminal Job
  resource blocks the initializer barrier at this observation.
- Zero proof Pods (including validation/gateway/terminal Job Pods). Only the
  reviewed local-path provisioner Pod exists in `local-path-storage`; no storage
  helper Pod exists.
- No app/backend starts, initialization, bindings, content inspection, native
  cron execution or functional acceptance occurred.

## Missing objects, alias and retained-storage reconciliation

All eleven intended Nextcloud declarations are absent:

- `configmap/nextcloud-apache-proof`
- `cronjob/nextcloud-cron`
- `deployment/nextcloud`
- `deployment/postgres`
- `deployment/redis`
- `pvc/nextcloud-data`
- `pvc/postgres-data`
- `pvc/redis-data`
- `service/nextcloud`
- `service/postgres`
- `service/redis`

Here `pvc/nextcloud-data` is the **desired-manifest name only**, not a discovered
or selected alias. There is no live web Deployment or CronJob HTML mapping to
review. **No `declarations(alias)` call or intended-document hashes were built.**
Parent may explicitly choose canonical desired name `nextcloud-data` for fresh
creation after the code/state blockers are resolved; that choice is not made by
this evidence.

Fresh API inventory: **zero proof-nextcloud PVCs** (39 PVCs cluster-wide).
PV follow-up: **zero PV claimRefs for proof-nextcloud**, including retained or
Released PVs (39 PVs cluster-wide). Thus there is no matching backing-path,
claimRef UID or released-volume identity to report/adopt. This is resource
metadata absence, **not proof of physical disk emptiness** or absence of orphaned
native data. No volume contents or backing directories were read or mounted.
Existing collabora/WOPI objects remain untouched and are outside the initializer
allowlist.

Only existing allowlisted identity is `secret/proof-credentials`, UID
`81144bf1-7ec2-42e3-90ba-564d787eed4f`, type `Opaque`. Projected key **names only**:
`NEXTCLOUD_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `REDIS_HOST_PASSWORD`; all required
names exist. No values, nonempty-value assertion, credentials, application data
or native payloads were inspected. Key presence is not runtime credential proof.

## Canonical journal state

Code requires `$HOME/.local/state/talos-data-proof`; that directory is **absent**.
Old brief path `$HOME/.local/state/home-infra/talos-proof/data` exists, mode0700,
with **zero canonical UUID.json files**. Only UUID journal event/run_id metadata
would have been selected; no credential or native payload file was opened.
No canonical pending/clean history can be validated from a nonexistent directory;
old-path absence of journals is not canonical-state acceptance. No directory
creation, migration, symlink, state adoption or historical-clean assertion was
performed. Parent must reconcile the canonical-state prerequisite explicitly;
a future worker must not silently use/create an alternate state to hide history.

## Storage and memory context — not admission

- Live `proof-local`: `rancher.io/local-path`, `Retain`,
  `WaitForFirstConsumer`, matching required fields.
- Live local-path config data exactly matches reviewed storage configuration;
  helper memory ceiling remains **32MiB**.
- Explicit proof Talos binary/config under `STATE/bin/talosctl` and
  `STATE/config/talosconfig`, endpoint `127.0.0.1:50120`, node `172.31.250.10`.
  Read-only `/proc/1/mountinfo` measured mount root `/`, target `/var/mnt/proof`,
  filesystem **XFS**, source **`/dev/sdb1`**, actual major:minor **`8:17`**.
  Device ID was measured, not inferred. No host/storage/network changes.
- Kubelet sample `2026-11-12T02:02:45Z`: availableBytes **1254494208**
  (1196.38MiB). Talos MemAvailable **1180340KiB** (1152.68MiB), captured with
  kubelet observation by `02:02:53.710426Z`; minimum **1152.68MiB**. Fresh at
  collection, historical context only now—not an admission check or grant.
- Actual binding envelope remains **64 + 3×32 + 192 = 352MiB**. Conservative
  independent dual-minimum gate remains **832MiB**, without decreases. Parent
  must independently refresh both measurements before any grant.

## Private evidence / handoff

Private snapshots outside Git: `/Users/mm/.local/state/initialization-preflight-21151f67-d150-4bc4-b78d-14a6f8b210b3` (0700). Each file is UUID-suffixed,
O_EXCL-created0600. Complete identity observations and blocker summary:
`/Users/mm/.local/state/initialization-preflight-21151f67-d150-4bc4-b78d-14a6f8b210b3/blocked-identity-summary-36b626fe-aad4-4b64-ae51-718c3d0972ce.json`.
Snapshot index with file hashes: `/Users/mm/.local/state/initialization-preflight-21151f67-d150-4bc4-b78d-14a6f8b210b3/snapshot-index-c1d67f3b-ee6b-4308-b4df-49f53bc1306f.json`.
These are **blocked read-only discovery artifacts**, not a complete candidate
initialization document/hash plan, receipt or grant. Complete plan remains
blocked by actual API envelope mismatch, canonical-state reconciliation and
explicit parent alias choice. After those narrow steps, generate reviewed
`document_hashes(declarations(chosen_alias))` without initialization authority.

Read-only Kubernetes operations were local config inspection and `get` queries;
Talos operations were only reads of mountinfo and meminfo. Secret retrieval used
output projection of UID/type/key names, never value output. Initial secret
projection failed due to template newline quoting; corrected projection succeeded,
with no values emitted. Object inventory captured other namespace ConfigMap
source/config fields privately alongside metadata; none was executed or adopted.
No production calls, VM start, create/apply/patch/scale/delete/exec, helper/app
starts, receipt creation or existing-file edits were performed. Parent-owned
`docs/talos-proof-delivery.md` became modified concurrently and is excluded from
this evidence-only commit.
