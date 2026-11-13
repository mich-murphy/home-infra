# Offline source review and prepared Jellyfin workflow

No live receipt, cluster/host/app execution, primary credential change, archive
capture or file replacement in this checkpoint. The six browser failures, Plex
restart history and both language400 attempts remain in the preceding chronology
and private files. Pinchflat research worker's three reserved files untouched.
All results below are **source review or offline tests**, not runtime acceptance.

## Plex creation: diagnosis, not another guessed activation

Retained private native response,22bytes: `'language' is invalid\n`. This
establishes native parameter validation failure, not an HTTP form/body requirement.
The retained request used POST `/library/sections` with URL-encoded query keys
`name,type,agent,scanner,language,location`, no request body. Agent was
`com.plexapp.agents.none`; attempted en-US then en both failed. No credential/query
value from authentication was copied here.

Sources reviewed:

- Official native API: https://developer.plex.tv/pms/ , embedded OpenAPI3.1,
  document version1.2.3. `libraryPostSection`, POST `/library/sections/all`, puts
  name/type/scanner/agent/language/locations/prefs in **query**; no form request
  body. Its type is integer and locations an array. This current document is NOT
  version-bound to pinned PMS1.43.5.11079-b3b13e506 and cannot silently replace the
  older request shape.
- Public PlexAPI client, commit `aa5bf6742eb806bbbebd2b65dee9fc47a81d92e1`,
  `plexapi/library.py::Library.add`: POST legacy `/library/sections`, query
  parameters including string type and singular/repeated location, no form body.
  `plexapi/server.py::agents` discovers GET `/system/agents?mediaType=1`;
  `plexapi/media.py::Agent.languageCodes` reads native Language.code entries.
  This is public CLIENT source, not the proprietary PMS implementation.

No exact-version public PMS creation implementation was located. Therefore the
language offered by THIS pinned server's personal-media agent is the remaining
native contract gate. No more guesses between en/en-US, no automatic provider
agent/cloud replacement and no body-vs-query trial-and-error activation.

Prepared read-only command, **only after new exact group receipt and narrowly
approved discovery/activation** (does not activate anything itself):

```sh
python3 scripts/talos-proof-media-plex-discover.py --group media-plex-tautulli \
  --state "$STATE" --ca "$CA"
```

It GETs identity/sections/native agents/media providers only, privately retains
native XML, and prints safe status/available personal-agent language codes. The
adapter now permits ONLY authenticated GET `/system/agents?mediaType=1`; agent
writes, other agent queries, plugin endpoints and cloud paths remain denied.
This allowlist addition is offline/unapplied. The prepared legacy creation helper
requires that native discovery explicitly advertise no-language `xn`. Absent it,
stop for contract review; **`xn` is not assumed offered or accepted live**.
Discovery must be reviewed before more library writes, including endpoint/type/
location differences above. No scan/player/Tautulli readiness change follows.

## qBit5.3: supported Secure-cookie improvement proposal

Exact public `release-5.3.0`, commit
`05fcaa8f505f0657d5cd7b7c377282b63855e8ae`:

- `src/webui/webapplication.cpp::setSessionCookie`: HttpOnly true, SameSite Lax
  while CSRF is enabled; Secure is
  `m_isSecureCookieEnabled && isOriginTrustworthy()`.
- `isOriginTrustworthy`: native HTTPS, OR effective reverse-proxy support plus
  request X-Forwarded-Proto equal to https. Does not infer TLS from Origin alone.
- Preference reload forces reverse-proxy support OFF internally if the parsed
  trusted-proxy list is empty—even if its saved/API preference is true.
- `src/base/preferences.cpp`: WebUI/SecureCookie defaults true;
  WebUI/ReverseProxySupportEnabled defaults false; WebUI/TrustedReverseProxiesList
  defaults empty. API keys in `src/webui/api/appcontroller.cpp` are
  `web_ui_secure_cookie_enabled`, `web_ui_reverse_proxy_enabled`,
  `web_ui_reverse_proxies_list` (confirm actual native preference readback before
  changing anything). Cookie name is QBT_SID_ plus actual internal WebUI port8080.

Smallest supported proposal for parent/network review, **NOT APPLIED**:

1. Keep SecureCookie true, CSRF true, HostHeaderValidation true, localhost auth
   required and current credentials unchanged.
2. HTTPS-only qBit route (no HTTP listener attachment), route Host matching browser
   origin, overwrite—not append—X-Forwarded-Proto=https at that TLS-only trusted
   Gateway. Never stamp https on an HTTP listener. Exact Gateway peer address(es)
   in TrustedReverseProxiesList, no 0.0.0.0/0, blanket proxy trust or Origin rewrite.
3. Read back effective support via native behavior: header flags alone cannot
   prove it. Source checks X-Forwarded-Proto globally once reverse-proxy support
   is effective; trusted-proxy parsing protects client-address resolution, not
   all forwarded-header attribution. Keep direct backend reachability narrowly
   restricted; validation/admin paths are trusted proof control-plane exceptions,
   not a production trust-boundary claim. If exact Gateway peer identity/header
   behavior cannot be bounded, stop and review native HTTPS plus verified backend
   TLS instead; do not invent trust identities or disable checks.
4. New optional browser `--require-secure-cookie` fails unless actual Chrome
   cookie Secure=true, then must still pass native login and exact-session hostile
   form denial/unchanged preference. No browser cookie rewriting, TLS-ignore
   expansion or Set-Cookie proxy forgery. Current bounded native PASS remains
   explicitly `production_ready_auth=false`; Secure=false is still a security gap.

No route or qBit settings changed in this source-review checkpoint. Existing
lease revocation, credential and archive hashes remain unchanged.

## Jellyfin native v12.4 preparation

Source pinned to public tag v12.4 commit
`83d0d0e7f76e23e2e085c8ff67d28b772d35967d`, matching requested image tag (actual
runtime version is checked, not inferred from image startup):

- Jellyfin.Api Controllers Playstate, MediaInfo, User, UserLibrary, Items,
  LibraryStructure; native JSON DTOs PlaybackStartInfo/ProgressInfo/StopInfo.
- `Emby.Server.Implementations/Library/UserDataManager.cs::UpdatePlayState`:
  default minimum resume duration300s; for shorter video it zeroes position and
  marks played. Source also enforces5%/90% thresholds and last-one-second completion.
- `MediaBrowser.Model/Configuration/LibraryOptions.cs`: TypeOptions disables
  remote metadata/image fetchers; obsolete EnableInternetProviders is not relied on.

New `scripts/talos-proof-media-jellyfin.py` prepares a real movie library using
ONLY the new immutable12-second fixture. It uses the existing primary credentials,
creates separately persisted fresh `proof-outsider` credentials without rotating
credentials.json, and saves every setup-config attempt exclusively. For the tiny
fixture ONLY MinResumeDurationSeconds becomes1, with actual readback and retained
prior fields. It does not lower completion safeguards or app resource ceilings.

Other user remains authenticated, nonadmin, media playback enabled globally but
EnableAllFolders=false/EnabledFolders empty. Gates require hidden listing plus
403/404 for exact item metadata, PlaybackInfo and actual video bytes, including an
attempt to name the owner's userId.401 is NOT accepted as an ACL pass. No fallback
to disabling all playback or deleting the user. Unexpected exposure fails and is
retained. Anonymous media must deny401/403 separately.

Browser `--jellyfin-lifecycle` obtains actual native PlaybackInfo PlaySessionId and
media-source ID. Native token/device ID accompany real decoded GET and JSON
Sessions/Playing, /Progress and /Stopped; positions come from actual video clock.
Session reads require exact owner/device/item and unpaused active state, followed
by stopped. Video must still advance while native playing callbacks return;
ended video cannot be reported as simultaneous playing. Callback failures/statuses
are retained, HTTP error bodies private. Stops too close to clip end FAIL rather
than accept a completed/nonresumable item.

Finish requires actual persisted PlaybackPositionTicks with Played=false and the
same item in native UserItems/Resume. Optional `--resume-record` first verifies
all prior state, feeds native saved ticks into PlaybackInfo and starts the custom
Chrome decoder at that position, requiring a target decoded frame and clock
advance, then another genuine lifecycle stop. This proves a proof client's use
of server resume, NOT native Jellyfin Web UI automatic resume or audible output.
Short-clip callback latency can legitimately fail near-end checks; never fake an
earlier stopped position to make it pass. Subtitle/native UI remain separate.

### Prepared serial standalone Jellyfin sequence — NOT EXECUTED

No Plex prerequisite. Only after new `group=jellyfin` receipt and parent review.
All admission uses fresh actual min(kubelet,Talos), unchanged704MiB app+reserve;
seeding additionally charges64MiB (768total). Commands use existing private STATE,
CA, MODULE, KUBECONFIG, TALOSCONFIG and parent TALOS_PROOF_MEDIA_LEASE.

```sh
# If Deployment/PVCs do not exist, initialize through normal guarded lifecycle:
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh start jellyfin "$STATE"
# Stop before seeding to maximize genuinely available guest headroom.
bash scripts/talos-proof-media-batch.sh stop jellyfin "$STATE"
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" --browser-video --seed jellyfin
# Seeder has deleted its Job/pod; activation refuses any remaining helper.
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh activate jellyfin "$STATE"
python3 scripts/talos-proof-media-jellyfin.py setup --state "$STATE" --ca "$CA" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4"
# The actual item GUID/media path comes from private jellyfin-browser-prepared.json.
python3 scripts/talos-proof-media-browser.py jellyfin --jellyfin-lifecycle \
  --state "$STATE" --ca "$CA" --module "$MODULE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4" \
  --media-path '/Videos/ACTUAL_ITEM_GUID/stream.mp4?static=true'
# Only PASS result's immutable functional_record is eligible as prior record.
python3 scripts/talos-proof-media-browser.py jellyfin --jellyfin-lifecycle \
  --resume-record ACTUAL_PASSED_FUNCTIONAL_RECORD.json \
  --state "$STATE" --ca "$CA" --module "$MODULE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4" \
  --media-path '/Videos/ACTUAL_ITEM_GUID/stream.mp4?static=true'
```

Record the latest **passed** functional basename after the resumed run. Do not
select an unverified candidate merely because a file exists. On any failure,
capture observations and private logs, then stop; preserve state and failed
candidates for diagnosis. No clean-setup reapply over restored PVCs. Setup refuses
existing marker/libraries instead of silently overwriting retained proof state;
an interrupted setup needs explicit observed compatibility repair/review, not
user/volume deletion or credential rotation.

For restart, observe/log before deletion, stop, refresh, activate, then run
`talos-proof-media-jellyfin.py verify --record LATEST_PASSED_RECORD.json` with the
same state/CA/fixture. Verify checks prior library/user identities, exact resume,
Played=false, resume list, unchanged proof thresholds, exact stream/range and
other-user permissions **before any playback or configuration writes**. Login
creates fresh native sessions; it does not rewrite durable media/user policy.

For clean recovery, `recovery snapshot jellyfin --state STATE` uses UUID-exclusive
archives and returns immutable manifest basename. Refresh actual memory before
helpers/admission as required. `recovery restore jellyfin --state STATE --manifest
STATE/ACTUAL_UUID_SNAPSHOT.json` preserves original PVCs/archives and appends its
result. Confirm distinct source/destination UIDs for EVERY claim. Refresh, use
**activate**, not start, wait helpers deleted, then same `verify --record`.
Functional recovery PASS requires those API/ACL/resume checks, not tar extraction.
Do not reuse a consumed restore manifest after a failure. Final observations/logs,
stop/wait all app/helper pods absent, archive/revoke receipt and release.

Actual native compatibility, callback timing for this very short video, actual
second-user ACL and different-PVC verification remain **PENDING LIVE**. No new
Plex/Jellyfin/qBit security or recovery PASS follows from this preparation.
Offline79 methods pass across the owned media suites (including7 Jellyfin and3
Plex discovery methods), plus static media Kustomize safety, Python compile,
Node syntax, Bash syntax and whitespace checks. Local TLS/protocol tests stay
local; mocks do not prove the real apps. Primary credential and existing archive
files were never opened for writing. Parent owns readiness/acceptance.
