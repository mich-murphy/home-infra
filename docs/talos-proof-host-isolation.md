# Controlled host-isolation evidence — offline verifier and proposed live plan

**Status: implementation approved; live execution NOT approved. Authorized
read-only metadata inspection completed; no listener, packet test, cgroup join or
policy instrumentation performed. A separate parent execution grant is required.
This document does not release a platform gate.**

## Why another test

`evidence/talos-platform/network-test.txt` has failures against potentially dead
endpoints and a guest-local `::1` attempt. It cannot establish host enforcement.
`evidence/talos-network-storage/policy-drops-live.txt` is stronger: real Cilium BPF
policy-denied events match individual pod flows and a live synthetic backend.
Those pod datapath events do not establish QEMU host-cgroup enforcement.

Read `talos-proof-host-lifecycle.md` before proposing host access. Existing
`host_lifecycle.py` validates UUID `555e8603-58e6-4fb6-a190-378a3f11c257`, exact
configuration and process/cgroup incarnation. Reuse that authority; do not invent
an alternative VMID-only identity gate or modify the existing supervisor/scripts.
Current state must be collected privately in the approved window, not inferred
from old receipts or the PID/inode in historical evidence.

Important terminology: the reviewed `isolation.sh` normally ends denied flows
with **REJECT**, not DROP. DROP is the temporary chain-rebuild shield. No new deny
rule may be manufactured for this experiment. A host REJECT is distinct from a
Cilium BPF DROP. Never turn `ECONNREFUSED`, timeout, cumulative counters or a
checker exit code into a standalone isolation claim.

## Concrete live proposal for parent review (not executable authorization)

1. Wait for the data owner to release its lease, avoid the source-backup window,
   and obtain a distinct parent-approved host-isolation window. Recheck guard,
   exact lifecycle identity, current host headroom, swap and PSI. The reported
   ~1742MiB available is close to the existing1536MiB stop floor; it is **not**
   admission for extra workload. Parent sets an adequate extra margin before
   starting. No new VM, guest restart, memory increase or host tuning.
2. Read-only inspect existing host addresses, listener occupancy, cgroup membership
   and filter policy privately. Pick one already assigned RFC1918 host address
   for actual guest TCP; never use a production service port. Loopback is suitable
   for owned-child tests, **not** guest `::1`/127.0.0.1 transport. Do not assume
   slirp gateway `.2` equals a host interface address. If safe routability to the
   controlled endpoint cannot be established, leave actual-node evidence open.
3. Start a dedicated minimal synthetic HTTP listener on one unused high TCP port,
   bound only to the chosen address, with a fresh random synthetic token. No
   proxying, filesystem serving, credentials, upstream calls or real registry.
   Binding must fail closed on occupancy; no SO_REUSEPORT or takeover of another
   service. Maximum one request per control and one bounded scoped attempt;
   maximum six trials, each attempt<=5s and overall collector<=60s. Suggested
   listener/child limits:64MiB address space,2s CPU,32 file descriptors, bounded
   messages<=1024bytes. These are proposed limits, not an implemented runner.
4. From outside the proof cgroup, confirm the exact endpoint responds with the
   token. Record listener acceptance and response as well as the client result.
   Source/destination family, address, protocol and destination port must match
   the eventual host-visible attempt; use distinct source ports. No existing
   conntrack tuple may be reused: the policy first accepts ESTABLISHED,RELATED.
5. Prefer an **already present** host-network Cilium tool for a literal-address,
   no-DNS, no-proxy TCP request from the actual node network namespace. Confirm
   its real installed commands/help rather than inventing exec flags. Do not
   create a hostNetwork pod or download an image just to get a tool. Record
   producer identity and host-visible slirp tuple. If absent, a guarded Talos
   image-pull against a synthetic fake registry is an alternative proposal only:
   first verify installed Talos CLI/API support, bound retries/time, prove that
   neither DNS nor default registries/mirrors/redirects are contacted, and obtain
   parent review of the exact command. This fallback is not implemented or
   approved. If neither path is safe, report the actual-node gap.
6. Attribute the exact flow to the existing scoped OUTPUT jump and existing
   private-address REJECT rule. Save counted filter snapshots before/after;
   ordinary aggregate counter growth alone is insufficient. If the current
   backend supports legacy TRACE, propose **separately reviewed**, nonterminal
   raw OUTPUT TRACE matching only the approved cgroup, family, source/destination,
   protocol and destination port, with further source-port narrowing where known.
   No TRACE/LOG of general VM traffic or payload. LOG alone before a deny does
   not establish the verdict; nft trace requires its own reviewed parser. The
   offline checker currently understands only legacy filter TRACE lines.
7. Run the scoped attempt, then repeat the same outside-cgroup positive control.
   The synthetic listener must remain running throughout and receive neither
   scoped request nor production data. Match TRACE tuple including source port
   and protocol to the bounded attempt interval and the unchanged rule number;
   confirm that existing rule's packet count increases.
8. Optional UDP53 and IPv6: only if explicitly approved, start an owned synthetic
   listener on a free bound address/port. **Skip port53 if occupied**, including
   wildcard TCP/UDP listeners; do not stop DNS services or query production DNS.
   UDP53 uses a synthetic echo payload, not a resolver query. An IPv6 loopback
   listener must be V6ONLY and already supported; do not enable IPv6 or add an
   address. This proves matching on the existing cgroup filter, not DNS semantics.
9. For these optional cases, place only a fresh, initially blocked **owned child**
   in the existing VM120 cgroup, before it creates sockets. Never move, signal,
   freeze, enumerate-and-kill or otherwise manipulate QEMU/other guest processes.
   Parent must approve the transient non-QEMU cgroup member. An external timeout
   supervisor outside the cgroup must retain a pidfd/exact child identity, enforce
   limits and reap just that child. No broad `kill`, cgroup.kill or VM stop. Label
   this evidence **owned-child cgroup-filter rejection only**. Guest IPv6 is
   disabled; no result here can establish actual guest IPv6 transport.
10. Cleanup must survive harness failure: an independent outside-cgroup supervisor
    with a hard wall deadline owns instrumentation/listener/child cleanup, plus
    normal finally/signal handlers. A shell trap alone does not survive SIGKILL.
    Instrumentation must have unique exact specifications, be removed by those
    specifications rather than changing rule numbers, and never touch existing
    filter enforcement. Refuse to install it unless the independent cleanup
    supervisor is already acknowledged. If identity changes, headroom falls,
    guard fails or unexpected traffic appears, stop only test-owned work and
    retain the gap. Confirm no instrumentation/listeners/children remain, original
    filter structure persists, guard stays active, VM incarnation and other guest
    identities remain unchanged. No clearing counters or conntrack state.

**The initial checkpoint had no runner. The implementation-only extension below
now supersedes that statement.** Live review must still settle
precise APIs/commands, safe endpoint, resource margin, independent cleanup and
identity checks. The verifier cannot enforce these operating conditions.

## Offline checker contract

Run locally, without SSH, Kubernetes or Talos access:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-isolation_test.py
python3 -B infrastructure/proxmox-proof/verify-isolation.py SANITIZED_RECEIPT.json
```

The helper reads one bounded local JSON file and never opens sockets or runs
commands. Success means **receipt-consistent-not-authenticated**, not live
acceptance. Operator assertions, source/timestamp provenance, lifecycle checks,
actual listener ownership and independent cleanup still require human review.
Never feed it private configs. CLI failures print only an error type, not input.
Synthetic unit-test fixtures are explicitly not live evidence.

Receipt schema1 (`kind: controlled-host-isolation`) contains
`live_collection_approved: true`, `cleanup_confirmed: true`, and1–6 `trials`.
Each trial has:

- `origin`: `node-tool` (IPv4 TCP only) or `owned-cgroup-child`;
- `flow`: literal `src`, `dst`, integer `sport`, `dport`, `protocol` (`TCP`/`UDP`),
  representing **host-visible** packets. Destinations restricted to RFC1918 or
  IPv4 loopback, and IPv6 `::1`; routability/ownership checked by the live reviewer;
- `listener`: `address`, `port`, `protocol`, `owned: true`, `scoped_receives: 0`;
- `token`:32 lowercase hex characters, synthetic only;
- `attempt`: integer monotonic `begin_ms`, `end_ms` (<=5s), `result: denied`;
- `positive_before`, `positive_after`: identical endpoint/source/protocol,
  distinct fresh source ports, `outside_scope`, `listener_received`,
  `response_received` all true, matching `token`, integer `at_ms` within10s
  before/after the attempt. Each control includes its own `flow`;
- `policy_before`, `policy_after`: sanitized counted `iptables-save -c` or
  `ip6tables-save -c` **filter table only**, including COMMIT. Reviewed exact
  proof-chain serialization is required; state ordering is normalized. Backend
  serialization differences fail closed and require review, not policy changes.
  Unrelated filter structure must also remain identical; counters cannot decrease;
- `reject_rule`: existing1-based rule index inside TALOS_PROOF_120;
- `trace`:<=100 `{at_ms, line}` records, sanitized legacy kernel TRACE lines,
  preserving `TRACE: filter:OUTPUT:rule:1` and
  `TRACE: filter:TALOS_PROOF_120:rule:N`, SRC/DST/PROTO/SPT/DPT for the same tuple.
  Both must occur inside the attempt interval, scope jump before rejection.

The test module provides executable **synthetic-only** schema examples. Do not
copy their asserted approval fields into live receipts. Preserve sanitized raw
observations and a source-hash/provenance manifest separately; this consistency
checker is not an attestation system and does not authenticate those artifacts.

## Claims deliberately left open

- Actual node-origin private TCP until an approved successful collection.
- Live owned-child UDP53/IPv6 matching until separately approved collection.
- Actual guest IPv6 transport (disabled) and slirp DNS proxy resolver behavior.
- Alternate/public resolver bypass: the policy allows public UDP/TCP53; private
  UDP53 denial does not prove a restriction the policy does not implement.
- Exhaustive isolation, root-operator bypass, application readiness or production
  cutover. Do not weaken policy to satisfy any synthetic test.

## Implementation-only extension: actual backend and bounded collector

Parent approved implementation, **not execution**. Read-only inspection using
`ssh -o BatchMode=yes -o ConnectTimeout=5 root@proxmox` established:

- iptables/ip6tables1.8.11 **legacy**, systemd257. No backend change is needed.
- TRACE target not loaded; modules exist on disk. IPv4 nf_log is nfnetlink_log,
  IPv6 is NONE. Neither journal TRACE nor xtables-monitor (nf_tables-only) is a
  suitable assumed collector. No module or logger/sysctl changes were made.
- Guard active, enrolled config valid, captured VM incarnation matches.
  MemAvailable2134MiB, swap28KiB, swapIO10 at inspection (not execution admission).
- Existing host addresses include10.77.1.100,127.0.0.1,::1. UDP53 and high18081
  were absent from the listener inventory. Occupancy must be rechecked at binding.
- Existing Cilium pod `cilium-8thlg` has hostNetwork=true. curl/wget/busybox absent;
  bash5.3.9, perl, timeout and cilium-dbg present. Read-only Perl module loading
  confirmed IO::Socket::INET without creating any socket. No token/config output.

### Targetless counter alternative — approval still required

`collect-isolation.py` supports one loopback **owned-child** trial only. It does
not claim node transport and cannot be pointed at production endpoints. To avoid
logger changes, it inserts a targetless counter rule directly before the existing
private/IPv6 REJECT, matching source+destination literal address, protocol, source
port, destination port, proof cgroup, and unique comment. A targetless iptables
rule counts then continues; it neither allows nor denies. For IPv4 loopback this
is rule5; for IPv6 rule2. The existing REJECT moves one position while the rule
is present and is never replaced.

The current collector holds only its NEW test-specific lock (not the existing
isolation/lifecycle lock), verifies the exact reviewed
policy, brackets one child attempt with outside-cgroup token controls, validates
exact counter serialization and adjacency, requires exact counter growth and at
least matching growth of the adjacent original REJECT, removes the exact rule,
and verifies original policy structure. It emits a **different capture schema**,
`controlled-host-isolation-capture`, with status
`adjacent-counter-capture-pending-human-review`. The earlier TRACE receipt checker
is intentionally not told to accept this capture as if it contained TRACE.
A reviewer must accept/refuse this attribution method before any live window.

Collector unit32MiB MemoryMax plus joined child32MiB RLIMIT_AS bounds extra test
memory to<=64MiB. The joined child has CPU1s, fd24 and alarm4s bounds. It receives
GO only after the supervisor holds its pidfd; it arms kernel PDEATHSIG and checks
parent liveness first. It pins the original scope directory inode and reuses the
existing lifecycle checks against the parent's incarnation digest before joining
and before creating sockets. Only its own PID is written. No QEMU pidfd/signal
is used. The unit's CPUQuota10% applies before joining; afterwards the child does
only one small socket exchange, bounded by its CPU/wall limits.

Normal/error cleanup uses the retained owned-child pidfd. If the supervisor is
SIGKILLed, PDEATHSIG kills the escaped child; independent systemd ExecStopPost
removes the exact counter. Runtime40s plus main stop10s plus StopPost timeout10s bounds the unit
lifecycle to60s. The collector rejects runtime/memory/cgroup/unit/StopPost-argument mismatches and
checks the1792MiB floor, unchanged swap/IO and bounded PSI at checkpoints. These
checks supplement, never replace or stop, the existing guard.

### Exact proposed commands — DO NOT RUN without new parent grant

Installed `systemd-run --help` confirms --unit, --service-type and --property.
Stage only the new collector and verifier alongside the existing private
host_lifecycle.py **after separately approved deployment**. No existing file is
replaced. Generate a fresh32hex run id; never reuse one. Below is a proposal, not
an execution receipt:

```sh
# On Proxmox only after explicit deployment AND live execution approval:
STATE=/root/.local/state/home-infra/talos-proof
COL=$STATE/collect-isolation.py
ID=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
ARGS="--approve 555e8603-58e6-4fb6-a190-378a3f11c257 --mode child --address 127.0.0.1 --protocol TCP --port 18081 --source-port 20003 --control-before 20001 --control-after 20002 --run-id $ID"
systemd-run --unit="talos-proof-isolation-$ID.service" --service-type=exec \
  --property=RuntimeMaxSec=40 --property=TimeoutStopSec=10 \
  --property=MemoryMax=32M --property=CPUQuota=10% --property=TasksMax=8 \
  --property=LimitNOFILE=32 --property=UMask=0077 \
  --property="ExecStopPost=/usr/bin/python3 -B $COL --cleanup $ARGS" \
  /usr/bin/python3 -B "$COL" $ARGS --output "$STATE/isolation-$ID.json"
```

No --collect: retain failed unit status for inspection. A subsequent separately
reviewed UDP53 or ::1 trial changes only the endpoint/protocol arguments in BOTH
ExecStopPost and ExecStart, uses fresh ID/source port, and requires explicit
optional-child approval. Do not run concurrent collectors.

The earlier checkpoint did not integrate node TCP. The node wrapper described
below now integrates this available-client
candidate, whose interpreter/module presence is confirmed but whose network
execution is **not** performed/approved, is:

```sh
KUBECONFIG="$HOME/.local/state/home-infra/talos-proof/config/kubeconfig" \
  kubectl --request-timeout=5s -n kube-system exec cilium-8thlg -- \
  timeout 3 perl -MIO::Socket::INET -e \
  '$s=IO::Socket::INET->new(PeerAddr=>"10.77.1.100",PeerPort=>18081,Proto=>"tcp",Timeout=>1) or exit 2; print $s "SYNTHETIC_TOKEN"; $s->recv($r,128); print length($r)," bytes\n";'
```

Do not run this against an absent listener or treat it as standalone denial
proof. It needs its own private-host-bound synthetic listener and controls, exact
host-visible slirp tuple attribution, and parent-reviewed integration. No curl
image pull or imaginary Talos command is required. The child mode does **not** provide that listener. The implementation extension
below adds a distinct node mode; only a separately approved successful live
collection could complete the actual-node requirement.

## Actual-node integration checkpoint — implementation only

The parent has approved **targetless-counter bounded attribution**, not live
execution/deployment. This extension supersedes the earlier loopback-only scope
and pending-method decision. The method is explicitly **not TRACE and not an
authenticated attestation**.

New Mac entry point (DO NOT RUN until media releases and a new parent grant):

```sh
python3 -B infrastructure/proxmox-proof/run-node-isolation.py \
  --approve-live-window 555e8603-58e6-4fb6-a190-378a3f11c257
```

There is deliberately no deploy/copy command in the wrapper. The parent must
approve staging the new collector/verifier alongside the unchanged lifecycle
module separately. The flag records operator intent; it does not itself confer
authority or override an active application lease.

### One actual node attempt

1. The wrapper forces Kubernetes server `https://127.0.0.1:64120`, validates the
   single Ready node UID4845bfd5-3bdb-453d-8503-83b43edb7a1e, and finds exactly one
   Ready hostNetwork Cilium agent on that node. It refuses **any active proof-*
   application/fixture pod**, nonzero Deployment/StatefulSet replicas, app
   DaemonSets, unsuspended CronJobs, or unfinished unsuspended Jobs. It does not
   stop or scale anything. This is intentionally conservative and may block
   non-application proof namespaces too; do not bypass it by stopping infrastructure.
2. It chooses a fresh32hex run id, a high TCP destination25000–28999 on the
   existing host address10.77.1.100, and three distinct non-ephemeral candidate
   source ports10000–18999. Root collector checks the actual ephemeral range,
   requires source ports below it, exclusively reserves endpoint and control
   source ports on disk, and binds without REUSE*. Reservation collision or
   occupancy fails closed, with no automatic endpoint retry. Old reservations
   remain private freshness metadata; do not delete them to force port reuse.
3. The wrapper starts only the new transient unit with the same32MiB MemoryMax,
   CPUQuota10%, TasksMax8 and fd32 limit. **Corrected hard deadline accounting:**
   RuntimeMaxSec40 + up to10s main termination + up to10s ExecStopPost =60s,
   rather than assuming TimeoutStopSec applies only once. Collector's own success
   deadline is35s. It validates actual unit properties and the exact parsed
   ExecStopPost argv, including all endpoint/control arguments.
4. The collector takes only `controlled-host-isolation.lock`, a new nonblocking
   test-only mutex. **It never takes the original isolation/lifecycle lock**, so
   the guard's existing stop path is unblocked. Any concurrent policy/incarnation
   change invalidates the evidence rather than being delayed by the test.
5. Collector binds the dedicated literal-address TCP echo listener. The first
   positive control runs in-process outside the proof cgroup, binds the reserved
   source address/port, checks the exact accepted peer and synthetic token, and
   requires exactly one acceptance. No second Python interpreter/thread is
   needed in node mode. The second control uses the other fresh source port.
6. The node predicate is exactly QEMU cgroup + sourceHostIP10.77.1.100 +
   destinationHostIP10.77.1.100 + TCP + unique destination port. **Unknown slirp
   source port is deliberately omitted**, not invented. For this address the
   targetless counter is directly adjacent to the existing10/8 REJECT (rule3
   before insertion). No intervening rule or new verdict is allowed. Reviewed
   canonical policy, instrumentation serialization/adjacency and initial zero
   counter are checked before publishing `armed`.
7. The Mac revalidates idle workloads and the same Cilium UID, writes a private
   producer-assertion record, and exclusively claims one attempt with noclobber.
   No retry is allowed even after uncertain SSH/exec failure. It executes the
   installed Perl IO::Socket::INET constructor **once**, under existing `timeout 3`
   with guest address-space limit12MiB, CPU1s and fd16. Limit setup uses `&&`, so failure
   cannot run an unbounded fallback. No DNS, image pull, shell network probe,
   proxy, redirect, new pod or registry is involved. The actual command is built
   by `node_command()` and passed as argv, not interpolated into a remote shell.
8. Collector waits at most20s for a claim and6s after seeing it, checking guard,
   exact identity,1792MiB floor, unchanged swap/IO and PSI at least once per
   second in that window. Missing Mac/result is **failure**, never denial.
   Any readable listener connection during the node window is failure. Root
   requires the Mac's denied-connect result, positive predicate counter delta,
   scoped OUTPUT jump growth and at least matching growth in the immediately
   adjacent original REJECT. Retransmissions can produce multiple packets but
   there is only one node connection-constructor call.
9. Repeat the outside-cgroup control, remove the exact predicate, verify the
   unchanged canonical policy, and close the owned listener. Normal failures
   remove instrumentation; uncertain insertion or supervisor death is handled by
   the independent exact-argv systemd ExecStopPost. No VM stop, process movement,
   QEMU signal, conntrack clearing, module/backend/sysctl change or global rule
   flush occurs. Node mode does not join any child to the VM cgroup.
10. The wrapper rechecks idle workloads/producer identity and requires the unit
    inactive with Result=success and ExecMainStatus0, including completed
    StopPost. It outputs **phase/status/receipt SHA256 only**. Raw capture and
    synthetic token remain in root-private state. Marker producer fields are
    explicitly Mac assertions, not authenticated kernel observations.

The resulting capture labels the method `endpoint+cgroup counter, not TRACE or
authenticated attestation`, records `slirp_source_port: unknown`, predicate packet
count and original policy snapshots. Human review must retain the narrower
endpoint/cgroup claim. A single controlled endpoint does not prove exhaustive
private-network/DNS bypass coverage. No live result exists yet.

### Resource practicality and remaining gates

The32MiB unit cap is unchanged. In-process node controls remove the largest
avoidable subprocess overhead; native iptables/systemctl helpers still share
that cap, and the receipt records systemd MemoryPeak. Fit has **not** been
measured live. OOM, unsupported property serialization, too-small Perl12MiB
limit, stale ports or timeout yields failure and cleanup, not a budget increase
or weaker test. Existing SSH/Kubernetes transport overhead is not bounded by the
unit's cgroup; the parent must include it in the64MiB total-extra-resource review
and fresh headroom check. Do not claim that MemoryMax alone measures all added
host/guest overhead. If adequate margin or the total budget cannot be established,
refuse execution rather than raise limits.

Optional owned-child UDP53/IPv6 remain implemented but **not authorized to run**.
The Linux no-network PDEATHSIG integration test can be run in fresh CI using
`PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-isolation_test.py`; this macOS
checkpoint skips that one test. No existing workflow was edited by this owner.

Resource planning is32MiB for all collector/native helper processes plus at most
24MiB combined guest address space for timeout+Perl (each inherits12MiB), leaving
8MiB of the64MiB budget for SSH/control-transport overhead. That8MiB allowance is
not independently enforced by this unit; it is an explicit pre-grant measurement
gate, not a claim of demonstrated fit. No increased limit or live run is
authorized by this planning arithmetic.
