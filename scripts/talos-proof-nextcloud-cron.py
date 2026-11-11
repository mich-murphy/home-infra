#!/usr/bin/env python3
"""Offline native-cron phase compiler. No cluster/host commands, credentials or grants.

Compilation is NOT admission. Live integration deliberately fails closed until the
serial-helper supervisor and restore window have parent-reviewed implementation.
"""
import argparse
import json
import os
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'nextcloud:35.0.2-apache@sha256:786c102155d2717ba0f53a62b3fdd7a1354edc48e800b94dbe32294d9a5752a2'
CLASS = r'OC\Authentication\Token\TokenCleanupJob'
PHASES = ('preflight', 'install-or-verify', 'fixture', 'before', 'cron', 'assert-restore')
GATE = ('Native cron live integration blocked: no reviewed serial-helper supervisor '
        'with per-operation endpoint/context/node UID/expiry, fresh dual-memory '
        '832MiB admission, PVC/Secret/backend identity inspection, private durable '
        'journal export and bounded restoration window. Offline payloads are not admission.')


def due(row, now):
    """Native TimedJob uses strict >86400; class filtering does not waive it."""
    return (row.get('class') == CLASS and type(row.get('id')) is int and row['id'] > 0
            and type(row.get('last_run')) is int and 0 <= row['last_run'] < now - 86400
            and row.get('reserved_at') == 0
            and type(row.get('last_checked')) is int and 0 <= row['last_checked'] <= now)


def barrier(pods):
    """All Job pods, even completed/failed/terminating/unlabelled, block admission."""
    for pod in pods:
        meta = pod['metadata']
        if meta['namespace'].startswith('proof-'):
            if any(o.get('kind') == 'Job' for o in meta.get('ownerReferences', [])):
                raise RuntimeError('existing proof Job pod blocks every serial phase')
            if meta['namespace'] == 'proof-nextcloud' and meta.get('labels', {}).get('app.kubernetes.io/name') not in ('postgres', 'redis'):
                raise RuntimeError('non-backend pod blocks CLI-only cron stage')
            if meta['namespace'] != 'proof-nextcloud':
                raise RuntimeError('other proof application pod blocks cron stage')


def job(phase, run_id):
    """Bounded inert Job document; never applied by this compiler."""
    if phase not in PHASES or str(uuid.UUID(run_id)) != run_id:
        raise ValueError('exact phase and canonical UUID required')
    command = ['sh', '-ec', 'umask 077; php /proof/native.php "$PROOF_PHASE" "$PROOF_RUN"']
    container = dict(name='cli', image=IMAGE, command=command,
                     env=[dict(name='PROOF_PHASE', value=phase), dict(name='PROOF_RUN', value=run_id),
                          dict(name='POSTGRES_HOST', value='postgres'), dict(name='POSTGRES_DB', value='nextcloud'),
                          dict(name='POSTGRES_USER', value='nextcloud'), dict(name='REDIS_HOST', value='redis')],
                     envFrom=[dict(secretRef=dict(name='proof-credentials'))],
                     securityContext=dict(allowPrivilegeEscalation=False, capabilities=dict(drop=['ALL'])),
                     resources=dict(requests=dict(cpu='25m', memory='64Mi'), limits=dict(cpu='500m', memory='192Mi')),
                     volumeMounts=[dict(name='html', mountPath='/var/www/html', readOnly=phase == 'preflight'),
                                   dict(name='payload', mountPath='/proof', readOnly=True)])
    spec = dict(automountServiceAccountToken=False, restartPolicy='Never',
                securityContext=dict(runAsUser=33, runAsGroup=33, seccompProfile=dict(type='RuntimeDefault')),
                containers=[container], volumes=[dict(name='html', persistentVolumeClaim=dict(claimName='nextcloud-data')),
                    dict(name='payload', configMap=dict(name='nextcloud-cron-payload-' + run_id))])
    return dict(apiVersion='batch/v1', kind='Job', metadata=dict(name='nc-' + phase + '-' + run_id,
                namespace='proof-nextcloud'), spec=dict(backoffLimit=0, activeDeadlineSeconds=180,
                template=dict(metadata=dict(labels={'app.kubernetes.io/name':'nextcloud',
                'app.kubernetes.io/part-of':'talos-proof'}), spec=spec)))


def payload_sources():
    source = json.loads((ROOT / 'docs/evidence/talos-data/nextcloud-cron-source-review-97384394-9c9c-47d4-8d17-50e63b9b62fd.json').read_text())
    # Docker build input is not necessarily present in the image. Do not invent
    # in-image parity for Dockerfiles/configuration fragments; core only here.
    return {s['path']: s['sha256'] for s in source['sources'] if not s['path'].startswith('docker/')}


def compile_bundle(run_id=None):
    run_id = run_id or str(uuid.uuid4())
    native = (ROOT / 'scripts/talos-proof-nextcloud-cron.php').read_text()
    return dict(status='OFFLINE_COMPILED_NOT_ADMITTED', run_id=run_id, gate=GATE,
                budget_mib=dict(postgres=384, redis=64, serial_cli=192, reserve=192, total=832),
                payload=dict(apiVersion='v1', kind='ConfigMap', metadata=dict(namespace='proof-nextcloud',
                    name='nextcloud-cron-payload-' + run_id), data={'native.php':native,
                    'core-hashes.json':json.dumps(payload_sources(), sort_keys=True),
                    'docker-hashes.json':json.dumps({s['path']:s['sha256'] for s in json.loads((ROOT/'docs/evidence/talos-data/nextcloud-cron-docker-config-source.json').read_text())['sources']}),
                    'intent.json':json.dumps(intent(run_id))}),
                jobs=[job(phase, run_id) for phase in PHASES])


def intent(run_id):
    return dict(run_id=run_id, label='SYNTHETIC_AGE_NOT_REAL_ELAPSED_EXPIRY',
                tokens={kind:dict(name='proof-cron-'+run_id+'-'+kind, remember=remember)
                        for kind,remember in [('candidate',0),('control',1)]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['compile', 'run'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'run':
        raise RuntimeError(GATE)  # use the separate receipt-bound supervisor, not a compiled bundle
    if args.output is None:
        parser.error('--output required; never emit payload/artifacts to stdout')
    # New UUID artifact, exclusive private creation; no overwriting old evidence.
    if args.output.name != str(uuid.UUID(args.output.stem)) + '.json':
        parser.error('output basename must be a canonical UUID.json')
    for path in (args.output, *args.output.absolute().parents):
        if path.is_symlink():
            raise RuntimeError('artifact symlink forbidden')
    if ROOT == args.output.absolute() or ROOT in args.output.absolute().parents:
        raise RuntimeError('private artifacts must be outside Git')
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(compile_bundle(), stream, indent=2)
    print('Offline payload compiled; live execution BLOCKED.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else type(error).__name__)
        raise SystemExit(1)
