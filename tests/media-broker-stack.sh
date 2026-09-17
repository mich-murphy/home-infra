#!/usr/bin/env bash
# Infra-side assertions only: Compose contract, published-port policy, and
# stack inventory. Source tests live in the mich-murphy/media-broker repo.
# --source-only runs the Docker-free contract checks that CI executes.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tests/media-broker-stack.sh [--source-only]

Source-only mode asserts the Compose contract, inventory coverage, and Ansible
policy without a Docker daemon. Full mode additionally renders the Compose file
and exercises the published-port template; it requires the desktop-linux
Docker context.
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
compose=${repo_root}/docker/media-broker/compose.yml
policy=${repo_root}/ansible/roles/docker-host/tasks/published-ports.yaml
defaults=${repo_root}/ansible/roles/docker-host/defaults/main.yaml
source_only=0
if [[ ${1:-} == "--source-only" ]]; then
  source_only=1
  shift
fi

if ! command -v yq >/dev/null 2>&1; then
  echo "ERROR: required command not found: yq" >&2
  exit 2
fi

assert_yq() {
  local description=$1 expression=$2
  if ! yq -e "${expression}" "${compose}" >/dev/null 2>&1; then
    echo "media-broker Compose contract failed: ${description}" >&2
    exit 1
  fi
}

# Provisioning defaults never activate the stack; Portainer owns deployment.
grep -q 'docker_media_broker_enabled: false' "${defaults}"
grep -q 'docker_media_broker_port: 8765' "${defaults}"

# Portainer must never build this image; a build block reintroduces the
# documented stale-context rebuild (docs/hermes-media.md).
assert_yq 'build block must be absent' '.services["media-broker"] | has("build") | not'
assert_yq 'image must be the published GHCR reference' \
  '.services["media-broker"].image | test("^ghcr[.]io/mich-murphy/media-broker:main(@sha256:[0-9a-f]{64})?$")'
assert_yq 'nonroot numeric user' '.services["media-broker"].user == "65532:65532"'
# cap_drop ALL and no-new-privileges are asserted generically for every stack
# by tests/docker-hardening.sh; this file only keeps broker-specific checks.
assert_yq 'read-only root filesystem' '.services["media-broker"].read_only == true'
assert_yq 'five mounted secrets' '.services["media-broker"].secrets | length == 5'
# yq expressions are single-quoted so the shell never expands the Compose
# interpolation syntax they assert on.
# shellcheck disable=SC2016
assert_yq 'source-pinned published port' \
  '.services["media-broker"].ports[0] == "${MEDIA_BROKER_BIND:?set MEDIA_BROKER_BIND in Portainer stack variables}:8765:8000"'
assert_yq 'fixed Host allow-list' '.services["media-broker"].environment.MEDIA_BROKER_ALLOWED_HOSTS == "docker-host:8765"'
assert_yq 'fixed Origin allow-list' '.services["media-broker"].environment.MEDIA_BROKER_ALLOWED_ORIGINS == "http://docker-host:8765"'
assert_yq 'bounded upstream responses' '.services["media-broker"].environment.MEDIA_BROKER_MAX_RESPONSE_BYTES == "5242880"'
assert_yq 'upstream keys are file references' \
  '[.services["media-broker"].environment | to_entries[] | select(.key | test("_API_KEY_FILE$"))] | length == 4'
assert_yq 'no bind mounts' '.services["media-broker"] | has("volumes") | not'
assert_yq 'host-managed secret files' \
  '[.secrets[].file | select(test("/etc/media-broker/secrets"))] | length == 5'

# Both bind settings must stay fail-closed: a default value would let a public
# bind happen without the explicit opt-in the broker requires.
for variable in MEDIA_BROKER_BIND_HOST MEDIA_BROKER_ALLOW_PUBLIC_BIND; do
  if ! grep -q "\${${variable}:?" "${compose}"; then
    echo "media-broker Compose contract failed: ${variable} must have no default" >&2
    exit 1
  fi
done

tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT
# The drift checker's full source-only pass runs as its own quality-gate
# step; here we only prove it rejects a declared Compose file that is absent.
missing_inventory=${tmp_dir}/missing-inventory.yaml
sed 's#docker/media-broker/compose.yml#docker/media-broker/missing.yml#' \
  "${repo_root}/docker/portainer-stacks.yaml" >"${missing_inventory}"
if "${repo_root}/scripts/check-portainer-drift.sh" --source-only "${missing_inventory}" >/dev/null 2>&1; then
  echo 'missing declared Compose fixture unexpectedly passed' >&2
  exit 1
fi

if [[ ${source_only} -eq 1 ]]; then
  echo 'Media-broker Compose contract and inventory assertions passed.'
  exit 0
fi

for command in docker python3; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command}" >&2
    exit 2
  fi
done
for variable in DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH; do
  if [[ -n "${!variable:-}" ]]; then
    echo "media-broker stack test rejects ${variable} overrides" >&2
    exit 2
  fi
done
docker_cmd() { docker --context desktop-linux "$@"; }
[[ "$(docker_cmd context show)" == desktop-linux ]] || {
  echo 'media-broker stack test requires Docker context desktop-linux' >&2
  exit 2
}
endpoint=$(docker_cmd context inspect --format '{{(index .Endpoints "docker").Host}}' desktop-linux)
[[ "${endpoint}" == unix:///Users/mm/.docker/run/docker.sock ]] || {
  echo "unexpected desktop-linux Docker endpoint: ${endpoint}" >&2
  exit 2
}
for secret in broker-token sonarr-api-key radarr-api-key lidarr-api-key tautulli-api-key; do
  : >"${tmp_dir}/${secret}"
done
normalized=${tmp_dir}/compose.json
compose_env=(
  MEDIA_BROKER_BIND=100.100.10.2 MEDIA_BROKER_BIND_HOST=0.0.0.0
  MEDIA_BROKER_ALLOW_PUBLIC_BIND=true
  MEDIA_BROKER_SECRETS_DIR="${tmp_dir}"
  SONARR_URL=http://sonarr:8989 RADARR_URL=http://radarr:7878
  LIDARR_URL=http://lidarr:8686 TAUTULLI_URL=http://tautulli:8181
)
env "${compose_env[@]}" docker --context desktop-linux compose -f "${compose}" config --format json >"${normalized}"
if env -u MEDIA_BROKER_BIND \
  MEDIA_BROKER_BIND_HOST=0.0.0.0 MEDIA_BROKER_ALLOW_PUBLIC_BIND=true \
  MEDIA_BROKER_SECRETS_DIR="${tmp_dir}" SONARR_URL=http://sonarr:8989 \
  RADARR_URL=http://radarr:7878 \
  LIDARR_URL=http://lidarr:8686 TAUTULLI_URL=http://tautulli:8181 \
  docker --context desktop-linux compose -f "${compose}" config --quiet >/dev/null 2>&1; then
  echo 'missing MEDIA_BROKER_BIND unexpectedly rendered' >&2
  exit 1
fi

python3 - "${policy}" "${normalized}" <<'PY'
import json
import pathlib
import sys
import yaml
from jinja2 import Environment

normalized = json.loads(pathlib.Path(sys.argv[2]).read_text())
normalized_service = normalized["services"]["media-broker"]
assert normalized_service["ports"][0]["host_ip"] == "100.100.10.2"
assert normalized_service["ports"][0]["published"] == "8765"
assert len(normalized_service["secrets"]) == 5

policy = pathlib.Path(sys.argv[1]).read_text()
assert "docker_media_broker_enabled | bool" in policy
assert "--ctorigdstport ' ~ docker_media_broker_port ~ ' --ctdir ORIGINAL -j DROP" in policy
media = policy.index("docker_media_broker_port")
fast = policy.index("--ctstate RELATED,ESTABLISHED")
assert media < fast
assert "docker_media_broker_port | int not in [443, 2375, 8006]" in policy

tasks = yaml.safe_load(policy)
block = next(item["ansible.builtin.blockinfile"]["block"] for item in tasks if item["name"] == "Allowlist Docker published ports in DOCKER-USER")
env = Environment()
env.filters["bool"] = bool
for enabled in (False, True):
    rendered = env.from_string(block).render(
        docker_media_broker_enabled=enabled,
        docker_media_broker_port=8765,
        docker_agent_proxy_client_address={"stdout": "100.100.10.20"},
        docker_media_broker_client_address={"stdout": "100.100.10.30"},
        docker_external_interface="eth0",
        docker_published_ports=[],
        docker_tailscale_fallback_ports=[],
        docker_agent_proxy_port=2375,
    )
    lines = [line.strip() for line in rendered.splitlines() if line.strip()]
    drop = "-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 8765 --ctdir ORIGINAL -j DROP"
    assert lines.index(drop) < lines.index("-A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN")
    allow = "-A DOCKER-USER -s 100.100.10.30/32 -i tailscale0 -p tcp -m conntrack --ctorigdstport 8765 --ctdir ORIGINAL -j RETURN"
    assert (allow in lines) is enabled
PY

echo 'Media-broker stack, Compose contract, and policy assertions passed.'
