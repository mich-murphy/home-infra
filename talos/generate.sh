#!/usr/bin/env bash
# Never place generated machine configs or credentials in the checkout.
set -euo pipefail
umask 077
HERE=$(cd "$(dirname "$0")" && pwd)
STATE=${STATE:-$HOME/.local/state/home-infra/talos-proof}
TALOSCTL="$STATE/bin/talosctl"
mkdir -p "$STATE/config"
chmod 700 "$STATE" "$STATE/config"
[[ ! -e "$STATE/config/controlplane.yaml" ]] || { echo 'Refusing to overwrite existing identity' >&2; exit 1; }
"$TALOSCTL" gen config talos-proof https://172.31.250.10:6443 \
  --additional-sans 127.0.0.1 --kubernetes-version 1.36.6 --install-image ghcr.io/siderolabs/installer:v1.14.5 \
  --with-cluster-discovery=false --with-docs=false --with-examples=false \
  --config-patch-control-plane "@$HERE/controlplane.patch.yaml" \
  --output-types controlplane,talosconfig --output "$STATE/config"
chmod 600 "$STATE/config/"*
