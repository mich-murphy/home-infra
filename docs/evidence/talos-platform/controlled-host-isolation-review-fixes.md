# Pre-live review fixes — OFFLINE checkpoint

No deployment or live test grant exists. No host command, packet probe, listener,
unit start, instrumentation or process/cgroup movement ran in this step. Data
owner c23fdbf1 currently has the exclusive CouchDB→Miniflux window. Earlier
app-zero observations are stale; the wrapper rechecks them in a future window.
Parent backup-safety/create.sh/workflow changes were not touched.

## Scope-independent exact cleanup

Removed the redundant inner cgroup match from the targetless predicate. The
unchanged canonical policy verifier requires ONE scoped OUTPUT entry, first in
OUTPUT, and rejects alternate chain entries. Attribution is inherited from that
entry. Exact predicate `-C/-D` contains no cgroup extension/path lookup and thus
remains usable after guard stop removes the original VM scope. It still matches
controlled sourceHostIP/destinationHostIP/TCP/high destination port/comment and
is immediately adjacent to the original matching REJECT, with no new verdict.

Regression mocks all Path.stat lookups as failing after scope disappearance and
checks that cleanup still issues exact deletion without --path/cgroup. Alternate
proof-chain entry is independently rejected. No isolation/lifecycle lock is held.

## Unsupported child execution removed

Node mode only. Removed Popen/second-Python startup, cgroup membership writes,
negative-child runtime and corresponding CLI flags; child/UDP/IPv6 modes are
rejected. The unused --source-port flag was also removed: the node's translated
source port is genuinely unknown. Both positive controls run in-process. No
RLIMIT_AS argument is used to pretend already-mapped Python memory has become
smaller. Future child trials require a new budget-safe design/review, not merely
an execution flag. The prior PDEATHSIG integration test was removed together
with that unsupported runtime, not reported as successful coverage.

32MiB unit/64MiB aggregate budget is unchanged; live total-overhead fit remains
unmeasured and a parent pre-grant gate. No live measurement was needed or made.

## Useful private failure diagnostics

Root collector and independent StopPost maintain separate root0600 per-run
phase/error JSON files. Private records contain phase, reason, assertion detail,
error type/errno and monotonic time. Mac writes a corresponding private0600
last-error file. Public errors expose fixed phase-specific reason codes only.
Subprocess argv/output/config/token contents are not copied into exception
records. Diagnostic disk/permission failure cannot prevent exact-rule cleanup;
that behavior has a mocked regression test. A failed diagnostic admission before
collector start cannot proceed to bind a listener.

## Baselines are not reset

Original enrollment swap24KiB is retained. Parent-reported28KiB/IO10 includes
historical4KiB/one-page growth, below the existing guard threshold. The test only
requires no further growth relative to its own actual start sample; it neither
re-enrolls nor rewrites enrollment state. Parent's16:50 host1946MiB/guest1173MiB
report is historical coordination information, not fresh test admission.

## Offline result

`PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-isolation_test.py`:
26 tests passed, no skips. Includes inherited attribution/alternate-entry refusal,
cleanup after missing scope, complete removal/rejection of child runtime,
private0600 diagnostic records, fixed public reasons, subprocess-token
non-disclosure and cleanup despite diagnostic failure. Existing node orchestration,
controls, canonical policy, counters, deadlines, reservations and admission
regressions remain. Python AST and `git diff --check` passed.

Ready for parent review/CI, not execution. Wait for data release and fresh
resource/identity checks plus a separate explicit node-window grant. Optional
child DNS/IPv6 remains disabled and unproved.
