# Serial browser/player live window — released, bounded results only

2026-11-11 18:14–18:26UTC. Parent granted90-minute receipts for exact
`qbittorrent`448MiB → `media-plex-tautulli`896MiB → `jellyfin`704MiB,
including192reserve. API64120/nodeUID4845bfd5-3bdb-453d-8503-83b43edb7a1e.
No standalone Plex/protocol fixture grant used. Parent owns acceptance.

## Native qBittorrent browser PASS

Chrome157.0.8103.51 used actual5.3 native controls. Native login204, actual
on-wire Sec-Fetch-Site same-origin and unmodified expected Origin, authenticated
preferences200, hostile same-site form carrying exactly the authenticated
nonempty session-cookie VALUE denied401/403, preference unchanged. Cookie is
exact observed `QBT_SID_8080`, not legacy `SID`; duplicate/different/empty/missing
values fail. Values never printed. Cookie was not Secure behind this HTTPS
adapter; that observed limitation remains, no app cookie/auth setting changed.
Exact independently CA+hostname-verified leaf SPKI only; browser HTTP/WSS guards
installed before navigation, external app requests blocked, no TLS global ignore.
This proves only this bounded native login/CSRF workflow, not production parity.

Six failed harness attempts before PASS remain in private immutable browser
attempt receipts; later failures also have private exception logs. Initial
interception request headers omitted Fetch Metadata: CDP actual on-wire headers
proved same-origin. Then native login navigation raced preferences evaluation;
wait now requires login document gone and network idle. Legacy SID and Secure
assumptions failed despite real authenticated preferences200. Exact actual cookie
name/value comparison replaces those assumptions; HTTPS-only transport remains.
No manual Origin-only401 was promoted to native-browser failure evidence.

Commands: `memory qbittorrent --talosctl .../bin/talosctl`, `batch activate`,
`browser qbittorrent --state STATE --ca CA --module installed-playwright-core`,
`observe`, private app-log capture, `batch stop`. Actual dual minimum1057 before
activation. qBit pod UID/status/imageIDs/cgroup current/peak/events captured
before deletion; no restart in these observations. Prior downloader transfers,
archives and recovered PVC references unchanged; no torrent rerun.

## Plex integration blocked before decoder/Tautulli

Only the12-second H264/AAC browser fixture was generated and seeded, immutable
120214bytes SHA2569f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb.
Seeder deleted before activation. Initial dual minimum991 admitted full group
plus64seeder960. Subsequent actual minima1130,1143,1046 remained above896;
no limit reductions/cache tricks/stale metric fallback.

1. First adapter startup failed: real Plex already occupied32401, adapter
   OSError98/address in use. Captured UIDb58da5c3-df88-4159-a9dc-fe1644ba57dd,
   adapter restartCount5/CrashLoopBackOff, real Plex restartCount0. No latest
   healthy pod erases this. Private app/adapter logs and sanitized cgroup/status
   observations retained before stop. Proof-only adapter/dependency ports changed
   consistently to33240 (real Plex still localhost32400), no production service.
2. First group stop partially stopped Plex then failed because Tautulli Deployment
   did not yet exist. Fixed stop to scale only existing selected Deployments;
   refresh still required before activation; subsequent deletion waits passed.
3. Adapter startup then passed, identity200/unclaimed0, but library sections401.
   Direct actual localhost32400 sections200 established forwarded client-IP
   headers were incompatible with the intended separately authenticated local
   adapter. Adapter now strips Forwarded/X-Forwarded-For/X-Real-IP before fixed
   localhost forwarding; its independent access-key check remains mandatory.
   No native/cloud token, identity or global Plex auth exception was fabricated.
4. After guarded stop/reapply/start, actual personal-media library creation
   returned400. Private response indicated an invalid language. Changing prepared
   en-US→en did not resolve400. Both failures remain; no library scan, decoded
   playback, timeline/session activity or Tautulli history PASS claimed.

Tautulli never started. Prepared same-client decoder/native timeline/history gate
remains unvalidated. Exact-version create-library contract needs offline diagnosis
and a new receipt, not more unbounded retries. Jellyfin was NOT STARTED: full
start/progress/stop/resume/other-user-denial/recovery harness is not ready.

## Release and preservation

Before stop, captured Plex UID/image/current+previous termination status/restarts,
cgroup counters and private logs. Final fresh minimum1019; group stop waited
selected namespaces empty. Final all-proof application/helper pod list `[]`.
All three receipts privately archived and original receipt paths removed/revoked.
No pods left waiting for parent. No source data/credentials/cloud accounts,
appInternet, host/source/Docker mutation, credential rotation or archive capture.

Offline followup makes future recovery archive names UUID-suffixed/exclusive,
new snapshot/attempt/restored manifests append-only, source manifests immutable,
and restore consumption exclusive even on failure. New restore CLI accepts
`--manifest PRIVATE_UUID_SNAPSHOT_JSON`, returns exact result/source manifest
names. Legacy manifests remain readable by default; existing qBit/SAB archive
files untouched. A consumed failed restore requires reviewed new snapshot, not
silent reuse/truncation. Recovery integration has NOT run in this window.

Offline browser7/playback3/dependency5/observe3/safety8/media6/recovery2 methods
passed. Mock/static coverage is not live acceptance. All original failures and
archive evidence are preserved. No readiness/acceptance table changed.
