# Docker deployment ownership

<!-- markdownlint-disable MD013 -->

Docker deployment has two controllers with a deliberate bootstrap seam:

| Owner | Responsibility |
| --- | --- |
| Ansible | Docker runtime, host policy, NFS storage, and `/srv/init`: Traefik, socket proxy, Portainer, and Pocket ID |
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

Portainer remains the authoritative record for credential identity, polling
interval, webhook token, and per-stack environment values because these are
secret-bearing or controller-specific. Audit them in the Portainer UI after a
restore and whenever repository authentication changes.

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
