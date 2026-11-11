# Talos proof platform — live Talos, Kubernetes API blocked

## Current checkpoint

VM120 is RUNNING: 2560MiB fixed,2vCPU,32GiBOS+64GiBdata. Authenticated
Talos1.14.5/RBAC and etcd/kubelet/cri are healthy. UserVolume `u-proof` is
ready on `/dev/sdb1`, XFS mounted `/var/mnt/proof`. Kubernetes bootstrap completed,
but **kube-apiserver:v1.36.6 exits139 (segfault), empty application logs**.
Scheduler/controller errors are downstream APIEOF. No node registers yet; no CNI,
apps, Gateway, complete isolation test or Taloshealth success can be claimed.
No existing guest, host tuning, production DNS/router/NFS/GPU was changed.

Host initial swap24KiB is recorded baseline. VM creation was initially blocked by
strict zero-swap guard; parent explicitly approved baseline-relative monitoring.
Two early stops were guard false positives from decaying PSIavg10 after brief boot
bursts; ONLY VM120 stopped. Corrected guard uses actual PSI total deltas: full>=1%
or some>=5% sustained30seconds, ongoing swapIO3samples, swapdelta>64MiB or immediate
MemAvailable<1536MiB. It runs privately on Proxmox. Latest stabilized samples:
host~3.4–3.6GiB available, swap24KiB unchanged, PSI actualdelta0%, no swapIO.
Guest1816MiB available/2384MiB total at APIsegfault, no dmesgOOM: RAM bump not justified.

## Pinned compatibility

- Talos/talosctl **v1.14.5**, GitHub latest stable release verified during discovery.
- Kubernetes **v1.36.6**, upstream `stable-1.36.txt`; Talos1.14 supports1.33–1.37.
- Cilium **v1.20.4** recommended to the networking owner: official tested Kubernetes
  matrix1.33–1.36. Talos default1.37.1 deliberately NOT used.
- Cilium/storage installation is another worker's scope. No CNI is installed here.
- Modern config deletes `KubeFlannelCNIConfig`, disables `KubeProxyConfig`, clears the
  control-plane scheduling taint, selects only proof nodeIP, uses public DNS, and
  disables discovery. KubePrism default7445 supports Cilium localhost:7445.

Sources fetched after web search (Google search itself returned an interstitial):
- https://github.com/siderolabs/talos/releases/tag/v1.14.5
- https://docs.siderolabs.com/talos/v1.14/platform-specific-installations/virtualized-platforms/proxmox.md
- https://docs.siderolabs.com/talos/v1.14/getting-started/support-matrix.md
- https://docs.siderolabs.com/kubernetes-guides/cni/deploying-cilium.md
- https://docs.cilium.io/en/stable/network/kubernetes/compatibility/
- https://dl.k8s.io/release/stable-1.36.txt

## Reproducible private tools and offline validation

From repository root:

```sh
infrastructure/proxmox-proof/bootstrap-tools.sh  # darwin-arm64 or linux-amd64
infrastructure/proxmox-proof/validate.sh
```

Both use `STATE`, default `$HOME/.local/state/home-infra/talos-proof`. Tool installer
checks the downloaded binary against official release SHA256 manifest before install.
Directories0700, generated identity/config/secrets0600; never commit generated config.
Downloaded binary0700. Do not use Nix talosctl1.13 against1.14 config.
`validate.sh` can run in CI, generates a fresh private identity if absent, and invokes:

```sh
"$STATE/bin/talosctl" validate --config "$STATE/config/controlplane.yaml" --mode metal --strict
```

Offline strict validation succeeded. It does NOT prove bootability or isolation.
`generate.sh` refuses to overwrite existing identity. Static patch changes require
regeneration in a fresh private STATE rather than overwriting an active cluster identity.

## Proposed resources / additive networking (UNVERIFIED)

VMID120 was absent cluster-wide. Dedicated VM:2vCPU host type, **2560MiB** fixed/no
balloon (reduced from approved3072 due falling host headroom),32GiB OS +64GiB dedicated
data local-zfs. q35/OVMF, no Secure Boot keys, VirtIO SCSI PCI (not Single), no GPU,
no guest agent. Below recommended4GiB control-plane RAM, above2GiB minimum. Resource
limits constrain subsequent applications; do not promise full35-container concurrency.

QEMU slirp user-mode network172.31.250.0/24; private DHCP node172.31.250.10,
gateway172.31.250.2; IPv6 disabled. It has no host bridge, LAN address or host route,
so no DHCP boundary/LAN address is consumed. Host `ip_forward` remains0. This is
**proof overlay only, not production networking parity**. No unverified native bridge
example is supplied as production-ready.

Proposed host forwards bind loopback only:
- Proxmox127.0.0.1:50120 -> guest50000 Talos
- Proxmox127.0.0.1:64120 -> guest6443 Kubernetes

`isolation.sh` scopes OUTPUT to `/sys/fs/cgroup/qemu.slice/120.scope`; allows established
replies, public HTTP(S), DNS and NTP only; rejects RFC1918, CGNAT, loopback, link-local,
multicast/reserved targets and all new IPv6. Refresh puts a cgroup DROP before rebuilding,
then removes it after the completed chain is linked. It rebinds the jump for each new
scope identity. Failures leave a DROP or paused VM, not a deliberately open chain.
This design still needs experimental validation, especially slirp's host gateway/DNS
proxying, socket cgroup attribution and hostfwd reply conntrack.

## Creation and startup

`create.sh` runs ONLY on Proxmox, requires explicit `APPROVE_TALOS_PROOF=120`, absence
of VM120 config, at least4450MiB MemAvailable and records existing swap baseline. Revalidate VMID
cluster-wide, no port collision, ISO checksum and resource budget before invocation.
It is intentionally not an old Terraform apply.

QEMU args include `-S` (CPUs paused). `onboot=0` prevents host reboot auto-start.
Copy `start.sh` and `isolation.sh` alongside `create.sh` in
`/root/.local/state/home-infra/talos-proof/`, then run `start.sh`. It starts paused,
installs isolation, then resumes. **Never directly resume VM120 before isolation.**
A direct `qm start120` remains paused because of `-S`; direct `qm resume120` bypasses
this administrative safety boundary. No hook is installed. Full host reboot requires
manual wrapper startup; guest reboot retains the same scope/rules. Both paths need live
verification; persistence is design, not yet demonstrated.

## Expected access / bootstrap after approval and network tests

Tunnel is active (SSH control socket `$STATE/ssh-control`). Exact tunnel (foreground or supervised separately):

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:50120:127.0.0.1:50120 \
  -L 127.0.0.1:64120:127.0.0.1:64120 root@proxmox
```

Private tool: `/Users/mm/.local/state/home-infra/talos-proof/bin/talosctl`.
Private machine config: `/Users/mm/.local/state/home-infra/talos-proof/config/controlplane.yaml`.
Private Talos identity: `/Users/mm/.local/state/home-infra/talos-proof/config/talosconfig`.
Private kubeconfig (exists, API currently unhealthy): `$STATE/config/kubeconfig`, endpoint
`https://127.0.0.1:64120`; cluster internal endpoint172.31.250.10:6443.

After transport tests, apply config via insecure maintenance endpoint127.0.0.1:50120,
then configure authenticated Talos endpoint127.0.0.1:50120 and node127.0.0.1 (direct
endpoint; not routed guest IP). Bootstrap etcd once, retrieve kubeconfig explicitly
outside default ~/.kube, and rewrite only that file's API server to tunnel endpoint.
Follow exact talosctl `--help` port syntax rather than assuming node forwarding semantics.
Install Cilium promptly after API available; pre-CNI NotReady is expected, not health.

## Required live acceptance still outstanding

1. Snapshot existing VM config hashes/status and read-only production reachability.
2. Verify paused QEMU start, cgroup matching counters, public DNS/HTTPS/NTP, hostfwd replies.
3. From guest AND pod, reject gateway proxy172.31.250.2 to host SSH/8006/loopback,
   RFC1918 production destinations, CGNAT/Tailscale, IPv6 and slirp DNS bypass.
4. Verify existing guest traffic unaffected, and guest reboot/full VM restart fail-closed.
5. Monitor MemAvailable >=1536MiB, swap delta0 and memory PSI; stop ONLY proof VM on breach.
6. Talos authenticated version/disks/services, `talosctl health`, API `/readyz?verbose`,
   node Ready after Cilium, no kube-proxy/flannel, and resource evidence.
7. Hand exact working kubeconfig/tunnel to parent/network worker. Not done yet.

## Updated operational details / cleanup

Factory installer is mandatory: `factory.talos.dev/metal-installer/376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba:v1.14.5`.
The initially tried ghcr.io installer tag404 was corrected before installation.
QEMU VGA is now `std` for troubleshooting (serial-only obscured installation errors).
Gateway loopback18080->30080 and18443->30443 are configured; platform owner must
coordinate actual dynamic service NodePorts. No Gateway traffic is proven.

Authenticated Talos node is172.31.250.10, not a localhost-with-port node target:
`talosctl --talosconfig "$STATE/config/talosconfig" --nodes172.31.250.10 version`
(with a space after `--nodes`). Endpoint127.0.0.1:50120 is stored in talosconfig.
`start.sh` starts the guard automatically; Python flock prevents duplicate guards.
Copy all four `start.sh`, `isolation.sh`, `resource-guard.py`, `create.sh` to the same
private Proxmox state directory. `-S` plus onboot0 fail closed on host restart.
No existing guest uses this cgroup or these firewall chains.

Cleanup after explicit approval:
1. Verify `qm config120` identifies `name:talos-proof` (use spaces in actual commands).
2. `qm stop 120` ONLY; stop private guard by its recorded PID after checking command.
3. Remove OUTPUT jumps targeting `TALOS_PROOF_120` from iptables/ip6tables by numeric
   line number descending (scope no longer exists, so cgroup path matching cannot
   safely be used to delete a stale binding). Flush/delete ONLY `TALOS_PROOF_120` chains.
4. `qm destroy120 --purge1 --destroy-unreferenced-disks1` (proper CLI spaces) ONLY after
   confirming dedicated VM identity and accepting destruction of proof data.
5. `ssh -S "$STATE/ssh-control" -O exit root@proxmox`; optionally delete ONLY proof ISO
   `/var/lib/vz/template/iso/talos-proof-v1.14.5-amd64.iso` and private proof state.
Never remove shared storage, old VMs, host bridges, production firewall rules or secrets
belonging to another environment. No automatic destructive cleanup is provided.
