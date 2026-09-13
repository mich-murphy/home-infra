#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
template=${repo_root}/ansible/roles/ai-dev/templates/nftables.conf.j2
tasks=${repo_root}/ansible/roles/ai-dev/tasks/firewall.yaml
reload_helper=${repo_root}/ansible/roles/ai-dev/files/reload-nftables

grep -q '^flush ruleset$' "${template}" && exit 1
grep -q '^table inet ai_dev {' "${template}"
grep -q 'dest: /etc/nftables.d/ai-dev.nft' "${tasks}"
grep -q 'include "/etc/nftables.d/ai-dev.nft"' "${tasks}"
grep -q 'lineinfile:' "${tasks}"
grep -q 'delete table inet ai_dev' "${tasks}"
grep -q 'nft flush ruleset' "${tasks}" && exit 1
grep -q 'nft -c -f /run/ai-dev-nftables.nft' "${tasks}"
grep -q 'nft -c -f /run/ai-dev-nftables-root.conf' "${tasks}"
grep -q 'ai_dev_allow_legacy_nft_migration' "${tasks}"
grep -q "'tailscale0' in nft_legacy" "${tasks}" && exit 1
grep -q 'ExecReload=' "${tasks}"
grep -q '^      RemainAfterExit=yes$' "${tasks}"
grep -q 'cat /etc/nftables.d/ai-dev.nft' "${reload_helper}"
grep -q 'cat /etc/nftables.conf' "${reload_helper}" && exit 1
grep -q 'delete table inet ai_dev' "${reload_helper}"
grep -q 'delete table inet filter' "${reload_helper}" && exit 1

grep -Fq '10-cloud-init-{{ ai_dev_physical_interface }}.network.d/90-ai-dev-ipv4-only.conf' "${tasks}"
grep -q '^      DHCP=ipv4$' "${tasks}"
grep -q '^      LinkLocalAddressing=no$' "${tasks}"
grep -q '^      IPv6AcceptRA=no$' "${tasks}"

echo "ai-dev nftables ownership and physical-interface IPv6 checks passed."
