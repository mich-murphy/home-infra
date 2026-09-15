# Hermes media-broker ownership and updates

<!-- markdownlint-disable MD013 -->

Portainer owns the live read-only broker as an **ordinary Git-connected
stack** named `media-broker`, using the same repository source and polling as
every other inventoried stack. The application source and its container image
live in the dedicated [`mich-murphy/media-broker`](https://github.com/mich-murphy/media-broker)
repository; this repository owns only the stack definition at
`docker/media-broker/compose.yml` and the host policy around it.

## Deployment pipeline

Merging to `main` in the media-broker repository deploys the latest image
without manual host steps:

1. **Publish**: the media-broker repository's CI runs the source suite and,
   on merge to `main`, pushes the image to GHCR as
   `ghcr.io/mich-murphy/media-broker:main` plus an immutable `:sha-<commit>`
   tag kept for rollback and audit.
2. **Tracking**: the Compose file here references `:main` unpinned. That is a
   deliberate, documented exception to this repository's digest-pinned house
   style: this stack always runs the newest published image.
3. **Redeploy**: Portainer's Git polling only redeploys when the Compose file
   itself changes; it cannot notice that a moving tag's digest changed. The
   Ansible-managed `media-broker-autoupdate` timer on docker-host closes that
   gap: every five minutes it pulls `:main` with the host Docker CLI and,
   when the running container's image differs, asks Portainer's local stack
   webhook to redeploy. Portainer remains the only deployment controller; the
   timer never runs Compose itself.

Rollback: stop tracking first (`systemctl disable --now
media-broker-autoupdate.timer`, or set `docker_media_broker_autoupdate_enabled:
false` in Ansible), then redeploy a known-good immutable `:sha-<commit>` tag
through Portainer's editor update. Re-enable the timer to resume tracking.
Do not re-add a `build:` block to the Compose file; Portainer must never
build this image (see history below).

## Why this stack was previously manual

The broker used to be a host-built candidate: the image
`home-infra/media-broker:candidate` was built from a root-owned checkout on
docker-host, which forced manual updates and caused two documented incidents:

- Portainer 2.45 schedules polling **by Git source, not by stack**. Creating
  the broker on the repository's shared polling source redeployed it on source
  ticks despite a manual-only policy. See the
  [2.45 source scheduler](https://github.com/portainer/portainer/blob/2.45.0/api/gitops/scheduling/scheduler.go).
- Portainer 2.45 can rebuild a stack from its **retained Git context** when a
  `build` block is present, even with `PullImage: false`. During the MCP SDK
  patch rollout this replaced a freshly built image with stale source.

Publishing a registry image from dedicated repository CI removes the root
cause of both: there is no build block to exploit, no host checkout to
reconcile, and a redeploy can only pull an immutable digest. The broker is now
explicitly allowed on the shared Git source; the earlier "do not connect this
stack" rule is obsolete and must not be reintroduced while the image comes
from GHCR.

## Stack configuration

- Stack and Compose project: `media-broker`; container: `media-broker`
- Compose path: `docker/media-broker/compose.yml` (image-only)
- Image: `ghcr.io/mich-murphy/media-broker:main` (unpinned by design; the
  host auto-update timer keeps the running container on the newest digest)
- Registry credentials for `ghcr.io` are stored in Portainer's registry store
- Update policy: shared Git polling for Compose changes, plus the
  `media-broker-autoupdate` timer for new image digests

Portainer supplies the interpolated `SONARR_URL`, `RADARR_URL`, `LIDARR_URL`,
`TAUTULLI_URL`, `MEDIA_BROKER_BIND`, `MEDIA_BROKER_BIND_HOST`,
`MEDIA_BROKER_ALLOW_PUBLIC_BIND`, and optional `MEDIA_BROKER_SECRETS_DIR`.
These values are URLs, nonsecret bind settings, and a host directory path.
Compose fixes the secret-file paths and the Host/Origin allow-lists. Never put
a backend API key or broker bearer value in Portainer's stack variables,
Compose environment, Git, or command arguments.

The fixed endpoint is `http://docker-host:8765/mcp`, with Host
`docker-host:8765` and Origin `http://docker-host:8765`. The host port binds
only the docker-host Tailscale IPv4. It is not exposed through Traefik, a LAN
exception, or shared port 443. The broker runs nonroot with a read-only
filesystem and has no Docker socket or media mounts.

## Host-side controls that remain

- The five files in `/etc/media-broker/secrets` (`broker-token`,
  `sonarr-api-key`, `radarr-api-key`, `lidarr-api-key`, `tautulli-api-key`)
  stay host-managed: directories `root:65532` mode `0750`, files
  `root:65532` mode `0640`. File-backed Compose secrets do not enforce their
  declared ownership or mode, so verify these after any host rebuild.
  Future ai-dev Ansible runs require the existing bearer as
  `hermes_media_broker_token` through protected variables.
- The auto-update timer reads `/etc/media-broker/autoupdate.env` (root:root
  mode `0600`), written by the `docker-host` role from the protected
  variables `docker_media_broker_autoupdate_github_token` (classic PAT with
  `read:packages`) and `docker_media_broker_autoupdate_webhook` (the
  Portainer stack webhook URL). Docker login state lives only in the
  root-owned `/var/lib/media-broker-autoupdate` directory.
- The host firewall admits TCP 8765 only from ai-dev's exact Tailscale
  address through `tailscale0`; the `docker-host` role defines and asserts
  the `DOCKER-USER` rules on every run.
- The broker uses a 5 MiB upstream-response bound for the observed 2.27 MiB
  Lidarr inventory.

## One-time migration runbook

Performed once, from the old manual stack to the Git stack:

1. Ensure the first image exists: the media-broker repository's `publish`
   job must have run on `main` so GHCR serves
   `ghcr.io/mich-murphy/media-broker:main`.
2. In Portainer, add `ghcr.io` registry credentials with pull access to the
   private package (classic PAT with `read:packages`).
3. Delete the existing `media-broker` stack (brief downtime; the old
   container name `media-broker-candidate` goes away with it). Do not delete
   host secret files.
4. Recreate the stack from Git: repository
   `https://github.com/mich-murphy/home-infra.git`, reference
   `refs/heads/main`, compose path `docker/media-broker/compose.yml`, the
   same nonsecret environment values as before, AutoUpdate polling enabled on
   the shared source. No relative-path volumes are needed for this stack.
5. Enable the stack webhook in Portainer's stack settings and copy its URL
   (`https://<host>:9443/api/stacks/webhooks/<uuid>`).
6. Provide the protected variables
   `docker_media_broker_autoupdate_github_token` (the same `read:packages`
   PAT) and `docker_media_broker_autoupdate_webhook` (the copied URL), set
   `docker_media_broker_autoupdate_enabled: true` for the docker host group,
   and run the `docker-host` role. The timer pulls `:main` within five
   minutes and redeploys whenever the published digest changes.
7. Wait for the container to become healthy, then verify: the running image
   matches the newest `:main` digest; authenticated reads from Hermes
   succeed for all four tools; unauthenticated requests are rejected; a
   different client is denied. Retain the existing ACL and token. No Hermes
   gateway restart is required.
8. Verify the full pipeline once: merge a trivial change in the media-broker
   repository, then confirm `journalctl -u media-broker-autoupdate.service`
   shows the pull and webhook redeploy and that the container's image ID
   changed to the new `:sha-<commit>` build.

This remains a read-only integration. Conversation-approved writes and
Jellyfin playback reporting are not enabled. Host controls are operational
policy, not a security boundary against root administrators.
