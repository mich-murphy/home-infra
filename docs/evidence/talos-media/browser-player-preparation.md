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
