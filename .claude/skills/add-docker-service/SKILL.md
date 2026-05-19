---
name: add-docker-service
description: Add a new Docker Compose service stack to the homelab. Use when adding a new application or service.
argument-hint: [service-name]
---

# Add Docker Service

Add a new Docker Compose service called $ARGUMENTS to the homelab.

## Steps

1. Create `docker/$ARGUMENTS/compose.yml`
2. Read `docker/init/compose.yml` for reference on the established patterns
3. Follow these conventions in the new compose file:
   - Pin the image to a SHA256 digest
   - Add `security_opt: no-new-privileges:true` to all containers
   - Join the `proxy` network for Traefik routing
   - Add Traefik labels: `traefik.enable=true`, router rule with `Host()`, `tls=true`, loadbalancer server port
   - Domain pattern: `$ARGUMENTS.local.elmurphy.com`
   - Mount `/etc/localtime:/etc/localtime:ro` if the service needs timezone awareness
   - Set `restart: unless-stopped`
   - If the service needs a database, create an isolated internal backend network with an explicit subnet (check existing compose files for the next available 172.x.1.0/24 range)
   - Use named volumes for persistent data
   - Use environment variables for any secrets — never hardcode
   - Media services: set `PUID=1215` and `PGID=1215`
   - Other services: set `PUID=1000` and `PGID=1000` where applicable

4. If the service needs NFS-backed storage, add appropriate volume mounts under `/mnt/data/`
5. If the service needs GPU access (transcoding), add device passthrough for `/dev/dri`
6. Validate the compose file: `cd docker/$ARGUMENTS && docker compose config`
