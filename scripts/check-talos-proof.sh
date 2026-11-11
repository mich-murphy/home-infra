#!/usr/bin/env bash
# Static checks only. No cluster credentials, SSH, apply, or production access.
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in kubectl python3 node kubeconform shellcheck; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
python3 tests/kubernetes-proof_test.py
python3 kubernetes/bootstrap/test_safety.py
for suite in tests/talos-proof-*_test.py; do
  python3 "$suite"
done
# Parse every browser harness without executing it; execute only explicitly
# offline *_test modules (including the OIDC exact-audience regression suite).
for source in tests/talos-proof-*.mjs; do
  node --check "$source"
done
for suite in tests/talos-proof-*_test.mjs; do
  node "$suite"
done
render=$(mktemp -d)
trap 'rm -rf "$render"' EXIT
python3 tests/kubernetes-proof-schemas.py "$render/schemas"
schema="$render/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
for group in media data media/integration media/protocol-qbittorrent media/protocol-sabnzbd media/pinchflat-rss; do
  printf 'Validating application profile: %s\n' "$group"
  kubectl kustomize "kubernetes/apps/$group" > "$render/apps.yaml"
  python3 tests/kubernetes-proof.py < "$render/apps.yaml"
  # Never ignore missing schemas: CRDs come from the exact bootstrap versions.
  kubeconform -strict -summary -kubernetes-version 1.36.0 \
    -schema-location default -schema-location "$schema" "$render/apps.yaml"
done
kubectl kustomize kubernetes/apps > "$render/all-apps.yaml"
for root in kubernetes/platform kubernetes/platform/validation kubernetes/operations/recovery; do
  kubectl kustomize "$root" > "$render/infra.yaml"
  kubeconform -strict -summary -kubernetes-version 1.36.0 \
    -schema-location default -schema-location "$schema" "$render/infra.yaml"
done
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
