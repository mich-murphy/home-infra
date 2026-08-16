#!/usr/bin/env bash
set -euo pipefail

readonly VMID=${VMID:-9003}
readonly NAME=${NAME:-ubuntu-server-24-04-clean}
readonly IMAGE_URL=${IMAGE_URL:-}
readonly IMAGE_SHA256=${IMAGE_SHA256:-}
readonly FIRST_BOOT_TIMEOUT=${FIRST_BOOT_TIMEOUT:-900}
readonly ISO_DIR=/var/lib/vz/template/iso
readonly SNIPPET_DIR=/var/lib/vz/snippets
readonly SNIPPET=ubuntu-template-builder.yml

usage() {
  cat <<'EOF'
Build the Ubuntu 24.04 cloud-image template on a Proxmox VE host.

Usage:
  sudo IMAGE_URL=https://.../noble-server-cloudimg-amd64.img \
    IMAGE_SHA256=<sha256> terraform/scripts/build-ubuntu-template.sh

Optional: VMID=9003 NAME=ubuntu-server-24-04-clean FIRST_BOOT_TIMEOUT=900

Use a versioned release URL and its published SHA256. On failure, inspect the
partial VM and its console. After confirming the target, clean it up with
`qm destroy 9003 --purge` before retrying.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ ${EUID} -eq 0 ]] || die "run this script as root on the Proxmox host"
[[ -n ${IMAGE_URL} ]] || { usage >&2; die "IMAGE_URL is required"; }
[[ ${IMAGE_SHA256} =~ ^[[:xdigit:]]{64}$ ]] || die "IMAGE_SHA256 must be a 64-character SHA256"
[[ ${FIRST_BOOT_TIMEOUT} =~ ^[0-9]+$ && ${FIRST_BOOT_TIMEOUT} -gt 0 ]] \
  || die "FIRST_BOOT_TIMEOUT must be a positive number of seconds"

for command in awk grep install qm pvesm sha256sum wget; do
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

install -d -m 0755 "${ISO_DIR}" "${SNIPPET_DIR}"
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

cat >"${SNIPPET_DIR}/${SNIPPET}" <<'EOF'
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

created=0
report_partial_vm() {
  if [[ ${created} -eq 1 ]]; then
    echo "ERROR: template build failed after creating VMID ${VMID}." >&2
    echo "Inspect with: qm config ${VMID}; qm terminal ${VMID}" >&2
    echo "After confirming the target, clean up with: qm destroy ${VMID} --purge" >&2
  fi
}
trap report_partial_vm ERR

qm create "${VMID}" --name "${NAME}" --memory 1024 --cores 2 --cpu host \
  --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --ostype l26 \
  --agent enabled=1,fstrim_cloned_disks=1
created=1
qm importdisk "${VMID}" "${image_path}" local-zfs
qm set "${VMID}" --scsi0 "local-zfs:vm-${VMID}-disk-0,discard=on"
qm set "${VMID}" --ide2 local-zfs:cloudinit --boot order=scsi0 --serial0 socket
qm set "${VMID}" --ipconfig0 ip=dhcp,ip6=auto --nameserver 10.77.1.1
qm set "${VMID}" --cicustom "user=local:snippets/${SNIPPET}"

qm start "${VMID}"
echo "Waiting up to ${FIRST_BOOT_TIMEOUT}s for ${VMID} first-boot customization to power off..."
deadline=$((SECONDS + FIRST_BOOT_TIMEOUT))
while [[ $(qm status "${VMID}" | awk '{print $2}') != stopped ]]; do
  if ((SECONDS >= deadline)); then
    die "VMID ${VMID} did not stop after ${FIRST_BOOT_TIMEOUT}s; inspect its console and cloud-init logs"
  fi
  sleep 5
done

qm set "${VMID}" --delete cicustom
qm template "${VMID}"
created=0
trap - ERR
echo "Created Ubuntu template ${VMID} (${NAME})."
