#!/usr/bin/env bash
set -euo pipefail

VMID=9003
NAME=ubuntu-server-24-04-clean
IMG=noble-server-cloudimg-amd64.img
URL=https://cloud-images.ubuntu.com/noble/current/${IMG}
SNIPPET=ubuntu-template-builder.yml

if qm status "${VMID}" >/dev/null 2>&1; then
  echo "Template ${VMID} already exists; nothing to do."
  exit 0
fi

cd /var/lib/vz/template/iso
if [ ! -f "${IMG}" ]; then
  wget -q "${URL}"
fi

mkdir -p /var/lib/vz/snippets
cat >"/var/lib/vz/snippets/${SNIPPET}" <<'EOF'
#cloud-config
package_update: true
packages:
  - qemu-guest-agent
runcmd:
  - systemctl enable qemu-guest-agent
  - rm -f /etc/systemd/resolved.conf.d/tailscaled.conf
  - ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
  - cloud-init clean --logs --machine-id
power_state:
  mode: poweroff
  timeout: 30
  condition: true
EOF

qm create "${VMID}" \
  --name "${NAME}" \
  --memory 1024 \
  --cores 2 \
  --cpu host \
  --net0 virtio,bridge=vmbr0 \
  --scsihw virtio-scsi-single \
  --ostype l26 \
  --agent enabled=1,fstrim_cloned_disks=1
qm importdisk "${VMID}" "${IMG}" local-zfs
qm set "${VMID}" --scsi0 local-zfs:vm-${VMID}-disk-0,discard=on
qm set "${VMID}" --ide2 local-zfs:cloudinit --boot order=scsi0 --serial0 socket
qm set "${VMID}" --ipconfig0 ip=dhcp,ip6=auto --nameserver 10.77.1.1
qm set "${VMID}" --cicustom "user=local:snippets/${SNIPPET}"

qm start "${VMID}"
echo "Waiting for ${VMID} first-boot customization to power off..."
while [ "$(qm status "${VMID}" | awk '{print $2}')" != "stopped" ]; do
  sleep 5
done

qm set "${VMID}" --delete cicustom
qm template "${VMID}"
