# Nextcloud deployment

This stack replaces ownCloud with a fresh Nextcloud installation and exposes the
existing TrueNAS `slow/owncloud` dataset as the system-wide `/data` external
storage. It does not overwrite that dataset. Nextcloud's application files,
PostgreSQL database, and Redis state use separate local Docker volumes.

The live ownCloud inspection on 2026-09-04 found that `/data` is an SMB external
storage backed by `10.77.20.101/owncloud`. The local `owncloud-data` volume is
only 80 MB and contains ownCloud configuration, sessions, and its small internal
data directory. User documents are on the TrueNAS share. The replacement uses
NFSv4.2 for the same dataset so credentials do not need to be stored in
Nextcloud.

## Storage prerequisite

Before running the `docker-host` Ansible role, export
`10.77.20.101:/mnt/slow/owncloud` from TrueNAS to the Docker host at
`10.77.20.246`. Map access to the dataset-owning `owncloud` user and group, and
permit read/write access. Do not leave the export open to the whole SRV VLAN.

Ansible mounts it at `/mnt/owncloud` with the repository's hard NFSv4.2 policy.
Confirm this before deploying the stack:

```sh
findmnt --target /mnt/owncloud
sudo -u mm test -r /mnt/owncloud
sudo -u mm test -w /mnt/owncloud
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

On first installation, `post-installation.sh` enables local external storage,
mounts `/mnt/owncloud` at `/data`, selects cron background jobs, installs
Nextcloud Office, and points it at `office.local.elmurphy.com`.

## Cutover

1. Snapshot `slow/owncloud`. Back up the ownCloud MariaDB volume and
   `owncloud-data` volume. Preserve all three old `owncloud-*` volumes.
2. Create and verify the restricted NFS export and apply the `docker-host`
   Ansible role.
3. Stop ownCloud and disable its Portainer Git updates. Do not remove its
   volumes.
4. Deploy this stack as `nextcloud`. Both the new hostname and old ownCloud
   hostname route to Nextcloud, so existing clients can be repointed gradually.
5. Sign in, open `/data`, create and edit a test file, then open an Office
   document. Check the Administration overview for warnings.
6. Re-scan only if files are missing from the external mount:

   ```sh
   docker exec --user www-data nextcloud php occ files:scan --all
   ```

7. Remove the old Portainer stack after the rollback window. Keep its volumes
   until backups and Nextcloud operation have been verified.

This cutover preserves files, not ownCloud metadata. Shares, comments, tags,
calendars, contacts, and app state remain in the old database. If those records
must be retained, use Nextcloud's documented ownCloud migration path instead of
this fresh-install procedure. ownCloud 10.16 must first migrate to Nextcloud
25.0.13, followed by one-major-version-at-a-time upgrades.

## Sources

- Nextcloud Docker image: https://github.com/nextcloud/docker/
- Reverse proxy configuration: https://docs.nextcloud.com/server/stable/admin_manual/configuration_server/reverse_proxy_configuration.html
- Redis caching and file locking: https://docs.nextcloud.com/server/stable/admin_manual/configuration_server/caching_configuration.html
- Nextcloud Office Docker setup: https://docs.nextcloud.com/server/latest/admin_manual/office/example-docker.html
- ownCloud migration: https://docs.nextcloud.com/server/stable/admin_manual/maintenance/migrating_owncloud.html
