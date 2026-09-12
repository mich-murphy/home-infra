# Docker deployment ownership

<!-- markdownlint-disable MD013 -->

Docker deployment has two controllers with a deliberate bootstrap seam:

| Owner | Responsibility |
| --- | --- |
| Ansible | Docker runtime, host policy, NFS storage, `/srv/portainer` for relative-path Git stacks, and `/srv/init`: Traefik, socket proxy, Portainer, and Pocket ID |
| Portainer GitOps | Application stacks listed in `docker/portainer-stacks.yaml` |
| Git | Compose definitions and the expected active-stack inventory |

The Ansible `docker-host` role installs Docker Engine and Compose from Docker's
stable Ubuntu repository, configures daemon and published-port policy, prepares
NFS storage, copies `docker/init` to `/srv/init`, and reconciles that bootstrap
stack. Portainer then deploys every other stack.

## Portainer Git configuration

Configure each inventory entry as a separate Portainer Git stack:

- repository: `https://github.com/mich-murphy/home-infra.git`;
- reference: `refs/heads/main`;
- Compose path: the entry's `compose_path`;
- credentials: stored in Portainer's Git credential store, never in Git or a
  Compose file;
- environment values and secrets: stored on the Portainer stack;
- update policy: enable Portainer's Git polling or webhook for the stack and
  keep its selected update policy consistent across application stacks.

A few stacks (`nextcloud`, `recyclarr`) bind-mount a file or directory that
lives next to their `compose.yml` in Git (for example
`./post-installation.sh` or `./recyclarr.yml`). Portainer only resolves these
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

## Agent socket proxy

The `init` stack runs two instances of the same pinned socket proxy image.
`docker-socket-proxy` serves Traefik on an internal network with no published
port. `docker-socket-proxy-agent` serves the ai-dev Hermes agent and is the
only one that is reachable off the host.

Keep them separate. Widening the agent's read surface must never widen
Traefik's, and the two have no reason to share a grant.

The agent instance sets `POST=0`, which refuses every write route including
exec and container creation, and allows only the read routes needed to
diagnose: containers, logs, stats, events, images, networks, volumes, info,
ping, and version. Three controls stand in front of it:

1. it publishes on `AGENT_PROXY_BIND`, docker-host's Tailscale address, which
   the `docker-host` role reads at run time and writes into `/srv/init/.env`,
   so the LAN cannot reach it;
2. the tailnet policy grants `tag:ai-dev` alone `tcp:2375`;
3. `DOCKER-USER` admits that one source address and drops every other client,
   so a mistake in the tailnet policy is not sufficient to expose the API.

The role asserts the last two, and asserts that the container never binds all
interfaces. An empty `AGENT_PROXY_BIND` would make Compose bind everywhere,
so the bind address is verified rather than assumed.

The proxy filters requests, not responses. `GET /containers/{id}/json` returns
a container's environment block, so the agent can read secrets passed through
Compose `environment:` entries. Moving those values out of the environment is
the only fix; no proxy setting achieves it.

## Removing a stack

Deleting a Compose directory does not decommission its Portainer stack. Use
this order:

1. Identify the exact Portainer stack and its persistent volumes or external
   data dependencies.
2. Disable automatic Git updates, then remove the stack in Portainer. Preserve
   volumes unless their deletion is separately approved and backed up.
3. Confirm its containers and Compose project label are absent from the Docker
   host.
4. Remove the matching entry from `docker/portainer-stacks.yaml` and delete its
   Compose source in the same reviewable change.
5. Run `scripts/check-portainer-drift.sh` on the Docker host.

The drift check is read-only. It compares expected Portainer-owned project
names with the `com.docker.compose.project` labels on running containers and
ignores the Ansible-owned `init` project. A missing project or an unexpected
project is a deployment discrepancy that must be explained before source is
deleted.
