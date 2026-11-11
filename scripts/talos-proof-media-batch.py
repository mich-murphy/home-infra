#!/usr/bin/env python3
"""Coordinator-leased one-service media lifecycle, exact proof target only."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys

safety = importlib.import_module('talos-proof-media-safety')
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
        if args.action == 'start':
            kube('apply', '-k', str(safety.ROOT / 'kubernetes/apps/media' / args.service))
            kube('apply', '-f', '-', data=json.dumps(secret).encode())
            kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=1', capacity=True)
        elif args.action == 'activate':
            kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=1', capacity=True)
        else:
            kube('-n', ns, 'rollout', 'restart', 'deployment/' + args.service, capacity=True)
        try:
            kube('-n', ns, 'rollout', 'status', 'deployment/' + args.service, '--timeout=300s')
        except RuntimeError:
            kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=0')
            raise
        print('Startup complete; functional/Gateway/persistence acceptance remains separate.')
    else:
        kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=0')
        kube('-n', ns, 'wait', '--for=delete', 'pod', '-l', 'app.kubernetes.io/name=' + args.service, '--timeout=180s')
        print('Service stopped; fresh proof PVC state retained.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Media proof stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
