#!/usr/bin/env bash
# Run on Proxmox AFTER qm start 120 (QEMU -S pauses CPUs); scope must exist for cgroup match.
# Only dedicated VM120's userspace-network sockets are affected.
set -euo pipefail
[[ -d /sys/fs/cgroup/qemu.slice/120.scope ]]
for tool in iptables ip6tables; do
  "$tool" -w -I OUTPUT 1 -m cgroup --path qemu.slice/120.scope -j DROP
  while "$tool" -w -C OUTPUT -m cgroup --path qemu.slice/120.scope -j TALOS_PROOF_120 2>/dev/null; do
    "$tool" -w -D OUTPUT -m cgroup --path qemu.slice/120.scope -j TALOS_PROOF_120
  done
  "$tool" -w -N TALOS_PROOF_120 2>/dev/null || true
  "$tool" -w -F TALOS_PROOF_120
  "$tool" -w -A TALOS_PROOF_120 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  if [[ $tool == iptables ]]; then
    for cidr in 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 224.0.0.0/4 240.0.0.0/4; do
      "$tool" -w -A TALOS_PROOF_120 -d "$cidr" -j REJECT
    done
    "$tool" -w -A TALOS_PROOF_120 -p tcp -m multiport --dports 80,443,4460 -j ACCEPT
    "$tool" -w -A TALOS_PROOF_120 -p udp -m multiport --dports 53,123 -j ACCEPT
    "$tool" -w -A TALOS_PROOF_120 -p tcp --dport 53 -j ACCEPT
  fi
  "$tool" -w -A TALOS_PROOF_120 -j REJECT
  "$tool" -w -C OUTPUT -m cgroup --path qemu.slice/120.scope -j TALOS_PROOF_120 2>/dev/null || \
    "$tool" -w -I OUTPUT 1 -m cgroup --path qemu.slice/120.scope -j TALOS_PROOF_120
  "$tool" -w -D OUTPUT -m cgroup --path qemu.slice/120.scope -j DROP
done
