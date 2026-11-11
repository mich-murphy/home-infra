#!/usr/bin/env bash
# Compatibility entry point. All kubectl operations use the fail-closed Python guard.
set -euo pipefail
exec python3 "$(dirname "$0")/talos-proof-media-batch.py" "$@"
