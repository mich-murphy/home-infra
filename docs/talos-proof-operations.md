# Bounded operational replacements (VM120 only)

## Status and design

**Offline staged; live gates NOT executed. No lease or kubeconfig received.** This is not production readiness, HA, production-data recovery, or a deployed monitoring service. VM120 starts at **2560 MiB**, not inventory's superseded 3-GiB planning value. Parent must grant an exclusive resource lease for each run; no concurrent app batches. Production source/host configuration and services are untouched.

| Existing capability | Minimal replacement | Current evidence / limits |
|---|---|---|
| Portainer declarative stacks | Flux 2.10.0 source + kustomize controllers only, immutable Git commit, harmless ConfigMap fixtures | Render-only; controller admission conditional on real baseline + >=20–25% memory headroom. No Helm/image/notification controller or app-root reconciliation |
| Beszel observations | External API reader: kubelet summary node/pod/container memory, node filesystem, PVC stats when reported, node capacity/allocatable, pod restart counters | Script + offline tests; no resident metrics workload. Bounded point samples, not historical peaks, dashboard, SLOs or enterprise stack |
| Beszel alerts | Real low-headroom and observed-restart rules; explicitly synthetic delivery-test event to an HTTP loopback-only sink on operator workstation | Receipt confirms HTTP delivery, not external paging. No SMTP/webhook/cloud credentials, no production integrations |
| Off-node recovery | Static file on dedicated source PVC → tar on workstation → different empty PVC; checksum checked after source pod deletion | Offline only. Not a live database backup, platform fixture restart test, or application restore |
| Talos control-plane recovery | Private off-node `talosctl etcd snapshot` plus checksum metadata | Snapshot capture staged; destructive etcd recovery NOT authorized or tested |

Whole inventory: media worker owns kometa, lidarr, radarr, tautulli, sabnzbd, sonarr, seerr, jellyfin, jellyplex-watched, plex, qbittorrent, prowlarr, audiobookshelf, recyclarr, pinchflat, qbitwebui (16). Data worker owns nextcloud-cron, nextcloud, miniflux, immich, immich-ml, nextcloud-office, nextcloud-redis, wallabag-redis, nextcloud-postgres, miniflux-db, couchdb, wallabag, wallabag-mariadb, pocket-id, immich-redis, immich-postgres (16). Infrastructure: traefik → platform Gateway/TLS; portainer → fixture-scoped Flux; beszel → this observation/alert proof; docker-socket-proxy → **omit**, Kubernetes API/RBAC replaces discovery, never mount Docker socket. These map all **36 live containers**. Ownership is capability mapping, not a passing status; detailed functional acceptance remains in inventory and respective worker reports. Generic file restore here does not satisfy each application's logical restore gate.

## Source pins / offline reproduction

- Flux release compatibility explicitly supports K8s 1.36 >=1.36.1; proof 1.36.6 fits. Source: <https://github.com/fluxcd/flux2/releases/tag/v2.10.0>.
- `kubernetes/operations/gitops/artifacts.lock.json` pins upstream install YAML SHA256 and registry manifest digests for source-controller and kustomize-controller v1.10.1. Release metadata fetched from GitHub API; image index digests queried from authenticated-anonymous GHCR manifest responses. The release YAML is downloaded/verified at render time, not a floating `kubectl apply URL`.
- Recovery BusyBox1.37.0 index digest matches the platform's verified pin. No new utility image.
- Python3 stdlib for live operations; PyYAML required for render/offline tests (use repository environment).

```sh
cd /Users/mm/dev/home-infra-talos-proof
python3 tests/talos-proof-operations_test.py
kubectl kustomize kubernetes/operations/recovery > /tmp/operations-recovery.yaml
# Render only, after parent pushes fixture commit; requires network for pinned manifest:
python3 scripts/talos-proof-operations-flux.py --revision COMMITTED_40_HEX_SHA \
  > /tmp/operations-flux.yaml
# Or add --install-yaml /private/cached/install.yaml (same checksum enforced).
```

No operations manifests are included in the app root. Applying the app autozero root therefore cannot reset fixture reconciliation or start operations workloads inadvertently. Controllers watch only `proof-operations-system`; their namespaced control Role does not grant workload mutation. Impersonated `fixture-reconciler` has ConfigMap-only rights in `proof-operations-gitops`, no Secrets/Pods/Deployments/namespace writes. No upstream cluster-admin binding is retained. CRD installation is an explicit parent-admin action. Fixture resources have no workload, tokens or production data. Before live Flux use verify controller version flags and effective RBAC; a denied API or unexpected privilege is a blocker, not justification to grant cluster-admin.

System namespace is deliberately **not** labeled `part-of: talos-proof` (uses `talos-proof-operations`) to avoid colliding with app blanket API denies. Explicit Cilium allowlists permit API TCP443/6443, CoreDNS, same-system peers. Only source-controller additionally permits github.com TCP443 via DNS-aware policy, with no wildcard Internet/LAN/host allow. Node-boundary isolation remains parent/platform owned: if GitHub is denied there, leave GitOps blocked; do not weaken host controls. The Git URL is public HTTPS with no credential. Private-repo credentials are not provisioned by this proof. DNS visibility is not permission to contact other endpoints. Ordinary recovery pods use `part-of: talos-proof`, no token, restricted security context and deny-all ingress/egress.

## Live commands — only after explicit parent lease

Keep private state 0700, files 0600. Never print Talos config, kubeconfig, snapshots, raw API objects, secret values or archive bytes. Scripts use restrictive umask and withhold failed subprocess output. Evidence destinations are private timestamped directories under `~/.local/state/home-infra/talos-proof/operations/`. Evidence JSON still needs operator review before publication. The API collector needs pod/node read plus **nodes/proxy GET**; this is a powerful kubelet proxy privilege, unsuitable for ordinary app identities. It runs off-node using the explicitly supplied proof-admin credential, never gives a pod that credential, and never runs against source host. Production should replace proxy permission with a least-privilege supported metrics pipeline.

```sh
# Parent supplies exact private filenames; do not guess an ambient current context.
export KUBECONFIG="$HOME/.local/state/home-infra/talos-proof/kubeconfig"
export TALOSCONFIG="$HOME/.local/state/home-infra/talos-proof/talosconfig"
export TALOS_PROOF_OPERATIONS_LEASE=vm120  # ONLY after parent's explicit exclusive grant
python3 scripts/talos-proof-operations.py monitor --test-alert
# Repeat monitor before/during/after an approved workload, not continuous in background.
# default threshold512Mi (~20% of2560Mi); request640Mi for25% headroom:
python3 scripts/talos-proof-operations.py monitor --minimum-available-mib 640
python3 scripts/talos-proof-operations.py recovery
python3 scripts/talos-proof-operations.py snapshot --node APPROVED_PROOF_TALOS_ENDPOINT
unset TALOS_PROOF_OPERATIONS_LEASE
```

Collector exports actual kubelet timestamps/workingSetBytes/availableBytes rather than substituting requests/limits. Node capacity includes storage/ephemeral-storage where API reports it. Filesystem and volume stats are actual reported values, not claims that unreported local-volume metrics exist. `ContainerRestartObserved` is an absolute nonzero counter, **not** a new-restart rate. Short-lived jobs or sampling gaps may be missed. No metrics/alerts persist inside the node: JSON history and HTTP receipts persist off-node only; deletion/retention is operator-managed. Injected `ProofDeliveryTest` is marked synthetic and cannot prove resource-exhaustion detection. Low-memory rule is offline-tested with representative measured-shaped data; live low-memory triggering must not intentionally OOM the 2.5-GiB node.

Recovery refuses nonempty source or destination directories and distinct-PV check is mandatory. It does not erase existing data on rerun. Dedicated PVCs remain retained; source pod is deleted before restore and restored pod is left for inspection. `fixture.tar` and `etcd.snapshot` are **off the VM**, on the workstation, never on production NFS. The snapshot includes cluster secrets: never copy it to Git or `/tmp`, publish only reviewed size/checksum metadata. Snapshot checksum shows transport integrity, not successful etcd recovery. Talos machine secrets/config and the correct Talos/Kubernetes versions are separately necessary for disaster recovery. Future authorized etcd restore must use a separate disposable control plane and validate API objects; never run bootstrap `--recover-from` on this proof/source as an incidental test.

For repeated fresh file-recovery runs, parent must authorize disposal/recreation of only the recovery namespace/PVCs and platform-approved handling of Retain PV directories. Namespace deletion alone does not reclaim retained backing directories; no broad `/var/mnt/proof` wipe command is provided. Do not duplicate or mutate `kubernetes/platform/validation` persistence fixtures.

## GitOps live acceptance (separate conditional lease)

Do not install just because limits sum to384Mi: take real baseline and reserve >=512–640Mi node available through reconciliation; stop on memory pressure/OOM/restart. Install is staged separately from app batches and can be removed before them. Parent must approve any GitHub access through fail-closed node boundary, push exact code SHA, and confirm repository is publicly readable.

```sh
# With approved proof kubeconfig and explicit lease; render at real pushed commit first.
kubectl apply --server-side -f /tmp/operations-flux.yaml
kubectl -n proof-operations-system rollout status deployment/source-controller --timeout=180s
kubectl -n proof-operations-system rollout status deployment/kustomize-controller --timeout=180s
kubectl -n proof-operations-system wait --for=condition=Ready gitrepository/proof-fixture --timeout=180s
kubectl -n proof-operations-system wait --for=condition=Ready kustomization/proof-fixture --timeout=180s
kubectl -n proof-operations-gitops wait --for=jsonpath='{.data.revision}'=1 configmap/reconciliation-fixture --timeout=90s
# Deliberate harmless drift; controller must restore desired Git state without manual apply.
kubectl -n proof-operations-gitops patch configmap reconciliation-fixture --type=merge -p '{"data":{"revision":"drift"}}'
kubectl -n proof-operations-gitops wait --for=jsonpath='{.data.revision}'=1 configmap/reconciliation-fixture --timeout=90s
# Declarative version change, then rollback to original immutable-source fixture path.
kubectl -n proof-operations-system patch kustomization proof-fixture --type=merge -p '{"spec":{"path":"./kubernetes/operations/gitops/fixture-v2"}}'
kubectl -n proof-operations-gitops wait --for=jsonpath='{.data.revision}'=2 configmap/reconciliation-fixture --timeout=90s
kubectl -n proof-operations-system patch kustomization proof-fixture --type=merge -p '{"spec":{"path":"./kubernetes/operations/gitops/fixture-v1"}}'
kubectl -n proof-operations-gitops wait --for=jsonpath='{.data.revision}'=1 configmap/reconciliation-fixture --timeout=90s
# Explicit negative privilege proof (must print no):
kubectl auth can-i create deployments -n proof-operations-gitops --as=system:serviceaccount:proof-operations-system:fixture-reconciler
kubectl auth can-i get secrets -n proof-operations-gitops --as=system:serviceaccount:proof-operations-system:fixture-reconciler
```

Record UTC start/end, source `.status.artifact.revision`, Kustomization `.status.lastAppliedRevision`, ConfigMap values before/after each transition, controller imageIDs/restarts and monitor samples. Rollback above is an actual desired-state path rollback between two checked-in ConfigMap revisions, **not** a claim of Git history revert/app rollback. Both are pinned to the same Git commit, with zero app writes. A full Git commit-revert release workflow remains a separate production gap. Never save full Deployment/Secret API dumps as public evidence.

After approval to release controller memory: suspend fixture Kustomization, delete only source/kustomize Deployments in `proof-operations-system`; do not delete cluster CRDs as app-batch cleanup. Retain small fixture/CRDs or explicitly uninstall owned resources later. Observe memory recovery and return lease to parent. Controller replicas/default resource limits are experimental bounded ceilings, not evidence that startup or large production repositories fit.

## Production gaps / truthful acceptance

- No app-data copies, no database-consistency claim. Each app owner must perform app-aware logical backup/clean restore; this proof's tiny static archive is only the storage transport capability.
- No etcd restore until an independent approved disposable recovery target exists. No single-node/local-PV HA, replication, encrypted remote retention service, automated backup schedule, restore RTO/RPO or offsite durability claim.
- No production dashboards/long-retention metrics, scheduled external collector, event log/audit retention, persistent alert queue, pager delivery/acknowledgement, Prometheus rules or enterprise observability stack.
- No broad auto-reconciliation of apps until safe per-app desired state replaces zero-replica batch control, credentials are separately managed and capacity supports it. Fixture scope intentionally prevents autozero interference.
- The full36-container simultaneous acceptance gate is capacity-blocked; these staged capabilities do not remove that limitation.
