# Coordinator platform acceptance checkpoint

2026-11-11 UTC, after host lifecycle worker's `82e20ee0` fault/recovery tests.
Platform source `a0e27380`, Talos bootstrap/taint correction `22b938b4`.
This accepts only the bounded platform behaviors below, **not application or
production migration readiness**.

## Reviewed worker evidence

- `../talos-network-storage/live-summary.md`: real NodePort HTTP and trusted TLS,
  negative routing/TLS, exact correlated Cilium BPF policy drops against a
  known-running fixture and blocked destination classes, XFS backing identity,
  nonce surviving pod UID replacement; platform fixture workloads stopped afterward.
- `../talos-platform/host-lifecycle-live.txt`: actual guard SIGKILL and watchdog
  hang cause exact-incarnation proof QEMU termination; cold restart succeeds with
  new cgroup bindings and active supervised guard. Source VM101/102 PID/starttime
  and configuration hashes remain unchanged. No host reboot performed.
- Parent reviewed the supervisor and start/guard unit source before granting the
  proof-only fault window. Platform target guard hard-pins endpoint, node UID/IP,
  context and verified TLS; storage helper rejects missing/wrong mount device.

## Independent checks after fault recovery

Using only the dedicated private Talos/Kubernetes credentials:

```sh
talosctl read /var/mnt/proof/pvc-12e57f52-b69a-4fb7-8f58-3452832a6cad_proof-network-test_fixture/www/index.html
kubectl --request-timeout=10s get nodes -o wide
ssh root@proxmox 'systemctl is-active talos-proof-guard.service; free -m'
```

Observed results:
- Exact expected persisted nonce: `synthetic-proof-20261111T124930Z`, matching the
  pre-fault fixture. This extends the pod-replacement observation to multiple
  proof-VM process stops/restarts without claiming disk-loss recovery.
- Sole node `talos-proof`: Ready, Kubernetes1.36.5, Talos1.14.5,
  InternalIP172.31.250.10; original UID preserved by separate lease admission check.
- Supervisor `active`.
- Host physical31834MiB; available2457MiB; rounded swap used0MiB (exact guard
  evidence reports24KiB unchanged). No proof-induced sustained pressure observed.
- VM remains2560MiB; 3072MiB was refused because fresh admission headroom failed.

## Accepted and unaccepted scope

**Accepted:** tested single-node control plane/CNI/Gateway path; explicit tested
pod policy denials; dedicated filesystem identity; synthetic persistence through
pod replacement and proof-VM faults; crash/hang supervision's tested fail-closed
paths; source-VM no-restart/config-hash comparison over that fault window.

**Not accepted:** application workflows, full concurrency, historical data restore,
production client/VLAN parity, host reboot behavior, every possible startup fault,
complete host DNS/IPv6 isolation coverage, disk-loss or etcd disaster recovery, HA,
long soak or production cutover. The earlier host timeout-only isolation transcript
remains weaker evidence and is not upgraded into an irrefutable isolation claim.

An exclusive CouchDB application lease was issued only after this host window was
released and the active supervisor/node identity were independently checked.
