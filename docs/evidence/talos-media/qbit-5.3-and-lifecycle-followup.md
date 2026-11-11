# Offline follow-up: qBittorrent5.3 / helper deletion / Gateway convergence

No cluster/Talos calls or activation in this follow-up. Old parent receipts are revoked; operations owns live Flux window. Fresh media credentials/PVCs and all failed observations from first-live-batch remain unchanged. These implementation tests are NOT live acceptance.

## Exact release source findings

Public references, all tag `release-5.3.0` at https://github.com/qbittorrent/qBittorrent/tree/release-5.3.0:

- `src/webui/webapplication.cpp`: `validateHostHeader()` first rejects an explicit HTTP Host port unequal to the backend local port, before considering domain allowlist. Thus Gateway authority `qbittorrent.proof.invalid:18443` versus backend8080 has a concrete401 path. `isCrossSiteRequest()` permits API requests without Origin/Referer; adding Referer was not a sufficient repair. `Sec-Fetch-Site: same-origin` passes its browser branch. Prior diagnosis of simply missing domain allowlist was incomplete.
- `src/base/preferences.cpp`: `getServerDomains()` defaults to `*`, so absence of ServerDomains does not prove a missing-domain rejection. No new wildcard or disabled protection was added.
- `src/webui/api/authcontroller.cpp`:5.3 `loginAction()` throws Unauthorized APIError for rejected credentials. Contrary to older API docs/parent hypothesis, wrong password CAN also produce401, not only HTTP200 `Fails.`. A route repair therefore does not establish credential correctness; actual login remains a live gate.
- `src/base/utils/password.cpp`: PBKDF2 SHA512,100000 iterations,16-byte salt,64-byte key, serialized base64(salt):base64(key), matches current offline bootstrap algorithm. This confirms algorithm compatibility, NOT the retained server's actual password acceptance.

Prepared proof-only HTTPRoute `URLRewrite.hostname` retains exact proof hostname but removes incoming external port from backend Host. Isolated and pipeline routes both include it. TLS authority/SNI remain unchanged in the client. CSRF and HostHeaderValidation remain enabled; no credentials change or production setting carried over. Cilium/Gateway URLRewrite support and actual outgoing Host remain **PENDING LIVE**. `batch activate qbittorrent STATE` applies only the repaired HTTPRoute before scale-up, never reapplies Deployment/default PVC claims. Fresh bootstrap and retained credentials are not rotated. Browser Origin/Referer behavior with non-browser clients remains a separate boundary, not claimed fixed by adding broad proxy trust.

## Fail-closed helper activation guard

Recovery and fixture Job cleanup already wait for actual Pod deletion after Job deletion. A separate activation guard now rejects ANY remaining Job-owned Pod in the selected namespace, including Pending/Running/Succeeded/Failed and Terminating. It runs before start/activate/restart (and before start's scale), with no reliance on coincidental available memory. Pipeline activation checks too; preview cleanup waits for actual helper deletion. No bounded retry that proceeds after timeout exists.

Negative unit tests invoke actual batch main for all three activation actions and all four phases with a Terminating Job pod, mocking kube execution and asserting **zero calls**: no apply, scale or rollout occurs. Deleted helper case succeeds at the guard. This closes the requested Pinchflat overlap defect; previous live deviation remains in first-live-batch.md, not erased.

## Known Gateway503 convergence gate

All first-batch workloads had startup/readiness probes. Pinchflat uses HTTP `/healthcheck`, ABS `/`, qbit `/`; their successful kubelet rollout does not prove Gateway endpoint propagation. Functional CLI now performs an anonymous HTTP200 readiness GET before authentication assertions: Pinchflat `/healthcheck`, ABS `/status`, Plex adapter `/proof-health`, other services `/`. Only this GET gate retries503, at most16 attempts with2-second spacing; response socket timeout remains45seconds. It reports observed503 count.401/403/404/500 immediately fail, never count as readiness success, and are not retried. Normal API calls and mutations are never retried. Unit tests prove503 convergence, bounded exhaustion, and immediate401/403 rejection.

## Correct memory collector

`TALOSCONFIG=.../config/talosconfig python3 scripts/talos-proof-media-memory.py qbittorrent --talosctl .../bin/talosctl` requires current parent lease + private kubeconfig and talosconfig. Uses explicit Talos endpoint127.0.0.1:50120/node172.31.250.10, fresh `/proc/meminfo`, actual kubelet node-proxy summary, takes floor-MiB minimum. Both reads must succeed. Revalidates lease after reading and edits ONLY available_mib/measured_at; failed Talos read leaves receipt unchanged. Unit verifies exact endpoint/config argv, min selection, preserved identity/group/expiry and no stale fallback. Command was NOT executed offline.

## Next authorized execution

1. Parent releases Flux and grants fresh qbit basic lease. Refresh actual min memory; existing256+192 gate unchanged. Activate existing qbit with repaired route, require Gateway readiness and real credential login; if401 remains, inspect only sanitized security/config state, without rotation. Then exercise→restart verify→stopped snapshot→differentPVC restore→activate verify→stop and verify pods deleted.
2. Protocol fixture ownership transferred from completed worker at590f7fae. Test renamed to `talos-proof-media-protocols_test.py`, so standard glob includes its six genuine socket tests. Read download-protocol-fixtures.md for the implementation interface. No protocol integration/activation performed yet. Actual transfer needs explicit qbit256+fixture128+reserve192=576 lease, narrow reciprocal policies, empty destination proof, positive counters, real completed app state and exact output SHA. SAB requires its own selected lease. Existing basic lease cannot authorize fixtures.
3. Tautulli/Seerr workflows, Kometa per-helper proxy/CA wiring, meaningful jellyplex divergence, actual arr imports/hardlinks/shared recovery remain unimplemented/unproved; do not claim generic scaffold completion. Prior public-source notes remain research, not live results.

Offline regression result:43 methods (previous33 +4 lifecycle +6 newly globbed protocol socket tests) pass. Both isolated and integration renders still pass existing static safety validators. No new live pass follows from this checkpoint.
