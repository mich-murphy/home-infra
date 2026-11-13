# Operations live proof — bounded capability acceptance, 2026-11-11

## Follow-up exclusive Flux lease: PASS, 15:06–15:08 UTC

The parent granted a new45-minute `operations-flux` lease after media completed and its receipts were revoked. This worker changed only lease observation fields, refreshed as **min(kubelet availableBytes / 2^20,Talos MemAvailable MiB)** before guarded commands; group, identity and expiry were unchanged. Ordinary earlier app activity had naturally changed cache accounting. No cache dropping, synthetic pressure, host/VM tuning, controller-limit reduction, network widening, flag or RBAC change was used. The independent supervised guard remained parent-owned.

| New gate | Result / receipt |
|---|---|
| First newly admitted attempt | `flux-initial-apply-failure.json`: admitted1394.6MiB, then apply failed; suspension cleanup also failed, Deployment deletion attempted in finally. Original subprocess errors were withheld/not retained; exact cause unknown. No configuration changes before retry. |
| Admission for successful run | `flux-admission.json`: kubelet1241980928bytes (1184.4MiB) >= unchanged939524096bytes (896MiB). Historical `flux-refusal.json` remains unchanged and valid. |
| Reconcile/drift/path rollback | `flux-live.json`:15:06:54–15:07:52UTC, observed **1 → drift → 1 → 2 → 1**. Public source artifact and applied revision both `sha1:5d9a9926106f76346950af20e8afc0ef346ac548`. Rollback changes fixture path, not Git commit/app release. |
| Negative RBAC | `flux-live.json`: fixture identity denied `create deployments` and `get secrets` in fixture namespace. No cluster-admin. |
| Runtime / bounded memory | `flux-measurements.json`: actual source/kustomize imageIDs match locked1.10.1 digests; all captured controller restart counters0. Minimum recorded transition available975474688bytes (930.3MiB), MemoryPressure=False. Per-command private guard additionally checked measured minimum against512MiB. Point samples are not a historical peak/instantaneous-minimum or soak guarantee. |
| Cleanup and release | `flux-final-state.json`, `flux-lease-release.json`: guarded15:08:36UTC audit found zero operations Deployments, zero active operations/proof-app pods, Kustomization suspended, fixture1, kubelet1161510912bytes (1107.7MiB). Receipt archived unchanged and active path removed immediately after audit. Shared CRDs/fixture retained. |

Private follow-up runner imported the same repository scripts, with no manifest changes. It used the fixed Talos1.14.5 CLI/config at endpoint127.0.0.1:50120/node172.31.250.10 and verified the existing receipt/context/TLS/node guard for Kubernetes commands. It refreshed only actual memory/time observations and checked pressure. The first apply error was not logged; error logging was added privately before the successful retry, which produced no command errors. No specific root-cause diagnosis is claimed. Final cleanup absence is independently evidenced, not inferred from the failed attempt.

Monitoring/loopback delivery, distinct-PVC recovery and private etcd snapshot were **not repeated**. Snapshot still predates Flux and is capture-only, never a restore test or post-Flux sentinel backup. No new VM/control-plane reset/host restart/source access. Parent owns host/source postflight and acceptance brief/gates. Current offline suite remains **15 passing tests**.

## Offline-only reproducibility / local retention follow-up

Inspection confirmed the accepted live runner submitted CRDs and custom resources together with no Established barrier. New code splits selected CRD apply → bounded Established wait → remaining generated objects; mock tests enforce the ordering and prohibit custom-resource apply after CRD apply/wait failure. **This closes an identified ordering gap, not a conclusive diagnosis of the first historical failure**: no original stderr exists. `flux-initial-apply-failure.json`, the earlier refusal, and all live receipts remain unchanged. The new bootstrap sequence is **live UNTESTED**; no live CRD deletion/reapply or cluster command was used.

Future generated Flux bootstrap failures retain raw stderr in private0600 exclusive-create files and a matching0600 receipt. Only fixed phase/category, exit code and stderr SHA256 are eligible for publication after review; raw stderr/config/command values remain private. Logging is scoped to Flux bootstrap apply/wait and does not change the generic operations helper. Exit and timeout paths are unit-tested with sensitive-looking sentinel errors and no stdout/stderr leakage.

`offline-bootstrap-retention.json` records a **local temporary** persistence/retention check: independently reload/hash an actual saved14:13:35UTC observation copy, retain it byte-identical, dry-run then explicitly prune a separate synthetic40-day-old timestamp fixture, and leave an unmarked synthetic archive unchanged. Original observations/recovery/snapshots were untouched. New monitor runs opt into bounded operator-run local retention with hashes/ownership/permissions checks; historical unmarked directories are not retroactively enrolled. This is not a new live monitor/alert run,40days of real elapsed retention, scheduled collector or production history/paging SLO.

Current offline validation: **19 tests pass** plus syntax checks. Historical live reconcile/drift/path rollback/RBAC/runtime/cleanup evidence still describes the earlier successful runner; it does not certify the new sequencing, diagnostic failure path or monitor-history marker path live. Parent acceptance gates/brief remain outside this change.

## Historical independent operations window — partial acceptance at that time

Everything below describes the earlier completed run only; its Flux refusal and untested status at that time are preserved, not the final follow-up status.

Window: 14:13:35–14:17:18 UTC. Target: VM120 only, enrolled node UID `4845bfd5-3bdb-453d-8503-83b43edb7a1e`, context `admin@talos-proof`, TLS API `https://127.0.0.1:64120`. Coordinator granted exclusive `operations` then `operations-flux` scope; no concurrent app workloads. The coordinator's preceding cold start selected3072MiB; this worker made no host/VM changes.

## Execution and provenance

Working tree: `feat/talos-live-proof`, baseline commit `3b0703395e82f1c6cf1a72659758bd6eef743ff2`. Public Flux fixture commit: `5d9a9926106f76346950af20e8afc0ef346ac548`.

Private runner imported the repository entry points and wrapped the existing guard. Before **every** guarded command it ran the fixed private Talos1.14.5 binary with fixed Talos config/endpoint/node and `memory`; it updated only lease `available_mib` and `measured_at`. It retained receipt group/expiry/identity checks and all repository context/TLS/UID checks, and added a stop below512MiB Talos available or node pressure. No private runner/config/archive/snapshot is published.

Executed sequentially (runner maps these to the corresponding repository `main()`):

```text
leased-runner.py monitor --test-alert
leased-runner.py recovery
leased-runner.py flux --action run --revision 5d9a9926106f76346950af20e8afc0ef346ac548
leased-runner.py snapshot
leased-runner.py monitor --minimum-available-mib 896
leased-runner.py flux --action run --revision 5d9a9926106f76346950af20e8afc0ef346ac548
```

The second Flux attempt only persisted a structured admission refusal after adding that instrumentation; both refused before manifest generation/apply. No deployment/controller cleanup command was needed because neither attempt installed anything. Final guarded reads collected pods/deployments across namespaces, retained recovery claims and node identity. Both active lease paths were then removed by archiving unchanged receipts as `operations.released-20261111T141718Z.json` and `operations-flux.released-20261111T141718Z.json` under private `leases/`.

Monitor/recovery/snapshot executed the baseline operations script before the later runtime-image evidence enhancement. Flux used locally modified instrumentation in this delivery, but never reached its new reconciliation sampling path. The future recovery `runtime_images`/explicit empty-directory receipt fields and Flux transition sampling are offline-tested changes, **not retroactively present in the live receipts**.

## Results and evidence

| Gate | Result | Evidence / interpretation |
|---|---|---|
| Actual observations | PASS, bounded point samples | `monitor-live.json`: kubelet node/pod/container working sets, available bytes, filesystem, capacity/allocatable, conditions, restart counters. No historical peak/soak claim; peak is not reported by this API. |
| Alert sink | PASS, loopback HTTP only | Initial synthetic `ProofDeliveryTest` proves delivery, not OOM detection. Existing absolute restart counts also delivered; later actual available723636224bytes below chosen896MiB threshold delivered `NodeMemoryHeadroomLow`. Counters unchanged between samples. No induced OOM or external pager. |
| Off-node recovery | PASS, synthetic static file only | `recovery-live.json`: fresh distinct claim UIDs/PV names, bound-claim-UID and Retain checks, tar SHA256 and matching restored-content SHA256. Both directories checked empty before source write; destination rechecked immediately before extraction. Source pod deleted and awaited before extracting into destination. Both pods removed in finally cleanup. No overwrite or app-consistency claim. |
| Flux | BLOCKED, NOT a pass | `flux-refusal.json`: kubelet available673435648bytes (~642.2MiB), required939524096bytes (896MiB). Earlier baseline710MiB also insufficient. Talos1421MiB MemAvailable is a different metric and was not substituted. No drift repair, path rollback, negative RBAC, runtime imageID/restart or sentinel proof. |
| Private etcd snapshot | CAPTURE PASS, RESTORE UNTESTED | `snapshot-capture.json`: 12443680bytes, SHA256 metadata only; archive remained private off-node0600. Captured after Flux refusal, without Flux sentinel. No engine restore/control-plane reset/VM121. |
| Cleanup and lease release | PASS | `final-state.json`, `lease-release.json`: no active operations pods, no operations Deployments, no other active proof app pods; both recovery claims still Bound. No CRDs/PVCs/PVs deleted. |

Recovery fixture declared BusyBox1.37.0 index digest `sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec`. Its runtime imageID/restarts were not captured before pod deletion; the declaration is not proof of actual runtime imageID. Flux controller versions/digests remain source pins only because admission failed. Actual Talos client/server1.14.5, kubelet1.36.5, containerd2.3.7, kernel6.18.58-talos were verified.

Private source archive and snapshot are under timestamped directories beneath `~/.local/state/home-infra/talos-proof/operations/`. Only reviewed JSON metadata is public. Host/source postflight is coordinator-owned; this worker did not access or change source services, production guests, host tuning or network boundaries.

## Offline validation

`python3 tests/talos-proof-operations_test.py`: **15 passing tests**, including the new zero/marginal/710MiB pre-apply admission refusal regression; initial inherited suite14 passing before execution. Controller transition sampling is not live acceptance. Current limits/reserve remain unchanged. A new coordinator lease and genuinely passing baseline are required to retry Flux.
