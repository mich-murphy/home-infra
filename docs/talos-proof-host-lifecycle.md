# VM120 supervised lifecycle (activation awaiting coordinator lease)

This implementation owns only proof VM120. It does not change existing guests,
host tuning, global networking, production storage or existing systemd units.
**Local tests are not live fail-closed acceptance. No host reboot is authorized.**

## Identity and startup contract

Approved SMBIOS UUID: `555e8603-58e6-4fb6-a190-378a3f11c257`, name `talos-proof`.
Only 2560/3072MiB fixed memory, 2 cores, x86-64-v2-AES, known dedicated VM120
disks, q35/OVMF, onboot0, no standard NIC/GPU/USB/hook and exactly the reviewed
slirp arguments are accepted. Four forwards must bind 127.0.0.1; management ports
are fixed. Gateway destination ports may be distinct NodePorts 30000–32767, but
**every configuration change requires explicit re-enrollment** of its exact digest.
Current approved Gateway mapping is 18080→30659, 18443→30310. Re-enroll only after
the coordinator approves any new dynamic ports/RAM. This is not an unrestricted
VMID/name gate. Generated credentials and full configs never enter evidence.

Root0700 state: `/root/.local/state/home-infra/talos-proof`. Identity, startup and
incarnation receipts are atomically replaced/fsynced root0600 files. The original
swap baseline is retained, never refreshed to hide subsequent swap growth.

`start.sh` starts the dedicated **oneshot** `talos-proof-start.service`:

1. Serialize with flock, validate exact enrolled configuration, reject an existing
   PID file/running guard, require Linux pidfd support.
2. Fresh admission: MemAvailable >= configured RAM + **1536MiB margin + 384MiB
   QEMU overhead allowance** (4480MiB/4992MiB). Memory profiles above3072 forbidden.
3. Start with -S; capture boot ID, PID, `/proc` start ticks, UUID and cgroup inode;
   require QMP paused/prelaunch state. Save the incarnation before isolation.
4. Replace IPv4/IPv6 proof filters under a whole-script flock. Existing DROP
   shield remains during each chain rebuild; rebind each recreated scope.
5. Start `talos-proof-guard.service`. `Type=notify` blocks until exact identity and
   the first safe sample ACK. Only then validate again and resume VM120.
6. Startup exceptions stop the captured process. The oneshot's ExecStopPost also
   handles wrapper SIGKILL/timeout, including the start-to-receipt gap. Its startup
   receipt is tied to systemd INVOCATION_ID so stale attempts cannot stop a later
   invocation. Successful startup marks that attempt complete.

## Supervision and exact-incarnation stop

Guard thresholds: MemAvailable<1536MiB; swap growth>65536KiB; three consecutive
5-second intervals with swap I/O; actual PSI total-delta rates full>=1% or some>=5%
sustained30seconds. Missed sample intervals>15seconds fail. No decaying PSI avg10
threshold. Guard checks identity on each iteration, not just startup. It exits
when its original process disappears. Flock rejects duplicate monitors; there is
no mutable background PID file. systemd MainPID is authoritative.

WatchdogSec15, startup timeout25, no restart; guard crash, SIGSTOP/watchdog,
startup failure and explicit service stop invoke ExecStopPost. Missing identity
or baseline prevents READY and invokes the same stop path. The stop path does
not depend on a healthy current configuration or baseline.

**Deliberate safety deviation from VMID-addressed `qm stop` retries:** cleanup
rechecks PID/start ticks/boot/UUID/executable, opens pidfd, rechecks, then signals
that pinned process (TERM, wait<=10seconds; KILL, wait<=5seconds). A delayed VMID
stop can otherwise kill a replacement VM120; pidfd cannot. Scope movement causes
the monitor to fail but does not prevent exact-process cleanup. Proxmox qmeventd
normally handles QEMU-exit cleanup; this must be verified in the live lease.
No signals are sent if the captured incarnation has gone. PID reuse and host
reboot receipts cannot authorize a different process. Existing guests are never
addressed. systemd TimeoutStop25 bounds StopPost execution.

The units have no [Install] and are never enabled. Host reboot does not autostart
VM120. Direct administrative `qm resume` remains a bypass; no existing Proxmox
unit/hook is modified. Do not claim protection against a root operator bypassing
the wrapper. Guest reboot normally retains the process/scope; host reboot remains
**untested and prohibited here** because it restarts production guests.

## Installation/activation: parent acknowledgement required

Do NOT run these during the platform owner's active lease. First obtain the
coordinator's checkpoint/outage/install approval and record before/after existing
guest PIDs/start times and resources. The following are commands for the approved
window, not a record that they have run:

1. Copy only reviewed infrastructure files to a private staging directory on
   Proxmox. Run `APPROVE_PROOF_SUPERVISOR_INSTALL=120 bash install-supervisor.sh`.
   It installs the two new proof-only units and code, daemon-reloads, and verifies
   them; it does not enable/start anything or kill the legacy guard. It refuses
   replacement while either new unit is active/deactivating.
2. From the private state directory:
   `python3 host_lifecycle.py enroll --approve-uuid 555e8603-58e6-4fb6-a190-378a3f11c257`.
   This writes an exact config/baseline receipt without starting the supervisor.
3. Under the explicit outage lease, save old scope identity:
   `APPROVE_PROOF_LIFECYCLE_TEST=555e8603-58e6-4fb6-a190-378a3f11c257 python3 lifecycle-proof.py checkpoint`.
4. Coordinator stops ONLY VM120 and verifies/stops ONLY the legacy guard PID.
   Do not replace the monitor live: this plan intentionally uses an outage to
   avoid overlapping ownership or unmonitored transition races. Confirm qmeventd
   removes the old scope/PID file. No other guest/unit is stopped.
5. If choosing approved3072MiB, coordinator changes ONLY proof memory after fresh
   post-stop measurements, and explicitly re-enrolls. Admission still must pass;
   approval is not permission to weaken the margin/overhead or change ARC/sysctls.
6. Run the harness `cold-start` action with the same explicit test approval. It
   invokes the supervised wrapper, verifies a new process/scope, checks exactly one
   scoped jump per family, and observes ordinary node packet-counter growth. No
   guest/pod exec, DNS/private-network probes or filter experiments are performed.
7. Check journal READY before resume, systemd MainPID, API readyz, host resources,
   original guest identities and qmeventd cleanup. Separately record guest resource
   measurements; do not infer resident headroom from configured allocations.
8. Only under continued outage lease, run `kill-guard`. Confirm original QEMU
   exited within45seconds and units report failure. Repeat a cold-start with a
   freshly captured pre-stop scope, then `hang-guard`. Capture sanitized harness
   JSON + selected supervisor events, not full journals/configs. Re-enrollment is
   required for any independently approved config change, not every cold start.
9. Missing-baseline/receipt startup rejection and wrapper death need owner-run
   injection cases too; offline mocks alone do not satisfy live acceptance.
   Back up root0600 receipts privately and restore them under the same lease.
10. Leave VM120 in the coordinator-approved final state, with supervised guard
    active if running. Recheck API, resources, existing guest identity and source
    Docker inventory via the appropriate owner.

`systemctl stop talos-proof-guard.service` is a **proof VM stop operation**, not a
harmless monitor restart. Never use it while a platform/application lease is active.
A failed cold-start admission leaves the VM stopped; do not bypass it with qm.

## Offline regression / outstanding proof

`PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-host_test.py` performs only
mocked lifecycle operations and private temporary-file tests. It covers unsafe
configuration/NIC/GPU/arguments, both RAM admissions, baseline thresholds, actual
PSI rates, missed samples, pidfd reuse recheck, bounded exact-process stop, guard
ACK suppression/duplicates, startup ordering/failure cleanup and stale invocation
receipts. Shell syntax/shellcheck are separate gates.

**Still unproved until the live lease:** systemd notify/watchdog behavior on this
host; actual crash/hang/startup-failure stop; QEMU-exit qmeventd cleanup; recreated
cgroup counter binding; cold-start healthy API; post-start resource margin under
platform load. IPv6, DNS-proxy and controlled reachable negative-destination tests
remain the platform owner's separate authorized network work. No reboot proof is
claimed and no network timeout is treated as isolation evidence.
