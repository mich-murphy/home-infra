# Talos proof platform

## Current checkpoint — 2026-11-13 host mitigation completed; proof off

Explicitly approved production maintenance completed one host reboot onto
7.0.14-24-pve with`kho=off`. KHO output is absent and CmaTotal/CmaFree are0.
Production VM101/102 and all36original containers recovered; VM111/120 remain off.
Temporary Docker startup holds, VM102autostart and host backup-storage settings
were restored. Original guard limits, swap baseline, ARC and swappiness settings
were not changed. [Maintenance evidence](evidence/talos-acceptance/kho-maintenance-completed-f7a723ea8a0d4640a2e586022501ce5a.json)
preserves the delayed VM102 shutdown failure and other diagnostics.

The120-second host observation with proof off recorded swap0/no swap-page delta.
Kernel and boot parameter changed together: the KHO restriction is removed, but
sole historical cause, representative capacity and proof recovery are not proved.
No new proof startup/application authority follows. Earlier checkpoints below
remain historical, including the original guard stop.

## Current state — 2026-11-12: stopped by guard

At07:18:58UTC the resource guard reported `sustained host swap IO`; its stop
handler confirmed the original proof QEMU exited. A later parent admission GET
received a connection reset. Read-only host inspection found no VM120 PID file
and the guard failed with `exit-code`. No new diagnostic receipt or invocation
occurred; VM120 remains off. No restart, baseline reset or threshold change was
attempted. A new guarded-start window requires explicit authorization via the
[existing lifecycle procedure](talos-proof-host-lifecycle.md), with fresh unchanged
checks—not direct `qm start`.

The deployed lifecycle/guard/unit hashes match the frozen repository. Original
swap baseline24KiB is retained; historical28KiB differs from the later6328KiB
observation after the stop. That later host MemAvailable5390.094MiB is not startup
authority. Last logged successful guard sample was2595MiB available/swap4652KiB;
the guard's raw swap-page increments were not logged. The responsible workload,
post-stop guest API/storage integrity and recovery remain unestablished.
[Sanitized evidence](evidence/talos-acceptance/guard-stop-before-diagnostic-634f727438df495397f768820517280c.json)
preserves private capture hashes. The verified checkpoints below are historical.

### Read-only allocator investigation

The same boot has default-enabled KHO on kernel7.0.14-17-pve and2850MiB of
nonoverlapping movable-only scratch. CurrentCmaFree~1446MiB withCmaTotal0 matches
the mechanism documented by Proxmox. This is a confirmed allocation restriction
and credible contributor, **not proof of the exact swap-triggering allocation**.
Historical VM host-memory charges were stable; current swapped victims do not
identify the reclaim initiator. See [the investigation and proposed maintenance](talos-proof-host-memory-remediation.md).
The targeted `kho=off` boot mitigation requires explicit production-host maintenance
approval and verification; it has not been applied. VM120 stays off and root-cause
resolution is not claimed.

## Verified checkpoint — 2026-11-11

VM120 is a new, isolated proof guest. Authenticated Talos1.14.5, etcd, kubelet and
container runtime are running. Kubernetes **1.36.5** `/readyz` passed; the single
node `talos-proof` became **Ready** after Cilium installation. Its recorded node UID
is `4845bfd5-3bdb-453d-8503-83b43edb7a1e`, InternalIP `172.31.250.10`.
The dedicated64-GiB `/dev/sdb1` XFS volume is mounted at `/var/mnt/proof`.
These facts are not proof of application or production readiness.

Parent read-only measurements after CNI/local-path startup: guest total2384MiB,
used1343MiB, available813MiB; Proxmox available2476MiB, QEMU RSS2506MiB,
unchanged24KiB swap, sampled actual memory PSI0%. Initial allocation is2560MiB.
The first3072MiB admission was refused (4546MiB available versus4992 required).
After all app pods were stopped, a later fresh post-stop observation5168MiB passed
the unchanged requirement. Parent changed only VM120 to **3072MiB**, re-enrolled
its exact configuration while preserving the original swap baseline, and completed
one supervised cold start. Existing VM101/102 PID/startticks/config hashes were
unchanged. API/node, trusted Gateway TLS and the persisted platform nonce survived.
See [RAM admission evidence](evidence/talos-acceptance/ram-admission-3072.json).
No other guest or host tuning was performed or authorized.

At3072MiB, guest actual total is2823MiB. Talos available1403–1420MiB differs
materially from kubelet available642–706MiB because working-set accounting includes
active file cache. The Flux896MiB admission consequently **refused before apply**.
Do not substitute the optimistic metric for a gate defined against the other;
new application receipts use the conservative minimum. These are point observations,
not representative peak/soak or full-concurrency capacity acceptance.

**Safety correction verified:** the supervised replacement demonstrated actual
SIGKILL and watchdog-hang → exact proof QEMU termination, followed by guarded
recovery. Target checks pin endpoint/context/TLS/node identity; a follow-up closes
short kubectl flags and inherited Helm/proxy/preferences overrides with negative
mock-CLI tests. See the [host lifecycle runbook](talos-proof-host-lifecycle.md) and
[delivery record](talos-proof-delivery.md) for current leases and remaining gaps.

## Versions and experiments

- Talos/talosctl **1.14.5**; Kubernetes **1.36.5**; Cilium **1.20.4** and Gateway API
  **1.6.1**. Talos defaults to1.37, outside the selected Cilium tested matrix; an
  explicit Kubernetes pin is required.
- Installer:
  `factory.talos.dev/metal-installer/376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba:v1.14.5`.
  The initially attempted obsolete `ghcr.io/siderolabs/installer` tag returned404.
- Initial Kubernetes1.36.6 apiserver repeatedly exited139 with empty logs. Guest
  memory was ample and there was no OOM evidence. Changing VM CPU from host to
  `x86-64-v2-AES` alone did not fix it. Using1.36.5 plus an explicit proof-kubelet
  restart produced a working API; all components were then aligned to1.36.5.
  Both image binaries could run `--version`. This is a useful A/B result, **not a
  proven upstream1.36.6 defect**; static-pod reconciliation was also involved.
- Generated hostname defaults initially registered `talos-ate-q71`. Explicit
  `HostnameConfig hostname: talos-proof, auto: off` corrected the identity. After
  verifying both UIDs and absence of app volumes, parent removed only the obsolete
  proof-node registration. Stale mirror Pods were not evidence of duplicate live
  control-plane processes.
- Talos1.14 taint removal requires `$patch: delete`, **not null**. The source patch
  now removes the control-plane NoSchedule taint declaratively; live application
  of this patch succeeded without a reboot and local-path then scheduled.

Sources:
- <https://github.com/siderolabs/talos/releases/tag/v1.14.5>
- <https://docs.siderolabs.com/talos/v1.14/platform-specific-installations/virtualized-platforms/proxmox>
- <https://docs.siderolabs.com/talos/v1.14/getting-started/support-matrix>
- <https://docs.siderolabs.com/talos/v1.14/deploy-and-manage-workloads/workloads-on-controlplane>
- <https://docs.siderolabs.com/kubernetes-guides/cni/deploying-cilium>
- <https://docs.cilium.io/en/v1.20/network/kubernetes/compatibility/>

## Dedicated resources and isolation

VM120, SMBIOS UUID `555e8603-58e6-4fb6-a190-378a3f11c257`:2vCPU, fixed3072MiB now
(initially2560MiB),
32-GiB OS and64-GiB data disks on local-zfs, q35/OVMF, VirtIO SCSI, no GPU or bridged
NIC. VM101/102 resources are unchanged; VM111 remains stopped. There are no
production VLAN/DNS/NFS/router modifications. VM120 is not managed by production
Terraform or the historical Kubernetes cutover switch.

### Production backup membership safeguard

The existing `backup-truenas-daily` job runs at02:30 with `all=1`, targeting
`truenas-backups`. Creating VM120 would otherwise silently include the temporary
proof in production NAS backups. Parent made one narrowly scoped membership
change: exclusions `9001,9003` → `9001,9003,120`, via
`pvesh set /cluster/backup/backup-truenas-daily --exclude 9001,9003,120`.
Before/after API objects were compared: **only `exclude` changed, only VM120 was
removed from membership**, and every existing guest's schedule, membership,
retention, storage and other settings stayed unchanged. No backup was triggered.
See [the sanitized receipt](evidence/talos-acceptance/proof-backup-exclusion.json).

This is the explicit existing-job configuration exception for the newly created
proof, not a claim that no Proxmox setting changed. Do not restore an entire old
job object during cleanup: it could overwrite later legitimate edits. On proof
retirement, inspect the current job and remove only120 if appropriate. Reapplying
the production backup role may overwrite this temporary exclusion; verify it
before another overnight proof window. No production playbook was run here.

`create.sh` now requires the companion `backup-safety.py` **before VM creation**.
Stage both files together and execute the script by path, not by piping it to
`bash -s`. The read-only gate rejects enabled all-guests jobs without120 excluded,
explicit120 membership, ambiguous pool/tag selectors and unreadable/malformed
responses. It never changes a job. Check current membership from the workstation:

```sh
ssh root@proxmox 'pvesh get /cluster/backup --output-format json' | \
  python3 infrastructure/proxmox-proof/backup-safety.py
```

Only a safe summary is printed, not raw job/recipient data. An unsafe result
requires explicit review at https://proxmox:8006/#v1:0:=datacenter:backup ; preserve
all existing guests/settings while excluding the new proof. This is a creation
preflight, **not** continuous enforcement against later administrator/job changes.

QEMU slirp uses172.31.250.0/24, private DHCP node `.10`, gateway `.2`, IPv6 disabled.
No host bridge, LAN IP, DHCP reservation or global forwarding setting is needed.
The QEMU-cgroup OUTPUT filter blocks new private/CGNAT/loopback/link-local/reserved
connections, permits required public HTTP(S), DNS and time traffic, and permits
established replies to loopback host forwards. Filter refresh installs a temporary
scope DROP before replacing rules and rebinds the recreated cgroup. Serialized
refresh, crash/watchdog cleanup and new-scope public packet-counter growth were
verified. Comprehensive host DNS/IPv6/private-destination bypass coverage remains
unproved; ordinary counter growth does not by itself establish those denials.

This is **proof-only networking, not native production network parity**. `onboot=0`
and QEMU `-S` keep cold starts administratively paused until the guarded wrapper
resumes them. Direct `qm resume 120` bypasses that administrative boundary; do not
claim protection against an administrator deliberately bypassing the wrapper.
Host reboot is not tested because rebooting Proxmox would disrupt production.
A proof-VM cold restart and guard-failure injection can be tested independently.

Early `network-test.txt` demonstrates public HTTPS200 and failures contacting
private targets. Its `ISOLATION-PASS` line is an **unaccepted historical assertion**:
timeouts lack per-test counter attribution, IPv6 `::1` is guest-local, and the
slirp DNS proxy was not covered. Cumulative reject counters support filtering but
do not complete those gates.

A later [controlled actual-node TCP trial](evidence/talos-platform/controlled-host-isolation-node-live.md)
now proves a narrower result: the same owned private endpoint accepted both
outside-cgroup controls, accepted no node connection, and its exact adjacent
predicate and existing REJECT each increased by2. Canonical policy was unchanged
and instrumentation removed. The parent independently rehashed/reparsed the
private receipt. This is endpoint/cgroup attribution, **not** TRACE/full-five-tuple,
DNS/IPv6 or exhaustive bypass proof. The first loader failure and earlier resource
refusal remain recorded; the completed window grants no further host execution.

## Private tools, configuration and API access

Default private state: `$HOME/.local/state/home-infra/talos-proof`.
Tools are checksum-verified; generated configuration/keys remain outside Git,
directories0700 and files0600. Use the matching Talos client, not an older Nix one.

```sh
export STATE="$HOME/.local/state/home-infra/talos-proof"
export TALOSCONFIG="$STATE/config/talosconfig"
export KUBECONFIG="$STATE/config/kubeconfig"
"$STATE/bin/talosctl" version
kubectl --request-timeout=15s get --raw /readyz
kubectl get nodes -o wide
```

Talos endpoint `127.0.0.1:50120`, node `172.31.250.10`; Kubernetes server
`https://127.0.0.1:64120`. An explicit dedicated kubeconfig plus recorded node UID
must be checked before mutations; context-name agreement alone is insufficient.
Never dump the full credential-bearing kubeconfig or machine configuration.

The existing SSH control socket is `$STATE/ssh-control`. Check it before creating
another tunnel. Equivalent foreground management/Gateway forwards are:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:50120:127.0.0.1:50120 \
  -L 127.0.0.1:64120:127.0.0.1:64120 \
  -L 127.0.0.1:18080:127.0.0.1:18080 \
  -L 127.0.0.1:18443:127.0.0.1:18443 root@proxmox
```

Cilium assigned Gateway NodePorts **30659/30310**. Parent remapped proof-only QEMU
HTTP18080→30659 and HTTPS18443→30310 through QMP, then persisted only VM120's args,
without reboot. Management forwards were unchanged. A recreated Gateway can choose
other NodePorts: discover and update the mapping, never assume these numbers.
Public proof CA is `$STATE/config/proof-gateway-ca.crt`; private keys are not evidence.

## Fresh creation and validation

`create.sh` requires explicit approval, unused VM120 and sufficient measured host
headroom. Verify cluster-wide VMID uniqueness, port availability, ISO checksum and
only dedicated disks before creating. Use the guarded lifecycle wrapper; do not
run a production Terraform apply or modify any existing guest.

For static validation, generate into a **fresh** temporary private STATE; never
regenerate an active cluster identity merely to validate changes:

```sh
export STATE
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
bash infrastructure/proxmox-proof/bootstrap-tools.sh
bash talos/generate.sh
bash infrastructure/proxmox-proof/validate.sh
```

`talos/bootstrap.sh` is a first-bootstrap-only helper and refuses an existing
kubeconfig. Apply machine configuration to the new VM's maintenance endpoint,
wait for authenticated API, bootstrap etcd once, retrieve private kubeconfig and
use the tunnel URL. Static validation does not prove bootability; evidence above
records failures it could not detect.

## Remaining acceptance and teardown boundary

Before accepting platform proof: verify scoped host counter deltas/DNS/IPv6,
Cilium policy drop verdicts, actual NodePort trusted TLS, storage device identity,
clean restart with a new cgroup, supervised guard failure behavior, Talos health,
off-node etcd snapshot **and tested recovery**, and source no-touch comparison.
See [architecture](talos-proof-architecture.md) and [operations](talos-proof-operations.md).

No automatic destructive teardown is provided. Stop only the verified proof VM
through its lifecycle tooling. Deleting it requires rechecking VM120 UUID/disks and
accepting loss of proof data. Remove only its scoped firewall jumps/chains, private
unit/state/tunnel and dedicated ISO when explicitly retiring the proof. Never
flush a shared firewall table, remove shared storage, or touch source guests.
