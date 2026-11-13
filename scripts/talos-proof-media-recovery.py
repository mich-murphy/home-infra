#!/usr/bin/env python3
"""Offline-consistent proof PVC snapshots and restore onto DIFFERENT fresh PVCs.

Stateful apps are stopped first. Binary archives stay private, never stdout/Git.
This is a fresh-fixture logical-volume recovery test, not a production backup tool.
"""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import PurePosixPath, Path
import secrets
import sys
import tarfile
import uuid

safety = importlib.import_module('talos-proof-media-safety')
MAX_ARCHIVE = 128 * 1024 * 1024
FRONTENDS = tuple(n for n in safety.SERVICES if n not in ('kometa', 'jellyplex-watched', 'recyclarr'))


def safe_archive(payload):
    if len(payload) > MAX_ARCHIVE:
        raise RuntimeError('fresh-fixture archive exceeded 128MiB bound')
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or member.isdev() or member.isfifo():
                raise RuntimeError('unsafe proof archive member')
            if member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or '..' in link.parts:
                    raise RuntimeError('unsafe proof archive link')


def archive_name(service, volume):
    return service + '-' + volume + '-snapshot-' + uuid.uuid4().hex + '.tar'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['snapshot', 'restore'])
    p.add_argument('service', choices=FRONTENDS)
    p.add_argument('--manifest', type=Path, help='explicit immutable snapshot manifest for restore; legacy default remains readable')
    p.add_argument('--state', required=True, type=Path)
    args = p.parse_args()
    state = safety.private_dir(args.state)
    group, ns = args.service, 'proof-' + args.service
    def kube(*command, **kwargs):
        return safety.kube(group, *command, **kwargs)
    safety.lease(group)
    safety.exclusivity(group)
    deployment = json.loads(kube('-n', ns, 'get', 'deployment', args.service, '-o', 'json'))
    podspec = deployment['spec']['template']['spec']
    image = podspec['containers'][0]['image']
    volumes = [(i, v) for i, v in enumerate(podspec['volumes']) if 'persistentVolumeClaim' in v]
    if not volumes:
        raise RuntimeError('stateful proof service has no PVCs')
    if args.action == 'snapshot' and args.manifest:
        raise RuntimeError('snapshot manifest name is generated exclusively, not caller-selected')
    manifest_path = ((state / (args.service + '-snapshot-' + uuid.uuid4().hex + '.json')) if args.action == 'snapshot'
                     else args.manifest or state / (args.service + '-snapshot.json'))
    if manifest_path.parent.resolve() != state:
        raise RuntimeError('restore manifest must be in the private state directory')
    if args.action == 'restore':
        snapshot = json.loads(safety.read_private(manifest_path))
        if snapshot['service'] != args.service or snapshot['image'] != image:
            raise RuntimeError('snapshot service/image mismatch')
        if snapshot.get('restored'):
            raise RuntimeError('snapshot already restored; preserve source/destination evidence')
        for item in snapshot['volumes']:
            payload = safety.read_private(state / item['archive'], binary=True)
            safe_archive(payload)
            if hashlib.sha256(payload).hexdigest() != item['sha256']:
                raise RuntimeError('snapshot checksum mismatch')
    if args.action == 'restore':
        # Exclusive consumed marker preserves failed attempts too; never silently
        # rerun extraction from the same receipt or truncate its source manifest.
        safety.write_private(manifest_path.with_suffix('.restore-started.json'),
                             json.dumps({'source_manifest': manifest_path.name, 'status': 'STARTED'}))
    # Capture current and historical failures before stopping destroys container counters.
    importlib.import_module('talos-proof-media-observe').capture(group, state)
    # Stop before tar capture: includes SQLite WAL/SHM and app config consistently.
    kube('-n', ns, 'scale', 'deployment', args.service, '--replicas=0')
    kube('-n', ns, 'wait', '--for=delete', 'pod', '-l', 'app.kubernetes.io/name=' + args.service, '--timeout=180s')
    # Fresh guest admission for only a 128MiB helper; no app runs concurrently.
    safety.guard(group, budget_mib=128)
    entries = []
    for index, volume in volumes:
        old_claim = volume['persistentVolumeClaim']['claimName']
        original = json.loads(kube('-n', ns, 'get', 'pvc', old_claim, '-o', 'json'))
        if args.action == 'snapshot':
            entry = {'volume': volume['name'], 'index': index, 'source_claim': old_claim,
                     'source_uid': original['metadata']['uid'], 'storage': original['spec']['resources']['requests']['storage'],
                     'archive': archive_name(args.service, volume['name'])}
        else:
            entry = next(x for x in snapshot['volumes'] if x['volume'] == volume['name'])
            if old_claim != entry['source_claim'] or original['metadata']['uid'] != entry['source_uid']:
                raise RuntimeError('source PVC identity changed before clean-PVC restore')
            fresh_name = 'recovery-' + volume['name'] + '-' + secrets.token_hex(4)
            fresh = {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim',
                     'metadata': {'name': fresh_name, 'namespace': ns, 'labels': {'app.kubernetes.io/part-of': 'talos-proof'}},
                     'spec': {'accessModes': ['ReadWriteOnce'], 'storageClassName': 'proof-local',
                              'resources': {'requests': {'storage': entry['storage']}}}}
            kube('create', '-f', '-', data=json.dumps(fresh).encode())
            entry['destination_claim'] = fresh_name
        entries.append(entry)
    safety.write_private(state / (args.service + '-recovery-attempt-' + uuid.uuid4().hex + '.json'),
                         json.dumps({'action': args.action, 'manifest': manifest_path.name, 'volumes': entries}))
    helper_name = 'proof-volume-recovery-' + secrets.token_hex(3)
    claims = [(e['volume'], e.get('destination_claim', e['source_claim'])) for e in entries]
    helper = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': helper_name, 'namespace': ns,
              'labels': {'app.kubernetes.io/part-of': 'talos-proof'}},
              'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 180, 'template': {'metadata': {'labels': {
                  'app.kubernetes.io/name': args.service, 'app.kubernetes.io/part-of': 'talos-proof'}}, 'spec': {
                      'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                      'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}, 'fsGroup': 1000},
                      'containers': [{'name': 'volume-recovery', 'image': image,
                          'command': ['/bin/sh', '-ec', 'sleep 170'],
                          'securityContext': {'runAsUser': 0, 'allowPrivilegeEscalation': False,
                                              'capabilities': {'drop': ['ALL'], 'add': ['DAC_OVERRIDE', 'CHOWN', 'FOWNER']}},
                          'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '200m', 'memory': '128Mi'}},
                          'volumeMounts': [{'name': v, 'mountPath': '/volumes/' + v, 'readOnly': args.action == 'snapshot'} for v, c in claims]}],
                      'volumes': [{'name': v, 'persistentVolumeClaim': {'claimName': c}} for v, c in claims]}}}}
    kube('create', '-f', '-', data=json.dumps(helper).encode())
    try:
        kube('-n', ns, 'wait', '--for=condition=Ready', 'pod', '-l', 'job-name=' + helper_name, '--timeout=90s')
        pod = kube('-n', ns, 'get', 'pod', '-l', 'job-name=' + helper_name, '-o', 'jsonpath={.items[0].metadata.name}').decode()
        for entry in entries:
            if args.action == 'snapshot':
                payload = kube('-n', ns, 'exec', pod, '--', 'tar', '-C', '/volumes/' + entry['volume'], '-cf', '-', '.')
                safe_archive(payload)
                safety.write_private(state / entry['archive'], payload)
                entry['sha256'], entry['bytes'] = hashlib.sha256(payload).hexdigest(), len(payload)
            else:
                payload = safety.read_private(state / entry['archive'], binary=True)
                kube('-n', ns, 'exec', '-i', pod, '--', 'tar', '-C', '/volumes/' + entry['volume'], '-xpf', '-', data=payload)
                destination = json.loads(kube('-n', ns, 'get', 'pvc', entry['destination_claim'], '-o', 'json'))
                entry['destination_uid'] = destination['metadata']['uid']
                if entry['destination_uid'] == entry['source_uid']:
                    raise RuntimeError('restore did not allocate a different PVC')
    finally:
        kube('-n', ns, 'delete', 'job', helper_name, '--wait=true', '--timeout=60s')
        kube('-n', ns, 'wait', '--for=delete', 'pod', '-l', 'job-name=' + helper_name, '--timeout=180s')
    result_path = manifest_path
    if args.action == 'snapshot':
        snapshot = {'service': args.service, 'image': image, 'volumes': entries, 'restored': False}
        safety.write_private(manifest_path, json.dumps(snapshot))
    else:
        patches = [{'op': 'replace', 'path': '/spec/template/spec/volumes/' + str(e['index']) + '/persistentVolumeClaim/claimName',
                    'value': e['destination_claim']} for e in entries]
        kube('-n', ns, 'patch', 'deployment', args.service, '--type=json', '-p', json.dumps(patches))
        snapshot.update(volumes=entries, restored=True)
        result_path = state / (args.service + '-restored-' + uuid.uuid4().hex + '.json')
        safety.write_private(result_path, json.dumps(dict(snapshot, source_manifest=manifest_path.name)))
    print(json.dumps({'service': args.service, 'action': args.action, 'result': 'VOLUME_OPERATION_ONLY',
                      'manifest': result_path.name, 'source_manifest': manifest_path.name, 'fresh_destination_pvcs': args.action == 'restore', 'volumes': len(entries),
                      'next_gate': 'start without reapplying bases, then read-before-write functional verification'}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Recovery stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
