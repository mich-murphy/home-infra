# Docker hardening policy

This is the steady-state security policy for the Compose services in this
repository. The last live validation was **2026-08-16**: all 37 running
containers used `no-new-privileges`, and the expected capability policy below
was present.

## Defaults

Every container must set:

```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
```

Add capabilities back only when the image startup path or runtime has a tested,
documented need. Image updates must not silently restore Docker's default
capability set. Device mappings such as `/dev/dri` are separate from Linux
capabilities and require their own functional checks.

## Retained-capability classes

LinuxServer.io and other root-initialised application images retain `CHOWN`,
`SETUID`, `SETGID`, `DAC_OVERRIDE`, `FOWNER`, and `KILL`. Their entrypoints use
these to initialise volumes, repair ownership, switch users, and supervise
processes. Database and cache images that initialise data directories as root
use the same set.

Service-specific additions are limited to:

- `NET_BIND_SERVICE` for hardened processes that bind below port 1024, such as
  Audiobookshelf and Wallabag.
- `SETPCAP` for ownCloud Redis, whose entrypoint adjusts its capability bounding
  set before starting Redis.

Fresh-volume initialisation cannot be inferred from a warm running volume.
LinuxServer.io, database, cache, and ownership-sensitive images must be tested
with disposable empty volumes when their image or capability set changes.

## Explicit exceptions

- **Traefik** retains the capabilities required to bind its entrypoints. It
  discovers services through the restricted Docker socket proxy rather than a
  direct socket mount.
- **Portainer** is the designated Docker API controller and keeps direct access
  to `/var/run/docker.sock`; capability dropping does not meaningfully reduce
  the authority granted by that socket.
- **Pocket ID** does not drop all capabilities. A live test failed with
  `su-exec: setgroups(1000): Operation not permitted`.
- **Immich machine learning** does not drop all capabilities. A live test left
  its health check failing.

These are exception records, not patterns for new services. Re-test them when
their image entrypoints materially change.

## Docker socket policy

Only Portainer mounts the Docker socket directly. Traefik uses the Tecnativa
socket proxy on an internal network. The proxy is read-only at the filesystem
level, drops all capabilities, uses a read-only root filesystem with temporary
`/tmp` and `/run`, and exposes only the GET-oriented API needed for discovery.
`POST`, `INFO`, and `NETWORKS` remain denied.

## Verification after image changes

For each changed stack, redeploy only that stack and verify:

1. Compose renders successfully and the intended `security_opt`, `cap_drop`,
   and `cap_add` values are present in `docker inspect`.
2. Health status and restart counts remain stable; logs contain no permission,
   bind, ownership, migration, or device errors.
3. The Traefik HTTPS route responds and the main application read/write path
   works.
4. GPU-backed services complete an actual hardware transcode or processing job.
5. Root-initialised images can initialise a disposable fresh volume before the
   production image is accepted.

Do not batch capability changes across stacks: a failure must be attributable
and reversible at the individual stack boundary.
