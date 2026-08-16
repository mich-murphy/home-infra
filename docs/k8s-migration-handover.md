# Docker → Kubernetes Migration: Handover

Status as of 2026-06-11. This documents the in-flight migration prep so any
model or engineer can resume without re-deriving context.

## Goal and constraints

Migrate the docker-host workload (13 compose stacks, ~25 containers, deployed
via Portainer GitOps) to a single-node Talos Kubernetes cluster on Proxmox.
**The cluster cannot be started yet**: the Proxmox host has 31GiB usable RAM
(faulty DIMM) and docker-host must stay live until cutover. All work is
IaC-only. Rollout day is: populate 1Password → `terraform apply -var
enable_talos=true` (one switch: creates the Talos VM, stops docker-host,
moves the iGPU) → bootstrap → restore data → repoint DNS.

## Decisions (settled — do not relitigate)

- **Topology**: single Talos node (control plane + worker), 8 cores / 12GiB,
  VMID 200, swaps with docker-host. TrueNAS (10G) and UniFi (4G) stay up.
- **Versions**: Talos **v1.13.3**, Cilium **1.18.10**, Gateway API **v1.3.0**
  standard CRDs, cert-manager v1.20.2, Flux 2.8.x.
  **Do NOT bump Cilium to 1.19.x** — 1.19.3/1.19.4 break host networking on
  single-node Talos (cilium issue #46010). A pin comment in the HelmRelease
  guards the Renovate bump; lift it only when a release notes the fix.
- **Node networking**: static `10.77.20.20/24` on SRV VLAN 20. Pod CIDR
  `10.244.0.0/16` and service CIDR `10.96.0.0/12` pinned in the machine
  config; collision-checked against 10.77.0.0/16, 10.66.0.0/30 (OOB) and
  100.64.0.0/10 (Tailscale).
- **LoadBalancer IPs**: Cilium L2 announcements on `ens18`, pool
  `10.77.20.224–254`. Gateway `.224`, qbittorrent peers `.225`, plex-direct
  `.226`. The SRV DHCP pool shrinks to `.50–.223`. docker-host's reservation
  `.246` sits inside the LB range but is removed at cutover; the two are
  never live simultaneously.
- **Ingress**: Cilium **Gateway API** (not legacy Cilium Ingress, not
  Traefik) + cert-manager Cloudflare DNS-01 wildcard `*.local.elmurphy.com`.
  Shared Gateway `prod` in namespace `gateway`. Cilium 1.18 supports Gateway
  API v1.3.0 only; the experimental channel (ExternalAuth, GEP-1494) waits
  for Cilium 1.20.
- **CNI bootstrap**: `talos/bootstrap/helmfile.yaml.gotmpl` reads the chart
  version AND values from the Flux HelmRelease via `readFile` — one copy of
  values; Flux adopts the release on first reconcile. This replaced an
  unpinned `cilium-cli:latest` inline-manifest Job.
- **Storage (app config)**: OpenEBS LocalPV hostpath 4.4.0, basePath
  `/var/mnt/openebs` (Talos UserVolumeConfig on the second 128G vdisk),
  default StorageClass. Alternatives were researched and rejected; the host
  ZFS mirror already provides snapshots and checksums.
- **Storage (media)**: static NFS PVs to TrueNAS `10.77.20.101`, mirroring
  the docker-host fstab. No CSI driver — fixed exports, zero controller RAM.
- **Backup**: VolSync 0.16.0 restic ReplicationSources to a TrueNAS NFS
  export via `moverVolumes` (upstream supports NFS since v0.15). Databases
  use dump CronJobs instead — Direct copies are not point-in-time safe.
- **SSO**: Pocket-ID migrates as-is. Cilium ≤1.19 has no forward-auth, so
  Authelia's differentiator is unusable; GEP-1494 in Cilium 1.20 is
  IdP-agnostic, so nothing is lost by keeping Pocket-ID.
- **Monitoring**: victoria-metrics-k8s-stack (pin an exact 0.82.x — it is a
  0.x chart) replaces beszel. Roughly 0.8–1.2GB versus 1.5–2GB for a trimmed
  kube-prometheus-stack; the VM operator auto-converts
  ServiceMonitor/PodMonitor objects.
- **Dropped**: portainer (Flux replaces it), traefik (cilium), beszel (VM
  stack). The Zigbee USB dongle on docker-host is unused and dies with it.
- **Media servers**: both Plex and Jellyfin; the iGPU is shared via
  intel-gpu-plugin `-shared-dev-num=4` (plex + jellyfin + immich-server).

## PR stack (all open; each based on the previous; merge in order)

1. **#1539** `feat/ci-k8s-talos-validation` — kubeconform resolves real CRD
   schemas (CRDs-catalog); talos gate renders with talosctl and validates;
   talosctl added to the flake.
2. **#1540** `fix/terraform-talos-vm` — Talos VM vlan/sizing/watchdog; gated
   iGPU handover between docker-host and the Talos VM;
   `started = !enable_talos` on docker-host; image-factory ISO download.
3. **#1541** `feat/talos-v113-rewrite` — machine config rewrite: schematic
   `97349bd8a02320e952ef34bdc1369278958bf77fb1b1cbddb62ec6719777a7b6`
   (i915, intel-ucode, qemu-guest-agent, util-linux-tools), static net,
   pinned CIDRs, `talos/firewall-patch.yaml` (apply with `--mode=try`!),
   UserVolumeConfig, WatchdogTimerConfig, PSA exemptions trimmed to
   kube-system.
4. **#1542** `feat/k8s-cilium-gateway` — `infrastructure/crds/` (gateway-api
   v1.3.0), Flux chain crds → controllers → configs → apps, cilium 1.18.10
   with inlined values + helmfile bootstrap, SRV LB pool, openebs
   basePath/default-SC/PSA label, ansible DHCP pool shrink.
5. **#1543** `feat/routeros-k8s-firewall` — forward-chain only: k8s-node and
   k8s-lb address-lists, node management-only, client→LB:443 intent rules.
6. **#1544** `feat/k8s-cert-manager-gateway` — cert-manager v1.20.2 with
   `config.enableGatewayAPI`, ClusterIssuers, wildcard Certificate, shared
   Gateway `prod`, linkding converted to HTTPRoute.
7. **#1545** `feat/k8s-storage-gpu-volsync` — NFS PV/PVCs, namespaces
   media/immich/tools/auth, intel-gpu-plugin DaemonSet, volsync controller.
8. **#1546** `feat/k8s-apps-media` — radarr (the **exemplar**), sonarr,
   lidarr, prowlarr, qbittorrent (+ peers LB), qbitwebui, sabnzbd,
   audiobookshelf, pinchflat; vendored volsync schemas in `.github/schemas/`
   (the CRDs-catalog copy is stale and rejects `moverVolumes`).
9. **#1547** `feat/k8s-apps-plex-jellyfin` — plex (+ direct LB), tautulli,
   seerr, kometa as CronJob, jellyfin.
10. **#1548** `feat/k8s-apps-immich` — immich server/valkey/postgres,
    pg_dumpall CronJob, CiliumNetworkPolicies.

## Conventions (the app template)

`kubernetes/apps/media/radarr/` is the canonical app shape — copy it:

- Files: `storage.yaml` (openebs-hostpath PVC), `service.yaml` (ClusterIP),
  `deployment.yaml` (replicas 1, Recreate), `httproute.yaml`
  (`parentRefs: prod/gateway`, host `<app>.local.elmurphy.com` from the old
  traefik label), `replicationsource.yaml` (ExternalSecret `<pvc>-volsync` +
  ReplicationSource), `kustomization.yaml`. Add `secret.yaml`
  (ExternalSecret), `cronjob.yaml`, `networkpolicy.yaml` as needed.
- Images: `tag@sha256` digests copied **verbatim** from the compose file.
- Container mount paths preserved exactly from compose (subPath on the
  shared NFS PVCs where compose mounted a subdirectory).
- LSIO/root-dropping images: pod `seccompProfile: RuntimeDefault`; container
  `allowPrivilegeEscalation: false`, drop ALL + exactly the compose cap_add
  list, PUID/PGID env. Fixed-user images: full linkding-style runAsNonRoot.
- Probes from compose healthchecks (liveness 30/30/5/3, readiness initial
  delay 10).
- VolSync: `RESTIC_REPOSITORY=/mnt/repository/<pvc-name>`, password from the
  1Password item `volsync/restic-password`, NFS moverVolume
  `10.77.20.101:/mnt/slow/backups/volsync`, staggered nightly schedules
  (03:00–04:25 used so far). Databases get no volsync — dump CronJobs write
  to `10.77.20.101:/mnt/slow/backups/dumps`, weekday-rotated
  (`<app>-$(date +%u).sql.gz`).
- TZ literal `Australia/Melbourne`. Comments only where code can't show it.
- Backend DBs/caches get a CiliumNetworkPolicy (`cilium.io/v2`) limiting
  ingress to their app (plus the backup job where one exists).

Validation (run before every commit; matches CI):

```sh
catalog="https://raw.githubusercontent.com/datreeio/CRDs-catalog/main"
tmpl="{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
nix shell .#kubectl .#kubeconform --command bash -c "
  kubectl kustomize <dir> | kubeconform -summary -strict \
    -ignore-missing-schemas \
    -schema-location default \
    -schema-location \".github/schemas/${tmpl}\" \
    -schema-location \"${catalog}/${tmpl}\""
```

## Remaining work

### PR 11 — tools + auth

Branch `feat/k8s-apps-tools-auth` exists; nothing committed yet.

Already written and validated (untracked in the working tree):
`kubernetes/apps/tools/{miniflux,owncloud,wallabag}/` — complete with
deployments, ExternalSecrets (miniflux templates `database-url` via
`target.template`), dump CronJobs (02:35/02:40/02:45), network policies, and
volsync for non-DB PVCs. Reviewed and faithful to compose.

Still to write:

1. `kubernetes/apps/tools/couchdb/` (dir exists, empty). Compose source:
   `docker/couchdb/compose.yml` — image `couchdb:3.5.2@sha256:9a84b…`, user
   5984:5984 (full runAsNonRoot block), drop ALL with no adds,
   `COUCHDB_USER=admin` plus `COUCHDB_PASSWORD` from an ExternalSecret
   (1Password `couchdb/password`), PVC `couchdb-data` 2Gi at
   `/opt/couchdb/data`, probe `/_up` on 5984, host
   `couchdb.local.elmurphy.com`. **CORS decision**: configure CouchDB
   natively via a ConfigMap ini mounted at
   `/opt/couchdb/etc/local.d/cors.ini` (NOT gateway responseHeaderModifier —
   multiple origins cannot be echoed statically):

   ```ini
   [chttpd]
   enable_cors = true

   [cors]
   origins = app://obsidian.md, capacitor://localhost, http://localhost
   credentials = true
   headers = accept, authorization, content-type, origin, referer
   methods = GET, PUT, POST, HEAD, DELETE
   max_age = 3600
   ```

2. `kubernetes/apps/auth/pocket-id/` (dir exists, empty). Compose source:
   `docker/init/compose.yml` lines 92–122 — image
   `ghcr.io/pocket-id/pocket-id:v2.8.0@sha256:a0736…`, env
   `APP_URL=https://pocket-id.local.elmurphy.com`, `TRUST_PROXY=true`,
   `ANALYTICS_DISABLED=true`, PUID/PGID 1000 (root-dropping → six-caps
   pattern), `ENCRYPTION_KEY` and `MAXMIND_LICENSE_KEY` from ExternalSecret
   `pocket-id-credentials` (1Password `pocket-id/encryption-key`,
   `pocket-id/maxmind-license-key`), PVC `pocket-id-data` 1Gi at `/app/data`,
   service port 1411, probe `/healthz` on 1411, host
   `pocket-id.local.elmurphy.com`, volsync at "25 4 \* \* \*".
3. Parent kustomizations: `kubernetes/apps/tools/kustomization.yaml`
   (owncloud, miniflux, wallabag, couchdb) and
   `kubernetes/apps/auth/kustomization.yaml` (pocket-id).
4. Un-suspend renovate: delete the `suspend: true` line in
   `kubernetes/apps/default/renovate/cronjob.yaml`.
5. Add `- tools` and `- auth` to `kubernetes/apps/kustomization.yaml`.
6. Validate `kubectl kustomize kubernetes/apps`, commit **by explicit path**
   (see caveats), open the PR with base `feat/k8s-apps-immich`.

### PR 12 — monitoring

- `kubernetes/infrastructure/crds/`: add a HelmRelease for
  `victoria-metrics-operator-crds` (VM charts repo) — the VM stack chart no
  longer bundles CRDs. `prometheus-operator-crds` was dropped: with the
  prometheus-operator converter disabled (below), nothing in the cluster
  emits ServiceMonitor/PodMonitor objects, so the CRDs would be dead weight.
- `kubernetes/infrastructure/controllers/monitoring/`: namespace
  `monitoring` with `pod-security.kubernetes.io/enforce: privileged`
  (node-exporter), HelmRepository + HelmRelease `victoria-metrics-k8s-stack`
  pinned to an exact 0.82.x. Values: vmsingle 7–14d retention with a 768Mi
  limit, vmagent 256Mi, vmalert and vmalertmanager 128Mi, Grafana 256Mi plus
  an HTTPRoute at `grafana.local.elmurphy.com`; disable the control-plane
  scrape jobs a single Talos node cannot serve. The prometheus-operator
  object converter is disabled (`disable_prometheus_converter: true`) — the
  chart renders only native VM CRDs; re-enable it (and add
  `prometheus-operator-crds`) if a future chart ships ServiceMonitors. Wire
  into the controllers kustomization.

### PR 13 — docs + cleanup

- `docs/k8s-migration.md`: full runbook (outline below).
- README: architecture, VM table and k8s section refresh (pass 1 —
  "prepared, pending cutover").
- Delete `kubernetes/archive/` (cert-manager was revived in #1544; the rest
  is superseded; git history preserves it).

### Post-cutover PR (after soak)

Remove `docker/`, `ansible/roles/docker` and the docker group vars/hosts
entries, the docker CI gate, the docker-host terraform resource and
cloud-init snippet (lift `prevent_destroy` deliberately), the routeros
`.246` reservation and the blanket `DFLT/KDS -> SRV` accepts (the explicit
`-> k8s-lb:443` rules from #1543 take over), and retire
`docs/docker-hardening.md`. README final pass.

## Rollout-day runbook outline (for PR 13)

1. **Pre-flight**: populate the 1Password `kubernetes` vault —
   `cloudflare/credential` (exists), `qbitwebui/encryption-key`,
   `plex/claim` (optional), `immich/db-*`, `owncloud/*`, `miniflux/*`,
   `wallabag/db-password`, `couchdb/password`, `pocket-id/*` (**the
   encryption key is a host file**: `/etc/pocket-id/encryption-key` on
   docker-host — copy it off BEFORE shutdown), `volsync/restic-password`.
   Verify the schematic ID matches the repo; `talosctl gen secrets/config`
   (keep out of git); apply the routeros DHCP shrink and k8s firewall rules;
   on TrueNAS allow `10.77.20.20` on the exports and create
   `/mnt/slow/backups/{volsync,dumps}`; rehearse the DB dumps.
2. **Freeze + backup**: `docker compose down` everything; pg_dumpall
   (immich), mariadb-dump (owncloud, wallabag), pg_dump (miniflux); tar every
   named volume from `/var/lib/docker/volumes/<name>/_data` to a TrueNAS
   staging dir (both ends mount the NAS — no ssh copies).
3. **Flip**: `terraform apply -var enable_talos=true`; `talosctl
   apply-config --insecure` with the controlplane patch, then the firewall
   patch with `--mode=try` first; `talosctl bootstrap`; `helmfile apply -f
   talos/bootstrap/helmfile.yaml.gotmpl`; flux bootstrap (gotk flow; the
   repo already points at `kubernetes/clusters/prod`); manually create the
   `onepassword-sdk-kubernetes` token secret in namespace `external-secrets`
   (the one bootstrap secret); watch Flux adopt the cilium release.
4. **Restore**: per app — scale to 0, run a one-off pod mounting the app PVC
   and the staging NFS dir, untar, chown to the app's UID, scale up.
   Databases restore from dumps via `kubectl exec`. Verify each app (probe
   green, login works, library scan).
5. **Cutover**: repoint the `*.local.elmurphy.com` wildcard DNS record from
   `10.77.20.246` to `10.77.20.224` (Cloudflare, outside this repo);
   RouterOS WAN dst-nat 25565 → `10.77.20.225`; remove the docker-host DHCP
   reservation.
6. **Soak + decommission**: docker-host stays stopped-but-intact as the
   rollback path (an `enable_talos=false` apply reverses everything);
   schedule Proxmox ZFS snapshots of the talos data vdisk; then the
   post-cutover PR.

## Caveats and sharp edges

- **The user live-edits the repo while agents work.** Unstaged changes you
  did not author are probably the user's. NEVER `git restore` or
  `git checkout --` over them; save `git diff > /tmp/backup.patch` first;
  commit by explicit path list, never `git add -A`. One batch of the user's
  comment-trim edits was already lost this way; a second batch is preserved
  at `/tmp/user-comment-trims.patch` and belongs on the #1543 branch.
- The local `terraform.tfstate` on the original machine still references the
  old telmate provider — `terraform init` there mutates the lockfile. CI
  validates from a clean checkout; never commit that lockfile change.
- iGPU passthrough under OVMF/q35 is untested until rollout day; the knobs
  are `rombar`/`pcie` on the hostpci block; the fallback is CPU transcode.
- The jellyfin compose published 8096 directly on the LAN; k8s serves it
  gateway-only. If direct-IP access matters, add a LoadBalancer like plex's.
- The Talos firewall patch can lock the node out — always `--mode=try`
  first.
- The bpg provider `watchdog` block validated offline but is untested
  against a live Proxmox; fall back to a one-time `qm set 200 --watchdog
  model=i6300esb,action=reset` if the apply rejects it.
