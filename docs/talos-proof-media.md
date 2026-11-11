# Isolated media proof

## Status and review gate

**Implemented statically; no live deployment or functional pass claimed.** Parent must review tests and live evidence before acceptance. The live node starts with 2560 MiB total RAM: activate **one media Deployment at a time**, only under a coordinator-granted resource lease. Limits are 512–768 MiB per application, not evidence that all source services fit simultaneously. Requests are scheduling reservations, not measured steady state. Image unpacking, controllers, storage and init containers also consume resources.

Current source of truth: `docker/{arrs,downloads,plex,jellyfin,jellyplex-watched,audiobookshelf,pinchflat,recyclarr}/compose.yml`. All **16 services** map to explicit Kustomize resources, with exact current Compose image digests (not running-image substitutions). Inventory notes a live-vs-Compose jellyplex-watched difference; this proof pins the requested current Compose and must not claim live-image fidelity for that service.

Historical design inspected via `git show origin/feature/talos-kubernetes:kubernetes/apps/media/jellyfin/deployment.yaml` and `...:kubernetes/apps/media/kometa/cronjob.yaml`. Its NFS claims, GPU resource, production URL, old digests, common namespace and active replicas were deliberately **not** carried forward.

## Boundaries

- One `proof-<service>` namespace per service; no broad common trust group. Every resource/pod carries `app.kubernetes.io/part-of: talos-proof`.
- Fresh `proof-local` 1-GiB PVCs only. No host/NFS mounts, GPU, host ports, production credentials/endpoints, public ingress or Internet allowance. Never mount source data, even read-only.
- Default deny ingress/egress, exact DNS namespace+pod selector on TCP/UDP 53, `proof-validation` ingress on application HTTP port only, exact source/destination namespace+app selectors for explicit dependencies. No IP blocks or blanket same-namespace allowance. Port-forward is an operator control-plane path and **does not prove NetworkPolicy enforcement**; parent network isolation tests remain mandatory.
- Allowed dependencies: arrs → qBittorrent/SABnzbd/Prowlarr; qbitwebui → qBittorrent; Tautulli/Kometa → Plex; Seerr → Jellyfin/Radarr/Sonarr; jellyplex-watched → Plex/Jellyfin; Recyclarr → Radarr/Sonarr. None are configured with production credentials. A policy allowance is not proof the integration works.
- `replicas: 0`; native helper CronJobs `suspend: true`, `Forbid`, zero retries, 180-second deadlines and one retained success/failure. Default reconciliation is safe; never unsuspend the entire group.
- Token automount disabled, RuntimeDefault seccomp, no privilege escalation, drop ALL capabilities. LinuxServer and Plex retain their Compose startup/chown/user-switch capabilities; audiobook port 80 retains NET_BIND_SERVICE. Fresh-config init explicitly runs as root with only CHOWN/DAC_OVERRIDE/FOWNER to initialize PVC ownership. Jellyfin/Recyclarr main processes are UID/GID 1000. Read-only root filesystem is enabled for Recyclarr with bounded disk scratch; other current images need runtime writes and are not incorrectly declared read-only.
- Jellyfin cache/Plex transcode use 256-MiB **disk** emptyDir, not memory tmpfs. Config and synthetic media persist on fresh PVCs. Cache/transcode survival is not user-data durability.

### Storage integration limitation

Per-service fixture PVCs are intentionally independent. qbitwebui's `/data/torrents` does **not** currently expose qBittorrent's files, and arr root folders do **not** share downloader bytes. Thus settings/API proof cannot be reported as an arr download/import/hardlink migration pass. A later reviewed integration batch needs a justified common trust boundary and fresh shared proof PVC/path topology (or explicit file transfer), with a local synthetic torrent/NNTP peer and memory lease. Do not substitute production download/indexer endpoints. Audiobookshelf proof media is read-only even though its production source is writable: writeback workflows remain a gap.

## Offline checks (no cluster mutation)

```sh
kubectl kustomize kubernetes/apps/media | python3 tests/kubernetes-proof.py
python3 tests/talos-proof-media_test.py
bash -n scripts/talos-proof-media-batch.sh
```

The suite checks current Compose mapping/digest parity, fail-closed rendered safety rules, default-deny/exact-selector egress, private secret modes/no credential stdout/refusal to silently rotate, deterministic synthetic fixture and bounded real helper invocations. These are **not runtime tests**.

## Fresh private bootstrap

```sh
STATE="$HOME/.local/state/talos-proof/media"  # outside this checkout; never commit
python3 scripts/talos-proof-media-bootstrap.py --state-dir "$STATE"
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE"
```

Generator creates 0700 state and 0600 files, refuses existing credentials, and prints only a state path. Service-specific Secret JSON contains newly generated API keys/passwords/encryption key plus a fresh seed config. Secrets are never part of Kustomize or Git. Seeds are copied only onto an uninitialized config PVC. Deleting/replacing Secret does **not** reset existing PVC credentials. Treat app stdout/logs as potentially secret-bearing: qbitwebui can print an initial password; do not commit raw logs. qBittorrent uses a preseeded PBKDF2 password, disables DHT/PeX/LSD and exposes no torrent listening port. Arr External UI authentication delegates access to this isolated namespace/control-plane boundary; API-key enforcement is explicitly tested. This is not an Internet-safe production UI authentication model.

Plex/Jellyfin helper tokens are deliberately `UNCONFIGURED-PROOF-ONLY`, not fake passing credentials. After fresh **proof** servers are initialized, manually update only private helper Secret fields with fresh proof-issued tokens under parent review. Never reuse Plex account claim, production machine IDs or application tokens. Recyclarr seed uses only proof arr keys and endpoints; it includes no production templates/custom formats. Kometa seed has no libraries and invalid TMDb credentials: it is a safe blocked starting point, **not a meaningful successful Kometa run**.

## Lease-gated runtime procedure (NOT EXECUTED)

Only after parent provides kubeconfig, approves tests and explicitly grants lease:

```sh
export KUBECONFIG=/private/path/to/proof-kubeconfig
export TALOS_PROOF_MEDIA_LEASE=/private/path/to/coordinator-media-lease.json
bash scripts/talos-proof-media-batch.sh start radarr "$STATE"
kubectl -n proof-radarr port-forward service/radarr 17878:7878  # separate terminal
python3 tests/talos-proof-media-functional.py radarr --base https://radarr.proof.invalid:18443 --ca "$STATE/proof-ca.crt" --state-dir "$STATE"
bash scripts/talos-proof-media-batch.sh stop radarr "$STATE"
```

Harness refuses a second active media Deployment, applies only one bundle, privately applies its Secret, starts one replica and waits at most 300 seconds. A rollout pass is startup evidence only. On any timeout/failure run `stop`; PVCs remain for investigation/recovery. Do not rely on the environment variable as a distributed lock: the coordinator owns resource arbitration. Stop port-forwards after each test. No script automatically starts dependencies or runs helpers.

For Jellyfin, start its batch, seed generated audio into its fresh PVC, then test through loopback:

```sh
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" --seed jellyfin
kubectl -n proof-jellyfin port-forward service/jellyfin 18096:8096
python3 tests/talos-proof-media-functional.py jellyfin --base https://jellyfin.proof.invalid:18443 --ca "$STATE/proof-ca.crt" --state-dir "$STATE" --fixture "$STATE/proof-tone.wav"
```

Seeder uses a transient 120-second Job with the same pinned service image, UID 1000, no token/capabilities, 16-MiB request/64-MiB limit, and only the proof fixture PVC. It streams a generated 32,044-byte two-second mono 440-Hz WAV, then deletes the Job. No external media/download occurs. The generated fixture's SHA256 is emitted for evidence. Jellyfin test performs fresh wizard/admin login, creates an offline music library, bounded scan, byte-identical direct audio stream, HTTP range seek and played-state write/read. It stores its fresh session token **privately** only. API/version incompatibilities fail; they must be fixed with observed evidence, never suppressed.

Restart persistence: record library/fixture IDs and played state, stop/start **without deleting PVCs**, authenticate again and read the existing state **before** re-running any test that writes it. Current harness does not automatically assert restart or clean-PVC restore, so neither is accepted yet. A WAV direct stream is not video/subtitle/resume, CPU transcode or GPU proof.

## Per-service acceptance matrix

Every row below is **PENDING LIVE**, not readiness-equivalent success.

| Source → proof workload | Implemented executable test / required remaining evidence |
|---|---|
| arrs/radarr → Deployment | Reject missing API key; fresh key; tag CRUD; rootfolder create/read/delete. Local synthetic movie import, settings persistence and downloader integration remain. |
| arrs/sonarr → Deployment | Same tag/rootfolder checks. Synthetic episode import and downloader integration remain. |
| arrs/lidarr → Deployment | API v1 missing-key rejection, tag CRUD and system status; rootfolder profile settings remain. Synthetic tagged music import/rename requires metadata strategy; no Internet enabled. |
| arrs/prowlarr → Deployment | Missing-key rejection + tag CRUD + system status. Local mock indexer/search-to-arr flow remains; no real indexers. |
| downloads/qbittorrent → Deployment | Fresh PBKDF2 login, assert empty torrent list/discovery disabled, preference write/read/restore. Local-only torrent transfer/recheck/persistence remains. |
| downloads/qbitwebui → Deployment | Fresh proof user seeded by pinned Bun init with bcrypt (no initial-password log). Executable authenticated instance CRUD, stored-credential connection and empty-queue stats, plus read-before-write persistence verification; requires explicit pipeline pair. PENDING LIVE. |
| downloads/sabnzbd → Deployment | API-key queue read, assert empty slots; refresh setting write/read/restore. Local NNTP fixture decode/checksum/recovery remains. |
| plex/plex → Deployment | Fresh unclaimed server and synthetic PVC; local token/library scan/stream/watch state test remains. Cloud claim/account is forbidden without explicit scoped parent authorization. |
| plex/tautulli → Deployment | Local Plex-only policy. Fresh setup + proof playback history/activity/settings test remains. |
| plex/seerr → Deployment | Proof Jellyfin/arr-only policy. Fresh setup/login/request lifecycle awaits safe metadata strategy; TMDb/cloud metadata blocked, not accepted as a dashboard pass. |
| plex/kometa → suspended CronJob | Native single run with read-only-config (protects config, **not** a Plex mutation dry-run). Empty library/invalid TMDb seed intentionally blocks meaningful run. Need proof library config, upstream CLI validation and approved metadata fixture strategy; do not run/claim success on empty config. |
| jellyfin/jellyfin → Deployment | Fresh setup/login + offline synthetic audio scan/exact stream/range seek/played flag test. Second-user ACL, resume, video/subtitles, restart/restore remain. No GPU. |
| jellyplex-watched → suspended CronJob | Real one-pass DRYRUN=True invocation against proof Plex/Jellyfin; fresh tokens still unset. Needs matching proof users/libraries and a deliberately divergent watched item; assert planned change plus no actual mutation. Exit zero alone is not acceptance. |
| audiobookshelf/audiobookshelf → Deployment | Executable fresh root setup/login, offline audiobook scan, exact stream SHA256/range seek, progress/bookmark CRUD and read-before-write durable-state verification. PENDING LIVE. |
| pinchflat/pinchflat → Deployment | Fresh Basic credentials configured. Executable anonymous rejection, CSRF-protected profile CRUD, retained nonempty profile and read-before-write persistence verification. No Source/YouTube download created. PENDING LIVE. |
| recyclarr/recyclarr → suspended CronJob | Real `sync --preview` with proof keys/endpoints. Offline fixture ConfigMap now replaces both implicit Git providers and supplies one synthetic custom format. Reviewed pipeline preview command checks planned Create plus unchanged Radarr customformat API before/after. Version/entrypoint/live behavior remain unverified. No empty-config/blocked fetch reported as success. |

Helper execution requires a separately reviewed **dependency batch** and parent allocation; the one-service harness intentionally cannot silently grant concurrent servers. No external Internet needs approved yet. Bring any required experimental allowance to parent before creating it; never allow private production networks.

## Evidence required before acceptance

Commit only sanitized summaries in `docs/evidence/talos-media/`: exact commands, image digests, UTC start/end, namespace/PVC UID, fixture checksum, test result, bounded resource measurements, restart and clean-PVC restore comparison, intentional auth/policy denials and unresolved limitations. Do not include Secret YAML, credentials, raw logs, session JSON or auth-bearing URLs. Current evidence contains only offline validation. Parent must review runtime test behavior and evidence before changing status.

## Integrated Gateway ingress (added for parent review)

All 13 UI services have an explicit HTTPRoute attached to Gateway `proof` in `proof-gateway`, host `<service>.proof.invalid`. Parent refs intentionally omit sectionName to attach to both existing HTTP/HTTPS wildcard listeners. There are no routes for helper CronJobs. Fresh proof namespaces carry the Gateway allowedRoutes label. No production DNS or public exposure is configured.

Policies allow the proof-gateway namespace on only each application HTTP port. Since Cilium Gateway proxies use the reserved `ingress` identity rather than ordinary namespaced pod identity, an additional narrowly selected CiliumNetworkPolicy allows `fromEntities: [ingress]` on the same exact target port. Parent networking review must verify this behavior and that only the dedicated proof Gateway exists; these identity allowances are not a claim of measured enforcement.

Once the platform is ready and a live lease is granted, test both route attachment (`Accepted`/`ResolvedRefs`) and functional traffic through the parent's SSH loopback forwards 18080→30080 and 18443→30443. For example, `curl --resolve radarr.proof.invalid:18443:127.0.0.1 --cacert /private/proof-ca.crt https://radarr.proof.invalid:18443/ping`; then run authenticated CRUD through that same trusted TLS route. The API harness now requires verified Gateway HTTPS: hostname/SNI remain the service proof hostname, TCP dials only 127.0.0.1:18443, and the private CA must verify the certificate. Proxy environment variables and cross-origin/downgrade redirects are blocked. Diagnostic port-forwards are not the functional acceptance path. No such live check has run.

## Fail-closed lease/target implementation update

`talos-proof-media-batch.sh` delegates to the small Python lifecycle command; no direct unguarded kubectl remains in it. `talos-proof-media-safety.py` is shared only by owned media scripts, not a templating/deployment framework. `TALOS_PROOF_MEDIA_LEASE` is a **private 0600 JSON file path**, not a nonempty authorization string. The coordinator issues `{group, context, endpoint, node_uid, expires, available_mib, measured_at}`. No live receipt is generated or invented by this worker.

Before every apply/scale/exec/create/delete/restart, the guard validates private owner/modes/no symlink ancestors, exact `https://127.0.0.1:64120`, API TLS verification and explicit CA, kubeconfig context, no credential-exec plugins, exactly one node, node name AND hostname `talos-proof`, and the recorded node UID. Each mutation checks all proof namespace pods and Deployment/StatefulSet desired replicas, including unlabelled/Pending workloads, rejecting concurrent data or other media groups (except platform validation/Gateway). Activation additionally requires a <=120-second-old guest available-memory observation with room for app limit plus 192 MiB reserve. Fixture seeding includes its extra 64-MiB bound. The coordinator remains responsible for global arbitration and safe cleanup if a lease expires.

Private state is mode0700; credential, lease, CA and kubeconfig files must be owned by the current user with mode0600, outside the checkout, without path traversal or symlinks. Existing unsafe modes are rejected, not silently repaired. Credential output uses exclusive no-follow opens; existing bootstrap state is never silently rotated. macOS temporary-directory tests canonicalize the OS `/var` alias before supplying it, rather than weakening the production no-symlink rule.

Offline negative tests: `python3 tests/talos-proof-media-safety_test.py` (7 test methods, including multiple endpoint/node/lease/memory mutants). Real ephemeral-local TLS tests: `python3 tests/talos-proof-media-tls_test.py` (4 methods: trusted success, wrong CA rejection, wrong hostname rejection, cross-origin redirect rejection). These never contact the proof cluster. All 16 offline test methods currently pass.

## Approved explicit shared-data integration profile (offline implementation)

Parent approved `proof-media-pipeline` as a common media/download trust boundary. `kubernetes/apps/media/integration/` is a separate explicit Kustomization, **not included in the isolated root**. It declares seven zero-replica pipeline Deployments, one suspended Recyclarr CronJob, a single fresh `proof-local` `/data` PVC and distinct service-prefixed config PVCs/Secrets. No production volume or NAS is involved. `/data/torrents`, `/data/usenet`, `/data/media/{movies,tv}` and `/data/music` are on the same filesystem, permitting real atomic move/hardlink import without pretending independent PVCs share bytes. qbitwebui private SQLite/salt move to `/config`; its `/data` content view is read-only. Pod selectors preserve explicit per-service network boundaries inside this justified shared-storage trust group.

Integration routes use `pipeline-<service>.proof.invalid` to avoid ambiguous duplicate routes when isolated bases already exist. Isolated routes remain `<service>.proof.invalid`. Both use the trusted Gateway client and existing wildcard listener, with no production DNS.

The pipeline CLI only accepts enumerated pairs: `qbittorrent+qbitwebui`, `qbittorrent+radarr`, `qbittorrent+sonarr`, `qbittorrent+lidarr`, `sabnzbd+radarr`, `radarr+recyclarr`. Parent must review the selected live batch; **a group lease never starts all pipeline applications**. An unselected third application pod/controller inside the shared namespace is rejected. No live lease exists at this checkpoint.

```sh
# ONLY with coordinator-issued group=media-pipeline lease and live clearance:
python3 scripts/talos-proof-media-pipeline.py start --pair qbittorrent+qbitwebui --state "$STATE"
python3 tests/talos-proof-media-functional.py qbitwebui --group media-pipeline --pair qbittorrent+qbitwebui --base https://pipeline-qbitwebui.proof.invalid:18443 --ca /private/proofconfig/proof-gateway-ca.crt --state-dir "$STATE"
python3 scripts/talos-proof-media-pipeline.py restart --pair qbittorrent+qbitwebui --state "$STATE"
# Repeat functional command with --phase verify: existing instance must survive before config writes.
python3 scripts/talos-proof-media-pipeline.py stop --pair qbittorrent+qbitwebui --state "$STATE"
```

Experimental fresh-fixture integration memory limits: arrs 384 MiB, Prowlarr 256 MiB, qBittorrent/qbitwebui/SABnzbd/Recyclarr 192 MiB. These are bounded **unmeasured experiment ceilings**, not proven service profiles. Guard sums the selected pair's ceilings plus 192 MiB reserve against the <=120-second-old guest memory receipt; no reduction of isolated heavy-service limits was hidden to force admission. An OOM/failure must be retained and reported; live admission may still fail and does not authorize a VM/host change.

### Real nonempty Recyclarr preview implementation

Current v8.7.3 source confirms `replace_default: true` suppresses implicit official providers. The proof ConfigMap uses local empty *replacement provider indexes* plus one nonempty local `Proof-Synthetic-Title` custom format matching only `PROOF_FIXTURE`. Thus empty provider indexes remove upstream dependencies; they do **not** constitute the preview test. The test must demonstrate an actual planned Create for the nonempty local format. Default bootstrap seed references this local trash ID; pipeline private seed is constrained to the proof Radarr endpoint/key only.

With the separately leased `radarr+recyclarr` pair started, `talos-proof-media-pipeline.py preview-recyclarr --pair radarr+recyclarr --state "$STATE" --ca PRIVATE_CA` runs the actual suspended CronJob once with `sync --preview`, requires a completed bounded Job, confirms planned `Create` + exact synthetic name/ID in private captured output, and compares authenticated proof Radarr customformat state before/after for no mutation. Logs stay private; only sanitized checks/hash print. The Job is deleted afterward. No run has occurred yet, so no helper success is claimed.

### Remaining explicit gaps

These additions supply executable workflows, not live acceptance. Plex local-unclaimed scan/playback, Tautulli actual proof Plex history, Seerr offline request workflow, Kometa meaningful nonempty run, jellyplex watched divergence preview, actual arr manual import/hardlink and clean-PVC restoration still need implementation/live evidence. Public Kometa config source hard-requires TMDb initialization even for local Plex builders. No fake credential, empty config or blocked request will be treated as success. Offline fixture substitution or a narrowly scoped parent-reviewed strategy is still needed.
