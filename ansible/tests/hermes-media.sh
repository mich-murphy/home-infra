#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
helper=${repo_root}/ansible/roles/ai-dev/files/manage-hermes-media.py
tasks=${repo_root}/ansible/roles/ai-dev/tasks/hermes-media.yaml
grep -q 'ai_dev_hermes_media_runtime_needed | bool' "${tasks}"
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT

config=${tmp_dir}/config.yaml
env_file=${tmp_dir}/.env
marker=${tmp_dir}/media-broker.managed
token='TEST_MEDIA_BROKER_SECRET_0123456789abcdef'
cat >"${config}" <<'YAML'
model: preserved-model
photon:
  enabled: true
moshi:
  gateway: 127.0.0.1:24543
mcp_servers:
  other:
    url: http://other.example.invalid/mcp
YAML
printf '%s' 'KEEP_ME=preserved' >"${env_file}"

run_helper() {
  MEDIA_BROKER_TOKEN="${token}" python3 "${helper}" \
    --config "${config}" --env "${env_file}" --marker "${marker}" \
    --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 "$@"
}
first_result=$(run_helper --mode enabled --takeover false)
grep -q '{"changed":true}' <<<"${first_result}"
first_hash=$(sha256sum "${config}" "${env_file}" "${marker}")
second_result=$(run_helper --mode enabled --takeover false)
grep -q '{"changed":false}' <<<"${second_result}"
[[ "${first_hash}" == "$(sha256sum "${config}" "${env_file}" "${marker}")" ]]
# Mode-only repairs must be reported and converge on the next run.
chmod 0644 "${config}" "${env_file}" "${marker}"
grep -q '{"changed":true}' <<<"$(run_helper --mode enabled --takeover false)"
grep -q '{"changed":false}' <<<"$(run_helper --mode enabled --takeover false)"
python3 - "${config}" "${env_file}" "${marker}" <<'PY'
import pathlib, stat, sys
assert all(stat.S_IMODE(pathlib.Path(p).stat().st_mode) == 0o600 for p in sys.argv[1:])
PY

python3 - "${config}" "${env_file}" <<'PY'
import pathlib, sys, yaml
config = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())
env = pathlib.Path(sys.argv[2]).read_text()
entry = config["mcp_servers"]["media_broker"]
assert config["photon"]["enabled"] is True
assert config["moshi"]["gateway"] == "127.0.0.1:24543"
assert "other" in config["mcp_servers"]
assert entry["tools"] == {"include": [
    "arr_library_inventory", "arr_quality_profiles", "arr_root_folders", "tautulli_play_history",
    "jellyfin_play_history", "arr_request_media", "arr_unmonitor_media", "arr_delete_media",
], "resources": False, "prompts": False}
assert entry["headers"] == {"Authorization": "Bearer ${MEDIA_BROKER_TOKEN}"}
assert entry["sampling"] == {"enabled": False}
assert entry["elicitation"] == {"enabled": False}
assert entry["enabled"] is True
assert "TEST_MEDIA_BROKER_SECRET" not in pathlib.Path(sys.argv[1]).read_text()
assert "MEDIA_BROKER_TOKEN=TEST_MEDIA_BROKER_SECRET_0123456789abcdef" in env
PY

# Disable needs no token and restores the original no-final-newline state.
python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode disabled
if grep -q 'media_broker' "${config}"; then exit 1; fi
if grep -q 'MEDIA_BROKER_TOKEN=' "${env_file}"; then exit 1; fi
grep -q 'other:' "${config}"
python3 - "${env_file}" <<'PY'
import pathlib, sys
assert pathlib.Path(sys.argv[1]).read_bytes() == b"KEEP_ME=preserved"
PY
[[ ! -e "${marker}" ]]

# Cleanup of an interrupted marker without either data file creates nothing.
marker_only=${tmp_dir}/marker-only
printf '%s\nenv_final_newline=1\n' 'ansible-managed-hermes-media-broker-v1' >"${marker_only}"
python3 "${helper}" --config "${tmp_dir}/marker-only.yaml" --env "${tmp_dir}/marker-only.env" --marker "${marker_only}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode disabled
[[ ! -e "${tmp_dir}/marker-only.yaml" && ! -e "${tmp_dir}/marker-only.env" && ! -e "${marker_only}" ]]

# Disabled fresh state is a no-op; enabling without a strict token fails.
fresh_hash=$(find "${tmp_dir}" -type f -print0 | sort -z | xargs -0 sha256sum)
python3 "${helper}" --config "${tmp_dir}/fresh.yaml" --env "${tmp_dir}/fresh.env" --marker "${tmp_dir}/fresh.marker" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode disabled
diff -u <(printf '%s\n' "${fresh_hash}") <(find "${tmp_dir}" -type f -print0 | sort -z | xargs -0 sha256sum)
if env -u MEDIA_BROKER_TOKEN python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover false; then
  echo 'enabled integration unexpectedly accepted a missing token' >&2
  exit 1
fi
before=$(sha256sum "${config}" "${env_file}")
if MEDIA_BROKER_TOKEN=$'BAD_TOKEN_0123456789abcdef\nINJECT=1' python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover false; then
  echo 'multiline token unexpectedly accepted' >&2
  exit 1
fi
[[ "${before}" == "$(sha256sum "${config}" "${env_file}")" ]]

# An unowned collision fails without mutation; explicit takeover establishes ownership.
cat >"${config}" <<'YAML'
mcp_servers:
  media_broker:
    url: http://unowned.example.invalid/mcp
YAML
before=$(sha256sum "${config}")
if MEDIA_BROKER_TOKEN="${token}" python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover false; then
  echo 'unowned entry unexpectedly accepted' >&2
  exit 1
fi
[[ "${before}" == "$(sha256sum "${config}")" ]]
MEDIA_BROKER_TOKEN="${token}" python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover true
grep -q 'ansible-managed-hermes-media-broker-v1' "${marker}"
python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode disabled

# A crash between the owned YAML and env replacements is recoverable on retry.
cat >"${config}" <<'YAML'
model: preserved-model
mcp_servers:
  other:
    url: http://other.example.invalid/mcp
YAML
printf '%s\n' 'KEEP_ME=preserved' >"${env_file}"
rm -f "${marker}"
if HERMES_MEDIA_TEST_FAIL_AFTER_YAML=1 MEDIA_BROKER_TOKEN="${token}" python3 "${helper}" \
  --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover false; then
  echo 'injected transaction failure unexpectedly succeeded' >&2
  exit 1
fi
[[ -e "${marker}" ]]
MEDIA_BROKER_TOKEN="${token}" python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover false
 grep -q 'MEDIA_BROKER_TOKEN=' "${env_file}"

# Malformed YAML and invalid endpoints fail without rewriting.
printf '%s\n' 'mcp_servers: [' >"${config}"
before=$(sha256sum "${config}")
if MEDIA_BROKER_TOKEN="${token}" python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://docker-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover false; then
  echo 'malformed config unexpectedly accepted' >&2
  exit 1
fi
[[ "${before}" == "$(sha256sum "${config}")" ]]
if MEDIA_BROKER_TOKEN="${token}" python3 "${helper}" --config "${config}" --env "${env_file}" --marker "${marker}" \
  --url http://other-host:8765/mcp --allowed-host docker-host --allowed-port 8765 --mode enabled --takeover false; then
  echo 'invalid endpoint unexpectedly accepted' >&2
  exit 1
fi

# Check the actual task commands and execute their secret-free probe bodies.
python3 - "${tasks}" "${tmp_dir}" <<'PY'
import json, os, pathlib, subprocess, sys, time, yaml
items = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())
by_name = {item['name']: item for item in items}
probe = by_name['Select a Hermes Python with YAML support']
marker_task = by_name['Read bounded media ownership metadata as Hermes']
for task in (probe, marker_task, by_name['Install the Hermes media integration helper']):
    assert task['become_user'] == '{{ ai_dev_hermes_user }}'
    assert task['vars']['ansible_python_interpreter'] == '{{ ai_dev_hermes_python }}'
for task in (probe, marker_task):
    assert task['check_mode'] is False and task['timeout'] <= 10
    assert task['no_log'] is True
assert probe['when'] == 'ai_dev_hermes_media_runtime_needed | bool'
assert not any('ansible.builtin.slurp' in task for task in items)
marker_script = marker_task['ansible.builtin.command']['argv'][3]
root = pathlib.Path(sys.argv[2])
valid = root / 'valid-marker'
valid.write_text('ansible-managed-hermes-media-broker-v1\nenv_final_newline=1\n')
symlink = root / 'symlink-marker'
symlink.symlink_to(valid)
fifo = root / 'fifo-marker'
os.mkfifo(fifo)
large = root / 'large-marker'
large.write_bytes(b'x' * 257)
for path, owned in ((valid, True), (symlink, False), (fifo, False), (large, False), (root / 'absent-marker', False)):
    result = subprocess.run([sys.executable, '-I', '-c', marker_script, str(path)],
                            capture_output=True, text=True, check=True, timeout=2)
    assert json.loads(result.stdout) == {'owned': owned}
    assert result.stderr == ''
script = probe['ansible.builtin.command']['argv'][3]
assert subprocess.run([sys.executable, '-I', '-c', script, sys.executable], timeout=7).returncode == 0
assert subprocess.run([sys.executable, '-I', '-c', script, str(root / 'absent-python')], timeout=7).returncode == 1
sleeper = root / 'slow-python'
sleeper.write_text('#!/bin/sh\nexec sleep 30\n')
sleeper.chmod(0o700)
started = time.monotonic()
assert subprocess.run([sys.executable, '-I', '-c', script, str(sleeper)], timeout=7).returncode == 1
assert 4.5 < time.monotonic() - started < 7
PY

echo 'Hermes media helper enable/disable/preservation checks passed.'
