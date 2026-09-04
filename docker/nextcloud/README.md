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

Before running the `docker-host` Ansible role, export
`10.77.20.101:/mnt/slow/owncloud` from TrueNAS to the Docker host at
`10.77.20.246`. Map access to the dedicated `nextcloud` user and group, and
permit read/write access. Do not leave the export open to the whole SRV VLAN.

Ansible mounts it at `/mnt/nextcloud` with the repository's hard NFSv4.2 policy.
Confirm this before deploying the stack:

```sh
findmnt --mountpoint /mnt/nextcloud
sudo -u mm test -r /mnt/nextcloud
sudo -u mm test -w /mnt/nextcloud
```

Do not run ownCloud and Nextcloud against this dataset at the same time.

## Portainer environment

Set these values on the new `nextcloud` Git stack:

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `NEXTCLOUD_DB_PASSWORD`
- `NEXTCLOUD_REDIS_PASSWORD`
- `COLLABORA_ADMIN_USERNAME`
- `COLLABORA_ADMIN_PASSWORD`

Use independent random values for each password. Portainer stores them; they do
not belong in Git.

On first installation, `post-installation.sh` verifies the NFS-backed primary
data directory, selects cron background jobs, installs Nextcloud Office and the
TOTP provider, and configures Collabora's internal and public URLs.

## Migration record

The original ownCloud deployment exposed the NAS as `/data` external storage.
On 2026-09-04, its files and Nextcloud's initial primary data tree were copied
without filename collisions into the NFS-backed `nextcloud-data` directory.
A checksum comparison reported zero differences before the old root-level copy
was removed. A full Nextcloud scan found 686 user files in 85 folders with zero
errors.

Rollback points:

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
