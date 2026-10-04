#!/usr/bin/env bash
# Check the cloud-init network settings Terraform gives Proxmox guests.
#
# Proxmox fills an unset nameserver or search domain from its own resolv.conf,
# which Tailscale owns, so every initialization block must set both. ai-dev's
# physical DMZ interface is IPv4-only, so a DMZ guest must not request IPv6.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT

for command in hcl2json jq; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command}" >&2
    exit 2
  fi
done

# Writes every proxmox_virtual_environment_vm in the .tf files below a
# directory to a JSON array of {address, body}.
vm_resources() {
  local dir=$1 out=$2 file
  : >"${out}.lines"
  while IFS= read -r -d '' file; do
    hcl2json "${file}" >"${out}.hcl" || return 2
    jq -c --arg file "${file#"${dir}"/}" '
      (.resource.proxmox_virtual_environment_vm // {}) | to_entries[]
      | {address: "\($file): proxmox_virtual_environment_vm.\(.key)", body: .value[]}
    ' "${out}.hcl" >>"${out}.lines" || return 2
  done < <(find "${dir}" -name '*.tf' -not -path '*/.terraform/*' -print0 | sort -z)
  jq -s '.' "${out}.lines" >"${out}"
}

# Prints one line per violation and fails if there is any. A dynamic block
# cannot be checked statically, so it is a violation rather than skipped.
check_vms() {
  local dir=$1 resources=${tmp_dir}/resources.json
  if ! vm_resources "${dir}" "${resources}"; then
    echo "cannot parse the Terraform files under ${dir}"
    return 2
  fi
  jq -r '
    def filled: . != null and . != "" and . != [];
    .[] | .address as $address | .body as $vm
    | ($vm.dynamic // {} | keys[] | "\($address): dynamic \(.) block cannot be checked"),
      (($vm.initialization // [])[] as $init
       | (if ($init.dns // [] | length) != 1
          then "\($address): initialization must declare one dns block"
          else empty end),
         (($init.dns // [])[]
          | (if (.servers | filled) then empty
             else "\($address): dns.servers must be set" end),
            (if (.domain | filled) then empty
             else "\($address): dns.domain must be set" end)),
         # vmbr1 is the physical DMZ bridge, and ai-dev is its guest.
         (if ($address | endswith(".ai_dev"))
             or ([$vm.network_device[]?.bridge] | index("vmbr1") != null)
          then
            (if ($init.ip_config // [] | length) == 0
             then "\($address): DMZ guest must declare its ip_config"
             else empty end),
            (if [($init.ip_config // [])[] | .ipv6 // empty] | length > 0
             then "\($address): DMZ guest must not request IPv6"
             else empty end)
          else empty end))
  ' "${resources}" >"${resources}.violations" || return 2
  if [[ -s ${resources}.violations ]]; then
    cat "${resources}.violations"
    return 1
  fi
}

failed=0

if ! check_vms "${repo_root}/terraform" >"${tmp_dir}/violations"; then
  sed 's/^/ERROR: /' "${tmp_dir}/violations" >&2
  failed=1
fi

# A renamed ai-dev resource must not silently drop out of the DMZ check.
if ! jq -e 'any(.[]; .address | endswith(": proxmox_virtual_environment_vm.ai_dev"))' \
  "${tmp_dir}/resources.json" >/dev/null; then
  echo "ERROR: proxmox_virtual_environment_vm.ai_dev not found; update this test" >&2
  failed=1
fi

# A clone inherits its template's DNS wherever Terraform sets none.
for script in "${repo_root}"/terraform/scripts/build-*-template.sh; do
  for option in --nameserver --searchdomain; do
    if ! grep -q -- "${option} " "${script}"; then
      echo "ERROR: ${script#"${repo_root}"/} must set ${option}" >&2
      failed=1
    fi
  done
done

# Negative fixtures prove each rule fails on its own.
expect_violation() {
  local name=$1 expected=$2 hcl=$3
  mkdir -p "${tmp_dir}/${name}"
  printf '%s\n' "${hcl}" >"${tmp_dir}/${name}/main.tf"
  if check_vms "${tmp_dir}/${name}" >"${tmp_dir}/${name}.out"; then
    echo "ERROR: expected fixture ${name} to fail" >&2
    failed=1
  elif ! grep -q -- "${expected}" "${tmp_dir}/${name}.out"; then
    echo "ERROR: fixture ${name} failed without '${expected}'" >&2
    failed=1
  fi
}

expect_violation missing-dns 'must declare one dns block' '
resource "proxmox_virtual_environment_vm" "guest" {
  initialization {
    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }
  }
}'

expect_violation missing-domain 'dns.domain must be set' '
resource "proxmox_virtual_environment_vm" "guest" {
  initialization {
    dns {
      servers = ["10.77.1.1"]
    }
  }
}'

expect_violation empty-servers 'dns.servers must be set' '
resource "proxmox_virtual_environment_vm" "guest" {
  initialization {
    dns {
      domain  = "home.arpa"
      servers = []
    }
  }
}'

expect_violation dmz-ipv6 'must not request IPv6' '
resource "proxmox_virtual_environment_vm" "guest" {
  initialization {
    dns {
      domain  = "home.arpa"
      servers = ["10.77.1.1"]
    }
    ip_config {
      ipv4 {
        address = "dhcp"
      }
      ipv6 {
        address = "dhcp"
      }
    }
  }
  network_device {
    bridge = "vmbr1"
  }
}'

expect_violation dynamic-initialization 'cannot be checked' '
resource "proxmox_virtual_environment_vm" "guest" {
  dynamic "initialization" {
    for_each = [1]
    content {}
  }
}'

if [[ ${failed} -ne 0 ]]; then
  exit 1
fi
echo "Cloud-init guest DNS and DMZ IPv6 checks passed (including negative fixtures)."
