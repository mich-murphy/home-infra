#!/usr/bin/env bash
# Static checks only. No cluster credentials, SSH, apply, or production access.
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in kubectl python3 kubeconform shellcheck; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
python3 tests/kubernetes-proof_test.py
render=$(mktemp -d)
trap 'rm -rf "$render"' EXIT
python3 tests/kubernetes-proof-schemas.py "$render/schemas"
schema="$render/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
for group in media data; do
  kubectl kustomize "kubernetes/apps/$group" > "$render/$group.yaml"
  python3 tests/kubernetes-proof.py < "$render/$group.yaml"
  # Never ignore missing schemas: CRDs come from the exact bootstrap versions.
  kubeconform -strict -summary -kubernetes-version 1.36.0 \
    -schema-location default -schema-location "$schema" "$render/$group.yaml"
done
kubectl kustomize kubernetes/apps > "$render/all-apps.yaml"
kubectl kustomize kubernetes/platform > "$render/platform.yaml"
kubeconform -strict -summary -kubernetes-version 1.36.0 \
  -schema-location default -schema-location "$schema" "$render/platform.yaml"
# Shell scripts may be named *.sh or extensionless executable; explicitly
# owned shell paths are collected without looking in private generated state.
while IFS= read -r script; do
  bash -n "$script"
  shellcheck "$script"
done < <(find talos infrastructure/proxmox-proof kubernetes/bootstrap scripts tests \
  -type f -name '*.sh' \( -path 'talos/*' -o -path 'infrastructure/proxmox-proof/*' \
  -o -path 'kubernetes/bootstrap/*' -o -name '*talos-proof*' \))
git diff --check
printf '%s\n' 'Static Talos proof checks passed. Runtime/restore/capacity gates are separate.'
