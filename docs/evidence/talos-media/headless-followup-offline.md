# Offline headless follow-up checkpoint

Activation **HOLD**. Both operational CLIs remain unconditionally **BLOCKED**;
`run()` now also refuses before guard/state/network access. No application PASS,
runtime authority, receipt approval, or browser-401 repair is asserted.

## Prepared repairs

- Plex proxy source preserves a single strictly decimal upstream Content-Length,
  rejects any Transfer-Encoding (including TE+CL), duplicate/comma-list/invalid
  lengths and Connection-nominated length before forwarding response headers.
  Decoder independently requires exactly one exact-length header and no TE.
  No ConfigMap reference, resource manifest, limit, or deployment was changed.
- Activity reply requests a bounded nonblocking stdout drain through EAGAIN,
  invalidates partial parser state, and quarantines through the next block end.
  Parser reports carry boundary epochs and batch IDs: old-epoch reports and ALL
  reports in the watermark batch cannot count as fresh advancement. Tests cover
  real owned pipe backlog, partial block, two queued reports delivered together,
  and later-batch advancement. **This does not establish producer freshness**:
  pinned FFmpeg production/flush semantics have not been source-reviewed here.
  Consequently these parser mechanics are preparation only and `run()` HOLDs.
- Pure aggregate snapshot admission requires one controller, one replica, a
  non-surging fixed strategy, and exactly one nonterminating Pod per service.
  It counts terminal/terminating duplicates rather than silently excluding them.
  Full effective limits are validated and summed with reserve. Snapshot checks
  are NOT atomic admission or proof of controller exclusivity over time.
- Actual Plex effective448/Tautulli256 profile is preserved; proposed512/192 is
  not interchangeable authority despite equal totals with192 reserve. Existing
  wiring remains unsupported. No Tautulli limit was lowered.
- Removed automatic failure-stop attempts. Unknown HTTP completion remains
  **UNRESOLVED remote completion** after local reap or any later stop ACK; no
  automatic playing retry or remote-cleanup-complete claim is permitted.

## Offline validation

41 tests passed: headless18, integration15, new follow-up8. Exact interpreter:
`/nix/store/npyrmk982c91wj89yp9nvpfpxspszr70-ansible-tooling/bin/python3`
(Python3.13.13), fresh0700 HOME, minimal environment, bytecode writes disabled.
New adapter tests use only two explicitly owned ephemeral loopback listeners,
new synthetic `NEW` bytes, and shutdown/join both servers. They exercise the
actual Handler forwarding path; they do not test the Gateway/TLS or live Plex.
Final0600 log: `/tmp/media-offline.6mRqWd/result.txt` in owned0700 directory.
Earlier discovery ran zero tests (not evidence); a subsequent system-Python3.9
run failed two existing hashlib.file_digest tests; exact3.13 reruns passed.
No workstation decoder run or public-source research was completed this slice.

## Remaining acceptance gaps

- End-to-end deadline across guards, header opening, decoder, native actions,
  history, teardown, and final expiry remains unimplemented. Worker per-action
  bounds and decoder bounds do not solve this. Blocking `run()` prevents using
  that incomplete path as runtime preparation authority.
- Public-source review of Tautulli2.18.2/PMS session mapping, settings, polling/
  monitoring thresholds, history durability, supported fields and pagination
  totals/completeness is still required. Existing client/item checks do NOT
  establish native same-session attribution. No field was invented and no
  fresh-client oracle was substituted for the original same-session claim.
- Pinned FFmpeg flush/production ordering remains unresolved as above.
- Real owned-descendant cleanup regression was not added; existing leader/IPC
  tests are not descendant evidence. Local cleanup is not remote cancellation.
- Snapshot accounting needs reviewed immutable/exclusive runtime wiring;
  desired replicas or a snapshot alone cannot bound all future simultaneous Pods.
- Darwin RSS sampling remains a watchdog, NOT a hard ceiling. Native browser401
  is unfixed. Parent acceptance, operational wiring and grants remain separate.

Only repository source/tests and this media note were changed. No private proof
state, credentials, original fixture, production/proof API, SSH, Pinchflat STOP,
Nextcloud diagnostic, CI, or push was accessed. Parent-owned files are excluded.
