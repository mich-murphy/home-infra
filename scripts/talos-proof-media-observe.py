#!/usr/bin/env python3
"""Lease-gated, sanitized append-only pod/resource evidence; never reads app logs."""
import argparse
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import uuid
import sys

safety = importlib.import_module('talos-proof-media-safety')
# Fixed read-only command. Missing cgroup v2 files are an explicit observation gap.
CGROUP = 'for f in memory.current memory.peak memory.stat memory.events; do printf "FILE %s\\n" "$f"; if test -r /sys/fs/cgroup/$f; then head -c 16384 /sys/fs/cgroup/$f; else printf "UNAVAILABLE\\n"; fi; done'


def summarize(pod):
    meta, status = pod['metadata'], pod.get('status', {})
    result = {'name': meta['name'], 'uid': meta['uid'], 'created': meta.get('creationTimestamp'),
              'phase': status.get('phase'), 'reason': status.get('reason'), 'containers': []}
    for key in ('initContainerStatuses', 'containerStatuses'):
        for item in status.get(key, []):
            result['containers'].append({k: item.get(k) for k in
                ('name', 'image', 'imageID', 'containerID', 'restartCount', 'state', 'lastState')} |
                {'init': key == 'initContainerStatuses'})
    # Termination messages may contain application output/secrets; retain only structured fields.
    for item in result['containers']:
        for key in ('state', 'lastState'):
            value = item.get(key) or {}
            item[key] = {kind: {k: v for k, v in fields.items() if k in
                ('reason', 'exitCode', 'signal', 'startedAt', 'finishedAt', 'containerID')}
                for kind, fields in value.items()}
    return result


def capture(service, state, group=None):
    safety.private_dir(state)
    ns = 'proof-' + service
    group = group or service
    if group != service and service not in safety.DEPENDENCY_BATCHES.get(group, ()):
        raise ValueError('observation member does not match dependency group')
    safety.lease(group)
    safety.exclusivity(group)
    def kube(*args):
        return safety.kube(group, '-n', ns, *args)
    pods = json.loads(kube('get', 'pods', '-o', 'json'))['items']
    output = {'service': service, 'observed_utc': datetime.now(timezone.utc).isoformat(), 'pods': [],
              'limitations': ['cgroup counters cover only current container lifetime; prior termination status retained separately',
                              'point observations do not measure an unsampled startup peak if memory.peak is unavailable']}
    for pod in pods:
        entry = summarize(pod)
        for container in entry['containers']:
            container['cgroup'] = None
            if 'running' in (container['state'] or {}):
                try:
                    payload = kube('exec', pod['metadata']['name'], '-c', container['name'], '--', '/bin/sh', '-c', CGROUP).decode()
                    # Only fixed file headers, numeric kernel counters and UNAVAILABLE may escape.
                    if len(payload) > 70000 or any(not valid_line(line) for line in payload.splitlines()):
                        raise RuntimeError('unexpected cgroup output')
                    container['cgroup'] = payload
                except Exception:
                    container['cgroup_error'] = 'UNAVAILABLE: exec/read failed or unexpected counter format'
        output['pods'].append(entry)
    filename = service + '-observation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex + '.json'
    safety.write_private(state / filename, json.dumps(output, indent=2))
    print(json.dumps({'service': service, 'observation_file': filename, 'pods': len(pods), 'result': 'OBSERVATION_ONLY'}))
    return output


def valid_line(line):
    if line in ('UNAVAILABLE', 'FILE memory.current', 'FILE memory.peak', 'FILE memory.stat', 'FILE memory.events'):
        return True
    parts = line.split()
    return (len(parts) == 1 and parts[0].isdigit()) or (len(parts) == 2 and parts[0].replace('_', '').isalnum() and parts[1].isdigit())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('service', choices=safety.SERVICES)
    p.add_argument('--group', choices=safety.DEPENDENCY_BATCHES)
    p.add_argument('--state', type=Path, required=True)
    args = p.parse_args()
    try:
        capture(args.service, args.state, args.group)
    except Exception as exc:
        print(json.dumps({'result': 'OBSERVATION_FAILED', 'error_type': type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
