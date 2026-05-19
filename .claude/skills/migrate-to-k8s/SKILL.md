---
name: migrate-to-k8s
description: Migrate an existing Docker Compose service to Kubernetes. Use when moving a service from the Docker stack to the K8s cluster.
argument-hint: [service-name]
---

# Migrate Docker Service to Kubernetes

Migrate the $ARGUMENTS service from Docker Compose to Kubernetes.

## Context

Read `docs/PRD.md` for the full migration plan and per-service checklist.

## Steps

1. Read the existing Docker Compose file: `docker/$ARGUMENTS/compose.yml`
2. Identify:
   - Container image and tag
   - Environment variables and secrets
   - Volume mounts (distinguish NFS vs local data)
   - Network requirements (internal backend networks, exposed ports)
   - Health checks
   - Resource usage patterns (GPU, high memory, etc.)
3. Create the Kubernetes manifests in `kubernetes/apps/default/$ARGUMENTS/`:
   - Use the `/add-k8s-app` skill patterns as reference
   - Map Docker environment variables to K8s `env` or `ExternalSecret` resources
   - Map Docker volumes:
     - Named volumes with SQLite → `openebs-hostpath` PVC
     - NFS mounts → NFS PV/PVC pointing to TrueNAS
     - Config file mounts → ConfigMap
   - Map Traefik labels → Cilium Gateway API `HTTPRoute`
   - Map Docker health checks → K8s `livenessProbe` / `readinessProbe`
   - If the service had an isolated backend network, use K8s `NetworkPolicy` instead
   - Preserve the same UID/GID via `securityContext`
4. If the service has a database sidecar (PostgreSQL, MariaDB, Redis):
   - Deploy as a separate `StatefulSet` or use an operator
   - Ensure data migration plan is documented
5. Add migration notes as comments in the K8s manifests for data migration steps
6. Validate: `kubectl apply --dry-run=client -f kubernetes/apps/default/$ARGUMENTS/`
7. Do NOT remove the Docker Compose file — it stays until the K8s service is validated in production
