# First-known child OOM stop and complete previous-Pod deletion — OFFLINE

Followup to parent review of a9083295 and the counter-race fix0b7d0ca4.
No lease, activation, proof-runtime/production call, credential change, resource
change or recovery-archive mutation. Parent still owns grant/readiness/root gates.

## Child-only OOM is fatal even with main restartCount0

New `talos-proof-media-pinchflat-watch.py` reads actual container-native
cgroup-v2 `memory.current`, `memory.peak`, `memory.stat` and `memory.events` using
the existing fixed read-only `/bin/sh`/`head` collector. There is NO new Python
process in the fixture for cgroup sampling; monitoring code runs on the workstation.
The existing provider snapshot reader remains unchanged by this followup.

Every running container, including RSS fixture and restartable init sidecars if
present, is sampled. Positive `oom`, `oom_kill` or `oom_group_kill` is immediately
fatal when observed, including `oom>0` without an OOM victim or a child-only kill
while main restartCount remains0. Current-lifetime positives are not normalized
away as a baseline. Pod current/previous termination and restart checks remain.
Missing/unreadable/malformed counters fail closed, never become zero. Samples
retain actual counters, Pod UID and container ID in UUID-exclusive0600 private
JSON. Observed failure also writes a separate immutable STOP receipt.

Provider native exec controls now have synchronous before/after samples and a
workstation periodic watcher during the entire exercise/verify. Native HTTP POST
controls also have before/after checkpoints. Any native exec failure—including
137 even if followup counters would be zero—latches STOP and retains the original
exception/private diagnostics; there is no RPC, command or activation retry.
The periodic watcher attempts immediate scale0 then best-effort observation and
Pod deletion on a failure even
while the main control exec is still blocked. Its latch prevents further control
commands. Evidence-write failure no longer skips the provider's cleanup attempt;
failed cleanup is explicitly reported as requiring parent action.

Batch startup samples before activation, while waiting for readiness, and during
rollout status. An existing STOP receipt blocks start/activate/restart BEFORE any
activation mutation. Retained STOP receipts are never automatically cleared:
parent must review any failed experiment and explicitly manage a later window,
not silently rerun the same receipt.

### Continuous outer-window watcher — future command only

Under a NEW explicit parent lease, an operator can start this bounded workstation
watcher in a separate terminal BEFORE the single authorized activation:

```sh
python3 scripts/talos-proof-media-pinchflat-watch.py --state "$STATE" --seconds 900
```

Only this outer watcher permits zero Pods while awaiting activation. Native
control preflights still require exactly one Pod with all app/fixture containers
running. The outer watcher covers startup→exercise gaps and checks every second
between completed sample passes. On a known failure it stops; its deadline or
interruption also attempts stop rather than leaving an unmonitored application.
Do not launch it without a parent grant, self-renew its lease or start a second
activation. Parent owns arbitration and cleanup if the lease expires or target
checks prevent mutation. Embedded exercise and startup checks remain defense in
depth, not permission to omit continuous observation across the window.

This is bounded fail-stop detection, not hard-real-time prevention. Native exec
and API latency can extend sampling intervals; Kubernetes may restart a container
between samples. Cgroup counters cover current container lifetimes, and status
checks preserve known restarts. Actual shell/exec overhead is UNMEASURED and
must be included in the future704 MiB experiment. No limits or VM sizing changed.

## Complete previous application/fixture/helper Pod deletion

Media `exclusivity()` now rejects EVERY Pod in another proof namespace, including
Succeeded, Failed, Pending and Terminating Pods. There is no proof-validation
fixture exemption and no blanket proof-gateway Pod/controller exemption.
Unselected pipeline Pods are rejected even in terminal phases. Positive foreign
Deployment/StatefulSet replicas remain forbidden even without Pods. Stopped
controllers with no Pods are not activation.

The checked-in Gateway profile declares Cilium Gateway/GatewayClass/configuration
and Service routing, with Cilium/Envoy platform infrastructure outside application
namespaces; it does not require an application Pod exemption in proof-gateway.
Platform system-namespace infrastructure remains outside the proof-application
namespace check. If a future Gateway implementation introduces real Pods inside
proof-gateway, this guard intentionally blocks them pending explicit identity/
owner-chain review—it does not infer infrastructure status from a namespace or
spoofable label. No platform resources or data-owner safety code were changed.

## Offline validation

- New watch suite **11 methods**, repeated **10 complete bounded runs**: positive
  oom alone/oom_kill alone with restart0; immutable native-counter evidence;
  unavailable counters; before/after command ordering; no control exec after a
  known failure; exec137 latch with no rerun; periodic stop during a blocked
  control interval; retained STOP blocks activation before mutations; immediate scale0 precedes
  extra diagnostic exec; validation/
  gateway/foreign terminal and terminating Pod refusal; foreign positive
  controllers; unselected terminal pipeline Pod refusal.
- All **24 media test files** passed separately, including the unchanged exact
  native-output SHA and settled snapshot/duplicate-byte coverage gates.
- Optional RSS static Kustomize safety render and whitespace checks passed.
- Repeat-test logs were UUID-exclusive0600 files in a private workstation
  temporary directory. No native runtime success or clean-all-CI claim follows.

The384 main +128 fixture +192 reserve =704 MiB trial remains unexecuted and
requires a NEW parent grant. Historical Jellyfin/Plex failures and all three
Pinchflat OOMs remain retained. No other group is live-authorized.
