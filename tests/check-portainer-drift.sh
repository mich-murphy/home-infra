#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
checker=${repo_root}/scripts/check-portainer-drift.sh
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT

# Quoted YAML scalars must be interpreted as their values, not as literal quotes.
sed -E 's/^    - name: (.+)$/    - name: "\1"/; s/^    compose_path: (.+)$/    compose_path: "\1"/' \
  "${repo_root}/docker/portainer-stacks.yaml" > "${tmp_dir}/quoted.yaml"
"${checker}" --source-only "${tmp_dir}/quoted.yaml" >/dev/null

# Removing one inventory entry exposes an application Compose file as unexpected.
sed '/name: immich/{N;d;}' "${repo_root}/docker/portainer-stacks.yaml" > "${tmp_dir}/missing.yaml"
if "${checker}" --source-only "${tmp_dir}/missing.yaml" >/dev/null 2>&1; then
  echo "expected missing inventory entry to fail" >&2
  exit 1
fi

# A duplicate stack name is rejected before path comparison.
cat "${repo_root}/docker/portainer-stacks.yaml" > "${tmp_dir}/duplicate.yaml"
printf '%s\n' '  - name: arrs' '    compose_path: docker/arrs/compose.yml' >> "${tmp_dir}/duplicate.yaml"
if "${checker}" --source-only "${tmp_dir}/duplicate.yaml" >/dev/null 2>&1; then
  echo "expected duplicate inventory entry to fail" >&2
  exit 1
fi

echo "Portainer drift checker offline tests passed."
