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
export TALOS_PROOF_MEDIA_LEASE=COORDINATOR_GRANTED_LEASE_ID
bash scripts/talos-proof-media-batch.sh start radarr "$STATE"
kubectl -n proof-radarr port-forward service/radarr 17878:7878  # separate terminal
python3 tests/talos-proof-media-functional.py radarr --base http://127.0.0.1:17878 --state-dir "$STATE"
bash scripts/talos-proof-media-batch.sh stop radarr "$STATE"
```

Harness refuses a second active media Deployment, applies only one bundle, privately applies its Secret, starts one replica and waits at most 300 seconds. A rollout pass is startup evidence only. On any timeout/failure run `stop`; PVCs remain for investigation/recovery. Do not rely on the environment variable as a distributed lock: the coordinator owns resource arbitration. Stop port-forwards after each test. No script automatically starts dependencies or runs helpers.

For Jellyfin, start its batch, seed generated audio into its fresh PVC, then test through loopback:

```sh
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" --seed jellyfin
kubectl -n proof-jellyfin port-forward service/jellyfin 18096:8096
python3 tests/talos-proof-media-functional.py jellyfin --base http://127.0.0.1:18096 --state-dir "$STATE" --fixture "$STATE/proof-tone.wav"
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
| downloads/qbitwebui → Deployment | Private fresh encryption key configured. Fresh admin login/API CRUD and proof-only qBittorrent connection not implemented; initial password potentially in logs. |
| downloads/sabnzbd → Deployment | API-key queue read, assert empty slots; refresh setting write/read/restore. Local NNTP fixture decode/checksum/recovery remains. |
| plex/plex → Deployment | Fresh unclaimed server and synthetic PVC; local token/library scan/stream/watch state test remains. Cloud claim/account is forbidden without explicit scoped parent authorization. |
| plex/tautulli → Deployment | Local Plex-only policy. Fresh setup + proof playback history/activity/settings test remains. |
| plex/seerr → Deployment | Proof Jellyfin/arr-only policy. Fresh setup/login/request lifecycle awaits safe metadata strategy; TMDb/cloud metadata blocked, not accepted as a dashboard pass. |
| plex/kometa → suspended CronJob | Native single run with read-only-config (protects config, **not** a Plex mutation dry-run). Empty library/invalid TMDb seed intentionally blocks meaningful run. Need proof library config, upstream CLI validation and approved metadata fixture strategy; do not run/claim success on empty config. |
| jellyfin/jellyfin → Deployment | Fresh setup/login + offline synthetic audio scan/exact stream/range seek/played flag test. Second-user ACL, resume, video/subtitles, restart/restore remain. No GPU. |
| jellyplex-watched → suspended CronJob | Real one-pass DRYRUN=True invocation against proof Plex/Jellyfin; fresh tokens still unset. Needs matching proof users/libraries and a deliberately divergent watched item; assert planned change plus no actual mutation. Exit zero alone is not acceptance. |
| audiobookshelf/audiobookshelf → Deployment | Synthetic WAV seed capability. Fresh admin setup/library scan/stream/bookmark/progress API test remains. |
| pinchflat/pinchflat → Deployment | Fresh config/download PVCs; all Internet blocked. Safe local media-profile CRUD/settings test remains; YouTube extraction not accepted without explicit experimental approval. |
| recyclarr/recyclarr → suspended CronJob | Real `sync --preview` with proof keys/endpoints. Upstream caches unavailable offline; needs version/entrypoint validation and nonempty local fixture formats/profiles plus before/after proof arr comparison. No empty-config/blocked fetch reported as success. |

Helper execution requires a separately reviewed **dependency batch** and parent allocation; the one-service harness intentionally cannot silently grant concurrent servers. No external Internet needs approved yet. Bring any required experimental allowance to parent before creating it; never allow private production networks.

## Evidence required before acceptance

Commit only sanitized summaries in `docs/evidence/talos-media/`: exact commands, image digests, UTC start/end, namespace/PVC UID, fixture checksum, test result, bounded resource measurements, restart and clean-PVC restore comparison, intentional auth/policy denials and unresolved limitations. Do not include Secret YAML, credentials, raw logs, session JSON or auth-bearing URLs. Current evidence contains only offline validation. Parent must review runtime test behavior and evidence before changing status.

## Integrated Gateway ingress (added for parent review)

All 13 UI services have an explicit HTTPRoute attached to Gateway `proof` in `proof-gateway`, host `<service>.proof.invalid`. Parent refs intentionally omit sectionName to attach to both existing HTTP/HTTPS wildcard listeners. There are no routes for helper CronJobs. Fresh proof namespaces carry the Gateway allowedRoutes label. No production DNS or public exposure is configured.

Policies allow the proof-gateway namespace on only each application HTTP port. Since Cilium Gateway proxies use the reserved `ingress` identity rather than ordinary namespaced pod identity, an additional narrowly selected CiliumNetworkPolicy allows `fromEntities: [ingress]` on the same exact target port. Parent networking review must verify this behavior and that only the dedicated proof Gateway exists; these identity allowances are not a claim of measured enforcement.

Once the platform is ready and a live lease is granted, test both route attachment (`Accepted`/`ResolvedRefs`) and functional traffic through the parent's SSH loopback forwards 18080→30080 and 18443→30443. For example, `curl --resolve radarr.proof.invalid:18443:127.0.0.1 --cacert /private/proof-ca.crt https://radarr.proof.invalid:18443/ping`; then run authenticated CRUD through that same trusted TLS route. Current API harness intentionally only accepts loopback HTTP and still requires an extension for trusted-CA hostname routing; do not treat port-forward success as integrated Gateway acceptance. No such live check has run.
