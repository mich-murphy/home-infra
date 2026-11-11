# Talos isolated proof delivery

## Checkout and scope
- Worktree: `/Users/mm/dev/home-infra-talos-proof`, branch `feat/talos-live-proof`, base `8de8c051` (`origin/main`). Registered with `gh stack` against main.
- Original `/Users/mm/dev/home-infra` contains extensive pre-existing user edits. Never modify, stage or reset them. Reference branch `origin/feature/talos-kubernetes` is historical design only, NOT safe to apply (stops docker-host, moves GPU and changes DNS/network).
- Deliver: smallest resource-safe live Talos node on Proxmox; maintainable declarative cluster/apps; isolated replicas of current Docker services; reproducible functional, isolation, persistence/recovery and resource evidence; honest migration readiness matrix.
- Absolute exclusions: no changes/restarts/stops to docker-host or its services, no shared production volume writes, no production DNS/routing changes, no GPU reassignment, no existing-VM resource changes. Read-only discovery permitted. Only dedicated proof resources may be mutated.
- Credentials never committed or printed; local private state outside git, mode 0700/0600. Copies use fresh proof credentials and must not contact production integrations or trigger real downloads/notifications.

## Capabilities and ownership
- Coordinator owns this brief, integration, quality gates and final acceptance. Supported background subagents, progress inspection and steering available. Requested worker model `gpt-6.1-sol` (startup pending).
- Shared worktree, disjoint paths; commit only explicit owned paths. No worker may use existing Terraform apply or bootstrap from old branch. Worker concurrency limit is 3; queued receipts are not startup evidence.
- `d03adc99-6042-4c0`: Talos/Proxmox; owns `talos/`, `infrastructure/proxmox-proof/`, `docs/talos-proof-platform.md`, `docs/evidence/talos-platform/`; verified active. Default30turn limit interrupted; resumed200 turns. Initial offline checkpoint `600bc67e`, live work continues.
- `b3689397-1069-4a2`: read-only source inventory; owns `docs/talos-proof-inventory.md`, `docs/evidence/talos-inventory/`; completed/stopped, commit `9520a571`, parent reviewed. 36 containers; discovery no-touch comparison clean. Final comparison still required.
- `6befdde0-8478-4ba`: Cilium/storage/Gateway; owns `kubernetes/platform/`, `kubernetes/bootstrap/`, `docs/talos-proof-architecture.md`, `docs/evidence/talos-network-storage/`; offline checkpoint `35ca89d2`; interrupted default30turn limit, resume200 queued to finish report then await live lease. No CNI install yet.
- `3a63b030-2464-411`: media workloads; owns `kubernetes/apps/media/`, `scripts/talos-proof-media*`, `tests/talos-proof-media*`, `docs/talos-proof-media.md`, `docs/evidence/talos-media/`; verified active, 17 services mapped; live lease NOT granted.
- `aded9180-673d-409`: data/identity workloads; owns `kubernetes/apps/data/`, `scripts/talos-proof-data*`, `tests/talos-proof-data*`, `docs/talos-proof-data.md`, `docs/evidence/talos-data/`; verified active; live lease NOT granted.
- `575577df-312b-45a`: operations; owns `kubernetes/operations/`, `scripts/talos-proof-operations*`, `tests/talos-proof-operations*`, `docs/talos-proof-operations.md`, `docs/evidence/talos-operations/`; queued200 turns. GitOps, lean monitoring/alerts, off-node recovery; no deploy lease.
- Coordinator additionally owns root integration, tests/CI/toolchain, runbook and final evidence. Live application testing requires coordinator-granted single resource lease; no concurrent memory-heavy suites.

## Initial observations / decisions
- SSH `root@proxmox` and `docker-host` works. Proxmox: 31,834 MiB physical, 5,024 MiB available, zram unused; VM101 TrueNAS and VM102 Docker each 10 GiB; VM111 stopped. Storage ample, CPU 28 threads. Capacity must be measured again before allocation; full concurrent service replicas may not fit without violating exclusion.
- Running Docker inventory: 36 containers including Nextcloud (not old ownCloud), Collabora, Immich + ML, media services, Pocket-ID, CouchDB, Miniflux, Wallabag, integration helpers, Beszel/Traefik/Portainer/socket-proxy.
- Prior branch explicitly rejected Mayastor for single node in favor of OpenEBS LocalPV; re-evaluate against measured capacity/current documentation, do not assume.
- Integration contract: `proof-<service/trust-group>` namespaces; `app.kubernetes.io/part-of: talos-proof`; storage class `proof-local`; `proof-validation` probe namespace; `proof-gateway` ingress namespace. Fresh independent data only, no production NFS; all-app default replicas=0/CronJobs suspended, activate bounded batches for resource-safe experiments. Full simultaneous service operation is a separate acceptance gate, not implied by staged tests.

- Capacity correction: available dropped to ~4.5GiB before allocation. Node budget reduced2560MiB; retain >=1.5GiB host available. Tiny24KiB pre-existing zram is baseline, not proof-caused pressure; guard against sustained PSI/swap traffic or >64MiB growth. No other guest/host tuning.
- Network: VM120 QEMU slirp172.31.250.10, localhost forwarded management/Gateway via SSH. No global forwarding/bridge/router/DNS changes. Scoped cgroup OUTPUT filter must remain fail-closed; parent flagged flush/recreated-scope hazards, worker correcting. NOT native production network parity.
- Pins: Talos1.14.5, Kubernetes1.36.6, Cilium1.20.4, GatewayAPI1.6.1 verified compatibility. Dedicated64GiB UserVolume `/var/mnt/proof`; lightweight local-path class proof-local Retain/WFFC. Mayastor requires2CPU+1GiB RAM+2GiB hugepages before Kubernetes and cannot replicate across one node: rejected.

## Verification and acceptance
- Acceptance pending. No cluster yet. Single-node failure tolerance cannot be claimed as HA. Healthy probes alone do not prove migration readiness; per-service functional and recovery checks required.

## Next action / open integration corrections
- VM120 created, bootstrapping. Node owner to provide API/kubeconfig and mount evidence, then platform lease before any apps.
- Parent review correction for platform owner: `local-path-storage` namespace currently has part-of=talos-proof and therefore clusterwide `egressDeny kube-apiserver` blocks provisioning controller API. Change platform namespace selector/label and add narrow API/DNS policy; preserve deny for app namespaces. Not yet sent directly (owner queued), NOT accepted.
- Gateway NodePorts currently dynamic but QEMU hostforwards30080/30443. Resolve declaratively if supported; otherwise discover/forward actual assigned ports. Do not claim TLS route until tested end-to-end.
- App workers instructed to add all frontend HTTPRoutes `<service>.proof.invalid` to Gateway proof/proof-gateway, align proof origins. Need observe uptake.
- Static safety gate, mutation regressions and CI parent-authored; full render gates pending app workers' complete manifests. Next inspect live isolation and disk, then serial app proof leases.
