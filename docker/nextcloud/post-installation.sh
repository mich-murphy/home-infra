#!/bin/sh
set -eu

occ() {
  php /var/www/html/occ "$@"
}

if [ ! -d /mnt/owncloud ]; then
  echo "The legacy data mount is missing at /mnt/owncloud" >&2
  exit 1
fi

occ app:enable files_external
occ config:system:set files_external_allow_create_new_local --type=boolean --value=true
occ files_external:create /data local null::null --config datadir=/mnt/owncloud
occ background:cron
occ config:system:set maintenance_window_start --type=integer --value=1
occ config:system:set default_phone_region --value=AU

if ! occ app:install richdocuments; then
  occ app:enable richdocuments
fi
occ config:app:set richdocuments wopi_url --value=https://office.local.elmurphy.com
