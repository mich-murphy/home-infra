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

- `docker/audiobookshelf/compose.yml`: `cap_drop: [ALL]`, `cap_add: [NET_BIND_SERVICE]` for port 80
- `docker/beszel/compose.yml`: `cap_drop: [ALL]`
- `docker/couchdb/compose.yml`: `cap_drop: [ALL]`
- `docker/downloads/compose.yml`: `qbitwebui` with `cap_drop: [ALL]`; `qbittorrent` and `sabnzbd` with LSIO retained init capabilities
- `docker/immich/compose.yml`: `immich-server` with `cap_drop: [ALL]`
- `docker/jellyfin/compose.yml`: `cap_drop: [ALL]`
- `docker/miniflux/compose.yml`: `miniflux` only
- `docker/pinchflat/compose.yml`: `cap_drop: [ALL]`
- `docker/plex/compose.yml`: `seerr` and `kometa` with `cap_drop: [ALL]`; `plex` and `tautulli` with retained init capabilities
- `docker/arrs/compose.yml`: all services with LSIO retained init capabilities

These changes intentionally exclude Docker socket controllers, database/cache
services, `immich-ml` after its healthcheck failed, and `pocket-id` after startup failed with `su-exec: setgroups(1000): Operation not permitted`.

### Already-Applied Fresh-Volume Audit

The LinuxServer.io fresh-volume issue does not apply to the non-LSIO capability
drops below. Do not back-apply the LSIO retained capability set to these
containers without a specific failure:

| Stack | Service | Fresh-volume capability risk |
| --- | --- | --- |
| `beszel` | `beszel` | Low. Image starts a single binary directly and has no observed ownership/bootstrap entrypoint. |
| `couchdb` | `couchdb` | Watch. Compose pins `user: 5984:5984`, so the root `chown`/`chmod`/`setpriv` branch in the official entrypoint is bypassed. Keep the volume owned by uid/gid `5984`; if this service ever starts as root or uses host bind mounts, it needs retained init capabilities instead of bare `cap_drop: [ALL]`. |
| `downloads` | `qbitwebui` | Low. Entrypoint only normalizes the command before launching Bun; no ownership repair or user switching observed. |
| `miniflux` | `miniflux` | Low. Image runs as uid `65534` and has no writable volume in this repo; DB initialization is in the separate Postgres container, not the app container. |
| `pinchflat` | `pinchflat` | Medium. Startup checks file permissions and exits on failure; it does not repair ownership. Root without capabilities can write to permissive/root-owned fresh named volumes, but host bind mounts such as `/downloads` must already be writable. |
| `plex` | `seerr` | Low. Image runs as `node:node`; the `/app/config` volume is owned by uid/gid `1000` after initialization. |
| `plex` | `kometa` | Low. Image starts via `tini` into Python and runs as root; no ownership repair or user switching observed. |
| `audiobookshelf` | `audiobookshelf` | Low. Entrypoint only normalizes the command before launching Node; `NET_BIND_SERVICE` is retained only for port 80. |

For LSIO services, the applied capability drop keeps the retained init
capabilities validated during the Prowlarr pilot: `CHOWN`, `SETUID`, `SETGID`,
`DAC_OVERRIDE`, `FOWNER`, and `KILL`. Runtime validation is still required for
fresh `/config` initialization, bind-mount writes, and service-specific behavior.

For GPU-backed services, capability drops do not grant or remove `/dev/dri`
device access by themselves. The applied drops still require post-deploy
validation of startup health plus an actual hardware transcode or video job.
`plex` keeps the retained init capability set because its official image starts
through `/init` as root before preparing the runtime process.

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

## Capability Classes

### Likely `cap_drop: [ALL]`

These services have no Docker socket, no database init, no known root ownership
entrypoint requirement, and no privileged host networking in this compose repo.
They still need deployment validation.

| Stack | Service | Notes |
| --- | --- | --- |
| `beszel` | `beszel` | Applied as pilot; app listens on 8090 and writes only to `beszel-data`. |
| `init` | `pocket-id` | Deferred; `cap_drop: [ALL]` caused startup permission errors and `su-exec: setgroups(1000): Operation not permitted`. |
| `downloads` | `qbitwebui` | Applied; app listens on 3000; validate `/data` and `/data/torrents` writes. |
| `plex` | `seerr` | Applied; app listens on 5055; `init: true` is not a capability need. |
| `plex` | `kometa` | Applied; no exposed port; validate config read/write and scheduled run behavior. |
| `immich` | `immich-ml` | Deferred; `cap_drop: [ALL]` left the service unhealthy during validation. |
| `miniflux` | `miniflux` | Applied; app listens on 8080; migrations are DB operations, not Linux capabilities. |
| `couchdb` | `couchdb` | Applied; already runs as `5984:5984`; validate named volume ownership. |
| `pinchflat` | `pinchflat` | Applied; app listens on 8945; validate `/downloads` and `/config` writes. |
| `audiobookshelf` | `audiobookshelf` | Applied with `NET_BIND_SERVICE` retained because the app listens on port 80; validate `/config`, `/metadata`, and audiobook library access. |

### Likely `cap_drop: [ALL]` With Device Validation

The capability drop should not remove `/dev/dri` access by itself; device access
depends on the device mapping and group permissions. Validate actual
transcoding, not just container startup.

| Stack | Service | Notes |
| --- | --- | --- |
| `jellyfin` | `jellyfin` | Applied; runs as `1000:1000` with `group_add: 992`; validate VAAPI/QSV playback. |
| `immich` | `immich-server` | Applied; uses `/dev/dri`; validate video transcode job and upload processing. |
| `plex` | `plex` | Applied with retained init capabilities; uses `/dev/dri`; validate startup and hardware transcode. |

### LinuxServer.io Images

Do not treat all LinuxServer.io images as unsupported for hardening. Their
individual image pages are the source of truth for tested read-only and non-root
operation. For this repo, keep capability drops separate from `user:` changes:
the normal `PUID`/`PGID` path starts as root, runs s6 init, prepares users,
folders, permissions, mods, custom files/services, and then starts the
application as `abc`. A warm container with existing volumes can appear to work
with `cap_drop: [ALL]`, but that is not a fresh-host bootstrap test. `user:`
changes bypass the normal `PUID`/`PGID` path and need the LSIO non-root recipe.

| Stack | Service | Image docs | Current notes |
| --- | --- | --- | --- |
| `arrs` | `radarr` | https://docs.linuxserver.io/images/docker-radarr/ | Applied with retained init capabilities; validate `/config` and `/data` ownership. |
| `arrs` | `sonarr` | https://docs.linuxserver.io/images/docker-sonarr/ | Applied with retained init capabilities; validate `/config` and `/data` ownership. |
| `arrs` | `lidarr` | https://docs.linuxserver.io/images/docker-lidarr/ | Applied with retained init capabilities; validate `/config`, `/data`, and `/music` ownership. |
| `arrs` | `prowlarr` | https://docs.linuxserver.io/images/docker-prowlarr/ | Applied as the LSIO pilot with retained init capabilities; validate fresh `/config` ownership and indexer/app writes. |
| `downloads` | `qbittorrent` | https://docs.linuxserver.io/images/docker-qbittorrent/ | Applied with retained init capabilities; also validate TCP/UDP torrent listener. |
| `downloads` | `sabnzbd` | https://docs.linuxserver.io/images/docker-sabnzbd/ | Applied with retained init capabilities; validate incomplete/complete download paths. |
| `plex` | `tautulli` | https://docs.linuxserver.io/images/docker-tautulli/ | Applied with retained init capabilities; validate config DB writes and Plex connectivity. |

For normal rootful LSIO operation on fresh volumes, do not start from
`cap_drop: [ALL]` with no re-adds. Test a retained init capability set first:

- `CHOWN`: required for startup ownership fixes on `/config` and bind mounts.
- `SETUID` and `SETGID`: required for the init path to switch from root to the
  configured `PUID`/`PGID`/`abc` user and group.
- `DAC_OVERRIDE` and `FOWNER`: usually needed while root fixes permissions on
  newly created or host-owned paths before the app drops privileges.
- `KILL`: keep for s6 supervision and clean shutdown of services running as
  the unprivileged app user.

Only add service-specific capabilities after logs prove a need. For this repo's
current LSIO services, no container listens below port 1024, so
`NET_BIND_SERVICE` is not expected for the LSIO batch.

Prowlarr pilot validation used disposable fresh named volumes. With the retained
init capability set, `/config` was initialized as `1215:1215`, Prowlarr ran as
`abc`, and migrations completed. With bare `cap_drop: [ALL]`, startup logged
`chown: Operation not permitted` and repeated `s6-applyuidgid` group-list
failures, which confirms that warm-volume tests are insufficient for LSIO
images.

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
2. Deploy the low-risk app batch one stack at a time: `couchdb`, `pinchflat`, `qbitwebui`, `seerr`, `kometa`, and `miniflux`.
3. Deploy low-port standalone apps such as `audiobookshelf` with only `NET_BIND_SERVICE` re-added when needed.
4. Deploy LinuxServer.io services as their own batch and preserve the fresh-host init capabilities above before removing more.
5. Deploy GPU services only when prepared to validate actual transcoding.
6. Convert DB/cache services to fixed users with pre-owned volumes before dropping all capabilities, or retain the init capabilities their official entrypoints need.
7. Address Traefik's Docker socket before spending much time on smaller capability tweaks there.

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
- LinuxServer.io images should be tested with fresh empty volumes because their init path configures users, folders, permissions, and services before the app starts.

## Later Passes

After capability drops are stable, evaluate `read_only: true` service by service
with explicit `tmpfs` entries for required writable runtime paths.
