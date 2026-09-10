#!/bin/sh
# Renders checkrr.yaml.tpl into a real config by substituting the
# RADARR_API_KEY / SONARR_API_KEY environment variables (set on the
# Portainer stack, never committed to Git) in place of the
# __RADARR_API_KEY__ / __SONARR_API_KEY__ placeholders.
#
# Checkrr has no native env-var or `${VAR}` config substitution (unlike
# Recyclarr's `!env_var` tag), so this is done here instead. The rendered
# file is written only to /tmp, which is a tmpfs (see compose.yml) - it is
# never persisted to the checkrr-data volume or the repo.
set -eu

: "${RADARR_API_KEY:?RADARR_API_KEY is required}"
: "${SONARR_API_KEY:?SONARR_API_KEY is required}"

sed \
  -e "s|__RADARR_API_KEY__|${RADARR_API_KEY}|g" \
  -e "s|__SONARR_API_KEY__|${SONARR_API_KEY}|g" \
  /config/checkrr.yaml.tpl > /tmp/checkrr-runtime.yaml

exec /checkrr -c /tmp/checkrr-runtime.yaml
