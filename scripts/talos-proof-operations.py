#!/usr/bin/env python3
"""Bounded, external operational proof. No resident monitoring stack or production access."""
import argparse
import datetime
import hashlib
import http.server
import json
import os
import stat
import time
import sys
from pathlib import Path
import subprocess
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / '.local/state/home-infra/talos-proof'
NS = 'proof-operations-recovery'
ENDPOINT = 'https://127.0.0.1:64120'
NODE_UID = '4845bfd5-3bdb-453d-8503-83b43edb7a1e'
GROUP = 'operations'


def run(args, **kw):
    # Errors intentionally omit command output: credentials/server responses stay private.
    p = subprocess.run(args, stderr=subprocess.PIPE, timeout=240, **kw)
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed ({p.returncode}); output withheld')
    return p.stdout


def no_symlinks(path):
    p = Path(os.path.expanduser(str(path)))
    if '..' in p.parts:
        raise RuntimeError('parent traversal forbidden')
    p = Path(os.path.abspath(p))
    for part in (p, *p.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError('symlink in private path forbidden')
    return p


def private_file(path):
    p = no_symlinks(path)
    root = no_symlinks(STATE)
    if not p.is_relative_to(root):
        raise RuntimeError('file must be under private proof state')
    for directory in (p.parent, *p.parent.parents):
        if not directory.is_relative_to(root):
            break
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
            raise RuntimeError('private directories must be owned mode 0700')
    info = p.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()):
        raise RuntimeError('private file must be owned regular mode 0600')
    return p


def raw_kube(config, *args, **kw):
    return run(['kubectl', '--kubeconfig', str(config), '--request-timeout=30s', *args], **kw)


def gate(group=None):
    group = group or GROUP
    config = private_file(os.environ.get('KUBECONFIG', '/nonexistent'))
    receipt_path = private_file(os.environ.get('TALOS_PROOF_OPERATIONS_LEASE', '/nonexistent'))
    receipt = json.loads(receipt_path.read_text())
    now = time.time()
    if (receipt.get('group') != group or group not in ('operations', 'operations-flux')
            or not isinstance(receipt.get('expires'), (int, float)) or receipt['expires'] <= now
            or receipt.get('endpoint') != ENDPOINT or receipt.get('node_uid') != NODE_UID
            or not isinstance(receipt.get('available_mib'), (int, float)) or receipt['available_mib'] <= 0
            or not isinstance(receipt.get('measured_at'), (int, float))
            or not 0 <= now - receipt['measured_at'] <= 120):
        raise RuntimeError('missing, stale or mismatched coordinator lease')
    cfg = json.loads(raw_kube(config, 'config', 'view', '--minify', '-o', 'json', stdout=subprocess.PIPE))
    contexts, clusters = cfg.get('contexts', []), cfg.get('clusters', [])
    context = cfg.get('current-context')
    if (not context or receipt.get('context') != context or len(contexts) != 1 or len(clusters) != 1
            or contexts[0].get('name') != context
            or contexts[0].get('context', {}).get('cluster') != clusters[0].get('name')):
        raise RuntimeError('inconsistent kubeconfig context/cluster binding')
    cluster = clusters[0]['cluster']
    if (cluster.get('server') != ENDPOINT or cluster.get('insecure-skip-tls-verify')
            or cluster.get('proxy-url') or cluster.get('tls-server-name')):
        raise RuntimeError('exact proof endpoint with verified TLS required')
    users = cfg.get('users', [])
    if (len(users) != 1 or contexts[0]['context'].get('user') != users[0].get('name')):
        raise RuntimeError('inconsistent kubeconfig user binding')
    user = users[0].get('user', {})
    if user.get('exec') or user.get('auth-provider'):
        raise RuntimeError('credential subprocess/providers forbidden for isolated proof')
    for settings, keys in [(cluster, ('certificate-authority',)),
                            (user, ('client-certificate', 'client-key', 'tokenFile'))]:
        for key in keys:
            if settings.get(key):
                reference = Path(settings[key])
                private_file(reference if reference.is_absolute() else config.parent / reference)
    nodes = json.loads(raw_kube(config, '--context', context, 'get', 'nodes', '-o', 'json', stdout=subprocess.PIPE))['items']
    if len(nodes) != 1:
        raise RuntimeError('expected dedicated single-node proof')
    node = nodes[0]
    meta = node['metadata']
    ips = [a['address'] for a in node.get('status', {}).get('addresses', []) if a['type'] == 'InternalIP']
    if (meta.get('name') != 'talos-proof' or meta.get('uid') != NODE_UID
            or meta.get('labels', {}).get('kubernetes.io/hostname') != 'talos-proof'
            or ips != ['172.31.250.10']):
        raise RuntimeError('proof node identity mismatch')
    return node


def kube(*args, **kw):
    # Revalidate before EVERY command, including exec, waits, and failure cleanup.
    gate()
    config = private_file(os.environ['KUBECONFIG'])
    receipt = json.loads(private_file(os.environ['TALOS_PROOF_OPERATIONS_LEASE']).read_text())
    return raw_kube(config, '--context', receipt['context'], '--server', ENDPOINT, *args, **kw)


def obj(*args):
    return json.loads(kube(*args, stdout=subprocess.PIPE))


def private_dir():
    root = no_symlinks(STATE)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise RuntimeError('private state directory must have mode 0700')
    parent = no_symlinks(root / 'operations')
    parent.mkdir(mode=0o700, exist_ok=True)
    if stat.S_IMODE(parent.lstat().st_mode) != 0o700:
        raise RuntimeError('operations directory must have mode 0700')
    out = parent / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out.mkdir(mode=0o700)
    return out


def summarize(node, summary, pods):
    """Allowlist operational measurements; never retain arbitrary API objects."""
    return {
        'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'node': node['metadata']['name'],
        'capacity': node['status']['capacity'],
        'allocatable': node['status']['allocatable'],
        'conditions': {c['type']: c['status'] for c in node['status'].get('conditions', [])},
        'memory': summary['node'].get('memory', {}),
        'filesystem': summary['node'].get('fs', {}),
        'pods': [{'namespace': p['podRef']['namespace'], 'name': p['podRef']['name'],
                  'memory': p.get('memory', {}), 'volumes': [
                      {k: v[k] for k in ('name', 'usedBytes', 'capacityBytes', 'availableBytes') if k in v}
                      for v in p.get('volume', [])],
                  'containers': [{'name': c['name'], 'memory': c.get('memory', {})}
                                 for c in p.get('containers', [])]} for p in summary.get('pods', [])],
        'restarts': [{'namespace': p['metadata']['namespace'], 'pod': p['metadata']['name'],
                      'containers': [{'name': c['name'], 'restartCount': c['restartCount']}
                                     for c in p.get('status', {}).get('containerStatuses', [])]}
                     for p in pods['items']],
    }


def alerts(sample, minimum_available, injected=False):
    result = []
    available = sample['memory'].get('availableBytes')
    if available is None:
        raise RuntimeError('node memory availableBytes missing; cannot evaluate alert')
    if available < minimum_available:
        result.append({'rule': 'NodeMemoryHeadroomLow', 'availableBytes': available,
                       'thresholdBytes': minimum_available})
    for p in sample['restarts']:
        for c in p['containers']:
            if c['restartCount']:
                result.append({'rule': 'ContainerRestartObserved', **p, 'container': c})
    if injected:
        result.append({'rule': 'ProofDeliveryTest', 'synthetic': True})
    return result


def deliver(events, path):
    """Local loopback sink; no caller-selected destination or external notifications."""
    received = []
    class Sink(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get('Content-Length', '0'))
            if n > 65536:
                self.send_error(413)
                return
            received.append(json.loads(self.rfile.read(n)))
            self.send_response(204)
            self.end_headers()
        def log_message(self, *args):
            pass
    with http.server.HTTPServer(('127.0.0.1', 0), Sink) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for event in events:
                request = urllib.request.Request(
                    f'http://127.0.0.1:{server.server_port}/proof-alert',
                    data=json.dumps(event).encode(), headers={'Content-Type': 'application/json'})
                # Explicitly bypass environment proxies, even for loopback.
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as r:
                    if r.status != 204:
                        raise RuntimeError('sink rejected alert')
        finally:
            server.shutdown()
            worker.join()
    if received != events:
        raise RuntimeError('alert delivery mismatch')
    path.write_text(json.dumps({'transport': 'HTTP loopback only', 'received': received}, indent=2) + '\n')


def monitor(node, out, args):
    name = node['metadata']['name']
    summary = obj('get', '--raw', f'/api/v1/nodes/{name}/proxy/stats/summary')
    sample = summarize(node, summary, obj('get', 'pods', '-A', '-o', 'json'))
    (out / 'measurements.json').write_text(json.dumps(sample, indent=2) + '\n')
    events = alerts(sample, args.minimum_available_mib * 1024**2, args.test_alert)
    deliver(events, out / 'alert-receipts.json')


def recovery(out):
    # A rerun must never adopt or overwrite an existing namespace/PVC/pod.
    if any(n['metadata']['name'] == NS for n in obj('get', 'namespaces', '-o', 'json')['items']):
        raise RuntimeError('recovery namespace already exists; explicit disposal approval required')
    attempted = False
    try:
        attempted = True
        kube('apply', '-k', str(ROOT / 'kubernetes/operations/recovery'), stdout=subprocess.DEVNULL)
        for pod in ('source', 'restored'):
            kube('-n', NS, 'wait', '--for=condition=Ready', f'pod/{pod}', '--timeout=180s', stdout=subprocess.DEVNULL)
        claims = obj('-n', NS, 'get', 'pvc', '-o', 'json')['items']
        ids = {p['metadata']['name']: {'uid': p['metadata']['uid'], 'volume': p['spec']['volumeName']} for p in claims}
        if (set(ids) != {'source', 'restored'} or ids['source']['uid'] == ids['restored']['uid']
                or ids['source']['volume'] == ids['restored']['volume']):
            raise RuntimeError('source and restored must be distinct PVCs and PVs')
        for claim in ids.values():
            pv = obj('get', 'pv', claim['volume'], '-o', 'json')
            if (pv['spec'].get('persistentVolumeReclaimPolicy') != 'Retain'
                    or pv['spec'].get('claimRef', {}).get('uid') != claim['uid']):
                raise RuntimeError('recovery volumes must be bound to exact claims and retained')
        pod_status = obj('-n', NS, 'get', 'pods', '-o', 'json')
        images = [{'pod': p['metadata']['name'], 'containers': [
            {k: c.get(k) for k in ('name', 'image', 'imageID', 'restartCount')}
            for c in p.get('status', {}).get('containerStatuses', [])]}
            for p in pod_status['items']]
        for pod in ('source', 'restored'):
            kube('-n', NS, 'exec', pod, '--', 'sh', '-ec', 'test -z "$(ls -A /data)"', stdout=subprocess.DEVNULL)
        payload = b'talos-proof isolated off-node recovery fixture v1\n'
        digest = hashlib.sha256(payload).hexdigest()
        kube('-n', NS, 'exec', '-i', 'source', '--', 'sh', '-ec',
             'set -C; cat > /data/fixture.txt', input=payload, stdout=subprocess.DEVNULL)
        archive = no_symlinks(out / 'fixture.tar')
        with archive.open('xb') as f:
            kube('-n', NS, 'exec', 'source', '--', 'tar', '-C', '/data', '-cf', '-', 'fixture.txt', stdout=f)
        kube('-n', NS, 'delete', 'pod', 'source', '--wait=true', stdout=subprocess.DEVNULL)
        # Recheck destination immediately before extraction; never overwrite existing files.
        kube('-n', NS, 'exec', 'restored', '--', 'sh', '-ec', 'test -z "$(ls -A /data)"', stdout=subprocess.DEVNULL)
        with archive.open('rb') as f:
            kube('-n', NS, 'exec', '-i', 'restored', '--', 'tar', '-C', '/data', '-xkf', '-', stdin=f, stdout=subprocess.DEVNULL)
        restored = kube('-n', NS, 'exec', 'restored', '--', 'cat', '/data/fixture.txt', stdout=subprocess.PIPE)
        if hashlib.sha256(restored).hexdigest() != digest:
            raise RuntimeError('restored checksum mismatch')
        (out / 'recovery.json').write_text(json.dumps({'claims': ids, 'fixture_sha256': digest,
            'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'off_node': True, 'source_pod_deleted_before_restore': True,
            'source_empty_before_write': True, 'destination_empty_before_restore': True,
            'runtime_images': images,
            'retained_pvs': True, 'restored_checksum_matches': True,
            'application_consistency': 'static synthetic file only'}, indent=2) + '\n')
    finally:
        if attempted:
            # Keep both PVCs/PVs and archives for diagnosis; release pod memory on failure too.
            # Cleanup is itself gated and will fail closed if lease/identity changes.
            kube('-n', NS, 'delete', 'pod', 'source', 'restored', '--ignore-not-found=true',
                 '--wait=true', stdout=subprocess.DEVNULL)


def snapshot(out, args=None):
    import yaml
    gate()
    config = private_file(os.environ.get('TALOSCONFIG', '/nonexistent'))
    cfg = yaml.safe_load(config.read_text())
    context = cfg.get('context')
    active = cfg.get('contexts', {}).get(context, {})
    if active.get('endpoints') != ['127.0.0.1:50120'] or active.get('nodes') != ['172.31.250.10']:
        raise RuntimeError('Talos config must bind fixed proof endpoint and node')
    binary = no_symlinks(STATE / 'bin/talosctl')
    info = binary.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise RuntimeError('pinned private Talos binary required')
    version = run([str(binary), 'version', '--client', '--short'], stdout=subprocess.PIPE).decode()
    if 'v1.14.5' not in version.split():
        raise RuntimeError('Talos client must be v1.14.5')
    dest = no_symlinks(out / 'etcd.snapshot')
    if dest.exists():
        raise RuntimeError('refusing snapshot overwrite')
    gate()
    run([str(binary), '--talosconfig', str(config), '--context', context,
         '--endpoints', '127.0.0.1:50120', '--nodes', '172.31.250.10',
         'etcd', 'snapshot', str(dest)], stdout=subprocess.DEVNULL)
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError('empty snapshot')
    dest.chmod(0o600)
    (out / 'snapshot.json').write_text(json.dumps({'bytes': dest.stat().st_size,
        'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'off_node': True,
        'restore_tested': False, 'contains_secrets': True}, indent=2) + '\n')


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['monitor', 'recovery', 'snapshot'])
    p.add_argument('--test-alert', action='store_true')
    p.add_argument('--minimum-available-mib', type=int, default=512)
    args = p.parse_args()
    node = gate()
    out = private_dir()
    if args.action == 'monitor':
        monitor(node, out, args)
    elif args.action == 'recovery':
        recovery(out)
    else:
        snapshot(out, args)
    print(f'Private evidence: {out} (review allowlisted JSON before copying to Git)')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Operations stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
