# Service-by-service proof readiness

Checkpoint: 2026-11-11. **No production cutover is approved.** This table maps all
36 discovered running containers to their proof implementation and actual evidence.
It is not a claim that36 replicas run concurrently: application defaults remain0,
CronJobs suspended, and live work uses serial, measured leases.

- **Bounded pass:** named synthetic workflows actually ran, within stated limits.
- **Partial:** some behavior passed, but a required capability remains unproved.
- **Pending/blocked:** declarations or test code are not functional evidence.

All historical-data migration, representative concurrency/soak, production
network/client parity and GPU parity remain unproved. Current3-GiB allocation
cannot host the complete source workload. See the [inventory](talos-proof-inventory.md)
for exact source versions and required tests, and [delivery record](talos-proof-delivery.md)
for current ownership and leases.

## Data and identity:16 source containers

| Source container | Proof replacement | Actual evidence / remaining gate |
|---|---|---|
| `couchdb` | Isolated single-node CouchDB + local PVC | **Bounded pass5421ecc7:** TLS auth denial, revision update/stale409, executable view, member allow/outsider read+write403, authenticated same-instance replication/deletion propagation, and distinct-PVC restore of actual security/design/docs/hashed proof-user records with permissions/view rechecked. CORS and representative historical datasets remain unproved. |
| `miniflux` | Miniflux + private PG + synthetic feed | **Bounded pass5421ecc7:** exact article, star/bookmark, read state and theme/page-size preferences persist through PG replacement and distinct fresh-PVC recovery. One initial app pod restarted2times with causes not captured; transient post-PG401 recovered1s. No production feed/account migration. |
| `miniflux-db` | Pinned PG18 | **Bounded pass:** logical dump to independent fresh PG PVC, then real expanded Miniflux validation. Historical scheduler failure and later2restart/401 caveats preserved. Latest PG peak139.512MiB; fixture63.992/64MiB predominantly file cache—no production capacity claim. |
| `pocket-id` | Fresh SQLite identity provider | **Bounded pass:** real browser WebAuthn registration/login, signed OIDC PKCE/JWKS/claims/userinfo, restart and fresh-PVC import with same user/passkey. Virtual—not physical—authenticator; browser exact leaf-SPKI pin. Audience-substring check fixed/tested; additional replay/wrong-verifier cases pending. |
| `wallabag` | Wallabag + private MariaDB/Redis/fixture | **Bounded pass:** real OAuth login, fixture URL extraction, read/update/archive/star/export/delete, DB restart and clean-PVC recovery. Image-fetch and async queue/reconnect coverage remain unproved. Exact fixture FQDN uses documented SHA-pinned Graby SSRF adapter; not unchanged production extraction policy. |
| `wallabag-mariadb` | Bounded MariaDB profile | **Bounded pass:** clean logical restore and existing-user/article/state/hash verified through Wallabag HTTP. No production dataset/peak-capacity claim. |
| `wallabag-redis` | Private Redis | **Partial:** running/PING/config observed. Async import-worker/queue integration and restart semantics unproved. |
| `nextcloud` | Nextcloud + new HTML/config/files PVC | **Pending:** staged WebDAV/share/recovery code; no live acceptance. Version/trash/share/ACL and coordinated DB+files recovery must be checked, not just login. |
| `nextcloud-cron` | Suspended bounded CronJob | **Pending:** same proof data/DB, explicitly leased one-shot only; no actual background-task result yet. |
| `nextcloud-office` | Collabora CODE, explicit finite security exception | **Partial/failed editing:** actual HTTPS/canvas/WSS and plain-text WOPI CheckFileInfo/GetFile/LOCK passed; bad-token401 and wrong-lock409 preserved file bytes. Six attempts did not prove typing/accepted PutFile/save/reopen. Latest welcome/mode selector corrected offline only; both renewed retries consumed and released.640MiB pressure and767.57/768MiB peak retained; no editing-capacity or full Nextcloud/richdocuments/Office-format pass. |
| `nextcloud-postgres` | Pinned PG18 + separate PVC | **Pending:** app-validating clean restore not executed for Nextcloud. |
| `nextcloud-redis` | Authenticated private Redis | **Pending:** lock contention/reconnect must be proved with Nextcloud, not inferred from Redis startup. |
| `immich` | Immich3 with corrected effective `/data` mount | **Pending:** upload/thumbnail/search/recovery stages prepared. Actual asset↔DB association, ACL/video/metadata and coordinated data recovery remain required. |
| `immich-ml` | CPU-only pinned model service | **Pending:** public model artifacts downloaded and hashed; real inference and useful image/text matching have not yet run. Health/ping is not inference. |
| `immich-postgres` | Pinned PG14 VectorChord/pgvectors image | **Pending:** extensions/indexes and genuine vector/app queries after clean restore. Generic PG18 is not a substitute. |
| `immich-redis` | Private Valkey | **Pending:** thumbnail/ML queue completion/reconnect; no production jobs replayed. |

Evidence: [data runbook](talos-proof-data.md),
[data results](evidence/talos-data/), and
[parent archive/PVC identity cross-check](evidence/talos-acceptance/data-archive-identity-check.json).
Pocket-ID proof follows current Compose2.19.2 while discovery recorded live2.19.1;
this fresh-state test is **not** an upgrade/migration rehearsal of the source database.

## Media and helpers:16 source containers

| Source container | Proof replacement | Actual evidence / remaining gate |
|---|---|---|
| `pinchflat` | Isolated frontend + config/download PVCs | **Partial:** trusted-TLS profile CRUD, replacement and different-fresh-PVC read-before-write recovery passed. Real provider/download workflow remains unproved. |
| `audiobookshelf` | Isolated library/config/metadata PVCs | **Bounded pass:** generated audiobook scan, exact stream/range bytes, progress/bookmark CRUD, restart and three fresh-PVC recovery checks. No production library/podcast/provider migration. |
| `qbittorrent` | Fresh private settings/data + BEP3 fixture | **Bounded pass7ac9f65c:** repaired route, actual5.3 auth204/preferences, real torrent transfer—1 handshake/2 pieces/32,044bytes—and completed on-disk SHA; fixture-off restart and different2PVC functional recovery. Initial401/API-response mismatch and progress1-without-file failure retained. Follow-upd65fce12 native browser login204/prefs200 and hostile same-site form with exact authenticated cookie denied/state unchanged passed. Six harness failures retained. Cookie lacked Secure behind TLS termination—separate security gap, not production auth parity. |
| `qbitwebui` | Fresh user/instance state and proof qbit dependency | **Pending:** executable exact-version workflow, no live connection/auth/queue-state proof yet. |
| `sabnzbd` | Fresh downloader + synthetic NNTP provider | **Bounded pass7ac9f65c:** real NNTP auth/body/yEnc32,044bytes, completed history and exact file SHA, fixture-off restart and different2PVC recovery. Hostname/API/lowercase AUTHINFO/output-name incompatibilities retained and corrected. Temporary provider removed, original directories restored. No real Usenet account/provider parity. |
| `radarr` | Isolated base + explicit shared `/data` integration profile | **Pending:** meaningful import/library/path/hardlink and recovery, not only root-folder/profile CRUD. |
| `sonarr` | Same bounded media-pipeline approach | **Pending:** episode workflow and real imported-file identity/persistence. |
| `lidarr` | Same bounded media-pipeline approach | **Pending:** music workflow and real imported-file identity/persistence. |
| `prowlarr` | Isolated indexer manager + local provider fixtures | **Pending:** actual test/query/result integration, not only empty configuration. |
| `jellyfin` | Fresh local server, no GPU/devices | **Pending:** generated media playback/seek/resume/subtitle and ACL/recovery; no GPU claim. |
| `plex` | Fresh unclaimed server + authenticated local-only adapter | **Blocked d65fce12:** adapter port collision/restart5 and forwarded-client-header incompatibility repaired; native library creation400 remains. No scan/decoded playback/timeline/history/recovery pass. Adapter key is **not** a cloud token/claim; native cloud/client parity unproved. |
| `tautulli` | Fresh monitor state against proof Plex | **Pending:** real playback/history/statistics integration and recovery. |
| `seerr` | Fresh request manager + isolated media/provider dependencies | **Pending:** actual authenticated request lifecycle/dependency behavior. |
| `recyclarr` | Suspended bounded Job + local provider fixtures | **Pending:** nonempty planned custom-format changes and unchanged app state required; empty preview is not a pass. |
| `kometa` | Suspended bounded Job + no-forwarding TMDb contract fixture | **Pending:** meaningful nonempty collection behavior; mock-provider wiring/runtime not yet accepted. No genuine TMDb account claim. |
| `jellyplex-watched` | Suspended bounded sync Job | **Pending:** meaningful divergent-state fixture and observed intended sync/dry-run behavior, not empty libraries. |

Evidence: [media runbook](talos-proof-media.md),
[first live batch including failures](evidence/talos-media/first-live-batch.md),
[actual transfer/recovery chronology](evidence/talos-media/live-download-transfers.md),
[native browser pass and player failures](evidence/talos-media/live-browser-player.md), and
[synthetic download protocol contract](evidence/talos-media/download-protocol-fixtures.md).
The first batch records a stale-Talos observation fallback, temporary helper overlap
and transient post-restore failures; those are not erased by later successes.
b06ae56f adds helper deletion waits and actual batch-runner negative tests proving
no apply/scale/rollout while a Job pod remains, plus an anonymous503-only readiness
gate (401/403 fail immediately). Parent reviewed these exact regressions before the
subsequent transfer window; its app/fixture/helper pods were all deleted.

## Infrastructure capabilities:4 source containers

| Source container | Replacement | Actual evidence / remaining gate |
|---|---|---|
| `traefik` | Cilium Gateway API + synthetic private-CA TLS | **Bounded pass:** real forwarded NodePort HTTP/TLS, routing/TLS negatives and persisted response. No production DNS/ACME/client/VLAN parity or certificate-renewal soak. |
| `portainer` | Declarative Kustomize + tightly scoped Flux | **Bounded pass3848e4cf:** real pinned Git reconciliation,1→drift→1→2→1, fixture identity denied Deployment creation/Secret reads; imageIDs pinned/restarts0, minimum transition kubelet930.3>512. Historical admission refusal and unexplained first apply failure preserved; unchanged retry passed. Cleanup verified. Later CRD Established-barrier correction has offline tests but no live retest. |
| `beszel` | Off-node metrics reader and local alert sink | **Bounded capabilities:** real resource collection, synthetic/observed-threshold alerts, independent saved-observation hash reload and marked-history retention safety passed; pruning used synthetic-age fixture, not production history. No deployed dashboard, continuously operated monitoring/pager/SLO or full Beszel UX replacement. |
| `docker-socket-proxy` | Omitted; Kubernetes controller/API/RBAC boundaries | **Design replacement:** no Docker socket mounted. Controller-specific effective RBAC and non-app admin boundary need their own evidence; omission alone is not a universal authorization proof. |

Platform: [network/storage evidence](evidence/talos-network-storage/live-summary.md),
[supervised lifecycle](talos-proof-host-lifecycle.md),
[parent post-fault checks](evidence/talos-acceptance/platform-after-faults.md),
[controlled actual-node TCP rejection](evidence/talos-platform/controlled-host-isolation-node-live.md).
The latter has same-endpoint positive controls and adjacent predicate/REJECT+2,
unchanged canonical policy and cleanup; it is not TRACE/full-five-tuple or
DNS/IPv6/exhaustive bypass acceptance. Parent independently verified the raw receipt,
plus6new archive hashes/modes and6distinct live PVC/PV/XFS paths:
[follow-up review](evidence/talos-acceptance/followup-archive-and-host-review.json).
Operations: [live evidence](evidence/talos-operations/README.md).
Generic off-node file restore passed; the12,443,680-byte private etcd snapshot is
**capture only**, not Talos/etcd disaster-recovery acceptance.

## Source protection and remaining delivery gate

A parent mid-run comparison found all36 original container IDs, imageIDs,
creation/start times, restart counts, health and running status unchanged:
[source comparison](evidence/talos-acceptance/source-midrun-comparison.json).
This is a bounded metadata observation, not a claim that ordinary application data
never changes. Final comparison is still required after the remaining work.

The dedicated VM is excluded from the inherited all-guests production NAS backup
job; only new VM120 membership changed, all existing guest settings remained intact.
No source data/credentials were migrated, no existing guest resized, no GPU moved,
and no production DNS/router cutover was performed. Continue resolving pending
criteria; **do not label the whole requested delivery complete from this table**.
