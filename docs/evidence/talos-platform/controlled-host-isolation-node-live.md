# Bounded actual-node host rejection — live result

**One actual node TCP attempt demonstrated endpoint/cgroup-attributed REJECT.**
Parent owns acceptance. This is not TRACE, full-five-tuple correlation,
authenticated attestation, exhaustive private isolation or DNS/IPv6 coverage.
The exclusive node window is released. Two authorized unit starts were consumed;
there is no authority for another start or optional child test.

## Authority and resources

The original64MiB planning gate was refused and retained in8d30dc43. The parent
explicitly revised the envelope to96MiB:32root enforced +24guest retained
conservatively +40transport. Session/helper conservative RSS29.35MiB was measured,
leaving10.65MiB transport planning margin. Existing global Tailscale daemon is
excluded baseline; neither transport nor existing daemon is claimed to have a
new hard cgroup cap. No private-only/PSS substitution or silent budget reduction.

Initial admission required1888MiB (fresh2003MiB before start2), during1792MiB;
start2 capture1961MiB, independent postcheck2016MiB. Guard1536MiB unchanged.
Swap remained28KiB/IO10. Both enrolled baseline and original baseline file still
24KiB; original IO9 and historical4KiB/one-page growth remain disclosed. No
baseline re-enrollment, backup-job write, source-data/archive write or host tuning.

## Two starts, one real TCP constructor

1. **Failure, not policy proof:** frozen c9e19152 root code; original external
   timeout failed under12MiB. Exact socket-free reproduction returned127 with
   libsystemd.so.0 mapping failure. The original wrapper did not preserve actual
   client exit/stderr, so diagnosis relies on that reproduction plus private
   forensics, not invented first-attempt counters. Root node-window deadline
   failed; StopPost complete; MemoryPeak13,131,776bytes (12.52MiB). Failed unit
   status and private journal/diagnostics retained.
2. Parent approved wrapper-only b7da6d29 correction: Perl alarm3 armed before its
   only constructor, exit124 on alarm (never denial2), AS12MiB/CPU1s/fd16 retained.
   Socket-free exact chain confirmed module VmSize10,612KiB/RSS8,032KiB and alarm
   exit124 in3.100s. Root collector/verifier stayed frozen, hash-verified c9e19152.
   The second unit then completed successfully, client exit2, standard kubectl remote-exit2
   diagnostic only (no alarm marker), collector/StopPost complete. Actual root MemoryPeak13,312,000
   bytes (12.695MiB) captured before exit; post-exit MemoryPeak/MemoryCurrent no
   longer set after cgroup resources were released.

Private raw successful receipt SHA256:
`79dc13fe74a43b3c196989b441112b6f2ff3888abeb1c5efa08c9e8517fd104a`.
Raw policy snapshots, journals, producer assertions and synthetic token remain
private; no credential or token values are published.

## Controls and attribution

Existing host address10.77.1.100, owned fresh TCP port28614. Source control ports
11008 and11009 are distinct, reserved, and below actual ephemeral32768–60999.
Each outside-cgroup control received the exact synthetic response and exactly
one listener acceptance. Node-window listener acceptance was zero.

The predicate matches sourceHostIP/destinationHostIP/TCP/unique destination port
and run comment, with no verdict and **no inner cgroup match**. Its attribution
is inherited from the verified sole QEMU-cgroup OUTPUT entry, first in OUTPUT,
with no alternate chain entry. Predicate directly precedes the original10/8
REJECT (original chain rule3), without an intervening rule. Unknown slirp source
port is explicitly omitted. Scope-independent exact cleanup does not resolve a
possibly removed cgroup path.

Independent offline parsing of private live receipts established:

| Observation | Before | After / delta |
|---|---:|---:|
| Unique endpoint predicate packets | 0 | 2 / +2 |
| Existing adjacent10/8 REJECT packets | 0 | 2 / +2 |
| Sole scoped OUTPUT jump | — | +230 |
| Outside positive-control listener acceptances | 1 before | 1 after |
| Node-window listener acceptance | — | 0 |

Two predicate packets do not imply two application connects: the reviewed Perl
has one constructor and no retry loop; transport may emit multiple packets.
Scoped OUTPUT also counts ordinary node traffic, so its230-packet growth is
supporting scope evidence, not itself exact denial attribution.

All full canonical filter structures match before, after predicate normalization,
after cleanup, and an independent postcheck. Unrelated rules are represented by
a structural hash in the JSON companion rather than dumping unrelated policy.
See `controlled-host-isolation-node-live.json` for exact hashes and sanitized
counter/control/resource receipt.

## Independent postcheck / release

- Guard active, same QEMU3987981/start288449562/scope inode61718.
- VM101/102/120 PIDs, start ticks and configuration hashes unchanged.
- Original lifecycle/isolation source hashes unchanged; no existing unit stopped.
- No test predicate rules, no listeners in candidate25000–28999 range.
- Both test units MainPID0/ControlPID0, no cgroup members, TasksCurrent and
  MemoryCurrent not set. First failed record retained for forensic review;
  second inactive/Result=success/ExecMainStatus0.
- Expected Ready node UID and same Ready hostNetwork Cilium UID revalidated;
  proof app/fixture pods inactive and controllers dormant at both wrapper
  checks and independent postcheck. These are checkpoints, not future leases.

No cgroup join, guest restart, route/address/sysctl/module/logger change,
production endpoint/DNS probe, new allow/deny rule or conntrack/counter clear.
Node window released promptly after these checks. Media/data may activate only
under the parent's next separate lease.

Remaining: guest DNS/alternate resolver bypass, IPv6 transport (disabled),
optional child UDP/IPv6 implementation (disabled), comprehensive endpoint/range
coverage, root-operator bypass and production readiness. No upgrade of these
claims is inferred from this one controlled result.
