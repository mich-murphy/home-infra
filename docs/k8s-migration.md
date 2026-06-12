# Docker to Kubernetes Migration Runbook

This repo now contains the prepared Talos/Kubernetes migration, but the live
homelab still runs from `docker-host`. The migration remains inert until
Terraform is run with `-var enable_talos=true`.

## Current State

- Docker services are live on `docker-host` at `10.77.20.246`.
- The Talos VM is gated by `var.enable_talos`, which defaults to `false`.
- With the default Terraform variables, Terraform keeps `docker-host` started,
  keeps the iGPU attached to `docker-host`, and does not create VM 200.
- With `-var enable_talos=true`, Terraform creates `talos-prod-1` as VM 200,
  stops `docker-host`, disables docker-host autostart, and moves the iGPU to
  the Talos VM.
- RouterOS and Kubernetes manifests are prepared for a single-node Talos
  cluster at `10.77.20.20` with Cilium LoadBalancer IPs
  `10.77.20.224-10.77.20.254`.

## Target Topology

| Component | Address | Notes |
| --- | --- | --- |
| TrueNAS | `10.77.20.101` | NFS storage and backup targets |
| docker-host | `10.77.20.246` | Current live services, stopped at cutover |
| talos-prod-1 | `10.77.20.20` | Single-node Talos control plane and worker |
| Cilium Gateway | `10.77.20.224` | `*.local.elmurphy.com` after DNS cutover |
| qBittorrent peers | `10.77.20.225` | WAN dst-nat target after cutover |
| Plex direct | `10.77.20.226` | Direct LoadBalancer service |

## Preflight

1. Populate the 1Password `kubernetes` vault:
   - `cloudflare/credential`
   - `qbitwebui/encryption-key`
   - `plex/claim`, if a fresh claim is needed
   - `immich/db-password`
   - `owncloud/admin-password`, `owncloud/db-root-password`, `owncloud/db-password`
   - `miniflux/admin-username`, `miniflux/admin-password`, `miniflux/db-password`
   - `wallabag/db-password`
   - `couchdb/password`
   - `pocket-id/encryption-key`, copied from `/etc/pocket-id/encryption-key`
     on `docker-host` before shutdown
   - `pocket-id/maxmind-license-key`
   - `volsync/restic-password`
2. Generate Talos secrets/config locally and keep them out of git.
3. Confirm `talos/schematic.yaml` matches the Terraform
   `local.talos_schematic_id`.
4. Apply the RouterOS DHCP shrink and Kubernetes firewall rules before the VM
   is started.
5. On TrueNAS, allow `10.77.20.20` on the NFS exports used by Kubernetes.
6. On TrueNAS, create backup targets:

   ```sh
   /mnt/slow/backups/volsync
   /mnt/slow/backups/dumps
   ```

7. Rehearse database dumps from docker-host:
   - `pg_dumpall` for Immich PostgreSQL
   - `pg_dump` for Miniflux PostgreSQL
   - `mariadb-dump` for OwnCloud and Wallabag

## Freeze and Backup

1. Stop Portainer GitOps or otherwise prevent compose redeploys.
2. Stop application stacks with Docker Compose.
3. Run final database dumps to the TrueNAS staging area.
4. Tar each named Docker volume from
   `/var/lib/docker/volumes/<name>/_data` to a TrueNAS staging directory.
5. Keep docker-host disks intact. They are the first rollback path.

## Terraform Flip

Run Terraform from the repo root module:

```sh
just init
umask 077; terraform -chdir=terraform apply -var enable_talos=true
```

Expected effects:

- VM 200 `talos-prod-1` is created and started.
- `docker-host` is stopped and `on_boot` is set false.
- The iGPU passthrough moves from `docker-host` to `talos-prod-1`.
- TrueNAS, UniFi, and ai-dev VMs remain running.

Rollback before data cutover is the inverse:

```sh
umask 077; terraform -chdir=terraform apply -var enable_talos=false
```

That stops/removes the gated Talos VM resources from state intent, starts
docker-host again, and returns the iGPU to docker-host.

## Talos Bootstrap

1. Apply the control plane config:

   ```sh
   talosctl apply-config --insecure --nodes 10.77.20.20 --file <controlplane.yaml>
   ```

2. Apply the Talos firewall patch in try mode first:

   ```sh
   talosctl patch machineconfig --nodes 10.77.20.20 --mode=try --patch @talos/firewall-patch.yaml
   ```

3. Bootstrap etcd:

   ```sh
   talosctl bootstrap --nodes 10.77.20.20 --endpoints 10.77.20.20
   ```

4. Install Cilium before Flux reconciles workloads:

   ```sh
   helmfile apply -f talos/bootstrap/helmfile.yaml.gotmpl
   ```

5. Confirm node health:

   ```sh
   talosctl health --nodes 10.77.20.20 --endpoints 10.77.20.20
   kubectl get nodes -o wide
   ```

## Flux Bootstrap

1. Bootstrap Flux against `kubernetes/clusters/prod`.
2. Manually create the one bootstrap secret for the 1Password SDK token in
   namespace `external-secrets`.
3. Watch reconciliation order:
   - `infra-crds`
   - `infra-controllers`
   - `infra-configs`
   - `apps`
4. Confirm Cilium adopts the bootstrap Helm release rather than replacing it.
5. Confirm the shared Gateway becomes ready and receives `10.77.20.224`.

## Restore

For each stateful app:

1. Scale the Deployment to zero.
2. Start a one-off restore pod mounting the app PVC and the TrueNAS staging
   NFS path.
3. Untar files into the PVC.
4. `chown` data to the UID/GID used by the Kubernetes manifest.
5. Restore database dumps with `kubectl exec` or a one-off job.
6. Scale the Deployment back to one replica.
7. Verify probes, login, and expected app-specific behavior.

Database PVCs are restored from dumps, not VolSync direct copies. Direct
filesystem copies of live databases are not point-in-time safe.

## DNS and Network Cutover

1. Repoint the `*.local.elmurphy.com` wildcard DNS record from
   `10.77.20.246` to `10.77.20.224` in Cloudflare.
2. Update RouterOS WAN dst-nat for qBittorrent peers to `10.77.20.225`.
3. Remove the docker-host DHCP reservation for `10.77.20.246` after the
   cutover is accepted.
4. Verify DFLT/KDS clients can reach only the intended Kubernetes LoadBalancer
   services.

## Validation

Local validation matching CI:

```sh
catalog="https://raw.githubusercontent.com/datreeio/CRDs-catalog/main"
tmpl="{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
kubectl kustomize kubernetes/apps | kubeconform -summary -strict \
  -ignore-missing-schemas \
  -schema-location default \
  -schema-location ".github/schemas/${tmpl}" \
  -schema-location "${catalog}/${tmpl}"
kubectl kustomize kubernetes/infrastructure/crds | kubeconform -summary -strict \
  -ignore-missing-schemas \
  -schema-location default \
  -schema-location ".github/schemas/${tmpl}" \
  -schema-location "${catalog}/${tmpl}"
kubectl kustomize kubernetes/infrastructure/controllers | kubeconform -summary -strict \
  -ignore-missing-schemas \
  -schema-location default \
  -schema-location ".github/schemas/${tmpl}" \
  -schema-location "${catalog}/${tmpl}"
```

Cluster checks:

```sh
kubectl get helmreleases -A
kubectl get kustomizations -A
kubectl get gateway,httproute -A
kubectl get pods -A
kubectl get volumesnapshotclasses,pvc -A
```

## Soak and Cleanup

Keep docker-host stopped but intact until the Kubernetes workloads have soaked.
After soak, open a separate decommission PR to remove:

- `docker/`
- `ansible/roles/docker`
- docker inventory and group vars
- the Docker Compose CI gate
- the docker-host Terraform resource and cloud-init snippet
- the RouterOS `.246` DHCP reservation
- blanket `DFLT/KDS -> SRV` accept rules superseded by Kubernetes LB rules
- `docs/docker-hardening.md`

Do not remove rollback paths in the same PR that performs the cutover.
