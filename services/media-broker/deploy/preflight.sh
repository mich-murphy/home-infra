#!/usr/bin/env bash
# Read-only production promotion preflight. It never creates secrets or starts
# Compose; the supported launcher invokes it before build/start.
set -euo pipefail

fail() { echo "preflight: $*" >&2; exit 1; }

# Never inherit a caller-selected daemon or TLS material. Production defaults to
# the local Docker host socket; tests pass an explicit approved context instead.
for variable in DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH; do
  [[ -z "${!variable+x}" ]] || fail "${variable} override is not permitted"
done
docker_host=${MEDIA_BROKER_DOCKER_HOST:-unix:///var/run/docker.sock}
docker_cmd=(docker --host "${docker_host}")

: "${MEDIA_BROKER_BIND:?set MEDIA_BROKER_BIND to the host Tailscale IPv4}"
: "${MEDIA_BROKER_AI_DEV_CLIENT:?set the configured ai-dev Tailscale identity}"
[[ "${MEDIA_BROKER_BIND_HOST:-}" == 0.0.0.0 ]] || fail 'public candidate requires MEDIA_BROKER_BIND_HOST=0.0.0.0'
[[ "${MEDIA_BROKER_ALLOW_PUBLIC_BIND:-}" == true ]] || fail 'public candidate requires MEDIA_BROKER_ALLOW_PUBLIC_BIND=true'
allowed_hosts=${MEDIA_BROKER_ALLOWED_HOSTS:-docker-host:8765}
allowed_origins=${MEDIA_BROKER_ALLOWED_ORIGINS:-http://docker-host:8765}
[[ "${allowed_hosts}" == docker-host:8765 ]] || fail 'Host allowlist must be exactly docker-host:8765'
[[ "${allowed_origins}" == http://docker-host:8765 ]] || fail 'Origin allowlist must be exactly http://docker-host:8765'
[[ "${allowed_hosts}" != *'*'* && "${allowed_hosts}" != *[[:space:]]* ]] || fail 'Host allowlist must be exact, non-wildcard authorities'
[[ "${allowed_origins}" != *'*'* && "${allowed_origins}" != *[[:space:]]* ]] || fail 'Origin allowlist must be exact, non-wildcard origins'
MEDIA_BROKER_ALLOWED_HOSTS="${allowed_hosts}" MEDIA_BROKER_ALLOWED_ORIGINS="${allowed_origins}" python3 -I <<'PY' || fail 'Host/Origin allowlists are not exact authorities/origins'
import os
from urllib.parse import urlsplit

hosts = tuple(item for item in os.environ["MEDIA_BROKER_ALLOWED_HOSTS"].split(",") if item)
origins = tuple(item for item in os.environ["MEDIA_BROKER_ALLOWED_ORIGINS"].split(",") if item)
if not hosts or not origins:
    raise SystemExit(1)
for value in hosts:
    parsed = urlsplit("//" + value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise SystemExit(1)
    parsed.port
for value in origins:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise SystemExit(1)
    parsed.port
PY

# tailscale(1) and the interface address are independent checks: a stale or
# mistyped value must never become a host bind address.
tailnet_ip=$(tailscale ip -4)
[[ "${tailnet_ip}" == "${MEDIA_BROKER_BIND}" ]] || fail 'bind is not the current tailscale IPv4'
ip_output=$(ip -4 -o addr show dev tailscale0) || fail 'tailscale0 is unavailable'
MEDIA_BROKER_INTERFACE_ADDRESSES="${ip_output}" python3 -I - "${MEDIA_BROKER_BIND}" <<'PY'
import ipaddress
import os
import re
import sys

bind = ipaddress.ip_address(sys.argv[1])
network = ipaddress.ip_network("100.64.0.0/10")
if bind.version != 4 or bind not in network:
    raise SystemExit("bind is not in Tailscale CGNAT range 100.64.0.0/10")
local = set(re.findall(r"inet (\d+\.\d+\.\d+\.\d+)/", os.environ["MEDIA_BROKER_INTERFACE_ADDRESSES"]))
if str(bind) not in local:
    raise SystemExit("bind is not assigned to tailscale0")
PY

ai_dev_ip=$(tailscale ip -4 "${MEDIA_BROKER_AI_DEV_CLIENT}") || fail 'unable to resolve configured ai-dev identity'
MEDIA_BROKER_AI_DEV_IP="${ai_dev_ip}" python3 -I <<'PY' || fail 'configured ai-dev identity did not resolve to one Tailscale IPv4'
import ipaddress
import os

values = os.environ["MEDIA_BROKER_AI_DEV_IP"].splitlines()
if len(values) != 1:
    raise SystemExit(1)
address = ipaddress.ip_address(values[0].strip())
if address.version != 4 or address not in ipaddress.ip_network("100.64.0.0/10"):
    raise SystemExit(1)
PY

policy=$(iptables -S DOCKER-USER)
mapfile -t rules < <(awk '$1 == "-A" { print }' <<<"${policy}")
allow="-A DOCKER-USER -s ${ai_dev_ip}/32 -i tailscale0 -p tcp -m conntrack --ctorigdstport 8765 --ctdir ORIGINAL -j RETURN"
drop="-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 8765 --ctdir ORIGINAL -j DROP"
# iptables -S has canonical property ordering. Requiring the first two actual
# rules to be exactly these values rejects extra flags, negation, jumps,
# duplicates, broad earlier returns, and an allow/drop swap.
[[ ${#rules[@]} -ge 2 && "${rules[0]}" == "${allow}" && "${rules[1]}" == "${drop}" ]] || fail 'media DOCKER-USER rules are not exact, ordered, and source-pinned'
media_rule_count=$(grep -Ec -- '(^| )8765( |$)' <<<"${policy}" || true)
[[ "${media_rule_count}" == 2 ]] || fail 'media port has extra or duplicate DOCKER-USER rules'

# The already deployed observer is the only permitted prerequisite. Inspect is
# read-only and validates the exact approved source, image, bind, topology, and
# sanitized route behavior without printing its environment or response data.
observer_json=$("${docker_cmd[@]}" inspect --format '{{json .}}' docker-socket-proxy-agent) || fail 'observer is not deployed'
backend_json=$("${docker_cmd[@]}" inspect --format '{{json .}}' docker-socket-proxy-agent-backend) || fail 'observer backend is not deployed'
network_json=$("${docker_cmd[@]}" network inspect --format '{{json .}}' docker-socket-proxy-agent-backend) || fail 'observer backend network is not deployed'
frontend_network_json=$("${docker_cmd[@]}" network inspect --format '{{json .}}' docker-socket-proxy-agent) || fail 'observer frontend network is not deployed'
observer_image_ref=python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
backend_image_ref=ghcr.io/tecnativa/docker-socket-proxy:v0.5.0@sha256:1f5038b54f06c3e18422902cf00ba21803d1c97805aae032e5e6673d532d3459
observer_image_json=$("${docker_cmd[@]}" image inspect --format '{{json .}}' "${observer_image_ref}") || fail 'observer image is not locally pinned'
backend_image_json=$("${docker_cmd[@]}" image inspect --format '{{json .}}' "${backend_image_ref}") || fail 'backend image is not locally pinned'
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
repo_source=${repo_root}/docker/init/agent-observer/observer.py
expected_checksum=$(sha256sum "${repo_source}" | awk '{print $1}')
observer_source=$(python3 -I -c 'import json,sys; value=json.loads(sys.argv[1]); print(next(item["Source"] for item in value["Mounts"] if item.get("Destination") == "/observer.py"))' "${observer_json}") || fail 'observer source mount is missing'
read -r observer_source_uid observer_source_mode < <(stat -c '%u %a' "${observer_source}")
observer_source_checksum=$(sha256sum "${observer_source}" | awk '{print $1}')
python3 -I - "${observer_json}" "${backend_json}" "${network_json}" "${frontend_network_json}" "${observer_image_json}" "${backend_image_json}" "${MEDIA_BROKER_BIND}" "${expected_checksum}" "${observer_source}" "${observer_source_uid}" "${observer_source_mode}" "${observer_source_checksum}" <<'PY' || fail 'observer runtime does not match the approved sanitized topology'
import json
import sys

observer, backend, network, frontend = json.loads(sys.argv[1]), json.loads(sys.argv[2]), json.loads(sys.argv[3]), json.loads(sys.argv[4])
observer_image, backend_image = json.loads(sys.argv[5]), json.loads(sys.argv[6])
bind, expected = sys.argv[7], sys.argv[8]
source, source_uid, source_mode, source_checksum = sys.argv[9:13]
def require(condition):
    if not condition:
        raise SystemExit(1)

require(observer["State"]["Status"] == "running")
require(observer["State"].get("Health", {}).get("Status") == "healthy")
require(observer["Config"]["Image"] == "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea")
require(observer["Image"] == observer_image["Id"])
require(observer_image["Config"].get("Entrypoint") in (None, []))
require(observer["Config"].get("Entrypoint") in (None, []))
require(observer["Config"].get("Cmd") == ["python3", "/observer.py"])
require(observer["Config"].get("User") == "65532:65532")
for value in (observer, backend):
    host_config = value["HostConfig"]
    require(host_config.get("ReadonlyRootfs") is True)
    require(host_config.get("CapDrop") == ["ALL"])
    require(host_config.get("CapAdd") in (None, []))
    require("no-new-privileges:true" in (host_config.get("SecurityOpt") or []))
ports = observer["HostConfig"].get("PortBindings") or {}
require(ports == {"2375/tcp": [{"HostIp": bind, "HostPort": "2375"}]})
mounts = observer.get("Mounts", [])
source_mounts = [item for item in mounts if item.get("Destination") == "/observer.py"]
require(len(source_mounts) == 1 and source_mounts[0].get("RW") is False)
require(len(mounts) == 1 and not any("docker.sock" in str(item) for item in mounts))
require(set(observer.get("NetworkSettings", {}).get("Networks", {})) == {"docker-socket-proxy-agent", "docker-socket-proxy-agent-backend"})
env = observer["Config"].get("Env", [])
require(f"OBSERVER_SOURCE_SHA256={expected}" in env)
require(source == source_mounts[0]["Source"])
require(source_uid == "0" and not (int(source_mode, 8) & 0o022))
require(source_checksum == expected)
require(backend["State"]["Status"] == "running")
require(backend["State"].get("Health", {}).get("Status") == "healthy")
require(backend["Config"]["Image"] == "ghcr.io/tecnativa/docker-socket-proxy:v0.5.0@sha256:1f5038b54f06c3e18422902cf00ba21803d1c97805aae032e5e6673d532d3459")
require(backend["Image"] == backend_image["Id"])
require(backend["Config"].get("Entrypoint") == backend_image["Config"].get("Entrypoint"))
require(backend["Config"].get("Cmd") == backend_image["Config"].get("Cmd"))
require(backend["Config"].get("User", "") == backend_image["Config"].get("User", ""))
require(not (backend["HostConfig"].get("PortBindings") or {}))

def env_map(entries):
    result = {}
    for entry in entries or []:
        key, separator, value = entry.partition("=")
        require(separator and key and key not in result)
        result[key] = value
    return result
image_env = env_map(backend_image["Config"].get("Env", []))
approved_overrides = {"CONTAINERS": "1", "PING": "1", "VERSION": "1", "POST": "0"}
image_env.update(approved_overrides)
require(env_map(backend["Config"].get("Env", [])) == image_env)
backend_mounts = backend.get("Mounts", [])
require(all(item.get("Type") in {"bind", "tmpfs"} for item in backend_mounts))
bind_mounts = [item for item in backend_mounts if item.get("Type") == "bind"]
require(len(bind_mounts) == 1 and bind_mounts[0].get("Source") == "/var/run/docker.sock" and bind_mounts[0].get("Destination") == "/var/run/docker.sock" and bind_mounts[0].get("RW") is False)
tmpfs_mounts = {item.get("Destination"): item for item in backend_mounts if item.get("Type") == "tmpfs"}
require(not tmpfs_mounts or (set(tmpfs_mounts) == {"/tmp", "/run"} and all(item.get("RW") is True for item in tmpfs_mounts.values())))
require(backend["HostConfig"].get("Tmpfs") == {"/tmp": "", "/run": ""})
require(set(backend.get("NetworkSettings", {}).get("Networks", {})) == {"docker-socket-proxy-agent-backend"})
require(network.get("Internal") is True and network.get("Driver") == "bridge")
require(frontend.get("Name") == "docker-socket-proxy-agent" and frontend.get("Internal") is False and frontend.get("Driver") == "bridge")
containers = frontend.get("Containers", {})
require(len(containers) == 1 and next(iter(containers.values())).get("Name") == "docker-socket-proxy-agent")
PY

"${docker_cmd[@]}" exec -e OBSERVER_PROBE_PORT="${OBSERVER_PROBE_PORT:-2375}" docker-socket-proxy-agent python3 -I -c '
import http.client, json, os

def require(condition):
    if not condition:
        raise SystemExit(1)

def projection(body):
    value = json.loads(body)
    require(isinstance(value, list))
    allowed = {"Id", "Names", "Image", "ImageID", "State", "Status", "ExitCode", "Health"}
    for item in value:
        require(isinstance(item, dict) and set(item) <= allowed)
        for key in ("Id", "Image", "ImageID", "State", "Status"):
            if key in item: require(isinstance(item[key], str))
        if "Names" in item: require(isinstance(item["Names"], list) and all(isinstance(x, str) for x in item["Names"]))
        if "ExitCode" in item: require(isinstance(item["ExitCode"], int) and not isinstance(item["ExitCode"], bool))
        if "Health" in item: require(isinstance(item["Health"], dict) and set(item["Health"]) <= {"Status"} and isinstance(item["Health"].get("Status"), str))

checks = [("GET", "/_ping", 200, False), ("GET", "/containers/json?all=1", 200, True), ("GET", "/containers/name/logs", 404, False), ("GET", "/containers/name/archive", 404, False), ("GET", "/events", 404, False), ("GET", "/containers/json?labels=probe", 400, False)]
for method, path, expected, is_list in checks:
    connection = http.client.HTTPConnection("127.0.0.1", int(os.environ.get("OBSERVER_PROBE_PORT", "2375")), timeout=5)
    connection.request(method, path)
    response = connection.getresponse()
    body = response.read(1048577)
    require(response.status == expected)
    require(len(body) <= 1048576)
    if is_list: projection(body)
    connection.close()
' || fail 'observer sanitized positive/denied route probes failed'

secret_dir=${MEDIA_BROKER_SECRETS_DIR:-/etc/media-broker/secrets}
[[ -d "${secret_dir}" ]] || fail 'root-managed secret directory is missing'
read -r dir_uid dir_gid dir_mode < <(stat -c '%u %g %a' "${secret_dir}")
[[ "${dir_uid}:${dir_gid}" == 0:65532 && "${dir_mode}" == 750 ]] || fail 'secret directory must be root:65532 mode 0750'
for secret in broker-token sonarr-api-key radarr-api-key lidarr-api-key tautulli-api-key; do
  path=${secret_dir}/${secret}
  [[ -f "${path}" && ! -L "${path}" ]] || fail "secret file is missing or symlinked: ${secret}"
  read -r uid gid mode < <(stat -c '%u %g %a' "${path}")
  [[ "${uid}:${gid}" == 0:65532 && "${mode}" == 640 ]] || fail "secret must be root:65532 mode 0640: ${secret}"
done

echo 'media-broker preflight passed; no secrets were created and no containers were started'
