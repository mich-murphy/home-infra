---
name: add-k8s-infra
description: Add or modify Kubernetes infrastructure controllers (Cilium, cert-manager, monitoring, etc.). Use for cluster-level components managed by Flux CD.
argument-hint: [component-name]
---

# Add Kubernetes Infrastructure Component

Add or modify the $ARGUMENTS infrastructure controller in the Kubernetes cluster.

## Context

Read `docs/PRD.md` section 4 for the planned infrastructure components. Infrastructure is deployed before applications via Flux CD.

## Steps

1. Read existing infrastructure in `kubernetes/infrastructure/controllers/` for reference patterns
2. Read `kubernetes/clusters/prod/infrastructure.yaml` to understand the Flux kustomization structure
3. Create the controller directory: `kubernetes/infrastructure/controllers/$ARGUMENTS/`
4. Create the Flux resources:
   - `HelmRepository` pointing to the upstream chart repository
   - `HelmRelease` with the chart name, version, and custom values
   - `kustomization.yaml` referencing these resources
5. For any cluster-wide configs (StorageClasses, ClusterSecretStores, etc.):
   - Place them in `kubernetes/infrastructure/configs/$ARGUMENTS/`
6. Add the component to the kustomization in `kubernetes/infrastructure/controllers/kustomization.yaml` if one exists
7. Pin Helm chart versions explicitly — do not use `*` or floating tags
8. Validate: `kubectl apply --dry-run=client -f kubernetes/infrastructure/controllers/$ARGUMENTS/`
