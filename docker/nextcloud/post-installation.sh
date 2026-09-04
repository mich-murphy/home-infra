#!/bin/sh
set -eu

occ() {
  php /var/www/html/occ "$@"
}

if [ ! -d /var/www/html/data ]; then
  echo "The NFS data directory is missing at /var/www/html/data" >&2
  exit 1
fi

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
