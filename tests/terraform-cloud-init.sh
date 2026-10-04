#!/usr/bin/env bash
# Check the cloud-init settings Terraform gives Proxmox guests.
#
# Proxmox fills an unset nameserver or search domain from its own resolv.conf,
# which Tailscale owns, so every initialization block must set both. ai-dev's
# physical DMZ interface is IPv4-only, so a DMZ guest must not request IPv6.
#
# Vendor-data carries a Tailscale auth key, so nothing may render it to a local
# file: a snippet is uploaded from source_raw with a root-only file_mode. A VM
# names its snippets by literal volume ID, because a reference to the file
# resource's id is unknown while the snippet is replaced, and the provider then
# updates and reboots the VM.
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

# Writes every resource in the .tf files below a directory to a JSON array of
# {address, type, body}.
tf_resources() {
  local dir=$1 out=$2 file
  : >"${out}.lines"
  while IFS= read -r -d '' file; do
    hcl2json "${file}" >"${out}.hcl" || return 2
    jq -c --arg file "${file#"${dir}"/}" '
      (.resource // {}) | to_entries[] | .key as $type
      | .value | to_entries[]
      | {address: "\($file): \($type).\(.key)", type: $type, body: .value[]}
    ' "${out}.hcl" >>"${out}.lines" || return 2
  done < <(find "${dir}" -name '*.tf' -not -path '*/.terraform/*' -print0 | sort -z)
  jq -s '.' "${out}.lines" >"${out}"
}

# Prints one line per violation and fails if there is any. A dynamic block
# cannot be checked statically, so it is a violation rather than skipped.
check_config() {
  local dir=$1 resources=${tmp_dir}/resources.json
  if ! tf_resources "${dir}" "${resources}"; then
    echo "cannot parse the Terraform files under ${dir}"
    return 2
  fi
  jq -r '
    def filled: . != null and . != "" and . != [];
    # The volume ID of every snippet Terraform uploads.
    [.[] | select(.type == "proxmox_virtual_environment_file"
                  and .body.content_type == "snippets")
     | .body.datastore_id as $store
     | (.body.source_raw // [])[] | "\($store):snippets/\(.file_name)"] as $snippets
    | .[] | .address as $address | .body as $body
    | if .type == "local_file" or .type == "local_sensitive_file" then
        "\($address): do not render files locally; upload a snippet from source_raw"
      elif .type == "proxmox_virtual_environment_file"
           and $body.content_type == "snippets" then
        (if ($body.source_raw // [] | length) == 1 then empty
         else "\($address): snippet must be uploaded from source_raw" end),
        (if ($body.file_mode // "" | test("^0?[0-7]00$")) then empty
         else "\($address): snippet file_mode must be root-only" end)
      elif .type == "proxmox_virtual_environment_vm" then
        ($body.dynamic // {} | keys[] | "\($address): dynamic \(.) block cannot be checked"),
        (($body.initialization // [])[] as $init
         | (if ($init.dns // [] | length) != 1
            then "\($address): initialization must declare one dns block"
            else empty end),
           (($init.dns // [])[]
            | (if (.servers | filled) then empty
               else "\($address): dns.servers must be set" end),
              (if (.domain | filled) then empty
               else "\($address): dns.domain must be set" end)),
           # vendor_data_file_id, user_data_file_id and the like.
           ($init | to_entries[] | select(.key | endswith("_data_file_id"))
            | .key as $key | .value as $id
            | if ($id | type) != "string" or ($id | contains("${"))
              then "\($address): initialization.\($key) must be a literal volume ID"
              elif any($snippets[]; . == $id) then empty
              else "\($address): initialization.\($key) names no snippet Terraform uploads"
              end),
           # vmbr1 is the physical DMZ bridge, and ai-dev is its guest.
           (if ($address | endswith(".ai_dev"))
               or ([$body.network_device[]?.bridge] | index("vmbr1") != null)
            then
              (if ($init.ip_config // [] | length) == 0
               then "\($address): DMZ guest must declare its ip_config"
               else empty end),
              (if [($init.ip_config // [])[] | .ipv6 // empty] | length > 0
               then "\($address): DMZ guest must not request IPv6"
               else empty end)
            else empty end))
      else empty end
  ' "${resources}" >"${resources}.violations" || return 2
  if [[ -s ${resources}.violations ]]; then
    cat "${resources}.violations"
    return 1
  fi
}

failed=0

if ! check_config "${repo_root}/terraform" >"${tmp_dir}/violations"; then
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
  if check_config "${tmp_dir}/${name}" >"${tmp_dir}/${name}.out"; then
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

expect_violation local-render 'do not render files locally' '
resource "local_sensitive_file" "vendor" {
  content  = "#cloud-config"
  filename = "files/vendor.cfg"
}'

expect_violation snippet-source-file 'must be uploaded from source_raw' '
resource "proxmox_virtual_environment_file" "vendor" {
  content_type = "snippets"
  datastore_id = "local"
  file_mode    = "0600"
  source_file {
    path      = "files/vendor.cfg"
    file_name = "vendor.yml"
  }
}'

expect_violation snippet-world-readable 'file_mode must be root-only' '
resource "proxmox_virtual_environment_file" "vendor" {
  content_type = "snippets"
  datastore_id = "local"
  file_mode    = "0644"
  source_raw {
    data      = "#cloud-config"
    file_name = "vendor.yml"
  }
}'

expect_violation vendor-data-reference 'must be a literal volume ID' '
resource "proxmox_virtual_environment_file" "vendor" {
  content_type = "snippets"
  datastore_id = "local"
  file_mode    = "0600"
  source_raw {
    data      = "#cloud-config"
    file_name = "vendor.yml"
  }
}
resource "proxmox_virtual_environment_vm" "guest" {
  initialization {
    vendor_data_file_id = proxmox_virtual_environment_file.vendor.id
    dns {
      domain  = "home.arpa"
      servers = ["10.77.1.1"]
    }
  }
}'

expect_violation vendor-data-unknown 'names no snippet Terraform uploads' '
resource "proxmox_virtual_environment_file" "vendor" {
  content_type = "snippets"
  datastore_id = "local"
  file_mode    = "0600"
  source_raw {
    data      = "#cloud-config"
    file_name = "vendor.yml"
  }
}
resource "proxmox_virtual_environment_vm" "guest" {
  initialization {
    vendor_data_file_id = "local:snippets/other.yml"
    dns {
      domain  = "home.arpa"
      servers = ["10.77.1.1"]
    }
  }
}'

if [[ ${failed} -ne 0 ]]; then
  exit 1
fi
echo "Cloud-init guest DNS, DMZ IPv6 and vendor-data snippet checks passed (including negative fixtures)."
