# Live Docker inventory and isolated Talos proof contract

## Scope and evidence

Discovery on **2026-11-11 UTC**, read-only on `docker-host`; see timestamped JSON in [evidence/talos-inventory](evidence/talos-inventory/). This is an inventory and proposed acceptance contract, **not evidence of migrated apps passing tests**. No source service, configuration, data or network was changed. No logs, database rows, environment values, secret files or credentials were collected. `docker exec` was used only for bounded `timeout 8 du -skx PATH` allocation scans; it creates a transient inspection process but does not intentionally write service data. Ordinary filesystem access may update atime.

Baseline: **36 running containers; 31 healthy, 5 without a Docker healthcheck** (kometa, nextcloud-cron, jellyplex-watched, portainer, recyclarr). Healthy is not a functional or consistency verdict. IDs, creation/start timestamps, restart counts, health, image references/IDs and mount sources are in `before-containers.json`; `after-containers.json` and `comparison.json` close this discovery window. Baseline includes recently started kometa/lidarr; subsequent changes must not automatically be attributed to proof work. Docker restart count does not capture replacement by a new container; compare IDs too.

### Reproducible exact commands

Run from the proof checkout only:

```sh
python3 docs/evidence/talos-inventory/capture.py before
python3 docs/evidence/talos-inventory/sizes.py
python3 docs/evidence/talos-inventory/capture.py after
```

Scripts contain exact SSH/Docker commands, inspect templates, bounds and sanitizer. Capture uses `ssh docker-host 'sudo -n docker ps -q'`, allowlisted `docker inspect --format ...`, and `docker stats --no-stream --format '{{json .}}'`. It does NOT dump full inspect, `.Config.Env`, healthcheck command/output or arbitrary labels. Size evidence contains each exact `sudo -n docker exec CONTAINER timeout 8 du -skx TARGET` command and exit status; maximum four scans concurrently. Eight-second timeout runs inside the container, avoiding an orphaned unbounded remote scan. Image evidence was obtained with:

```sh
ssh docker-host 'sudo -n docker image inspect --format '\''{"id":{{json .Id}},"digests":{{json .RepoDigests}},"created":{{json .Created}},"size_bytes":{{.Size}}}'\'' IMAGE_IDS'
```

`IMAGE_IDS` is the sorted unique `image_id` set from baseline. `images.json` records image IDs, registry digests, creation and uncompressed sizes. The image digest in `.Config.Image` is the deployment reference; RepoDigests/image IDs preserve actual local resolution, including floating tags. `compose-summary.json` extracts only image, dependencies, mounts and devices from `docker/*/compose.yml`; no environment/secret values. Historical design read with `git show origin/feature/talos-kubernetes:docs/k8s-migration-handover.md`; never applied. An initial inspect template failed on containers without Health; corrected capture uses `index .State "Health"`. Failed attempt changed nothing and captured no usable baseline.

## Architecture and source-of-truth differences

- **Cloud/files:** Nextcloud web + cron share HTML/config and file data; PostgreSQL 18 stores metadata; Redis locks/cache; Collabora CODE provides WOPI editing. This is **Nextcloud**, not historical ownCloud. `docker/nextcloud/README.md` documents the ownCloud migration and a Docker-host-only TrueNAS export. Do not broaden that export or mount it writable in proof.
- **Photos:** Immich server + PostgreSQL 14 with VectorChord/pgvectors + Valkey + ML model cache. Server currently has `/dev/dri` in Compose; no GPU may be reassigned. CPU functional proof is not GPU/transcoding performance acceptance.
- **Media:** Plex/Jellyfin share read-only media/music; audiobookshelf has writable audiobook source; Radarr/Sonarr/Lidarr share writable media/download paths; Prowlarr configures indexers; qBittorrent/SABnzbd execute downloads; qbitwebui shares torrent files. Seerr, Tautulli, Kometa, Recyclarr, jellyplex-watched and Pinchflat are active integration/automation paths, not inert dashboards.
- **Identity/tools:** Pocket-ID is the OIDC issuer and passkey store. CouchDB, Miniflux/Postgres, Wallabag/MariaDB/Redis have independent state and acceptance requirements. No running linkding/renovate container was found; old branch declarations do not make them current requirements.
- **Infrastructure:** Traefik reads socket-proxy and issues production DNS-01 certs; Portainer administers Docker; Beszel collects monitoring. Replace capabilities, not necessarily these containers: isolated ingress/TLS, declarative deployment/reconciliation, cluster metrics/alerts, storage and recovery. Never expose the production Docker socket to a proof workload (read-only bind of a socket does not make its API read-only).

Current repo differs from running source: Traefik repo v3.7.17 vs live v3.7.16; Pocket-ID repo v2.19.2 vs live v2.19.1; Portainer `lts` digest differs; jellyplex-watched `main` digest differs. Pin **live** digests for a fidelity test and test upgrades separately. Full references are recorded in evidence. Historical branch's 12-GiB node, stopping Docker, GPU movement, IP/LB ranges, production DNS, ACME credentials and backup destinations are unsafe to reuse. Its LocalPV + static NFS + logical DB backup approach is direction only; its old app counts and absent modern Nextcloud/Immich assumptions are stale.

## Current memory and all running services

Docker stats baseline sum is **3,609.792 MiB = 3.525 GiB**, not host RSS or peak. Linux Docker CLI discounts inactive file cache; workload/transcode/ML/editor peaks can be much larger. Limits near 9.707 GiB mean effectively host capacity, not a usable allocation plan. Only Kometa and qBittorrent have 1-GiB explicit memory limits in baseline.

Table below: `V(name)` means `/var/lib/docker/volumes/name/_data`; sizes are allocated MiB rounded from KiB scans, not logical file length. Repeated shared paths must not be summed. Every full image digest and every host/container mount mapping is in baseline JSON; short digests in this table identify the exact recorded deployment, not substitute pins.

| Container | Live version; digest prefix | Current MiB | Persistent locations (allocated MiB) |
|---|---|---:|---|
| kometa | `kometa:nightly`; `c89cd9404aaf` | 89.35 | `V(kometa-data)` → `/config` (RW; 910.3 MiB) |
| lidarr | `lidarr:3.1.6.5079-ls48`; `a91ef0642c15` | 135.9 | `V(lidarr-data)` → `/config` (RW; 2,927.1 MiB)<br>`/mnt/data` → `/data` (RW; 4,218,674.4 MiB)<br>`/mnt/music` → `/music` (RW; 298,149.8 MiB) |
| nextcloud-cron | `nextcloud:35.0.2-apache`; `786c102155d2` | 76.03 | `V(nextcloud-html)` → `/var/www/html` (RW; 926.4 MiB)<br>`/mnt/nextcloud/nextcloud-data` → `/var/www/html/data` (RW; 1,511.8 MiB) |
| nextcloud | `nextcloud:35.0.2-apache`; `786c102155d2` | 64.66 | `V(nextcloud-html)` → `/var/www/html` (RW; 926.4 MiB)<br>`/mnt/nextcloud/nextcloud-data` → `/var/www/html/data` (RW; 1,511.8 MiB) |
| miniflux | `miniflux:2.3.5`; `8fd6c3c434ec` | 22.8 | No persistent mounts |
| radarr | `radarr:6.4.4.10685-ls326`; `51a9ac2a9eb4` | 218.7 | `V(radarr-data)` → `/config` (RW; 523.8 MiB)<br>`/mnt/data` → `/data` (RW; 4,218,674.4 MiB) |
| immich | `immich-server:v3.3.6`; `e1981983b1c1` | 534.1 | `V(f5b26395d8a0b6f3b4990b4265bc25719a38ce0a9ac47933e6069118641cd954)` → `/data` (RW; 0.0 MiB)<br>`/etc/localtime` → `/etc/localtime` (RO; not scanned)<br>`/mnt/photos` → `/usr/src/app/upload` (RW; UNKNOWN) |
| immich-ml | `immich-machine-learning:v3.3.6`; `14367bfb374b` | 55.41 | `V(immich-ml-cache)` → `/cache` (RW; 1,708.0 MiB) |
| tautulli | `tautulli:v2.18.2-ls251`; `7ca2e2627127` | 89.32 | `V(tautulli-data)` → `/config` (RW; 424.5 MiB) |
| sabnzbd | `sabnzbd:5.1.3-ls280`; `693c208f697d` | 80.79 | `V(sabnzbd-data)` → `/config` (RW; 260.6 MiB)<br>`/mnt/data/usenet` → `/data/usenet` (RW; 59,277.3 MiB) |
| nextcloud-office | `code:26.04.6.1.1`; `95f29f1c0a17` | 41.81 | No persistent mounts |
| nextcloud-redis | `redis:8.10.3`; `1f88291b4c57` | 13.5 | `V(nextcloud-cache)` → `/data` (RW; 10.7 MiB) |
| wallabag-redis | `redis:8.10.3-alpine`; `71885d8cc6e4` | 6.059 | No persistent mounts |
| sonarr | `sonarr:4.0.20.3014-ls329`; `44b06045a98b` | 181.2 | `V(sonarr-data)` → `/config` (RW; 357.4 MiB)<br>`/mnt/data` → `/data` (RW; 4,218,674.4 MiB) |
| nextcloud-postgres | `postgres:18.6`; `e3d24f6906d0` | 43.14 | `V(nextcloud-db)` → `/var/lib/postgresql` (RW; 96.9 MiB) |
| miniflux-db | `postgres:18`; `e3d24f6906d0` | 58.21 | `V(miniflux-db)` → `/var/lib/postgresql` (RW; 97.7 MiB) |
| couchdb | `couchdb:3.5.3`; `907eab5b7e55` | 48.66 | `V(couchdb-data)` → `/opt/couchdb/data` (RW; 712.6 MiB) |
| wallabag | `wallabag:2.6.15.1`; `2e9d9fbbba6f` | 36.65 | `V(wallabag-data)` → `/var/www/wallabag/web/assets/images` (RW; 0.0 MiB) |
| wallabag-mariadb | `mariadb:13.0.2`; `f4054da26e3a` | 18.27 | `V(wallabag-db)` → `/var/lib/mysql` (RW; 175.3 MiB) |
| seerr | `seerr:v3.5.1`; `d8fab675b55a` | 170.5 | `V(seerr-data)` → `/app/config` (RW; 5.6 MiB) |
| jellyfin | `jellyfin:12.4`; `fea863d0cd9e` | 434.4 | `V(jellyfin-cache)` → `/cache` (RW; 343.7 MiB)<br>`V(jellyfin-data)` → `/config` (RW; 5,070.3 MiB)<br>`/mnt/data/media` → `/data/media` (RO; 3,724,190.0 MiB)<br>`/mnt/music` → `/data/music` (RO; 298,149.8 MiB) |
| jellyplex-watched | `jellyplex-watched:main`; `e3b33047846c` | 59.07 | `V(jellyplex-watched-data)` → `/data` (RW; 0.4 MiB) |
| pocket-id | `pocket-id:v2.19.1`; `f085157f0b6e` | 76.27 | `V(pocketid-data)` → `/app/data` (RW; 52.5 MiB) |
| traefik | `traefik:v3.7.16`; `1336e85aaed2` | 141.9 | `V(traefik-data)` → `/letsencrypt` (RW; 0.0 MiB)<br>`/srv/init/traefik-dynamic.yml` → `/traefik-dynamic.yml` (RO; not scanned)<br>`/srv/init/traefik.yml` → `/traefik.yml` (RO; not scanned) |
| plex | `pms-docker:1.43.5.11079-b3b13e506`; `6d778d41daae` | 106.2 | `V(plex-data)` → `/config` (RW; 7,294.8 MiB)<br>`V(plex-transcode)` → `/transcode` (RW; 0.0 MiB)<br>`/mnt/data/media` → `/data/media` (RO; 3,724,190.0 MiB)<br>`/mnt/music` → `/data/music` (RO; 298,149.8 MiB) |
| beszel | `beszel:0.21.1`; `8514a69d9bbb` | 45.79 | `V(beszel-data)` → `/beszel_data` (RW; UNKNOWN) |
| qbittorrent | `qbittorrent:5.3.0_v2.1.2-ls485`; `75ecbb1c89ab` | 66.3 | `V(qbittorrent-data)` → `/config` (RW; 47.6 MiB)<br>`/mnt/data/torrents` → `/data/torrents` (RW; 883,260.1 MiB) |
| portainer | `portainer-ee:lts`; `0cd22f754ac5` | 131 | `V(portainer-data)` → `/data` (RW; UNKNOWN)<br>`/run` → `/var/run` (RO; not scanned) |
| docker-socket-proxy | `docker-socket-proxy:v0.5.0`; `1f5038b54f06` | 12.02 | `/run` → `/host-run` (RO; not scanned) |
| prowlarr | `prowlarr:2.6.5.5623-ls165`; `b3b00047ed20` | 151.6 | `V(prowlarr-data)` → `/config` (RW; 142.1 MiB) |
| audiobookshelf | `audiobookshelf:2.37.2`; `b897c33f0597` | 46.05 | `V(audiobookshelf-data)` → `/config` (RW; 623.7 MiB)<br>`V(audiobookshelf-metadata)` → `/metadata` (RW; 637.0 MiB)<br>`/mnt/audiobooks` → `/data/audiobooks` (RW; 29,812.4 MiB) |
| recyclarr | `recyclarr:8.7.3`; `9c6c74d52cfc` | 8.543 | `V(recyclarr-data)` → `/config` (RW; 80.8 MiB)<br>`/srv/portainer/portainer-compose-unpacker/stacks/recyclarr/home-infra/docker/recyclarr/custom-formats` → `/config/custom-formats` (RO; 0.0 MiB)<br>`/srv/portainer/portainer-compose-unpacker/stacks/recyclarr/home-infra/docker/recyclarr/recyclarr.yml` → `/config/recyclarr.yml` (RO; not scanned)<br>`/srv/portainer/portainer-compose-unpacker/stacks/recyclarr/home-infra/docker/recyclarr/settings.yml` → `/config/settings.yml` (RO; not scanned) |
| pinchflat | `pinchflat:v2025.6.6`; `4e975edf58f0` | 137.7 | `V(pinchflat-data)` → `/config` (RW; 367.2 MiB)<br>`/mnt/data/media/youtube` → `/downloads` (RW; 227,800.2 MiB) |
| qbitwebui | `qbitwebui:2.44.2`; `75907e7013de` | 44.3 | `V(qbitwebui-data)` → `/data` (RW; 8.6 MiB)<br>`/mnt/data/torrents` → `/data/torrents` (RW; 883,260.1 MiB) |
| immich-redis | `valkey:9.0.1`; `546304417fea` | 12.99 | No persistent mounts |
| immich-postgres | `postgres:14-vectorchord0.4.3-pgvectors0.2.0`; `bcf63357191b` | 150.6 | `/var/lib/immich-postgres` → `/var/lib/postgresql/data` (RW; 475.3 MiB) |

## Data size interpretation and correctness hazards

- Shared `/mnt/data`: **4,119.8 GiB** allocated; `/mnt/data/media`: **3,637.0 GiB**; torrents **862.6 GiB**; usenet **57.9 GiB**; YouTube **222.5 GiB**. These are overlapping views, not additive capacity requirements. NFS `du` allocation can also reflect server accounting/hardlinks; do not infer exclusive physical bytes or transfer time.
- `/mnt/music`: **291.2 GiB**; audiobooks **29.1 GiB**; Nextcloud files **1.48 GiB**. Bulk full copies are unnecessary and inappropriate for proof; use representative synthetic fixtures and explicit bounded subsets only after authorization.
- Photo scan hit the hard 8-second deadline: **UNKNOWN**, not empty. Beszel/Portainer scans failed because their images lack `timeout`; sizes remain **UNKNOWN** rather than installing tools or mounting volumes elsewhere. `/run`, localtime and individual configuration binds were intentionally not scanned. No file-content scans or unbounded retries.
- **Immich ambiguity:** live server has an anonymous volume at `/data` (4 KiB allocation) in addition to `/mnt/photos -> /usr/src/app/upload`. v3 path semantics must be confirmed against effective nonsecret application storage configuration and a known asset through an authorized operator; no environment values were retrieved here. A healthy server and a large old photo mount do not establish that new uploads/backups use the expected location. Preserve/resolve both mappings before any migration. ML cache is about **1.67 GiB**, not user photos; pre-stage exact model files offline or use a proof-only controlled download, then test actual inference.
- Nextcloud HTML (~927 MiB), PostgreSQL (~97 MiB), and primary files (~1,512 MiB) form one logical state. HTML contains configuration/app code/secrets; DB+files must agree on file IDs, versions, shares and encryption keys. Redis locks/cache are not a reason to migrate stale locks. Cron must remain disabled until proof URLs/notifications/external storage are sanitized.
- Database directory sizes are **not valid backup artifacts**. Live `cp`, `docker cp`, tar or rsync of Postgres/MariaDB directories cannot claim transaction consistency. Use owner-approved logical dumps/restores or coordinated crash-consistent snapshots plus documented recovery. Such backup execution was not performed because this task is read-only discovery; dump files and DB operations need separate approval.
- SQLite applications may use WAL; copying only `.db` loses transactions. An authorized online-backup API or coordinated filesystem snapshot covering DB/WAL/SHM is needed. Raw mutable files copied at different times are not a proven recovery point. CouchDB data is append-only but shards, security metadata, design docs and replication checkpoints require application-aware backup/recovery; no arbitrary live-directory copy claim.
- Media apps store absolute paths, ownership, completed/incomplete jobs, hardlink assumptions and API tokens. Preserve proof-local path topology and UID/GID permissions, but never preserve runnable production jobs or tokens. Whole-tree copy can include backups, logs, thumbnails and secrets far beyond the database.

## Isolation and fixture admission gate (before starting any copied app)

1. Dedicated proof storage only; **no writable production NFS/PVC/hostPath**, no Docker socket, no GPU, no production DNS or DHCP changes. Prefer no production storage mount at all; read-only NFS still exposes private content and can cause heavy scans.
2. Default-deny egress enforced and demonstrated at the node/network boundary as well as pod policy. Deny production LAN, management VLANs, NAS, OIDC endpoints and Internet; permit only proof DNS and exact proof peers. Block IPv6, alternate DNS and direct-IP escape paths too. CNI-only policy may not cover hostNetwork/controller/node traffic; prohibit hostNetwork and test boundary denial before secret-bearing copies are introduced. DNS resolution is not permission to connect. Record denial counters/tests without contacting real production APIs.
3. Fresh database/API/admin/OIDC signing/encryption credentials, proof issuer/redirect URLs, local certificates or private CA; **no Cloudflare/ACME production DNS credentials**, Plex claim token/account, SMTP, push, webhook, indexer, Usenet, tracker, YouTube cookie or notification credentials. Do not commit copied configs or dump contents. Store any authorized private copy outside Git with 0700/0600 permissions.
4. Quarantine offline copies; redact/rewrite integration endpoints and tokens before startup; deny egress remains mandatory because sanitization can miss encrypted DB fields, queued jobs and newly enabled defaults. Fresh encryption keys cannot decrypt old app credentials: explicitly reset/recreate integrations, do not silently claim preserved functionality. Production OIDC clients/passkeys/sessions are not proof users.
5. Start schedulers, crawlers and workers suspended. Empty queues/torrents/RSS feeds/replication jobs and disable telemetry, auto updates, scheduled searches and notifications. Enable one proof-only task at a time against mocks or isolated peers. Clone DB IDs or Plex server machine identifiers can register duplicate clients or mutate cloud state even if media files are read-only.
6. Fixture manifest: deterministic tiny text/PDF/ODT, several generated JPEGs with known EXIF/time/location and a visible object/face where licensed, a short locally generated video/audio chapter/subtitle, fixture RSS/article server, a local torrent seed/tracker and optional NNTP stub. Record checksums, expected counts, source/license and expected results. Do not use real family photos or feed a real external URL merely for realism.
7. A private authorized read-only subset can improve restore/path compatibility confidence, but must have explicit scope, consistent capture point, sanitization record, isolated staging path and deletion policy. No subset copied in this discovery. Synthetic initialization proves software workflows, **not historical production-data restore**.

## Per-service functional acceptance (all tests on isolated proof only)

Common gate for every stateful row: create known fixture; read back with expected value/checksum; record IDs/counts; restart pod; confirm durable state; restore to a **different clean PVC** and repeat. Record exact image/PVC IDs, commands, start/end UTC and results. Readiness alone is insufficient. Negative cross-tenant/auth checks matter. The following are **planned, not executed**:

| Service(s) | Required functional test beyond readiness | Dangerous copied state / safe execution |
|---|---|---|
| Nextcloud | Fresh proof login, WebDAV upload/download checksum, rename/delete/recover, version restore, share to second proof user, deny third user; compare DB file records with files; restart/restore preserves version/share | Sanitize trusted domains/proxies, overwrite URLs, OIDC/SMTP/webhooks/external storage, federation, app credentials; DB+HTML+files coordinated |
| nextcloud-cron | Enable only after sanitization; run one proof background task, observe completion and last-run progression without duplicate jobs | Shares all Nextcloud state; queued notifications can call production |
| nextcloud-office | Browser opens proof ODT via Nextcloud WOPI, edit/save, close/reopen and verify changed bytes/version; reject wrong host/token; survive restart | Use proof WOPI allowlist/public URL, never production Collabora URLs; discovery XML alone is not acceptance |
| nextcloud-postgres | Restore a logical dump; verify schema/version and fixture user/file/share rows via app; DB restart/recovery | Match PG18 layout/major; no live file copy |
| nextcloud-redis | Two proof requests contend for file lock, no corrupt concurrent edit; release/recover lock after restart; auth required | Fresh cache/lock state and password; do not restore stale production locks |
| Immich | Upload fixture image/video, checksum download, generate thumbnail, timeline/EXIF correctness, album/share ACL and video playback, restart and restore asset/DB association | Disable external libraries/OIDC/SMTP/webhooks/jobs until rewritten; resolve actual upload path; no GPU claim |
| immich-ml | Actual inference on known image; smart-search query returns expected fixture; measure cold/warm peak and model-cache persistence | Health endpoint is not model inference. No production cache fetch credentials or uncontrolled downloads |
| immich-postgres | Preserve required VectorChord/pgvectors extensions and indexes; restore app fixture, execute vector search and app queries | Match pinned PG14 extension image; PG18 generic image is not a replacement |
| immich-redis | Isolated thumbnail/ML queue completes once, prove reconnect after restart and no silently lost required work | Fresh queue; do not replay production jobs |
| Plex | Scan generated media, local authenticated direct playback/seek/subtitles, persist watch progress and library on restart | Fresh machine ID/token; no production account claim or cloud registration. GPU transcode explicitly deferred |
| Jellyfin | Same local playback/seek/subtitle/resume plus second-user ACL; optional CPU transcode measured separately | Disable copied plugins/webhooks/OIDC/metadata fetchers; GPU deferred |
| audiobookshelf | Scan synthetic audiobook, stream chapter, persist progress/bookmark and cover metadata across restart/restore | Downloaded podcasts/metadata providers disabled; production mount is writable, proof fixture must not be |
| Radarr | Add synthetic movie unmonitored, import fixture from local completed-download path, verify rename/checksum/root ownership and API result | Disable search/RSS/indexers/download clients; only proof endpoints |
| Sonarr | Same for synthetic series/episode, verify episode matching and import state | Same; avoid automatic missing-episode searches |
| Lidarr | Same for a fixture album/track, verify matching/import/path mapping | Same; music root is separately mounted |
| Prowlarr | Query deterministic mock indexer; verify result and sync to proof Arr instance only | Delete/recreate indexer credentials and application endpoints; no production indexer queries |
| qbittorrent | Transfer tiny fixture from local isolated seed/tracker, hash-check completed file, prove path/pause/restart persistence | No copied torrents/resume jobs, public DHT/PeX/LSD/trackers/NAT mapping; paused flags alone insufficient |
| qbitwebui | Fresh login, connect to proof qBittorrent API, list/pause/resume local fixture and download intended fixture only; deny path traversal | Replace encrypted connection store/key; never connect to production qBittorrent |
| sabnzbd | Validate local NZB/queue and path mapping; with isolated NNTP fixture, complete tiny payload/checksum and persist history | No real Usenet credentials or copied queue. If no local NNTP stub, mark actual transfer unproven |
| Seerr | Proof user submits request, approval creates only proof Arr object; verify permission boundary and duplicate handling | Fresh Plex/Jellyfin/Arr endpoints; no prod notifications or download clients |
| Tautulli | Observe one proof Plex playback and persisted history; notifications go to mock sink | Fresh Plex token/server ID; no real webhook/email notifications |
| Kometa | One explicit execution against proof Plex builds/updates fixture collection and is idempotent on second run | Do not start copied scheduled config; replace Plex/TMDb/Trakt/other API tokens with mocks; external metadata compatibility can remain deferred |
| Recyclarr | One explicit sync to proof Arr updates known custom-format/quality setting; second sync no unexpected drift | Fresh API keys/URLs; no scheduled execution or live upstream downloads |
| jellyplex-watched | Mark fixture watched in proof Plex, sync to proof Jellyfin; assert only mapped proof user/library changes, reverse direction if enabled, idempotency | Two production write APIs despite read-only media. Fresh endpoints/tokens/mappings; DRYRUN is not isolation |
| Pinchflat | Parse deterministic local/mock source, enqueue controlled fixture and verify output/metadata/restart | Real YouTube compatibility cannot be asserted from mock; copied subscriptions/cookies can trigger large real downloads |
| Pocket-ID | Fresh passkey registration/login on dedicated secure proof origin; OIDC authorization-code + PKCE flow to test client, validate issuer/JWKS/audience/nonce, deny wrong redirect; restore and login again | Fresh issuer/signing/client/session keys and proof users; no production OIDC clients or passkeys; virtual authenticator acceptable if documented |
| CouchDB | Create proof DB/doc, update with revision, reject stale revision conflict, query design view, exercise authorized isolated replication, restore docs/security | Remove production replication targets/checkpoints and credentials; test tenant denial |
| Miniflux | Fetch local fixture RSS, exact article count/content, mark read/star, persist preferences and restore via PG | Remove copied subscriptions/integrations, OIDC and SMTP; no internet polling |
| miniflux-db | App reads restored feed/read state after DB restart; schema migrations only on proof copy | Logical PG18 restore, no raw directory copy |
| Wallabag | Import article from local fixture HTTP origin, verify extracted title/body/image and API export/read state, restart and restore | Sanitize API clients/feeds/SMTP and user external integrations; no arbitrary URL fetching (SSRF risk) |
| wallabag-mariadb | Logical restore then verify app article/user associations and charset through app | Match MariaDB version; data directory copy while live not accepted |
| wallabag-redis | Execute proof queue/cache operation and verify reconnect/retry without duplicate article | Fresh empty queue, no production job replay |
| Traefik replacement | Dedicated proof hostname/TLS chain, intended route/backend, large WebDAV upload and Collabora WebSocket; reject unknown hosts; negative isolation checks | No production DNS-01 credentials; no reuse of live LB addresses |
| Portainer replacement | Declarative apply/reconcile changes a harmless fixture, drift correction and rollback tested; secret handling/RBAC | Flux is an option, not evidence by itself; never attach source Docker socket/Portainer API |
| socket-proxy replacement | Demonstrate no source Docker API dependency and management boundary denied from proof pod | Usually omit entirely; do not reproduce access to `/run` |
| Beszel replacement | Observe per-pod/node memory/restarts/storage, trigger proof-only test alert to local sink, verify persistence/retention | Old branch 0.8–1.2 GiB monitoring stack exceeds small proof budget; lightweight metrics may be staged |
| Storage/backup replacement | PVC checksum survives pod/node restart; explicit clean-PVC restore succeeds; prove production export cannot be written | LocalPV single-node durability is not HA; backup on same node/disk is not disaster recovery |

## Honest resource and staged-delivery gates

Measured app idle lower bound is **3.525 GiB**. At 4 GiB that leaves only **486 MiB** for Talos, etcd, API server, scheduler/controller, kubelet/container runtime, CNI/DNS, ingress and storage; at 3 GiB apps alone exceed RAM by **538 MiB**. Even a planning-only **1–1.5 GiB** base reserve implies **4.53–5.03 GiB before workload peaks**, ML, office editing, database recovery or metrics. This is a lower-bound infeasibility argument, not a recommended full-production size. Historical 12-GiB migration design is not authorization to allocate it.

Measure actual fresh-node baseline before choosing any stage. Require at least 20–25% node memory headroom under the tested workload; record node available/working-set, per-container peaks and OOM/restarts, not just configured limits or one idle stats sample. Avoid forcing every pod into tiny limits to obtain misleading green readiness.

**Parent decision:** approved node is **3 GiB**. Use **fresh data only**; no production copies are needed or authorized for these functional stages. Production-data migration fidelity/restore is a separate unpassed gate. At most three app workers may execute concurrently, but worker concurrency does not authorize concurrent app batches beyond measured capacity.

Suggested staged batches (one at a time, release previous app memory; retain dedicated PVCs):

1. **Platform + identity/tools:** route/TLS/storage/reconcile/backup, Pocket-ID + OIDC test client; then CouchDB, Miniflux and Wallabag individually. Measured Docker sums: Pocket-ID 76 MiB; CouchDB 49 MiB; Miniflux+DB 81 MiB; Wallabag+DB+Redis 61 MiB. Fresh stack/migration peaks differ.
2. **Nextcloud complete functional group:** web+cron+PG+Redis+Collabora measured **239 MiB idle** but editor/PHP/cron bursts not represented. Allocate headroom based on a real upload/editor session and controlled cron; retain complete group together for WOPI testing.
3. **Immich complete group:** server+PG+Valkey+ML measured **753 MiB idle**; cold model inference/index generation can dominate memory. Pre-stage models, tiny fixture batch, single worker where supported; record any disabled feature/concurrency. If peak cannot fit, mark ML functional gate blocked rather than omit it and call Immich complete.
4. **Media workflow:** proof Arr/download pair with mock indexer/local payload, then separate player tests; Plex+Jellyfin+jellyplex-watched must overlap for sync (measured **600 MiB** together). Run Tautulli/Seerr/Kometa against the applicable player in separate controlled sub-stages. Player scan/transcode peaks are not idle demand. No production GPU equivalence claimed.
5. **Recovery/isolation replay:** restart/restore each complete dependency group and repeat fixtures; leave all others stopped. Infrastructure remains active and measured throughout. Collect source before/after again around the actual proof, not just this inventory.

A **full concurrent gate remains blocked by capacity** unless parent obtains dedicated safe resources and measures every group together under representative activity. Staged success proves only those explicitly tested dependency edges. It cannot establish whole-stack contention, background scheduler overlap, full-data migration time, production GPU performance, production passkey continuity, HA or disaster recovery. Migration-readiness matrix must retain those as unproven/blocked, and distinguish synthetic functional proof from sanitized-copy restore and production cutover readiness.
