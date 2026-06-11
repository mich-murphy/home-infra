#!/usr/bin/env bash
set -euo pipefail

VMID=9002
NAME=arch-cloud
IMG=Arch-Linux-x86_64-cloudimg.qcow2
URL=https://geo.mirror.pkgbuild.com/images/latest/${IMG}
SUM_URL=${URL}.SHA256

if qm status "${VMID}" >/dev/null 2>&1; then
  echo "Template ${VMID} already exists; nothing to do."
  exit 0
fi

cd /var/lib/vz/template/iso
DOWNLOADED=0
if [ ! -f "${IMG}" ]; then
  wget -q "${URL}"
  DOWNLOADED=1
fi

# Checksum comes from the same mirror as the moving "latest" image, so this mainly protects download integrity.
SUM_LINE=$(wget -qO- "${SUM_URL}" | grep " ${IMG}\$")
if ! echo "${SUM_LINE}" | sha256sum --check --status -; then
  echo "ERROR: SHA256 verification failed for ${IMG}" >&2
  if [ "${DOWNLOADED}" -eq 1 ]; then
    rm -f "${IMG}"
  fi
  exit 1
fi

qm create "${VMID}" --name "${NAME}" --memory 1024 --cores 2 --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --ostype l26 --agent 1
qm importdisk "${VMID}" "${IMG}" local-zfs
# no iothread: it can hang the host on local-zfs zvols (see modules/proxmox_vm/main.tf)
qm set "${VMID}" --scsi0 local-zfs:vm-${VMID}-disk-0,discard=on
qm set "${VMID}" --ide2 local-zfs:cloudinit --boot order=scsi0 --serial0 socket
qm template "${VMID}"
