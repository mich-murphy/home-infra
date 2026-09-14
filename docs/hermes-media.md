# Hermes media-broker ownership and updates

<!-- markdownlint-disable MD013 -->

Portainer now owns the live read-only broker as stack `media-broker`, container
`media-broker-candidate`. The handoff assigned stack ID 39; look up the stack by
name after a restore rather than assuming that ID is permanent. The repository
remains the source of its canonical Compose definition and application code.

The stack is **manually updated, not connected to Portainer's shared Git
source**. Its Git workflow, AutoUpdate, and webhook are absent. Authenticated
reads from Hermes, four-tool discovery, unauthenticated rejection, and an actual
historical Tautulli read passed after handoff. Backend credentials, the existing
Tailscale grant, and Hermes configuration were retained without rotation or a
new gateway restart.

## Why this stack does not use Git polling

Portainer 2.45 schedules polling by Git source, not independently by stack.
Creating this stack with `AutoUpdate: null` reused the repository's existing
five-minute polling source. That source tried an unwanted image pull, despite
the requested manual policy. The running broker remained healthy.

The broker was detached using Portainer's supported editor/update operation.
Its Git workflow and automatic-update settings were then verified absent.
The source used by the other application stacks retained its five-minute
interval. Do not reconnect this broker to that source or disable polling for
unrelated stacks as a workaround.

This behavior is explicit in Portainer's
[2.45 source scheduler](https://github.com/portainer/portainer/blob/2.45.0/api/gitops/scheduling/scheduler.go):
a source tick redeploys its referenced artifacts. A separate Git-connected
broker deployment remains future work and requires a supported way to isolate
its update policy. The current manual Portainer ownership is intentional.

## Stack configuration

- Stack and Compose project: `media-broker`
- Canonical Compose: `services/media-broker/deploy/compose.yml`
- Container: `media-broker-candidate`
- Existing external application network: `proxy`
- AutoUpdate: disabled; webhook: none; Git workflow: none
- Deployment method: authenticated Portainer editor/API update after host checks

Portainer supplies the interpolated `SONARR_URL`, `RADARR_URL`, `LIDARR_URL`,
`TAUTULLI_URL`, `MEDIA_BROKER_BIND`, `MEDIA_BROKER_BIND_HOST`,
`MEDIA_BROKER_ALLOW_PUBLIC_BIND`, and optional `MEDIA_BROKER_SECRETS_DIR`.
These values are URLs, nonsecret bind settings, and a host directory path.
Compose fixes the secret-file paths and the Host/Origin allow-lists.
Never put a backend API key or broker bearer value in Portainer's stack
variables, Compose environment, Git, or command arguments.

The fixed endpoint is `http://docker-host:8765/mcp`, with Host
`docker-host:8765` and Origin `http://docker-host:8765`. The host port binds
only the verified docker-host Tailscale IPv4. It is not exposed through
Traefik, a LAN exception, or shared port 443. The broker runs nonroot with a
read-only filesystem and has no Docker socket or media mounts.

## Guarded manual update

1. Check out the reviewed release under the root-owned
   `/srv/hermes-media-candidate` directory, retaining its restricted nonsecret
   deployment `.env`. Reconcile the observer's source/checksum first if that
   source changed. Do not run the standalone candidate launcher after Portainer
   takes ownership, since that would introduce a second deployment controller.
2. Reuse the five existing files in `/etc/media-broker/secrets`: `broker-token`,
   `sonarr-api-key`, `radarr-api-key`, `lidarr-api-key`, and `tautulli-api-key`.
   Directories must be `root:65532` mode `0750`; files must be `root:65532` mode
   `0640`. File-backed Compose secrets do not enforce their declared ownership
   or mode, so these host checks are required. Do not rotate credentials during
   a normal update. Future ai-dev Ansible runs require the existing bearer as
   `hermes_media_broker_token` through protected variables.
3. Set the nonsecret values in the host shell. Portainer variables are not
   inherited by a separate host build:

   ```sh
   cd /srv/hermes-media-candidate
   export MEDIA_BROKER_BIND=100.64.0.2 # replace with the verified host Tailscale IP
   export MEDIA_BROKER_AI_DEV_CLIENT=ai-dev
   export MEDIA_BROKER_BIND_HOST=0.0.0.0
   export MEDIA_BROKER_ALLOW_PUBLIC_BIND=true
   export SONARR_URL=http://sonarr:8989
   export RADARR_URL=http://radarr:7878
   export LIDARR_URL=http://lidarr:8686
   export TAUTULLI_URL=http://tautulli:8181
   services/media-broker/deploy/preflight.sh
   ```

   Preflight verifies the exact source-pinned host policy, sanitized observer,
   frontend/private-backend topology, deployed source identity, and secret
   ownership/modes. Stop if it fails.
4. Explicitly build the locked application source on docker-host:

   ```sh
   docker --host unix:///var/run/docker.sock compose \
     -f services/media-broker/deploy/compose.yml build --pull=false media-broker
   ```

   Stop on build failure. Portainer does not run preflight, and a cached image
   does not prove that changed source was rebuilt.
5. Authenticate to Portainer and update only `media-broker` using the canonical
   Compose content from that same reviewed revision and its nonsecret settings.
   Keep image pulling disabled, pruning disabled, and automatic updates/webhooks
   absent. Use the host-built `home-infra/media-broker:candidate` image; it is
   local to docker-host, not a public registry image. The prebuilt image is
   required: do not rely on Portainer retaining a Git build context after detach.
6. Wait for the controller operation to finish and the container to be healthy.
   An accepted API request is not proof of completed deployment. Retest
   authenticated reads from Hermes, all four tools, unauthenticated rejection,
   and denial from a different client. Retain the existing ACL and token.
   Ownership or image updates alone do not require restarting the Hermes user
   gateway; Ansible does not restart it automatically.

The host firewall admits TCP 8765 only from ai-dev's exact Tailscale address
through `tailscale0`, before its general established-connection rules. ai-dev
permits egress only to the dedicated docker-host endpoint. The broker uses a
5 MiB upstream-response bound for the observed 2.27 MiB Lidarr inventory.

This remains a read-only integration. Conversation-approved writes and Jellyfin
playback reporting are not enabled. Host preflight and controller procedures
are operational controls, not a security boundary against root administrators.
