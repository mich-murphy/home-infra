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

The `recyclarr` stack bind-mounts files that live next to its `compose.yml` in
Git (`./recyclarr.yml`, `./settings.yml`, `./custom-formats/`, and Checkrr's
`./checkrr.yaml.tpl`). Portainer only resolves these
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
port. `docker-socket-proxy-agent` serves the ai-dev Hermes agent.

Keep them separate. Widening the agent's read surface must never widen
Traefik's, and the two have no reason to share a grant.

The agent instance refuses every write route and allows only the read routes
needed to diagnose. Independent controls restrict it to the ai-dev tailnet
address; the `docker-host` role defines them and asserts them on every run,
including that the container never binds all interfaces. An empty
`AGENT_PROXY_BIND` would make Compose bind everywhere, so the bind address is
verified rather than assumed.

The proxy filters requests, not responses: inspecting a container returns its
environment block, so any secret passed through a Compose `environment:` entry
is readable through it. Moving those values out of the environment is the only
fix; no proxy setting achieves it.

## Removing a stack

Deleting a Compose directory does not decommission its Portainer stack: remove
the stack in Portainer first, preserving its volumes, then delete the Compose
source and its `docker/portainer-stacks.yaml` entry in the same change. Run
`scripts/check-portainer-drift.sh` on the Docker host to confirm. The check is
read-only, and an unexplained missing or unexpected project must be resolved
before source is deleted.
