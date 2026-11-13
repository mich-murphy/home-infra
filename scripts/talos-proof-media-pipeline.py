#!/usr/bin/env python3
"""Explicit fresh shared-/data pipeline; activate ONE reviewed bounded pair only."""
import argparse
import base64
import importlib
import json
import hashlib
from pathlib import Path
import sys
import yaml

safety = importlib.import_module('talos-proof-media-safety')
NS = 'proof-media-pipeline'


def sync_recyclarr(kube, api, state):
    """Two actual nonempty syncs: assert real creation, then stable ID+definition."""
    before = api.call('/api/v3/customformat')
    if any(x['name'] == 'Proof-Synthetic-Title' for x in before):
        raise RuntimeError('first actual sync requires synthetic format absent; do not erase prior evidence')
    cron = json.loads(kube('-n', NS, 'get', 'cronjob', 'recyclarr', '-o', 'json'))
    run_id = str(__import__('time').time_ns())
    hashes = []
    first = None
    for step in (1, 2):
        safety.guard('media-pipeline')
        safety.require_helpers_deleted('media-pipeline')
        name = 'recyclarr-sync-' + run_id + '-' + str(step)
        spec = json.loads(json.dumps(cron['spec']['jobTemplate']['spec']))
        spec['template']['spec']['containers'][0]['args'] = ['sync']  # Real mutation, never preview.
        job = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': name, 'namespace': NS,
               'labels': {'app.kubernetes.io/part-of': 'talos-proof'}}, 'spec': spec}
        kube('create', '-f', '-', data=json.dumps(job).encode(), capacity=True)
        try:
            kube('-n', NS, 'wait', '--for=condition=complete', 'job/' + name, '--timeout=210s')
        finally:
            try:
                logs = kube('-n', NS, 'logs', 'job/' + name)
                safety.write_private(state / (name + '.log'), logs)
                hashes.append(hashlib.sha256(logs).hexdigest())
                # Retain structured failure/image identity privately; do not print arbitrary logs.
                pods = kube('-n', NS, 'get', 'pods', '-l', 'job-name=' + name, '-o', 'json')
                sanitized = [importlib.import_module('talos-proof-media-observe').summarize(p) for p in json.loads(pods)['items']]
                safety.write_private(state / (name + '-pods.json'), json.dumps(sanitized))
            finally:
                kube('-n', NS, 'delete', 'job', name, '--wait=true', '--timeout=60s')
                kube('-n', NS, 'wait', '--for=delete', 'pod', '-l', 'job-name=' + name, '--timeout=180s')
        after = api.call('/api/v3/customformat')
        created = [x for x in after if x['name'] == 'Proof-Synthetic-Title']
        if len(created) != 1 or not created[0].get('specifications') or not created[0].get('id'):
            raise RuntimeError('actual sync did not create exactly one nonempty synthetic custom format')
        if step == 1:
            if sorted((x for x in after if x['name'] != 'Proof-Synthetic-Title'), key=lambda x: x['id']) != sorted(before, key=lambda x: x['id']):
                raise RuntimeError('sync unexpectedly changed unrelated custom formats')
            first = sorted(after, key=lambda x: x['id'])
        elif sorted(after, key=lambda x: x['id']) != first:
            raise RuntimeError('second actual sync drifted IDs or definitions')
    safety.write_private(state / ('recyclarr-sync-' + run_id + '-result.json'), json.dumps({'custom_formats': first, 'log_sha256': hashes}))
    print(json.dumps({'service': 'recyclarr', 'result': 'PASS', 'checks': ['actual nonempty synthetic Create', 'second actual sync stable IDs+definitions; no drift'], 'log_sha256': hashes}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify', 'start', 'stop', 'restart', 'preview-recyclarr', 'sync-recyclarr'])
    parser.add_argument('--pair', required=True, choices=safety.PIPELINE_PAIRS)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--ca', type=Path, help='private trusted Gateway CA for helper before/after API checks')
    args = parser.parse_args()
    safety.select_pipeline(args.pair)
    members = args.pair.split('+')  # downloader starts first by explicit allowlist ordering
    state = safety.private_dir(args.state)
    secrets = []
    for name in members:
        secret = json.loads(safety.read_private(state / f'{name}-secret.json'))
        if secret.get('kind') != 'Secret' or secret.get('metadata', {}).get('namespace') != 'proof-' + name or secret['metadata'].get('name') != 'bootstrap':
            raise RuntimeError('private source bootstrap secret does not match selected proof service')
        secret['metadata'].update(name=name + '-bootstrap', namespace=NS)
        if name == 'recyclarr':
            config = yaml.safe_load(base64.b64decode(secret['data']['seed']))
            config.pop('sonarr', None)
            config['radarr']['proof']['base_url'] = 'http://radarr:7878'
            secret['data']['seed'] = base64.b64encode(yaml.safe_dump(config).encode()).decode()
        secrets.append(secret)
    def kube(*command, **kwargs):
        return safety.kube('media-pipeline', *command, **kwargs)
    safety.lease('media-pipeline')
    safety.exclusivity('media-pipeline')
    if args.action in ('preview-recyclarr', 'sync-recyclarr'):
        if args.pair != 'radarr+recyclarr' or args.ca is None:
            parser.error('preview requires --pair radarr+recyclarr and trusted --ca')
        api_type = importlib.import_module('talos-proof-media-http').API
        credentials = json.loads(safety.read_private(state / 'credentials.json'))
        api = api_type('https://pipeline-radarr.proof.invalid:18443',
                       {'X-Api-Key': credentials['radarr']['api_key']}, service='pipeline-radarr',
                       ca=safety.private_file(args.ca))
        api.wait_ready('/')
        if args.action == 'sync-recyclarr':
            sync_recyclarr(kube, api, state)
            return
        before = api.call('/api/v3/customformat')
        if any(x['name'] == 'Proof-Synthetic-Title' for x in before):
            raise RuntimeError('preview requires synthetic format to be absent before execution')
        safety.guard('media-pipeline')
        kube('-n', NS, 'create', 'job', 'recyclarr-proof-preview', '--from=cronjob/recyclarr', capacity=True)
        try:
            kube('-n', NS, 'wait', '--for=condition=complete', 'job/recyclarr-proof-preview', '--timeout=210s')
            logs = kube('-n', NS, 'logs', 'job/recyclarr-proof-preview')
            safety.write_private(state / 'recyclarr-preview.log', logs, replace=True)
            after = api.call('/api/v3/customformat')
            if before != after:
                raise RuntimeError('preview mutated proof Radarr custom formats')
            if not all(token in logs for token in [b'Create', b'Proof-Synthetic-Title', b'11111111111111111111111111111111']):
                raise RuntimeError('successful job did not demonstrate the nonempty planned synthetic creation')
            print(json.dumps({'service': 'recyclarr', 'result': 'PASS',
                              'checks': ['nonempty local-provider preview', 'planned synthetic format Create', 'Radarr API state unchanged'],
                              'preview_log_sha256': hashlib.sha256(logs).hexdigest()}))
        finally:
            kube('-n', NS, 'delete', 'job/recyclarr-proof-preview', '--wait=true', '--timeout=60s')
            kube('-n', NS, 'wait', '--for=delete', 'pod', '-l', 'job-name=recyclarr-proof-preview', '--timeout=180s')
        return
    if args.action == 'verify':
        print('Verified exact target and coordinator media-pipeline lease for selected bounded pair.')
        return
    if args.action == 'stop':
        for name in reversed(members):
            if name == 'recyclarr':
                continue
            kube('-n', NS, 'scale', 'deployment', name, '--replicas=0')
        kube('-n', NS, 'wait', '--for=delete', 'pod', '--all', '--timeout=180s')
        print('Selected pipeline pair stopped; fresh shared data/config PVCs retained.')
        return
    safety.guard('media-pipeline')
    safety.require_helpers_deleted('media-pipeline')
    if args.action == 'start':
        active = json.loads(safety.kubectl_read('get', 'deployments', '-A', '-o', 'json'))['items']
        if any(x['metadata']['namespace'] == NS and x['spec'].get('replicas', 1) for x in active):
            raise RuntimeError('pipeline is already active; stop it before applying default-zero profile')
        kube('apply', '-k', str(safety.ROOT / 'kubernetes/apps/media/integration'))
        for secret in secrets:
            kube('apply', '-f', '-', data=json.dumps(secret).encode())
    try:
        for name in members:
            if name == 'recyclarr':
                continue  # Suspended helper needs explicit reviewed preview execution.
            if args.action == 'start':
                kube('-n', NS, 'scale', 'deployment', name, '--replicas=1', capacity=True)
            else:
                kube('-n', NS, 'rollout', 'restart', 'deployment/' + name, capacity=True)
            kube('-n', NS, 'rollout', 'status', 'deployment/' + name, '--timeout=300s')
    except RuntimeError:
        for name in reversed(members):
            if name == 'recyclarr':
                continue
            kube('-n', NS, 'scale', 'deployment', name, '--replicas=0')
        raise
    print('Selected bounded pair started; functional import/connection evidence still required.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Pipeline stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
