# Offline transfer/helper integration checkpoint

No live calls/lease/activation. Data owns exclusive CODE/WOPI window. Prior failed observations and existing media credentials/PVCs unchanged.52 offline methods pass (43 previous +6 transfer integration contracts +3 helper contracts); four renders pass existing static validator. These are executable integration preparations, NOT real qBit/SAB download, helper, or recovery acceptance.

## Explicit protocol profiles

New fixture-only Kustomizations: `kubernetes/apps/media/protocol-qbittorrent` and `.../protocol-sabnzbd`. Parent notified to add both render paths to its owned main gate. Both default replicas0 and require existing selected-service namespace; neither reapplies client Deployment/PVC references. Fixture128MiB uses pinned Tautulli Python image, read-only rootfs, nonroot, no token/caps, startup/readiness/liveness bounds. Payload is known32044-byte generated WAV, SHA256 `3efcae84508fce7c87b5366774aa9cc25b54281a4b5f9301761c270c90b12562`, mounted as regular subPath ConfigMap file; fixture mounts NO client PVC. Image Python/subPath runtime behavior remain live gates.

Narrow policy: namespace AND app selectors, qBit→fixture TCP8080/6881, SAB→fixture TCP8119 only; no NNTP HTTP artifact fetch by SAB (runner obtains NZB through fixture localhost control-plane exec and submits API upload). Fixture initiates no connections. Existing qBit/SAB broad podSelector{} *allow* policies were narrowed to client app selectors so they cannot accidentally grant the new fixture DNS/Gateway/dependency ingress. Namespace-wide default deny remains. Profile temporary allowances are deleted after fixture stops and all fixture pods are deleted; default deny stays.

Parent receipt must contain existing group qbittorrent OR sabnzbd plus **`protocol_fixture: "download-protocols"`**. Full prospective admission is client256+fixture128+reserve192=576MiB from fresh dual-metric minimum. Starting fixture rechecks before apply and scale. Basic activation detects any desired/live/Terminating fixture and charges128 too; no basic-lease bypass. Stopped-volume helper admission REFUSES while fixture desired/pods remain. Negative tests demonstrate575 refusal/576 admission, unauthorized fixture rejection, automatic basic-runner charge, and no stopped-helper overlap. No limit shrink.

## Runner and actual acceptance gates

With a new explicit parent lease, trusted CA and preserved state:

```text
# First complete qbit basic auth/prefs repair; retain CSRF/Host validation.
python3 scripts/talos-proof-media-transfer.py start-fixture qbittorrent --state STATE
python3 scripts/talos-proof-media-transfer.py exercise qbittorrent --state STATE --ca CA
python3 scripts/talos-proof-media-transfer.py stop-fixture qbittorrent --state STATE
# fixture MUST be off/deleted before restart/snapshot/restore helper work.
# Reuse existing batch restart + stopped snapshot + distinct freshPVC restore + activate.
python3 scripts/talos-proof-media-transfer.py verify qbittorrent --state STATE --ca CA
# Same command family for sabnzbd, separately granted and strictly serial.
# After final persistence/recovery verification, remove temporary SAB settings:
python3 scripts/talos-proof-media-transfer.py cleanup-settings sabnzbd --state STATE --ca CA
```

`exercise` refuses an existing retained transfer marker. It exclusively creates a random fresh `/data/.../protocol-*` destination after asserting absence; does not delete/prepopulate. Persisted attempt marker precedes submission/settings changes, preserving failure recovery. Metadata is fetched only from fixture's fixed localhost endpoints, never binary-printed. App upload uses bounded multipart. qBit requires empty queue and disabled DHT/PeX/LSD; tracks exact infohash, progress1, completed-size, amount_left0. SAB requires empty queue/history/provider list, configures only public synthetic server with two connections/SSLoff, sets isolated temporary/incomplete and completed paths, submits NZB with pp0/no script, requires matching successful Completed history/no fail message. Existing provider configs are refused, not overwritten.

Both require source identity unchanged, positive actual protocol counter deltas (including bytes>=payload size), and `sha256sum`+size of actual app output. Source has no access to destination, so matching bytes cannot arise from seeding the client volume. Output path is constrained to proof `/data` and synthetic basename. Private immutable successful marker retains baseline/final counters and app IDs. `verify` reads completed state+output hash without creating destination/submitting/configuring server or reading fixture; works with fixture off after restart or distinctPVC recovery. It is separate from older settings-only qBit test, which assumes empty queue. Use transfer verifier once a torrent exists; do not mistake settings verifier's empty-queue refusal for protocol data loss. No real-client completion is claimed until these commands run.

SAB cleanup removes only temporary fixture server/restores original download/complete settings; synthetic output/history stays for audit. Full original misc settings are PRIVATE only. Failure attempt records also retain original directory settings, allowing explicit cleanup after a failed attempt. Final app stop/observer/wait required. Client/fixture cgroup/pod identity evidence is captured before fixture stop. Root default profiles remain0.

Origin/Host scope: qbit route-only repair remains pending live. Current transfer API is a no-Origin CLI path; browser/intended external Origin behavior is NOT claimed. Exact5.3 source permits absent Origin but checks present Origin against Host (or forwarded Host when explicitly configured); safe proof-specific proxy/Origin integration may need further repair without disabling CSRF/host validation. Ordinary API auth failures remain hard gates, never retried or relabeled.

## Recyclarr: actual mutation plus second-run no-drift gate

New `talos-proof-media-pipeline.py sync-recyclarr --pair radarr+recyclarr --state STATE --ca CA` requires an explicit reviewed pair lease, not this future qBit/SAB window. Reads nonempty local customformat state before mutation; requires synthetic name absent. Runs actual `sync` (no --preview) twice from suspended bounded CronJob template, without unsuspending it. First authenticated API read must show exactly one nonempty synthetic format and unchanged unrelated formats. Second must preserve exact IDs+definitions, not merely exit0/log text. Logs/pod image+termination status retained privately, sanitized hashes printed; jobs and pods deleted before next run. Unit proves real args on both runs and rejects second-run ID drift. Runtime image/entrypoint/provider compatibility remains pending; no preview-only acceptance.

## Kometa: scoped synthetic metadata proxy/CA wiring

Suspended Kometa now mounts existing strict synthetic TMDb contract code and dedicated proof TLS Secret. A128MiB **native sidecar initContainer** starts loopback18081 before main, remains during run, and terminates when main exits (unlike a regular never-ending sidecar that would prevent Job completion). Native-sidecar Kubernetes/runtime compatibility remains an explicit live gate. Kometa admission now512MiB main+sidecar, not384, before reserve/dependent Plex. No helper live lease is implied.

Only Kometa main receives loopback HTTPS_PROXY/HTTP_PROXY and dedicated REQUESTS_CA_BUNDLE/SSL_CERT_FILE. NO_PROXY excludes localhost and proof .svc Plex endpoint. No global CA/DNS/host override, upstream forwarding or real metadata account. Dedicated code ConfigMap generated under fixtures Kustomization; protocol fixtures not included in media root. Native sidecar gets fresh synthetic API key from existing bootstrap, TLS leaf/key from separate Secret; no old bootstrap regeneration.

`python3 scripts/talos-proof-media-contract-ca.py --state STATE` generates new dedicated30-day proofCA and api.themoviedb.org leaf **offline**, verifies hostname, writes only private0600 files plus `metadata-contract-secret.json`, and refuses partial/existing outputs. No actual state generation/apply occurred here. Private CA signing key is NOT in Secret. Unit verifies issuance/permissions/refusal to rotate. This is MOCK TMDb-contract compatibility, not account/provider integration. Actual Kometa collection creation and idempotent second run still require executable pair runner/collection API assertions and live compatibility evidence; wiring alone is not acceptance.

## Remaining work, explicitly not accepted

Tautulli setup/activity/history workflow; Seerr fresh local/Jellyfin setup + synthetic metadata request lifecycle; Kometa real collection/second-run orchestration; jellyplex mapped actual watched-state mutation (dryrun insufficient); arr real import/hardlink and shared recovery. Existing allowed policies and API stubs do not satisfy these gates. Continue offline implementation in the next bounded checkpoint while awaiting parent-granted media window.
