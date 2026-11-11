# Talos proof platform — provisioning blocked, NOT live

## Status and safety decision

No VM120 exists, no Talos node was booted, and no kubeconfig/API/health evidence exists.
The create guard rejected host capacity first, then rejected swap usage. **Do not treat
these artifacts as demonstrated live isolation or migration readiness.** No existing VM,
bridge, host sysctl, router, DNS, NFS, Docker service or GPU was changed. An official
checksum-verified ISO and private helper scripts were copied to Proxmox; no VM created.

Initial available memory was4961MiB, then declined to~4516MiB independently of proof
allocation. Swap grew from0 to24KiB before proof creation. Even though tiny, relaxing
the explicit zero-swap guard would not satisfy the agreed resource requirement.
Investigate read-only and obtain renewed parent approval before proceeding. Do not
change ARC/host tuning, existing VM resources or running production services.

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

## Creation and startup (NOT executed successfully)

`create.sh` runs ONLY on Proxmox, requires explicit `APPROVE_TALOS_PROOF=120`, absence
of VM120 config, at least4450MiB MemAvailable and exactly0 swap used. Revalidate VMID
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

No tunnel currently exists. Proposed exact tunnel (foreground or supervised separately):

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:50120:127.0.0.1:50120 \
  -L 127.0.0.1:64120:127.0.0.1:64120 root@proxmox
```

Private tool: `/Users/mm/.local/state/home-infra/talos-proof/bin/talosctl`.
Private machine config: `/Users/mm/.local/state/home-infra/talos-proof/config/controlplane.yaml`.
Private Talos identity: `/Users/mm/.local/state/home-infra/talos-proof/config/talosconfig`.
Expected kubeconfig (does NOT exist): `$STATE/config/kubeconfig`, endpoint
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
