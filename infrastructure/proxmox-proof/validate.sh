#!/usr/bin/env bash
# Offline validation; private identity retained outside git. Never use older Nix talosctl.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${STATE:-$HOME/.local/state/home-infra/talos-proof}
export STATE
[[ -x "$STATE/bin/talosctl" ]] || "$ROOT/infrastructure/proxmox-proof/bootstrap-tools.sh"
[[ -e "$STATE/config/controlplane.yaml" ]] || "$ROOT/talos/generate.sh"
"$STATE/bin/talosctl" validate --config "$STATE/config/controlplane.yaml" --mode metal --strict
