# Bounded operational replacements (VM120 only)

## Status and design

**Bounded live capability acceptance, 2026-11-11: monitoring/HTTP alert delivery, off-node clean-PVC file recovery, private etcd snapshot capture and subsequently authorized Flux reconciliation/drift/path rollback/negative RBAC passed. The original Flux admission refusal remains valid historical evidence; a new exclusive lease and genuinely higher measured headroom enabled the later run. All operations leases released; zero active operations workloads.** This is not production readiness, HA, production-data recovery, or a deployed monitoring service. Coordinator performed a separately approved supervised cold start at **3072 MiB** before this lease; the earlier 2560-MiB profile and refused bump are historical evidence, not altered here. Parent must grant an exclusive resource lease for each run; no concurrent app batches. Production source/host configuration and services are untouched.

| Existing capability | Minimal replacement | Current evidence / limits |
|---|---|---|
| Portainer declarative stacks | Flux 2.10.0 source + kustomize controllers only, immutable Git commit, harmless ConfigMap fixtures | Later exclusive live run passed: immutable source, ConfigMap drift repair, fixture path1→2→1, negative RBAC; controllers removed. Historical642.2MiB admission refusal retained. No Helm/image/notification controller or app-root reconciliation |
| Beszel observations | External API reader: kubelet summary node/pod/container memory, node filesystem, PVC stats when reported, node capacity/allocatable, pod restart counters | Live kubelet summary observations passed; no resident metrics workload. Bounded point samples, not historical peaks, dashboard, SLOs or enterprise stack |
| Beszel alerts | Real low-headroom and observed-restart rules; explicitly synthetic delivery-test event to an HTTP loopback-only sink on operator workstation | Receipt confirms HTTP delivery, not external paging. No SMTP/webhook/cloud credentials, no production integrations |
| Off-node recovery | Static file on dedicated source PVC → tar on workstation → different empty PVC; checksum checked after source pod deletion | Live off-node archive and distinct empty-PVC checksum restore passed. Not a live database backup, platform fixture restart test, or application restore |
| Talos control-plane recovery | Private off-node `talosctl etcd snapshot` plus checksum metadata | Private off-node capture passed (12,443,680 bytes); destructive etcd recovery NOT authorized or tested |

Whole inventory: media worker owns kometa, lidarr, radarr, tautulli, sabnzbd, sonarr, seerr, jellyfin, jellyplex-watched, plex, qbittorrent, prowlarr, audiobookshelf, recyclarr, pinchflat, qbitwebui (16). Data worker owns nextcloud-cron, nextcloud, miniflux, immich, immich-ml, nextcloud-office, nextcloud-redis, wallabag-redis, nextcloud-postgres, miniflux-db, couchdb, wallabag, wallabag-mariadb, pocket-id, immich-redis, immich-postgres (16). Infrastructure: traefik → platform Gateway/TLS; portainer → fixture-scoped Flux; beszel → this observation/alert proof; docker-socket-proxy → **omit**, Kubernetes API/RBAC replaces discovery, never mount Docker socket. These map all **36 live containers**. Ownership is capability mapping, not a passing status; detailed functional acceptance remains in inventory and respective worker reports. Generic file restore here does not satisfy each application's logical restore gate.

## Source pins / offline reproduction

- Flux release compatibility explicitly supports K8s 1.36 >=1.36.1; proof 1.36.5 fits. Source: <https://github.com/fluxcd/flux2/releases/tag/v2.10.0>.
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
# Parent supplies private mode0600 configs and a short-lived JSON resource receipt.
export KUBECONFIG="$HOME/.local/state/home-infra/talos-proof/config/kubeconfig"
export TALOSCONFIG="$HOME/.local/state/home-infra/talos-proof/config/talosconfig"
export TALOS_PROOF_OPERATIONS_LEASE="$HOME/.local/state/home-infra/talos-proof/leases/operations.json"
python3 scripts/talos-proof-operations.py monitor --test-alert
# Repeat before/during/after approved work, not continuously in background.
python3 scripts/talos-proof-operations.py monitor --minimum-available-mib 640
python3 scripts/talos-proof-operations.py recovery
python3 scripts/talos-proof-operations.py snapshot
unset TALOS_PROOF_OPERATIONS_LEASE
```

The receipt is coordinator-issued, **not** the former `vm120` environment marker. Its JSON schema is
`{group, context, endpoint, node_uid, expires, available_mib, measured_at}`; group must be
`operations` for collector/recovery/snapshot or `operations-flux` for Flux. Times are UTC Unix
seconds; expiry must be future and the guest available-memory measurement at most120s old
(not host available RAM). The coordinator may explicitly delegate refreshing **only** available_mib/measured_at from verified actual Talos memory before commands; group/expiry/identity remain coordinator-owned. This live lease delegated those two fields to the operations worker. Talos MemAvailable and kubelet availableBytes are different measurements; the Flux gate still uses kubelet stats and cannot substitute the larger Talos value.
All private directories under the proof state root are owner-only0700, regular files0600;
symlinks in the original path or any ancestor are rejected **before** resolve/open.

Every Kubernetes command, including **every exec, wait, mutation and failure cleanup**,
revalidates the receipt and active kubeconfig context→cluster/user mapping. It requires exactly
`https://127.0.0.1:64120`, TLS verification enabled, no proxy/TLS-name override or credential
exec/auth-provider, exactly one node named and hostname-labelled `talos-proof`, only InternalIP
`172.31.250.10`, and recorded UID `4845bfd5-3bdb-453d-8503-83b43edb7a1e` in both receipt and API.
Matching but wrong context/server/receipt combinations cannot authorize production. Actual
commands explicitly pin kubeconfig/context/server. Referenced credential files receive the
same private-path checks. This is an accidental-target guard, not protection against a malicious
local same-UID process racing filesystem writes. A node recreation requires explicit reviewed
identity re-enrollment, never automatic UID adoption.

Snapshot has **no caller-selected target or PATH binary**: only
`~/.local/state/home-infra/talos-proof/bin/talosctl`, version exactly `v1.14.5`, fixed endpoint
`127.0.0.1:50120` and node `172.31.250.10`; active private Talos config must agree. TLS remains
on; no insecure flags. The version check is not a substitute for parent verification of the
installed official binary provenance. Snapshot output never overwrites a prior artifact.

Collector exports actual kubelet timestamps/workingSetBytes/availableBytes rather than substituting requests/limits. Node capacity includes storage/ephemeral-storage where API reports it. Filesystem and volume stats are actual reported values, not claims that unreported local-volume metrics exist. `ContainerRestartObserved` is an absolute nonzero counter, **not** a new-restart rate. Short-lived jobs or sampling gaps may be missed. No metrics/alerts persist inside the node: JSON history and HTTP receipts persist off-node only; deletion/retention is operator-managed. Injected `ProofDeliveryTest` is marked synthetic and cannot prove resource-exhaustion detection. Low-memory rule is offline-tested with representative measured-shaped data; live low-memory triggering must not intentionally OOM the node.

Recovery refuses nonempty source or destination directories and distinct-PV check is mandatory. It does not erase existing data on rerun. An existing recovery namespace is rejected before apply; reruns require separately approved disposal. Both PVC UIDs and PV names must differ, each PV must bind its exact claim UID and use Retain. Dedicated PVCs/PVs remain retained; source pod is deleted before restore, and both pods are removed in guarded finally cleanup on success/failure to release memory. No PVC/PV or data deletion is automated. Source writes use shell noclobber, archives exclusive-create and tar extraction keep-old-files; destination emptiness is rechecked immediately before extraction. `fixture.tar` and `etcd.snapshot` are **off the VM**, on the workstation, never on production NFS. The snapshot includes cluster secrets: never copy it to Git or `/tmp`, publish only reviewed size/checksum metadata. Snapshot checksum shows transport integrity, not successful etcd recovery. Talos machine secrets/config and the correct Talos/Kubernetes versions are separately necessary for disaster recovery. Future authorized etcd restore must use a separate disposable control plane and validate API objects; never run bootstrap `--recover-from` on this proof/source as an incidental test.

For repeated fresh file-recovery runs, parent must authorize disposal/recreation of only the recovery namespace/PVCs and platform-approved handling of Retain PV directories. Namespace deletion alone does not reclaim retained backing directories; no broad `/var/mnt/proof` wipe command is provided. Do not duplicate or mutate `kubernetes/platform/validation` persistence fixtures.

## GitOps live acceptance (separate conditional lease)

Do not install just because limits sum to384Mi: take real baseline and reserve >=512–640Mi node available through reconciliation; stop on memory pressure/OOM/restart. Install is staged separately from app batches and can be removed before them. Parent must approve any GitHub access through fail-closed node boundary, push exact code SHA, and confirm repository is publicly readable.

```sh
# Same exact-target receipt mechanism, but parent must issue group=operations-flux.
# Render remains offline/nonmutating; run verifies upstream checksum in memory and
# applies only the generated scoped manifest, not arbitrary caller-selected YAML.
python3 scripts/talos-proof-operations-flux.py --action run \
  --revision 5d9a9926106f76346950af20e8afc0ef346ac548
# On an expired lease, request refreshed receipt before explicit guarded cleanup:
python3 scripts/talos-proof-operations-flux.py --action cleanup
```

Do not use unguarded `kubectl apply/patch/exec` commands from an ambient context. The guarded
run requires actual kubelet available memory >=896Mi (384Mi controller ceilings +512Mi reserve),
rejects other active app batches, installs generated controllers, waits for initial fixture1,
patches harmless ConfigMap drift and verifies repair, changes desired fixture path to2 and
rolls back to1, then proves fixture identity cannot create Deployments or read Secrets.
The run always attempts guarded controller cleanup, including on failure. A partial apply
still attempts Deployment deletion even if suspension fails. Cleanup never removes shared
CRDs/namespaces or storage. If identity or lease changes it fails closed rather than targeting
an unverified cluster; parent must renew the receipt to release proof memory. This is not a
substitute for the independent host resource guard.

Record UTC start/end, source `.status.artifact.revision`, Kustomization `.status.lastAppliedRevision`, ConfigMap values before/after each transition, controller imageIDs/restarts and monitor samples. Rollback above is an actual desired-state path rollback between two checked-in ConfigMap revisions, **not** a claim of Git history revert/app rollback. Both are pinned to the same Git commit, with zero app writes. A full Git commit-revert release workflow remains a separate production gap. Never save full Deployment/Secret API dumps as public evidence.

Guarded run cleanup suspends fixture Kustomization and deletes only source/kustomize Deployments in `proof-operations-system`; do not delete cluster CRDs as app-batch cleanup. Retain small fixture/CRDs or explicitly uninstall owned resources later. Observe memory recovery and return lease to parent. Controller replicas/default resource limits are experimental bounded ceilings, not evidence that startup or large production repositories fit.

## Live result, 2026-11-11 14:13–14:17 UTC

[Sanitized receipts and execution notes](evidence/talos-operations/README.md).

- Initial collector read real node/pod/container/filesystem stats, delivered existing absolute restart-count observations and a clearly synthetic `ProofDeliveryTest` to the workstation HTTP loopback sink. A later actual below896MiB measurement delivered `NodeMemoryHeadroomLow`; this is a headroom alert, **not an OOM test**. No restart-counter increase was observed between the two point samples.
- Recovery created two fresh PVCs/PVs, checked both directories empty, wrote only a synthetic file, saved an exclusive-create tar off-node, deleted the source pod, rechecked destination emptiness, extracted without overwrite, and matched content SHA256. Both pods deleted; both claims remain Bound with Retain PVs. This does not establish app-aware backup or restore.
- Flux refused twice before apply. First available node sample was710MiB; the persisted second refusal measured642.2MiB, below896MiB (384MiB controller ceilings +512MiB reserve). Talos reported1421MiB MemAvailable at the earlier observation; those are not interchangeable metrics. No controller startup, runtime imageIDs/restarts, reconciliation, drift repair, path change/rollback, negative RBAC or Flux sentinel claim is made. No policy/RBAC/flag changes were exercised live.
- Private etcd snapshot capture passed after the Flux refusal, without a Flux sentinel; metadata only is published. No etcd engine restore, bootstrap recovery, control-plane reset or VM121 was attempted.
- Talos client/server1.14.5, Kubernetes1.36.5, containerd2.3.7, kernel6.18.58-talos. Recovery used the pinned BusyBox1.37.0 declaration; its actual runtime imageID/restart count was not captured before deletion, so no retrospective runtime identity claim is made. Future recovery runs now capture these fields.
- Final guarded audit: node same enrolled UID, no active proof app pods, no operations Deployments. Leases released by archiving unchanged receipts and removing the active receipt paths. No host change, VM restart, source operation or retained-data deletion was performed. Host/source postflight remains coordinator-owned.

## Flux follow-up live result, 2026-11-11 15:06–15:08 UTC

A newly coordinator-issued exclusive `operations-flux` lease authorized a retry after ordinary prior media activity changed cache accounting. No cache dropping, pressure injection, host/VM tuning, resource-limit reduction, network widening, flag change or RBAC change was used. The896MiB admission gate and512MiB observed reserve were unchanged. Parent continued to own the supervised host guard, backup exclusion and admission decisions; this worker did not touch them.

- First new attempt admitted at1394.6MiB kubelet available, but `apply` failed and cleanup suspension also failed; Deployment deletion was still attempted by `finally`. Error output was withheld and not retained, so the exact cause is **unknown**, not claimed to be a diagnosed CRD/flag/RBAC issue. No configuration was changed before retry. This failed attempt is preserved in `flux-initial-apply-failure.json`.
- Successful retry admitted at1184.4MiB. Live reconciliation ran15:06:54–15:07:52UTC against public immutable commit `5d9a9926106f76346950af20e8afc0ef346ac548`. Source artifact and Kustomization applied revision both equal `sha1:5d9a9926106f76346950af20e8afc0ef346ac548`.
- Actual ConfigMap revision sequence: **1 → drift → 1 → 2 → 1**. The first1 after drift was controller repair;2→1 was desired fixture-path rollback at the same commit, not a Git commit revert or app rollback.
- Impersonated `fixture-reconciler` was denied `create deployments` and `get secrets` in the fixture namespace. No cluster-admin binding was introduced. Existing GitHub-only source egress was sufficient; no policy changes were needed.
- Flux2.10.0 release pins source-controller and kustomize-controller1.10.1. Actual runtime imageIDs matched the pinned manifest digests in `artifacts.lock.json`; both restart counters remained0 across all four post-start transition samples. Node reports Talos1.14.5, Kubernetes1.36.5, containerd2.3.7 and kernel6.18.58-talos.
- Recorded transition samples had minimum kubelet available **930.3MiB**, with MemoryPressure=False. The private runner also refreshed only lease memory/time before each guarded command using **min(kubelet availableBytes,Talos MemAvailable)** and stopped below512MiB. Samples are point observations, not proof of an unsampled instantaneous minimum or long soak.
- Cleanup suspended the Kustomization and deleted both controller Deployments. Independent guarded audit15:08:36UTC found **zero operations Deployments and zero active operations/proof-app pods**, fixture revision1, suspension=true, kubelet available1107.7MiB. The active exclusive lease was then archived unchanged and removed. Shared CRDs/namespaces/fixture remain; no retained PVC/PV or data was deleted.
- No monitoring/recovery/snapshot rerun, etcd restore/reset, new VM, host restart, source access or production change was performed. The earlier snapshot is still capture-only and predates this Flux fixture.

Reviewed receipts: [live transitions](evidence/talos-operations/flux-live.json), [admission](evidence/talos-operations/flux-admission.json), [bounded measurements/runtime images](evidence/talos-operations/flux-measurements.json), [final audit](evidence/talos-operations/flux-final-state.json), [lease release](evidence/talos-operations/flux-lease-release.json). The historical [admission refusal](evidence/talos-operations/flux-refusal.json) is unchanged.

## Production gaps / truthful acceptance

- No app-data copies, no database-consistency claim. Each app owner must perform app-aware logical backup/clean restore; this proof's tiny static archive is only the storage transport capability.
- No etcd restore until an independent approved disposable recovery target exists. No single-node/local-PV HA, replication, encrypted remote retention service, automated backup schedule, restore RTO/RPO or offsite durability claim.
- No production dashboards/long-retention metrics, scheduled external collector, event log/audit retention, persistent alert queue, pager delivery/acknowledgement, Prometheus rules or enterprise observability stack.
- No broad auto-reconciliation of apps until safe per-app desired state replaces zero-replica batch control, credentials are separately managed and capacity supports it. Fixture scope intentionally prevents autozero interference.
- The full36-container simultaneous acceptance gate is capacity-blocked; these staged capabilities do not remove that limitation.
