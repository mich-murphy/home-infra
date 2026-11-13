# First actual media batch — safe checkpoint

UTC 2026-11-11 14:31–14:41. Explicit parent serial lease; exact API https://127.0.0.1:64120, context admin@talos-proof, node UID4845bfd5-3bdb-453d-8503-83b43edb7a1e. VM configured3072MiB. All application/helper pods deleted at end (`kubectl get pods -A -o json`, filtered proof namespaces excluding Gateway/validation: `[]`). No host/Docker/otherVM change. Parent review required; not full media acceptance.

## Actual bounded results

- **Pinchflat PASS, profile scope only:** trusted Gateway TLS, anonymous rejection, fresh Basic credentials, CSRF profile CRUD, retained nonempty profile. Restart read-before-write PASS. Stopped two-volume archives restored to distinct freshPVC UIDs; restored profile read-before-write PASS. No Source/provider download.
- **Audiobookshelf PASS, synthetic audiobook scope:** trusted TLS local init/login, anonymous rejection, one offline scan, exact32044-byte WAV SHA256 `3efcae84508fce7c87b5366774aa9cc25b54281a4b5f9301761c270c90b12562`, HTTP206 exact range, progress and bookmark CRUD. Restart and different fresh threePVC restoration verified existing library/item/progress/bookmark before writes and replayed exact bytes. No external metadata/download.
- **qBittorrent BLOCKED:** genuine pinned server started, but HTTPS API login401, including with same-origin Referer. No settings exercise, restart or restore PASS. Suspected5.3 WebUI domain/Host validation issue; NOT confirmed. Config retained, credentials unchanged. Newly generated PBKDF2 bootstrap migrated upstream into `[WebUI]` section; HostHeaderValidation/CSRF remain true. Next worker should repair only fresh proof domain configuration via bounded stopped-PVC helper, not disable validation or rotate credentials. No torrent transfer claim.

## Exact command families

All commands ran from this worktree. `KUBECONFIG=~/.local/state/home-infra/talos-proof/config/kubeconfig`; `STATE=~/.local/state/home-infra/talos-proof/media`; `CA=~/.local/state/home-infra/talos-proof/config/proof-gateway-ca.crt`; service-specific parent receipt `leases/media-SERVICE.json`.

- `python3 scripts/talos-proof-media-bootstrap.py --state-dir "$STATE"` (prepared state was absent; no first-batch namespaces/PVCs existed; generated once, not rotated).
- `python3 scripts/talos-proof-media-batch.py start|restart|activate|stop SERVICE "$STATE"`
- `python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" --seed audiobookshelf`
- `python3 tests/talos-proof-media-functional.py SERVICE --base https://SERVICE.proof.invalid:18443 --ca "$CA" --state-dir "$STATE" [--phase verify] [--fixture "$STATE/proof-tone.wav"]`
- `python3 scripts/talos-proof-media-recovery.py snapshot|restore SERVICE --state "$STATE"`
- `python3 scripts/talos-proof-media-observe.py SERVICE --state "$STATE"`

TLS client uses CA verification, exact service hostname/SNI and loopback18443; no diagnostic port-forward functional substitution. Published JSON has exact podUID/imageID/current+last termination and memory.current/peak/stat/events, plus archive hashes and source/destination PVC UIDs. Private credentials, raw logs and archives remain outside Git.

## Failures and procedural deviations retained

1. Initial Talos read targeted guest50000 and timed out. Initial receipt refresh used min(actual kubelet706MiB, previously supplied Talos1400), NOT a fresh Talos read. Disclosed immediately to parent. Subsequent reads correctly used configured loopback50120 and actual `/proc/meminfo` plus kubelet summary; no further identity/group/expiry edits. Subsequent conservative admission observations: Pinchflat min1572/1159=1159; ABS min1619/1301=1301, min1367/1234=1234, min1339/1266=1266; qbit min1324/1269=1269. App256+reserve192; ABS seed adds64; stopped recovery helper128+reserve192. No pressure/cache-drop/limit reduction.
2. First restored Pinchflat verification failed on unexpected anonymous status; same unchanged verifier later PASS. First restored ABS verification HTTP503; stopped, refreshed memory, reactivated, observed, unchanged verifier PASS. Readiness probes DO exist (an earlier verbal no-probe diagnosis was wrong); Gateway endpoint convergence is suspected, not proven. These are retained failed attempts, not suppressed results.
3. Pinchflat recovery Job delete returned while helper pod was still Terminating, briefly overlapping restored app. Actual1159MiB receipt exceeded app256+helper128+reserve192=576, but lifecycle did not explicitly enforce this overlap. Fixed recovery and seeder cleanup to wait for pod deletion after Job deletion before activation/next stage. ABS used fixed cleanup. Retain this procedural defect in review; do not generalize permission for overlap.
4. No observed OOM/oom_kill/restarts in captured app lifetimes. Pinchflat memory.peak reached268435456bytes (the256MiB ceiling) with captured memory.events max/oom/oom_kill0: limited experiment, not comfortable production headroom. ABS max observed peak80343040bytes; qbit49963008bytes. Old podUIDs and measurements remain in JSON, not just latest restartCount0. These are cgroup peaks for the recorded container lifetimes, not a full-node capacity claim.

All three Deployments are stopped with PVCs retained. Pinchflat/ABS Deployment claims now reference restored volumes: use **activate**, NOT start, to preserve those references. qbit can resume via activate after an approved bounded domain-configuration repair. Media lease released at this checkpoint; any resumed activation requires parent clearance. Protocol worker reserved paths remain untouched.
