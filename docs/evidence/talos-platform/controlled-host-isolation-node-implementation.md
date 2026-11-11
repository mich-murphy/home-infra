# Actual-node integration — OFFLINE implementation checkpoint

Parent approved targetless-counter bounded attribution, not live deployment or
execution. No new SSH/cluster inspection, listeners, test packets, unit starts,
cgroup joins or policy mutations were performed in this implementation step.
Media/qBit/SAB's active lease remains respected. Existing supervisor/isolation
scripts, workflows and parent brief/gates were not edited.

New Mac wrapper implements exact-node UID/hostNetwork Cilium checks, conservative
zero-active-proof-app/fixture checks and dormant controllers, fresh endpoint and
control ports, independently supervised collector startup, exclusive one-attempt
claim and exactly one installed-Perl constructor. Output is phase/status/hash
only. This is endpoint+cgroup attribution: unknown slirp source port is explicit,
not fabricated full-five-tuple evidence or TRACE/authenticated attestation.

Root node mode binds only the existing private host address10.77.1.100 at a
reserved unused high port, brackets the node attempt with known-running same-
endpoint controls using distinct reserved source ports below the actual ephemeral
range, verifies exact targetless-predicate adjacency to unchanged10/8 REJECT,
requires predicate/scope/REJECT counter growth and zero node-window listener
acceptance, removes its own exact rule and verifies canonical policy. Persistent
root-private reservations prevent reuse by this harness. App-zero/producer fields
are expressly Mac assertions, not kernel attestation.

The old long-held isolation flock was removed. Only a NEW test-specific mutex is
held, so original guard-stop/lifecycle locks are never blocked. Concurrent
identity/policy change causes test failure, not delayed guard enforcement.

Deadline correction: Runtime40s + up to10s main stop + up to10s ExecStopPost <=60s.
The earlier50+10 proposal overlooked that stop timeout can apply twice. Collector
success deadline35s. Unit cap remains32MiB; node controls are now in-process
rather than a second Python worker. Live MemoryPeak and combined64MiB budget fit
are still unmeasured; existing SSH/Kubernetes overhead must be included by the
parent before granting execution. No limit was raised. Guest Perl is limited to
12MiB address space/CPU1s, under timeout3; limit failure does not run a fallback.

Offline result:26 unittest methods,25 passed and1 Linux-only PDEATHSIG integration
skipped on macOS. Includes node predicate/no invented sport, correct private
REJECT adjacency, idle-cluster/controller rejection, one-connect orchestration,
safe hash-only output, Mac-loss fail-closed, unexpected listener readiness,
reservation reuse refusal, in-process control/no retry, exact StopPost argv and
resource/deadline rejection. Existing child pidfd and cleanup regression tests
remain. `git diff --check` passed. No live isolation acceptance is claimed.

Next: parent review/checkpoint and CI on Linux, media release, approved staging,
fresh headroom/total resource review, then a separate explicit live execution
grant. Optional owned-child DNS/IPv6 require their own later trial approvals.
