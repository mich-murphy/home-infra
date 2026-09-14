#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT

for command in docker-compose yq; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${command}" >&2
    exit 2
  fi
done

python3 "${repo_root}/tests/agent-observer_test.py"

# yq expressions intentionally use single quotes so the shell does not expand them.
# shellcheck disable=SC2016
check_normalized_file() {
  local stack=$1
  local normalized=$2
  local failed=0

  allowed_capability() {
    local label=$1
    local capability=$2

    # This class is deliberately an allow-list of the current services whose
    # entrypoints need root-owned volume initialisation. It is not a default
    # for every service that happens to use cap_drop ALL.
    case "${label}" in
      arrs/radarr|arrs/sonarr|arrs/lidarr|arrs/prowlarr|downloads/qbittorrent|downloads/sabnzbd|immich/redis|immich/database|jellyplex-watched/jellyplex-watched|miniflux/miniflux-db|nextcloud/nextcloud|nextcloud/nextcloud-cron|nextcloud/nextcloud-postgres|nextcloud/nextcloud-redis|plex/plex|plex/tautulli|wallabag/wallabag|wallabag/db|wallabag/redis)
        case "${capability}" in
          CHOWN|SETUID|SETGID|DAC_OVERRIDE|FOWNER|KILL) return 0 ;;
        esac
        ;;
      nextcloud/nextcloud-office)
        case "${capability}" in
          AUDIT_WRITE|CHOWN|DAC_OVERRIDE|FOWNER|FSETID|KILL|MKNOD|NET_BIND_SERVICE|NET_RAW|SETFCAP|SETGID|SETPCAP|SETUID|SYS_CHROOT) return 0 ;;
        esac
        ;;
    esac

    case "${label}/${capability}" in
      audiobookshelf/audiobookshelf/NET_BIND_SERVICE|wallabag/wallabag/NET_BIND_SERVICE|nextcloud/nextcloud-redis/SETPCAP)
        return 0
        ;;
    esac
    return 1
  }

  while IFS= read -r service; do
    export HARDENING_SERVICE=${service}
    local label=${stack}/${service}
    local expects_nnp=1
    local expects_cap_drop=1
    case "${label}" in
      init/traefik|init/portainer|init/pocket-id|immich/immich-ml)
        # Documented entrypoint exceptions in docs/docker-hardening.md.
        expects_cap_drop=0
        ;;
      nextcloud/nextcloud-office)
        expects_nnp=0
        ;;
    esac

    if [[ ${expects_nnp} -eq 1 ]]; then
      if ! yq -e '.services | .[strenv(HARDENING_SERVICE)].security_opt // [] | any_c(. == "no-new-privileges:true")' "${normalized}" >/dev/null 2>&1; then
        echo "${label}: missing no-new-privileges:true" >&2
        failed=1
      fi
    elif yq -e '.services | .[strenv(HARDENING_SERVICE)].security_opt // [] | any_c(. == "no-new-privileges:true")' "${normalized}" >/dev/null 2>&1; then
      echo "${label}: no-new-privileges:true is not allowed by its documented exception" >&2
      failed=1
    fi

    if [[ ${expects_cap_drop} -eq 1 ]]; then
      if ! yq -e '.services | .[strenv(HARDENING_SERVICE)].cap_drop // [] | any_c(. == "ALL")' "${normalized}" >/dev/null 2>&1; then
        echo "${label}: missing cap_drop ALL" >&2
        failed=1
      fi
    elif yq -e '.services | .[strenv(HARDENING_SERVICE)].cap_drop // [] | any_c(. == "ALL")' "${normalized}" >/dev/null 2>&1; then
      echo "${label}: cap_drop ALL is not expected for its documented exception" >&2
      failed=1
    fi

    while IFS= read -r capability; do
      if ! allowed_capability "${label}" "${capability}"; then
        echo "${label}: unexpected cap_add ${capability}" >&2
        failed=1
      fi
    done < <(yq -r '.services | .[strenv(HARDENING_SERVICE)].cap_add // [] | .[]?' "${normalized}")
  done < <(yq -r '.services | keys | .[]' "${normalized}")

  return "${failed}"
}

while IFS= read -r compose_file; do
  stack=$(basename "$(dirname "${compose_file}")")
  normalized=${tmp_dir}/${stack}.json
  docker-compose -f "${compose_file}" config --format json >"${normalized}"
  if ! check_normalized_file "${stack}" "${normalized}"; then
    exit 1
  fi
done < <(find "${repo_root}/docker" -name compose.yml -print | sort)

# Canonical service deployments live outside docker/, but use the same
# hardening policy. Keep the service name explicit rather than deriving
# "deploy" from the Compose file's parent directory.
canonical_compose=${repo_root}/services/media-broker/deploy/compose.yml
canonical_normalized=${tmp_dir}/media-broker.json
docker-compose -f "${canonical_compose}" config --format json >"${canonical_normalized}"
if ! check_normalized_file media-broker "${canonical_normalized}"; then
  exit 1
fi

# The exposed name is now a projection, while the socket proxy remains an
# unexposed backend. Keep these topology assertions next to the generic
# container hardening checks.
init_normalized=${tmp_dir}/init-observer.json
docker-compose -f "${repo_root}/docker/init/compose.yml" config --format json >"${init_normalized}"
if yq -e '.services["docker-socket-proxy-agent"].volumes // [] | any_c(.source == "/var/run/docker.sock")' "${init_normalized}" >/dev/null 2>&1; then
  echo "init/docker-socket-proxy-agent: observer must not mount docker.sock" >&2
  exit 1
fi
if ! yq -e '.services["docker-socket-proxy-agent"].user == "65532:65532"' "${init_normalized}" >/dev/null 2>&1; then
  echo "init/docker-socket-proxy-agent: observer must run as its dedicated unprivileged user" >&2
  exit 1
fi
if ! yq -e '.services["docker-socket-proxy-agent-backend"].ports // [] | length == 0' "${init_normalized}" >/dev/null 2>&1; then
  echo "init/docker-socket-proxy-agent-backend: backend must not publish a port" >&2
  exit 1
fi
if ! yq -e '.networks["docker-socket-proxy-agent-backend"].internal == true' "${init_normalized}" >/dev/null 2>&1; then
  echo "init/docker-socket-proxy-agent-backend: backend network must be internal" >&2
  exit 1
fi
if ! yq -e '(.services["docker-socket-proxy-agent"].networks | has("docker-socket-proxy-agent")) and (.services["docker-socket-proxy-agent"].networks | has("docker-socket-proxy-agent-backend"))' "${init_normalized}" >/dev/null 2>&1; then
  echo "init/docker-socket-proxy-agent: observer must attach to frontend and private backend networks" >&2
  exit 1
fi
if yq -e '.networks["docker-socket-proxy-agent"].internal == true' "${init_normalized}" >/dev/null 2>&1; then
  echo "init/docker-socket-proxy-agent: published observer frontend must not be internal" >&2
  exit 1
fi

# The source checksum must participate in the normalized service configuration;
# changing it is the Compose recreation trigger for the bind-mounted process.
observer_source_hash=$(sha256sum "${repo_root}/docker/init/agent-observer/observer.py" | cut -d' ' -f1)
observer_changed_hash=$(printf '%s' changed-source | sha256sum | cut -d' ' -f1)
config_with_source_hash=${tmp_dir}/init-observer-source-hash.json
config_with_changed_hash=${tmp_dir}/init-observer-changed-hash.json
AGENT_OBSERVER_SOURCE_SHA256=${observer_source_hash} docker-compose -f "${repo_root}/docker/init/compose.yml" config --format json >"${config_with_source_hash}"
AGENT_OBSERVER_SOURCE_SHA256=${observer_changed_hash} docker-compose -f "${repo_root}/docker/init/compose.yml" config --format json >"${config_with_changed_hash}"
if [[ $(yq -r '.services["docker-socket-proxy-agent"].environment.OBSERVER_SOURCE_SHA256' "${config_with_source_hash}") != "${observer_source_hash}" ]]; then
  echo "init/docker-socket-proxy-agent: source checksum missing from service config" >&2
  exit 1
fi
if [[ $(yq -r '.services["docker-socket-proxy-agent"].environment.OBSERVER_SOURCE_SHA256' "${config_with_source_hash}") == "$(yq -r '.services["docker-socket-proxy-agent"].environment.OBSERVER_SOURCE_SHA256' "${config_with_changed_hash}")" ]]; then
  echo "init/docker-socket-proxy-agent: changed source checksum must change service config" >&2
  exit 1
fi
source_service_hash=$(AGENT_OBSERVER_SOURCE_SHA256=${observer_source_hash} docker-compose -f "${repo_root}/docker/init/compose.yml" config --hash docker-socket-proxy-agent | awk '{print $2}')
changed_service_hash=$(AGENT_OBSERVER_SOURCE_SHA256=${observer_changed_hash} docker-compose -f "${repo_root}/docker/init/compose.yml" config --hash docker-socket-proxy-agent | awk '{print $2}')
if [[ -z "${source_service_hash}" || "${source_service_hash}" == "${changed_service_hash}" ]]; then
  echo "init/docker-socket-proxy-agent: changed source checksum must change Compose service hash" >&2
  exit 1
fi

# Negative fixtures ensure each required field is checked independently rather
# than allowing a service to bypass both assertions as one exception.
if check_normalized_file init "${repo_root}/tests/fixtures/docker-hardening-missing-nnp.json"; then
  echo "expected missing no-new-privileges fixture to fail" >&2
  exit 1
fi
if check_normalized_file fixture "${repo_root}/tests/fixtures/docker-hardening-unexpected-capability.json"; then
  echo "expected unexpected capability fixture to fail" >&2
  exit 1
fi
if check_normalized_file fixture "${repo_root}/tests/fixtures/docker-hardening-unexpected-init-capability.json"; then
  echo "expected unexpected init capability fixture to fail" >&2
  exit 1
fi

echo "Normalized Compose hardening assertions passed (including negative fixtures)."
