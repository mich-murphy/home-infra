# Docker Hardening

Roll out container hardening one stack at a time. Do not apply capability drops,
read-only filesystems, or user changes globally without validating each service.

## Capability Drop Rollout

Start with low-risk app containers:

- Single application container
- No database/cache sidecar in the same service
- No `/var/run/docker.sock` mount
- No GPU device passthrough
- No privileged host networking
- Internal listener on port 1024 or higher
- No root entrypoint that performs ownership, user, or database init

Applied capability drops:

- `docker/beszel/compose.yml`: `cap_drop: [ALL]`
- `docker/couchdb/compose.yml`: `cap_drop: [ALL]`
- `docker/downloads/compose.yml`: `qbitwebui` only
- `docker/immich/compose.yml`: `immich-ml` only
- `docker/init/compose.yml`: `pocket-id` only
- `docker/miniflux/compose.yml`: `miniflux` only
- `docker/pinchflat/compose.yml`: `cap_drop: [ALL]`
- `docker/plex/compose.yml`: `seerr` and `kometa` only

These changes intentionally exclude Docker socket controllers, database/cache
services, LinuxServer.io images, and GPU-backed media services.

## Research Baseline

Docker Compose supports `cap_drop` and `cap_add`; Docker's default container
capability set still includes capabilities such as `CHOWN`, `SETUID`, `SETGID`,
`NET_BIND_SERVICE`, and others. A hardened rollout should therefore distinguish
"the app does not need a capability" from "the image entrypoint does not need a
capability during startup."

Relevant upstream notes:

- Docker Compose services reference: https://docs.docker.com/reference/compose-file/services/
- Docker runtime capabilities reference: https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities
- LinuxServer.io images use `PUID`/`PGID`; their docs recommend those variables for normal rootful operation: https://docs.linuxserver.io/general/understanding-puid-and-pgid/
- LinuxServer.io container init uses s6 and runs init scripts for users, folders, permissions, mods, and custom files: https://www.linuxserver.io/blog/how-is-container-formed
- LinuxServer.io non-root operation is supported on a tested-image basis and has caveats around `/run`, Docker Mods, custom scripts/services, and `no-new-privileges`: https://docs.linuxserver.io/misc/non-root/
- Traefik's Docker provider requires Docker API access and documents socket proxy patterns: https://doc.traefik.io/traefik/providers/docker/
- Portainer local Docker socket mode requires access to `/var/run/docker.sock`: https://docs.portainer.io/admin/environments/add/docker/socket
- MariaDB documents that the official image briefly needs root and `CHOWN` to fix volume ownership before dropping privileges: https://mariadb.com/docs/server/server-management/automated-mariadb-deployment-and-administration/docker-and-mariadb/docker-official-image-frequently-asked-questions
- Postgres official entrypoint creates/chowns data directories and uses `gosu` when started as root: https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh
- Redis official entrypoint chowns data and uses `gosu` when started as root: https://github.com/redis/docker-library-redis/blob/master/docker-entrypoint.sh
- CouchDB Docker docs state the image runs as `couchdb` uid `5984`: https://docs.couchdb.org/en/stable/install/docker.html
- Jellyfin Docker docs require `/dev/dri` for hardware acceleration: https://jellyfin.org/docs/general/installation/container/
- Immich Docker hardware transcoding uses `/dev/dri` for QSV/VAAPI: https://immich.app/docs/features/hardware-transcoding
- Nextcloud Docker docs note that changing the default user makes the image stop assuming root privileges: https://github.com/nextcloud/docker

## Capability Classes

### Likely `cap_drop: [ALL]`

These services have no Docker socket, no database init, no known root ownership
entrypoint requirement, and no privileged host networking in this compose repo.
They still need deployment validation.

| Stack | Service | Notes |
| --- | --- | --- |
| `beszel` | `beszel` | Applied as pilot; app listens on 8090 and writes only to `beszel-data`. |
| `init` | `pocket-id` | Applied; app listens on 1411; validate writable `/app/data`. |
| `downloads` | `qbitwebui` | Applied; app listens on 3000; validate `/data` and `/data/torrents` writes. |
| `plex` | `seerr` | Applied; app listens on 5055; `init: true` is not a capability need. |
| `plex` | `kometa` | Applied; no exposed port; validate config read/write and scheduled run behavior. |
| `immich` | `immich-ml` | Applied; no device mount in current compose; validate model cache writes. |
| `miniflux` | `miniflux` | Applied; app listens on 8080; migrations are DB operations, not Linux capabilities. |
| `couchdb` | `couchdb` | Applied; already runs as `5984:5984`; validate named volume ownership. |
| `pinchflat` | `pinchflat` | Applied; app listens on 8945; validate `/downloads` and `/config` writes. |

### Likely `cap_drop: [ALL]` With Device Validation

The capability drop should not remove `/dev/dri` access by itself; device access
depends on the device mapping and group permissions. Validate actual
transcoding, not just container startup.

| Stack | Service | Notes |
| --- | --- | --- |
| `jellyfin` | `jellyfin` | Runs as `1000:1000` with `group_add: 992`; validate VAAPI/QSV playback. |
| `immich` | `immich-server` | Uses `/dev/dri`; validate video transcode job and upload processing. |
| `plex` | `plex` | Uses `/dev/dri`; official image uses s6-style init, so validate startup and hardware transcode before keeping the drop. |

### LinuxServer.io Images

Do not treat all LinuxServer.io images as unsupported for hardening. Their
individual image pages are the source of truth for tested read-only and non-root
operation. For this repo, keep capability drops separate from `user:` changes:
`cap_drop: [ALL]` tests whether the normal rootful init path can start without
Docker's default capabilities; `user:` changes bypass the normal `PUID`/`PGID`
path and need the LSIO non-root recipe.

| Stack | Service | Image docs | Current notes |
| --- | --- | --- | --- |
| `arrs` | `radarr` | https://docs.linuxserver.io/images/docker-radarr/ | Page lists read-only and non-root operation; validate `/config` and `/data` ownership. |
| `arrs` | `sonarr` | https://docs.linuxserver.io/images/docker-sonarr/ | Page lists read-only and non-root operation; validate `/config` and `/data` ownership. |
| `arrs` | `lidarr` | https://docs.linuxserver.io/images/docker-lidarr/ | Page lists read-only and non-root operation; validate `/config`, `/data`, and `/music` ownership. |
| `arrs` | `prowlarr` | https://docs.linuxserver.io/images/docker-prowlarr/ | Page lists read-only and non-root operation; simplest LSIO Arr candidate. |
| `downloads` | `qbittorrent` | https://docs.linuxserver.io/images/docker-qbittorrent/ | Page lists read-only and non-root operation; also validate TCP/UDP torrent listener. |
| `downloads` | `sabnzbd` | https://docs.linuxserver.io/images/docker-sabnzbd/ | Page lists read-only and non-root operation; validate incomplete/complete download paths. |
| `plex` | `tautulli` | https://docs.linuxserver.io/images/docker-tautulli/ | Page lists read-only and non-root operation; validate config DB writes and Plex connectivity. |

LSIO non-root recipe notes:

- `user: <uid>:<gid>` makes `PUID` and `PGID` ineffective.
- Mounted volume/path ownership must be managed manually.
- Docker Mods do not run.
- Custom services do not run.
- Custom scripts are limited.
- With `no-new-privileges=true`, LSIO documents a `/run` tmpfs owned by the chosen uid/gid, for example `tmpfs: [/run:uid=1000,gid=1000,exec]`.

### Root Init / Ownership Sensitive

These are poor first-pass `cap_drop: [ALL]` candidates. Their image docs or
entrypoints indicate startup ownership fixes, user switching, or service init
that can require capabilities such as `CHOWN`, `SETUID`, `SETGID`, `FOWNER`, or
`DAC_OVERRIDE`.

| Stack | Service | Why it needs extra care |
| --- | --- | --- |
| `immich` | `redis` | Valkey/Redis style entrypoint may chown and drop from root when started as root. |
| `immich` | `database` | Postgres-derived image; DB data directory ownership/init is capability sensitive. |
| `nextcloud` | `nextcloud`, `nextcloud-cron` | Official image has root-aware entrypoint behavior and shared app/data volumes. |
| `nextcloud` | `nextcloud-postgres` | Official Postgres entrypoint chowns data and drops privileges when root. |
| `nextcloud` | `nextcloud-redis` | Official Redis entrypoint chowns data and drops privileges when root. |
| `owncloud` | `owncloud` | Official app image performs permission/setup work; validate chown/chmod behavior. |
| `owncloud` | `owncloud-mariadb` | MariaDB docs explicitly call out temporary root plus `CHOWN`. |
| `owncloud` | `owncloud-redis` | Official Redis entrypoint pattern; persistent cache volume increases ownership risk. |
| `wallabag` | `wallabag` | PHP/web image on port 80 with app asset volume; validate root entrypoint behavior. |
| `wallabag` | `db` | MariaDB entrypoint ownership/init path. |
| `wallabag` | `redis` | Official Redis entrypoint pattern. |
| `miniflux` | `miniflux-db` | Official Postgres 18 entrypoint; current mount point is `/var/lib/postgresql`. |

### Docker Socket Controllers

Linux capabilities are not the main risk for these services. The Docker socket
is the control plane. A read-only bind mount does not turn Docker API operations
into read-only API access.

| Stack | Service | Recommended direction |
| --- | --- | --- |
| `init` | `traefik` | Move to a Docker socket proxy or file provider. With `cap_drop: [ALL]`, either add `NET_BIND_SERVICE` or move internal entrypoints above 1024 if low-port binding fails. |
| `init` | `portainer` | Keep as the explicit Docker API controller; isolate access rather than relying on capability drops. |

## Suggested Rollout Order

1. Keep `beszel` as the pilot.
2. Deploy the low-risk app batch one stack at a time: `couchdb`, `pocket-id`, `pinchflat`, `qbitwebui`, `seerr`, `kometa`, `immich-ml`, and `miniflux`.
3. Try GPU services only when prepared to validate actual transcoding.
4. Treat LinuxServer.io services as their own batch and follow each image's docs; if `cap_drop: [ALL]` fails on the normal `PUID`/`PGID` path, test a minimal re-add set starting with `CHOWN`, `SETUID`, and `SETGID`.
5. Convert DB/cache services to fixed users with pre-owned volumes before dropping all capabilities, or retain the init capabilities their official entrypoints need.
6. Address Traefik's Docker socket before spending much time on smaller capability tweaks there.

Deployment checklist for each stack:

1. Add `cap_drop: [ALL]` to the selected service.
2. Redeploy only that stack.
3. Check container health and restart count.
4. Check logs for permission errors, failed binds, failed `chown`, or denied device access.
5. Confirm the Traefik route responds.
6. Exercise the main UI workflow.
7. Leave the stack running through one scheduled/background task cycle when applicable.

Known exception patterns:

- Traefik may need `NET_BIND_SERVICE` unless all bound ports are above 1024.
- Database images can require `CHOWN`, `SETUID`, or `SETGID` during init unless volumes are pre-owned and the service runs as a fixed non-root user.
- GPU-backed services need explicit `/dev/dri` validation after capability drops.
- Services with Docker socket access should be moved to a socket proxy before deeper hardening.
- LinuxServer.io images should be tested separately because their init path configures users, folders, permissions, and services before the app starts.

## Later Passes

After capability drops are stable, evaluate `read_only: true` service by service
with explicit `tmpfs` entries for required writable runtime paths.
