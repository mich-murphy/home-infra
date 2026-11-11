# Separate native workflows — released live window, failures retained

2026-11-11 approximately20:04–20:17UTC. Parent explicitly granted serial
Jellyfin→Plex/Tautulli→Pinchflat,90-minute receipts, exact
admin@talos-proof / https://127.0.0.1:64120 /
nodeUID4845bfd5-3bdb-453d-8503-83b43edb7a1e. No independent Plex, arr, qBit
security, other activation, resource change or security bypass authorized.
Parent separately approved stopped adapter-only code/reference update.

**Released, OFFLINE ONLY again.** All three receipts UUID-exclusively archived
and original paths removed/revoked. Final app/helper pods `[]`, positive desired
app controllers `[]` across proof namespaces excluding platform Gateway/validation.
Final fresh actual kubelet1343/Talos1124=min1124MiB. No restore/snapshot/volume-archive
capture, credential rotation, qBit/SAB mutation, production/cloud/host change.
Old qBit/SAB recovery archives and Deployment refs were not targeted. Parent owns
acceptance; the five transferred arr/recovery files were not changed in this run.

## Jellyfin FIRST — security failure, NOT accepted

Standalone704MiB full ceiling; seed additionally64MiB. Actual fresh minima1129
before initial start,1084 before stopped seeding,1120 before activation. Every
memory update used both actual readings; no expiry/group/identity edits. Commands:

```sh
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh start jellyfin "$STATE"
bash scripts/talos-proof-media-batch.sh stop jellyfin "$STATE"
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" --browser-video --seed jellyfin
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh activate jellyfin "$STATE"
python3 scripts/talos-proof-media-jellyfin.py setup --state "$STATE" --ca "$CA" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4"
```

First setup returned404 before wizard completion; exact failing path was not
retained, so no exact cause is claimed. Private diagnostics established version
12.4.0, wizard incomplete and proof user not yet selected. Explicit native startup
configuration/user/remoteaccess/complete requests each returned204, using unchanged
fresh proof credentials. Second setup401 was isolated: actual native login200,
then `/Users/Me`401. Tokenless MediaBrowser Authorization shadowed X-Emby-Token.
Runner now preserves native device/client identity AND includes the issued token
inside Authorization. No auth setting or issued credential was changed.

Next setup authenticated successfully, configured tiny-clip resume duration floor1
(retaining normal percentage/completion safeguards), created the real movie
library and separately persisted proof-outsider, then **FAILED anonymous media
access gate**. Independent new anonymous client returned200,120214bytes, SHA256
`9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`, byte-identical
to actual retained12sec fixture. This is actual media exposure, not a health page
or an authenticated cookie reused as anonymous. No denial gate was suppressed.

Setup marker was never written because setup failed. Retained library/users/config
must not be overwritten by rerunning fresh setup. No browser lifecycle, persisted
resume, outsider ACL, restart or clean-PVC recovery PASS. Primary proof credentials
were not rotated. Current/previous private logs, pod state, anonymous forensic JSON
and observations retained before stop. Main restartCount0; current lifetime
memory.peak536866816bytes. This does not make the security failure acceptable.

## Plex/Tautulli — genuine API milestone, browser/native boundary blocks play

Full896MiB group reservation. Stopped adapter-only update admitted at fresh
min1148. `plex-discover.py --prepare-adapter --group media-plex-tautulli --state
STATE --ca CA` refused any selected pod/nonzero controller, applied one immutable
code ConfigMap and tested/replaced the Deployment spec atomically. Private full
before/after comparison proved ONLY the adapter code ConfigMap reference changed;
PVC/Secret refs, images, resources and other spec fields stayed identical.
No base reapply or activation in prepare. The deployed code is the already-reviewed
adapter with exact authenticated GET `/system/agents?mediaType=1` allowance.

```sh
python3 scripts/talos-proof-media-dependencies.py start --group media-plex-tautulli \
  --service plex --state "$STATE"
python3 scripts/talos-proof-media-plex-discover.py --group media-plex-tautulli \
  --state "$STATE" --ca "$CA"
# Native discovery reviewed before creation, not a guessed language.
python3 tests/talos-proof-media-functional.py plex --group media-plex-tautulli \
  --base https://plex.proof.invalid:18443 --ca "$CA" --state-dir "$STATE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4"
python3 scripts/talos-proof-media-memory.py media-plex-tautulli --talosctl "$ROOT/bin/talosctl"
python3 scripts/talos-proof-media-dependencies.py start --group media-plex-tautulli \
  --service tautulli --state "$STATE"
python3 scripts/talos-proof-media-browser.py plex --group media-plex-tautulli --tautulli \
  --state "$STATE" --ca "$CA" --module "$MODULE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4" \
  --media-path /library/parts/1/1794421024/file.mp4
```

First read-only discovery identity503 retained; sections/agents/providers200.
Second read-only discovery all four200. Native personal agent explicitly offered
ONLY `xn`. Legacy query creation then PASSED real personal-library scan, exact
fixture stream/range and watched write/read, without cloud claim/native token
fabrication. API byte checks are not decoded playback. Fresh minimum976 admitted
Tautulli startup; tiny-clip threshold and empty-history prechecks passed in browser
preparation. A separate diagnostic GET `/` hit a downgrade redirect refusal; no
redirect/TLS protection was relaxed. Tautulli API remained reachable.

Two actual browser attempts FAILED before decode. First private error was generic;
second retained bounded media network diagnostics: MP4 request401, media-element
code4/format error. Read-only same-media comparisons established no Origin/Referer
headers→200; exact browser Origin→401; exact browser Referer→401; Fetch Metadata
only→200; Range only→206. Native localhost/unclaimed behavior is incompatible with
this browser path under current security boundary. Neither Origin nor Referer was
stripped/rewritten, no Plex auth/security setting disabled. No frames, timeline,
same-client Tautulli activity or durable history PASS. No simulated fallback.

Both apps' current/previous private logs and pod/cgroup evidence captured before
group stop waited all selected pods deleted. Plex and adapter restartCount0;
Tautulli restartCount0. Existing prior Plex adapter restart5 remains historical
failure evidence, not erased by these clean new pods.

## Pinchflat — native RPC OOM, no provider pass

Fresh minima1138 before prepare and1122 before activation. Exact receipt marker
`provider_fixture=pinchflat-rss`, full576MiB=256main+128fixture+192reserve.
Prepare preserved existing recovered config/downloads claims and credentials;
mounted only exact read-only subPath input to fixture, not either output PVC.

```sh
python3 scripts/talos-proof-media-pinchflat-provider.py prepare --state "$STATE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4"
python3 scripts/talos-proof-media-memory.py pinchflat --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh activate pinchflat "$STATE"
python3 scripts/talos-proof-media-pinchflat-provider.py exercise --state "$STATE" --ca "$CA"
```

Two exercise attempts failed during initial native RPC/queue-control execution.
First only generic guarded kubectl error retained. Safe exception plumbing was
added to keep stdout/stderr exclusively PRIVATE; second retained exec exit137.
Observation then established main restartCount2, last termination OOMKilled137,
current restarted lifetime memory.peak268435456bytes. Fixture restartCount0.
Current lifetime oom_kill0 does NOT erase previous container OOM. The main memory
limit was NOT increased; no cache trick, forced restart or guard bypass attempted.
Native release RPC starts an additional BEAM process inside the app container;
this is a candidate overhead issue, not a measured attribution or permission to
raise resources. No stock downloader identity/probe, native Source/index/download,
network-byte coverage or updater-blocking PASS was reached. Do not infer no native
boot jobs ran simply because exercise did not reach its provider phase.

Current/previous logs, full pod states and cgroups retained before stop/deletion.
No browser/provider persistence/restore run, no new profiles/output preseed, no
binary replacement. Fixture HTTP socket tests remain only fixture contract tests.

## Evidence and next review

Private UUID/exclusive receipts retain failures and adapter comparisons. Companion
[sanitized observation JSON](native-workflows-observations-3e8ef20a-4c6a-4b05-8795-e6d42376f7c2.json)
records exact pod UIDs/imageIDs, current/previous states, restarts and measured
cgroup counters. PVC UID captures were not added in this
window; no new recovery acceptance is claimed. Primary app logs and session data
remain private, never in Git.

Next work is OFFLINE diagnosis of Jellyfin anonymous-stream authorization, native
Plex browser Origin/Referer contract without stripping security headers, and
Pinchflat RPC overhead/compatibility within approved bounds. No new activation is
authorized. Custom muted decoder is not native UX/audio/GPU/production-client proof.

Offline regression:125 media test methods pass, including the21 transferred arr/
recovery tests (still no arr live acceptance). Added token-header identity,
stopped adapter full-spec preservation and private-only kubectl failure-output
checks. Root and optional RSS Kustomize safety renders, Node browser/player
syntax, Bash syntax and whitespace checks pass. Future browser/observation/
playback captures now consistently use UUID suffixes and exclusive writes;
retained older random-suffixed captures were not renamed, replaced or deleted.
