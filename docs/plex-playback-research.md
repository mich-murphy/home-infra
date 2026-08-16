# Plex Playback and Transcoding Update Research

Research date: 2026-07-30 (Australia/Melbourne).

## Conclusion

There is no Plex Media Server update newer than the deployed
`1.43.3.10828-00f62d37d`.

Plex's official downloads API returns that exact version for both the
[public channel](https://plex.tv/api/downloads/5.json?channel=public) and the
[Plex Pass channel](https://plex.tv/api/downloads/5.json?channel=plexpass).
The official Docker registry also identifies
`1.43.3.10828-00f62d37d` as the newest versioned image and points `latest` at
the image published on 2026-07-14
([Docker Hub API](https://hub.docker.com/v2/repositories/plexinc/pms-docker/tags?page_size=100&ordering=last_updated)).
Plex announced the same build for all users on 2026-07-14
([official release announcement](https://forums.plex.tv/t/plex-media-server/30447?page=36)).

Consequently, there is no available server release that can be claimed to fix
the observed browser playback stalls, DASH segment timeouts, audio-remux
transcoding stalls, or native Android/Google TV access failures.

## Confirmed Release Information

Plex rebuilt its transcoder on the FFmpeg 6.1 baseline for the 1.43 series.
When Plex first published the 1.43 beta, it explicitly warned that the
transcoder had been refreshed from the ground up and might still contain
lingering bugs
([official 1.43 beta announcement](https://forums.plex.tv/t/plex-media-server/30447/692)).
That warning is useful context, but it is not confirmation that the live
failures have a transcoder regression as their root cause.

The deployed `1.43.3.10828` release already contains one DASH-related fix:
"Correct the Content-Type of DASH manifest files" (`PM-5259`). Its published
fix list does not mention:

- DASH segment generation or segment-request stalls
- two-minute transcode timeouts or repeated segment requests
- AAC audio conversion stalls
- Android TV or Google TV playback or server-discovery failures
- native remote clients failing while Plex Web works

The full list is in Plex's
[official 1.43.3 release announcement](https://forums.plex.tv/t/plex-media-server/30447?page=36).
The local failures occurred while running this build, so `PM-5259` does not
resolve them in this deployment.

## Related but Unconfirmed Reports

Two user reports on Plex's official forum are symptomatically relevant, but
neither is a Plex-confirmed diagnosis or fix:

- A `1.43.3.10828` user reported that remote Plex Web worked while native
  Android and Smart TV clients failed. A Plex Ninja moderator noted that the
  server had received a fresh certificate; the reporter said the native-client
  failure persisted afterward. Plex documents Ninjas as knowledgeable
  non-employee users
  ([forum role definitions](https://forums.plex.tv/t/user-groups/273958)).
  The thread contains no Plex employee response, release reference, root-cause
  confirmation, or fix
  ([forum report](https://forums.plex.tv/t/remote-playback-fails-in-native-apps-while-plex-web-works-remotely/940717)).
- A macOS user reported that `1.43.3.10828` caused TrueHD/MLP audio transcodes
  to loop indefinitely and that `1.43.2.10687` had worked immediately before
  the update
  ([forum report](https://forums.plex.tv/t/truehd-mlp-audio-transcodes-fail-transcoder-writes-mlp-files-into-eae/940690)).
  That report concerns TrueHD/MLP and macOS. It does not establish the cause of
  this Linux Docker deployment's AAC conversion and DASH stalls, and Plex has
  not acknowledged it in the thread.

These reports support continued suspicion around the 1.43.3 playback path, but
they do not prove that one bug explains both the browser and Google TV
symptoms. In particular, a native-client connectivity failure over Tailscale
can occur before media playback or transcoding begins.

## Operational Recommendation

Do not perform an "upgrade" for these symptoms: both official update channels
and the official Docker repository already stop at the deployed build.

If a controlled software comparison is needed, the available test is a
temporary rollback to the official
[`1.43.2.10687-563d026ea` Docker tag](https://hub.docker.com/r/plexinc/pms-docker/tags?name=1.43.2.10687-563d026ea),
after backing up Plex's `/config`. A successful rollback test would implicate a
1.43.3 regression, but would not by itself identify which transcoder component
is responsible. Google TV reachability should still be tested separately from
playback because every user connects through Tailscale.

Monitor the
[Plex Media Server announcements](https://forums.plex.tv/t/plex-media-server/30447/last)
and the official Plex Pass downloads API. A future build should not be treated
as a confirmed fix unless its release notes or a Plex staff response explicitly
cover the affected path, or it passes a reproduction test using the same media
and clients.
