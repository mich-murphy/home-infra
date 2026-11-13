# Offline browser/player preparation — no live verdict

Ownership reassigned explicitly; old receipts revoked. Data owns the exclusive
live window. This change performed **no cluster, host, Docker or other guest
execution** and did not open/read credentials or modify retained private state.
No new credential, archive, CA or live receipt was generated.

## Native qBittorrent browser gate

Read exact public `release-5.3.0` sources:

- https://github.com/qbittorrent/qBittorrent/blob/release-5.3.0/src/webui/webapplication.cpp
- https://github.com/qbittorrent/qBittorrent/blob/release-5.3.0/src/webui/www/public/index.html
- https://github.com/qbittorrent/qBittorrent/blob/release-5.3.0/src/webui/www/public/scripts/login.js

The native login form dispatches fetch;5.3 prefers browser-set Sec-Fetch-Site
`same-origin` over Origin comparison. Manual Origin-only401 is not evidence of
broken native browser login. No CSRF/Host setting or request Origin was weakened.

Prepared command, **only after a new explicit coordinator grant**:

```sh
STATE="$HOME/.local/state/home-infra/talos-proof/media"
CA="$HOME/.local/state/home-infra/talos-proof/config/proof-gateway-ca.crt"
# KUBECONFIG and TALOS_PROOF_MEDIA_LEASE must be exact parent-issued files.
python3 scripts/talos-proof-media-browser.py qbittorrent --state "$STATE" \
  --ca "$CA" --module /private/installed/playwright
```

Wrapper checks current lease/exclusivity; child rechecks before navigation and
hostile mutation. Independent Python TLS verifies CA **and hostname** on the
127.0.0.1:18443 transport before deriving the leaf SPKI. Chrome gets only that
exact SPKI exception, not global TLS ignore. Browser origin remains default443
`https://qbittorrent.proof.invalid`, with resolver transport mapped to18443.
HTTP and WebSocket allowlists precede page creation; service workers blocked;
all WSS denied because these workflows need none. No browser traces/profile,
HAR, DOM, screenshots or tokens are persisted. Playwright must already exist;
no dependency/browser download is automatic.

Native selectors match exact public5.3 login markup. Gate requires native204,
browser Sec-Fetch-Site same-origin, authenticated preferences200, real hostile
form POST denied, and unchanged preference. The hostile page is locally fulfilled,
not a network server. It **requires an actual SID cookie on the hostile request**:
if SameSite/Chrome suppresses it, gate fails rather than claiming CSRF from an
unauthenticated401. This behavior is not yet live-validated. Only the synthetic
max_active_downloads marker would change if protection failed; failure is retained,
not concealed by cleanup. Existing protocol evidence is unaffected.

## New immutable H264 fixture and actual decoder gate

```sh
# Offline local Mac generation; NEVER rerun over an existing fixture.
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" \
  --browser-video --ffmpeg /absolute/local/ffmpeg
# Granted player window only; seeds existing new MP4 + SRT, does not regenerate.
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" \
  --browser-video --seed plex  # or jellyfin
# After actual API scan obtains exact original media path and JF private session:
python3 scripts/talos-proof-media-browser.py plex --state "$STATE" --ca "$CA" \
  --module /private/installed/playwright \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4" \
  --media-path /library/parts/ACTUAL_ID/ACTUAL_TIMESTAMP/file.mp4
# JF path: /Videos/ACTUAL_ITEM_ID/stream.mp4?static=true (quote the argument)
```

The new12-second H264 constrained-baseline/AAC-LC320x180 fixture is distinct from
the retained historical14790-byte MPEG4/AAC artifact. Exclusive writes refuse
replacement. Browser seeding does not rewrite the old MP4/WAV. Local temporary
ffmpeg9.0.1 generation produced120214bytes, duration12.021354seconds,
SHA256 `9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`;
ffprobe independently confirmed H264 constrained baseline/AAC-LC. Temporary
artifacts were removed; existing private STATE was untouched. Encoder builds can
differ: record actual resulting SHA, not an assumed universal checksum.

The wrapper first compares actual server stream SHA with the private fixture.
Chrome then must present video frames, advance clock by1second, seek to7seconds,
present a decoded target frame and advance past8seconds. Merely receiving HTTP
bytes cannot pass. Exact origin/path-only auth headers are injected only on that
media request. A custom locally fulfilled video document is explicitly **not**
native Plex cloud/UI parity. Muted playback proves neither audible output nor
application resume/watch progress. Results explicitly flag those false.

## Admission and outstanding gates

No admission limits changed. qBit alone448MiB including reserve; protocol fixture
must be OFF for this browser-only batch (otherwise existing guard charges576).
Plex alone640; Jellyfin704; seeding adds64. Dependency budgets remain:
Plex+Tautulli896, Plex+Kometa1152, Seerr stages1216,
Plex+Jellyfin+jellyplex1344MiB including192reserve. Recent1173–1183 headroom is
not a fresh receipt. Collect actual dual memory metrics before future admission;
never substitute cache/old samples or shrink limits. The browser wrapper validates
lease/exclusivity but does not itself start anything or grant admission.

Still required: real browser run; actual Plex/JF API scan compatibility; app-level
resume progress and subtitle presentation; Jellyfin second-user ACL; read-before-
write restart plus different-PVC recovery including progress/user policy. Existing
Plex API functional test assumes one fixture and old watched marker; do not seed
both MP4 variants into that one-item workflow or relabel its byte-range assertion
as browser seek. Choose an explicitly reviewed single fixture before player start.
Tautulli/Kometa/Seerr orchestration already exists in cd54ba2d, not replaced here.
Jellyplex upstream cloud myPlexAccount discovery is still a genuine boundary;
no fabricated identity or cloud parity claim. Arr import/hardlink and Pinchflat
mock-source downloads remain separate unimplemented/unproved gates.

Offline tests include real local TLS trusted key success, wrong CA and wrong
hostname failures, immutable fixture refusal and pre-navigation route checks.
No live browser/application PASS follows from those tests or this document.

## Reassigned-owner offline integration review checkpoint

No new receipt, cluster/host access, private credential read/rotation, fixture
replacement or live browser pass occurred in this checkpoint. Earlier failures,
archives, original MPEG4 clip and recovered PVCs are unchanged.

- Hostile qBit request now requires exactly one **nonempty SID value equal to**
  the valid authenticated context's exact-host/root-path/secure SID. Empty,
  different, duplicate and missing SID fail. Values never enter results/errors.
- Browser `--group` is checked against existing safety `DEPENDENCY_BATCHES`
  membership before connecting. Child lease rechecks use that **same group**.
  qBit cannot use a dependency group. Unknown groups and wrong members fail;
  standalone defaults remain unchanged. No second lease, exclusivity expansion,
  reduced limits, stale memory fallback or admission bypass is introduced.
- The legacy sequential Tautulli workflow is deliberately retired: downloading
  bytes and subsequently posting playing timelines cannot establish concurrent
  decoding. Its old CLI now fails with directions to the integrated gate.

Prepared command, **NOT EXECUTED**, only with a newly granted exact896MiB
Plex+Tautulli group receipt, fresh dual-metric admission and deleted helpers:

```sh
python3 scripts/talos-proof-media-browser.py plex --group media-plex-tautulli \
  --tautulli --state "$STATE" --ca "$CA" --module /private/installed/playwright \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4" \
  --media-path /library/parts/ACTUAL_ID/ACTUAL_TIMESTAMP/file.mp4
```

Requires real `plex-functional.json` IDs from a reviewed scan containing only the
selected browser fixture, actual Tautulli setup, and explicit
`Monitoring.logging_ignore_interval=0` for the tiny clip. Existing history is a
hard failure, not cleared. The bridge sends identical freshly generated client
and session identifiers on the decoded original-media GET and native Plex
`/:/timeline` requests. Timeline position/duration come from the actual video,
not fixed synthetic playing offsets. Activity must match that exact item/client
and playing state. After callbacks return, the video must still be unpaused,
not ended and advancing; an ended decoder can never establish simultaneous
playing. Explicit pause posts stopped and checks Plex no longer reports this
client playing, then real Tautulli durable history must match the item/client
with positive duration. Strict server/session/version incompatibilities fail;
no cloud identity or extra session is fabricated to get past them. Adapter key
remains local proof authentication, not a Plex cloud token.

HTTP and WSS guards still precede navigation; all external app requests are
blocked on the Mac (Cilium does not protect this browser). Exact independently
CA-verified leaf SPKI only, no global TLS ignore. Browser results, including
failures, are retained as uniquely named sanitized private attempt JSON. A
successful decoder followed by failed history has overall FAIL, not helper PASS.
This is still a custom muted decoder, not native Plex UI/audible playback,
resume, user ACL or recovery. Jellyfin actual start/progress/stop, resume,
second-user denial and restart/different-PVC recovery remain separate pending
gates. Other helper preparations are not replaced or promoted.

Offline: browser7, playback3, dependency5, safety8 and media6 methods passed;
Node syntax checks and Python compile checks passed. SID executable Node tests
emit no values; group tests assert original group lease/exclusivity calls and
unchanged896MiB budget. Mock callbacks verify exact-client activity discrimination
and timeline identifiers; they do **not** establish real Plex/Tautulli behavior.
