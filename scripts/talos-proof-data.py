#!/usr/bin/env python3
"""Private credentials and lease-gated sequential proof lifecycle. Never logs secrets."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ('nextcloud', 'immich', 'miniflux', 'wallabag', 'couchdb', 'pocket-id')
# Includes fixture, excludes suspended cron. Conservative memory limits, MiB.
BUDGET = dict(nextcloud=1728, immich=1600, miniflux=448, wallabag=896, couchdb=256, **{'pocket-id':192})


def kube(*args, data=None):
    result = subprocess.run(['kubectl', *args], input=data, capture_output=True, text=True, timeout=960)
    if result.returncode:
        # Kubernetes errors can contain submitted manifests/credentials; never echo them.
        raise RuntimeError('kubectl operation failed: ' + ' '.join(args[:3]))
    return result.stdout


def private(path):
    p = Path(path).expanduser().resolve()
    if p == ROOT or ROOT in p.parents or p.is_symlink():
        raise RuntimeError('private state must be outside checkout')
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(p.stat().st_mode) != 0o700:
        raise RuntimeError('private state directory must have mode 0700')
    return p


def credentials(state):
    path = state / 'credentials.json'
    if path.exists():
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError('credential file must have mode 0600')
        return json.loads(path.read_text())
    result = {}
    for g in GROUPS:
        password, admin, redis = (secrets.token_hex(24) for _ in range(3))
        e = {}
        if g in ('nextcloud', 'immich', 'miniflux'):
            e['POSTGRES_PASSWORD'] = password
        if g == 'nextcloud':
            e.update(NEXTCLOUD_ADMIN_PASSWORD=admin, REDIS_HOST_PASSWORD=redis)
        elif g == 'immich':
            e.update(DB_PASSWORD=password, PROOF_ADMIN_PASSWORD=admin)
        elif g == 'miniflux':
            e.update(ADMIN_PASSWORD=admin, DATABASE_URL=f'postgres://miniflux:{password}@postgres:5432/miniflux?sslmode=disable')
        elif g == 'wallabag':
            e.update(MYSQL_ROOT_PASSWORD=secrets.token_hex(24), MARIADB_PASSWORD=password,
                     SYMFONY__ENV__DATABASE_PASSWORD=password, PROOF_ADMIN_PASSWORD=admin,
                     SYMFONY__ENV__SECRET=secrets.token_hex(32))
        elif g == 'couchdb':
            e['COUCHDB_PASSWORD'] = admin
        elif g == 'pocket-id':
            e['ENCRYPTION_KEY'] = base64.b64encode(secrets.token_bytes(32)).decode()
        result[g] = e
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(result, f)
    return result


def lease(group):
    if not os.environ.get('KUBECONFIG'):
        raise RuntimeError('explicit proof-only KUBECONFIG required')
    p = Path(os.environ.get('TALOS_PROOF_DATA_LEASE', '/nonexistent'))
    # Parent supplies a private JSON receipt: {"group":"...", "context":"...", "expires": UNIX_TIME}.
    import time
    receipt = json.loads(p.read_text())
    context = kube('config', 'current-context').strip()
    if receipt['group'] != group or receipt['context'] != context or receipt['expires'] <= time.time():
        raise RuntimeError('missing, expired, or mismatched coordinator resource lease')
    return receipt


def guard(group):
    # Fail closed without metrics. Limits plus measured node working set must leave 192MiB.
    pods = json.loads(kube('get', 'pods', '-A', '-l', 'app.kubernetes.io/part-of=talos-proof', '-o', 'json'))
    if any(p['metadata']['namespace'] not in ('proof-' + group, 'proof-validation', 'proof-gateway') and p.get('status', {}).get('phase') not in ('Succeeded', 'Failed') for p in pods['items']):
        raise RuntimeError('another proof group has live pods; release its lease first')
    nodes = json.loads(kube('get', 'nodes', '-o', 'json'))['items']
    if len(nodes) != 1:
        raise RuntimeError('expected dedicated single proof node')
    alloc = nodes[0]['status']['allocatable']['memory']
    if not alloc.endswith('Ki'):
        raise RuntimeError('unsupported node memory units')
    try:
        metric = json.loads(kube('get', '--raw', '/apis/metrics.k8s.io/v1beta1/nodes'))['items'][0]['usage']['memory']
    except RuntimeError:
        # This minimal platform intentionally has no metrics-server. Parent can supply
        # a fresh Talos guest available-memory observation, not host/Proxmox free RAM.
        import time
        receipt = lease(group)
        age = time.time() - receipt.get('measured_at', 0)
        if not 0 <= age <= 120:
            raise RuntimeError('fresh guest available-memory measurement required in lease')
        available = receipt.get('available_mib', 0)
        if not isinstance(available, (int, float)) or available > int(alloc[:-2]) / 1024:
            raise RuntimeError('invalid lease memory observation')
    else:
        if not metric.endswith('Ki'):
            raise RuntimeError('unsupported metrics memory units')
        available = (int(alloc[:-2]) - int(metric[:-2])) / 1024
    if available < BUDGET[group] + 192:
        raise RuntimeError('insufficient memory headroom for group limits plus 192MiB reserve')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'apply', 'activate', 'deactivate', 'test', 'run'])
    p.add_argument('--group', choices=GROUPS)
    p.add_argument('--state', required=True, help='outside-git private directory, mode0700')
    a = p.parse_args()
    os.umask(0o077)
    state = private(a.state)
    creds = credentials(state)
    if a.action == 'prepare':
        print('Fresh proof credentials available privately (values never displayed).')
        return
    if not a.group:
        p.error('--group required for cluster operations')
    lease(a.group)
    ns = 'proof-' + a.group
    if a.action == 'apply':
        kube('apply', '-k', str(ROOT / 'kubernetes/apps/data' / a.group))
        manifest = {'apiVersion':'v1','kind':'Secret','metadata':{'name':'proof-credentials','namespace':ns},'type':'Opaque','stringData':creds[a.group]}
        kube('apply', '-f', '-', data=json.dumps(manifest))
    elif a.action in ('activate', 'run'):
        guard(a.group)
        try:
            kube('-n', ns, 'scale', 'deployment', '--all', '--replicas=1')
            kube('-n', ns, 'wait', '--for=condition=available', 'deployment', '--all', '--timeout=900s')
            if a.group == 'wallabag':
                kube('-n', ns, 'exec', 'deployment/wallabag', '--', 'sh', '-ec', 'cd /var/www/wallabag; php bin/console fos:user:change-password wallabag "$PROOF_ADMIN_PASSWORD" --no-interaction')
            if a.action == 'run':
                subprocess.run([sys.executable, str(ROOT / 'tests/talos-proof-data-live.py'), a.group, str(state)], check=True, timeout=1800)
        finally:
            if a.action == 'run' or sys.exc_info()[0] is not None:
                # Cleanup remains valid if the lease expires while the bounded test runs.
                kube('-n', ns, 'scale', 'deployment', '--all', '--replicas=0')
                kube('-n', ns, 'wait', '--for=delete', 'pod', '--all', '--timeout=180s')
    elif a.action == 'deactivate':
        kube('-n', ns, 'scale', 'deployment', '--all', '--replicas=0')
        kube('-n', ns, 'wait', '--for=delete', 'pod', '--all', '--timeout=180s')
    else:
        subprocess.run([sys.executable, str(ROOT / 'tests/talos-proof-data-live.py'), a.group, str(state)], check=True, timeout=1800)
    print(a.action + ': ' + a.group + ' completed')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not leak HTTP bodies, command errors or credentials in tracebacks.
        print('Data proof stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
