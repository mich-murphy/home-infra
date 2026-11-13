# Offline Worker containment — partial preparation only

Base HEAD: `0862d3b518f1279b76e02989d46dd42b0d1eafe1`; uncommitted source snapshot:

- `scripts/talos-proof-media-headless-integration.py`: SHA256 `095138e869bb188552070b7d5674149308e2b7cdc431d146d4eb9aab9e1e0b32`
- `tests/talos-proof-media-headless-integration_test.py`: SHA256 `006cc31ba7ef2744baa29b901874fdd0e50c36064af9abbf86e360778555221c`

## Contract and assumptions

Worker IPC polling never reaps. Successful `Popen(start_new_session=True)`
establishes the retained leader PID=SID=PGID. TERM, one-second nominal grace,
final KILL, then reap share one nominal two-second cleanup budget. IPC close
failure does not skip group cleanup. Known-reaped, changed SIGCHLD policy, or
ownership-check failure reports cleanup UNKNOWN without signalling OR a fresh
waitpid. The retained handle then needs explicit owner disposition. No signal
follows reaping. Serialization precedes resource allocation; spawn failure
closes both owned sockets, preserving the original exception.

Validity requires exclusive waiter ownership, a retained Popen reference,
default SIGCHLD policy, no native SA_NOCLDWAIT, and descendants staying in the
original process group. Visible SIGCHLD policy and known returncode are checked;
arbitrary foreign waiters/native policies cannot be excluded by these checks.
No protection against such a waiter or escaped SID/PGID is claimed. Inspected
all Worker callers: production Worker ownership is internal; Pump's process
references refer to the decoder and were not changed.

Darwin can return ESRCH for zombie getpgid/getsid before reaping. Those queries
are not used as an ownership test. A real NOTE_EXIT observation establishes an
exited-but-unreaped leader in the descendant regression. Darwin group signalling
can also fail when no live group members remain; non-ESRCH signal errors stay
UNKNOWN, not silently treated as cleanup success. The IPC-only fixtures ignore
TERM and establish readiness before cancellation.

## Focused tests

Interpreter: `/nix/store/npyrmk982c91wj89yp9nvpfpxspszr70-ansible-tooling/bin/python3`
(Python 3.13.13), Darwin. Commands, run sequentially:

```
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-headless-integration_test.py -v
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-headless_test.py -q
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-headless-followup_test.py -q
git diff --check
```

Final portability-corrected results: integration 28, headless 18, follow-up 8
passed; diff check clean. All runs were on Darwin; no skips.
Integration's real synthetic leader/child/grandchild report ancestry, SID and
PGID over owned local IPC. TERM-resistant descendants retain the owned endpoint;
EOF and leader reap are bounded. Tests instrument no pre-final-signal poll,
communicate or wait, and no post-reap group signal. Both live-leader and Darwin
NOTE_EXIT-before-cleanup variants run, without skips. The same mandatory
exit-before-cleanup regression selects exact-owned-PID nonreaping waitid on
Linux, as detailed below. Independent test cleanup
retains the exclusive unreaped anchor through any fallback final KILL and uses
a bounded reap. Tests also cover IPC-close failure, denied TERM, known-reaped,
policy/identity failure with no signal or new wait, spawn/serialization failure,
and blocked run/public entrypoints before state/network access.

Initial attempts failed on the invalid zombie SID/PGID query and empty-group
signalling; these were not acceptance evidence. Initial synthetic descendants
had a 30-second self-exit, and their numeric groups were not signalled after
leader reaping. No process scans/global pkill were used.

## Parent-found portability correction

Parent review found the first 26-test implementation unconditionally used
`select.kqueue()`, unavailable on Linux CI. That version's passing Darwin result
was not Linux portability evidence. The observer now selects:

- Darwin: register `KQ_FILTER_PROC` / `NOTE_EXIT` before submitting the action
  that permits the fixture to exit. Require the returned event's exact leader
  identity and NOTE_EXIT flag, with Popen.returncode still None.
- Linux: use only `waitid(P_PID, owned_pid, WEXITED | WNOHANG | WNOWAIT)` in a
  nominal two-second monotonic local observation loop. Require the exact owned
  PID, CLD_EXITED, zero exit status, and Popen.returncode still None. WNOWAIT
  preserves the unreaped anchor; this is not Popen.poll/wait or a process scan.
- Unsupported platforms: fail explicitly; never silently skip the regression.

The common real child/grandchild test still requires final group KILL before
actual reap. Two new test methods bring integration to 28: Linux branch-contract
coverage using doubles (no Linux kernel execution), and explicit unsupported-
platform failure. Linux doubles cover a not-yet-exited result, exact options/PID,
success, wrong identity, wrong exit code/status, and monotonic expiry. Actual
Darwin NOTE_EXIT/descendant coverage passed in the rerun. **Actual Linux kernel
waitid and real Linux descendant execution remain unverified until parent-
scheduled CI; no Linux run is claimed here.** Production Worker source was not
changed for this portability correction. No full gate, commit or push was run.

## Limits / unchanged HOLDs

The cleanup budget bounds nominal grace and wait allowance, not unpreemptible
OS/Python stalls, socket-close implementations, scheduling, or guaranteed KILL
completion. EOF proves endpoint closure for this controlled fixture, not a
universal process-tree census. Local cleanup is not remote HTTP cancellation,
request ordering, native session attribution, or application acceptance.

Whole-pipeline deadline remains OPEN: guards, headers, decoder setup/producer,
source.close/join, actions/history and final expiry are not jointly preempted.
No supervisor, deadline scaffold, headless.py/general guard/profile changes,
CLI activation, or native-oracle changes were added. run() remains HOLD before
all access; both public CLIs remain BLOCKED. Session mapping, FFmpeg flush,
settings/pagination, immutable runtime accounting and browser401 remain separate
HOLDs. No runtime authority, live binding, production --owned-worker execution,
private proof state, credentials, remote API/SSH, image execution, commit or
push. Existing follow-up and original acceptance evidence leaves are unchanged.
Parent owns root-document integration and scheduling the full gate.
