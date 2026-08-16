#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/check-portainer-drift.sh [--source-only] [inventory]

Source-only mode validates that every application Compose file is inventoried.
Live mode additionally compares the inventory with running Compose projects;
run it on the Docker host or set DOCKER_HOST to a read-only Docker endpoint.
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_only=0
if [[ ${1:-} == "--source-only" ]]; then
  source_only=1
  shift
fi
inventory=${1:-"${repo_root}/docker/portainer-stacks.yaml"}

for command in awk comm find sort; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command}" >&2
    exit 2
  fi
done

if [[ ! -r ${inventory} ]]; then
  echo "ERROR: inventory is not readable: ${inventory}" >&2
  exit 2
fi

tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT

awk '/^[[:space:]]+- name:/ { print $3 }' "${inventory}" | sort -u > "${tmp_dir}/expected"
awk '/^[[:space:]]+compose_path:/ { print $2 }' "${inventory}" | sort -u > "${tmp_dir}/expected-paths"
find "${repo_root}/docker" -mindepth 2 -maxdepth 2 -name compose.yml \
  ! -path "${repo_root}/docker/init/compose.yml" \
  -print \
  | awk -v root="${repo_root}/" '{ sub("^" root, ""); print }' \
  | sort -u > "${tmp_dir}/actual-paths"

missing_paths=$(comm -23 "${tmp_dir}/expected-paths" "${tmp_dir}/actual-paths")
unexpected_paths=$(comm -13 "${tmp_dir}/expected-paths" "${tmp_dir}/actual-paths")
if [[ -n ${missing_paths} || -n ${unexpected_paths} ]]; then
  [[ -z ${missing_paths} ]] || printf 'Inventory paths without Compose files:\n%s\n' "${missing_paths}"
  [[ -z ${unexpected_paths} ]] || printf 'Application Compose files missing from inventory:\n%s\n' "${unexpected_paths}"
  exit 1
fi

if [[ ${source_only} -eq 1 ]]; then
  echo "Portainer stack inventory covers every application Compose file."
  exit 0
fi

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: required command not found: docker" >&2
  exit 2
}
docker ps --format '{{.Label "com.docker.compose.project"}}' \
  | awk 'NF && $0 != "init"' \
  | sort -u > "${tmp_dir}/actual"

missing=$(comm -23 "${tmp_dir}/expected" "${tmp_dir}/actual")
unexpected=$(comm -13 "${tmp_dir}/expected" "${tmp_dir}/actual")

if [[ -n ${missing} || -n ${unexpected} ]]; then
  [[ -z ${missing} ]] || printf 'Expected stacks without running containers:\n%s\n' "${missing}"
  [[ -z ${unexpected} ]] || printf 'Unexpected running Compose projects:\n%s\n' "${unexpected}"
  exit 1
fi

echo "Portainer application stack inventory matches running Compose projects."
