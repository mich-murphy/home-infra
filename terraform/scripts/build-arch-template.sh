#!/usr/bin/env bash
set -euo pipefail

VMID=9002
NAME=arch-cloud
IMG=Arch-Linux-x86_64-cloudimg.qcow2
URL=https://geo.mirror.pkgbuild.com/images/latest/${IMG}

if qm status "${VMID}" >/dev/null 2>&1; then
  echo "Template ${VMID} already exists; nothing to do."
  exit 0
fi

cd /var/lib/vz/template/iso
if [ ! -f "${IMG}" ]; then
  wget -q "${URL}"
fi

qm create "${VMID}" --name "${NAME}" --memory 1024 --cores 2 --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --ostype l26 --agent 1
qm importdisk "${VMID}" "${IMG}" local-zfs
qm set "${VMID}" --scsi0 local-zfs:vm-${VMID}-disk-0,discard=on,iothread=1
qm set "${VMID}" --ide2 local-zfs:cloudinit --boot order=scsi0 --serial0 socket
qm template "${VMID}"
