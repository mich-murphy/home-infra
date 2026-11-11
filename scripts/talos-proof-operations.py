#!/usr/bin/env python3
"""Bounded, external operational proof. No resident monitoring stack or production access."""
import argparse
import datetime
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / '.local/state/home-infra/talos-proof'
NS = 'proof-operations-recovery'


def run(args, **kw):
    # Errors intentionally omit command output: credentials/server responses stay private.
    p = subprocess.run(args, stderr=subprocess.PIPE, timeout=240, **kw)
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed ({p.returncode}); output withheld')
    return p.stdout


def kube(*args, **kw):
    return run(['kubectl', '--request-timeout=30s', *args], **kw)


def obj(*args):
    return json.loads(kube(*args, stdout=subprocess.PIPE))


def private_dir():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if STATE.stat().st_mode & 0o077:
        raise RuntimeError('private state directory must have mode 0700')
    out = STATE / 'operations' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out.mkdir(parents=True, mode=0o700)
    return out


def gate():
    if os.environ.get('TALOS_PROOF_OPERATIONS_LEASE') != 'vm120':
        raise RuntimeError('explicit parent VM120 resource lease required')
    config = Path(os.environ.get('KUBECONFIG', '/nonexistent')).resolve()
    if not config.is_file() or not config.is_relative_to(STATE.resolve()):
        raise RuntimeError('explicit proof KUBECONFIG under private state required')
    if config.stat().st_mode & 0o077:
        raise RuntimeError('kubeconfig must have mode 0600')
    nodes = obj('get', 'nodes', '-o', 'json')['items']
    if len(nodes) != 1:
        raise RuntimeError('expected dedicated single-node proof')
    return nodes[0]


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
    kube('apply', '-k', str(ROOT / 'kubernetes/operations/recovery'), stdout=subprocess.DEVNULL)
    for pod in ('source', 'restored'):
        kube('-n', NS, 'wait', '--for=condition=Ready', f'pod/{pod}', '--timeout=180s', stdout=subprocess.DEVNULL)
    claims = obj('-n', NS, 'get', 'pvc', '-o', 'json')['items']
    ids = {p['metadata']['name']: {'uid': p['metadata']['uid'], 'volume': p['spec']['volumeName']} for p in claims}
    if ids['source']['volume'] == ids['restored']['volume']:
        raise RuntimeError('source and restored must be distinct PVs')
    # Refuse reuse/nonempty data. Never wipe a PVC to make a failing test pass.
    for pod in ('source', 'restored'):
        kube('-n', NS, 'exec', pod, '--', 'sh', '-ec', 'test -z "$(ls -A /data)"', stdout=subprocess.DEVNULL)
    payload = b'talos-proof isolated off-node recovery fixture v1\n'
    digest = hashlib.sha256(payload).hexdigest()
    kube('-n', NS, 'exec', '-i', 'source', '--', 'sh', '-ec', 'cat > /data/fixture.txt', input=payload, stdout=subprocess.DEVNULL)
    archive = out / 'fixture.tar'
    with archive.open('wb') as f:
        kube('-n', NS, 'exec', 'source', '--', 'tar', '-C', '/data', '-cf', '-', 'fixture.txt', stdout=f)
    # Remove source pod before restore: no running source writer or shared source mount.
    kube('-n', NS, 'delete', 'pod', 'source', '--wait=true', stdout=subprocess.DEVNULL)
    with archive.open('rb') as f:
        kube('-n', NS, 'exec', '-i', 'restored', '--', 'tar', '-C', '/data', '-xf', '-', stdin=f, stdout=subprocess.DEVNULL)
    restored = kube('-n', NS, 'exec', 'restored', '--', 'cat', '/data/fixture.txt', stdout=subprocess.PIPE)
    if hashlib.sha256(restored).hexdigest() != digest:
        raise RuntimeError('restored checksum mismatch')
    (out / 'recovery.json').write_text(json.dumps({'claims': ids, 'fixture_sha256': digest,
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'off_node': True, 'source_pod_deleted_before_restore': True,
        'restored_checksum_matches': True, 'application_consistency': 'static synthetic file only'}, indent=2) + '\n')


def snapshot(out, args):
    config = Path(os.environ.get('TALOSCONFIG', '/nonexistent')).resolve()
    if not config.is_file() or not config.is_relative_to(STATE.resolve()) or config.stat().st_mode & 0o077:
        raise RuntimeError('private proof TALOSCONFIG mode 0600 required')
    if not args.node:
        raise RuntimeError('--node proof Talos endpoint required')
    dest = out / 'etcd.snapshot'
    run(['talosctl', '--talosconfig', str(config), '--nodes', args.node, 'etcd', 'snapshot', str(dest)], stdout=subprocess.DEVNULL)
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError('empty snapshot')
    (out / 'snapshot.json').write_text(json.dumps({'bytes': dest.stat().st_size,
        'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'off_node': True,
        'restore_tested': False, 'contains_secrets': True}, indent=2) + '\n')


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['monitor', 'recovery', 'snapshot'])
    p.add_argument('--test-alert', action='store_true')
    p.add_argument('--minimum-available-mib', type=int, default=512)
    p.add_argument('--node', help='proof Talos API endpoint; snapshot only')
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
    main()
