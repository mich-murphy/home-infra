# Non-browser headless decoder preparation — OFFLINE ONLY

## Status and scope

Implemented the decoder component described in
`native-auth-rpc-source-followup.md:129–160`. **No headless application pass,
native browser pass, activation authorization, or production/runtime evidence is
claimed.** No credentials, private proof state, existing fixture bytes, cluster,
Plex, Tautulli, or Pinchflat were accessed. Existing media code, manifests, flake,
gates, and root documents were inspected only; their integration remains the
parent's responsibility. Pinchflat remains STOP/untouched.

Owned additions:

- `scripts/talos-proof-media-headless.py`
- `tests/talos-proof-media-headless_test.py`
- `tests/talos-proof-media-headless-workstation.py` (explicit manual check only)
- this preparation note

The CLI always exits nonzero with `BLOCKED`: no current media activation grant or
reviewed headless receipt/integration exists. It accepts no credential, URL, or
receipt switch and does not invent an authority schema. Library primitives are
for reviewed parent integration, not authorization to run them live.

## Implemented component

`open_plex_stream()` requires the exact existing `talos-proof-media-http.API`,
Plex service, explicit CA, HTTPS proof origin, and no HTTP diagnostic mode. It uses
the API's independently CA/hostname-verified opener (including its SNI and
loopback TCP transport), not FFmpeg networking. Only the scanned original
`/library/parts/<digits>/<digits>/file.mp4` path is accepted. Client/session
headers are explicit, shared immutable identity values; conflicting API identity
headers are rejected. HTTP200, exact final URL, identity content encoding, exact
Content-Length, and no Transfer-Encoding are required. Redirect results, partial
responses, arbitrary URLs and query strings are rejected. **Parent must confirm
that the actual original Plex endpoint returns this strict response shape.**

`decode()` feeds source bytes directly through one bounded queue to one owned
local FFmpeg stdin. It incrementally enforces exact length and SHA-256; no source
file is saved or substituted. Live HTTP reads use `read1` with a one-second socket
timeout and unchunked fixed-length framing, avoiding indefinite `read(n)` refill
on trickling input. Default expected proof source is the supplied existing
12.021354-second H264/AAC fixture: 120214 bytes,
SHA-256 `9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`.
Those bytes were **not read** during this work. Explicit size/hash overrides on
the low-level decoder exist solely for new offline synthetic fixtures; reviewed
live integration must use the fixed defaults.

FFmpeg is an explicit `/nix/store/<hash>-ffmpeg.../bin/ffmpeg` executable, never a
shell or PATH lookup. Its fixed command uses `-readrate 1`, 0.25-second progress,
`-protocol_whitelist pipe`, `-i pipe:0`, `-map 0:v:0`, `-an`,
`-c:v wrapped_avframe -f null -`; no copy, generated decoder input, hardware
acceleration request, URL, saved input, external-file protocol or subprocess
protocol is available. Raw decoded video is not written to disk. Audio/GPU/client
parity is explicitly not tested.

Bounds and ownership:

- 120214-byte maximum source, 8192-byte read chunks, two queued chunks; streaming
  hash and exact byte count must succeed before lifecycle playing acceptance.
- 25-second wall watchdog; 30 CPU-second child limit; single codec/filter threads;
  64 MiB maximum individual FFmpeg allocation; 64 descriptors; no core dump.
- Linux: 1 GiB kernel address-space limit. **Darwin limitation:** this workstation
  rejects `RLIMIT_AS`; instead libproc inspects the exact child PID's resident
  size on each event-loop iteration (at most 50 ms selector wait) and terminates
  above 1 GiB. This RSS watchdog is NOT a hard memory ceiling: scheduler/callback
  delays and allocations between samples can overshoot. Live review must accept
  this distinction or add a hard sandbox; no silent hard-bound claim is made.
- Aggregate stdout/stderr cap 256 KiB. Retained raw logs have UUID names and
  `O_EXCL|O_NOFOLLOW`, mode 0600, under an owned mode-0700 UUID run directory.
  Excess output fails rather than filling disk; private diagnostic logs remain
  on decoder failure. Source bytes are never logged.
- Fresh private HOME/cwd/TMPDIR, minimal explicit locale-only environment besides
  HOME/TMPDIR; no inherited proxy, token, PATH, startup-file or loader variables.
- Exact owned child PID only; terminate, bounded wait, kill if necessary, reap,
  close descriptors/response, cancel and join producer, remove temporary HOME.
  No process-name scans, broad signals, detached helper processes or shell.
- The integration observer must be trusted and nonblocking; synchronous HTTP
  calls in it would violate the wall-watchdog and after-response watermark
  contract. This restriction is a remaining integration review requirement,
  not something this Python callback API can sandbox.

The lifecycle checker rejects playing until at least two strictly advancing
frame **and** media-time reports, a still-live process, and verified fixture EOF.
It requires the identical identity for playing and stopped timelines; unique
same-item/client playing activity while the process remains alive; later live
progress beyond an **after-response** watermark; successful actual decoder end
before a confirmed native stopped result; and one positive-duration same-client
history row not in the pre-run history-ID baseline. It does not synthesize
activity, history, duration or timestamps. These checks accept real observations
from a future adapter; the unit-test dictionaries are not application evidence.

Tiny inputs can fully buffer before playback ends. No claim is made that a
network socket remains open for the clip's entire duration.

## Parent integration required BEFORE any live use

1. Obtain/review an exact scoped receipt through the existing coordinator lease
   interface; recheck target, identity, expiry and group before original GET and
   every timeline/activity/history action, with cancellation on expiry. No new
   lease is created or refreshed here. Existing `talos-proof-media-safety.lease`
   and `talos-proof-media-browser.check_lease` remain unchanged.
2. Reuse `talos-proof-media-playback.prepare`/existing session interfaces for a
   fresh client and session and the exact scanned item. Capture actual pre-run
   history IDs (or enforce its existing empty-history condition). Bind the same
   immutable identity to the actual `open_plex_stream` GET and native playing /
   stopped timeline calls. Do not use the existing eager `API.call(raw=True)` to
   predownload the fixture. Do not reread a saved fixture as decoder input.
3. Wire the decoder observer nonblockingly to bounded actual API operations.
   Keep the decoder output pump running while Tautulli responds. Serialize the
   completion event back onto that pump and take its watermark **after** the
   response, not before sending the request. Require subsequent advancing frames
   and a fresh process-liveness check. Do not run synchronous HTTP inside the
   decoder observer, accept queued pre-response snapshots, or accept post-exit
   progress as concurrent activity.
4. Use decoder media time for native playing/stopped timelines, not manufactured
   wall times. Recheck process liveness immediately before playing. After genuine
   successful decoder end send native stopped and verify no same-client playing
   session, then obtain unique durable history. Existing playback callbacks and
   `finish` need reviewed wiring around the stricter lifecycle ordering; importing
   them alone does not establish those gates. Failure/cancellation must perform
   bounded best-effort native stop under a still-valid lease, never record a pass.
5. Wire both new tests explicitly into parent tooling if desired. No flake/gate
   edits or implied automatic root-gate success occurred here. Review workstation
   hard-vs-watchdog memory semantics and bounded asynchronous API cancellation.

The planned 896 MiB envelope (Plex 512 + Tautulli 192 + reserve 192) remains a
**plan, not a grant**. No pod limit reduction, budget amendment or media activation
was performed. A future successful headless result would remain separate from
FAILED native-browser Origin/Referer HTTP401 and from audio/GPU/client parity.

## Offline validation actually performed

Commands from this worktree, with bytecode writes disabled:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-headless_test.py
18 tests — OK

PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-headless-workstation.py \
  --ffmpeg /nix/store/m24vq3ip8fv6m6jypdm534z48kwqz4cw-ffmpeg-headless-9.0.1-bin/bin/ffmpeg
6 tests — OK (about 5 seconds)
```

Unit checks cover exact stream bounds/hash/corruption, malformed/regressing or
nonadvancing progress, post-exit rejection, identity mismatch, stale/duplicate/
zero-duration history, cancelled/failed/timeout child cleanup, fixed decoder
command, strict HTTP request/response contracts, and fail-closed CLI. Process and
application doubles in these tests are unit contracts only.

The separate manual workstation suite uses the existing exact Nix FFmpeg 9.0.1
path to generate one **new**, five-second 96x64/10fps H264 MP4 in memory, then feeds
only those synthetic bytes into the real bounded decoder. It checks 50 decoded
frames, advancing media time while alive after hash validation, successful reap,
0600 private bounded logs, HOME cleanup, mid-decode cancellation, corruption,
oversize input, decoder failure despite a matching non-media hash, and wall-time
termination. Temporary fixtures/logs are removed by the test harness. There is no
optional skip path: missing tools or decode failure exit nonzero. This is a
manual decoder check, **not a full gate, Plex/Tautulli proof, or existing-fixture
runtime evidence**. Initial workstation attempts exposed Darwin's rejected
address-space limit and the `/var` symlink in tempfile paths; the final suite uses
the documented RSS watchdog and canonical private test directory, without
weakening the component's no-symlink input-root checks.
