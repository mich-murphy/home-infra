# RSS384 window: stopped preparation blocked; lease released

Window `49eae0a3-75d7-44e1-b5d8-103211169c8e`, 2026-11-11 UTC.
**No activation, no native exercise, no provider/capacity/decoder/recovery pass.**
The 384+128+192=704 MiB ceiling was not lowered. Parent retains acceptance,
brief/readiness/platform gates. No host/VM sizing/start, Internet/cloud, archive
capture/restore, binary/credential replacement, other-group activation or output
preseeding was performed.

## Actual sequence and blocker

- Read the exact new grant and public image review; retained initial issued copy.
  Independently verified target context/API/node UID, no foreign proof Pods,
  stopped retained controller UID, both retained PVC UIDs, and bootstrap Secret.
- Hashed 156 existing private media/config/issued-receipt files before work.
- Found the collector/guard expected legacy `available_mib`, whereas the exact
  grant provides `kubelet_available_mib` and `talos_available_mib`. Updated the
  collector to refresh only those two fields and `measured_at`; admission derives
  their minimum and rejects incomplete/invalid observations. Identity, expiry,
  group, scope and issued history remain unchanged. Legacy-only receipts retain
  compatibility; a legacy high value cannot override lower independent readings.
- Fresh exact-endpoint measurements: kubelet **1311 MiB**, Talos **1136 MiB**.
- Ran stopped `provider prepare` once with the original 120214-byte MP4. It failed
  with `Pinchflat resource/profile drift from explicit approved ceiling` during
  prospective validation, **before any ConfigMap/Secret/Deployment mutation**.
- Retained main CPU limit is Kubernetes-canonical string `"1"`; approved resource
  oracle expected string `"1000m"`. These are numerically equivalent, but the old
  raw-dictionary equality rejected the prospective template. Existing main limit
  remains 256 MiB; it was NOT patched to384. No gate bypass, resource rewrite or
  second preparation attempt was made in this window.
- Full Deployment JSON before/after is identical. A private file named
  `deployment-prepared.json` contains the unchanged stopped readback, **not a
  successfully prepared profile**.
- No outer OOM watcher was started because preparation failed before activation
  was eligible; there was no running application to monitor. No native PID1,
  node/cookie, loader/RPC version, runtime erl_call/yt-dlp hash/version, Source,
  extractor, Oban index/download, output or byte-coverage facts were obtained.
  Neither zero restarts during startup nor clean live cgroup counters are claimed.
  No runtime log/lastState/kernel collection was needed: no app Pod existed.

## Release and immutable-state proof

At release all proof application/helper Pods were absent, all proof Deployment/
StatefulSet replicas were0, and all proof CronJobs were suspended. The controller
remained stopped throughout. All 156 hashed old files are unchanged, including
old credentials, archives/results, original fixture, config and issued history.

The active grant was copied exclusively mode0600 to
`leases/revoked-media-pinchflat-rss384-49eae0a3-75d7-44e1-b5d8-103211169c8e.json`,
then the active pathname was removed. The issued copy remains unchanged. There is
no authorization to retry from the revoked receipt.

Post-release observation only, separate from receipts: kubelet **1345 MiB**,
Talos **1153 MiB**, measured_at `1794437806.029239`. No expiry/identity change.

Private evidence directory under media:
`rss384-window-49eae0a3-75d7-44e1-b5d8-103211169c8e/`.

| Private record | SHA256 |
| --- | --- |
| old-files-before.json AND old-files-after.json | `f0646a0b977aa4c1c7bb1fd6e7220348e8314ee1ec0f9210530b1d8df9fa2e11` |
| deployment-before.json AND deployment-prepared.json | `614224ba2c919420168976460eaaec706fd9f2cb819b97333f0ac1015999119b` |
| release-proof.json | `3fc1db84bb9b825d1448ddbbc6724dc82c5fbdaf55ca18388a8f49f916463ddb` |
| post-release-memory.json | `1fbb657b3f67ab6777a52f074b09178112d82b6038101b8b95cff87977c36626` |
| offline-test-results.json | `6f8c0b0f27b34e48e7725ffc0cce356bdd895e8863246171f919aa3e82ac825a` |

## Offline correction after release — NOT retried live

Resource oracle now compares exact supported quantities rather than spelling,
using the existing strict parser. `1` equals `1000m`; 999m/1001m/2, missing/extra
resource keys, memory/request drift, unknown containers and init/pod-level drift
still fail. The full effective512 MiB Pod ceiling and192 reserve remain required.
The stopped full-spec atomic patch and all preservation guards are unchanged.

All23 `talos-proof-media-*_test.py` files pass (**154 methods**) in private bounded
workstation runs, including10 provider and11 watcher methods. New regression
coverage checks canonical CPU equality versus genuinely changed limits, dual
memory minimum/invalid/missing values, and observation-only collector writes.
These are scoped offline tests, not the parent's full static count or live proof.
A future live attempt needs a new parent grant, fresh identities/headroom, stopped
preparation, prestarted watcher, private bound current log streaming, one bounded
activation/exercise, native runtime gates, and mandatory cleanup/release. This
window contains no restart or fresh-PVC recovery authorization or evidence.
