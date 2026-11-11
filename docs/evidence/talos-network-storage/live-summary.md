# Authorized live platform checkpoint

Observed node/host clock: **2026-11-11 UTC** (timestamps in raw evidence). This is a
new isolated proof VM only, no production changes by this worker.

## Identity and bootstrap safety

Sole Kubernetes node `talos-proof`, UID `4845bfd5-3bdb-453d-8503-83b43edb7a1e`,
InternalIP172.31.250.10, Kubernetes1.36.5, Talos1.14.5; explicit API forwarded to
`https://127.0.0.1:64120`. `proof_guard.py` now hard-pins endpoint and recorded
name/UID/IP, requires CA trust/TLS, forces explicit verified context, forbids target
and TLS override flags, and runs before each wrapped kubectl operation and Helm.
Caller-supplied wrong configuration plus consistently wrong expected server cannot
pass. Six offline test methods cover valid target, consistently wrong config/server,
TLS skip, node UID/name/IP mismatch, multiple nodes and actual helper mount gate.
No kubeconfig, private key, tokens or Secret payload is stored in evidence.

Initial Helm installation exposed a CRD race: operator readiness precedes asynchronous
Cilium CRD creation. Installer now waits for required CRDs to exist and be Established,
then Cilium/Envoy rollouts before applying policies. Retried successfully. See
`install-live*.txt`; earlier failures are retained, not passed off as successful runs.

Control-plane taint blocked local-path scheduling. A guarded imperative taint removal
was briefly used before parent notified it was fixing Talos declaratively; that code
was removed. Parent owns the persistent Talos taint deletion. Current bootstrap does
not mutate node taints; fresh nodes must be schedulable by declarative machineconfig.

## Storage PASS (bounded meaning)

`verify-live-final.txt` records:
- DNS and permitted validation-client HTTP to synthetic fixture.
- Synthetic nonce written and synced to new `proof-local` PVC.
- Rollout restart changed pod UID from `8c5afe8f-4ea1-49e7-9373-f5360d574b76` to
  `283d878f-a94d-46a2-bd94-c60ca0332cb8`; new pod read exact persisted nonce
  `synthetic-proof-20261111T124930Z`.

`volume-mount-live.txt` proves fixture `/data` is XFS from `/dev/sdb1`, mounted from
`/pvc-12e57f52-b69a-4fb7-8f58-3452832a6cad_proof-network-test_fixture`; PV path is
under `/var/mnt/proof`, node affinity is `talos-proof`, requested capacity64Mi.
The helper itself independently verified dedicated XFS `/dev/sdb1` root mount before
mkdir. Offline absent/wrong-device/subdirectory-bind tests fail closed.

This is **same-node pod restart persistence**, not VM/disk-loss recovery, backup
restore, replicated durability, enforced capacity quotas or HA. Dedicated64GiB disk,
Retain policy, fresh synthetic fixtures only; no production NFS/data.

## Network policy PASS with observed BPF verdicts

`policy-drops-live.txt` records exact producers and paired positive/negative tests:
validation client10.244.1.90 successfully read the known-running backend10.244.1.237:8080.
Denied client10.244.1.147 in a different trust namespace generated these captured
Cilium BPF events, correlated separately for each request:
- Known-live backend10.244.1.237:8080: `Policy denied`.
- Synthetic private192.168.254.254:8080: `Policy denied by denylist`, identity world.
- Documentation-world198.51.100.1:8080: `Policy denied by denylist`, identity world.
- Own proof node172.31.250.10:6443: `Policy denied by denylist`, identity host.

No real production endpoint was contacted. These are observed kernel policy drops,
not inferences from an unreachable-address timeout. Default egress and ingress deny,
hard world/host/API denies, explicit frontend-port app policies, and a separately
scoped trusted storage-controller API/DNS policy are active. Infrastructure namespaces
are not selected by the app boundary. This does not sandbox privileged/host-network
workloads; restricted app admission and the host owner's independent VM-network
guard are still essential. Host private-LAN guard evidence is owned elsewhere.

## Gateway PASS through real NodePort datapath

Parent remapped ONLY VM120 QEMU forwards: localhost18080→node30659,
localhost18443→node30310. No Kubernetes Service port-forward substitute was used.
`gateway-status-live.yaml` and `route-status-live.yaml` record Accepted/Programmed/
ResolvedRefs conditions; `gateway-live.txt` has TLS1.3 handshake and verified SAN.
`gateway-assertions-live.txt` final assertions all passed:
- HTTP200 with persisted nonce through localhost18080.
- HTTPS200 with same nonce through localhost18443, explicit synthetic CA trust,
  hostname `fixture.proof.invalid`; no `-k`.
- Unmatched `unmatched.proof.invalid`: HTTP404 and trusted HTTPS404.
- Without synthetic CA: curl exit60 (untrusted issuer).
- Outside listener SNI `outside.invalid`: curl exit35 (handshake refused before
  certificate validation), **not** falsely described as certificate-name verification.

A rerun immediately after fixture recreation initially returned503 while backend
programming converged. Positive Gateway requests now allow bounded warmup; final
full assertion run passed. A pod Ready event alone is not instantaneous Gateway
readiness, and no zero-interruption availability claim is made.

Public CA remains local at
`/Users/mm/.local/state/home-infra/talos-proof/config/proof-gateway-ca.crt`.
Private key remains only Kubernetes Secret; certificate is synthetic,7-day lifetime.

## Measured footprint, not just requests

`guest-footprint-live.json` is a kubelet stats/summary snapshot after all fixture
pods were scaled0 and deleted. Platform working set **448151552 bytes =427.4MiB**:
Cilium326.7MiB, operator55.8MiB, Envoy21.8MiB, local-path23.0MiB. Earlier active-test
snapshot was~307MiB combined; memory varies with cache/activity, so do not treat the
smaller sample as a fixed footprint. All remaining platform/control-plane pods had
zero restarts at this checkpoint; Cilium status OK.

Guest node working set1611MiB, kubelet-estimated available773MiB, PSI avg10/60/300=0.
Talos independent memory report:2384MiB total,1342MiB used,814MiB available.
Samples differ in time/accounting. VM configured2560MiB, not increased by this worker.

`host-footprint-live.txt`: host available2471MiB, swap used24KiB, PSI averages0,
ZFS ARC size3014875344bytes (~2875MiB), target/max3GiB. This is a point-in-time
observation, **not approval or evidence that3–3.5GiB guest RAM or concurrent heavy
app replicas are safe**. Parent's capacity guard owns such decisions. No existing
VM resources or host cache settings changed by this worker.

## Handoff state and remaining limits

All three fixture Deployments are replicas0; reusable fixture PVC and test manifests
remain, validation client deployment remains reusable at0. No application manifests
were deployed. Platform itself remains healthy for parent integration. No monitoring
stack installed. No node-reboot, disk-loss, backup restore, multi-node durability,
production DNS/routing parity or app migration-readiness claim is made.
