# Docker deployment ownership

<!-- markdownlint-disable MD013 -->

Docker deployment has two controllers with a deliberate bootstrap seam:

| Owner | Responsibility |
| --- | --- |
| Ansible | Docker runtime, host policy, NFS storage, `/srv/portainer` for relative-path Git stacks, and `/srv/init`: Traefik, socket proxy, Portainer, and Pocket ID |
| Portainer | Application controller for `docker/portainer-stacks.yaml`; Git updates for ordinary stacks, guarded manual updates for `media-broker` |
| Git | Compose definitions and the expected active-stack inventory |

The Ansible `docker-host` role installs Docker Engine and Compose from Docker's
stable Ubuntu repository, configures daemon and published-port policy, prepares
NFS storage, copies `docker/init` to `/srv/init`, and reconciles that bootstrap
stack. Portainer is the intended controller for every other inventoried stack.
The `media-broker` project is now Portainer-managed with guarded manual updates.
An inventory entry alone does not establish live ownership; verify controller
state after a restore.

## Portainer Git configuration

Configure ordinary inventory entries as separate Portainer Git stacks.
**Do not connect `media-broker` to the shared Git source.** Portainer 2.45 polls
by source and cannot enforce its manual-only policy through a per-stack
`AutoUpdate: null`. The broker instead uses authenticated editor/API updates
from reviewed Git source, after the host checks in its runbook.

For the ordinary Git-connected stacks:

- repository: `https://github.com/mich-murphy/home-infra.git`;
- reference: `refs/heads/main`;
- Compose path: the entry's `compose_path`;
- credentials: stored in Portainer's Git credential store, never in Git or a
  Compose file;
- environment values and secrets: follow each stack's policy. For `media-broker`,
  store only interpolated nonsecret settings in Portainer; backend API keys and
  the broker bearer token remain in host-managed files described in the
  [media-broker runbook](hermes-media.md);
- update policy: enable Portainer's Git polling or webhook for ordinary stacks.
  **Exception: `media-broker` must have AutoUpdate disabled and no webhook.**
  Its manual redeploy requires the host preflight and explicit image build in
  [the media-broker runbook](hermes-media.md).

The `recyclarr` stack bind-mounts files that live next to its `compose.yml` in
Git (`./recyclarr.yml`, `./settings.yml`, and `./custom-formats/`). Portainer
only resolves these
relative paths when the stack has **"Enable relative path volumes"** turned
on in its Git stack settings, with **Local filesystem path** set to
`/srv/portainer` (created by the `docker-host` role). Portainer's unpacker
clones the repository beneath that directory on the host and rewrites the
`./` mounts to point into the clone. Without it, the daemon resolves the
relative path inside Portainer's own data volume, which does not exist on
the host, and Docker silently creates an empty directory in its place: the
container starts with a directory where the file should be. Turn this on for
any stack whose compose file uses a `./`-relative bind mount.

Portainer remains the authoritative record for credential identity, polling
interval, webhook token, and per-stack environment values because these are
secret-bearing or controller-specific. Audit them in the Portainer UI after a
restore and whenever repository authentication changes. This does not make
Portainer the owner of the media broker's API keys or bearer token; those remain
in restricted host files.

## Agent Docker observer

The `init` stack runs Traefik's pinned socket proxy on an internal network and a
separate two-service path for the ai-dev Hermes agent. The
`docker-socket-proxy-agent` container keeps the existing tailnet address and
port 2375, but is now a small read-only HTTP projection with no Docker socket.
It talks only to the fixed, unexposed
`docker-socket-proxy-agent-backend` service on a private internal network. The
observer also attaches to a dedicated non-internal frontend solely because
Docker cannot publish a port from an internal-only network; no other service
attaches to that frontend. The backend is the pinned Tecnativa proxy with only
`CONTAINERS`, `VERSION`, and `PING` reads enabled and `POST=0`.

The observer permits only `GET`/`HEAD` `/_ping`, `/version`,
`/containers/json` (with only `all=0` or `all=1`), and
`/containers/{strict-name-or-id}/json`, with an optional Docker API version
prefix. It rejects writes, encoded or ambiguous paths, and all other Docker
routes including logs, archives, events, images, volumes, and configuration
reads. Responses contain only IDs, names, image references, state, status, exit
codes, and health `Status`; environment, labels, commands, mount paths,
networks, health logs, arbitrary nested data, and backend errors are not
returned. The observer has finite request, concurrency, upstream header/body, and
upstream time limits and does not follow redirects or environment proxies.
It resolves the fixed backend once at startup, before accepting clients, and
uses the cached numeric address thereafter; startup DNS follows the container
OS resolver's own timeout and is intentionally outside the request deadline.
If the backend address changes, restart/reconcile the observer so it resolves
again. Docker inspect and CLI compatibility is deliberately reduced: this endpoint
is for safe status observation, not full `docker inspect`, and it provides no
logs.

Independent controls restrict the existing port to the ai-dev tailnet address;
the `docker-host` role defines them and asserts them on every run, including
that the container never binds all interfaces. An empty `AGENT_PROXY_BIND`
would make Compose bind everywhere, so the bind address is verified rather than
assumed. Only the backend mounts `/var/run/docker.sock`; both services drop
all capabilities and the observer runs read-only as an unprivileged user. The
root-controlled observer source is hashed into the Compose service
configuration during bootstrap, so a source update recreates the observer
instead of leaving an old process behind a replaced bind-mounted inode.

The router permits DFLT and KDS to the Docker host only on TCP 443. Traefik's
`kds-media-only` IP allow-list middleware is attached to every non-media router,
including the TrueNAS, Portainer, and dashboard routes; only Plex and Jellyfin
are intentionally reachable from KDS. Jellyfin's direct TCP 8096 fallback is
allow-listed for the Tailscale range only, not DFLT or KDS.

## Hermes media-broker candidate

The read-only media broker is Portainer-managed without a Git workflow,
AutoUpdate, or webhook. The shared repository source's polling policy was left
unchanged for other stacks. The inventory points to the canonical
`services/media-broker/deploy/compose.yml`; guarded manual updates and the
Portainer 2.45 source-polling limitation are documented in
[`docs/hermes-media.md`](hermes-media.md).

## Removing a stack

Deleting a Compose directory does not decommission its Portainer stack: remove
the stack in Portainer first, preserving its volumes, then delete the Compose
source and its `docker/portainer-stacks.yaml` entry in the same change. Run
`scripts/check-portainer-drift.sh` on the Docker host to confirm. The check is
read-only, and an unexplained missing or unexpected project must be resolved
before source is deleted.
