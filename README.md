# home-infra

<!-- markdownlint-disable MD013 -->

Infrastructure-as-code for a single-server homelab running on Proxmox. Terraform
provisions infrastructure, Ansible configures hosts and the router, and Docker
Compose plus Portainer GitOps run application services.

The approved simplification scope and implementation order are recorded in
[docs/simplification-handover.md](docs/simplification-handover.md).

## Hardware

| Component   | Specification                                                      |
| ----------- | ------------------------------------------------------------------ |
| CPU         | Intel Core i7-14700 (20C/28T)                                      |
| RAM         | Designed for 64GB Micron DDR5 ECC; 32GB currently installed        |
| Motherboard | Supermicro X13SAE                                                  |
| Boot disk   | 250GB NVMe                                                         |
| VM storage  | 2x 1TB Samsung EVO NVMe (ZFS mirror, Proxmox-managed)              |
| Data SSDs   | 2x Kingston DC600M 960GB (ZFS special vdev mirror, TrueNAS HBA)    |
| Data HDDs   | 2x Seagate IronWolf 10TB (ZFS mirror, TrueNAS via HBA)             |

TrueNAS pool layout, dataset tuning, and the storage change plan are
documented in [docs/truenas-storage.md](docs/truenas-storage.md).
One faulty 32GB module has been removed. Current VM sizing and the intentionally
stopped UniFi controller reflect the installed 32GB constraint.

## Architecture

```text
Proxmox v9.1.6 (hypervisor)
├── TrueNAS VM (SRV VLAN) ─── NFS shares (media, downloads, bulk storage)
├── Docker Host VM (Ubuntu 24.04) ─── live services via Docker Compose
│   └── Traefik → *.local.elmurphy.com (TLS via Cloudflare ACME)
├── UniFi OS Server VM (MGMT) ─── cold controller infrastructure (off normally)
├── ai-dev VM (DMZ) ─── Isolated AI development sandbox
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
| DMZ | RB5009 `ether2` / Proxmox `vmbr1` | Isolated ai-dev VM (`10.77.99.0/24`) |
| OOB | RB5009 `ether7` | Break-glass router access (`10.66.0.0/30`) |

The server has two ethernet ports: `eno2`/`vmbr0` trunks MGMT/SRV to RB5009
`ether3`, while `eno1`/`vmbr1` is the untagged DMZ uplink to RB5009 `ether2`.
The UniFi U6-Pro AP is adopted in the controller. The three managed WLANs are
attached to the default `All APs` group and mapped to the DFLT/KDS/GST
VLAN-only networks. The ai-dev VM is isolated on the physical DMZ
(`10.77.99.0/24`), protected by host nftables default-deny input rules, and
controlled-output rules, and further scoped by an external Tailscale policy
managed outside this repo.
Its mobile workflow and deployment checks are documented in
[docs/ai-dev.md](docs/ai-dev.md).

## Repository Structure

```text
.
├── terraform/       # Proxmox VM provisioning
├── ansible/         # Host, bootstrap-stack, and RouterOS configuration
├── docker/          # Bootstrap and Portainer-owned Compose definitions
├── network/         # Shared non-secret VLAN, subnet, and address inventory
├── docs/            # Documentation
├── flake.nix        # Nix dev shell
└── justfile         # Task runner
```

## Prerequisites

- [Nix](https://nixos.org/) with flakes enabled (provides all tooling via `flake.nix`)
- [direnv](https://direnv.net/) (auto-loads the Nix dev shell)

The dev shell includes Terraform, Ansible, Docker Compose, ShellCheck, `just`,
Actionlint, and Alejandra.

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

| VM | ID | Spec | Purpose |
| --- | --- | --- | --- |
| truenas | 101 | 2 CPU, 10GB RAM, 32GB | NAS with HBA passthrough |
| docker-host | 102 | 6 CPU, 8GB RAM, 128GB | Docker Compose services |
| ai-dev | 110 | 4 CPU, 5GB RAM, 150GB | AI development sandbox |
| unifi-controller | 111 | 2 CPU, 4GB max / 2GB min, 40GB | Cold UniFi OS Server infrastructure |

Cloud-init template (`cloud_init.tftpl`) bootstraps the management user, installs qemu-guest-agent, and joins Tailscale.
TrueNAS, docker-host, ai-dev, and the UniFi controller use `prevent_destroy`.
Pinned MAC addresses are supplied through sensitive Terraform variables in the
ignored root `.envrc`. The UniFi controller intentionally has `on_boot = false`
and `started = false` while the server has 32GB installed; this is not drift.
Start VM 111 before running the UniFi Ansible role or any `terraform/network`
plan/apply, and stop it again after controller-dependent work is complete.
Template build usage and recovery are documented in
[docs/proxmox-templates.md](docs/proxmox-templates.md).

## Ansible

Configures provisioned hosts and the RB5009 with these primary roles:

| Role        | Purpose                                                     |
| ----------- | ----------------------------------------------------------- |
| common      | SSH hardening, user management                              |
| ai-dev      | Host provisioning and Home Manager activation               |
| firewall    | Reusable UFW policy                                         |
| docker-host | Docker, NFS, published-port policy, bootstrap deployment    |
| unifi       | UniFi OS Server install                                     |
| routeros    | RB5009 VLANs, DHCP, firewall, NAT, OOB port                 |

Secrets are managed via ansible-vault (`ansible/group_vars/secrets.yaml`).

RouterOS strict mode is the current steady state. `just routeros` maintains the
strict config; `just routeros-scaffold` is only for pre-strict bootstrap or
recovery work. See `ansible/roles/routeros/README.md`.

The `docker-host` role installs Docker Engine and Compose from Docker's stable
Ubuntu repository, prepares NFS storage, enforces published-port policy, and
deploys the Ansible-owned bootstrap stack.

## Network Operations

Apply/verify order for a fresh rebuild is manual: root Terraform → start VM 111
→ `just run unifi-controller` → `terraform/network` → `just routeros` → stop
VM 111. Shared non-secret network facts live in `network/inventory.yaml` and are
consumed by both Terraform roots and the RouterOS play.

## Docker Services

All services run behind Traefik on the shared `proxy` network with TLS via the
Cloudflare DNS challenge. Ansible owns the `/srv/init` bootstrap stack because
Traefik and Portainer must exist before Portainer can operate. Portainer GitOps
owns every application stack in `docker/portainer-stacks.yaml`. The inventory,
Git settings, drift check, and removal order are documented in
[docs/docker-deployment.md](docs/docker-deployment.md).

| Stack                | Services                                       |
| -------------------- | ---------------------------------------------- |
| **init**             | Traefik, Portainer, Pocket-ID (SSO)            |
| **arrs**             | Radarr, Sonarr, Lidarr, Prowlarr               |
| **downloads**        | qBittorrent, SABnzbd                           |
| **plex**             | Plex, Tautulli, Seerr, Maintainerr, Kometa     |
| **jellyfin**         | Jellyfin, Jellyseerr                           |
| **immich**           | Immich Server, Immich ML, PostgreSQL, Redis    |
| **nextcloud**        | Nextcloud, PostgreSQL, Redis, cron, Collabora  |
| **miniflux**         | Miniflux, PostgreSQL                           |
| **couchdb**          | CouchDB (Obsidian sync)                        |
| **audiobookshelf**   | Audiobookshelf                                 |
| **wallabag**         | Wallabag, MariaDB, Redis                       |
| **pinchflat**        | Pinchflat (YouTube archival)                   |
| **beszel**           | Infrastructure monitoring                      |

### Conventions

- Images pinned to SHA256 digests (managed by Renovate)
- `security_opt: no-new-privileges:true` on all containers
- `cap_drop: [ALL]` by default with documented retained init capabilities and exceptions; see [docs/docker-hardening.md](docs/docker-hardening.md)
- Backend databases use isolated Docker-allocated internal networks
- GPU passthrough (`/dev/dri`) for Plex, Jellyfin, Immich transcoding
- NFS mounts at `/mnt/data`, `/mnt/music`, `/mnt/audiobooks`, etc.

## CI/CD

- **Quality Gates**: Path-scoped static validation on pull requests (plus manual dispatch)
  - Actions workflow linting for `.github/workflows/**`
  - Nix flake check for `flake.nix` and `flake.lock`
  - Terraform format and validate for `terraform/**`
  - ShellCheck for Proxmox template scripts
  - Docker Compose render checks for `docker/**`
  - Ansible lint plus syntax-check of the complete `ansible/run.yaml` playbook
- **Renovate**: Automated dependency updates on schedule (GitHub Actions)
  - Config validation only runs when Renovate config changes
  - Semantic commits with `actions-renovate/` branch prefix
  - Auto-merge for digest updates only; major updates require Dependency Dashboard approval
  - Custom versioning for Linuxserver.io images
  - Manual approval required for Immich updates
