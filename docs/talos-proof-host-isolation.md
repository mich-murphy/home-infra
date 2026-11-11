# Controlled host-isolation evidence — offline verifier and proposed live plan

**Status: offline only; no live test, listener, host metadata probe or policy
instrumentation performed by this work. Parent approval and a separate execution
window are required. This document does not release a platform gate.**

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

**No live runner is included.** Its review must settle backend/TRACE support,
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
