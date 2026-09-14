# Hermes media-broker production candidate

<!-- markdownlint-disable MD013 -->

The read-only candidate is now running on docker-host as Compose project
`media-broker`, container `media-broker-candidate`. Its root-owned source lives
at `/srv/hermes-media-candidate`; the Compose file is
`services/media-broker/deploy/compose.yml` within that directory. It remains
outside `docker/portainer-stacks.yaml`. Portainer/Git ownership promotion is
still pending, so live inventory drift checks will report this extra project.
No Ansible task creates credentials or starts this stack.

The sanitized Docker observer and its private backend are deployed. Verified
from the Hermes account: sanitized Docker reads succeed, sensitive Docker routes
are denied, and the broker serves all four read-only MCP tools. Authenticated
Arr and Tautulli calls succeed; unauthenticated broker requests and a
non-ai-dev client's connection are denied. The Hermes **user** gateway service
was restarted and registered four broker tools. Photon/Moshi configuration and
unrelated environment entries were preserved. No write tools are enabled.

Host group variables now explicitly enable the media rules and Hermes entry;
role defaults remain disabled. Future ai-dev reconciliation requires the
existing broker token as `hermes_media_broker_token` through protected Ansible
variables. Reuse `/etc/media-broker/secrets/broker-token` on docker-host rather
than generating a replacement or exposing it in command arguments.

## Staged rollout

1. **Observer first.** Reconcile the existing sanitized Docker observer and
   verify it is healthy, read-only, has no Docker socket on the exposed
   projection, and binds only to the Docker host's Tailscale address. Do not
   proceed if that prerequisite is not healthy.
2. **Prepare root-managed secrets.** On docker-host, an operator creates the
   directory `/etc/media-broker/secrets` as `root:65532`, mode `0750`, and
   exactly these files as `root:65532`, mode `0640`: `broker-token`,
   `sonarr-api-key`, `radarr-api-key`, `lidarr-api-key`, and `tautulli-api-key`.
   File-backed Compose secrets do **not** enforce declared `uid`, `gid`, or
   `mode` fields; these host ownership and mode checks are therefore required.
   The files are readable by UID/GID 65532 but not world-readable. The bearer
   token is one line of 32-256 URL-safe characters (`A-Z`, `a-z`, `0-9`, `_`,
   `-`). Never put secret values in Compose environment or Git.
3. **Host policy.** Docker host provisioning keeps port `8765` reserved with
   an original-direction `DOCKER-USER` DROP even while the broker is disabled.
   When explicitly enabled, only the exact ai-dev Tailscale `/32` arriving on
   `tailscale0` is returned before the established-connection fast path. The
   port is distinct from `443`, `2375`, and `8006`, and is not in general or
   fallback port lists. The client address must be a real `100.64.0.0/10`
   Tailscale IPv4, not merely an arbitrary `100.*` address.
4. **Candidate stack.** Run `deploy/preflight.sh` first. It is read-only: it
   verifies the local Tailscale bind address, exact source-pinned host rules,
   the observer prerequisite, and secret ownership/modes, then stops. Use the
   supported `deploy/launch.sh --enable-candidate`; it reruns this preflight
   and only then builds and starts against docker-host's local Unix socket.
   Set `MEDIA_BROKER_BIND_HOST=0.0.0.0` and
   `MEDIA_BROKER_ALLOW_PUBLIC_BIND=true`. The candidate's exact fixed values
   are Host `docker-host:8765` and Origin `http://docker-host:8765`; wildcard
   values are rejected. Loopback remains the application default. The host
   port is the verified Tailscale IPv4 (`8765:8000`), never a Traefik router or
   shared `443` listener. The broker has no media or Docker socket mounts.
5. **External ACL.** Approve the narrow Tailscale ACL for ai-dev to the
   Docker host's TCP 8765 endpoint and test authenticated MCP discovery and
   unauthenticated rejection. There is no RouterOS LAN exception: do not add
   a LAN path for this endpoint.
6. **AI-dev last.** Only after the candidate and ACL pass, enable Hermes with
   the same broker token, then manually restart the Hermes gateway and verify
   its four allow-listed read-only tools. Ansible does not restart the gateway.

The broker's upstream URLs are environment configuration only and should use
existing `proxy` network service names/ports: Sonarr `8989`, Radarr `7878`,
Lidarr `8686`, and Tautulli `8181`. The candidate sets a 5 MiB upstream
response bound for the observed 2.27 MiB Lidarr inventory. It uses five
file-mounted secrets and passes only secret paths and URLs through the
container environment.

The preflight and candidate commands must use the explicitly selected local
Docker context for any local test; build or infrastructure failures stop the
rollout. Direct Compose invocation is unsupported because it bypasses preflight
and host secret-mode checks (and is not a security boundary against root).
Do not deploy during validation or provision credentials through Ansible.
The live candidate does not follow Git automatically. Publishing or merging
these definitions does not transfer ownership to Portainer or redeploy it.
