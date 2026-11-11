# Pinchflat counter completion race — offline fix, not a live grant

## Failed CI remains failed

At exact SHA `5ba46de3c838dfc2d394965fc1f106e9bd34e4fe`:

- Push [43098895835](https://github.com/mich-murphy/home-infra/actions/runs/43098895835)
  **FAILED**. Its retained log reports
  `test_ranges_reconstruct_media_and_count_unique_not_duplicates`, line154,
  `AssertionError: 1036 != 1043` (14 fixture tests, one failure).
- Sibling PR [43098900812](https://github.com/mich-murphy/home-infra/actions/runs/43098900812)
  succeeded at the SAME SHA. It does not erase the failed push or establish
  clean-all-CI status. Both identities/conclusions were read via GitHub CLI;
  the exact failed assertion was confirmed from the failed log.

No rerun or new CI result is claimed here. Earlier preparation evidence remains
historical local-test evidence, not a statement that every CI run was green.

## Verified ordering and deterministic reproduction

The synchronous HTTP handler writes and flushes the response body, THEN updates
media byte counts/coverage. The socket helper reads exactly Content-Length;
that read can finish while the handler has not yet performed its counter commit.
The original test immediately called unsynchronized `snapshot()` after the final
seven-byte suffix response. This ordering permits the observed full1036-byte
coverage with only1036 accumulated body bytes rather than1036+7=1043.

A new event-gated real-socket regression pauses the handler specifically AFTER
write/flush and BEFORE `commit_media`. The client receives the exact suffix;
raw old state is deterministically1036, not1043. This reproduces the problematic
interleaving without assuming the precise scheduler timing in the historical CI
run. After explicit event release, settled counters are exactly1043 and unique
coverage remains1036. Expectations and the native actual-output SHA gate have
not been weakened.

## Completion barriers and persistence ordering

- A reentrant request lock covers the complete synchronous handler. `snapshot`
  and `publish` must acquire it within3 seconds or fail; they cannot observe the
  handler's intermediate route/write/counter state. The regression verifies both
  operations time out while the delayed commit is held, rather than publishing
  incomplete counters. Once released, the exact original byte expectations pass.
- The provider previously read `latest.json` directly. Atomic replacement avoids
  torn JSON, but does NOT make an old file fresh: the main loop can still be
  finishing a response while the reader sees the previous valid publication.
- The provider now atomically writes a fresh UUID nonce to the fixture-local
  `latest.json.request`. Publication reads that nonce only after the request
  completion barrier, serializes a settled snapshot to an exclusive0600 temporary
  file, closes it, then atomically replaces `latest.json`. The reader returns
  ONLY after observing its own nonce AND `settled: true` in that file. It waits
  at most5 seconds, polling the explicit acknowledgement at20 ms intervals;
  this is not a guessed delivery sleep or repeated-until-expected-bytes check.
  Missing acknowledgement fails closed, without an old-snapshot fallback.
- Download-phase control is now an atomic phase-file replacement BEFORE nonce
  issuance. The acknowledged snapshot must have phase `download`. The old
  separate `printf`/phase-only polling loop is removed. Baseline and final
  provider reads both use the same fresh-publication barrier.
- A real local subprocess runs the actual sidecar reader against an old valid
  publication, verifies it remains pending until publication, and checks its
  returned JSON exactly equals the persisted file with the same fresh token and
  correct metadata/download phase isolation. A separate deterministic deadline
  regression rejects stale JSON. No fixture HTTP route or network allowance
  was added.

Settled means a consistent point-in-time snapshot after the current handler,
NOT a guarantee that no future request can arrive. The native queue drain/stage
checks remain required. Atomic replace is process-visible publication ordering,
not an fsync/power-loss durability claim. `latest.json` and request/phase files
remain ephemeral views; archived run evidence remains UUID-exclusive/private.
If the fixture exits, stops publishing or an overlapping reader overwrites the
request slot, the unmatched reader times out rather than accepting stale data.

## Truthful byte semantics

No media delivery/coverage count moves before successful body write AND flush.
Budget reservation remains conservative even for aborted writes, but is now
reported separately as `reserved_body_bytes`. `sent_body_bytes` advances only
after successful write/flush, just like media-body coverage. A forced failed-write
regression proves reservation consumes budget while sent/media/unique bytes stay
zero and the next over-budget request is rejected. Successful server-side writes
are NOT proof of client consumption or durable native application output.
The independent actual native-file size/SHA validation is unchanged.

## Offline validation checkpoint

Final versions passed bounded repeat counts:

- Fixture suite: **10 complete runs ×17 methods**, including the delayed-commit,
  persisted nonce/phase reader and aborted-write regressions.
- Provider suite: **10 complete runs ×9 methods**, including stale-snapshot
  timeout and existing native completion/output integrity contracts.
- All **23 media test files** passed again as a separate full sweep.
- Optional RSS Kustomize static safety render and whitespace checks passed.

Logs and machine-readable summary were UUID-named exclusive0600 files in a
private workstation temporary directory. These are local tests, not CI or native
Pinchflat execution. The two original CI URLs/results above remain retained.

All work stayed OFFLINE: no proof-runtime/production calls, activation, lease,
credential change or recovery-archive mutation. Other owners' data paths were
not staged. The384/704 experiment still requires parent guard review and a NEW
explicit live grant; this fix supplies neither. A future stopped prepare must
install the new hash-named immutable fixture code before any authorized trial.
