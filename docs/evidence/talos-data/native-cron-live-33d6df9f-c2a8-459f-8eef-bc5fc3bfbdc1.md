# Single native sequence — preflight BLOCKED, stopped / PENDING

**No Nextcloud native install, fixture, cron or functional PASS.**

Run: `33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1`.
Starting HEAD: `6b264f04acf65ac362ab3829d9b3e77781defe55`.
Exactly one authorized supervisor `run` invocation executed
**2026-11-12 03:49:52–03:53:54 UTC**, returning exit1. No retry, repair,
code/limit/ini/gate change, fallback helper, new authority or cleanup activation
occurred. Parent root docs/gates/integrity/acceptance files are excluded.

## Scope reached and exact evidence limitation

The guarded runner started only the receipt-bound PostgreSQL/Redis backends and
created the payload ConfigMap and **one preflight Job**:

- Job: `proof-nextcloud/nc-preflight-33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1`.
- Observed Job UID: `533acd2d-4bea-43d0-8cd9-acaa04684dbf`.
- Failed Pod: `nc-preflight-33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1-7mgdm`.
- Pod UID: `753a1862-ee71-4aa4-ab09-2055fcc5c6c8`.
- CLI: exit1, reason Error, restartCount0; raw containerID/imageID/state/lastState
  are retained privately with the full Pod specification.

The PHP payload **was reached**. Its sole log line is a JSON observation with
`status: BLOCKED_OR_FAILED`, `error_type: RuntimeException`, and four native
cgroup measurements. There were no preceding PHP warnings/fatal-error lines.
The captured actual Pod envelope matches the intended preflight Job. The
retained payload ConfigMap exactly matches the reviewed PHP source and
unchanged core/Docker hash indexes.

**The exact failing preflight gate is unknown.** The payload emits exception
class only, not message or traceback. RuntimeException alone cannot establish
which source-parity/config/inventory/database/Redis gate failed. The CLI also
exports only a fixed exception type. This is a concrete diagnostic limitation,
not a source/config parity PASS or proof of any particular blocker.

No successful preflight result exists. Neither install-or-verify, fixture,
before, cron, assert-restore nor cleanup was launched. No native install command,
owned NULL-password token creation/synthetic aging, due-job precheck/native cron,
physical candidate deletion, live-control-survival or native restoration oracle
was reached. In particular, this run does **not** establish current application
volume emptiness, empty database, Redis authentication or a usable installation.
PostgreSQL/Redis startup may initialize/write their backend volumes; their data
was retained and not reset or reinspected. Historical read-only binding emptiness
is not a renewed post-run empty-volume assertion.

## Admission and bounded resource observations

Before launch, new private0600 receipt, exact PHP/supervisor hashes, current
context/TLS endpoint and sole Ready Node matched. All51 pre-existing journal
files were privately hash-indexed and subsequently verified unchanged.

Target: `admin@talos-proof`, `https://127.0.0.1:64120`, Node UID
`4845bfd5-3bdb-453d-8503-83b43edb7a1e`; namespace UID
`52497afe-f428-4b0e-aa52-cc92e9f2bf6a`; original Secret UID
`81144bf1-7ec2-42e3-90ba-564d787eed4f`. Independent final Secret inspection
projected UID only, never credential values.

Three fresh independent dual admissions were journaled. Observed minima:
kubelet **1214.96484375MiB**, Talos **1084.1484375MiB**, both above832MiB.
PG384 + Redis64 + one CLI192 + reserve192 remains **832MiB**.
No main web/CODE/other application group was activated.

The failed preflight helper's actual native cgroup observations were:

| Measurement | Value |
| --- | ---: |
| memory.current | 94810112 bytes |
| memory.peak | 94810112 bytes (90.41796875MiB) |
| memory.events oom | 0 |
| memory.events oom_kill | 0 |
| memory.stat anon | 9486336 bytes |
| memory.stat file | 83226624 bytes |

Full counter records are retained privately. No helper OOM is evidenced; this
measurement cannot establish capacity or completion of later heavy phases. The
sequential lightweight-PHP-parent/one-heavy-child cron model was **not exercised**
because the cron phase was not reached.192MiB remains a bounded trial ceiling,
not satisfaction of Nextcloud's512MB-per-process/PHP-memory-limit recommendation.

## Capture, stop and retained state

The failed helper's raw Pod state/current logs were captured **before** its
exact-UID-precondition retirement. Previous logs were not applicable because
restartCount was0. The runner then captured backend Pod state and performed
guarded UID-bound replicas0 patches and absence waits. Additional generic
pre-deletion backend captures/logs are retained; their metadata records contain
no capture-gap markers. This does not claim complete backend lifetime/cgroup
coverage. No `stop-unconfirmed` event was recorded and no extra stop invocation
was needed.

Fresh independent final API reads and pure-validator replay confirmed:

- Zero proof Pods, Jobs and DaemonSets, including terminal CLI/helpers; all proof
  application controllers replicas0 and schedules suspended.
- Only the existing local-path provisioner controller Pod in storage namespace;
  no storage helper observed.
- All original eleven declarations and Secret retain their original UIDs.
- All three application/backend PVCs remain Bound to original PV UIDs, exact
  claimRefs, Retain policies, backing paths and capacities. No volume was deleted,
  reset or content-cleaned. Payload ConfigMap is also retained.
- All six native prerequisite NetworkPolicy UIDs and full declared specs match.
- Original51 journal files remain byte-for-byte unchanged. New-run events retain
  pending, blocked-pending-cleanup and stop evidence, **without clean**. The only
  unresolved pending transaction is this failed run.

The original binding's automatic-provisioner lifetime log/cgroup gap remains
historical and explicit. This native run neither repeats nor repairs it.

## Private handoff and authority retirement

Private base: `$HOME/.local/state/home-infra/talos-proof/diagnostics/`.
New output/capture/finalization files are O_EXCL0600; shared journal root remains
0700 with append-only UUID0600 events. No credentials/raw tokens/logs were
emitted to public stdout/evidence.

- `native-cron-prelaunch-history-33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1.json`:
  exact original51-file hash index.
- `native-cron-invocation-33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1.json`:
  private stdout/stderr paths, timestamps, exit1 and unchanged receipt hash.
  Stdout44bytes; stderr0bytes.
- `native-cron-final-stopped-snapshot-c918d571-31b2-4829-8582-657dd9713f90.json`:
  independent final identities, namespace/Node, Secret UID, retained declarations,
  policies/PVCs/PVs, all proof controller/Pod state.
- `native-cron-failure-handoff-5d1f1373-d42b-4d61-9a2a-cc34143942d8.json`:
  reached/unreached phases, exact failed-helper identity/status, counters,
  private raw-evidence paths/hashes, source hashes and explicit diagnostic gaps.
  SHA256: `e6237bd943d2333e34084aeb54a000e689b3b84bc1a5bcf2a557cd4eee01992b`.
- `native-cron-final-receipt-33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1.json`:
  exact final receipt archive, fsynced/O_EXCL0600 before active-path removal.
  Receipt SHA256:
  `f88bd1cd10b6050efe42768fa0a2fb16a88bd36026d080b9669c069373404e01`.
- `native-cron-finalization-33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1.json`:
  archive/removal and exact payload ConfigMap/source-index verification record.

The active receipt was removed only after exact archive comparison and fsync;
immutable issued history was not edited/refreshed. No new cleanup/recovery/run
receipt was issued. PENDING deliberately remains; ordinary activation/reuse is
blocked. Parent must review the failed preflight and diagnostic limitation before
any separately authorized recovery. No automatic main rerun, cleanup activation,
credential rotation, PVC reset, VM start or guard bypass is implied or performed.
