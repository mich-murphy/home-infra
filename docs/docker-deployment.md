# Docker deployment ownership

<!-- markdownlint-disable MD013 -->

Docker deployment has two controllers with a deliberate bootstrap seam:

| Owner | Responsibility |
| --- | --- |
| Ansible | Docker runtime, host policy, NFS storage, `/srv/portainer` for relative-path Git stacks, and `/srv/init`: Traefik, socket proxy, Portainer, and Pocket ID |
| Portainer | Intended application controller for `docker/portainer-stacks.yaml`; desired Git updates for inventoried stacks |
| Git | Compose definitions and the expected active-stack inventory |

The Ansible `docker-host` role installs Docker Engine and Compose from Docker's
stable Ubuntu repository, configures daemon and published-port policy, prepares
NFS storage, copies `docker/init` to `/srv/init`, and reconciles that bootstrap
stack. Portainer is the intended controller for every other inventoried stack.
An inventory entry alone does not establish live ownership; verify controller
state after a restore.

## Portainer Git configuration

Configure every inventory entry as a separate Portainer Git stack.

For the ordinary Git-connected stacks:

- repository: `https://github.com/mich-murphy/home-infra.git`;
- reference: `refs/heads/main`;
- Compose path: the entry's `compose_path`;
- credentials: stored in Portainer's Git credential store, never in Git or a
  Compose file;
- environment values and secrets: follow each stack's policy; never commit them;
- update policy: enable Portainer's Git polling or webhook for every stack.

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
restore and whenever repository authentication changes.

## Docker management boundary

Traefik retains its read-only, unexposed socket proxy on an internal network.
Portainer intentionally mounts the Docker socket directly because its management
APIs require it; a read-only bind mount does not make the Docker API read-only.
Treat Portainer administration as privileged Docker-host access. A Portainer
socket proxy is deliberately not part of this design. Further admin-reachability
restrictions are a separate task; this retirement does not widen firewall rules
or split networks.

Containers that need the Docker socket bind the host's `/run` directory
read-only and non-recursively, never the `docker.sock` file itself. dockerd
recreates the socket whenever it restarts (for example during an apt upgrade).
Because `live-restore` keeps containers running across that restart, a
file bind would leave them holding the old, dead inode. That is what stopped
Portainer deploys and the socket proxy from 2026-10-19 to 2026-10-26.

The router permits DFLT and KDS to the Docker host only on TCP 443. Traefik's
`kds-media-only` IP allow-list middleware is attached to every non-media router,
including the TrueNAS, Portainer, and dashboard routes; only Plex and Jellyfin
are intentionally reachable from KDS. Jellyfin's direct TCP 8096 fallback is
allow-listed for the Tailscale range only, not DFLT or KDS.

## Jellyfin transcode scratch

The active encoding path is `/cache/transcodes` on the local named disk cache.
Compose no longer declares the old `/transcode` tmpfs mount, but that unused
mount remains in the running container until a Portainer-managed recreation.
Actual transcoding/playback was not tested as part of this cleanup.

## Monitoring configuration

The Beszel hub is Portainer-owned. Its binary agents on Proxmox and Docker are
currently installed outside Ansible; agent ownership and automatic restoration
remain a reproducibility task. Hub administrative credentials are in the
personal xportal 1Password account's `Private / Beszel` item, accessed through
desktop approval rather than the restricted homelab service account. SMTP and
recipient details remain in Beszel's persistent controller data, not Git.

On 2026-10-07 both systems reported up and these rules were verified through the
hub API for the existing notification owner:

| System | CPU | Memory | Disk | Status |
| --- | --- | --- | --- | --- |
| docker-host | 80%, 10 min (existing) | 90%, 5 min | 80%, 10 min (existing) | Enabled, min field 2 |
| proxmox | 90%, 10 min | 90%, 5 min | 80%, 10 min | Enabled, min field 2 |

Beszel's SMTP test endpoint accepted a marked test email to the existing
recipient; the user confirmed inbox receipt on 2026-10-07. No alert incident was
fabricated.
Proxmox ZFS pool metrics are present, but TrueNAS/SMART coverage is not yet
established. Native backup-job and TrueNAS volume alerts must not be assumed
covered by these resource alerts.

Docker agent connectivity was restored with a runtime UFW rule permitting only
hub `172.20.1.8` on `br-6e5e47ea39f2` to local agent
`100.96.174.126:45876/tcp`. That address/bridge is a live snapshot, not a portable
policy: after recreation, verify the actual hub address and agent connectivity.
Prefer an outbound agent connection or a stable, automatically reconciled
source-pinned policy as the durable follow-up. Do not open the agent port to
ordinary LAN clients to work around this dependency.

Portainer's 2026-10-07 controller inventory did not include the running
`jellyplex-watched` project. Its entry in the desired inventory is not proof of
controller ownership; reconcile that separate drift without deleting the
running watched-state service as part of retirement.

## Removing a stack

Deleting a Compose directory does not decommission its Portainer stack: remove
the stack in Portainer first, preserving its volumes, then delete the Compose
source and its `docker/portainer-stacks.yaml` entry in the same change. Run
`scripts/check-portainer-drift.sh` on the Docker host to confirm. The check is
read-only, and an unexplained missing or unexpected project must be resolved
before source is deleted.
