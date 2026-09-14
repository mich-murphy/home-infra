# Read-only media broker

This project exposes a small MCP server over the official Python SDK's
Streamable HTTP transport. The adapters target Sonarr 4.0.19 (API v3), Radarr
6.3.0 (API v3), Lidarr 3.1.0 (API v1), and Tautulli 2.18.1. It has four tools:

- `arr_library_inventory` (Sonarr, Radarr, or Lidarr; bounded local pagination)
- `arr_quality_profiles`
- `arr_root_folders`
- `tautulli_play_history` (movie, episode, or track; inclusive maximum 31-day range and optional numeric user filter)

There are no write tools, generic upstream requests, approval endpoints, Seerr,
or Jellyfin integrations. Arr APIs return arrays, so inventory pagination is
performed after one bounded response and reports that fact honestly.

## Local run

Create one file for the broker bearer token and one file for each upstream API
key, with restrictive permissions. The environment contains paths only, never
key values:

```sh
export MEDIA_BROKER_TOKEN_FILE=/run/user/1000/media-broker/token
export SONARR_URL=http://127.0.0.1:8989
export SONARR_API_KEY_FILE=/run/user/1000/media-broker/sonarr
export RADARR_URL=http://127.0.0.1:7878
export RADARR_API_KEY_FILE=/run/user/1000/media-broker/radarr
export LIDARR_URL=http://127.0.0.1:8686
export LIDARR_API_KEY_FILE=/run/user/1000/media-broker/lidarr
export TAUTULLI_URL=http://127.0.0.1:8181
export TAUTULLI_API_KEY_FILE=/run/user/1000/media-broker/tautulli
export MEDIA_BROKER_ALLOWED_HOSTS=127.0.0.1:8000
export MEDIA_BROKER_ALLOWED_ORIGINS=http://127.0.0.1:8000
uv run media-broker
```

All four upstreams and all secret files are required. The broker defaults to
loopback binding, HTTPS certificate verification, no redirects, a 10-second
total upstream deadline, and a 2 MB upstream response limit. Host and Origin
values are exact allow-lists; wildcard syntax is rejected. Tautulli requests
use its inclusive `after`/`before` date bounds with `grouping=0` and
`include_activity=0` so each returned row represents a playback event.
All upstreams use `X-Api-Key` header authentication. Tautulli 2.18.1 supports
this header; the broker never includes credentials in query URLs.

History projections contain only scalar, validated fields. The explicitly
approved stable identifiers `tautulli_user_id`, `tautulli_rating_key`, and
`tautulli_history_id` come from Tautulli's `user_id`, `rating_key`, and `id`
fields respectively. They are present for household selection and stable
matching; names, emails, IPs, device identifiers, and unknown fields are not
returned. Tautulli's numeric watched status of `1` means completed; `0`,
`0.25`, `0.5`, and `0.75` mean incomplete. A missing or unrecognized status
is reported as unknown, not false.

Run checks with `uv run --dev pytest` and `uv run --dev ruff check .`.

## Local-only container example

This local-only example is intentionally not wired into the repository's
production deployment and must not be used as a production deployment. The
production candidate Compose file is the inventoried
`deploy/compose.yml`; secret files should be mounted by
the operator; this example has no media or Docker socket mounts. The image runs
as UID/GID 65532, so host-mounted secret files must be readable by that numeric
identity without becoming world-readable (for example, root-owned `0640` files
with group 65532 and a directory traversable by that group, or files owned by
65532 with mode `0400`). Do not put keys in `.env.local-only`; it contains paths
only. Container archive/backup or Docker-proxy access can expose file-mounted
credential contents, which is another reason this example is not production
configuration.

```yaml
services:
  media-broker:
    build: .
    network_mode: host
    env_file: .env.local-only
    volumes:
      - ./secrets:/run/secrets:ro
```

MCP authentication proves possession of the configured bearer token, not human
consent or authorization for a particular media action. The broker is read-only
but upstream credentials and playback titles remain sensitive household data;
keep it on a trusted loopback or private network and review client access.
The production candidate configuration lives at
[`deploy/compose.yml`](deploy/compose.yml). Portainer owns the live stack with
manual updates, no Git workflow, and no automatic redeployment. The required
host preflight, explicit image build, and authenticated update procedure are in
[`docs/hermes-media.md`](../../docs/hermes-media.md). Direct Compose invocation
is unsupported because it bypasses the preflight; this is operational policy,
not a security boundary against root.
