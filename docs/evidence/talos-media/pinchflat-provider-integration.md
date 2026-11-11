# Optional native Pinchflat RSS provider — OFFLINE preparation

No activation, cluster/host calls, current receipt, primary credential rewrite,
archive capture or downloader replacement. Research ownership transferred after
its stopped checkpoint. This builds on—not a replacement for—the historical
13 real socket tests. Existing profiles/artifacts and all preceding failures are
unchanged. Parent owns acceptance and the next grant/order: Jellyfin first, narrow
Plex discovery/playback next, this provider separately if ready. Plex does not
have to pass for Jellyfin/provider to run.

## Concrete implementation

`kubernetes/apps/media/pinchflat-rss` is an OPTIONAL Kustomization, absent from
root media. Same main image,256MiB; Python runtime sidecar pinned to existing
Tautulli image,128MiB;192reserve = **576MiB**. Defaults replicas0; no CronJob,
external endpoint, broad egress rule, proxy/CA or Service for the origin. Existing
app network denial remains authoritative for native boot/daily updater attempts.
Generic origin binds127.0.0.1:7913 only, within the app Pod's network namespace.
No app Internet allowance is added. Live policy enforcement still needs actual
retained observations; a manifest is not proof of effective isolation.

Origin code is provisioned as a hash-named immutable ConfigMap. Input is ONLY the
retained `Proof Browser Fixture (2000).mp4`,120214bytes, SHA256
`9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`, in a
hash-named immutable Secret mounted read-only by the fixture only. Its exact
fixture.mp4 subPath is a regular bind-mounted file: the origin retains O_NOFOLLOW
and does not weaken its input loader to follow projected-volume symlinks. No binary in
Git. Fixture cannot mount either app PVC, and the app has no fixture input/code/
stats mount or API token. It must fetch bytes through stock native downloader.
Prepare never generates the MP4 or reapplies base Deployment/PVC references.
It requires the existing service/controller stopped and EVERY helper/app Pod
actually deleted, then patches only optional fields and verifies unchanged claims.

RSS→independent metadata-bearing HTML→MP4, fixed routes, no upstream client.
HTML now accurately describes PT12S. Original bounded file/range/path/method/body/
request-budget properties remain. Fixture incarnation has a UUID. Sidecar-only
local phase control transitions metadata→download once; no backward transition.
Each phase tracks its OWN full unique byte coverage and body/route counters.
Thus direct extractor probes or indexing that read the MP4 cannot count as the
later native download. Counter view in bounded emptyDir is ephemeral/atomic;
all observed baselines/results are separately archived as private UUID-exclusive
receipts. This does not replace archive APIs or truncate any earlier evidence.
The900s maximum fixture lifetime is deliberate; expiration/restart is a retained
failure, not permission to reset counters or restart around admission.

Shared media safety detects declared/live RSS sidecars even in stopped Deployment
specs: exact annotation/container agreement and receipt
`provider_fixture: pinchflat-rss` required; ordinary activate cannot omit the128MiB
charge. Prospective prepare also pays576. Wrong group, unknown/inconsistent
profile, absent/wrong marker, or575MiB fresh headroom FAIL. Stopped-volume helper
still uses its existing128MiB bound only after all selected apps/sidecars stopped;
helper deletion and fresh dual-metric activation gates remain unchanged.

## Native source review and verifier

Public Pinchflat v2025.6.6 source at
`076f2fe78b32f5f0a4997639c89601774d34016b`: native Sources/Profile controller
forms/router; Source/MediaItem/Profile schemas; MediaCollection source details;
Tasks relation creation; MediaDownloadWorker; runtime config and Dockerfile.
Native Tasks for a media item store media_item_id, not source_id: read-only job
observation explicitly joins MediaItem and coalesces source identity. No inferred
completed jobs or inserted database rows.

`talos-proof-media-pinchflat-provider.py` actions:

- **prepare:** exact-marker576 guard, stopped/no-helper check; immutable code/input
  provisioning and optional profile patch. No scale/start. Preserves recovered
  config+downloads claims and unchanged existing credentials.
- **exercise:** pauses ALL native Oban queues, waits executing jobs drain. Records
  actual app-configured downloader path, `command -v`, SHA256 and `--version`;
  requires the real `/usr/local/bin/yt-dlp`. Runs an explicitly labeled independent
  HTML extraction probe with that same STOCK binary (not app-download acceptance).
  Required id/title/upload_date20260101/duration12 must come from actual extractor.
  No workstation binary or replacement provider identities. Probe cannot pass the
  download phase because it is accounted separately.
- Exclusively creates `/downloads/rss-proof-UUID`, empty before submission; owner
  UID/GID come from the actual application runtime, avoiding root-owned output
  false completion. Creates a NEW uniquely named media profile and native Source
  through real Basic+CSRF-protected HTTP controls. Does not change old profiles.
  Native Source must classify as a real nonempty playlist, then actual slow index
  must yield exactly one media item from the HTML URL. Missing generic-extractor
  collection/required metadata is a hard failure, not patched into records.
- Runtime YT_DLP_WORKER_CONCURRENCY=1 is **per queue only**. Harness pauses/drains
  all queues, allows ONLY media_collection_indexing, pauses/drains, records actual
  zero download-phase baseline, then allows ONLY media_fetching. Runtime selected
  queue concurrency must equal1. Observed executing jobs must be at most one and
  belong only to the selected stage. Boot/updater concurrency before this stage
  remains separately observed, not concealed by the per-queue setting.
- Native completed slow-index AND MediaDownloadWorker jobs must link to the same
  Source/item. Item must retain real media_downloaded_at, expected uploaded_at,
  duration12, media_id/title matching independent HTML extraction, file size120214
  and no last_error. Actual disk path must stay under that unique destination,
  be a regular nonsymlink MP4, exact size/SHA. Require positive actual download
  requests, full unique byte coverage of all120214bytes in the native-download
  phase, and unchanged fixture UUID/input identity. Rows, progress or HTTP200
  alone cannot pass. Remux/output hash changes FAIL this exact-byte scope; no
  copied/renamed source bytes or invented stream-identity exception.
- Record actual bundled downloader SHA/version again and require unchanged;
  retain updater job states/attempts before/after plus native private logs in the
  live procedure. No `yt-dlp -U`, monkeypatch or updater-escape allowance. A failed
  attempt retains private RPC/metadata observations and UUID failure receipt.
- **verify:** explicit prior PASSED immutable result basename; read native state
  before submission/destination/config writes. Require exact retained Source,
  media item, completed index/download jobs, old profile settings, actual disk
  hash and actual bundled downloader identity. No copying source input to pass.

The Source validation/index/download forms, release RPC and generic extractor
compatibility have NOT run. Strict native contract mismatches are potential
blockers. Native queue control is through public Oban APIs; state queries are
constant SELECTs only. There is no credential/API/production URL in stdout.

## Prepared future sequence — NOT a grant

Only after parent separately authorizes exact `group=pinchflat`, marker above,
full576 ceiling and current identity/expiry; all earlier media receipts revoked.
No simultaneous Jellyfin/Plex/provider groups. All commands use existing private
STATE/CA/KUBECONFIG/TALOSCONFIG; no bootstrap rerun or credential rotation.

```sh
# Prior serial group is stopped; parent grants this provider window separately.
python3 scripts/talos-proof-media-memory.py pinchflat --talosctl "$ROOT/bin/talosctl"
python3 scripts/talos-proof-media-pinchflat-provider.py prepare --state "$STATE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4"
python3 scripts/talos-proof-media-memory.py pinchflat --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh activate pinchflat "$STATE"
python3 scripts/talos-proof-media-pinchflat-provider.py exercise --state "$STATE" --ca "$CA"
```

If generic extraction or native Source creation fails, preserve it and STOP,
capturing private logs and observation UID/imageID/termination/restarts/cgroups
before deletion. Do not launch a giant YouTube mock, edit rows or replace yt-dlp.
No silent fallback to treating fixture-only socket tests as provider completion.
Successful completion returns immutable `exercise-result` basename; only an
actually PASSED record is eligible for persistence verification.

Replacement: capture observations/private main+fixture logs, `batch stop`, wait
all Pod deletion, refresh BOTH actual metrics via memory collector, then
**activate**, not start. Never restart around guard. Run provider `verify --record
ACTUAL_PASSED_EXERCISE_RESULT.json --state STATE` before any submission, Source
mutation or destination initialization. No counter reuse across replaced fixture
incarnations; original successful transfer counters stay in its immutable record.
Any unexpectedly executing native jobs during read-before-write verification
fail rather than being silently canceled to make state look durable.

Then stopped consistent recovery of **both app PVCs** (config + downloads):
`recovery snapshot pinchflat --state STATE`, retain returned UUID manifest;
refresh actual metrics for stopped helper as required; `recovery restore pinchflat
--state STATE --manifest STATE/ACTUAL_UUID_SNAPSHOT.json`; confirm distinct fresh
source/destination UIDs for each claim and preserve old claims/archives. Refresh,
activate after every helper Pod deleted, same provider read-before-write verify.
Input Secret is external read-only fixture input, not an app-output PVC. This
workflow requires two independently fresh restored PVCs, NOT copying fixture
input into downloads. Snapshot/extraction-only success is not functional recovery.
Any additional recovery rehearsal needs new UUID manifests/archives; never reuse
consumed source receipt, truncate earlier archives or rename/drop old proof.

Final observations/private logs, stop/wait all application/helper Pods absent,
archive/revoke receipt, release. No production credentials/cloud account/source
data, no global TLS/auth relaxation and no external app egress.

## Offline evidence / remaining gaps

101 owned media test methods pass, including14 real fixture socket tests,6 provider
mutation/static checks and10 safety tests; both root/optional Kustomize static
safety checks and Python compile/whitespace checks pass. Socket payload remains
nonplayable ftyp-prefixed bytes: NO bundled extractor/native Source/pipeline,
resource peak, updater-blocking, replacement or two-PVC recovery pass is claimed.
The exact known12sec fixture exists privately but was not opened for writing or
played in this checkpoint. Existing credential and archive files unchanged.
Prepared Plex discovery/qBit Secure-cookie proposal/Jellyfin lifecycle remain
intact; parent readiness/matrix/brief untouched.
