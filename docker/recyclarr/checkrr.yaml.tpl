# Checkrr configuration template. See docs/checkrr.md for how this is
# deployed, how secrets are injected, and how to run a one-off scan.
#
# The __RADARR_API_KEY__ / __SONARR_API_KEY__ placeholders are substituted by
# entrypoint.sh from the RADARR_API_KEY / SONARR_API_KEY environment
# variables at container start; the rendered file only ever exists in the
# container's tmpfs /tmp, never on disk or in Git.
#
# Checkrr has no native env-var or secrets-file config mechanism (confirmed
# against upstream source: config is loaded only via koanf's plain YAML file
# provider, no env provider or `${VAR}`/`!env_var` support like Recyclarr
# has), hence the sed-based template/render step in entrypoint.sh.
---
lang: "en-us"
checkrr:
  # Radarr/Sonarr mount /mnt/data (host) at /data in their own containers, so
  # these paths already match what Radarr/Sonarr report as file/root-folder
  # paths. No `mappings:` translation is required.
  #
  # /data/media/youtube is intentionally included even though nothing below
  # matches it to an arr instance: Checkrr only ever calls an arr's delete API
  # for a path that matches one of that arr's registered root folders
  # (Sonarr/Radarr.MatchPath). No arr instance here has a youtube root folder,
  # so youtube files are always ffprobe/ffmpeg-checked and any failure is only
  # ever recorded (csvfile/db/logs) - never deleted, never reported to an arr.
  # This is Checkrr's only "report-only" mode; it is not a dedicated flag.
  checkpath:
    - /data/media/movies
    - /data/media/tv
    - /data/media/youtube
  database: /data/checkrr.db
  debug: false
  csvfile: /data/badfiles.csv
  # Runs once a day. New imports are picked up on the next run because they
  # have no prior hash in the bbolt database; unchanged files are skipped
  # after their first successful check via a fast imohash comparison, so
  # only new/changed files pay the full ffprobe/ffmpeg-full cost on any
  # given day.
  cron: "@daily"
  ignorehidden: true
  # Left off deliberately: some legitimate rips (commentary-free trailers,
  # a handful of silent-era or music-only files) have no audio stream, and
  # a false positive here is deleted via Radarr/Sonarr, not just logged.
  # Enable only after confirming the library has no such files.
  requireaudio: false
  # ffprobe alone only reads container/stream headers - this is what let the
  # motivating incident's file pass (see docs/checkrr.md). ffmpeg-full runs
  # `ffmpeg -v error -i <file> -f null -`, a full demux+decode of every frame
  # in the file, which is what actually caught that incident's ~18 scattered
  # EBML structural errors. ffmpeg-quick is left off because it only reads
  # the first `ffmpeg-quick-seconds`, which would have missed errors later in
  # the file body.
  ffmpeg-full: true
  ffmpeg-quick: false
  ffprobe: true
  # No removevideo/removeaudio/removelang codec-preference deletions here:
  # this deployment is scoped to corruption detection only, not library
  # transcoding policy.
  ignoreexts:
    - .nfo
    - .txt
    - .nzb
    - .url
    - .srt
    - .ass
    - .sub
    - .idx
    - .jpg
    - .jpeg
    - .png
logs:
  stdout:
    out: stdout
    formatter: default
arr:
  radarr:
    process: true
    service: radarr
    address: radarr
    apikey: __RADARR_API_KEY__
    baseurl: /
    port: 7878
    ssl: false
  sonarr:
    process: true
    service: sonarr
    address: sonarr
    apikey: __SONARR_API_KEY__
    baseurl: /
    port: 8989
    ssl: false
