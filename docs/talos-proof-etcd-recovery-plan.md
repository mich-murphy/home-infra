# Proposed isolated etcd recovery — blocked on explicit approval

**NOT AUTHORIZED OR EXECUTED.** The existing 12,443,680-byte snapshot is capture-only.
The [operations contract](talos-proof-operations.md) requires a separate disposable
recovery target. No second VM is authorized. Executing this alternative therefore
requires an explicit decision to supersede that restriction for **one destructive,
in-place EPHEMERAL reset and guest reboot of VM120**. It may leave the proof API
unavailable. It grants no Proxmox cold start, RAM increase or production change.

Review/approval location: https://github.com/mich-murphy/home-infra/pull/2005

This is a source-backed design, not an executable runbook or live lease. Parent
integration, actual volume/resource observations and a separately reviewed runner
remain required. Original target guards, host lifecycle/enforcement code and
historical enrollment baselines must remain unchanged.

## Supported method and crucial qualification

Talos v1.14 documentation and the v1.14.5 integration test support snapshot →
non-graceful selected reset/reboot → authenticated bootstrap from snapshot on a
single control-plane node. The relevant command shapes are `etcd snapshot`,
`reset --graceful=false --reboot --system-labels-to-wipe=EPHEMERAL`, and
`bootstrap --recover-from`. **Do not execute these from this document.**

EPHEMERAL-only is valid **only if actual ETCD/CRI/KUBELET volumes are directory-backed
under it**. Talos1.14 supports promoted dedicated system partitions; the upstream
test checks resolved VolumeStatus and accounts for them. Unexpected promotions
block this minimal proposal; never automatically expand the destructive label list.

A correctly scoped EPHEMERAL reset preserves STATE/machine configuration/CA and
does not target the separate XFS `/dev/sdb1` mounted at `/var/mnt/proof`. It erases
etcd, ordinary image/kubelet state and ephemeral diagnostics. Configuration alone
is not proof of actual disk placement. Every application backing path must resolve
to the dedicated filesystem, not merely have the expected path prefix.

## Mandatory phases before any acceptance

1. **Approval and preservation:** obtain the explicit policy exception and a new
   bounded receipt. All apps/controllers0, CronJobs suspended, no app/helper pods,
   Flux suspended/controllers absent. Export required historical guest diagnostics;
   preserve every old archive/failure/credential byte. Verify actual versions,
   volume mapping, filesystem UUID/device, guard and fresh resource observations.
2. **Identity baseline:** record all PV/PVC UIDs/bindings/Retain policies/backing
   paths, private Secret content hashes, Service addresses/NodePorts, Gateway/TLS
   identities and existing persistence nonce. Obtain a bounded, quiescent content
   and metadata manifest of all application backing directories, including retained
   directories, symlinks/hardlinks and relevant ownership/modes/xattrs. The collector
   itself requires review and resource accounting; hashing is not free.
3. **Real rollback oracle:** create one new uniquely owned ConfigMap containing
   nonce A. Independently read A and its UID. Capture a NEW UUID-named off-node
   snapshot in a0700 directory/file0600, exclusively created; preserve the old
   capture. Verify SHA256, embedded checksum, status/revision/key count and version
   bindings. Change ONLY this ConfigMap to B and independently read B/same UID.
4. **Bounded recovery:** under the separate identity gate below, perform exactly
   the approved selected reset/reboot. Require authenticated return, preserved
   identity/layout and expected absent old member data/etcd Preparing state.
   Bootstrap once from the exact new snapshot with integrity checking enabled.
   No maintenance/insecure mode, first-bootstrap shortcut, skip-hash-check,
   whole-disk/user-volume wipe, guessed flags or reset/rebootstrap retry loop.
5. **Independent acceptance:** require healthy single-member etcd, ready API and
   original node UID; same ConfigMap UID with A restored after witnessed B; all apps
   still stopped; identical snapshot-time Secret/PVC/PV/Service/TLS identities and
   application-volume content/metadata manifests; unchanged dedicated filesystem
   and persistence nonce. Trusted Gateway TLS must validate. A503 with all backends
   stopped is expected, not application functional acceptance.

## API-down targeting must remain fail-closed

The ordinary target gate requires a working Kubernetes API and cannot simply be
skipped. A new bounded recovery state machine must first pass that gate and bind
node UID `4845bfd5-3bdb-453d-8503-83b43edb7a1e`, then pin the **existing** Talos CA,
client/config digest, context, endpoint `127.0.0.1:50120` and node `172.31.250.10`.
Authenticated `SystemInformations.hardware.talos.dev/systeminformation.spec.uuid`
must equal VM120's `555e8603-58e6-4fb6-a190-378a3f11c257` before each recovery mutation.
Bind snapshot digest/path, volume/config identities, phase, expiry and bounded
attempts. No general Kubernetes mutation is permitted while its ordinary gate
cannot pass. After return, require that original node UID; no automatic adoption
or credential regeneration. This is accidental-target protection, not attestation
against a malicious clone.

## Stop boundaries and limits

- A guest reboot normally retains QEMU PID/start ticks/cgroup while changing guest
  boot ID. Independently verify host-incarnation continuity. Keep3072MiB/2vCPU,
  original guard thresholds and original swap baseline.
- If QEMU exits or the guard stops it, **leave VM120 stopped**. No `qm start/resume`,
  guard bypass/restart or automatic recovery boot is granted.
- Stop on identity/layout/checksum mismatch, missing preservation, expired scope,
  inadequate resources, image-pull failure or recovery deadline. Do not widen
  networking to repair a pull failure.
- Expect infrastructure image repulls. Keep Talos1.14.5/Kubernetes1.36.5 and actual
  existing etcd identity; no upgrade belongs in this drill.
- Talos1.14.5 restore supplies no revision-bump/mark-compacted options. Record Raft
  membership/revisions without requiring old numeric IDs or resourceVersions.
  Restart external watches; object UIDs and snapshot data are the identity oracles.
- This could establish **actual etcd rollback only**. It would not restore the older
  capture, restore application files, prove HA or approve production migration.

## Versioned research provenance

Read-only worker `f0c49c93-7f24-47b` reviewed repository files and public sources;
no runtime calls, changes or execution authority were involved.

- [v1.14 disaster recovery](https://docs.siderolabs.com/talos/v1.14/build-and-extend-talos/cluster-operations-and-maintenance/disaster-recovery)
- [v1.14.5 recovery integration test](https://github.com/siderolabs/talos/blob/v1.14.5/internal/integration/api/etcd-recover.go)
- [v1.14 disk layout](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/storage-and-disk-management/disk-management/layout)
- [v1.14 system volumes](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/storage-and-disk-management/disk-management/system)
- [v1.14.5 reset CLI](https://github.com/siderolabs/talos/blob/v1.14.5/cmd/talosctl/cmd/talos/reset.go)
- [v1.14.5 reset sequencing](https://github.com/siderolabs/talos/blob/v1.14.5/internal/app/machined/pkg/runtime/v1alpha1/v1alpha1_sequencer.go)
- [v1.14.5 snapshot CLI](https://github.com/siderolabs/talos/blob/v1.14.5/cmd/talosctl/cmd/talos/etcd.go)
- [v1.14.5 bootstrap CLI](https://github.com/siderolabs/talos/blob/v1.14.5/cmd/talosctl/cmd/talos/bootstrap.go)
- [v1.14.5 restore service](https://github.com/siderolabs/talos/blob/v1.14.5/internal/app/machined/pkg/system/services/etcd.go)
- [v1.14.5 authenticated hardware UUID resource](https://github.com/siderolabs/talos/blob/v1.14.5/pkg/machinery/resources/hardware/system_information.go)
