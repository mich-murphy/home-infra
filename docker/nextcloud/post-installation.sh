#!/bin/sh
set -eu

occ() {
  php /var/www/html/occ "$@"
}

if [ ! -d /mnt/nextcloud ]; then
  echo "The legacy data mount is missing at /mnt/nextcloud" >&2
  exit 1
fi

occ app:enable files_external
occ config:system:set files_external_allow_create_new_local --type=boolean --value=true
occ files_external:create /data local null::null --config datadir=/mnt/nextcloud
occ background:cron
occ config:system:set maintenance_window_start --type=integer --value=1
occ config:system:set default_phone_region --value=AU

if ! occ app:install richdocuments; then
  occ app:enable richdocuments
fi
if ! occ app:install twofactor_totp; then
  occ app:enable twofactor_totp
fi
occ richdocuments:activate-config \
  --wopi-url=http://nextcloud-office:9980 \
  --callback-url=http://nextcloud
