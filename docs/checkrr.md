# Checkrr

<!-- markdownlint-disable MD013 -->

Checkrr scans the media library for corrupt files and, when it can identify
the file as a tracked Radarr or Sonarr download, deletes it through that
app's own API and lets the app re-search and re-download it. It runs as its
own daemon in the `recyclarr` Portainer stack, on the `proxy` network, talking
to `http://radarr:7878` and `http://sonarr:8989` the same way Recyclarr does.

## Why this exists

An episode file imported cleanly through Sonarr (WEB-DL MKV, 3.1 GB) but had
about 18 Matroska structural errors ("invalid as first byte of an EBML
number") scattered through the file body. `ffprobe` against the file's
headers passed. Only a full packet-level demux
(`ffmpeg -v error -i FILE -c copy -f null -`) surfaced the errors. Neither
Radarr nor Sonarr detect this class of corruption on import.

Checkrr's `ffprobe` check (upstream `check/checkrr.go`, `ffProbe` branch) only
calls `ffprobe.ProbeURL`, i.e. header/stream metadata - the same check that
missed the incident. Checkrr's `ffmpeg-full` check runs:

```console
ffmpeg -v error -i <file> -hwaccel auto -f null -
```

a full demux and decode of every frame with no output, which is functionally
the same check that caught the incident (upstream doesn't pass `-c copy`, so
it also fully decodes rather than just demuxing - a strictly stronger check).
This deployment enables `ffmpeg-full` for that reason; see
`docker/recyclarr/checkrr.yaml.tpl` for the full check rationale.
`ffmpeg-quick` (first N seconds only) is deliberately left off because the
incident's errors were scattered through the file body, not the start.

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

Checkrr has no native environment-variable or `${VAR}`/secrets-file config
mechanism (confirmed against upstream source: `main.go` only loads config via
koanf's plain YAML `file.Provider`, no env provider, no `!env_var` tag like
Recyclarr's). `docker/recyclarr/checkrr.yaml.tpl` is checked into Git with
`__RADARR_API_KEY__`/`__SONARR_API_KEY__` placeholders instead of real keys.
`docker/recyclarr/checkrr-entrypoint.sh` substitutes the `RADARR_API_KEY`/
`SONARR_API_KEY` environment variables (set on the Portainer stack) into
those placeholders with `sed`, writing the result only to
`/tmp/checkrr-runtime.yaml` - a tmpfs mount, never the `checkrr-data` volume
or the repo - before exec'ing `checkrr` against that rendered file.

Required Portainer stack environment values:

| Variable         | Purpose                                     |
| ---------------- | -------------------------------------------- |
| `TZ`             | Container timezone, matches other stacks      |
| `RADARR_API_KEY` | Radarr API key (Settings → General in Radarr) |
| `SONARR_API_KEY` | Sonarr API key (Settings → General in Sonarr) |

## Deployment

The compose file bind-mounts `checkrr.yaml.tpl` and `entrypoint.sh` from this
directory read-only into `/config`, and `/mnt/data/media` read-only into
`/data/media` (matching the path Radarr/Sonarr themselves see, since they
mount `/mnt/data` at `/data` - no Checkrr `mappings:` translation is needed).
State (the bbolt db and `badfiles.csv`) lives on the named `checkrr-data`
volume.

**Before the first deploy**, enable **"Enable relative path volumes"** on the
`recyclarr` stack in Portainer, with **Local filesystem path** `/srv/portainer`
(see [docs/docker-deployment.md](docker-deployment.md)) - without it the
`./checkrr.yaml.tpl` and `./entrypoint.sh` bind mounts resolve to nothing and
the container fails to start (missing config).

The container runs as root (upstream's alpine image has no non-root user);
`cap_drop: [ALL]`, `no-new-privileges`, and a read-only root filesystem
contain it. `deploy.resources.limits` (2 CPUs, 1 GiB) and a reduced
`cpu_shares` keep a full-library `ffmpeg-full` pass from starving other
containers or the NFS-backed media library; Checkrr itself only ever
processes one file at a time (its file walk has no worker pool), so these are
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

- **Baseline pass duration**: the first full-library pass runs `ffmpeg-full`
  against every existing file (nothing has a stored hash yet). At roughly
  1.5-6 minutes per ~3 GB episode observed in testing (see dry-run notes in
  the PR/commit that introduced this stack), a 4.4 TB library could take
  multiple days end-to-end. Subsequent daily runs only re-check new/changed
  files, so this is a one-time cost, but it competes with the docker-host
  VM's other workloads (6 vCPU, 8 GB RAM) and the NFS server for that
  duration. Consider whether to seed the bbolt database or otherwise stage
  the baseline pass (e.g. temporarily narrowing `checkpath` to one library at
  a time) rather than letting the full 4.4 TB scan run unattended
  immediately after first deploy.
- **`requireaudio`** is left `false` deliberately (a false positive here is a
  deletion, not just a log line). Enable only after confirming the library
  has no legitimate audio-less files.
- **Root-user container**: acceptable given the mitigations above, but flag
  if the human wants a differently-built/non-root image instead.
