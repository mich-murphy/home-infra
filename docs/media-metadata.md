# Media metadata and library integrity

<!-- markdownlint-disable MD013 -->

How Radarr, Sonarr, Jellyfin and Plex agree on what a file is, and how broken
files are caught. These settings live in the applications (Docker volumes),
not in Git, so this page is the record of the intended state.

## Identity flows from the download managers

- Radarr and Sonarr name folders with the provider id (`{tmdb-…}` for movies,
  `{tvdb-…}` for series) and write Kodi/Emby NFO sidecars with the same ids
  (Settings → Metadata → Kodi (XBMC) / Emby, metadata on, images off). The
  media servers read those ids instead of guessing from titles, which is what
  produced remakes matched to the original.
- Both apps have Connect notifications to Plex and Jellyfin with "Update
  Library" on for import, upgrade, rename and delete, so the affected folder is
  rescanned immediately. NFS does not deliver inotify events, so this is the
  primary trigger; Plex additionally runs a scheduled scan every six hours.

## Jellyfin

| Library | Type | Path | Metadata |
| --- | --- | --- | --- |
| Movies | movies | `/data/media/movies` | NFO first, then TheMovieDb and OMDb (internet providers on) |
| TV | tvshows | `/data/media/tv` | NFO first, then TheTVDB, TheMovieDb, OMDb (internet providers on) |
| YouTube | tvshows | `/data/media/youtube/shows` | NFO only (internet providers off) |
| Music | music | `/data/music` | MusicBrainz and TheAudioDB |

Internet providers must stay off for YouTube: Pinchflat writes `tvshow.nfo`
and per-video NFOs with a `youtube` unique id, and any online provider will
match a channel name to an unrelated TV series whose title happens to collide.
Channel items must carry only the `youtube` id.

The TheTVDB plugin is installed because TheMovieDb has no episode titles for
some long-running series and talk shows. When titles are missing after a
provider change, refresh the series with "Replace all metadata"; a plain
refresh keeps the existing placeholder name.

## Plex

| Section | Type | Agent | Notes |
| --- | --- | --- | --- |
| Movies | movie | Plex Movie | honours `{tmdb-…}` in folder names |
| TV | show | Plex TV Series | aired order |
| YouTube | show (hidden) | Plex NFO Series | one show per channel folder, seasons flattened |
| Music | artist (hidden) | Plex Music | |

The YouTube section must use the NFO agent. With the online TV agent every
channel's videos were pooled into one show because Pinchflat's date-based
episode numbers collide across channels. Changing the agent on an existing
section does not split the pooled show; the section had to be deleted and
re-created (watched state comes back from Jellyfin via jellyplex-watched).

Unmatched movies (`local://` guid) are usually new imports the agent has not
matched yet; "Refresh metadata" on the item matches it from the folder id.

## File integrity

Radarr and Sonarr validate only container headers on import, so body-level
corruption imports cleanly. There is no automated integrity scan; a corrupt
file surfaces as playback failure. To fix one by hand: delete the episode or
movie file in the app,
mark the grab as failed in History (this blocklists the release) and search
again, then verify the replacement plays through.

## Jellyfin container mounts

Music is mounted once, at `/data/music`, which is the library path. Keep
nested bind mounts out of read-only binds: a nested mount that depends on a
directory existing inside the read-only share stops the container starting the
moment that directory disappears.
