#!/usr/bin/env bash
set -euo pipefail
# Explicit endpoint/context agreement avoids accidentally using a production context.
: "${KUBECONFIG:?dedicated proof kubeconfig required}"
: "${PROOF_CONTEXT:?explicit proof context required}"
: "${PROOF_API_SERVER:?expected exact Kubernetes server URL required}"
: "${PROOF_DISK_MOUNT_CONFIRMED:?set yes only after Talos mount evidence confirms dedicated disk at /var/mnt/proof}"
[[ "$PROOF_DISK_MOUNT_CONFIRMED" == yes ]]
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
python3 "$ROOT/kubernetes/bootstrap/proof_guard.py"
K=(python3 "$ROOT/kubernetes/bootstrap/proof_guard.py" --context "$PROOF_CONTEXT")
actual=$("${K[@]}" config view --minify -o jsonpath='{.clusters[0].cluster.server}')
[[ "$actual" == "$PROOF_API_SERVER" ]] || { echo 'API mismatch' >&2; exit 1; }
"${K[@]}" get nodes -o json | python3 -c 'import json,sys; ns=json.load(sys.stdin)["items"]; assert len(ns)==1; assert ns[0]["status"]["nodeInfo"]["kubeletVersion"].startswith(("v1.33.","v1.34.","v1.35.","v1.36.")), "Unsupported Kubernetes version"'
CACHE=${PROOF_ARTIFACT_CACHE:-${TMPDIR:-/tmp}/talos-proof-artifacts}
python3 "$ROOT/kubernetes/bootstrap/fetch.py" "$CACHE"
for file in "$CACHE"/gateway-*-1.6.1.yaml; do "${K[@]}" apply --server-side -f "$file"; done
python3 "$ROOT/kubernetes/bootstrap/proof_guard.py"
# The guard rejects inherited HELM_KUBE*, Kubernetes fallback and proxy overrides.
# Pin the actual Helm transport as well as its preceding identity check.
helm upgrade --install cilium "$CACHE/cilium-1.20.4.tgz" --kubeconfig "$KUBECONFIG" --kube-context "$PROOF_CONTEXT" --kube-apiserver "$PROOF_API_SERVER" --kube-insecure-skip-tls-verify=false --namespace kube-system --values "$ROOT/kubernetes/platform/cilium/values.yaml" --wait --timeout 10m
# Operator installs Cilium CRDs asynchronously; Helm readiness is not CRD readiness.
for crd in ciliumnetworkpolicies.cilium.io ciliumclusterwidenetworkpolicies.cilium.io ciliumgatewayclassconfigs.cilium.io; do
  "${K[@]}" wait --for=create "crd/$crd" --timeout=180s
  "${K[@]}" wait --for=condition=Established "crd/$crd" --timeout=180s
done
"${K[@]}" -n kube-system rollout status ds/cilium --timeout=300s
"${K[@]}" -n kube-system rollout status ds/cilium-envoy --timeout=180s
"${K[@]}" apply -k "$ROOT/kubernetes/platform"
"${K[@]}" -n local-path-storage rollout status deploy/local-path-provisioner --timeout=180s
# TLS secret intentionally created separately, private key never stored in checkout.
echo 'Platform applied. Create proof-gateway/proof-tls using bootstrap/tls.sh before HTTPS validation.'
