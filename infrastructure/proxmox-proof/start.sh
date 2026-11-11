#!/usr/bin/env bash
# Requires reviewed files/units installed and an approved root0600 identity receipt.
# The oneshot unit supervises even wrapper death; it never enables boot startup.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run on Proxmox as root' >&2; exit 1; }
systemctl start talos-proof-start.service
systemctl is-active --quiet talos-proof-guard.service
printf '%s\n' 'VM120 startup completed with supervised guard acknowledgement.'
