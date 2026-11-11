#!/usr/bin/env python3
"""Bounded read-only allocation scans through existing containers, four at once."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import shlex
import subprocess

out = Path(__file__).parent
containers = json.loads((out / 'before-containers.json').read_text())['containers']
seen = set()
jobs = []
for c in containers:
    for m in c['mounts']:
        source = m['Source']
        if source in seen or source in ['/run', '/etc/localtime'] or source.endswith(('.yml', '.yaml')):
            continue
        seen.add(source)
        jobs.append((c['name'].lstrip('/'), source, m['Destination']))

def scan(job):
    name, source, target = job
    # timeout runs IN the container, so terminating SSH cannot leave an unbounded scan.
    command = 'sudo -n docker exec ' + shlex.quote(name) + ' timeout 8 du -skx ' + shlex.quote(target)
    r = subprocess.run(['ssh', 'docker-host', command], capture_output=True, text=True, timeout=25)
    # du output includes target only; no filenames or file contents are collected.
    return dict(container=name, source=source, target=target, command=command,
                exit_code=r.returncode, stdout=r.stdout.strip(), stderr=r.stderr.strip())

with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(scan, jobs))
(out / 'sizes.json').write_text(json.dumps(dict(captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    method='allocated KiB; du -x; hard 8-second per-path timeout; max four scans; timeout/error means UNKNOWN not zero',
    scans=results), indent=2) + '\n')
for r in results:
    print(r['container'], r['source'], r['exit_code'], r['stdout'] or r['stderr'])
