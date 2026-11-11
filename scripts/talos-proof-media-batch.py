#!/usr/bin/env python3
"""Coordinator-leased one-service media lifecycle, exact proof target only."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import time

safety = importlib.import_module('talos-proof-media-safety')
observe = importlib.import_module('talos-proof-media-observe')
FRONTENDS = tuple(x for x in safety.SERVICES if x not in ('kometa', 'recyclarr', 'jellyplex-watched'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'verify', 'restart', 'activate'])
    parser.add_argument('service', choices=FRONTENDS)
    parser.add_argument('state', type=Path)
    args = parser.parse_args()
    state = safety.private_dir(args.state)
    # Validate all credential inputs BEFORE any apply, including the public bundle apply.
    credentials = json.loads(safety.read_private(state / 'credentials.json'))
    secret = json.loads(safety.read_private(state / f'{args.service}-secret.json'))
    ns = 'proof-' + args.service
    if args.service not in credentials or secret.get('kind') != 'Secret' or secret.get('metadata', {}).get('namespace') != ns or secret['metadata'].get('name') != 'bootstrap':
        raise RuntimeError('private bootstrap state does not match requested service')
    safety.lease(args.service)
    if args.action == 'verify':
        safety.exclusivity(args.service)
        print('Verified exact proof API, TLS, context, single-node identity, lease and private state.')
        return
    def kube(*command, **kwargs):
        return safety.kube(args.service, *command, **kwargs)
    if args.action in ('start', 'restart', 'activate'):
        safety.guard(args.service)
        safety.require_helpers_deleted(args.service)
        if args.action == 'start':
            kube('apply', '-k', str(safety.ROOT / 'kubernetes/apps/media' / args.service))
            kube('apply', '-f', '-', data=json.dumps(secret).encode())
            safety.require_helpers_deleted(args.service)
            kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=1', capacity=True)
        elif args.action == 'activate':
            # Route-only repair preserves any restored Deployment PVC references.
            if args.service == 'qbittorrent':
                kube('apply', '-f', str(safety.ROOT / 'kubernetes/apps/media/qbittorrent/httproute.yaml'))
                safety.require_helpers_deleted(args.service)
            kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=1', capacity=True)
        else:
            observe.capture(args.service, state)
            kube('-n', ns, 'rollout', 'restart', 'deployment/' + args.service, capacity=True)
        try:
            if args.service == 'pinchflat':
                deadline = time.monotonic() + 300
                while True:
                    pods = json.loads(safety.kubectl_read('get', 'pods', '-n', ns, '-o', 'json'))['items']
                    safety.resources.pinchflat_no_restart(pods)
                    if pods and all(any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in p.get('status', {}).get('conditions', [])) for p in pods):
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Pinchflat bounded startup timed out')
                    time.sleep(1)
            kube('-n', ns, 'rollout', 'status', 'deployment/' + args.service, '--timeout=300s')
        except RuntimeError:
            # Preserve failed pod UID/image/last termination and cgroup evidence before deletion.
            try:
                observe.capture(args.service, state)
            finally:
                kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=0')
                kube('-n', ns, 'wait', '--for=delete', 'pod', '-l', 'app.kubernetes.io/name=' + args.service, '--timeout=180s')
            raise
        print('Startup complete; functional/Gateway/persistence acceptance remains separate.')
    else:
        try:
            observe.capture(args.service, state)
        finally:
            kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=0')
            kube('-n', ns, 'wait', '--for=delete', 'pod', '-l', 'app.kubernetes.io/name=' + args.service, '--timeout=180s')
        print('Service stopped; fresh proof PVC state retained.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Media proof stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
