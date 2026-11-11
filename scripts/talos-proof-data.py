#!/usr/bin/env python3
"""Private credentials and lease-gated sequential proof lifecycle. Never logs secrets."""
import argparse
import base64
import json
import math
import hashlib
import time
import re
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ENDPOINT = 'https://127.0.0.1:64120'
EXPECTED_HOSTNAME = 'talos-proof'
LEASE_GROUP = None
LEASE_STAGE = None
STATE_DIR = None
CANONICAL_DATA_STATE = Path.home()/".local/state/talos-data-proof"
MUTATIONS = {'apply','scale','exec','rollout','delete','create','patch','label','annotate','run','replace','cp','edit','set'}
GROUPS = ('nextcloud', 'immich', 'miniflux', 'wallabag', 'couchdb', 'pocket-id')
# Includes fixture, excludes suspended cron. Conservative memory limits, MiB.
BUDGET = dict(nextcloud=1920, immich=2240, miniflux=448, wallabag=576, couchdb=256, **{'pocket-id':192})

# Explicit coordinator-approved component stages; no implicit heavy-group activation.
STAGES = {
    'nextcloud': {
        'web': ('nextcloud', 'postgres', 'redis'),
        'cron': ('postgres', 'redis'),
        'collabora': ('collabora',),
        'wopi': ('collabora', 'wopi-fixture'),
        'full': ('nextcloud', 'postgres', 'redis', 'collabora'),
    },
    'immich': {
        'app': ('immich', 'postgres', 'valkey'),
        'ml': ('ml',),
        'full': ('immich', 'ml', 'postgres', 'valkey'),
    },
}
LIMITS = {'nextcloud':640, 'postgres-nextcloud':384, 'redis':64, 'collabora':768,
          'immich':768, 'ml':1024, 'postgres-immich':384, 'valkey':64, 'wopi-fixture':64}


def selection(group, stage=None):
    stage = LEASE_STAGE if stage is None else stage
    if group not in STAGES:
        if stage is not None:
            raise RuntimeError('component stages are only defined for heavy groups')
        return None, BUDGET[group]
    if stage not in STAGES[group]:
        raise RuntimeError('heavy group requires an explicit component stage')
    names = STAGES[group][stage]
    budget = sum(LIMITS.get(name + '-' + group, LIMITS.get(name, 0)) for name in names)
    if group == 'nextcloud' and stage == 'cron':
        budget += 192  # one bounded Job from the suspended CronJob, never concurrent web
    return names, budget


def selected_controllers(group):
    names, _ = selection(group)
    result = ['deployment/' + name for name in names] if names else []
    if group == 'nextcloud' and LEASE_STAGE == 'cron':
        result.append('cronjob/nextcloud-cron')
    return sorted(result)


def helper_deletion_barrier():
    """Do not start an application while any proof Job pod still exists."""
    pods = json.loads(kube('get', 'pods', '-A', '-o', 'json'))['items']
    for pod in pods:
        meta = pod['metadata']
        if meta['namespace'].startswith('proof-') and any(owner['kind']=='Job' for owner in meta.get('ownerReferences', [])):
            kube('-n', meta['namespace'], 'wait', '--for=delete', 'pod/' + meta['name'], '--timeout=180s')


def scale_selected(ns, replicas):
    if replicas:
        helper_deletion_barrier()
    names, _ = selection(LEASE_GROUP)
    targets = ['deployment/' + name for name in names] if names else ['deployment', '--all']
    kube('-n', ns, 'scale', *targets, '--replicas=' + str(replicas))
    if replicas:
        kube('-n', ns, 'wait', '--for=condition=available', *targets, '--timeout=900s')


def destructive(args):
    return (bool({'delete','apply','replace','set'}.intersection(args)) or ('scale' in args and '--replicas=0' in args) or
            ('rollout' in args and 'restart' in args) or ('patch' in args and any('deployment' in arg for arg in args)))


def capture_forensics(namespace, phase):
    """Off-node API reads only. Raw previous logs never enter public stdout/evidence."""
    if namespace != 'proof-' + str(LEASE_GROUP):
        raise RuntimeError('forensics limited to the leased group')
    if STATE_DIR is None:
        raise RuntimeError('private forensic state directory required before deletion')
    state = private(STATE_DIR)
    def write(name, data):
        path = no_symlinks(state / name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(data)
        return {'file':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    lease(LEASE_GROUP)
    proc = subprocess.run(['kubectl','-n',namespace,'get','pods','-o','json'],capture_output=True,check=True,timeout=30)
    raw_status = write('pod-status-' + str(uuid.uuid4()) + '.json', proc.stdout)
    record = {'phase':phase, 'observed_at':time.time(), 'pods':[], 'private_raw_status':raw_status}
    for pod in json.loads(proc.stdout)['items']:
        item = {'uid':pod['metadata']['uid'], 'phase':pod.get('status',{}).get('phase'), 'containers':[]}
        for status in pod.get('status',{}).get('initContainerStatuses',[]) + pod.get('status',{}).get('containerStatuses',[]):
            container = {key:status[key] for key in ('name','containerID','imageID','restartCount') if key in status}
            for field in ('state','lastState'):
                container[field]={}
                for kind,value in status.get(field,{}).items():
                    safe = {key:value[key] for key in ('exitCode','signal','startedAt','finishedAt') if key in value}
                    if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',value.get('reason','')): safe['reason']=value['reason']
                    container[field][kind]=safe
            # Completed/failed short-lived CLI pods still have current logs.
            if status.get('state'):
                lease(LEASE_GROUP)
                try:
                    logs = subprocess.run(['kubectl','-n',namespace,'logs',pod['metadata']['name'],'-c',status['name'],'--timestamps=true','--tail=2000','--limit-bytes=1048576'],capture_output=True,timeout=30)
                    if logs.returncode==0:
                        container['current_logs']=write('current-log-'+str(uuid.uuid4())+'.txt',logs.stdout)
                    else: container['current_logs_gap']='APIUnavailable'
                except subprocess.TimeoutExpired:
                    container['current_logs_gap']='TimeoutExpired'
            if status.get('restartCount',0):
                lease(LEASE_GROUP)
                try:
                    logs = subprocess.run(['kubectl','-n',namespace,'logs',pod['metadata']['name'],'-c',status['name'],'--previous','--timestamps=true','--limit-bytes=1048576'],capture_output=True,timeout=30)
                    if logs.returncode==0:
                        container['previous_logs']=write('previous-log-'+str(uuid.uuid4())+'.txt',logs.stdout)
                    else: container['previous_logs_gap']='APIUnavailable'
                except subprocess.TimeoutExpired:
                    container['previous_logs_gap']='TimeoutExpired'
            item['containers'].append(container)
        record['pods'].append(item)
    saved = write('pod-forensics-'+str(uuid.uuid4())+'.json',json.dumps(record).encode())
    # No raw states/messages, account data or log contents in public metadata.
    return {'phase':phase,'sha256':saved['sha256']}


def kube(*args, data=None):
    if MUTATIONS.intersection(args):
        if LEASE_GROUP not in GROUPS:
            raise RuntimeError('mutation requires an explicitly selected proof group')
        lease(LEASE_GROUP)
        if destructive(args):
            try: capture_forensics('proof-' + LEASE_GROUP, 'before mutation')
            except Exception as error: print('Forensic capture gap: ' + type(error).__name__, file=sys.stderr)
    result = subprocess.run(['kubectl', *args], input=data, capture_output=True, text=True, timeout=960)
    if result.returncode:
        # Kubernetes errors can contain submitted manifests/credentials; never echo them.
        raise RuntimeError('kubectl operation failed: ' + ' '.join(args[:3]))
    return result.stdout


def no_symlinks(path):
    """Check the original path AND each existing ancestor before any resolve/open."""
    expanded = Path(os.path.expanduser(str(path)))
    if '..' in expanded.parts:
        raise RuntimeError('parent traversal is forbidden in private state paths')
    p = Path(os.path.abspath(expanded))
    for part in (p, *p.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError('symlinks are forbidden in private state paths')
    return p


def private(path):
    p = no_symlinks(path)
    # Check checkout containment using canonical location, after rejecting links.
    canonical = p.resolve()
    if canonical == ROOT or ROOT in canonical.parents:
        raise RuntimeError('private state must be outside checkout')
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = p.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('private state directory must have mode 0700')
    return p


def credentials(state):
    path = no_symlinks(state / 'credentials.json')
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
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
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(result, f)
    return result


def target_identity(receipt):
    """Bind every mutation to exact loopback endpoint and coordinator-recorded node."""
    config = json.loads(kube('config', 'view', '--minify', '-o', 'json'))
    clusters = config.get('clusters', [])
    if len(clusters) != 1:
        raise RuntimeError('expected exactly one active kubeconfig cluster')
    cluster = clusters[0]['cluster']
    if cluster.get('server') != EXPECTED_ENDPOINT or receipt.get('endpoint') != EXPECTED_ENDPOINT:
        raise RuntimeError('proof endpoint must be exactly https://127.0.0.1:64120')
    if cluster.get('insecure-skip-tls-verify'):
        raise RuntimeError('proof API TLS verification must not be disabled')
    nodes = json.loads(kube('get', 'nodes', '-o', 'json'))['items']
    if len(nodes) != 1:
        raise RuntimeError('expected exactly one dedicated proof node')
    meta = nodes[0]['metadata']
    if meta.get('name') != EXPECTED_HOSTNAME or meta.get('labels', {}).get('kubernetes.io/hostname') != EXPECTED_HOSTNAME:
        raise RuntimeError('node must be named and labelled talos-proof')
    if not receipt.get('node_uid') or meta.get('uid') != receipt['node_uid']:
        raise RuntimeError('proof node UID differs from coordinator receipt')
    return nodes[0]


def lease(group):
    if not os.environ.get('KUBECONFIG'):
        raise RuntimeError('explicit proof-only KUBECONFIG required')
    p = no_symlinks(os.environ.get('TALOS_PROOF_DATA_LEASE', '/nonexistent'))
    import time
    info = p.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError('resource lease must be a regular private 0600 file')
    receipt = json.loads(p.read_text())
    context = kube('config', 'current-context').strip()
    if receipt.get('group') != group or receipt.get('context') != context or receipt.get('expires', 0) <= time.time():
        raise RuntimeError('missing, expired, or mismatched coordinator resource lease')
    if group in STAGES:
        selection(group)
        if receipt.get('stage') != LEASE_STAGE or receipt.get('selected_controllers') != selected_controllers(group):
            raise RuntimeError('lease must explicitly approve stage and exact sorted selected_controllers')
    target_identity(receipt)
    return receipt


def participants(group):
    names, _ = selection(group)
    controllers = json.loads(kube('get','deployments,statefulsets','-A','-o','json'))['items']
    if any(c['metadata']['namespace'].startswith('proof-') and
           c['metadata']['namespace'] not in ('proof-'+group,'proof-validation','proof-gateway') and
           c['spec'].get('replicas',1) for c in controllers):
        raise RuntimeError('another proof group has an active controller, including without pods')
    if names:
        deployments = json.loads(kube('-n', 'proof-' + group, 'get', 'deployments', '-o', 'json'))['items']
        if any(d['metadata']['name'] not in names and d['spec'].get('replicas', 0) for d in deployments):
            raise RuntimeError('unselected controller has active replicas in staged boundary')
        cronjobs = json.loads(kube('-n', 'proof-' + group, 'get', 'cronjobs', '-o', 'json'))['items']
        jobs = json.loads(kube('-n', 'proof-' + group, 'get', 'jobs', '-o', 'json'))['items']
        if any(not c['spec'].get('suspend', False) for c in cronjobs) or any(j.get('status', {}).get('active', 0) for j in jobs):
            raise RuntimeError('staged admission requires suspended schedules and no active Jobs')
    # Fail closed without metrics. Limits plus measured node working set must leave 192MiB.
    pods = json.loads(kube('get', 'pods', '-A', '-l', 'app.kubernetes.io/part-of=talos-proof', '-o', 'json'))
    if any(p['metadata']['namespace'] not in ('proof-' + group, 'proof-validation', 'proof-gateway') and p.get('status', {}).get('phase') not in ('Succeeded', 'Failed') for p in pods['items']):
        raise RuntimeError('another proof group has live pods; release its lease first')
    if names:
        for pod in pods['items']:
            if pod['metadata']['namespace'] != 'proof-' + group or pod.get('status', {}).get('phase') in ('Succeeded','Failed'):
                continue
            # Cron may only run after the admission check, never alongside a previous Job.
            owners = pod['metadata'].get('ownerReferences', [])
            app = pod['metadata'].get('labels', {}).get('app.kubernetes.io/name')
            if app not in names or any(o['kind'] == 'Job' for o in owners):
                raise RuntimeError('unselected participant has live pods in staged boundary')
def guard(group):
    participants(group)
    _, budget = selection(group)
    nodes = json.loads(kube('get', 'nodes', '-o', 'json'))['items']
    if len(nodes) != 1:
        raise RuntimeError('expected dedicated single proof node')
    alloc = nodes[0]['status']['allocatable']['memory']
    if not alloc.endswith('Ki'):
        raise RuntimeError('unsupported node memory units')
    # Kubelet eviction availability and Talos MemAvailable differ under active file
    # cache. Require both independently measured signals; never infer from RSS.
    import time
    receipt = lease(group)
    age = time.time() - receipt.get('measured_at', 0)
    values = [receipt.get('kubelet_available_mib'), receipt.get('talos_available_mib')]
    if not 0 <= age <= 120:
        raise RuntimeError('fresh kubelet AND Talos available-memory measurements required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 < v <= int(alloc[:-2])/1024 for v in values):
        raise RuntimeError('valid kubelet AND Talos available-memory measurements required')
    available = min(values)
    if available < budget + 192:
        raise RuntimeError('insufficient memory headroom for group limits plus 192MiB reserve')


def shared_data_state(state):
    if no_symlinks(state).resolve() != CANONICAL_DATA_STATE.resolve():
        raise RuntimeError('canonical shared data journal directory required')
    return private(state)


def native_cron_events(state):
    events = []
    for path in state.glob('*.json'):
        try:
            ident = uuid.UUID(path.stem)
            if str(ident) != path.stem: continue
        except ValueError: continue
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError('unsafe UUID journal')
        value = json.loads(path.read_text())
        if not isinstance(value, dict): raise RuntimeError('invalid UUID journal')
        if isinstance(value.get('event'), str): events.append(value)
    return events


def pending_native_cron(state):
    """Run UUID reuse is forbidden; count imbalance also fails closed for old journals."""
    counts = {}
    for value in native_cron_events(state):
        if value.get('event') in ('pending', 'clean'):
            run = value['run_id']
            counts.setdefault(run, [0, 0])[value['event'] == 'clean'] += 1
    return {run for run, (pending, clean) in counts.items() if pending > clean or pending > 1}


def main():
    global LEASE_GROUP, LEASE_STAGE, STATE_DIR
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'apply', 'activate', 'deactivate', 'test', 'run', 'verify'])
    p.add_argument('--group', choices=GROUPS)
    p.add_argument('--stage', help='explicit heavy-group component stage approved in lease')
    p.add_argument('--state', required=True, help='outside-git private directory, mode0700')
    a = p.parse_args()
    if a.group == 'nextcloud' and a.stage == 'cron' and a.action in ('activate', 'run', 'test'):
        # Stop before credentials(), API reads or mutation. The former lastcron-only
        # path is not the native retention proof and must not earn acceptance.
        raise RuntimeError('Native cron integration BLOCKED; see docs/talos-proof-nextcloud-cron-plan.md')
    os.umask(0o077)
    state = shared_data_state(a.state)
    STATE_DIR = state
    if a.group == 'nextcloud' and a.action in ('apply', 'activate', 'run', 'test') and pending_native_cron(state):
        raise RuntimeError('pending native cron cleanup blocks unsafe activation')
    creds = credentials(state)
    if a.action == 'prepare':
        print('Fresh proof credentials available privately (values never displayed).')
        return
    if not a.group:
        p.error('--group required for cluster operations')
    LEASE_GROUP = a.group
    LEASE_STAGE = a.stage
    selection(a.group)
    lease(a.group)
    ns = 'proof-' + a.group
    if a.action == 'verify':
        print('Verified coordinator lease, exact endpoint and recorded proof node identity.')
        return
    if a.action == 'apply':
        participants(a.group)
        kube('apply', '-k', str(ROOT / 'kubernetes/apps/data' / a.group))
        manifest = {'apiVersion':'v1','kind':'Secret','metadata':{'name':'proof-credentials','namespace':ns},'type':'Opaque','stringData':creds[a.group]}
        kube('apply', '-f', '-', data=json.dumps(manifest))
    elif a.action in ('activate', 'run'):
        guard(a.group)
        try:
            scale_selected(ns, 1)
            if a.group == 'wallabag':
                kube('-n', ns, 'exec', 'deployment/wallabag', '--', 'sh', '-ec', 'cd /var/www/wallabag; php bin/console --env=prod fos:user:change-password wallabag "$PROOF_ADMIN_PASSWORD" --no-interaction')
            if a.action == 'run':
                subprocess.run([sys.executable, str(ROOT / 'tests/talos-proof-data-live.py'), a.group, str(state), *(['--stage', a.stage] if a.stage else [])], check=True, timeout=1800)
        finally:
            if a.action == 'run' or sys.exc_info()[0] is not None:
                # Cleanup also revalidates endpoint/node and requires an unexpired lease.
                if a.group == 'nextcloud' and a.stage == 'cron':
                    kube('-n', ns, 'delete', 'job', 'nextcloud-cron-proof', '--ignore-not-found=true', '--wait=true', '--timeout=180s')
                scale_selected(ns, 0)
                kube('-n', ns, 'wait', '--for=delete', 'pod', '--all', '--timeout=180s')
    elif a.action == 'deactivate':
        scale_selected(ns, 0)
        kube('-n', ns, 'wait', '--for=delete', 'pod', '--all', '--timeout=180s')
    else:
        subprocess.run([sys.executable, str(ROOT / 'tests/talos-proof-data-live.py'), a.group, str(state), *(['--stage', a.stage] if a.stage else [])], check=True, timeout=1800)
    print(a.action + ': ' + a.group + ' completed')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not leak HTTP bodies, command errors or credentials in tracebacks.
        print('Data proof stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
