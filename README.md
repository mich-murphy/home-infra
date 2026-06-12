# home-infra

Infrastructure-as-code for a single-server homelab running on Proxmox. Manages VM provisioning, host configuration, containerised application services, and a prepared Talos Kubernetes migration.

## Hardware

| Component   | Specification                                                      |
| ----------- | ------------------------------------------------------------------ |
| CPU         | Intel Core i7-14700 (20C/28T)                                      |
| RAM         | 64GB Micron DDR5 ECC                                               |
| Motherboard | Supermicro X13SAE                                                  |
| Boot disk   | 250GB NVMe                                                         |
| VM storage  | 2x 1TB Samsung EVO NVMe (ZFS mirror, Proxmox-managed)              |
| Data SSDs   | 2x Micron 960GB DC SSD (ZFS mirror metadata vdev, TrueNAS via HBA) |
| Data HDDs   | 2x Seagate IronWolf 10TB (ZFS mirror, TrueNAS via HBA)             |

## Architecture

```
Proxmox v9.1.6 (hypervisor)
├── TrueNAS VM (SRV VLAN) ─── NFS shares (media, downloads, bulk storage)
├── Docker Host VM (Ubuntu 24.04) ─── live services via Docker Compose
│   └── Traefik → *.local.elmurphy.com (TLS via Cloudflare ACME)
├── UniFi OS Server VM (MGMT) ─── Network controller for AP/WLANs
├── ai-dev-bgd VM (DMZ) ─── Isolated AI development sandbox
└── [Talos K8s VM] ─── prepared, gated by enable_talos, pending cutover
```

### Network (MikroTik RB5009 + UniFi AP)

Routing, DHCP, firewall policy and inter-VLAN isolation live on the MikroTik
RB5009 and are managed by the Ansible `routeros` role. The UniFi controller runs
as a dedicated Proxmox VM (`unifi-controller`, VMID 111) and the AP/WLAN objects
are managed through the UniFi controller API (`terraform/network`).

| Network | VLAN / link | Purpose |
| --- | --- | --- |
| MGMT | native VLAN 1 | Wired-only management plane (`10.77.1.0/24`) |
| SRV | VLAN 20 | TrueNAS + docker-host services (`10.77.20.0/24`) |
| DFLT | VLAN 30 | Main wireless clients (`10.77.30.0/24`) |
| KDS | VLAN 50 | Kids wireless clients with filtered DNS (`10.77.50.0/24`) |
| GST | VLAN 60 | Guest wireless clients with UniFi L2 isolation (`10.77.60.0/24`) |
| DMZ | RB5009 `ether2` / Proxmox `vmbr1` | Isolated ai-dev VMs (`10.77.99.0/24`) |
| OOB | RB5009 `ether7` | Break-glass router access (`10.66.0.0/30`) |

The server has two ethernet ports: `eno2`/`vmbr0` trunks MGMT/SRV to RB5009
`ether3`, while `eno1`/`vmbr1` is the untagged DMZ uplink to RB5009 `ether2`.
The UniFi U7 Pro AP is adopted in the controller. The three managed WLANs are
attached to the default `All APs` group and mapped to the DFLT/KDS/GST
VLAN-only networks. The ai-dev VMs are isolated on the physical DMZ
(`10.77.99.0/24`), protected by host nftables default-deny input rules, and
further scoped by an external Tailscale ACL policy managed outside this repo.

## Repository Structure

```
.
├── terraform/       # Proxmox VM provisioning
├── ansible/         # Host configuration (Docker host, game server)
├── docker/          # Docker Compose services (active until cutover)
├── kubernetes/      # Flux CD manifests (prepared, not live)
├── talos/           # Talos Linux cluster config (prepared, not live)
├── docs/            # Documentation
├── flake.nix        # Nix dev shell
└── justfile         # Task runner
```

## Prerequisites

- [Nix](https://nixos.org/) with flakes enabled (provides all tooling via `flake.nix`)
- [direnv](https://direnv.net/) (auto-loads the Nix dev shell)

The dev shell includes: terraform, ansible, just, talosctl, kubectl, k9s, fluxcd, helm, alejandra.

## Quick Start

```sh
# Enter the dev shell (automatic with direnv, or manually)
nix develop

# Terraform
just init       # terraform init
just apply      # terraform apply
just destroy    # terraform destroy
just network-init && just network-apply   # UniFi VLAN-only networks + WLANs

# Ansible
just reqs                   # install galaxy requirements
just run docker-host        # run playbook against a host
just run unifi-controller   # configure UniFi OS Server VM
just routeros               # steady-state strict RouterOS config
just edit                   # edit encrypted vault secrets
```

## Terraform

Provisions VMs on Proxmox using the [bpg/proxmox](https://registry.terraform.io/providers/bpg/proxmox) provider. Secrets sourced from 1Password via the `onepassword` provider.
Run Terraform through the `just` recipes so local state and generated cloud-init files are created with a restrictive umask. Terraform state is secret-bearing because provider data includes Proxmox credentials, WLAN PSKs, and bootstrap auth material.

| VM           | ID  | Spec                          | Purpose                            |
| ------------ | --- | ----------------------------- | ---------------------------------- |
| truenas      | 101 | 2 CPU, 10GB RAM, 32GB         | NAS with HBA passthrough           |
| docker-host  | 102 | 6 CPU, 10GB RAM, 128GB        | Current Docker Compose services    |
| ai-dev-bgd   | 110 | 2 CPU, 4GB RAM, 150GB         | AI development sandbox             |
| unifi        | 111 | 2 CPU, 4GB RAM, 40GB          | UniFi OS Server                    |
| talos-prod-1 | 200 | 8 CPU, 12GB RAM, 100GB+128GB  | Kubernetes, created at cutover only |

Cloud-init template (`cloud_init.tftpl`) bootstraps the management user, installs qemu-guest-agent, and joins Tailscale.
TrueNAS and docker-host are managed with `prevent_destroy`; their pinned MAC addresses are supplied through sensitive Terraform variables in the ignored root `.envrc`. The Talos VM is gated by `enable_talos=false` by default; enabling it creates VM 200, stops docker-host, and moves the iGPU passthrough to Talos.

## Ansible

Configures provisioned hosts and the RB5009 with these primary roles:

| Role     | Purpose                                     |
| -------- | ------------------------------------------- |
| common   | SSH hardening, user management              |
| firewall | UFW rules                                   |
| media    | NFS mounts, media user/group (UID/GID 1215) |
| docker   | Docker engine installation                  |
| unifi    | UniFi OS Server install                     |
| routeros | RB5009 VLANs, DHCP, firewall, NAT, OOB port |

Secrets are managed via ansible-vault (`ansible/group_vars/secrets.yaml`).

RouterOS strict mode is the current steady state. `just routeros` maintains the
strict config; `just routeros-scaffold` is only for pre-strict bootstrap or
recovery work. See `ansible/roles/routeros/README.md`.

## Network Operations

Apply/verify order for a fresh rebuild is manual: root Terraform →
`just run unifi-controller` → `terraform/network` → `just routeros`.

## Docker Services

All services run behind Traefik on the shared `proxy` network (172.20.1.0/24) with TLS via Cloudflare DNS challenge. Services are managed by Portainer.

| Stack              | Services                                       |
| ------------------ | ---------------------------------------------- |
| **init**           | Traefik, Portainer, Pocket-ID (SSO)            |
| **arrs**           | Radarr, Sonarr, Lidarr, Prowlarr               |
| **downloads**      | qBittorrent, SABnzbd                           |
| **plex**           | Plex, Tautulli, Overseerr, Maintainerr, Kometa |
| **jellyfin**       | Jellyfin, Jellyseerr                           |
| **immich**         | Immich Server, Immich ML, PostgreSQL, Redis    |
| **owncloud**       | OwnCloud, MariaDB, Redis                       |
| **miniflux**       | Miniflux, PostgreSQL                           |
| **couchdb**        | CouchDB (Obsidian sync)                        |
| **komga**          | Komga (manga/comics)                           |
| **audiobookshelf** | Audiobookshelf                                 |
| **wallabag**       | Wallabag, MariaDB, Redis                       |
| **pinchflat**      | Pinchflat (YouTube archival)                   |
| **beszel**         | Infrastructure monitoring                      |

### Conventions

- Images pinned to SHA256 digests (managed by Renovate)
- `security_opt: no-new-privileges:true` on all containers
- `cap_drop: [ALL]` is rolled out service-by-service; see [docs/docker-hardening.md](docs/docker-hardening.md)
- Backend databases use isolated internal networks (e.g., `172.30.1.0/24`)
- GPU passthrough (`/dev/dri`) for Plex, Jellyfin, Immich transcoding
- NFS mounts at `/mnt/data`, `/mnt/music`, `/mnt/audiobooks`, etc.

## Kubernetes (Prepared)

Talos Linux single-node cluster managed by Flux CD. The manifests are prepared for cutover but are not live while `enable_talos=false`.

Prepared components include Cilium Gateway API, cert-manager, External Secrets backed by 1Password, OpenEBS LocalPV, static TrueNAS NFS PVs, VolSync/restic backups, Intel GPU device plugin, media/tool/auth app migrations, Immich without machine learning, and VictoriaMetrics monitoring. The rollout checklist lives in [docs/k8s-migration.md](docs/k8s-migration.md).

## CI/CD

- **Quality Gates**: Path-scoped static validation on pull requests (plus manual dispatch)
  - Actions workflow linting for `.github/workflows/**`
  - Nix flake check for `flake.nix` and `flake.lock`
  - Terraform format and validate for `terraform/**`
  - Docker Compose render checks for `docker/**`
  - Offline Kubernetes kustomize builds with kubeconform schema validation for `kubernetes/**`
  - Talos YAML parsing for `talos/**`
- **Renovate**: Automated dependency updates on schedule (GitHub Actions)
  - Config validation only runs when Renovate config changes
  - Semantic commits with `actions-renovate/` branch prefix
  - Auto-merge for digest updates only; major updates require Dependency Dashboard approval
  - Custom versioning for Linuxserver.io images
  - Manual approval required for Immich updates
