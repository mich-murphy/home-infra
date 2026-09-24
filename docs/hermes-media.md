# Hermes media-broker ownership and updates

<!-- markdownlint-disable MD013 -->

Portainer owns the read-only broker as an **ordinary Git-connected stack**
named `media-broker`, using the same repository source and polling as every
other inventoried stack. The application source and its container image live
in the dedicated [`mich-murphy/media-broker`](https://github.com/mich-murphy/media-broker)
repository; this repository owns only the stack definition at
`docker/media-broker/compose.yml` and the host policy around it.

This describes the target state. Until the one-time migration runbook below
is performed, the live stack is still the earlier manually updated one.

## Deployment pipeline

Merging to `main` in the media-broker repository deploys without manual host
steps, using the same digest-pin trigger every other stack relies on:

1. **Publish**: the media-broker repository's CI runs the source suite and,
   on merge to `main`, pushes the image to GHCR as
   `ghcr.io/mich-murphy/media-broker:main` plus an immutable `:sha-<commit>`
   tag kept for rollback and audit.
2. **Pin**: the Compose reference here is `:main@sha256:<digest>`. Renovate
   (already authenticating to ghcr.io as `mich-murphy` via its hostRules)
   updates the digest whenever `:main` moves and automerges the PR under the
   repository's existing digest-automerge rule. Renovate runs on a cron
   schedule; use its workflow dispatch to pin a fresh release immediately.
3. **Redeploy**: the digest bump is a commit on home-infra `main` — exactly
   the change Portainer's Git polling watches. It redeploys the stack and
   pulls the pinned digest.

The digest pin is the deploy trigger, not a style preference: Portainer's
auto-update compares repository commit hashes and never consults the
registry, so an unpinned moving tag would stay stale until an unrelated
commit happened to land. Portainer's only registry-aware feature is an
inbound registry webhook, which is unusable here (nothing gets through
Tailscale, and GHCR does not offer registry webhooks).

Rollback is `git revert` of the digest-bump commit (Portainer redeploys the
previous digest on the next poll) or an emergency editor update pinning a
known `:sha-<commit>` tag. Do not re-add a `build:` block to the Compose
file; Portainer must never build this image (see history below).

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
- Image: `ghcr.io/mich-murphy/media-broker:main@sha256:...` (Renovate-pinned;
  unpinned only briefly before Renovate's first pin after introduction)
- Registry credentials: the package is private, so Portainer needs a `ghcr.io`
  registry entry. This is manual UI state, not established by this repository;
  add it in migration step 3 and audit it after a restore
- Update policy: shared Git polling; Renovate digest bumps are the trigger
- Health: the image carries the `HEALTHCHECK` (unauthenticated `GET /health`
  on the container port answering a static body); the Compose file keeps no
  override, so Portainer reports the real probe result

Portainer supplies the interpolated `SONARR_URL`, `RADARR_URL`, `LIDARR_URL`,
`TAUTULLI_URL`, `JELLYFIN_URL`, `QBITTORRENT_URL`, `QBITTORRENT_USERNAME`,
`MEDIA_BROKER_BIND`, `MEDIA_BROKER_BIND_HOST`,
`MEDIA_BROKER_ALLOW_PUBLIC_BIND`, and optional `MEDIA_BROKER_SECRETS_DIR`.
These values are URLs, the nonsecret qBittorrent WebUI username, nonsecret
bind settings, and a host directory path.
Compose fixes the secret-file paths (including the qBittorrent WebUI password),
the Host/Origin allow-lists, the
response bound, the three write gates
(`MEDIA_BROKER_ENABLE_REQUESTS`, `MEDIA_BROKER_ENABLE_DELETES`, and
`MEDIA_BROKER_ENABLE_RESEEDS`, all enabled), and the reseed save-path
allow-list (`QBITTORRENT_RESEED_SAVE_PATHS`). Never put a backend API key or broker bearer value in Portainer's
stack variables, Compose environment, Git, or command arguments.

## Gated write tools

Beyond the twelve read tools (inventory, quality profiles, root folders,
catalogue candidate search, the season and album detail inventories, both
play-history tools, the Jellyfin users list, and the three read-only
qBittorrent torrent tools), the broker exposes eight
write tools because the Compose environment enables all three gates.
`arr_request_media` adds one catalogue-resolved candidate per call — with an
optional season selection for Sonarr, so a trial add can monitor and search
season one only — and `arr_search_item` queues an upstream search for one
item's monitored missing content; both take effect immediately.
`arr_unmonitor_media` unmonitors one item, `arr_monitor_media` reverses it,
and `arr_set_season_monitoring` (Sonarr) and `arr_set_album_monitored`
(Lidarr) reversibly flip monitoring below the item level. `arr_delete_media`
always runs in two phases: a preview call returns a signed confirmation token
that expires after five minutes and is bound to the exact service, item,
album, and file mode; only a second call carrying that token deletes. For
Lidarr an optional album id deletes a single album instead of the artist,
with the preview showing both album and artist titles. Import-list exclusions
are never added, so exclusion lists stay operator-managed.

## Torrent client visibility

With `QBITTORRENT_URL`, `QBITTORRENT_USERNAME`, and the password file set, the
broker registers three read-only qBittorrent tools: `torrent_client_stats`,
`torrent_client_inventory`, and `torrent_client_check_paths`. They exist for
ratio and reseed audits: verifying tracker-reported seeding state against the
client and checking which re-add candidates still have complete data. The
broker logs in to the WebUI server-side and caches the session cookie. The
read tools issue no writes to the client. ai-dev gains no new egress: Hermes
still reaches only the broker.

## Torrent reseeds

`MEDIA_BROKER_ENABLE_RESEEDS` registers `torrent_client_reseed`, which re-adds
one `.torrent` file over data already on disk and starts it only after a full
recheck verifies every piece. The broker adds it stopped, tagged
`media-broker-reseed`, throttled to 1 B/s, with an explicit save path, then
rechecks it. A verified torrent is started (`reseeding`). Anything else is
removed with its data kept (`aborted_incomplete`), and a torrent the broker did
not add is never touched (`already_present`). A recheck that outlasts the call
reports `checking`, and replaying the same call resumes it, so a whole batch
can be re-run after any interruption.

The only allowed save path is `/data/torrents/music`, the music category's
path as qBittorrent sees it through its `/mnt/data/torrents` bind. The broker
refuses to reseed while qBittorrent appends an extension to incomplete files,
or while excluded file names and the unwanted folder are both enabled, because
an incomplete recheck would then rename or move files on disk. Both are off
today; keep them off. The media-broker repository README documents the full
flow and its one residual risk: a reseeded torrent announces to the trackers
named in the supplied metainfo.

The fixed endpoint is `http://docker-host:8765/mcp`, with Host
`docker-host:8765` and Origin `http://docker-host:8765`. The host port binds
only the docker-host Tailscale IPv4. It is not exposed through Traefik, a LAN
exception, or shared port 443. The broker runs nonroot with a read-only
filesystem and has no Docker socket or media mounts.

## Host-side controls that remain

- The seven files in `/etc/media-broker/secrets` (`broker-token`,
  `sonarr-api-key`, `radarr-api-key`, `lidarr-api-key`, `tautulli-api-key`,
  `jellyfin-api-key`, `qbittorrent-password`)
  stay host-managed: directories `root:65532` mode `0750`, files
  `root:65532` mode `0640`. File-backed Compose secrets do not enforce their
  declared ownership or mode, so verify these after any host rebuild.
  `qbittorrent-password` holds the password of the qBittorrent WebUI account
  named by `QBITTORRENT_USERNAME`; rotate both together.
  Future ai-dev Ansible runs require the existing bearer as
  `hermes_media_broker_token` through protected variables.
- qBittorrent's WebUI Host-header validation must accept the broker's direct
  `qbittorrent:8080` authority; the Traefik hostname fronting already forces
  that setting off, so this is a verification step, not a change.
- The host firewall admits TCP 8765 only from ai-dev's exact Tailscale
  address through `tailscale0`; the `docker-host` role defines and asserts
  the `DOCKER-USER` rules on every run.
- The broker uses a 5 MiB upstream-response bound for the observed 2.27 MiB
  Lidarr inventory.

## One-time migration runbook

Performed once, from the old manual stack to the Git stack. Steps 3 onward
assume the pull request introducing `docker/media-broker/compose.yml` has
already merged, because Portainer resolves that path from `refs/heads/main`.

1. Merge that pull request to `main` and confirm the Compose file resolves
   there.
2. Ensure the first image exists: the media-broker repository's `publish`
   job must have run on `main` so GHCR serves
   `ghcr.io/mich-murphy/media-broker:main`.
3. In Portainer, add `ghcr.io` registry credentials with pull access to the
   private package (classic PAT with `read:packages`). Skip this step if the
   package is made public.
4. Delete the existing `media-broker` stack (brief downtime; the old
   container name `media-broker-candidate` goes away with it). Do not delete
   host secret files.
5. Recreate the stack from Git: repository
   `https://github.com/mich-murphy/home-infra.git`, reference
   `refs/heads/main`, compose path `docker/media-broker/compose.yml`, the
   same nonsecret environment values as before, AutoUpdate polling enabled on
   the shared source. No relative-path volumes are needed for this stack.
6. Wait for the container to become healthy, then verify: the running image
   is the current `:main` build; authenticated calls from Hermes succeed for
   the nineteen registered tools; unauthenticated requests are rejected; a
   different client is denied. Retain the existing ACL and token. No Hermes
   gateway restart is required.
7. Confirm Renovate opens and automerges the initial digest-pin PR for the
   image, and that Portainer redeploys on it. From then on, every
   media-broker merge becomes a Renovate digest bump → automerge → Portainer
   redeploy. If Renovate cannot resolve the digest, its token lacks
   `read:packages` for the private package — fix the token before relying on
   the pipeline.

Jellyfin playback reporting and the gated writes (requests, deletes, and
reseeds) are all enabled — the
broker is no longer read-only, so the confirmation flow above covers every
destructive path. Host controls are operational policy, not a security
boundary against root administrators.
