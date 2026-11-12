# Native headless integration preparation — OFFLINE, activation BLOCKED

## Outcome

Added a native Plex/Tautulli adapter in
`scripts/talos-proof-media-headless-integration.py`, with offline contract tests.
This is **not a finished/authorized operational CLI, application PASS, root-gate
validation, or activation grant**. Both headless CLIs exit nonzero/BLOCKED without
reading private state. The adapter library is prepared for subsequent review;
its `run()` is not connected to CLI activation. Unsupported activation wiring is
reported instead of bypassing the existing coordinator/profile interfaces.

No proof API, SSH, application endpoint, existing media fixture, credentials,
private proof state, workload, library, or configuration was accessed or changed
in this work. Nextcloud/data-owner paths and parent-owned transport/indexer tests
were untouched. No flake, root gate, root document or platform changes. Pinchflat
STOP/state/archive/credentials remain untouched.

## Prepared contracts

- New exact proposed receipt field `headless`, mode
  `plex-tautulli-native-headless-v1`, in the existing
  `media-plex-tautulli` coordinator lease. It binds client/session/item, original
  part path, immutable 120214-byte fixture and SHA-256
  `9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`,
  exact Nix decoder path and executable SHA-256, the same lease expiry,
  canonical hashes of both complete PodTemplates, component limits, reserve,
  total, and explicit Darwin watchdog limitation. Canonical JSON comparison
  distinguishes numeric/boolean types; browser/other receipts do not authorize.
  This is a proposed schema, **not a coordinator-issued receipt**.
- Existing `safety.guard`, lease/target identity, exclusivity, helper-deletion and
  resource-oracle interfaces are reused. Independent fresh kubelet and Talos
  memory observations remain mandatory. Full regular/init/restartable-sidecar
  effective limits must equal Plex 512 + Tautulli 192; reserve 192 gives **896
  MiB planned, not granted**. Existing group budgets are not amended.
- Existing HTTP API supports optional bounded response size and socket timeout;
  defaults are unchanged. The native adapter caps response bodies at 32768 bytes
  and socket operations at one second, with a three-second total owned action
  deadline. Request timeout/error, process exit, malformed/oversize IPC or unknown
  result is a failure, never acceptance.
- Original media uses the existing independently verified Plex HTTPS opener and
  is streamed directly into FFmpeg stdin. No eager `API.call(raw=True)` download,
  saved input, fixture override, fake playing/activity/history, credential reset,
  fake cloud token, Origin/Referer stripping or TLS-ignore path was introduced.
- Native GET/timelines share immutable client/session headers; native playing and
  stopped carry real decoder media time. Tautulli activity/history require the
  same client and exact item, baseline history IDs, a unique new positive-duration
  history row, successful actual decoder end and actual stopped/playing-absence
  checks. Pre-existing rows are retained, not deleted.
- One owned exec API worker serializes actions. Decoder callbacks perform only
  nonblocking bounded socket IPC, never HTTP, hashing or kubectl calls. Partial
  local IPC replies do not block the decoder pump. There are no worker threads,
  multiprocessing resource trackers, or process-name scans. Worker teardown
  terminates its newly created owned session (including any guard-owned kubectl
  read child), applies a kill bound, and waits for its exact process leader.
- Response completion is consumed on the decoder pump. The first complete
  progress report consumed **after** activity response is only a watermark;
  another strictly advancing live frame/media-time report is required. Liveness
  is rechecked immediately before playing in the API worker and after activity
  on the pump. Post-exit progress can supply final stop time only after concurrency
  was already established; it cannot establish concurrency.
- Failure first cancels/reaps the action worker, then attempts one bounded owned
  native stopped action, rechecking the still-valid lease. A remote request whose
  response timed out can have an unknown server-side outcome even after local
  cancellation; cleanup cannot establish success in that case. No playing retry
  or acceptance is permitted. Cleanup failure does not erase the original failure.

## Decoder fork/memory review

Removed decoder `preexec_fn`. A fresh `python -I -S` exec trampoline applies
resource limits then replaces itself with the exact Nix FFmpeg and fixed
stdin-only command. It accepts no alternate networking/decoder argument set.
The decoder retains fresh private HOME/cwd/TMPDIR and its minimal environment,
output/time/input bounds, exact-PID watchdog and owned cleanup.

**Darwin RSS sampling is NOT a hard memory ceiling.** It can overshoot between
samples or under scheduler delay. Workstation tests use only a known bounded NEW
synthetic input; they do not establish a hard memory limit, production safety,
existing-fixture compatibility or application acceptance. Linux retains RLIMIT_AS.

## Outstanding gates BEFORE any future grant

1. **Activation/profile wiring is unsupported.** Current existing component
   profiles are not the proposed 512/192 full-template profile; equal aggregate
   budget is not component authorization. No mutation path or alternate lease
   was added to work around this. Parent must review/install supported stopped
   profile wiring and separately approve the new exact receipt schema.
2. Capture/review actual native Tautulli polling and history settings against
   supported API/source. This adapter does **not** guess settings keys, change
   polling/history configuration, or assume the old browser zero-ignore threshold
   alone suffices. Three-second action bounds include target/guard reads and may
   reject a slow valid setup; no timeout increase is implied.
3. Capture actual Tautulli activity/history response shapes, durable-history delay
   and pagination. The prepared adapter uses existing `sessions`, `data`,
   `rating_key`, `machine_id`, `row_id`, `duration` contracts and bounds visible
   history rows; it does **not** establish complete baseline pagination or native
   short-clip monitoring support. Baseline currently rejects nonempty history
   without deleting it, preserving the existing first-run-only restriction.
   Nonempty/paginated baseline needs supported completeness review before use. Offline dictionaries are not source/API proof.
4. Capture the actual Plex original-part response shape: exact HTTP200, unchanged
   final URL, identity encoding, no Transfer-Encoding, Content-Length 120214; prove
   the scanned exact item is this immutable fixture. Existing bytes were not read.
   Confirm native timeline/session behavior with these shared identities.
5. Parent must independently review worker/descendant cancellation, receipt and
   full-template binding, supported activation, Darwin watchdog acceptance and
   the adapter's library-only integration. No new root-gate/flake wiring occurred.

## Offline validation actually performed

All commands ran only in `/Users/mm/dev/home-infra-talos-proof` with
`PYTHONDONTWRITEBYTECODE=1`:

```text
python3 tests/talos-proof-media-headless-integration_test.py       15 OK
python3 tests/talos-proof-media-headless_test.py                   18 OK
python3 tests/talos-proof-media-playback_test.py                    3 OK
python3 tests/talos-proof-media-safety_test.py                     13 OK
python3 tests/talos-proof-media-tls_test.py                         4 OK
python3 tests/talos-proof-media-headless-workstation.py \
  --ffmpeg /nix/store/m24vq3ip8fv6m6jypdm534z48kwqz4cw-ffmpeg-headless-9.0.1-bin/bin/ffmpeg
                                                                 6 OK
git diff --check                                                  OK
```

The new tests exercise proposed receipt drift/expiry/decoder hash, full-template
restartable-init charging, after-response watermark and later live progress,
post-exit/expiry failure, bounded HTTP bodies, fixed launcher arguments, actual
owned local exec/IPC serialization, incomplete replies, deadline failure and
worker reap. Local IPC responders are test doubles, **not mocked app PASS**.
The six workstation checks remain decoder component proof only: they generate
new synthetic bytes and do not call any app. Parent acceptance, root validation
and future activation grant remain separate.
