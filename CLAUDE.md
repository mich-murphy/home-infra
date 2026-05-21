# Claude Configuration

## Project Overview

Homelab infrastructure-as-code repository. All services currently run on Docker Compose (the `docker/` folder). The `kubernetes/` and `talos/` folders contain inactive configuration for a planned Kubernetes migration — see `docs/PRD.md` for details.

## Development Environment

- Nix flake provides all tooling — run `nix develop` or use direnv
- Task runner: `just` (see `justfile` for available commands)
- Nix formatter: `alejandra` (run `nix fmt`)

## Conventions

### General

- Conventional Commits: `fix(scope): msg`, `feat(scope): msg`, `chore(scope): msg`
- Scopes match folder names: `terraform`, `ansible`, `docker`, `kubernetes`, `talos`, `nix`, `deps`
- Do not add comments, docstrings, or type annotations to code you didn't change
- Format Nix files with `alejandra` before committing

### Terraform

- Working directory: `terraform/`
- Provider: telmate/proxmox for Proxmox VMs
- Secrets: 1Password via the `onepassword` provider — never hardcode credentials
- Always run `terraform plan` before `terraform apply`
- State files are gitignored — do not commit `.tfstate` files

### Ansible

- Working directory: `ansible/`
- Secrets stored in `ansible/group_vars/secrets.yaml` (ansible-vault encrypted)
- Vault password file: `ansible/.vaultpass` (gitignored)
- Roles: common, firewall, media, docker, ai-dev
- Target hosts: docker-host, ai-dev-bgd, ai-dev-bc

### Docker Compose

- Working directory: `docker/`
- Each service stack has its own subdirectory with `compose.yml`
- All services join the `proxy` network for Traefik routing
- Image tags must include SHA256 digest pins (Renovate manages updates)
- Always set `security_opt: no-new-privileges:true`
- Use Traefik labels for routing — pattern: `<service>.local.elmurphy.com`
- Backend databases get isolated internal networks with explicit subnets
- Use environment variables or `.env` files for secrets — never hardcode
- Media services use UID/GID 1215, other services use 1000

### Kubernetes (inactive)

- Working directory: `kubernetes/`
- Flux CD for GitOps deployment
- Infrastructure in `kubernetes/infrastructure/`, apps in `kubernetes/apps/`
- HelmRelease for infrastructure components, Helm charts for applications

### Nix

- `flake.nix` defines the dev shell — add new tooling here
- Supports x86_64-linux and aarch64-darwin
- Format with `alejandra` (available in dev shell)

## Key Paths

| Path                              | Purpose                       |
| --------------------------------- | ----------------------------- |
| `terraform/main.tf`               | VM definitions                |
| `terraform/cloud_init.tftpl`      | Cloud-init template           |
| `ansible/run.yaml`                | Main playbook                 |
| `ansible/group_vars/secrets.yaml` | Encrypted secrets             |
| `docker/init/compose.yml`         | Traefik, Portainer, Pocket-ID |
| `docker/init/traefik.yml`         | Traefik static config         |
| `docker/init/traefik-dynamic.yml` | Traefik dynamic routing       |
| `docs/PRD.md`                     | Kubernetes migration PRD      |
| `renovate.json`                   | Renovate dependency config    |

## Verification

- Terraform: `cd terraform && terraform validate && terraform plan`
- Ansible: `cd ansible && ansible-playbook run.yaml --syntax-check`
- Docker Compose: `cd docker/<stack> && docker compose config`
- Nix: `nix flake check && nix fmt -- --check .`
