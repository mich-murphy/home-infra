# Controlled host isolation — node-only collector

**Implementation/method approved; deployment and live execution NOT approved.**
The data owner currently has the exclusive CouchDB→Miniflux window. Earlier
application-zero observations are stale. Wait for release, fresh parent resource
review and a separate explicit execution grant. No platform gate is released by
this document or by passing offline tests.

## Evidence gap and precise method

The historical `evidence/talos-platform/network-test.txt` timeout/refusal tests
lack known-running private controls and per-flow host verdicts. Its
`ISOLATION-PASS` is not accepted evidence. The exact Cilium BPF events in
`evidence/talos-network-storage/policy-drops-live.txt` are strong pod evidence,
not proof of QEMU host-cgroup filtering.

The reviewed permanent host verdict is **REJECT**, not DROP. DROP is only the
rebuild shield. The parent-approved method is a **targetless adjacent counter**,
not TRACE or authenticated attestation. No new allow or deny rule is introduced.

Read-only inspection previously established iptables/ip6tables1.8.11 **legacy**,
systemd257, and a valid active guard/incarnation. TRACE is not loaded; IPv4 nf_log
is nfnetlink_log, IPv6 is NONE. The collector does not load modules, change
logging/backend/sysctls, or assume journal/xtables-monitor TRACE availability.
The existing host-network Cilium tool has Perl/IO::Socket::INET, bash and timeout;
curl/wget/busybox are absent. Those inspections created no test sockets.

## Current implementation: actual node TCP only

- `collect-isolation.py`: independently bounded root collector and exact cleanup.
- `run-node-isolation.py`: Mac orchestrator; no deployment action.
- `verify-isolation.py`: offline legacy-TRACE receipt consistency checker, not an
  attestation system. Its older synthetic child fixtures are not executable
  authorization or evidence of a budget-safe child collector.
- `tests/talos-proof-isolation_test.py`: offline synthetic/mock regression suite.

**Child/UDP53/IPv6 execution is disabled**, not merely awaiting a flag. The old
Popen/second-Python runtime, cgroup-join code, pidfd child machinery and related
CLI flags have been removed. There is no negative child process in node mode.
The old proposed loopback-child unit command is withdrawn. A future child design
needs separate budget proof and review: setting RLIMIT_AS below an interpreter's
already-existing mappings does not establish a memory bound on those mappings.
The old PDEATHSIG integration test was removed with that unsupported runtime;
the current suite has no platform-specific skip.

### One bounded node attempt

1. Mac forces API server `https://127.0.0.1:64120`, requires one Ready node with
   UID4845bfd5-3bdb-453d-8503-83b43edb7a1e and a unique Ready hostNetwork Cilium
   agent on it. It refuses active proof-* application/fixture pods, nonzero
   Deployment/StatefulSet replicas, DaemonSets, unsuspended CronJobs and unfinished
   unsuspended Jobs. It never scales/stops anything. This intentionally
   conservative superset may block infrastructure proof namespaces too; do not
   stop infrastructure to bypass it. Recheck immediately before the attempt and
   after completion, not just at an earlier checkpoint.
2. Choose a fresh32hex run id, destination TCP25000–28999 on the **existing**
   host IP10.77.1.100, and two distinct positive-control source ports. Root
   validates those source ports are below the actual host ephemeral range.
   Persistent root-private exclusive endpoint/control-port reservations prevent
   harness reuse. Reservation collision or bind occupancy fails closed; there
   is no fallback endpoint, SO_REUSE*, production service probe or conntrack clear.
3. Root validates enrollment/configuration and exact QEMU incarnation using the
   unchanged existing `host_lifecycle.py`. It checks the active guard,
   MemAvailable>=1792MiB, unchanged test-start swap/IO, and existing PSI bounds.
   These checks supplement, never stop or replace, the existing guard.
4. Bind the dedicated literal-address echo listener. Positive controls execute
   **in-process**, outside the proof cgroup, using the two fresh source ports.
   Require the exact accepted peer, synthetic token/response and exactly one
   acceptance per control. No second Python interpreter or thread is started.
5. Verify the canonical filter: **one sole cgroup-scoped OUTPUT entry**, first
   in OUTPUT, and no alternate proof-chain entry. Insert a targetless predicate
   directly before the existing matching10/8 REJECT (original rule3), matching
   sourceHostIP10.77.1.100, destinationHostIP10.77.1.100, TCP, unique destination
   port and unique comment. Unknown slirp source port is deliberately omitted.
6. **No redundant inner cgroup match** is present. Attribution is inherited from
   the verified sole scoped OUTPUT entry. This is essential for cleanup: exact
   `-C/-D` must not need to resolve a cgroup path after the guard stops QEMU and
   removes its scope. Predicate cleanup performs no cgroup lookup and does not
   inspect or signal QEMU. Snapshot normalization removes only the exact test
   predicate and verifies immediate adjacency with no intervening rule.
7. Publish `armed` only after verifying canonical policy/adjacency and initial
   zero predicate count. Mac revalidates node/Cilium identity and idle workloads,
   records private producer assertions and exclusively claims one attempt with
   noclobber. Never retry after an uncertain SSH/exec result.
8. Execute the installed Perl IO::Socket::INET constructor **once**, against the
   literal controlled address/port. Existing `timeout 3`, guest address-space
   limit12MiB, CPU1s and fd16 apply before Perl starts; `&&` prevents fallback if
   limit setup fails. There is no DNS, image pull, proxy, redirect, registry,
   new pod or service modification. `node_command()` constructs exact argv.
9. Root waits<=20s for a claim and<=6s after observing it, checking identity,
   guard/headroom/swap/PSI each second. Mac loss, missing result, or any readable
   listener connection during the node window is failure, not inferred denial.
   Require denied-connect result, positive predicate counter delta, scoped OUTPUT
   growth and at least matching growth of the adjacent unchanged REJECT.
   Retransmissions may create multiple packets from this one constructor call.
10. Repeat the same-endpoint positive control, delete only the exact predicate,
    verify unchanged canonical policy, and close the owned listener. Mac requires
    postchecks and inactive unit with Result=success/ExecMainStatus0, including
    completed StopPost. Output is phase/status/receipt SHA256 only; raw receipts
    and synthetic tokens remain private. Producer fields are explicitly Mac
    assertions, not authenticated kernel observations.

The capture labels **endpoint counter inheriting sole scoped OUTPUT entry; not
TRACE or authenticated attestation**, records unknown slirp source port, predicate
count and policy snapshots. This is narrower than full-five-tuple tracing and is
not exhaustive private-network or DNS bypass coverage. The TRACE consistency
checker deliberately does not accept this distinct capture schema as TRACE.

## Independent cleanup, locks and limits

Only the new nonblocking `controlled-host-isolation.lock` is held. The original
isolation/lifecycle locks are **never** taken: guard stop must remain unblocked.
Concurrent policy/incarnation changes invalidate evidence rather than delaying
existing lifecycle enforcement.

The exact cleanup argv is independently owned by systemd ExecStopPost. Normal
failures delete the predicate; uncertain insertion, main-process crash or Mac
loss still reaches StopPost. Cleanup is idempotent, targetless and independent of
scope-path existence. It never flushes chains, clears counters, changes existing
verdicts, stops existing units or touches other guests.

- RuntimeMaxSec40 + up to10s main stop + up to10s StopPost <=60s. TimeoutStopSec
  can apply twice; the earlier50+10 proposal was not a correct worst-case bound.
- Collector success deadline35s; MemoryMax32MiB, CPUQuota10%, TasksMax8, fd32.
  Actual unit properties and exact parsed cleanup argv must match the run.
- Node controls are in-process. Native iptables/systemctl helpers share the32MiB
  cap. No second Python image initializes before a cgroup join: that route is gone.
- Guest timeout+Perl inherit12MiB address-space limits each before exec, giving a
  conservative24MiB guest-process allowance. With the32MiB host cap this leaves
  8MiB of the64MiB plan for transport overhead. Existing SSH/API overhead is not
  independently capped by the test unit; **measured total fit remains a parent
  pre-grant gate**, not an assertion from RLIMIT_AS or MemoryMax alone.
- Capture systemd MemoryPeak. OOM, unsupported property serialization, too-small
  Perl limit or timeout fails closed. Do not raise the aggregate64MiB budget.

## Private diagnostics and historical resources

Collector updates root0600 per-run `.collector.diagnostic.json`; StopPost has a
separate `.cleanup.diagnostic.json`. Records retain precise phase, fixed reason,
failed assertion detail, error type/errno and monotonic time. Subprocess argv,
outputs, configs and tokens are not copied into exception diagnostics. Diagnostic
I/O failure must **never** prevent rule cleanup. Public failures emit fixed
phase-specific reason codes, not private exception text or opaque RuntimeError
alone. Mac writes analogous root-private-user-state
`node-isolation-last-error.json`; its public output is also fixed reasons only.

The original enrollment swap baseline remains **24KiB**. Parent-reported current
28KiB/IO10 includes historical **4KiB/one-page growth**, below the existing guard
threshold, not a reset baseline. The collector captures actual test-start samples
and requires no further swap/IO growth during its test. It does not enroll, write
or replace the original baseline. Parent's16:50 report1946MiB host available and
1173MiB guest minimum is a historical coordination report, not current admission.
Fresh checks must follow the active data owner's release.

## Commands and remaining acceptance

Offline only:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-isolation_test.py
```

After **separate staging AND explicit live grant only**, the proposed Mac entry is:

```sh
python3 -B infrastructure/proxmox-proof/run-node-isolation.py \
  --approve-live-window 555e8603-58e6-4fb6-a190-378a3f11c257
```

The flag records operator intent, not authority. Wrapper stages nothing and
starts only the new bounded transient collector unit. Exact unit/client argv
are in `launch_command()` and `node_command()`; no invented Talos CLI or image
pull is used. No --collect is passed: preserve failed-unit status for review.

Still unproved: live actual-node private TCP under this method, practical32MiB
collector/64MiB aggregate fit, live supervisor-failure cleanup, slirp DNS proxy and
alternate resolver behavior, actual guest IPv6 (disabled), and optional child
UDP53/IPv6 (implementation disabled). No root-operator bypass, exhaustive
isolation, readiness or production-cutover claim is made.
