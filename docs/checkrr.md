# Checkrr

<!-- markdownlint-disable MD013 -->

Checkrr scans the media library for corrupt files and, when it can identify
the file as a tracked Radarr or Sonarr download, deletes it through that
app's own API and lets the app re-search and re-download it. It runs as its
own daemon in the `recyclarr` Portainer stack, on the `proxy` network, reaching
Radarr and Sonarr the same way Recyclarr does.

## Why this exists

Matroska structural errors can sit in a file body while the headers stay
valid, so the file imports cleanly through Sonarr and `ffprobe` passes it.
Neither Radarr nor Sonarr detect that class of corruption, and Checkrr's
`ffprobe` check does not either — it reads header and stream metadata only.

This deployment therefore enables `ffmpeg-full`, a full demux and decode of
every frame. `ffmpeg-quick` (first N seconds only) is deliberately left off,
because the errors this exists to catch are scattered through the file body
rather than the start. `docker/recyclarr/checkrr.yaml.tpl` carries the full
check rationale.

## What it checks and how it decides a file is bad

- **Paths**: `/data/media/movies` and `/data/media/tv` (Radarr/Sonarr-managed,
  full checks + auto re-download). `/data/media/youtube` is also scanned, but
  Pinchflat's downloads aren't registered with Radarr or Sonarr, so no arr
  instance's root folder ever matches that path - Checkrr only calls an arr's
  delete API for a path matching one of that arr's registered root folders
  (`Sonarr.MatchPath`/`Radarr.MatchPath` in upstream `connections/`). Corrupt
  YouTube files are always logged (db, `badfiles.csv`, container logs) but
  never deleted or reported anywhere. This is Checkrr's only "report-only"
  behaviour; there's no dedicated dry-run flag, this deployment relies on the
  path-matching side effect instead.
- **Checks run per file**: `ffprobe` (headers/streams) then `ffmpeg-full`
  (full demux+decode). Either producing an error marks the file bad.
- **Incremental scans**: every successfully-checked file gets an `imohash`
  (fast partial-content hash) stored in a bbolt database
  (`/data/checkrr.db`, on the `checkrr-data` volume). On the next run, a file
  whose hash still matches is skipped entirely - only new or changed files
  pay the full `ffprobe`/`ffmpeg-full` cost. This is what makes the daily
  cron affordable against a multi-TB library after the first pass.
- **Schedule**: `cron: "@daily"` (once a day). A newly-imported file has no DB
  entry yet, so it is always fully checked on the next run - within 24 hours
  of import, per the requirement that new imports get checked promptly.

## What happens to a corrupt file, end-to-end

1. `ffprobe` or `ffmpeg-full` reports an error for the file.
2. Checkrr asks the matching arr instance (by comparing the file's path
   against that arr's registered root folders) for the tracked
   episode/movie file record.
3. If found, it calls that arr's `DeleteEpisodeFile`/`DeleteMovieFile` API,
   then sends `RescanSeries`/`RescanMovie` and `SeriesSearch`/`MoviesSearch`
   commands - Radarr/Sonarr handle the actual on-disk delete and re-download
   from there, through the app's normal search/grab/import pipeline.
4. If no match is found (untracked file, e.g. an `.nfo`/subtitle sidecar or
   anything under `/data/media/youtube`), Checkrr never deletes anything
   itself - it has no direct filesystem-delete path for media files; deletion
   only ever happens through a matched arr's own API. The file is just
   recorded as bad (db + `badfiles.csv`) for manual follow-up.

This means a corrupt file is only ever deleted when Checkrr can hand the
re-download to Radarr or Sonarr, satisfying the "never delete otherwise"
requirement by the tool's own architecture, not by a flag this deployment has
to remember to set.

## Secrets

Checkrr has no native environment-variable or secrets-file config mechanism,
so `checkrr.yaml.tpl` is checked in with placeholders and the entrypoint
substitutes the API keys at start-up, writing the rendered config only to a
tmpfs path — never to the `checkrr-data` volume or the repo.

`docker/recyclarr/compose.yml` declares the environment values the stack
requires: a timezone and the Radarr and Sonarr API keys. Set them on the
Portainer stack.

## Deployment

The compose file bind-mounts `checkrr.yaml.tpl` and `entrypoint.sh` from this
directory read-only into `/config`, and `/mnt/data/media` read-only into
`/data/media` (matching the path Radarr/Sonarr themselves see, since they
mount `/mnt/data` at `/data` - no Checkrr `mappings:` translation is needed).
State (the bbolt db and `badfiles.csv`) lives on the named `checkrr-data`
volume.

**Before the first deploy**, enable **"Enable relative path volumes"** on the
stack in Portainer — see [docs/docker-deployment.md](docker-deployment.md).

The container's resource limits keep a full-library `ffmpeg-full` pass from
starving other containers or the NFS-backed media library. Checkrr processes
one file at a time — its file walk has no worker pool — so the limits are
upper bounds, not a concurrency setting.

## Running a one-off scan and reading the report

The daemon already runs `@daily`; to check on demand:

```console
docker exec checkrr /checkrr -c /tmp/checkrr-runtime.yaml --run-once -d
```

This reuses the config the running container already rendered from its
environment (no secrets are re-entered). `-d` adds debug logging.

Read the results:

```console
# Live/most recent run log
docker logs checkrr

# Every file Checkrr has ever flagged bad, with reason and timestamp
docker exec checkrr cat /data/badfiles.csv
```

A `reacquire` log line and a `badfiles.csv` row with `reacquire: true` means
Radarr/Sonarr was told to delete and re-search the file. `reacquire: false`
means it was logged only (untracked file, most commonly a YouTube file or a
sidecar Checkrr didn't recognize).

## Open questions before first deploy

- **Baseline pass duration**: the first full-library pass checks every
  existing file and can run for days, competing with the docker-host VM's
  other workloads and the NFS server. Stage it — narrow `checkpath` to one
  library at a time — rather than letting it run unattended after first
  deploy. Subsequent daily runs only re-check new or changed files.
- **`requireaudio`** is left `false` deliberately (a false positive here is a
  deletion, not just a log line). Enable only after confirming the library
  has no legitimate audio-less files.
- **Root-user container**: acceptable given the mitigations above, but flag
  if the human wants a differently-built/non-root image instead.
