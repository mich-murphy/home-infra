#!/usr/bin/env bash
set -euo pipefail

readonly VMID=${VMID:-9002}
readonly NAME=${NAME:-arch-cloud}
readonly IMAGE_URL=${IMAGE_URL:-}
readonly IMAGE_SHA256=${IMAGE_SHA256:-}
readonly ISO_DIR=/var/lib/vz/template/iso

usage() {
  cat <<'EOF'
Build the Arch cloud-image template on a Proxmox VE host.

Usage:
  sudo IMAGE_URL=https://.../Arch-Linux-x86_64-cloudimg.qcow2 \
    IMAGE_SHA256=<sha256> terraform/scripts/build-arch-template.sh

Optional: VMID=9002 NAME=arch-cloud

Use a versioned image URL and its published SHA256. On a failure after VM
creation, inspect `qm config 9002`, then remove the partial VM with
`qm destroy 9002 --purge` before retrying.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ ${EUID} -eq 0 ]] || die "run this script as root on the Proxmox host"
[[ -n ${IMAGE_URL} ]] || { usage >&2; die "IMAGE_URL is required"; }
[[ ${IMAGE_SHA256} =~ ^[[:xdigit:]]{64}$ ]] || die "IMAGE_SHA256 must be a 64-character SHA256"

for command in qm pvesm wget sha256sum; do
  command -v "${command}" >/dev/null 2>&1 || die "required command not found: ${command}"
done
pvesm status --storage local >/dev/null || die "Proxmox storage 'local' is unavailable"
pvesm status --storage local-zfs >/dev/null || die "Proxmox storage 'local-zfs' is unavailable"

if qm status "${VMID}" >/dev/null 2>&1; then
  if qm config "${VMID}" | grep -q '^template: 1$'; then
    echo "Template ${VMID} already exists; nothing to do."
    exit 0
  fi
  die "VMID ${VMID} exists but is not a template; inspect it and remove the partial VM before retrying"
fi

install -d -m 0755 "${ISO_DIR}"
image=${IMAGE_URL##*/}
[[ -n ${image} && ${image} != */* ]] || die "could not derive a safe filename from IMAGE_URL"
image_path=${ISO_DIR}/${image}
partial_path=${image_path}.partial

if [[ ! -f ${image_path} ]]; then
  rm -f -- "${partial_path}"
  wget --progress=dot:giga -O "${partial_path}" "${IMAGE_URL}"
  printf '%s  %s\n' "${IMAGE_SHA256}" "${partial_path}" | sha256sum --check --status - \
    || { rm -f -- "${partial_path}"; die "SHA256 verification failed for ${image}"; }
  mv -- "${partial_path}" "${image_path}"
else
  printf '%s  %s\n' "${IMAGE_SHA256}" "${image_path}" | sha256sum --check --status - \
    || die "cached image failed SHA256 verification: ${image_path}"
fi

created=0
report_partial_vm() {
  if [[ ${created} -eq 1 ]]; then
    echo "ERROR: template build failed after creating VMID ${VMID}." >&2
    echo "Inspect with: qm config ${VMID}" >&2
    echo "After confirming the target, clean up with: qm destroy ${VMID} --purge" >&2
  fi
}
trap report_partial_vm ERR

qm create "${VMID}" --name "${NAME}" --memory 1024 --cores 2 \
  --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --ostype l26 --agent 1
created=1
qm importdisk "${VMID}" "${image_path}" local-zfs
# No iothread: it can hang the host on local-zfs zvols.
qm set "${VMID}" --scsi0 "local-zfs:vm-${VMID}-disk-0,discard=on"
qm set "${VMID}" --ide2 local-zfs:cloudinit --boot order=scsi0 --serial0 socket
qm template "${VMID}"
created=0
trap - ERR
echo "Created Arch template ${VMID} (${NAME})."
