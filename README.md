# home-infra

<!-- markdownlint-disable MD013 -->

Infrastructure-as-code for a single-server homelab running on Proxmox. Terraform
provisions infrastructure, Ansible configures hosts and the router, and Docker
Compose plus Portainer GitOps run application services.

## Hardware

32GB ECC RAM is installed of the 64GB the board is designed for, which is what
constrains VM sizing. TrueNAS pool layout and dataset tuning are documented in
[docs/truenas-storage.md](docs/truenas-storage.md).

## Architecture

```text
Proxmox VE (hypervisor)
├── TrueNAS VM (SRV VLAN) ─── NFS shares (media, downloads, bulk storage)
├── Docker Host VM (Ubuntu 24.04) ─── live services via Docker Compose
│   └── Traefik → per-service TLS hostnames (Cloudflare ACME)
├── UniFi OS Server VM (MGMT) ─── cold controller infrastructure (off normally)
├── ai-dev VM (DMZ) ─── Isolated AI development sandbox
```

### Network (MikroTik router + UniFi AP)

Routing, DHCP, firewall policy and inter-VLAN isolation live on the MikroTik
router and are managed by the Ansible `routeros` role. The UniFi controller runs
as a dedicated Proxmox VM (`unifi-controller`, VMID 111) and the AP/WLAN objects
are managed through the UniFi controller API (`terraform/network`).

| Network | Purpose |
| --- | --- |
| MGMT | Wired-only management plane |
| SRV | TrueNAS + docker-host services |
| DFLT | Main wireless clients |
| KDS | Kids wireless clients with filtered DNS |
| GST | Guest wireless clients with UniFi L2 isolation |
| DMZ | Isolated ai-dev VM |
| OOB | Break-glass router access |

VLAN IDs, subnets, addresses, and the physical port map are in
`network/inventory.yaml` and `ansible/group_vars/routeros.yaml`. The server
trunks MGMT/SRV over one ethernet port and carries the untagged DMZ uplink on
the other. The UniFi U6-Pro AP is adopted in the controller. The three managed WLANs are
attached to the default `All APs` group and mapped to the DFLT/KDS/GST
VLAN-only networks. The ai-dev VM is isolated on the physical DMZ,
protected by host nftables default-deny input rules, and
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
Terraform state is secret-bearing. Run Terraform through the `just` recipes so local state and generated cloud-init files are created with a restrictive umask.

| VM | ID | Purpose |
| --- | --- | --- |
| truenas | 101 | NAS with HBA passthrough |
| docker-host | 102 | Docker Compose services |
| ai-dev | 110 | AI development sandbox |
| unifi-controller | 111 | Cold UniFi OS Server infrastructure |

`terraform/main.tf` is authoritative for each VM's CPU, memory and disk.

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

Configures provisioned hosts and the router with these primary roles:

| Role        | Purpose                                                     |
| ----------- | ----------------------------------------------------------- |
| common      | SSH hardening, user management                              |
| ai-dev      | Host provisioning and Home Manager activation               |
| firewall    | Reusable UFW policy                                         |
| docker-host | Docker, NFS, published-port policy, bootstrap deployment    |
| unifi       | UniFi OS Server install                                     |
| routeros    | Router VLANs, DHCP, firewall, NAT, OOB port                 |

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
[docs/docker-deployment.md](docs/docker-deployment.md). Radarr and Sonarr
custom formats and quality profiles are managed as code by Recyclarr; see
[docs/recyclarr.md](docs/recyclarr.md); the same stack runs Checkrr, which scans
for corrupt files and re-downloads them via Radarr/Sonarr
([docs/checkrr.md](docs/checkrr.md)). Library identity and metadata provider
settings are described in [docs/media-metadata.md](docs/media-metadata.md).

| Stack                | Services                                       |
| -------------------- | ---------------------------------------------- |
| **init**             | Traefik, Portainer, Pocket-ID (SSO)            |
| **arrs**             | Radarr, Sonarr, Lidarr, Prowlarr               |
| **recyclarr**        | Recyclarr (TRaSH sync), Checkrr (integrity)    |
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
| **jellyplex-watched** | Jellyfin/Plex watched-state sync              |

### Conventions

- Images pinned to SHA256 digests (managed by Renovate)
- `security_opt: no-new-privileges:true` on all containers
- `cap_drop: [ALL]` by default with documented retained init capabilities and exceptions; see [docs/docker-hardening.md](docs/docker-hardening.md)
- Backend databases use isolated Docker-allocated internal networks
- GPU passthrough (`/dev/dri`) for Plex, Jellyfin, Immich transcoding
- NFS mounts at `/mnt/data`, `/mnt/music`, `/mnt/audiobooks`, etc.

## CI/CD

- **Quality gates**: path-scoped static validation on pull requests. Each
  workflow under `.github/workflows/` declares the paths it guards and the
  checks it runs.
- **Renovate**: automated dependency updates on a schedule. `renovate.json`
  carries a `description` on every rule, including which updates auto-merge and
  which need Dependency Dashboard approval.
