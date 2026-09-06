# Subtitle Manager Selection

<!-- markdownlint-disable MD013 -->

## Decision

Deploy Bazarr as the subtitle manager for the existing Sonarr, Radarr, and
Jellyfin stack. Bazarr is the best fit because it is purpose-built as a Sonarr
and Radarr companion, supports OpenSubtitles.com, language profiles, wanted
queues, upgrades, scoring, and subtitle synchronization, and can notify
Jellyfin immediately after subtitle changes. Its project and LinuxServer image
also have a substantially longer operating history than the newer candidates:
the LinuxServer image history begins in 2018.

Sources:

- [Bazarr project](https://github.com/morpheus65535/bazarr)
- [Bazarr settings reference](https://wiki.bazarr.media/Additional-Configuration/Settings/)
- [Bazarr Jellyfin integration](https://wiki.bazarr.media/Additional-Configuration/Jellyfin/)
- [LinuxServer Bazarr image](https://docs.linuxserver.io/images/docker-bazarr/)

This is a selection for conventional English sidecar acquisition, not
transcription or translation. Do not deploy Whisper, Subgen, or another AI
service as part of this change.

## Comparison

| Option | Role and strengths | Decision |
| --- | --- | --- |
| Bazarr | Dedicated Sonarr/Radarr companion with per-title language requirements, providers, scoring, wanted searches, upgrades, synchronization, and direct Jellyfin refresh. | Deploy. It offers the most complete established workflow for this stack. |
| Jellyfin Open Subtitles | Official Jellyfin catalog plugin that downloads from Open Subtitles and supports per-library language configuration. | Simpler alternative when subtitle download at the media-server layer is sufficient. It does not replace Bazarr's Sonarr/Radarr-centered wanted, profile, upgrade, scoring, and synchronization workflow. |
| SubBuzz | Third-party Jellyfin/Emby subtitle plugin supporting multiple subtitle sites. | Simpler Jellyfin-local alternative, but not the selected library-management workflow. |
| Subgen | Whisper-based subtitle generation that can receive Bazarr requests or Jellyfin webhooks and can refresh Jellyfin after generation. | AI adjunct for media with no usable provider subtitle, not a replacement for provider-first management. Out of scope because transcription adds compute cost and generated-text quality review. |
| Sublarr | Newer self-hosted manager with Sonarr, Radarr, Jellyfin, provider search, scoring, synchronization, and optional experimental LLM translation. | Promising, especially for anime and translation, but not yet as established as Bazarr. Re-evaluate after it has a longer production and release history. |

Sources:

- [Jellyfin plugin catalog](https://jellyfin.org/docs/general/server/plugins/)
- [Jellyfin Open Subtitles source](https://github.com/jellyfin/jellyfin-plugin-opensubtitles)
- [SubBuzz source](https://github.com/josdion/subbuzz)
- [Subgen source and configuration](https://github.com/McCloudS/subgen)
- [Sublarr project site](https://sublarr.de/en/)
- [Sublarr FAQ](https://sublarr.de/en/faq/)

The maturity judgment is deliberately relative. Sublarr describes its search,
scoring, and *arr integration as production-ready, but its 1.0 announcement
dates to June 2026; Bazarr and its maintained container image have years of
published history. Sublarr's own documentation still labels LLM translation
experimental.

## Configuration Rationale

### Integration and storage

- Keep Bazarr dependent on Sonarr and Radarr rather than treating it as a
  standalone filesystem scanner. The upstream project defines Bazarr as their
  companion application, and the Jellyfin integration also requires them.
- Mount the shared media path as `/data/media`, matching the paths Sonarr and
  Radarr report. Bazarr documents path mappings as necessary only when the
  applications see the same file through different paths.
- Store subtitles alongside media, which Bazarr recommends. Re-encode downloads
  as UTF-8 so the sidecars have consistent text encoding.
- Run with the media UID/GID so newly written sidecars remain accessible to the
  media applications. LinuxServer documents `PUID` and `PGID` specifically for
  host-volume ownership.
- Keep the Bazarr UI and configuration volume private. Enable Bazarr form
  authentication behind Traefik TLS, and enter provider and API credentials
  interactively so no credentials are committed to Git.

Sources:

- [Bazarr settings reference](https://wiki.bazarr.media/Additional-Configuration/Settings/)
- [Bazarr Jellyfin integration](https://wiki.bazarr.media/Additional-Configuration/Jellyfin/)
- [LinuxServer PUID and PGID guidance](https://docs.linuxserver.io/general/understanding-puid-and-pgid/)

### Language and coverage

- Create one English language profile with forced set to `Both`. Bazarr defines
  this as requesting both normal subtitles and forced subtitles, where forced
  subtitles cover foreign or alien speech and otherwise untranslated on-screen
  text.
- Apply the profile by default to new series and movies. Validate a small sample
  before mass-assigning it to the existing indexed library.
- Treat suitable embedded text subtitles as coverage, while enabling
  `Ignore Embedded PGS Subtitles`. Bazarr exposes that combination explicitly;
  it avoids downloading duplicate text coverage while not allowing an
  image-based PGS track to satisfy the external-text requirement.
- Include unmonitored Sonarr and Radarr items so the one-time backfill covers the
  entire indexed library.

Source: [Bazarr settings reference](https://wiki.bazarr.media/Additional-Configuration/Settings/)

### Search quality and load

- Use OpenSubtitles.com as the sole provider for this deployment. This is an
  intentional simplicity tradeoff: it creates a single-provider availability
  risk, and the account has a finite download allowance.
- Set minimum match scores to 90 for episodes and 80 for movies. These are
  site-specific quality thresholds, not upstream defaults.
- Synchronize automatically only below 96 for episodes and 86 for movies. This
  targets weaker accepted matches and avoids spending CPU and NFS bandwidth on
  stronger matches. Bazarr warns that synchronization may extract audio and can
  consume substantial CPU and network resources.
- Enable adaptive searching so repeatedly unsuccessful items are queried less
  often. Enable upgrades for Bazarr-downloaded subtitles so later, better
  matches can replace earlier downloads.
- Backfill through the wanted queue gradually and inspect the first scheduled
  cycle. OpenSubtitles reports a remaining download allowance through its API,
  so avoid an unrestricted first-run burst.

Sources:

- [Bazarr performance tuning](https://wiki.bazarr.media/Additional-Configuration/Performance-Tuning/)
- [Bazarr settings reference](https://wiki.bazarr.media/Additional-Configuration/Settings/)
- [OpenSubtitles API documentation](https://ai.opensubtitles.com/docs)

### Jellyfin refresh

Connect with a dedicated Jellyfin API key, select the movie and TV libraries,
enable refresh for both, and choose `Immediate`. Bazarr documents that this
method re-reads the affected item's metadata immediately without contacting
external metadata providers; the asynchronous method instead sends a filesystem
notification that Jellyfin handles later.

Source: [Bazarr Jellyfin integration](https://wiki.bazarr.media/Additional-Configuration/Jellyfin/)

## Interactive Setup

Keep all credentials in Bazarr's named configuration volume rather than in
Compose or Git. After deploying only the `bazarr` stack in Portainer:

1. Open `https://bazarr.local.elmurphy.com`, enable Bazarr form authentication,
   and set the UI credentials.
2. Enable Sonarr at `http://sonarr:8989` and Radarr at
   `http://radarr:7878`, enter their API keys, enable inclusion of unmonitored
   items, and leave path mappings empty.
3. Add OpenSubtitles.com as the only provider and enter its account credentials.
4. Configure subtitle storage beside the media, UTF-8 encoding, embedded
   subtitle detection, and `Ignore Embedded PGS Subtitles`.
5. Create an English profile with normal and forced subtitles (`Both`). Make it
   the default for new series and movies, but initially assign it only to the
   validation sample.
6. Set minimum scores to 90 for series and 80 for movies. Enable automatic
   synchronization below 96 for series and 86 for movies, adaptive searching,
   and upgrades of subtitles downloaded by Bazarr.
7. Add Jellyfin at `http://jellyfin:8096` with a dedicated API key. Select the
   movie and TV libraries, enable updates for both, and select immediate
   refresh.
8. After the validation sample passes, mass-assign the English profile to all
   existing series and movies. Let the wanted queue backfill gradually and
   monitor the provider allowance.

## Operational Validation

Before assigning the profile library-wide:

1. Test connections to Sonarr, Radarr, OpenSubtitles.com, and Jellyfin.
2. Download subtitles for one movie and one episode, including a known forced
   subtitle case.
3. Confirm the sidecars are correctly named, UTF-8 encoded, stored beside the
   media, and owned by UID/GID 1215.
4. Confirm Jellyfin exposes each track immediately without a full-library scan.
5. Confirm existing embedded text subtitles are not duplicated and embedded PGS
   does not prevent acquisition of external text.
6. Exercise a match in the synchronization window and inspect CPU and NFS
   activity.
7. Monitor the first scheduled wanted search for quota, permissions, provider,
   and timing errors.
