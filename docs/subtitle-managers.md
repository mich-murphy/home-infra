# Subtitle manager selection

<!-- markdownlint-disable MD013 -->

## Decision

Deploy Bazarr as the subtitle manager for the existing Sonarr, Radarr, and
Jellyfin stack. It is purpose-built as a Sonarr and Radarr companion and is the
only candidate offering the complete wanted-queue, scoring, upgrade and
synchronization workflow this stack needs.

Jellyfin Open Subtitles, SubBuzz, Subgen and Sublarr were evaluated and not
adopted. Re-evaluate Sublarr once it has a longer production history.

This is a selection for conventional English sidecar acquisition, not
transcription or translation. Do not deploy Whisper, Subgen, or another AI
service as part of this change.

## Intended configuration

Bazarr's configuration lives in its own volume and UI, not in Git, so this is
the only record of intended state.

- Depends on Sonarr and Radarr rather than scanning the filesystem standalone.
  Media is mounted at `/data/media`, matching the paths Sonarr and Radarr
  report, so no path mappings are needed.
- Subtitles are stored beside the media, re-encoded as UTF-8, and written with
  the media UID/GID so the media applications retain access.
- Form authentication is enabled behind Traefik TLS. Provider and API
  credentials are entered interactively and never committed.
- One English language profile with forced set to `Both`, default for new
  series and movies, applied to a validation sample before the library-wide
  backfill. Unmonitored Sonarr and Radarr items are included so the backfill
  covers the whole indexed library.
- Embedded text subtitles count as coverage, with `Ignore Embedded PGS
  Subtitles` enabled so an image-based track cannot satisfy the external-text
  requirement.
- OpenSubtitles.com is the sole provider. This is an intentional simplicity
  tradeoff: single-provider availability risk, and a finite download allowance,
  so the wanted-queue backfill runs gradually rather than as one burst.
- Minimum match scores 90 for episodes and 80 for movies — site-specific
  thresholds, not upstream defaults. Automatic synchronization only below 96
  and 86 respectively, because synchronization may extract audio and can
  consume substantial CPU and NFS bandwidth.
- Adaptive searching and upgrades of Bazarr-downloaded subtitles are enabled.
- Jellyfin is connected with a dedicated API key, with refresh enabled for the
  movie and TV libraries and set to `Immediate`, which re-reads the affected
  item without contacting external metadata providers.
