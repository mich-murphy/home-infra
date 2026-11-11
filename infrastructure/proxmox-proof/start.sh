#!/usr/bin/env bash
# QEMU -S means CPUs stay paused until isolation is installed, including after host reboot.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
[[ $(qm config 120 | grep '^name:') == 'name: talos-proof' ]]
qm start 120
if ! bash "$HERE/isolation.sh"; then qm stop 120; exit 1; fi
qm resume 120
