#!/usr/bin/env bash
# Render the optional media rule without restoring main's retired static checks.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
template=${repo_root}/ansible/roles/ai-dev/templates/nftables.conf.j2
render_dir=$(mktemp -d)
trap 'rm -rf -- "${render_dir}"' EXIT

for enabled in false true; do
  cat >"${render_dir}/vars.yml" <<YAML
ai_dev_hermes_media_broker_enabled: ${enabled}
ai_dev_hermes_media_broker_port: 8765
ai_dev_physical_interface: eth0
ai_dev_dmz_gateway: 10.77.99.1
ai_dev_dns_server: 10.77.1.1
ai_dev_docker_proxy_port: 2375
ai_dev_proxmox_api_port: 8006
ai_dev_docker_proxy_address:
  stdout: 100.64.0.2
ai_dev_proxmox_api_address:
  stdout: 100.64.0.3
YAML
  ansible localhost -c local -m template \
    -a "src=${template} dest=${render_dir}/${enabled}" -e "@${render_dir}/vars.yml" >/dev/null
  if [[ ${enabled} == true ]]; then
    grep -q 'tcp dport 8765 accept' "${render_dir}/${enabled}"
  elif grep -q 'tcp dport 8765 accept' "${render_dir}/${enabled}"; then
    echo 'disabled firewall render unexpectedly contains media-broker allow' >&2
    exit 1
  fi
done

echo 'Hermes media enabled/disabled firewall renders passed.'
