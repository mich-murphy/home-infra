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

render() {
  local ports=$1 dest=$2
  cat >"${render_dir}/vars.yml" <<YAML
ai_dev_physical_interface: eth0
ai_dev_dmz_gateway: 10.77.99.1
ai_dev_dns_server: 10.77.1.1
ai_dev_tailnet_tcp_ports: ${ports}
YAML
  ansible localhost -c local -m template \
    -a "src=${template} dest=${dest}" -e "@${render_dir}/vars.yml" >/dev/null
}

# Rules in one chain, without indentation.
chain() {
  sed -n "/chain $1 {/,/^[[:space:]]*}\$/p" "$2" | sed -E 's/^[[:space:]]+//'
}

# The production list must be exactly HTTPS for tailscale serve; CPA and the
# controller listen on loopback, so their ports are never admitted.
production_ports=$(sed -n '/^ai_dev_tailnet_tcp_ports:/,/^[^ ]/p' "${repo_root}/ansible/group_vars/ai_dev.yaml" |
  sed -nE 's/^  - ([0-9]+)$/\1/p' | paste -sd, -)
[[ ${production_ports} == '443' ]] || fail "ai_dev_tailnet_tcp_ports must be [443], got [${production_ports}]"

for ports in '[]' "[${production_ports}]"; do
  rendered=${render_dir}/ai-dev.nft
  render "${ports}" "${rendered}"
  input=$(chain input "${rendered}")
  output=$(chain output "${rendered}")

  # Ingress: SSH, Mosh and exactly the listed TCP ports, all on tailscale0,
  # ahead of the tailscale0 drop. Nothing else from the tailnet.
  expected_ingress=$'iifname "tailscale0" tcp dport 22 accept\niifname "tailscale0" udp dport 60000-61000 accept'
  for port in $(tr -d '[],' <<<"${ports}"); do
    expected_ingress+=$'\n'"iifname \"tailscale0\" tcp dport ${port} accept"
  done
  expected_ingress+=$'\niifname "tailscale0" drop'
  ingress=$(grep -E '^iifname "tailscale0"' <<<"${input}")
  [[ ${ingress} == "${expected_ingress}" ]] || fail "unexpected tailnet ingress for ${ports}: ${ingress}"
  if grep -E 'dport 443( |$)' <<<"${input}" | grep -vq '^iifname "tailscale0" '; then
    fail "HTTPS is admitted outside tailscale0 for ${ports}"
  fi
  if grep -Eq 'dport (8317|8318)( |$)' <<<"${input}"; then
    fail "a loopback-only proxy port is admitted for ${ports}"
  fi
  grep -qx 'iifname "eth0" drop' <<<"${input}" || fail 'physical DMZ input is not default-denied'

  # Egress: MagicDNS is the only tailnet destination, ahead of the blanket drop.
  egress=$(grep -E '^oifname "tailscale0"' <<<"${output}")
  expected_egress=$'oifname "tailscale0" ip daddr 100.100.100.100 udp dport 53 accept\noifname "tailscale0" ip daddr 100.100.100.100 tcp dport 53 accept'
  [[ ${egress} == "${expected_egress}" ]] || fail "unexpected tailnet egress rules: ${egress}"
  grep -qxF 'ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10 } drop' <<<"${output}" ||
    fail 'blanket private and tailnet egress drop is missing'
done

echo 'ai-dev firewall renders passed.'
