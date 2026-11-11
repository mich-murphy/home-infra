# Offline pinned auth/RPC followup — no new live grant

Followup to [released native failures](native-workflows-20261111.md), not a
replacement chronology. All three media receipts remain revoked. No cluster,
proof-host, production, native app, credential, archive or app-network mutation.
Only public source HTTPS reads, offline private-evidence parsing and local tests.
The three new indexer-fixture paths remain reserved to0436e724 and untouched.

## Jellyfin12.4: the anonymous file was real; LAN classification is not an auth fix

Pinned source: Jellyfin commit
[`83d0d0e7f76e23e2e085c8ff67d28b772d35967d`](https://github.com/jellyfin/jellyfin/tree/83d0d0e7f76e23e2e085c8ff67d28b772d35967d),
matching the reviewed12.4 tag. Actual runtime12.4.0 and Compose digest
`fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771`
were recorded live. The new anonymous client got exact120214-byte fixture SHA
`9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`.
No token/cookie inheritance or health-page explanation changes that failure.

Exact source path findings:

- [`Jellyfin.Api/Controllers/VideosController.cs`](https://github.com/jellyfin/jellyfin/blob/83d0d0e7f76e23e2e085c8ff67d28b772d35967d/Jellyfin.Api/Controllers/VideosController.cs):
  `GetVideoStream` and `GetVideoStreamByContainer` have NO Authorize attribute.
  `BaseJellyfinApiController` has none either. `StreamingHelpers.GetStreamingState`
  permits an empty userId, gets the item without a user restriction and passes
  null user to playback-source lookup. The static branch returns original bytes.
- [`Jellyfin.Server/Extensions/ApiServiceCollectionExtensions.cs`](https://github.com/jellyfin/jellyfin/blob/83d0d0e7f76e23e2e085c8ff67d28b772d35967d/Jellyfin.Server/Extensions/ApiServiceCollectionExtensions.cs):
  authorization sets DefaultPolicy, but NOT FallbackPolicy. DefaultPolicy does
  not automatically protect undecorated actions. Therefore the mere existence
  of default authorization is not a stream-auth guarantee.
- [`AnonymousLanAccessHandler`](https://github.com/jellyfin/jellyfin/blob/83d0d0e7f76e23e2e085c8ff67d28b772d35967d/Jellyfin.Api/Auth/AnonymousLanAccessPolicy/AnonymousLanAccessHandler.cs)
  succeeds for null/loopback/local remote IP. It is an endpoint policy, NOT a
  configurable universal anonymous-stream toggle, and these stream actions do
  not apply it. Disabling a guessed `AnonymousLanAccess` flag is not a fix.
- [`MediaBrowser.Common/Net/NetworkConfiguration.cs`](https://github.com/jellyfin/jellyfin/blob/83d0d0e7f76e23e2e085c8ff67d28b772d35967d/MediaBrowser.Common/Net/NetworkConfiguration.cs)
  exposes `KnownProxies`, `LocalNetworkSubnets`, `EnableRemoteAccess`, etc., but
  no reviewed require-auth-for-all-streams switch. `ConfigureForwardHeaders`
  disables forwarded-header processing entirely when KnownProxies is empty;
  otherwise it accepts X-Forwarded-For/Proto/Host from configured proxy addresses.
  No blanket proxy trust or invented Gateway peer address is proposed.
- [`NetworkManager.InitializeLan/IsInLocalNetwork/ShouldAllowServerAccess`](https://github.com/jellyfin/jellyfin/blob/83d0d0e7f76e23e2e085c8ff67d28b772d35967d/src/Jellyfin.Networking/Manager/NetworkManager.cs):
  empty LocalNetworkSubnets falls back to private RFC1918 ranges and loopback;
  loopback is always LAN. These facts make a private Gateway peer plausibly LAN,
  but actual runtime named network config/normalized peer were not captured live.
  Do not report an observed exact peer or trusted-proxy classification.
- [`IPBasedAccessValidationMiddleware`](https://github.com/jellyfin/jellyfin/blob/83d0d0e7f76e23e2e085c8ff67d28b772d35967d/Jellyfin.Api/Middleware/IpBasedAccessValidationMiddleware.cs)
  allows local requests or calls ShouldAllowServerAccess, returning503 if blocked.
  That is an IP-access filter for anonymous AND authenticated requests, not
  token authentication. Making Gateway remote while EnableRemoteAccess=false
  would also block the owner; enabling remote access would again expose an
  undecorated stream. Neither is an auth fix.

**Conclusion:** no supported native configuration that makes these exact static
stream actions require authentication was found in the pinned source. This is a
real blocker, not permission to silently add guessed flags, change trusted
networks, skip the negative test or reset users/PVCs. Any native auth patch/image
change or Gateway authorization design needs separate parent review and a new
live grant. A Gateway auth design must validate REAL native token and per-item ACL
for media, not merely header presence, and must preserve authenticated outsider
byte denial. No such Gateway wiring or new network configuration is implemented.

### Correction to the earlier token-header explanation

The old live chronology accurately retains Authenticate200→Users/Me401 and the
successful native `Authorization: MediaBrowser ..., Token="issued-token"` fix.
Its explanation that a tokenless Authorization header *shadowed* X-Emby-Token
was too strong. Exact
[`AuthorizationContext.GetAuthorizationInfoFromDictionary`](https://github.com/jellyfin/jellyfin/blob/83d0d0e7f76e23e2e085c8ff67d28b772d35967d/Jellyfin.Server.Implementations/Security/AuthorizationContext.cs)
accepts X-Emby-Token/X-MediaBrowser-Token/api_key ONLY if
`EnableLegacyAuthorization=true`; that setting defaults false in
ServerConfiguration. With legacy enabled, an absent Token falls back to the
legacy header even when Authorization exists. Thus default-disabled legacy auth,
not unconditional precedence alone, explains source behavior. Runtime setting
was not retained with the failure, so its exact value remains unobserved. The
native Token= fix is correct without re-enabling legacy auth; failure history
was not rewritten. The code comment now reflects this exact source distinction.

### Retained partial setup adoption — prepared, deliberately still blocked

`talos-proof-media-jellyfin.py adopt` is a small retained-state verifier, NOT a
fresh setup/repair path. Existing proof credentials and outsider file are reused
without regeneration; exactly one existing Proof Browser library/location/item,
owner/outsider identities, current12.4 completed wizard, exact fixture bytes/range,
prior resume-settings attempt and disabled remote metadata/image fetchers must
match. Named network configuration is read and retained privately, not modified.
Only session login and new UUID-exclusive local candidate receipts occur before
adoption. No library/user/policy/configuration POST is made.

The header/cookie-free anonymous client must deny BOTH full and Range media
requests401/403. The authenticated outsider ACL/stream gates must also pass. Any
leak/401-as-outsider/transport failure leaves the fixed prepared marker absent;
no fake adoption just because the candidate JSON exists. Existing prepared marker
is never overwritten. Restart/restore verification now repeats anonymous denial
as well as prior resume and authenticated outsider checks.

Future command, only under a new parent grant AFTER an auth-boundary remedy:

```sh
python3 scripts/talos-proof-media-jellyfin.py adopt --state "$STATE" --ca "$CA" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4" \
  --attempt ACTUAL_RETAINED_jellyfin-resume-config-attempt_UUID.json
```

`--attempt` is the exact existing private-state basename, not a generated
replacement or a guess. Current retained byte exposure is expected to FAIL this
adoption. Local marker adoption is PREPARED_ONLY, never lifecycle/recovery PASS.
No native library scan is re-triggered and no playback is manufactured.

## Plex: transient delegation is not an accountless bootstrap contract

Public native docs: https://developer.plex.tv/pms/ , operation
`securityPostToken`, `/security/token?type=delegation&scope=all`: temporary token
with **the same access level as caller's token**, up to48h, invalid on restart;
POST preferred. This is not a published way to invent the initial authenticated
identity of an unclaimed server. The docs are current, not proprietary exact
PMS1.43.5.11079 implementation source.

Pinned public client
[`plexapi/server.py::createToken`](https://github.com/pkkid/python-plexapi/blob/aa5bf6742eb806bbbebd2b65dee9fc47a81d92e1/plexapi/server.py)
explicitly returns None without a token, with comment “Handle unclaimed servers”.
Its user-switch flow obtains a real account user's token; official
[token guidance](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
requires Plex-account sign-in. No supported native accountless session/delegation
bootstrap that solves our Origin/Referer401 was established. This is an OPEN
local/unclaimed-browser boundary, not proof that a hidden native capability
cannot exist. Do not call /security/token with the proof adapter key as though it
were Plex-issued. No cloud account/claim, production/native token borrowing,
Origin/Referer stripping or security-setting exception is proposed.

### Possible narrower headless proof — source-reviewed design only

FFmpeg9.0.1 public
[`doc/ffmpeg.texi`](https://github.com/FFmpeg/FFmpeg/blob/n9.0.1/doc/ffmpeg.texi)
provides real-time `-readrate 1`, programmatic `-progress`, and periodic
`-stats_period`. `fftools/ffmpeg.c::print_report` emits actual emitted frame count,
output media time and progress=continue/end. These support a NON-BROWSER decoder
proof, but do not themselves prove decoded source frames when stream-copy or
synthetic outputs are allowed.

A future small runner could feed only the actual CA/hostname-verified same-Plex
HTTP response into local ffmpeg stdin, validate its exact fixture hash while
streaming, and force real video decode→wrapped_avframe/null output, NOT `-c copy`:

```text
LOCAL_FFMPEG -hide_banner -loglevel error -nostdin -nostats -stats_period 0.25
  -progress pipe:1 -readrate 1 -i pipe:0 -map 0:v:0 -an
  -c:v wrapped_avframe -f null -
```

The pipe producer must not predownload/close and then fake playing: require live
process + strictly advancing decoded frame/media-time progress BEFORE native
playing timeline; the SAME client/session headers on the actual HTTP GET and
native timelines; advancing frames/process still alive after Tautulli activity
returns; then genuine decoder stop/native stop and unique positive-duration
same-client history. Bounded tiny input may buffer early, so “streaming decode”
does not imply the network socket remains open for the clip's entire duration.
No saved-file substitute, fabricated timestamps, post-exit activity or stale
history is allowed. TLS stays in the existing independently verified Python
client, no ffmpeg TLS bypass or credentials in command-line URLs. Until such a
runner is implemented/reviewed/live-proven, this is NOT a headless pass either.
Browser playback remains separately FAILED401 regardless of headless outcome.

## Pinchflat: lightweight native transport preparation, no resource increase

Exact public Pinchflat v2025.6.6 source
[`076f2fe78b32f5f0a4997639c89601774d34016b`](https://github.com/kieraneglin/pinchflat/tree/076f2fe78b32f5f0a4997639c89601774d34016b):
`docker/selfhosted.Dockerfile` builds Elixir1.18.4/OTP27.2.4 via `mix release`,
then copies that release into the final Debian image. Requested image digest
`4e975edf58f0861a5cbfe8fc6aac4851ff5a02dfc3f05ffeea4982e3084a5a4a`
was observed live. No new image was pulled/executed here.

- Elixir1.18.4
  [`Mix.Tasks.Release.Init.rpc`](https://github.com/elixir-lang/elixir/blob/v1.18.4/lib/mix/lib/mix/tasks/release.init.ex)
  explicitly execs Elixir with hidden rpc-node/start_clean: another BEAM VM.
  This matches the **possibility** of observed second BEAM, not PID/argv proof.
- OTP27.2.4
  [`erts/etc/common/Makefile.in`](https://github.com/erlang/otp/blob/OTP-27.2.4/erts/etc/common/Makefile.in)
  installs native C `erl_call` among embedded runtime programs; Elixir
  `Mix.Release.copy_erts` recursively copies the ERTS bin directory. This is a
  source-backed prediction of `/app/erts-VERSION/bin/erl_call` in the requested
  release, NOT an observation of that exact runtime file/hash.
- OTP27.2.4
  [`erl_call_cmd.md`](https://github.com/erlang/otp/blob/OTP-27.2.4/lib/erl_interface/doc/references/erl_call_cmd.md)
  and `src/prog/erl_call.c` support `-e` Erlang-expression evaluation,
  `-fetch_stdout` from the target evaluation's group leader, `-no_result_term`,
  timeout and dynamic hidden name. C-node client does NOT start a local BEAM.
  `-fetch_stdout` works with target OTP>=24. Timeout does NOT abort an already
  executing remote expression, so no automatic retry after timeout.
- Pinchflat native router has Basic+CSRF Source/profile/index/download controls,
  but no reviewed native global Oban pause/drain/state HTTP route. The dev
  dashboard is Phoenix LiveDashboard, not an Oban queue-control contract. Source
  enable/disable cannot prove every native queue idle. No fake app API is added.

Prepared provider `rpc()` now uses ONLY bundled ELF `erl_call`, deriving ERTS
path and reading the RUNNING PID1 release node/distribution/cookie privately.
Exact short native node pinchflat/sname, safe cookie format, executable nonsymlink
ELF, actual client SHA and exactly one BEAM before/after are required. No default
node/cookie guessing, secret stdout, `-s` auto-start, module compile/replacement or
fallback to the known-OOM Elixir RPC. Fixed SELECTs/public Oban control expressions
run inside the existing native application; real JSON stdout and unique transport
identity must be present, not exit-zero alone. All output stays UUID-exclusive
private. Missing binary/identity/stdout or any failure stops the attempt.

This code has NOT executed in the image. Future grant must first verify actual
bundled path/ELF/hash, node/cookie compatibility and capture cgroup/process/resource
comparisons; process-count samples alone do not prove no transient process peak.
The app remains256MiB, fixture128MiB, full576 including reserve. No resource or
concurrency limit was lowered/raised. Runtime boot jobs can still overlap before
queue pause; parent review is required before another activation. Per-queue1 is
not global concurrency1. Stock yt-dlp is never replaced or updated by the harness.

### Parent kernel evidence: three correlated OOM events, not just two RPC errors

Parent captured proof-node dmesg READ-ONLY, native command exit0, immutable0600
`diagnostics/pinchflat-kernel-06dd62a9dbc44ec5a59b262199908bd9.log`.
Offline SHA verified:
`75e20244e98d1d189ab8a0eee13acd33d00eab1e4d5f8f4c04dae33c85d91348`.
[Sanitized extracted correlation](pinchflat-kernel-correlation-aa551520-1f53-4020-9513-185275ecc67c.json)
retains provenance/line offsets/numeric task fields, NOT the raw log.

All three CONSTRAINT_MEMCG summaries name actual pod
089ed926-0240-432f-a25a-1199beaa770e. Exact observed correlation:

| Kernel UTC | Container ID prefix | Task-table BEAM PIDs / RSS pages | Other observed comms | Outcome |
|---|---|---|---|---|
|20:13:09.270|002075d54f9f|44223/53814;44489/8557|yt-dlp|victim44223; first generic failure receipt20:13:09.533|
|20:16:20.620|ceefe691926b|44582/53264;45076/1390|yt-dlp,python3|victim44582; exec137 receipt20:16:20.888|
|20:16:35.689|f26d8b522e57|46009/55384 (one BEAM)|yt-dlp,two python3|victim46009 during observation/cleanup, no new RPC attempt|

Task tables contain11/15/18 tasks respectively, not a full process-duration trace.
Victim RSS in explicit kernel KiB fields (anon/file/shmem) is
128440/444/86372;126364/488/86204;134688/484/86364. Keep task-table pages as pages;
RSS/shared mappings are NOT additive cgroup charges. No inference that provider
media decoding/download itself needs more RAM: no provider Source/workflow was
reached. Boot yt-dlp presence is real, but argv/job relationship is missing, so
cannot label each process as updater/extractor/download just from comm.

Second and third full container IDs match private pod statuses exactly. First
ID is a historical same-pod memcg different from the continuously healthy fixture;
its pre-restart pod status/argv was not captured. The two extra BEAM roles are
plausibly RPC clients from source/timing, NOT proven command-line mappings.
The third event with only one BEAM shows extra RPC VM is not established as the
sole cause. The original first application error remains generic/unknown at its
capture; later kernel correlation supplies additional evidence, not a rewritten
original exit status.

The retained final20:16:37 stop observation ALSO records current main terminated
OOMKilled137 at20:16:35, restartCount2, lastState second OOM20:16:20. Thus there
were THREE killed main incarnations, despite restartCount2 (third had not restarted
before stop). Current/previous logs were collected, but logs cannot recover every
previous incarnation. Fixture restart0. No additional cluster/host calls here.

## Offline validation

129 owned media test methods passed (the reserved fixture worker's separate7
socket methods also ran successfully without edits to its files). New regressions
cover independent empty anonymous cookie/header state, full/range leak refusal,
retained adoption without durable app POSTs, preservation of failed candidates,
mandatory native stdout/process identity and transport failure with NO fallback.
The embedded lightweight shell passes local Bash syntax. Node browser/player
syntax, wrapper Bash syntax and whitespace checks pass. These are mocks/local
contracts, not native runtime or resource compatibility. No readiness/root/brief
or reserved indexer-fixture file changed; parent retains acceptance ownership.
