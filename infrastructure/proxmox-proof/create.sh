#!/usr/bin/env bash
# Explicitly approved, isolated proof VM ONLY. Run on Proxmox.
set -euo pipefail
[[ ${APPROVE_TALOS_PROOF:-} == 120 ]] || { echo 'Set APPROVE_TALOS_PROOF=120 after review'; exit 1; }
[[ ! -e /etc/pve/qemu-server/120.conf ]]
AVAIL=$(awk '/MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
(( AVAIL >= 4450 )) || { echo "Insufficient headroom: ${AVAIL}MiB"; exit 1; }
[[ $(awk '/SwapFree:/{f=$2}/SwapTotal:/{t=$2}END{print t-f}' /proc/meminfo) == 0 ]]
qm create 120 --name talos-proof --cores 2 --cpu host --memory 2560 --balloon 0 \
 --machine q35 --bios ovmf --efidisk0 local-zfs:0,efitype=4m,pre-enrolled-keys=0 \
 --scsihw virtio-scsi-pci --scsi0 local-zfs:32,discard=on --scsi1 local-zfs:64,discard=on \
 --ide2 local:iso/talos-proof-v1.14.5-amd64.iso,media=cdrom --boot 'order=scsi0;ide2' \
 --serial0 socket --vga serial0 --ostype l26 --onboot 0 --agent 0 \
 --args '-S -netdev user,id=proofnet,net=172.31.250.0/24,dhcpstart=172.31.250.10,ipv6=off,hostfwd=tcp:127.0.0.1:50120-172.31.250.10:50000,hostfwd=tcp:127.0.0.1:64120-172.31.250.10:6443 -device virtio-net-pci,netdev=proofnet,mac=02:00:00:00:01:20'
echo 'Created but NOT started. Use start.sh: QEMU -S pauses CPUs until isolation is installed.'
