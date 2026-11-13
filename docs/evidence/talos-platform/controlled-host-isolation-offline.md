# Controlled host isolation: OFFLINE checkpoint

Status: **NOT LIVE EVIDENCE; host isolation gates remain open.**

All work ran locally in `/Users/mm/dev/home-infra-talos-proof`. No SSH, host
metadata request, Kubernetes/Talos API request, socket listener, network probe,
cgroup movement, process signal or policy mutation was performed. Existing
supervisor/isolation scripts and parent briefs/gates were not edited.

## Reviewed inputs

- `docs/talos-proof-host-lifecycle.md`: exact-incarnation authority, guard/headroom
  constraints and historical host lifecycle acceptance, not DNS/IPv6 acceptance.
- `docs/talos-proof-platform.md`: historical timeout-only `ISOLATION-PASS` is an
  unaccepted assertion; guest IPv6 is disabled in slirp.
- `docs/evidence/talos-platform/network-test.txt`: weak timeout/refusal evidence,
  without known-running private controls or per-flow host verdict correlation.
- `docs/evidence/talos-network-storage/policy-drops-live.txt`: strong pod Cilium
  BPF DROP correlations, not a demonstration of host-cgroup REJECT enforcement.
- Local `infrastructure/proxmox-proof/isolation.sh`: actual permanent verdict is
  REJECT. DROP appears only as the temporary rebuild shield. Public UDP/TCP53 is
  allowed; private DNS denial cannot prove public resolver prohibition.

## Offline validation performed

```text
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-isolation_test.py
.........
Ran 9 tests in 0.079s
OK

git diff --check
(no output; success)
```

Nine test methods include multiple rejection subcases: independently reviewed
policy shape, state-order normalization, known synthetic positive receipts,
IPv4/IPv6 and TCP/UDP child-only labeling, missing controls, wrong endpoints,
reused ports, stale/out-of-window traces, mismatched tuples, timeout-only result,
missing scope/reject counter deltas, counter reset, policy drift, manufactured
deny, duplicate entry, scope mismatch, approval/cleanup gates, trial bounds and
CLI input non-disclosure. Socket and subprocess operations are forbidden during
an in-process verifier test. The separate CLI smoke test launches only the local
Python helper against temporary synthetic files; it opens no network sockets.

The synthetic test fixtures assert observations to exercise the parser. They are
**not a host capture**, do not represent approved live collection, and must not
be published as successful host isolation evidence.

## Source SHA256 at checkpoint

```text
181a25120da865c669a20f67820f0d5613a360f4774cc1a4137125acf657572b  infrastructure/proxmox-proof/verify-isolation.py
8920d6fba1188405a3989d610dcb953cc5af83066784a09811400fb3d4e27cea  tests/talos-proof-isolation_test.py
a5f2efb3fef57e461b7ec3f45784077a3c87720a5358b4b7adb9f420dedd5967  docs/talos-proof-host-isolation.md
81675b61ca2867a41e942d54fa9980c4aa37e9472981bbc9ab469eb5a4de8f94  infrastructure/proxmox-proof/isolation.sh (read only; unchanged)
ef58d97d423d1e283b2917a0b2e024420c6786b58fb232c1dad2941e11e2f4c5  infrastructure/proxmox-proof/host_lifecycle.py (read only; unchanged)
```

## Parent decision needed before live implementation/execution

The full proposed plan and schema are in `docs/talos-proof-host-isolation.md`.
Approve/refuse a separate window only after the data lease ends and resource
headroom is adequate. Settle exact synthetic host endpoint, installed node tool
or supported bounded registry fallback, current policy/TRACE backend, owned-child
authority and independent timeout cleanup. No executable live runner is included.

Remaining gaps: actual-node private TCP, live child cgroup UDP53/IPv6 matching,
slirp DNS proxy/alternate resolver behavior, and actual guest IPv6 (disabled).
Verifier success means only `receipt-consistent-not-authenticated`; human review
of raw provenance, identity, controls, safe collection and cleanup remains
mandatory. No parent acceptance gate has been upgraded.
