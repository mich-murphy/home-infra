#!/usr/bin/env bash
# Execute preflight and launcher decisions against command/data fixtures only.
# No Docker daemon is contacted and no test resource is created.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
preflight=${repo_root}/services/media-broker/deploy/preflight.sh
launcher=${repo_root}/services/media-broker/deploy/launch.sh
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT
bin=${tmp_dir}/bin
mkdir -p "${bin}"
source_file=${repo_root}/docker/init/agent-observer/observer.py
checksum=$(sha256sum "${source_file}" | awk '{print $1}')

cat >"${tmp_dir}/policy" <<EOF
-A DOCKER-USER -s 100.100.10.30/32 -i tailscale0 -p tcp -m conntrack --ctorigdstport 8765 --ctdir ORIGINAL -j RETURN
-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 8765 --ctdir ORIGINAL -j DROP
-A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
-A DOCKER-USER -p tcp --dport 443 -j RETURN
EOF
cat >"${bin}/tailscale" <<'SH'
#!/bin/sh
if [ "$#" -ge 3 ]; then printf '%s\n' "${FIXTURE_AI_DEV_IP:-100.100.10.30}"; else printf '%s\n' 100.100.10.2; fi
SH
cat >"${bin}/ip" <<'SH'
#!/bin/sh
printf '%s\n' '1: tailscale0    inet 100.100.10.2/32 scope global tailscale0'
SH
cat >"${bin}/iptables" <<'SH'
#!/bin/sh
cat "${FIXTURE_POLICY}"
SH
cat >"${bin}/stat" <<'SH'
#!/bin/sh
path=$3
case "${path}" in
  */observer.py) printf '%s\n' "0 ${FIXTURE_SOURCE_MODE:-755}" ;;
  */secrets) printf '%s\n' '0 65532 750' ;;
  *) printf '%s\n' "0 65532 ${FIXTURE_SECRET_MODE:-640}" ;;
esac
SH
cat >"${bin}/docker" <<'SH'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "${FIXTURE_DOCKER_LOG}"
case "${1:-}" in
  --host)
    shift 2
    ;;
esac
case "${1:-}" in
  inspect)
    name=''
    for arg in "$@"; do name=${arg}; done
    if [ "${name}" = docker-socket-proxy-agent ]; then cat "${FIXTURE_OBSERVER_JSON}"; else cat "${FIXTURE_BACKEND_JSON}"; fi
    ;;
  network)
    name=''
    for arg in "$@"; do name=${arg}; done
    if [ "${name}" = docker-socket-proxy-agent ]; then cat "${FIXTURE_FRONTEND_NETWORK_JSON}"; else cat "${FIXTURE_NETWORK_JSON}"; fi
    ;;
  image)
    name=''
    for arg in "$@"; do name=${arg}; done
    if echo "${name}" | grep -q '^python:'; then cat "${FIXTURE_OBSERVER_IMAGE_JSON}"; else cat "${FIXTURE_BACKEND_IMAGE_JSON}"; fi
    ;;
  exec)
    if [ "${FIXTURE_EXEC_STATUS:-0}" -ne 0 ]; then exit "${FIXTURE_EXEC_STATUS}"; fi
    shift
    while [ "${1:-}" = -e ]; do shift 2; done
    shift
    shift 2
    OBSERVER_PROBE_PORT="${FIXTURE_PROBE_PORT}" python3 -I -c "$2"
    ;;
  compose)
    exit "${FIXTURE_COMPOSE_STATUS:-0}"
    ;;
  *) exit 0 ;;
esac
SH
chmod 0755 "${bin}"/*

mkdir -p "${tmp_dir}/secrets"
for secret in broker-token sonarr-api-key radarr-api-key lidarr-api-key tautulli-api-key; do
  printf '%s\n' fake >"${tmp_dir}/secrets/${secret}"
done
python3 - "${tmp_dir}" "${source_file}" "${checksum}" <<'PY'
import json
import pathlib
import sys

root, source, checksum = map(pathlib.Path, sys.argv[1:])
observer = {
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
    "Config": {"Image": "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea", "Env": [f"OBSERVER_SOURCE_SHA256={checksum}"], "Cmd": ["python3", "/observer.py"], "User": "65532:65532"},
    "HostConfig": {"PortBindings": {"2375/tcp": [{"HostIp": "100.100.10.2", "HostPort": "2375"}]}, "ReadonlyRootfs": True, "CapDrop": ["ALL"], "CapAdd": [], "SecurityOpt": ["no-new-privileges:true"]},
    "Mounts": [{"Source": str(source), "Destination": "/observer.py", "RW": False}],
    "NetworkSettings": {"Networks": {"docker-socket-proxy-agent": {}, "docker-socket-proxy-agent-backend": {}}},
}
backend = {
    "State": {"Status": "running", "Health": {"Status": "healthy"}},
    "Config": {"Image": "ghcr.io/tecnativa/docker-socket-proxy:v0.5.0@sha256:1f5038b54f06c3e18422902cf00ba21803d1c97805aae032e5e6673d532d3459", "User": "", "Env": ["CONTAINERS=1", "PING=1", "VERSION=1", "POST=0"]},
    "HostConfig": {"PortBindings": {}, "ReadonlyRootfs": True, "CapDrop": ["ALL"], "CapAdd": [], "SecurityOpt": ["no-new-privileges:true"]},
    "Mounts": [{"Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock"}, {"Type": "tmpfs", "Destination": "/tmp"}],
    "NetworkSettings": {"Networks": {"docker-socket-proxy-agent-backend": {}}},
}
network = {"Name": "docker-socket-proxy-agent-backend", "Driver": "bridge", "Internal": True}
frontend = {"Name": "docker-socket-proxy-agent", "Driver": "bridge", "Internal": False, "Containers": {"observer-id": {"Name": "docker-socket-proxy-agent"}}}
observer_image = {"Id": "sha256:observer", "Config": {"Entrypoint": None, "Cmd": None, "User": "", "Env": []}}
backend_image = {"Id": "sha256:backend", "Config": {"Entrypoint": ["/usr/local/bin/docker-entrypoint.sh"], "Cmd": ["haproxy", "-f", "/usr/local/etc/haproxy/haproxy.cfg"], "User": "", "Env": ["PATH=/usr/local/sbin:/usr/local/bin"]}}
observer["Image"] = observer_image["Id"]
backend["Image"] = backend_image["Id"]
backend["Config"]["Entrypoint"] = backend_image["Config"]["Entrypoint"]
backend["Config"]["Cmd"] = backend_image["Config"]["Cmd"]
backend["Mounts"] = [{"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": False}]
backend["HostConfig"]["Tmpfs"] = {"/tmp": "", "/run": ""}
backend["Config"]["Env"] = backend_image["Config"]["Env"] + ["CONTAINERS=1", "PING=1", "VERSION=1", "POST=0"]
(root / "observer.json").write_text(json.dumps(observer))
(root / "backend.json").write_text(json.dumps(backend))
(root / "observer-image.json").write_text(json.dumps(observer_image))
(root / "backend-image.json").write_text(json.dumps(backend_image))
(root / "network.json").write_text(json.dumps(network))
(root / "frontend-network.json").write_text(json.dumps(frontend))
PY

probe_port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
cat >"${tmp_dir}/probe-server.py" <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import pathlib
import sys
import time

mode_file = pathlib.Path(sys.argv[1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        mode = mode_file.read_text().strip()
        if mode == "timeout": time.sleep(6)
        if self.path == "/_ping": status, body = 200, b"OK"
        elif self.path == "/containers/json?all=1":
            if mode == "status": status, body = 500, b"error"
            elif mode == "malformed": status, body = 200, b"{"
            elif mode == "extra": status, body = 200, b'[{"Env":"bad"}]'
            elif mode == "oversize": status, body = 200, b"x" * 1048577
            else: status, body = 200, json.dumps([{"Names": ["Env-Command-Networks"], "Image": "image:Env-Command-Networks", "State": "running"}]).encode()
        elif self.path in ("/containers/name/logs", "/containers/name/archive", "/events"): status, body = 404, b"{}"
        elif self.path == "/containers/json?labels=probe": status, body = 400, b"{}"
        else: status, body = 404, b"{}"
        self.send_response(status); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
HTTPServer(("127.0.0.1", int(sys.argv[2])), Handler).serve_forever()
PY
printf '%s\n' good >"${tmp_dir}/probe-mode"
python3 "${tmp_dir}/probe-server.py" "${tmp_dir}/probe-mode" "${probe_port}" &
probe_pid=$!
sleep 0.1
trap 'kill "${probe_pid}" 2>/dev/null || true; rm -rf -- "${tmp_dir}"' EXIT
base_env=(PATH="${bin}:$PATH" FIXTURE_POLICY="${tmp_dir}/policy" FIXTURE_DOCKER_LOG="${tmp_dir}/docker.log" FIXTURE_OBSERVER_JSON="${tmp_dir}/observer.json" FIXTURE_BACKEND_JSON="${tmp_dir}/backend.json" FIXTURE_NETWORK_JSON="${tmp_dir}/network.json" FIXTURE_FRONTEND_NETWORK_JSON="${tmp_dir}/frontend-network.json" FIXTURE_OBSERVER_IMAGE_JSON="${tmp_dir}/observer-image.json" FIXTURE_BACKEND_IMAGE_JSON="${tmp_dir}/backend-image.json" FIXTURE_PROBE_PORT="${probe_port}" MEDIA_BROKER_BIND=100.100.10.2 MEDIA_BROKER_AI_DEV_CLIENT=ai-dev MEDIA_BROKER_BIND_HOST=0.0.0.0 MEDIA_BROKER_ALLOW_PUBLIC_BIND=true MEDIA_BROKER_SECRETS_DIR="${tmp_dir}/secrets")
run_preflight() { env "${base_env[@]}" "$preflight"; }
run_preflight >/dev/null

# Canonical output generated from any accepted rule spelling is the fixture
# consumed by the parser; first-two exactness rejects all unsafe alternatives.
for bad in broad-before swapped missing-drop wrong-source wrong-interface wrong-port; do
  case "${bad}" in
    broad-before) printf '%s\n%s\n' '-A DOCKER-USER -p tcp --dport 8765 -j RETURN' "$(tail -n +1 "${tmp_dir}/policy")" >"${tmp_dir}/bad" ;;
    swapped) { sed -n '2p' "${tmp_dir}/policy"; sed -n '1p' "${tmp_dir}/policy"; sed -n '3,$p' "${tmp_dir}/policy"; } >"${tmp_dir}/bad" ;;
    missing-drop) sed '2d' "${tmp_dir}/policy" >"${tmp_dir}/bad" ;;
    wrong-source) sed 's/100.100.10.30/100.100.10.31/' "${tmp_dir}/policy" >"${tmp_dir}/bad" ;;
    wrong-interface) sed 's/tailscale0/eth0/' "${tmp_dir}/policy" >"${tmp_dir}/bad" ;;
    wrong-port) sed 's/8765/8766/g' "${tmp_dir}/policy" >"${tmp_dir}/bad" ;;
  esac
  if env "${base_env[@]}" FIXTURE_POLICY="${tmp_dir}/bad" "$preflight" >/dev/null 2>&1; then
    echo "unsafe ${bad} fixture unexpectedly passed" >&2
    exit 1
  fi
done
FIXTURE_AI_DEV_IP=100.100.10.31; export FIXTURE_AI_DEV_IP
if run_preflight >/dev/null 2>&1; then echo 'ai-dev identity mismatch unexpectedly passed' >&2; exit 1; fi
unset FIXTURE_AI_DEV_IP
for accepted_mode in 755 444; do
  env "${base_env[@]}" FIXTURE_SOURCE_MODE="${accepted_mode}" "$preflight" >/dev/null
done
if env "${base_env[@]}" FIXTURE_SOURCE_MODE=620 "$preflight" >/dev/null 2>&1; then
  echo 'source mode 0620 unexpectedly passed' >&2
  exit 1
fi
for probe_mode in status malformed extra oversize timeout; do
  printf '%s\n' "${probe_mode}" >"${tmp_dir}/probe-mode"
  if run_preflight >/dev/null 2>&1; then
    echo "probe ${probe_mode} fixture unexpectedly passed" >&2
    exit 1
  fi
done
printf '%s\n' good >"${tmp_dir}/probe-mode"
cp "${tmp_dir}/observer.json" "${tmp_dir}/observer.good.json"
for variant in binding source status cmd user entrypoint readonly capdrop capadd security image mount topology; do
  python3 - "${tmp_dir}/observer.json" "${variant}" <<'PY'
import json
import sys
path, variant = sys.argv[1:]
value = json.load(open(path))
if variant == "binding": value["HostConfig"]["PortBindings"]["2375/tcp"][0]["HostIp"] = "100.100.10.99"
elif variant == "source": value["Config"]["Env"] = ["OBSERVER_SOURCE_SHA256=bad"]
elif variant == "status": value["State"]["Status"] = "exited"
elif variant == "cmd": value["Config"]["Cmd"] = ["sh"]
elif variant == "entrypoint": value["Config"]["Entrypoint"] = ["sh"]
elif variant == "user": value["Config"]["User"] = "0:0"
elif variant == "readonly": value["HostConfig"]["ReadonlyRootfs"] = False
elif variant == "capdrop": value["HostConfig"]["CapDrop"] = []
elif variant == "capadd": value["HostConfig"]["CapAdd"] = ["NET_ADMIN"]
elif variant == "security": value["HostConfig"]["SecurityOpt"] = []
elif variant == "image": value["Config"]["Image"] = "python:latest"
elif variant == "mount": value["Mounts"][0]["RW"] = True
else: value["Mounts"].append({"Source": "/var/run/docker.sock", "Destination": "/docker.sock"})
json.dump(value, open(path, "w"))
PY
  if run_preflight >/dev/null 2>&1; then echo "observer ${variant} fixture unexpectedly passed" >&2; exit 1; fi
  cp "${tmp_dir}/observer.good.json" "${tmp_dir}/observer.json"
done
python3 - "${tmp_dir}/observer.json" <<'PY'
import json
path = __import__('sys').argv[1]
value = json.load(open(path)); value["State"]["Status"] = "exited"; json.dump(value, open(path, "w"))
PY
if env "${base_env[@]}" PYTHONOPTIMIZE=1 "$preflight" >/dev/null 2>&1; then
  echo 'optimized bad observer fixture unexpectedly passed' >&2
  exit 1
fi
cp "${tmp_dir}/observer.good.json" "${tmp_dir}/observer.json"
cp "${tmp_dir}/network.json" "${tmp_dir}/network.good.json"
for variant in backend-status backend-image backend-user backend-port backend-post backend-security backend-extra-env backend-duplicate-post backend-post1 backend-extra-mount backend-extra-volume backend-wrong-source backend-wrong-target backend-writable-socket backend-missing-tmp backend-missing-run network; do
  cp "${tmp_dir}/backend.json" "${tmp_dir}/backend.good.json"
  python3 - "${tmp_dir}/backend.json" "${tmp_dir}/network.json" "${variant}" <<'PY'
import json
import sys
backend_path, network_path, variant = sys.argv[1:]
value = json.load(open(backend_path))
if variant == "backend-status": value["State"]["Status"] = "exited"
elif variant == "backend-image": value["Config"]["Image"] = "proxy:latest"
elif variant == "backend-user": value["Config"]["User"] = "65532:65532"
elif variant == "backend-port": value["HostConfig"]["PortBindings"] = {"2375/tcp": [{"HostIp": "0.0.0.0", "HostPort": "2375"}]}
elif variant == "backend-post": value["Config"]["Env"].remove("POST=0")
elif variant == "backend-security": value["HostConfig"]["SecurityOpt"] = []
elif variant == "backend-extra-env": value["Config"]["Env"].append("IMAGES=1")
elif variant == "backend-duplicate-post": value["Config"]["Env"].append("POST=0")
elif variant == "backend-post1": value["Config"]["Env"] = ["POST=1" if item == "POST=0" else item for item in value["Config"]["Env"]]
elif variant == "backend-extra-mount": value["Mounts"].append({"Type": "bind", "Source": "/tmp", "Destination": "/extra", "RW": False})
elif variant == "backend-extra-volume": value["Mounts"].append({"Type": "volume", "Name": "unexpected", "Source": "/var/lib/docker/volumes/unexpected/_data", "Destination": "/extra", "RW": False})
elif variant == "backend-wrong-source": value["Mounts"][0]["Source"] = "/tmp/docker.sock"
elif variant == "backend-wrong-target": value["Mounts"][0]["Destination"] = "/socket"
elif variant == "backend-writable-socket": value["Mounts"][0]["RW"] = True
elif variant == "backend-missing-tmp": value["HostConfig"]["Tmpfs"].pop("/tmp")
elif variant == "backend-missing-run": value["HostConfig"]["Tmpfs"].pop("/run")
else:
    network = json.load(open(network_path)); network["Internal"] = False; json.dump(network, open(network_path, "w")); json.dump(value, open(backend_path, "w")); raise SystemExit
json.dump(value, open(backend_path, "w"))
PY
  if run_preflight >/dev/null 2>&1; then echo "${variant} fixture unexpectedly passed" >&2; exit 1; fi
  cp "${tmp_dir}/backend.good.json" "${tmp_dir}/backend.json"
  cp "${tmp_dir}/network.good.json" "${tmp_dir}/network.json"
done
cp "${tmp_dir}/frontend-network.json" "${tmp_dir}/frontend.good.json"
for variant in frontend-internal frontend-extra frontend-empty; do
  python3 - "${tmp_dir}/frontend-network.json" "${variant}" <<'PY'
import json
import sys
path, variant = sys.argv[1:]
value = json.load(open(path))
if variant == "frontend-internal": value["Internal"] = True
elif variant == "frontend-extra": value["Containers"]["other-id"] = {"Name": "other"}
else: value["Containers"] = {}
json.dump(value, open(path, "w"))
PY
  if run_preflight >/dev/null 2>&1; then echo "${variant} fixture unexpectedly passed" >&2; exit 1; fi
  cp "${tmp_dir}/frontend.good.json" "${tmp_dir}/frontend-network.json"
done
if env "${base_env[@]}" FIXTURE_EXEC_STATUS=1 "$preflight" >/dev/null 2>&1; then
  echo 'observer denied-route fixture unexpectedly passed' >&2
  exit 1
fi
mv "${tmp_dir}/secrets/broker-token" "${tmp_dir}/secrets/real-token"
ln -s real-token "${tmp_dir}/secrets/broker-token"
if env "${base_env[@]}" "$preflight" >/dev/null 2>&1; then echo 'symlink secret fixture unexpectedly passed' >&2; exit 1; fi
rm "${tmp_dir}/secrets/broker-token"
mv "${tmp_dir}/secrets/real-token" "${tmp_dir}/secrets/broker-token"
if env "${base_env[@]}" FIXTURE_SECRET_MODE=644 "$preflight" >/dev/null 2>&1; then echo 'unsafe secret mode unexpectedly passed' >&2; exit 1; fi

# The launcher requires the explicit flag and must not build/start after a
# failed preflight. Fake docker records calls but performs no mutations.
: >"${tmp_dir}/docker.log"
if env "${base_env[@]}" FIXTURE_POLICY="${tmp_dir}/bad" "$launcher" --enable-candidate >/dev/null 2>&1; then
  echo 'launcher unexpectedly passed failed preflight' >&2
  exit 1
fi
if grep -Eq 'compose (build|up)' "${tmp_dir}/docker.log"; then
  echo 'launcher invoked build/up after failed preflight' >&2
  exit 1
fi
: >"${tmp_dir}/docker.log"
env "${base_env[@]}" FIXTURE_POLICY="${tmp_dir}/policy" "$launcher" --enable-candidate >/dev/null
exec_line=$(grep -n 'exec -e' "${tmp_dir}/docker.log" | tail -n 1 | cut -d: -f1)
build_line=$(grep -n -- '^--host unix:///var/run/docker.sock compose -f .* build --pull=false media-broker$' "${tmp_dir}/docker.log" | cut -d: -f1)
up_line=$(grep -n -- '^--host unix:///var/run/docker.sock compose -f .* up -d media-broker$' "${tmp_dir}/docker.log" | cut -d: -f1)
if [[ -z "${exec_line}" || -z "${build_line}" || -z "${up_line}" || ${exec_line} -ge ${build_line} || ${build_line} -ge ${up_line} ]]; then
  echo 'launcher sequence was not preflight, build, up' >&2
  exit 1
fi
if ! grep -q -- '--host unix:///var/run/docker.sock' "${tmp_dir}/docker.log"; then
  echo 'launcher did not pin the production local socket' >&2
  exit 1
fi
if env "${base_env[@]}" "$launcher" >/dev/null 2>&1; then echo 'launcher accepted missing opt-in flag' >&2; exit 1; fi

echo 'Preflight canonical/negative fixtures and launcher fail-closed checks passed.'
