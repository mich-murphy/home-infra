# Isolated single-node Talos proof platform

## Scope and topology

This is a capacity-constrained functional proof, not a production migration. The
provisioning proposal is one new Talos VM120 with **2560MiB initial RAM**
(reduced from the earlier3GiB proposal by the host capacity guard),2vCPU and a new64GiB
data disk; no VM existed at this offline checkpoint. Planned networking is user-mode QEMU/slirp172.31.250.10/24, gateway172.31.250.2. API and Gateway
access use explicit SSH/QEMU proof-only forwards. No LAN bridge, production DNS,
production NAT rules, existing services, GPU assignment or production volumes change.
The process/cgroup-scoped VM egress deny must independently protect production private
ranges. The node provisioning worker owns validation of that boundary.

Kubernetes explicitly pins1.36.x rather than Talos1.14.5's newer default. Platform
pins Cilium1.20.4, whose documented tested matrix is1.33–1.36, and Gateway API1.6.1,
the documented pair (not latest1.7.0). Public artifacts have SHA256 locks; chart
rendering retains upstream digest-pinned Cilium/operator/Envoy images. Local-path
and helper images are explicitly digest-pinned. This avoids mutable `latest` and
blind adoption of a newer incompatible Kubernetes/CNI combination.

## Storage decision

| Choice | Real requirements and properties | Decision |
|---|---|---|
| Replicated OpenEBS Mayastor | Per io-engine node: two exclusive CPU cores,1GiB ordinary RAM plus at least2GiB hugepages (1024×2MiB), NVMe/TCP kernel support; control plane and other components consume additional memory. A single node cannot provide independent failure domains. | Reject: consumes essentially entire3GiB guest before Talos/Kubernetes/Cilium/apps. A one-replica setting would not fix resource requirements or create durability. |
| OpenEBS LocalPV Hostpath | Files/directories on a node-local filesystem, no replicated io-engine; can bind dedicated Talos user volume. The full OpenEBS umbrella chart introduces unnecessary optional components and values surface. | Viable lightweight storage model, but no need for umbrella release. |
| Rancher local-path-provisioner0.0.37 | One small controller, short-lived hostPath helper pods, WFFC/node affinity. No enforced PVC-size quota, no replication, no native snapshots or CSI expansion. | Selected minimal maintained local-path implementation; dedicated `/var/mnt/proof`, StorageClass `proof-local`, `Retain`, no destructive automated teardown. |

The disk must be positively identified and mounted before bootstrap; a directory on
Talos system disk is **not** equivalent. Installer requires human confirmation of
mount evidence, it cannot inspect Talos disks via Kubernetes alone. The helper independently checks
its actual mountinfo for the XFS `/dev/sdb1` filesystem root before creating a volume;
missing mount/OS-disk fallback fails closed. Proof workloads
must use fresh PVCs/synthetic fixtures only. No NFS, TrueNAS or production host mounts.
Pod restart persistence means reattaching the same local disk path on the same node;
it proves neither recovery after disk/VM loss nor replicated durability. Backup,
restore and node-reboot recovery remain separately unproven until exercised.

## Network and access

Per-app namespaces `proof-<service/trust-group>` carry namespace label
`app.kubernetes.io/part-of: talos-proof`. A Cilium clusterwide policy selects that
namespace label; both ingress and egress default deny. Only CoreDNS TCP/UDP53 is
allowed baseline egress. Hard `egressDeny` for `world`, `host`, `remote-node` and
`kube-apiserver` overrides additive allow policies: apps cannot contact production
LAN hosts, Internet, node APIs or arbitrary host services. These Cilium identities
avoid accidentally exempting production addresses via overly broad private CIDRs.
Only independently labelled proof pod endpoints may receive explicit dependency
permissions. App workers must grant both source egress and destination ingress.
Do not add CIDR/world/host exceptions for convenience.

Validation namespace has source egress to proof endpoints; destination app policies
must explicitly permit validation on intended ports. Gateway traffic arrives at backends
as Cilium's reserved `ingress` identity, which app policies must allow on frontend ports; a namespace
selector on `proof-gateway` alone would be incorrect for this datapath. GatewayClass
uses Cilium NodePort parameters, never LoadBalancer or L2 announcement. HTTP and TLS
listeners accept routes only from labelled proof namespaces under `*.proof.invalid`.
The synthetic wildcard self-signed cert is generated outside git with private temp
permissions; no cert-manager. Trust-verified curl uses exported public cert and
`--resolve`, not production DNS or `-k`. Unmatched-host negative proof is required.
Gateway listener ports80/443 map to generated NodePorts; use approved VM forwards.

These policies are not protection against privileged/host-network app pods, cluster
administrators or a compromised node. Enforce restricted PSA in app namespaces,
disable automatic SA tokens, and never place apps in privileged infrastructure
namespaces. Local-path infrastructure needs Kubernetes API and hostPath helper access;
it is a trusted exception outside proof-app selection (`part-of: talos-proof-infrastructure`),
with a separate default-deny policy allowing only API TCP443/6443 and CoreDNS TCP/UDP53,
not a production integration.

## Capacity budget and staged execution

At2560MiB initial guest RAM the fit is tighter still; no live fit is claimed.
Steady platform requests: Cilium256Mi/100m, operator64Mi/25m, Envoy64Mi/25m,
local-path32Mi/10m = **416Mi RAM and160m CPU**. Limits total992Mi. This excludes
Talos, etcd, API server, scheduler, controller manager, CoreDNS, kernel/BPF maps,
image unpacking and temporary helper pods. Requests/limits are a budget, **not live
footprint evidence**. Small BPF map limits are appropriate only for this proof.
No monitoring stack/metrics-server/Flux installed. Actual process/cgroup usage from
Talos must demonstrate headroom before running apps; start all app deployments at0
replicas and execute bounded service/trust-group batches. OOM/throttling is a failed
capacity result, not grounds to silently resize existing VMs.

## Delivery and acceptance

See `kubernetes/bootstrap/README.md` for guarded install, TLS generation, synthetic
fixtures, staged storage/network verification and Gateway tunnel verification.
Offline Helm and Kustomize renders passed. Authorized live checkpoint on Kubernetes
**1.36.5** now passed storage/policy/Gateway checks; see
`docs/evidence/talos-network-storage/live-summary.md` for actual observations,
failures corrected and bounded conclusions. Negative timeouts against synthetic
private/documentation addresses are not sufficient policy-drop evidence alone:
correlate Cilium drop verdicts. Pair denied cross-app access with positive validation
access to the same running backend. Record resource/mount evidence and all command
exit statuses under `docs/evidence/talos-network-storage/`. No secrets in evidence.
