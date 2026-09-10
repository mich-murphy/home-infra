# Recyclarr

<!-- markdownlint-disable MD013 -->

Recyclarr keeps Radarr and Sonarr custom formats and quality profiles in sync
with `docker/recyclarr/recyclarr.yml` instead of being hand-edited in each
app's UI. It runs on a cron schedule inside the `recyclarr` Portainer stack
and talks to Radarr and Sonarr over the internal `proxy` network
(`http://radarr:7878`, `http://sonarr:8989`); it has no web UI of its own.

## What Recyclarr manages

- **Quality profiles** are guide-backed: `recyclarr.yml` references the TRaSH
  Guides profile by `trash_id` (Radarr `WEB 1080p`, Sonarr `WEB-1080p`) and
  Recyclarr pulls the quality order, cutoff, upgrade settings, scores and the
  guide's default custom format groups (Unwanted Formats, Golden Rule HD,
  Streaming Services) from the guide. Only deliberate deviations are written as
  overrides:
  - `WEB 1080p (Dual Audio)` / `WEB-1080p (Dual Audio)` are named variants of
    the same guide profile for non-English titles. Bluray-1080p is merged into
    the 1080p cutoff group so it ranks equal to WEB 1080p; Radarr and Sonarr
    only compare custom format scores between equally ranked qualities, so a
    dual-audio Bluray can replace an original-only WEB file without Bluray
    ever counting as a plain quality upgrade or downgrade.
  - Sonarr `WEB-1080p` keeps the previous guide's fallback qualities
    (Bluray-1080p, HDTV-1080p, 720p) allowed because 177 existing episode
    files use them. Remove that `qualities:` block to adopt the pure guide
    profile; Sonarr will then queue those episodes for upgrade.
  - The stock `Any`, `Any (Dual Audio)`, `HD-1080p` and `HD - 720p/1080p`
    profiles carry only the language guards and the dual-audio bonus.
- **Scores are authoritative.** `reset_unmatched_scores` is enabled on every
  managed profile, so a score set in the UI for a format that is not in
  `recyclarr.yml` is reset to 0 on the next sync.
- **Custom formats** come from the guide's groups plus the `Wrong Language`
  format from the language group (the group's default `Language: Not Original`
  is excluded because it duplicates it). Two bespoke formats,
  `Dual Audio (Original + English)` and `Dual Audio (Release Title)`, are not
  published by TRaSH Guides; their specifications live in
  `docker/recyclarr/custom-formats/{radarr,sonarr}/*.json` and are registered
  as local `resource_providers` in `docker/recyclarr/settings.yml`, so they are
  referenced by a `local-...` trash ID like any guide format.
- **Quality definitions** follow the guide's `movie` and `series` size tables.
  At adoption these matched the live values (the guide's current maximums are
  effectively unlimited).

## What stays manual

- **Media naming**: the live naming formats don't match any TRaSH Guides
  preset and syncing them would rename the whole library. `media_naming` is
  left out so Recyclarr never touches it.
- **Radarr quality profile language** (`Original` on the two WEB 1080p
  profiles) is synced from the guide profile; the stock `Any` profile's
  language stays manual. Language preference is otherwise expressed through
  the custom formats above.
- **Delay profiles, indexers, download clients, and root folders** are
  entirely outside Recyclarr's scope and stay manual in Radarr/Sonarr/Prowlarr.
- **Lidarr** is not supported by Recyclarr at all (confirmed against upstream
  docs — Recyclarr only targets Radarr and Sonarr). Lidarr custom formats and
  quality profiles remain fully manual.
- **Unscored streaming-service formats** in Radarr (AMZN, NF, ...) exist only
  so the file naming format can print them; `delete_old_custom_formats` stays
  `false` so Recyclarr never removes them.

## Deployment

The compose file bind-mounts `recyclarr.yml`, `settings.yml`, and
`custom-formats/` from this directory read-only into `/config`, over the named
`recyclarr-data` volume that holds Recyclarr's own state (guide cache and
logs). This follows the same pattern as the `nextcloud` stack's
`./post-installation.sh` bind mount.

**Before the first deploy**, enable **"Enable relative path volumes"** on the
`recyclarr` stack in Portainer (see
[docs/docker-deployment.md](docker-deployment.md)) — without it the `./`
bind mounts resolve to nothing and the container starts with no
configuration.

Required Portainer stack environment values:

| Variable         | Purpose                                              |
| ---------------- | ----------------------------------------------------- |
| `TZ`             | Container timezone, matches other stacks               |
| `RADARR_API_KEY` | Radarr API key (Settings → General in Radarr)          |
| `SONARR_API_KEY` | Sonarr API key (Settings → General in Sonarr)          |
| `CRON_SCHEDULE`  | Optional; defaults to `0 4 * * *` (daily at 04:00)      |

## Previewing and syncing

Recyclarr runs `sync` automatically on `CRON_SCHEDULE`. To check what a sync
would do without changing anything in Radarr or Sonarr, run a preview from
inside the running container:

```console
docker exec recyclarr recyclarr sync --preview
```

`--preview` still calls the Radarr/Sonarr APIs to fetch current state, but
never calls an API that changes it. Always review preview output before
letting a changed `recyclarr.yml` sync for the first time.

## First-sync caution

The first sync takes ownership of the profiles and custom formats above.
Preview it first (`sync --preview`, with `--log debug` to see the per-format
diff; Recyclarr 8 reports only a summary at the default level). When this
stack was introduced the preview showed:

- Radarr: four new unwanted formats scored -10000 on both 1080p profiles (Bad
  Dual Groups, Black and White Editions, Line/Mic Dubbed, Upscaled). No quality,
  cutoff or size changes.
- Sonarr: the same two unwanted formats that exist for series (Bad Dual Groups,
  Upscaled), streaming-service scores moved from the old guide's tiered values
  to the current flat 75, three new streaming formats (ATV, PLAY, ROKU) and the
  HD/UHD Streaming Boost formats at 75, and the `Bluray + WEB 1080p` group
  created on the Dual Audio profile.

Both servers' `Repack v2`/`Repack v3` and Radarr's `Remux + WEB 1080p`
profiles were renamed to the guide names (`Repack2`/`Repack3`, `WEB 1080p`)
before adoption so Recyclarr updates them in place instead of creating
duplicates. `delete_old_custom_formats: false` means nothing is ever deleted;
formats not listed here are left untouched apart from their score being reset
to 0 on managed profiles.
