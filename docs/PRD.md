# Product Requirements Document: Homelab Kubernetes Migration

## Context

The homelab currently runs all application services via Docker Compose on a single Ubuntu 24.04 VM managed by Portainer. The primary goal over the next 6-12 months is to migrate all services to a Kubernetes cluster running Talos Linux, managed declaratively via Flux CD and GitOps. A critical blocker exists: the Proxmox host hangs within minutes of the first Flux CD deployment on the cluster. This issue must be resolved before any migration can proceed. There is no hard deadline — Docker Compose is stable and functional as a fallback.

---

## 1. Non-Negotiable Requirements

- **Data integrity**: Zero data loss during migration. All databases, media libraries, and application state must be preserved.
- **Reproducibility**: All cluster and application configuration must be declarative, versioned in git, and reproducible from scratch.
- **Stability first**: The cluster must be proven stable under load before any production service is migrated.

---

## 2. Stability Investigation (Phase 0 — Prerequisite)

### Problem
Proxmox host hangs within minutes of the first Flux CD deployment. A fresh Talos cluster without Flux deployments runs fine. No useful logs from either the K8s cluster or Proxmox host.

### Key clue
The instability has **not** been tested with manual `kubectl apply` deployments — only via Flux CD. This is the most important test to run next.

### Investigation plan
1. **Isolate Flux CD**: Deploy a minimal workload (e.g., linkding) via `kubectl apply` instead of Flux. Run for 30+ minutes under normal use. If stable, Flux's reconciliation loop or resource usage is the likely culprit.
2. **Isolate Flux components**: If manual deploys are stable, add Flux components one at a time (source-controller first, then kustomize-controller, then helm-controller) to identify which controller triggers the issue.
3. **Monitor host-level resources during deployment**: Use `dmesg -w`, `htop`, `zpool iostat`, and `iostat` on the Proxmox host while deploying to catch resource exhaustion, OOM kills, or ZFS issues at the moment of hang.
4. **Check NVMe health**: Run `smartctl` on the Proxmox NVMe drives — intermittent NVMe hangs can freeze the entire host and produce no logs.
5. **Test with reduced VM resources**: Try the current 8c/12GB allocation to rule out resource contention with other VMs / ZFS ARC.

### Success criteria
- Cluster runs stable for 24+ hours with at least one application deployed.
- No Proxmox host hangs during the test period.

---

## 3. Cluster Architecture

### Topology
- **Single-node** Talos Linux control plane (scheduling workloads on control plane)
- VM hosted on Proxmox

### VM Resources
- **16 CPU cores / 24GB RAM** (scaled up from current 8c/12GB)
- Must leave sufficient RAM for Proxmox host, ZFS ARC, TrueNAS VM, and Docker host (during parallel operation)
- 2x disks: 100GB boot + 128GB data (current config, may need adjustment)

### Networking
- **Dual-homed VM**: NICs on both Skynet (trusted) and Skynet-DMZ (internet-exposed) VLANs
- Managed via Proxmox with the two physical ethernet ports mapped to respective VLANs

### Domain
- Migrating from `*.local.elmurphy.com` to `catalyst-labs.tech`
- Domain pattern TBD (e.g., `*.catalyst-labs.tech` or `app.catalyst-labs.tech`)

---

## 4. Core Infrastructure Components

All deployed via Flux CD in the `kubernetes/` folder. Infrastructure is deployed before applications.

| Component | Purpose | Notes |
|---|---|---|
| **Cilium** | CNI, ingress (Gateway API), DNS, network policies | Minimize external dependencies — use Cilium for networking, ingress, and service mesh where possible |
| **cert-manager** | TLS certificates via Let's Encrypt | Automated certificate lifecycle |
| **External Secrets Operator** | Secrets sync from 1Password | Already partially configured |
| **OpenEBS** | Local NVMe-backed storage for SQLite/databases | Recommended by Talos |
| **NFS provisioner** | TrueNAS NFS mounts for media/bulk data | For media libraries, downloads, etc. |
| **Prometheus + Grafana** | Monitoring and observability | Full metrics stack with dashboards |
| **Cloudflare Tunnel** | Public exposure for selected services | Replaces direct DMZ exposure for public services |
| **Tailscale** | Private access for internal services | VPN overlay for remote access |
| **Actions Runner Controller** | Self-hosted GitHub Actions runners | Already have partial ARC config |

---

## 5. Storage Strategy

- **OpenEBS local storage**: For applications with SQLite databases or performance-sensitive workloads (e.g., Immich, Nextcloud, Linkding, FreshRSS, Miniflux)
- **NFS from TrueNAS**: For media libraries, downloads, and bulk data (e.g., Plex/Jellyfin media, Sonarr/Radarr downloads, audiobooks, comics)
- Storage class definitions should make it clear which to use for each workload type

---

## 6. Network Segmentation

### Existing VLAN structure (Ubiquiti Dream Machine)
| VLAN | Purpose | Isolation |
|---|---|---|
| Skynet | Trusted devices (laptop, server) | Can access IoT, Jnr |
| Skynet - IoT | Smart home devices | Response-only to Skynet |
| Skynet - Work | Work devices (MAC whitelist) | Fully isolated |
| Skynet - Jnr | Kids devices (content + time filtering) | Limited access |
| Skynet - Guest | Visitors | Limited access |
| Skynet - DMZ | Internet-exposed services (ethernet) | Fully isolated |

### K8s network strategy
- K8s VM dual-homed on Skynet + Skynet-DMZ
- Cilium network policies for pod-level segmentation within the cluster
- Public-facing services route through Cloudflare Tunnel (DMZ NIC)
- Internal services accessible via Tailscale or Skynet LAN

---

## 7. Kubernetes Manifest Structure

All config lives in `kubernetes/` folder.

```
kubernetes/
├── clusters/prod/          # Flux CD bootstrap and entrypoints
│   ├── flux-system/
│   ├── infrastructure.yaml # Points to infrastructure/
│   └── apps.yaml           # Points to apps/
├── infrastructure/
│   ├── controllers/        # Kustomize overlays for infra Helm charts
│   │   ├── cilium/
│   │   ├── cert-manager/
│   │   ├── external-secrets/
│   │   ├── openebs/
│   │   ├── prometheus/
│   │   ├── grafana/
│   │   ├── cloudflare-tunnel/
│   │   └── actions-runner-controller/
│   └── configs/            # Cluster-wide configs (storage classes, secrets stores)
│       ├── external-secrets/
│       └── storage-classes/
└── apps/
    └── default/            # Per-app Helm charts or plain manifests
        ├── linkding/
        ├── freshrss/
        ├── miniflux/
        ├── immich/
        ├── jellyfin/
        ├── plex/
        ├── nextcloud/
        └── ...
```

- **Infrastructure**: Kustomize overlays wrapping upstream Helm charts (HelmRelease via Flux)
- **Applications**: Individual Helm charts per app for maximum flexibility
- Keep the structure flat and scannable

---

## 8. Resource Limits

- Define `ResourceQuota` and `LimitRange` for namespaces
- Every pod must have resource requests and limits defined
- Reserve headroom for Flux controllers and system components (~2 cores, 2GB RAM)
- Target utilization: ~70% of allocated VM resources under normal load

---

## 9. Migration Strategy

### Approach: Parallel operation with gradual cutover

1. **Phase 0**: Resolve cluster stability (see Section 2)
2. **Phase 1**: Deploy core infrastructure (Cilium, cert-manager, External Secrets, storage, monitoring)
3. **Phase 2**: Migrate low-risk stateless or simple apps (Linkding, FreshRSS, Miniflux)
4. **Phase 3**: Migrate complex stateful apps (Immich, Nextcloud, databases)
5. **Phase 4**: Migrate media stack (Plex, Jellyfin, Sonarr, Radarr, etc.)
6. **Phase 5**: Decommission Docker host VM, reclaim resources

### Per-service migration checklist
- [ ] K8s manifest / Helm chart written and tested
- [ ] Secrets migrated to 1Password / External Secrets
- [ ] Persistent data migrated or NFS mount configured
- [ ] DNS updated to point to K8s ingress
- [ ] Verified working in K8s for 48+ hours
- [ ] Docker Compose service stopped
- [ ] Docker data backed up and archived

### Docker Compose stack remains running throughout until each service is individually validated in K8s.

---

## 10. Backup & Disaster Recovery

This needs further planning. Initial considerations:
- GitOps covers all declarative config (cluster + app manifests)
- TrueNAS ZFS snapshots cover NFS-backed data
- OpenEBS local volumes need a backup strategy (Velero, restic, or scheduled snapshots)
- Database dumps (CouchDB, any PostgreSQL) should be scheduled and stored on NFS
- Document full cluster rebuild procedure from scratch

---

## 11. Key Files to Modify

| File | Change |
|---|---|
| `terraform/main.tf` | Update K8s VM resources (16c/24GB), add second NIC for DMZ |
| `terraform/variables.tf` | New variables for K8s VM sizing |
| `talos/controlplane-patch.yaml` | Update for dual-NIC, resource adjustments |
| `kubernetes/clusters/prod/` | Update Flux bootstrap config |
| `kubernetes/infrastructure/` | Add new controllers (cert-manager, prometheus, grafana, cloudflare-tunnel, ARC) |
| `kubernetes/apps/` | Per-app Helm charts for each migrated service |
| `flake.nix` | Add any new tooling (e.g., cilium CLI, velero) |

---

## 12. Open Questions

1. **Domain structure**: What subdomain pattern for `catalyst-labs.tech`? (e.g., `app.catalyst-labs.tech` vs `*.catalyst-labs.tech`)
2. **Backup strategy**: Velero vs simpler restic-based backup for OpenEBS volumes
3. **Flux CD stability root cause**: Manual kubectl test needed before proceeding
4. **RAM budget**: Need to audit current RAM usage across all Proxmox VMs to confirm 24GB is feasible
5. **Cilium Gateway API maturity**: Verify Cilium's Gateway API implementation covers all needed ingress features (TLS termination, path routing, auth middleware)

---

## 13. Execution with Claude Code Agents

This project has a team of Claude Code agents and skills configured to execute the migration. This section documents how to use them effectively.

### Agent Team

Agents are defined in `.claude/agents/` and specialise in different domains of this project.

| Agent | Domain | Model | Invocation |
|---|---|---|---|
| **lead** | Orchestration, architecture | opus | `@lead` or `claude --agent lead` |
| **docker** | Docker Compose services | sonnet | `@docker` or `claude --agent docker` |
| **kubernetes** | K8s, Flux CD, Helm, Talos | sonnet | `@kubernetes` or `claude --agent kubernetes` |
| **terraform** | Proxmox VM provisioning | sonnet | `@terraform` or `claude --agent terraform` |
| **ansible** | Host configuration | sonnet | `@ansible` or `claude --agent ansible` |
| **network** | Ingress, TLS, DNS, policies | sonnet | `@network` or `claude --agent network` |
| **platform** | Nix, CI/CD, monitoring | sonnet | `@platform` or `claude --agent platform` |

The **lead** agent coordinates the team. It can spawn all specialist agents and delegates implementation work to them. Use it for complex multi-domain tasks.

### Skills (Slash Commands)

Skills are defined in `.claude/skills/` and provide structured workflows for common operations.

| Skill | Purpose | Example |
|---|---|---|
| `/add-docker-service <name>` | Add a new Docker Compose service | `/add-docker-service homepage` |
| `/terraform-plan` | Validate and plan Terraform changes | `/terraform-plan` |
| `/ansible-run <host>` | Run Ansible against a host (manual only) | `/ansible-run docker-host` |
| `/add-k8s-app <name>` | Add a K8s application Helm chart | `/add-k8s-app linkding` |
| `/add-k8s-infra <name>` | Add a K8s infrastructure controller | `/add-k8s-infra cert-manager` |
| `/migrate-to-k8s <name>` | Migrate a Docker service to K8s | `/migrate-to-k8s freshrss` |
| `/nix-update` | Update the Nix dev shell | `/nix-update` |

### How to Use: Phase-by-Phase

#### Phase 0 — Stability Investigation

This phase is primarily manual (SSH into Proxmox, observe hardware). Claude agents assist with preparation and analysis.

```
# Use the terraform agent to update VM resources
@terraform Scale the talos-prod-1 VM to 16 cores and 24GB RAM, and add a second NIC for the DMZ VLAN

# Use the kubernetes agent to prepare a minimal test manifest
@kubernetes Create a standalone linkding deployment manifest I can apply with kubectl (not Flux) for stability testing

# After manual testing, use the lead to analyse results
@lead I've confirmed the cluster is stable with kubectl apply but hangs with Flux. Help me design an isolation test for Flux components.
```

#### Phase 1 — Core Infrastructure

Deploy infrastructure controllers to the stable cluster.

```
# Use the lead for the full phase — it will delegate to specialists
@lead Deploy Phase 1 core infrastructure: Cilium, cert-manager, External Secrets, OpenEBS, NFS provisioner, and Prometheus/Grafana. Refer to the PRD for component details.

# Or invoke individual agents for specific components
@kubernetes /add-k8s-infra cert-manager
@kubernetes /add-k8s-infra openebs
@network Configure Cilium Gateway API with cert-manager integration for TLS on catalyst-labs.tech
@platform /nix-update — add cilium-cli and velero to the dev shell
```

#### Phase 2 — Migrate Simple Apps

Start with low-risk stateless applications.

```
# Migrate one service at a time
@kubernetes /migrate-to-k8s linkding
@kubernetes /migrate-to-k8s freshrss
@kubernetes /migrate-to-k8s miniflux

# Or use the lead to coordinate multiple migrations
@lead Migrate linkding, freshrss, and miniflux from Docker to Kubernetes. Follow the per-service checklist in the PRD.
```

#### Phase 3 — Migrate Stateful Apps

Complex apps with databases need extra care.

```
# The lead coordinates cross-domain work
@lead Migrate Immich to Kubernetes. This has PostgreSQL with pgvector, Redis, ML service, and GPU passthrough. Ensure data migration is planned before any changes.

# Review storage and networking specifically
@network Design Cilium network policies for Immich (isolate database, expose only the server)
```

#### Phase 4 — Migrate Media Stack

```
@lead Migrate the media stack (Plex, Jellyfin, Sonarr, Radarr, Lidarr, Prowlarr, qBittorrent, SABnzbd) to Kubernetes. All use NFS for media storage and some need GPU passthrough.
```

#### Phase 5 — Decommission Docker

```
@lead All services are validated in K8s. Plan the decommission of the Docker host VM. Update Terraform to remove it, clean up Ansible config, and archive the docker/ folder.
```

### Choosing the Right Invocation Method

| Scenario | Method | Why |
|---|---|---|
| Complex task spanning multiple domains | `@lead <task>` | Lead decomposes and delegates across the team |
| Single-domain implementation | `@<specialist> <task>` | Direct access to the right expert |
| Structured workflow (new service, migration) | `/<skill> <args>` | Follows established conventions step by step |
| Start an entire session focused on one area | `claude --agent <name>` | Agent's system prompt replaces default, full session context |
| Quick one-off in a script | `claude -p "<prompt>" --agent <name>` | Non-interactive headless execution |

### Parallel Work with Worktrees

When multiple agents need to make changes to different parts of the repo simultaneously, use git worktrees to avoid conflicts:

```bash
# Start parallel sessions in isolated worktrees
claude --worktree phase1-cilium --agent kubernetes
claude --worktree phase1-cert-manager --agent kubernetes
claude --worktree phase1-monitoring --agent platform
```

Each worktree gets its own branch. Merge results back to main when validated. Add `.claude/worktrees/` to `.gitignore`.

### Prompt Writing Tips

**Be specific about the PRD phase and section:**
```
# Good — references PRD, names the phase, states the goal
@lead Implement PRD Phase 1. Start with Cilium and cert-manager as described in Section 4. Use the existing kubernetes/infrastructure/ structure from Section 7.

# Bad — vague, no context
Set up Kubernetes
```

**Include constraints and non-negotiables:**
```
# Good — states what matters
@kubernetes Create the Immich Helm chart. It needs: GPU passthrough for ML, OpenEBS storage for PostgreSQL (SQLite-like performance needs), NFS for photo library at /mnt/data/media/photos. Resource limits are mandatory per PRD Section 8.

# Bad — missing critical details
@kubernetes Add Immich to K8s
```

**Use the lead for ambiguous or cross-cutting work:**
```
# Good — the lead will figure out which agents to involve
@lead The domain is changing from local.elmurphy.com to catalyst-labs.tech. Update all configuration across Docker (Traefik), Kubernetes (Cilium Gateway API, cert-manager), and Terraform (cloud-init).
```

### Documentation References

| Topic | URL |
|---|---|
| Custom agents | https://code.claude.com/docs/en/sub-agents.md |
| Agent teams | https://code.claude.com/docs/en/agent-teams.md |
| Skills | https://code.claude.com/docs/en/skills.md |
| Headless / automation | https://code.claude.com/docs/en/headless.md |
| CLI reference (`--agent`, `-p`, etc.) | https://code.claude.com/docs/en/cli-reference.md |
| Git worktrees for parallel work | https://code.claude.com/docs/en/common-workflows.md |
| Permissions and tool restrictions | https://code.claude.com/docs/en/permissions.md |
| Hooks (automated behaviours) | https://code.claude.com/docs/en/hooks-guide.md |
| Model selection | https://code.claude.com/docs/en/model-config.md |
| GitHub Actions integration | https://code.claude.com/docs/en/github-actions.md |
| Best practices | https://code.claude.com/docs/en/best-practices.md |
