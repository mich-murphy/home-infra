# Service-by-service proof readiness

Current status: 2026-11-13. **VM120 remains stopped; no production cutover is approved.**
Approved host maintenance completed on kernel7.0.14-24-pve with`kho=off`;
KHO output/CMA-free restriction removed and36production containers recovered.
[Maintenance evidence](evidence/talos-acceptance/kho-maintenance-completed-f7a723ea8a0d4640a2e586022501ce5a.json)
is not proof-workload or capacity acceptance. No proof startup/grant occurred.
The guard reported sustained host swap IO at07:18:58UTC and confirmed QEMU exit.
A later read-only admission failed before any new receipt or diagnostic invocation.
The VM is left off pending separate guarded-start authority and fresh verification.
The [KHO maintenance outcome](talos-proof-host-memory-remediation.md) verifies the
mitigation, not sole incident attribution or a representative soak. Historical
passes below remain evidence of their named windows, not current running state or
post-stop integrity. See [the stop evidence](evidence/talos-acceptance/guard-stop-before-diagnostic-634f727438df495397f768820517280c.json).

This table maps all
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
| `pocket-id` | Fresh SQLite identity provider | **Bounded pass34ef3547:** same retained user/passkey (no new registration), positive signed OIDC/claims/userinfo, redeemed-code replay400/no tokens, fresh-code wrongPKCE400/no tokens, unregistered redirect/no code/zero callbacks, all repeated after pod replacement and distinct fresh-PVC import. Exact audience membership and CA-derived leaf-SPKI; virtual—not physical—authenticator. No source-database migration/attestation claim. |
| `wallabag` | Wallabag + private MariaDB/Redis/fixture | **Bounded pass5622c159:** prior OAuth/article CRUD/export plus actual SVG fetch/local hash and native async importer/worker/API state. Article/image survive DB replacement/freshDB restore, but imagePVC RETAINED—not fresh image recovery. Transient500, one observation gap and limit-inclusive peaks retained; no capacity claim. Exact fixture FQDN uses SHA-pinned Graby SSRF adapter, not unchanged production extraction policy. |
| `wallabag-mariadb` | Bounded MariaDB profile | **Bounded pass:** clean logical restore and existing-user/article/state/hash verified through Wallabag HTTP. No production dataset/peak-capacity claim. |
| `wallabag-redis` | Private Redis | **Bounded pass5622c159:** actual native producer→pending depth1/API absent→real worker completion/authenticated content/read/star, repeated after Redis replacement using fresh processes. Not transparent reconnect, in-flight durability or exactly-once delivery. |
| `nextcloud` | Nextcloud + new HTML/config/files PVC | **Pending:** staged WebDAV/share/recovery code; no live acceptance. Version/trash/share/ACL and coordinated DB+files recovery must be checked, not just login. |
| `nextcloud-cron` | Suspended192MiB CronJob | **Pending native acceptance:** first initialization created11 stopped declarations but rejected empty env/metadata serialization before binding. A separate provenance-bound continuation then verified3empty read-only XFS mounts and retained BoundPVC/PV identities; helper removed/receipt released, all history preserved. Four declared backend NetworkPolicies installed without altering existing policies. A separate one-shot832MiB native run then failed read-only preflight with an unexported RuntimeException gate; no install/fixture/cron or functional pass. Helpers/backends stopped and receipt released. A separately authorized GET-only proof subsequently resolved PENDING by appending one clean event, preserving all81 prior files; it changed no Kubernetes resources and earned no functional pass. Backend startup may have written retained volumes. Public image review found a version.php Git-vs-packaged metadata mismatch; the old error remains unrecovered. The separate one-shot832MiB diagnostic then failed at the packaged-metadata hash gate (actual hash unavailable), before HTML/SQL/Redis checks. Helper captured and all stopped; one failed result plus clean,84oldfiles unchanged, receipt released. Backend rawPodstate was captured, but PG/Redis logs/cgroup counters were not; helperOOM0 must not be extrapolated. Diagnostic-only backend capture is now prepared with independent cleanup and restricted absolute-tool execution; anonymous pinned-image metadata establishes fixed tool/loader paths, not live execution. The fixed reader now requires TERM→KILL escalation; timeouts/unknown outcomes remain failures. Another trial requires fresh admission and separate authority. A confined ConfigMap-projection reader has15realPHP regressions within the522-method full gate; no live acceptance or new grant. Installation, token aging and cron remain unproved. No lastcron-only, binding-only or draft acceptance. |
| `nextcloud-office` | Collabora CODE, explicit finite security exception | **Partial/failed editing:** eight retained attempts (sevenTXT, one nativeODT). ActualODT loaded with edit permission and CheckFileInfo/GetFile/LOCK; token401/lock409 preserved bytes. Session warning blocked welcome close; no marker/acceptedPutFile/save/reopen/hostdeny. Dialog fixes and known-running alternate-host control prepared offline only. Inclusive peak768/768 with sampled OOM0 is not anonymous-use/headroom proof. No Office editing/full Nextcloud integration pass. |
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
| `pinchflat` | Isolated frontend + config/download PVCs | **Partial:** trusted-TLS profile CRUD, replacement and different-fresh-PVC read-before-write recovery passed. Optional RSS trial756385cc failed before provider proof. Later kernel correlation found3memcg OOMs in that pod: first2twoBEAM, third1BEAM plus yt-dlp/Python; RPC is not the sole established cause. One384+128+192=704 trial ran and was released: runtime erl_call hash/oneBEAM established, but no structured RPC result; stock downloader/Source/index/download not reached. Main peak384/max2028, sampled OOM/restarts0—not capacity acceptance. Offline MFA/result/shutdown fixes tested on workstation only; retained STOP still blocks activation. Existing CRUD recovery is not provider recovery. |
| `audiobookshelf` | Isolated library/config/metadata PVCs | **Bounded pass:** generated audiobook scan, exact stream/range bytes, progress/bookmark CRUD, restart and three fresh-PVC recovery checks. No production library/podcast/provider migration. |
| `qbittorrent` | Fresh private settings/data + BEP3 fixture | **Bounded pass7ac9f65c:** repaired route, actual5.3 auth204/preferences, real torrent transfer—1 handshake/2 pieces/32,044bytes—and completed on-disk SHA; fixture-off restart and different2PVC functional recovery. Initial401/API-response mismatch and progress1-without-file failure retained. Follow-upd65fce12 native browser login204/prefs200 and hostile same-site form with exact authenticated cookie denied/state unchanged passed. Six harness failures retained. Cookie lacked Secure behind TLS termination—separate security gap, not production auth parity. |
| `qbitwebui` | Fresh user/instance state and proof qbit dependency | **Pending:** executable exact-version workflow, no live connection/auth/queue-state proof yet. |
| `sabnzbd` | Fresh downloader + synthetic NNTP provider | **Bounded pass7ac9f65c:** real NNTP auth/body/yEnc32,044bytes, completed history and exact file SHA, fixture-off restart and different2PVC recovery. Hostname/API/lowercase AUTHINFO/output-name incompatibilities retained and corrected. Temporary provider removed, original directories restored. No real Usenet account/provider parity. |
| `radarr` | Isolated base + explicit shared `/data` integration profile | **Pending:** meaningful import/library/path/hardlink and recovery, not only root-folder/profile CRUD. |
| `sonarr` | Same bounded media-pipeline approach | **Pending:** episode workflow and real imported-file identity/persistence. |
| `lidarr` | Same bounded media-pipeline approach | **Pending:** music workflow and real imported-file identity/persistence. |
| `prowlarr` | Isolated indexer manager + local provider fixtures | **Pending:** actual test/query/result integration, not only empty configuration. |
| `jellyfin` | Fresh local server, no GPU/devices | **Security failure756385cc:** independent anonymous client received exact120214B video/SHA, not a health page. Real library/outsider created, but setup marker withheld; do not reset retained state. No decoded lifecycle/resume/outsider ACL/recovery pass. Pinned source review found undecorated stream actions/no fallback policy and no supported require-auth switch; LAN/proxy reclassification is not a fix. No bypass or configuration change. |
| `plex` | Fresh unclaimed server + authenticated local-only adapter | **Partial756385cc:** native agent discovery explicitly supplied xn; real scan/exactbytes/range/watched CRUD passed. Browser media401 with actual Origin/Referer blocks decoding; neither header stripped. Prior collision/restart5/400 retained. No decoded playback/history/recovery pass. Adapter key is **not** a native/cloud token; account/client parity unproved. |
| `tautulli` | Fresh monitor state against proof Plex | **Pending:** native API/empty-history preparation reached756385cc, but Plex browser failed before frames. No actual matching playback/history/statistics or recovery pass. |
| `seerr` | Fresh request manager + isolated media/provider dependencies | **Pending:** actual authenticated request lifecycle/dependency behavior. |
| `recyclarr` | Suspended bounded Job + local provider fixtures | **Pending:** nonempty planned custom-format changes and unchanged app state required; empty preview is not a pass. |
| `kometa` | Suspended bounded Job + no-forwarding TMDb contract fixture | **Pending:** meaningful nonempty collection behavior; mock-provider wiring/runtime not yet accepted. No genuine TMDb account claim. |
| `jellyplex-watched` | Suspended bounded sync Job | **Pending:** meaningful divergent-state fixture and observed intended sync/dry-run behavior, not empty libraries. |

Evidence: [media runbook](talos-proof-media.md),
[first live batch including failures](evidence/talos-media/first-live-batch.md),
[actual transfer/recovery chronology](evidence/talos-media/live-download-transfers.md),
[native browser pass and earlier player failures](evidence/talos-media/live-browser-player.md),
[later native security/resource failures and API milestone](evidence/talos-media/native-workflows-20261111.md), and
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
**capture only**, not Talos/etcd disaster-recovery acceptance. Parent independently
matched the original hash/mode/size and embedded SHA256 trailer, not engine restore.
The [same-VM recovery proposal](talos-proof-etcd-recovery-plan.md) is blocked on
explicit human exception to the existing separate-target restriction; no reset or
reboot authority exists.

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
