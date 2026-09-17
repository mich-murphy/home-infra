#!/usr/bin/env bash
# Infra-side assertions only: Compose contract, published-port policy, and
# stack inventory. Source tests live in the mich-murphy/media-broker repo.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
compose=${repo_root}/docker/media-broker/compose.yml
policy=${repo_root}/ansible/roles/docker-host/tasks/published-ports.yaml
# Provisioning defaults never activate the stack; Portainer owns deployment.
grep -q 'docker_media_broker_enabled: false' "${repo_root}/ansible/roles/docker-host/defaults/main.yaml"
grep -q 'docker_media_broker_port: 8765' "${repo_root}/ansible/roles/docker-host/defaults/main.yaml"

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
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT
# Source-only discovery covers the canonical docker/* deployment path and
# rejects an inventory declaration whose Compose file is absent.
"${repo_root}/scripts/check-portainer-drift.sh" --source-only
missing_inventory=${tmp_dir}/missing-inventory.yaml
sed 's#docker/media-broker/compose.yml#docker/media-broker/missing.yml#' \
  "${repo_root}/docker/portainer-stacks.yaml" >"${missing_inventory}"
if "${repo_root}/scripts/check-portainer-drift.sh" --source-only "${missing_inventory}" >/dev/null 2>&1; then
  echo 'missing declared Compose fixture unexpectedly passed' >&2
  exit 1
fi
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

python3 - "${compose}" "${policy}" "${normalized}" <<'PY'
import json
import pathlib
import re
import sys
import yaml
from jinja2 import Environment

compose = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())
normalized = json.loads(pathlib.Path(sys.argv[3]).read_text())
service = compose["services"]["media-broker"]
normalized_service = normalized["services"]["media-broker"]
assert normalized_service["ports"][0]["host_ip"] == "100.100.10.2"
assert normalized_service["ports"][0]["published"] == "8765"
assert len(normalized_service["secrets"]) == 5
assert service["user"] == "65532:65532"
assert service["cap_drop"] == ["ALL"]
assert service["read_only"] is True
assert service["security_opt"] == ["no-new-privileges:true"]
# Must stay build-free (docs/hermes-media.md); the digest is absent only
# before Renovate's first pin.
assert "build" not in service, "media-broker compose must not contain a build block"
assert re.fullmatch(r"ghcr\.io/mich-murphy/media-broker:main(@sha256:[0-9a-f]{64})?", service["image"]), service["image"]
assert service["ports"] == ["${MEDIA_BROKER_BIND:?set MEDIA_BROKER_BIND in Portainer stack variables}:8765:8000"]
assert len(service["secrets"]) == 5
assert set(service["environment"]) >= {
    "SONARR_URL", "RADARR_URL", "LIDARR_URL", "TAUTULLI_URL",
    "SONARR_API_KEY_FILE", "RADARR_API_KEY_FILE", "LIDARR_API_KEY_FILE",
    "TAUTULLI_API_KEY_FILE", "MEDIA_BROKER_TOKEN_FILE",
}
assert service["environment"]["MEDIA_BROKER_MAX_RESPONSE_BYTES"] == "5242880"
assert service["environment"]["MEDIA_BROKER_ALLOWED_HOSTS"] == "docker-host:8765"
assert service["environment"]["MEDIA_BROKER_ALLOWED_ORIGINS"] == "http://docker-host:8765"
for mount in service.get("volumes", []):
    assert "docker.sock" not in str(mount) and "media" not in str(mount).lower()
for secret in compose["secrets"].values():
    assert "/etc/media-broker/secrets" in secret["file"]

policy = pathlib.Path(sys.argv[2]).read_text()
assert "docker_media_broker_enabled | bool" in policy
assert "--ctorigdstport ' ~ docker_media_broker_port ~ ' --ctdir ORIGINAL -j DROP" in policy
media = policy.index("docker_media_broker_port")
fast = policy.index("--ctstate RELATED,ESTABLISHED")
assert media < fast
assert "docker_media_broker_port | int not in [443, 2375, 8006]" in policy

tasks = yaml.safe_load(pathlib.Path(sys.argv[2]).read_text())
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
