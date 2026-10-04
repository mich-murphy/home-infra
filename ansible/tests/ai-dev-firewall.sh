#!/usr/bin/env bash
# Render the ai-dev nftables fragment and check the tailnet containment it promises.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
template=${repo_root}/ansible/roles/ai-dev/templates/nftables.conf.j2
render_dir=$(mktemp -d)
trap 'rm -rf -- "${render_dir}"' EXIT

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

cat >"${render_dir}/vars.yml" <<'YAML'
ai_dev_physical_interface: eth0
ai_dev_dmz_gateway: 10.77.99.1
ai_dev_dns_server: 10.77.1.1
YAML
ansible localhost -c local -m template \
  -a "src=${template} dest=${render_dir}/ai-dev.nft" -e "@${render_dir}/vars.yml" >/dev/null
rendered=${render_dir}/ai-dev.nft

# Egress: MagicDNS is the only tailnet destination, ahead of the blanket drop.
egress=$(grep -E '^[[:space:]]*oifname "tailscale0"' "${rendered}" | sed -E 's/^[[:space:]]+//')
expected_egress=$'oifname "tailscale0" ip daddr 100.100.100.100 udp dport 53 accept\noifname "tailscale0" ip daddr 100.100.100.100 tcp dport 53 accept'
[[ ${egress} == "${expected_egress}" ]] || fail "unexpected tailnet egress rules: ${egress}"
grep -qE '^[[:space:]]*ip daddr \{ 10\.0\.0\.0/8, 172\.16\.0\.0/12, 192\.168\.0\.0/16, 100\.64\.0\.0/10 \} drop$' "${rendered}" ||
  fail 'blanket private and tailnet egress drop is missing'

echo 'ai-dev firewall render passed.'
