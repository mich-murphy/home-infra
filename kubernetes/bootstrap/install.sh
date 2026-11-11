#!/usr/bin/env bash
set -euo pipefail
# Explicit endpoint/context agreement avoids accidentally using a production context.
: "${KUBECONFIG:?dedicated proof kubeconfig required}"
: "${PROOF_CONTEXT:?explicit proof context required}"
: "${PROOF_API_SERVER:?expected exact Kubernetes server URL required}"
: "${PROOF_DISK_MOUNT_CONFIRMED:?set yes only after Talos mount evidence confirms dedicated disk at /var/mnt/proof}"
[[ "$PROOF_DISK_MOUNT_CONFIRMED" == yes ]]
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
K=(kubectl --context "$PROOF_CONTEXT")
actual=$("${K[@]}" config view --minify -o jsonpath='{.clusters[0].cluster.server}')
[[ "$actual" == "$PROOF_API_SERVER" ]] || { echo 'API mismatch' >&2; exit 1; }
"${K[@]}" get nodes -o json | python3 -c 'import json,sys; ns=json.load(sys.stdin)["items"]; assert len(ns)==1; assert ns[0]["status"]["nodeInfo"]["kubeletVersion"].startswith(("v1.33.","v1.34.","v1.35.","v1.36.")), "Unsupported Kubernetes version"'
CACHE=${PROOF_ARTIFACT_CACHE:-${TMPDIR:-/tmp}/talos-proof-artifacts}
python3 "$ROOT/kubernetes/bootstrap/fetch.py" "$CACHE"
for file in "$CACHE"/gateway-*-1.6.1.yaml; do "${K[@]}" apply --server-side -f "$file"; done
helm upgrade --install cilium "$CACHE/cilium-1.20.4.tgz" --kube-context "$PROOF_CONTEXT" --namespace kube-system --values "$ROOT/kubernetes/platform/cilium/values.yaml" --wait --timeout 10m
"${K[@]}" apply -k "$ROOT/kubernetes/platform"
"${K[@]}" -n local-path-storage rollout status deploy/local-path-provisioner --timeout=180s
# TLS secret intentionally created separately, private key never stored in checkout.
echo 'Platform applied. Create proof-gateway/proof-tls using bootstrap/tls.sh before HTTPS validation.'
