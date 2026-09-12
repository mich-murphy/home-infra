# Nextcloud deployment

This stack stores Nextcloud's primary data directory on the existing TrueNAS
`slow/owncloud` dataset. Ansible mounts the export on the Docker host at
`/mnt/nextcloud`; Compose bind-mounts `/mnt/nextcloud/nextcloud-data` at
`/var/www/html/data`. Nextcloud's code and configuration, PostgreSQL database,
and Redis state remain in separate local Docker volumes.

The NFS export maps requests to TrueNAS's dedicated `nextcloud` user and is
restricted to the Docker host. The old SMB share is disabled so files cannot be
changed behind Nextcloud's file cache.

## Storage prerequisite

Before running the `docker-host` Ansible role, export the TrueNAS
`slow/owncloud` dataset to the Docker host alone. Map access to the dedicated
`nextcloud` user and group, and permit read/write access. Do not leave the
export open to the whole SRV VLAN.

Ansible mounts it at `/mnt/nextcloud` with the repository's hard NFSv4.2 policy.
Confirm this before deploying the stack:

```sh
findmnt --mountpoint /mnt/nextcloud
sudo -u <mgmt-user> test -r /mnt/nextcloud
sudo -u <mgmt-user> test -w /mnt/nextcloud
```

Do not run ownCloud and Nextcloud against this dataset at the same time.

## Portainer environment

`compose.yml` declares the environment values the stack requires. Set each on
the `nextcloud` Git stack in Portainer, using independent random values for
every password. Portainer stores them; they do not belong in Git.

On first installation, `post-installation.sh` verifies the NFS-backed primary
data directory, selects cron background jobs, installs Nextcloud Office and the
TOTP provider, and configures Collabora's internal and public URLs.

## Migration record

Migrated from ownCloud on 2026-09-04, verified by checksum comparison and a
full Nextcloud scan. Rollback points:

- TrueNAS snapshot `slow/owncloud@pre-primary-data-20260904T122131Z`;
- host backup `/srv/migration-backups/owncloud-20260904T074701Z`.

Re-scan after any filesystem-level restore:

```sh
docker exec --user www-data nextcloud php occ files:scan --all
```

## Sources

- Nextcloud Docker image: https://github.com/nextcloud/docker/
- Reverse proxy configuration: https://docs.nextcloud.com/server/stable/admin_manual/configuration_server/reverse_proxy_configuration.html
- Redis caching and file locking: https://docs.nextcloud.com/server/stable/admin_manual/configuration_server/caching_configuration.html
- Nextcloud Office Docker setup: https://docs.nextcloud.com/server/latest/admin_manual/office/example-docker.html
- ownCloud migration: https://docs.nextcloud.com/server/stable/admin_manual/maintenance/migrating_owncloud.html
