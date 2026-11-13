#!/usr/bin/env bash
# First install/bootstrap only, never regenerate or overwrite an existing cluster identity.
set -euo pipefail
umask 077
STATE=${STATE:-$HOME/.local/state/home-infra/talos-proof}
T="$STATE/bin/talosctl"
C="$STATE/config/talosconfig"
[[ ${APPROVE_BOOTSTRAP:-} == talos-proof ]] || { echo 'Explicit APPROVE_BOOTSTRAP=talos-proof required'; exit 1; }
[[ ! -e "$STATE/config/kubeconfig" ]] || { echo 'Existing cluster kubeconfig: refusing bootstrap'; exit 1; }
"$T" validate --config "$STATE/config/controlplane.yaml" --mode metal --strict
"$T" apply-config --insecure --nodes 127.0.0.1:50120 --file "$STATE/config/controlplane.yaml"
"$T" --talosconfig "$C" config endpoint 127.0.0.1:50120
"$T" --talosconfig "$C" config node 172.31.250.10
# Installation and reboot take time; wait for authenticated Talos, not a fixed delay.
for attempt in $(seq 1 60); do
  if "$T" --talosconfig "$C" version >/dev/null 2>&1; then break; fi
  (( attempt < 60 )) || { echo 'Authenticated Talos did not become available'; exit 1; }
  sleep 5
done
"$T" --talosconfig "$C" bootstrap
"$T" --talosconfig "$C" kubeconfig "$STATE/config/kubeconfig"
chmod 600 "$STATE/config/kubeconfig"
cluster=$(kubectl --kubeconfig "$STATE/config/kubeconfig" config view -o jsonpath='{.clusters[0].name}')
kubectl --kubeconfig "$STATE/config/kubeconfig" config set-cluster "$cluster" --server=https://127.0.0.1:64120
printf 'KUBECONFIG=%s/config/kubeconfig\n' "$STATE"
