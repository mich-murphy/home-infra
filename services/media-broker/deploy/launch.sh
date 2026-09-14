#!/usr/bin/env bash
# Supported production-candidate launcher. Activation always requires the
# explicit flag; direct Compose invocation is intentionally unsupported.
set -euo pipefail

fail() { echo "launch: $*" >&2; exit 2; }
[[ "${1:-}" == --enable-candidate && $# -eq 1 ]] || fail 'pass --enable-candidate explicitly'
for variable in DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH MEDIA_BROKER_DOCKER_HOST; do
  [[ -z "${!variable+x}" ]] || fail "${variable} override is not permitted"
done

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
compose=${script_dir}/compose.yml
preflight=${script_dir}/preflight.sh
# This launcher is for docker-host itself, never a remote Docker context.
docker_host=unix:///var/run/docker.sock
docker_cmd=(docker --host "${docker_host}")

MEDIA_BROKER_DOCKER_HOST="${docker_host}" "${preflight}"
"${docker_cmd[@]}" compose -f "${compose}" build --pull=false media-broker
"${docker_cmd[@]}" compose -f "${compose}" up -d media-broker
