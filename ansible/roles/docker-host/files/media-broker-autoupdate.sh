#!/usr/bin/env bash
# Pull-based auto-update for the media-broker stack. Pulls the tracked :main
# tag with the host Docker CLI and, only when the running container's image
# differs, asks Portainer's local stack webhook to redeploy. Portainer remains
# the only deployment controller; this script never runs Compose itself and
# never logs credentials.
set -euo pipefail

image="ghcr.io/mich-murphy/media-broker:main"
container="media-broker"
: "${MEDIA_BROKER_GHCR_USERNAME:?set MEDIA_BROKER_GHCR_USERNAME}"
: "${MEDIA_BROKER_GHCR_TOKEN:?set MEDIA_BROKER_GHCR_TOKEN}"
: "${MEDIA_BROKER_PORTAINER_WEBHOOK:?set MEDIA_BROKER_PORTAINER_WEBHOOK}"

# Dedicated root-only docker login state; never touch another user's config.
docker_config=/var/lib/media-broker-autoupdate
mkdir -p "${docker_config}"
chmod 0700 "${docker_config}"

printf '%s' "${MEDIA_BROKER_GHCR_TOKEN}" \
  | DOCKER_CONFIG="${docker_config}" docker login ghcr.io \
      -u "${MEDIA_BROKER_GHCR_USERNAME}" --password-stdin >/dev/null

DOCKER_CONFIG="${docker_config}" docker pull -q "${image}" >/dev/null
pulled_id=$(docker image inspect --format '{{.Id}}' "${image}")
running_id=$(docker inspect --format '{{.Image}}' "${container}" 2>/dev/null || true)

if [[ -z "${running_id}" ]]; then
  echo "media-broker-autoupdate: container ${container} is not running; skipping redeploy"
  exit 0
fi
if [[ "${running_id}" == "${pulled_id}" ]]; then
  exit 0
fi

echo "media-broker-autoupdate: ${image} changed; triggering Portainer redeploy"
curl -fsSk -X POST --max-time 30 "${MEDIA_BROKER_PORTAINER_WEBHOOK}"
