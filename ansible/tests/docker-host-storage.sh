#!/usr/bin/env bash
set -euo pipefail

fake_bin=$(mktemp -d)
trap 'rm -rf "${fake_bin}"' EXIT

cat >"${fake_bin}/findmnt" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

target=
for argument in "$@"; do
  case ${argument} in
    /mnt/*) target=${argument} ;;
  esac
done

if [[ ${target} == /mnt/idle && ${*} == *--fstab* ]]; then
  printf '%s\n' 'nas:/idle nfs4'
elif [[ ${target} == /mnt/idle ]]; then
  printf '%s\n' '/mnt/idle systemd-1 autofs'
elif [[ ${target} == /mnt/active && ${*} == *--fstab* ]]; then
  printf '%s\n' 'nas:/active nfs4'
elif [[ ${target} == /mnt/active ]]; then
  # Real findmnt lists both layers unless --uniq excludes the shadowed autofs.
  if [[ ${*} != *--uniq* ]]; then
    printf '%s\n' '/mnt/active systemd-1 autofs'
  fi
  printf '%s\n' '/mnt/active nas:/active nfs4'
elif [[ ${target} == /mnt/idle-wrong && ${*} == *--fstab* ]]; then
  printf '%s\n' 'nas:/wrong nfs4'
elif [[ ${target} == /mnt/idle-wrong ]]; then
  printf '%s\n' '/mnt/idle-wrong systemd-1 autofs'
elif [[ ${target} == /mnt/foreign-autofs && ${*} == *--fstab* ]]; then
  printf '%s\n' 'nas:/configured nfs4'
elif [[ ${target} == /mnt/foreign-autofs ]]; then
  printf '%s\n' '/mnt/foreign-autofs other-automounter autofs'
elif [[ ${target} == /mnt/wrong && ${*} == *--fstab* ]]; then
  printf '%s\n' 'nas:/configured nfs4'
elif [[ ${target} == /mnt/wrong ]]; then
  printf '%s\n' '/mnt/wrong nas:/wrong nfs4'
elif [[ ${target} == /mnt/absent ]]; then
  exit 1
fi
SCRIPT
chmod 0755 "${fake_bin}/findmnt"

FAKE_FINDMNT="${fake_bin}/findmnt" ansible-playbook tests/docker-host-storage.yaml
