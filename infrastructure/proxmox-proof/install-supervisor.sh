#!/usr/bin/env bash
# INSTALL ONLY, no start/enable/restart and no changes to existing units.
# Parent must acknowledge the installation window before running this script.
set -euo pipefail
[[ $EUID == 0 && ${APPROVE_PROOF_SUPERVISOR_INSTALL:-} == 120 ]] || exit 1
HERE=$(cd "$(dirname "$0")" && pwd)
STATE=/root/.local/state/home-infra/talos-proof
for unit in talos-proof-guard.service talos-proof-start.service; do
  active=$(systemctl show "$unit" -p ActiveState --value)
  [[ $active == inactive || $active == failed ]] || { echo "Refusing replacement of active $unit" >&2; exit 1; }
done
[[ ! -L $STATE ]]
install -d -m 700 "$STATE"
# Do not overwrite files while a supervised process is using them.
for file in host_lifecycle.py resource-guard.py isolation.sh start.sh; do
  install -m 700 "$HERE/$file" "$STATE/$file"
done
for unit in talos-proof-guard.service talos-proof-start.service; do
  install -m 644 "$HERE/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/talos-proof-{guard,start}.service
printf '%s\n' 'Installed proof-only units, NOT enabled or started. Existing legacy guard remains untouched.'
