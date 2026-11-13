# Pinned Tautulli/PMS public-source findings — activation HOLD

## Scope and provenance

This is source research, **not application PASS**, authorization, runtime validation,
or implementation. Both operational CLIs and `run()` remain **BLOCKED**. Parent
owns acceptance, root documents, gates and DATA. Only this new evidence leaf is
written. Read the actual acceptance filename
`docs/evidence/talos-acceptance/media-headless-integration-review-a1fdd277c8a14195b42232c74d72989b.md`,
`headless-followup-offline.md`, and commit
`41059033b554a56a0f1a110b286b16d3ca49ff7f`. Existing failures/HOLDs are not superseded.

Public GitHub ref/tree discovery and anonymous repository search preceded raw
source downloads; an additional anonymous PMS-contract web search yielded no
usable normative contract. No Docker/GitHub credentials were consulted. Downloads
are outside Git in owned0700 `/tmp/095aeb90-1ee5-4b79-a8e8-156407c82bc2`,
created0600 with O_EXCL; no raw binary/base64 output. No proof/production APIs,
SSH, private proof state, credentials, original fixture bytes or Pinchflat STOP
were accessed. No runtime tests or activation/settings mutators were implemented.
Only public source hashes and sanitized repository image metadata appear here.

Repository manifests `kubernetes/apps/media/{plex,tautulli}/resources.yaml` pin:

- PMS `plexinc/pms-docker:1.43.5.11079-b3b13e506@sha256:6d778d41daae68f89115aa87a44ae14a96b23e71a2093da173b5a9aac4091336`.
- Tautulli `ghcr.io/linuxserver/tautulli:v2.18.2-ls251@sha256:7ca2e262712700ae28ca5b32f9cebf1168e3ea3bfcd97a8da6e040f5ca6227a5`.

Public tag discovery:
<https://api.github.com/repos/Tautulli/Tautulli/git/ref/tags/v2.18.2>
resolves to commit **9484667bc1f2d159368a999320b8f495bbfbd00a**.
All Tautulli paths/line references below use that commit, not moving master.
This establishes upstream source identity, not independently inspected container
contents or the LinuxServer packaging-to-runtime correspondence.

Pinned source URL base (append each path in the hash table):
<https://github.com/Tautulli/Tautulli/tree/9484667bc1f2d159368a999320b8f495bbfbd00a>.
Direct key references:

- [PMS session parser](https://github.com/Tautulli/Tautulli/blob/9484667bc1f2d159368a999320b8f495bbfbd00a/plexpy/pmsconnect.py#L1878-L1941)
- [history writer](https://github.com/Tautulli/Tautulli/blob/9484667bc1f2d159368a999320b8f495bbfbd00a/plexpy/activity_processor.py#L174-L322)
- [history query](https://github.com/Tautulli/Tautulli/blob/9484667bc1f2d159368a999320b8f495bbfbd00a/plexpy/datafactory.py#L46-L390)
- [native settings handler](https://github.com/Tautulli/Tautulli/blob/9484667bc1f2d159368a999320b8f495bbfbd00a/plexpy/webserve.py#L3258-L3395)
- [CSRF validation](https://github.com/Tautulli/Tautulli/blob/9484667bc1f2d159368a999320b8f495bbfbd00a/plexpy/webauth.py#L274-L288)

## 1. Activity identity survives temporarily, not as a stored history session ID

`PmsConnect.get_sessions()` requests native `/status/sessions` (88–100).
`get_current_activity()` parses Video/Track/Photo children; `get_session_each()`
maps these **distinct** native XML fields:

| Native XML | Tautulli field | Meaning/source boundary |
|---|---|---|
| media element `sessionKey` | `session_key` | PMS session key, not a client UUID |
| child `Session.id` | `session_id` | Native session ID; empty string if Session absent |
| child `Player.machineIdentifier` | `machine_id` | Observed player identity; NOT an independently proven mapping from a submitted `clientIdentifier` |
| media `ratingKey` | `rating_key` | Item identity |

The returned dictionary merges all of these (2419–2443). `WebInterface.get_activity`
(5916 onward) is exposed through `@addtoapi`, accepts session_key/session_id
filters and retrieves native activity. These are not history DB identifiers.
`ActivityProcessor.write_session()` (31 onward) retains session_key/session_id/
machine_id in the temporary `sessions` table. `ActivityHandler` receives native
websocket `sessionKey` and ratingKey, looks up temporary state by key, and obtains
live native details through `get_current_activity()` (40–89). Websocket parsing
is in `web_socket.process()` (262–295).

**Critical loss:** `write_session_history()` (174 onward) writes a new
`session_history` row with started/stopped, rating_key, user, player, machine_id,
view_offset etc. Its explicit values (292–319) omit **both session_key and
session_id**. `DataFactory.get_datatables_history()` selects `NULL AS session_key`
for persisted rows (130), returns that null at371, and has no persisted native
session_id field. The activity union separately returns a live session_key but
NULL row_id. A newly returned non-null history row_id/id is a Tautulli DB row ID,
not a native session ID. Therefore returned stored history does **not** retain
an observed native Session.id. Do not invent a history session_id field, compare
history row_id to native IDs, or treat a submitted receipt session as observation.

### Explicitly narrower candidate oracle — parent review required, not accepted

If parent accepts replacing the original same-stored-native-session-ID requirement:

1. Reserve a fresh unpredictable client identity for one attempt, one item and
   an exclusive proof window. Establish complete baseline history and no native
   activity for that client/item. Mere UUID generation is not isolation proof.
2. Observe genuine PMS activity and Tautulli activity agreeing on item and
   observed player machine_id, nonempty native Session.id and sessionKey. Keep
   these native IDs as **activity-only evidence**. Missing/ambiguous fields HOLD.
3. Independently validate how the chosen native request's clientIdentifier becomes
   Player.machineIdentifier for this pinned PMS. Source consumer naming alone
   does not establish it. Require genuine advancement/decoder evidence through
   the already reviewed boundaries; receipt echo is insufficient.
4. After a known-complete owned stop, require no matching live activity and exactly
   one new persisted ungrouped history ID for observed machine_id + item + user/
   library/window, absent from the complete baseline; reject competing matching
   activity/history. Native started/stopped/play_duration should be consistent
   with that observed window, not used as a fabricated session-ID equivalence.
5. Re-read the same persisted ID after the authorized durability step. Describe
   result only as **fresh-client/item activity-to-new-history association under
   isolation**, never stored native same-session attribution or cryptographic
   identity. Unknown HTTP completion remains UNRESOLVED, not permission to retry.

This is weaker: uniqueness/exclusivity may be wrong, IDs may be transformed, and
history cannot distinguish two native sessions sharing client/item. Parent must
review the weaker claim before any implementation or new runtime grant.

## 2. Supported configuration, security, and short-clip limits

`config.py` defaults LOGGING_IGNORE_INTERVAL=120 and MONITORING_INTERVAL=60
(148/154). `write_session_history()` computes integer wall-clock real_play_time
as stopped − started − paused_counter, not decoder duration/view_offset (230–245).
For movie/episode, less than the nonzero ignore interval disables logging. Thus
120 seconds is incompatible with an ordinary12.021-second play; lowering a poll
interval does not fix this. User/library keep_history must also be true and
metadata lookup must succeed (177–188,255–282); numeric rating_key and supported
media_type are required. A track has a separate skip rule (<15s when duration
>=30s), so do not generalize the movie rule to all content.

Native settings UI `data/interfaces/default/settings.html:170–179` explicitly
supports **logging_ignore_interval=0** ('0 to disable' the ignore threshold,
not authentication/security). A parent-reviewed fresh proof configuration could
choose that native value instead of a near12-second threshold vulnerable to
integer rounding/timing. This note does not authorize changing it. Retain all
security protections and require exact selected settings readback, not a guessed
config fragment. `MONITORING_INTERVAL` is absent from `SETTINGS` and the settings
form, despite its config definition and legacy paused-counter use in
`activity_pinger.check_active_sessions()`. It is not a supported UI polling knob.
`web_socket.start_thread()` performs an initial session check; notification
`playing` events call ActivityHandler. `initialize_scheduler()` (419–493) sets
reconnect30s when disconnected, not periodic60s active-session polling. Websocket
liveness/events and short-play capture are runtime HOLDs, not guaranteed by60s→1s.

Supported settings path is authenticated admin GET `settings`, then native form
POST **configUpdate** (`webserve.py:3258–3395`), not a guessed API command.
`configUpdate` is not decorated `@addtoapi`; `get_settings` in API2 is read-only.
The handler clears every omitted CHECKED_SETTINGS checkbox and can alter password/
JWT state: a partial one-field POST is unsafe. Any future approved change must
preserve the full native form semantics and secret placeholders, not disable
security or blindly replay downloaded settings. Do not print form/settings bodies.

`webstart.py:220–247` enables CSRF; `base.html:17` exposes the per-session meta
csrf-token; `webauth.check_csrf_token()` compares session token to **X-CSRF-Token**
for state-changing requests. Use genuine authenticated session/cookies and that
header, retaining Origin/Referer and TLS verification. Upstream exempts /api and
valid X-Api-Key requests, but that is not a recommendation to bypass the native
form CSRF path. API2 validates an enabled32-character API key and supports
X-Api-Key (`api2.py:91–123`); that key is separate from a PMS/cloud identity.

`configUpdate` processes allowed settings in memory and writes config; the history
writer reads current CONFIG on each call. No Tautulli process restart is required
by this source path solely for ignore-threshold change. Server changes may refresh
cloud resources/reconnect websocket, first_run calls webstart.restart and starts
connection, interval changes can reschedule jobs. Do not call these all equivalent
to an application restart. Direct INI edits are **not** a demonstrated hot reload;
a future offline stopped-instance config approach requires separately reviewed
startup/readback, not this handler's in-memory behavior. No mutator was written.

### Adapter credential is NOT Plex cloud identity

Repository `plex-unclaimed-proxy.py` authenticates a fresh adapter access key in
X-Plex-Token (or independent Basic credentials), strips it before fixed localhost
forwarding, and tunnels native websocket bytes. That can authorize an adapter
request but cannot claim Plex account login, claim, cloud registration, account
owner, Plex Pass, or Tautulli cloud-user refresh. `plextv.PlexTV` targets
https://plex.tv; `get_full_users_list()` obtains account/friends/shared-server data
(332 onward), used by `users.refresh_users()`. `users.get_details()` has Local
fallback, which is not cloud-auth success. No fake cloud token, account response,
or newly disabled security is permitted. Genuine unclaimed local history support
for this exact image/adapter/user-library state remains **HOLD**.

Available first-party packaging documentation:
<https://github.com/plexinc/pms-docker/blob/abba890d29db2e83321371253a8a3c2be2218196/README.md#parameters>
(public tree discovery pinned abba890d29db2e83321371253a8a3c2be2218196).
It says PLEX_CLAIM obtains a real server token, and omission does not automatically
log in; it does not guarantee all unclaimed server API behavior. This is current
packaging documentation, **not matching PMS binary source** or a normative API
contract for1.43.5.11079. No binary/image downloaded or inspected. Native timeline
clientID/clientIdentifier acceptance, Session.id generation/stability, direct file
stream reporting, websocket notification timing, and unclaimed browser security
are closed-PMS/runtime **HOLD**, not proven by Tautulli's parser or Docker README.
No supported contract found here equates submitted session/client fields to the
native Session.id returned by this binary.

## 3. History pagination, completeness and durability

`WebInterface.get_history()` (1890–2060+) documents start/length (default25),
order, grouping/include_activity and item/user/library filters. Explicitly request
**grouping=0, include_activity=0**: otherwise config defaults can group distinct
rows or union active temporary sessions into apparent history.
`DataFactory.get_datatables_history()` returns recordsTotal, recordsFiltered and
data (377–385). `datatables.ssp_query()` uses LIMIT/OFFSET and counts filtered
result groups, while totalCount is COUNT(id) of the base history table (115–173).
Accordingly recordsTotal is not necessarily equal to filtered data length/count;
recordsFiltered is the matching result cardinality. User-session restrictions,
metadata/media-info joins and grouping affect visibility. Counts/page reads are
not a single atomic multi-page snapshot. A persisted row missing joined metadata
may temporarily not appear even if the base table total increased.

Bounded future read plan: preserve these counters and request settings from each
page, validate nonnegative integer totals and consistent filter/ungrouped/no-activity
semantics, advance offsets by actual returned rows until exactly recordsFiltered
unique non-null persisted row IDs have been enumerated. Require no duplicate IDs,
no gaps/early empty page, and stable totals/membership across a confirming scan in
an exclusive/quiescent window. No machine_id query filter is documented: enumerate
the whole supported item/user/library-filtered scope then inspect machine_id
locally. A100-row page is a transfer bound, not a completeness proof. An explicit
row/page/byte/time cap may fail closed with **INCOMPLETE/HOLD**, never silently
truncate or use length=-1 as an unbounded workaround. Stable count alone does not
exclude concurrent replacement; enforce isolation, and HOLD when it cannot be
established. Baseline and post-stop comparisons require the same complete scope.

`ActivityHandler.on_stop()` writes history and removes temp state on successful
row ID, else schedules force_stop_stream30s later (141–175); retries are bounded
by SESSION_DB_WRITE_ATTEMPTS (default5), and failure can discard the stale temp
session (630–665). Metadata, events, DB locks and retries prevent any universal
'write within one poll' promise. Poll only within an approved end-to-end deadline;
expiry/no row is HOLD, not permission to synthesize/import history or retry play.
`database.MonitorDatabase.action()` uses connection transaction contexts per
statement, retries certain lock/open errors, and uses WAL/NORMAL defaults
(425–468; config142/188). History/metadata/media-info writes are not proven here
as one atomic all-table transaction. API visibility is not power-loss durability.
A future approved application restart/read-before-write of the same row can test
restart persistence separately; PVC/node/power-loss durability remains another
claim. No restart was performed, and no runtime durability bound is asserted.

## Bounded next decisions, not activation work

1. Parent decide whether the explicitly weaker fresh-client oracle is acceptable;
   absent that decision, original stored-session-ID requirement remains unmet.
2. Parent review a native secure configuration route for an isolated unclaimed
   proof instance (threshold0, user/library logging, websocket and metadata), with
   full-form preservation/readback and no fabricated cloud identity. If native
   unclaimed support cannot meet it without prohibited workarounds, HOLD rather
   than substituting synthetic app output or disabling protections.
3. Separately source/runtime-review pinned PMS request→activity client mapping
   and websocket/short-play behavior; this note supplies only consumer contracts.
4. Only after those decisions and separate authorization, design complete bounded
   history enumeration and restart-readback; do not activate from a source review.

All earlier HOLDs remain: end-to-end deadline, producer-side FFmpeg freshness,
real descendant cleanup, immutable/exclusive aggregate resource wiring and live
adapter/Gateway/framing validation. Unknown HTTP outcome stays UNRESOLVED remote
completion even after local reap/later stop ACK; no automatic playing retry or
remote-cleanup-complete claim. Browser401 remains unfixed. Darwin exact-PID RSS
sampling is a watchdog, **not a hard ceiling**. Existing component-test results
and failed/zero-test discovery in the follow-up are not upgraded here.

## Public download SHA-256 manifest

These are public source bytes only (not fixtures, runtime state or credentials).
Paths resolve under the pinned Tautulli URL base above unless explicitly noted.

| Public source path | SHA-256 |
|---|---|
| `plexpy/pmsconnect.py` | `b55989a0f6b550aac4103c066d290a0b71251590dc2e133b89e9ff35a09ea83f` |
| `plexpy/activity_processor.py` | `5784537c44bad975114cbcd9cce5bd3a71844b673f07ddcdb448ed1ddce48d14` |
| `plexpy/activity_handler.py` | `2e5f86e345c7824a4c41a5384cfeda413099de0e90e8a854a816179b8840d9e8` |
| `plexpy/activity_pinger.py` | `9f2d8e224e1773921f1dc8cb95144675370dac1838be5696cabedfa7a6916ae2` |
| `plexpy/datafactory.py` | `59ea53ee6d1b67d2faf4504adfb6a20f224d25f85a2f7614c054bd5214bc3d03` |
| `plexpy/datatables.py` | `f731ec00151bf61d00aab203debf164572205fe975f6a860b1d0f957f422691d` |
| `plexpy/webserve.py` | `b848c3234157a680715eaaa3d1d8c6e701ec89e0afb9fec8cc7906d51df90de1` |
| `plexpy/config.py` | `78219a36de30d8af5a80e3f57c614cc673271e61501ee7abef92d975d43e306d` |
| `plexpy/api2.py` | `9c5e10ffd8c2d8bea0075011d8879425df23ddb682bb3a5e7f58caf33c9e1389` |
| `plexpy/database.py` | `acc6d2ff887d1175b0f200fca862751ee905337dc26e3507ff61c71c691be8e5` |
| `plexpy/web_socket.py` | `43f47b08ea275281ed12c6890aa01b598c632896bc4f82315c239a08684186af` |
| `plexpy/webstart.py` | `fd2b8405f55496701efb7c7821448a30604c071ce5651343974abb1ee06001c5` |
| `plexpy/webauth.py` | `b28f9758a8781f7183b30144f76cae5623e161dbe25d3c3f3928119a279b43b0` |
| `plexpy/session.py` | `31b5ff5f1f95c72a1bf22a43416587c4ccf4bb56f026702aeceb018e9cf20960` |
| `plexpy/__init__.py` | `4a1f3dc5a8776400a65759ea994838ebf616d165c71b8b05fa45b219fdda9e58` |
| `plexpy/users.py` | `3477e714d83e366220a095c27f90ed3f818bf06949bb702cb5172baf3e67dbf3` |
| `plexpy/plextv.py` | `513fcc3c8de31ece566048e93abb83f964c3803ec97cbeab26724aded6da770f` |
| `plexpy/libraries.py` | `65c037f267f5bc8ae28c4f1854680a7ccf77d5822257ed905954309b806b13a3` |
| `data/interfaces/default/settings.html` | `3be6d59b66af3700f5687b452ae563f48f9ce5306df906fb5975bfd0606bff2e` |
| `data/interfaces/default/base.html` | `7ce1865a79ad286ce28a9743e99def5866b063aa7a5c62b6eeff673a1cbd6369` |
| `plexinc/pms-docker@abba890d29db2e83321371253a8a3c2be2218196/README.md` | `42b44494398a9d05ad173fb6f4623a807d72c93b872d9e30691e5f4b97fe1fc1` |
