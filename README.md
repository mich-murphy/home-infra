# home-infra

Infrastructure-as-code for a single-server homelab running on Proxmox. Manages VM provisioning, host configuration, and containerised application services.

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
├── TrueNAS VM ─── NFS shares (media, downloads, bulk storage)
├── Docker Host VM (Ubuntu 24.04) ─── 18+ services via Docker Compose
│   └── Traefik → *.local.elmurphy.com (TLS via Cloudflare ACME)
└── [Talos K8s VM] ─── Inactive, pending stability investigation
```

### Network (MikroTik RB5009 + UniFi AP)

| VLAN / subnet       | Purpose                                      |
| ------------------- | -------------------------------------------- |
| MGMT / 10.77.1.0/24 | Wired management only: Proxmox, IPMI, UniFi  |
| SRV / 10.77.20.0/24 | Service workloads, including `docker-host`   |
| DFLT / 10.77.30.0/24 | Trusted wireless clients                     |
| KDS / 10.77.50.0/24 | Kids devices with filtered DNS controls      |
| GST / 10.77.60.0/24 | Guest wireless clients                       |
| DMZ / 10.77.99.0/24 | Isolated untrusted/sandbox workloads         |

The server has two ethernet ports: `vmbr0` is the MGMT native / production VLAN trunk,
and `vmbr1` is the untagged physical DMZ. Service VMs use explicit VLAN tags rather
than landing on MGMT by default.

## Repository Structure

```
.
├── terraform/       # Proxmox VM provisioning
├── ansible/         # Host configuration (Docker host, game server)
├── docker/          # Docker Compose services (active)
├── kubernetes/      # Flux CD manifests (inactive)
├── talos/           # Talos Linux cluster config (inactive)
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

# Ansible
just reqs                   # install galaxy requirements
just run docker-host        # run playbook against a host
just edit                   # edit encrypted vault secrets
```

## Terraform

Provisions VMs on Proxmox using the [telmate/proxmox](https://registry.terraform.io/providers/Telmate/proxmox) provider. Secrets sourced from 1Password via the `onepassword` provider.
Run Terraform through the `just` recipes so local state and generated cloud-init files are created with a restrictive umask. Terraform state is secret-bearing because provider data includes Proxmox credentials, WLAN PSKs, and bootstrap auth material.

| VM           | ID  | Spec                         | Purpose                 |
| ------------ | --- | ---------------------------- | ----------------------- |
| docker-host  | 102 | 4 CPU, 12GB RAM, 128GB       | Docker Compose services |
| talos-prod-1 | 200 | 8 CPU, 12GB RAM, 100GB+128GB | Kubernetes (inactive)   |

Cloud-init template (`cloud_init.tftpl`) bootstraps the ansible user, installs qemu-guest-agent, Tailscale, and Docker.

## Ansible

Configures provisioned VMs with four roles:

| Role     | Purpose                                     |
| -------- | ------------------------------------------- |
| common   | SSH hardening, user management              |
| firewall | UFW rules                                   |
| media    | NFS mounts, media user/group (UID/GID 1215) |
| docker   | Docker engine installation                  |

Secrets are managed via ansible-vault (`ansible/group_vars/secrets.yaml`).

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
| **nextcloud**      | Nextcloud, PostgreSQL, Redis                   |
| **owncloud**       | OwnCloud, MariaDB, Redis                       |
| **miniflux**       | Miniflux, PostgreSQL                           |
| **couchdb**        | CouchDB (Obsidian sync)                        |
| **freshrss**       | FreshRSS                                       |
| **komga**          | Komga (manga/comics)                           |
| **audiobookshelf** | Audiobookshelf                                 |
| **wallabag**       | Wallabag, MariaDB, Redis                       |
| **pinchflat**      | Pinchflat (YouTube archival)                   |
| **minecraft**      | Crafty (Minecraft server manager)              |
| **beszel**         | Infrastructure monitoring                      |

### Conventions

- Images pinned to SHA256 digests (managed by Renovate)
- `security_opt: no-new-privileges:true` on all containers
- Backend databases use isolated internal networks (e.g., `172.30.1.0/24`)
- GPU passthrough (`/dev/dri`) for Plex, Jellyfin, Immich transcoding
- NFS mounts at `/mnt/data`, `/mnt/music`, `/mnt/audiobooks`, etc.

## Kubernetes (Inactive)

Talos Linux single-node cluster managed by Flux CD. Currently offline due to unresolved Proxmox host instability when Flux deploys workloads. See [docs/PRD.md](docs/PRD.md) for the migration plan.

## CI/CD

- **Renovate**: Automated dependency updates on schedule (GitHub Actions)
  - Semantic commits with `actions-renovate/` branch prefix
  - Auto-merge for minor/patch (non-zero versions)
  - Custom versioning for Linuxserver.io images
  - Manual approval required for Immich updates
