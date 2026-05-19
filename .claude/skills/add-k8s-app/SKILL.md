---
name: add-k8s-app
description: Add a new application to the Kubernetes cluster configuration. Use when creating Helm charts or manifests for a new K8s workload.
argument-hint: [app-name]
---

# Add Kubernetes Application

Add a new application called $ARGUMENTS to the Kubernetes Flux CD configuration.

## Context

Read `docs/PRD.md` for the full migration plan. The Kubernetes cluster is currently inactive but configuration should be prepared for when it is operational.

## Steps

1. Read existing apps in `kubernetes/apps/default/` for reference patterns
2. Read `kubernetes/clusters/prod/apps.yaml` to understand the Flux CD kustomization structure
3. Create the application directory: `kubernetes/apps/default/$ARGUMENTS/`
4. Create the Helm chart or plain manifests:
   - For a new app: create a Helm chart with `Chart.yaml`, `values.yaml`, and templates
   - Include `Deployment`, `Service`, and `HTTPRoute` (Cilium Gateway API) resources
   - Define resource requests and limits for all containers
   - Use `ExternalSecret` for any secrets (synced from 1Password)
   - Choose the correct storage class:
     - `openebs-hostpath` for SQLite databases or performance-sensitive workloads
     - NFS PV/PVC for media and bulk data
5. If the app needs a Flux `HelmRelease` and `HelmRepository`, create those in the app directory
6. Add the app to the kustomization in `kubernetes/apps/default/kustomization.yaml` if one exists
7. Validate manifests: `kubectl apply --dry-run=client -f kubernetes/apps/default/$ARGUMENTS/`
