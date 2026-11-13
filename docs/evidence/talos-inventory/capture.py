#!/usr/bin/env python3
"""Read-only allowlisted Docker metadata; never retrieves Env or health output."""
import datetime
import json
from pathlib import Path
import shlex
import subprocess
import sys

out = Path(__file__).parent
prefix = sys.argv[1] if len(sys.argv) > 1 else 'before'

def remote(command):
    return subprocess.check_output(['ssh', 'docker-host', command], text=True, timeout=90)

def save(suffix, key, data):
    (out / f'{prefix}-{suffix}.json').write_text(json.dumps({
        'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        key: data,
    }, indent=2) + '\n')

ids = remote('sudo -n docker ps -q').split()
template = '''{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Config.Image}},"image_id":{{json .Image}},"created":{{json .Created}},"started":{{json .State.StartedAt}},"status":{{json .State.Status}},"restart_count":{{json .RestartCount}},"health":{{with index .State "Health"}}{{json .Status}}{{else}}null{{end}},"mounts":{{json .Mounts}},"memory_limit":{{.HostConfig.Memory}},"network_mode":{{json .HostConfig.NetworkMode}},"networks":{{json .NetworkSettings.Networks}},"compose_service":{{json (index .Config.Labels "com.docker.compose.service")}},"compose_files":{{json (index .Config.Labels "com.docker.compose.project.config_files")}}}'''
raw = remote('sudo -n docker inspect --format ' + shlex.quote(template) + ' ' + ' '.join(ids))
containers = [json.loads(line) for line in raw.splitlines()]
for container in containers:
    container['networks'] = list(container['networks'])
save('containers', 'containers', containers)
raw = remote("sudo -n docker stats --no-stream --format '{{json .}}'")
save('stats', 'stats', [json.loads(line) for line in raw.splitlines()])
print(f'Captured {len(containers)} containers; no environment values or health log output')
