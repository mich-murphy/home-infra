#!/usr/bin/env python3
"""Generate a two-second synthetic tone; optionally seed one fresh proof PVC.
No external fetch, copyrighted content, production volume or transcoding required.
"""
import argparse
import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import struct
import wave


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', type=Path, required=True)
    p.add_argument('--seed', choices=['jellyfin', 'plex', 'audiobookshelf'])
    args = p.parse_args()
    safety = importlib.import_module('talos-proof-media-safety')
    os.umask(0o077)
    state = safety.private_dir(args.state_dir, create=True)
    repo = safety.ROOT
    if args.seed:
        safety.guard(args.seed, extra_mib=64)
    path = safety.no_symlinks(state / 'proof-tone.wav')
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b''.join(struct.pack('<h', int(4000 * math.sin(2 * math.pi * 440 * i / 8000))) for i in range(16000)))
    safety.write_private(path, stream.getvalue(), replace=True)
    print(json.dumps({'fixture': 'proof-tone.wav', 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'source': 'mathematically generated 440Hz sine; no external input'}))
    if not args.seed:
        return
    # Same current Compose digest; no extra mutable utility image.
    import yaml
    docs = list(yaml.safe_load_all((repo / f'kubernetes/apps/media/{args.seed}/resources.yaml').read_text()))
    deployment = next(x for x in docs if x['kind'] == 'Deployment')
    image = deployment['spec']['template']['spec']['containers'][0]['image']
    ns = 'proof-' + args.seed
    job = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': 'seed-synthetic-fixture', 'namespace': ns, 'labels': {'app.kubernetes.io/part-of': 'talos-proof'}}, 'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 120, 'template': {'metadata': {'labels': {'app.kubernetes.io/name': 'fixture-seeder', 'app.kubernetes.io/part-of': 'talos-proof'}}, 'spec': {'restartPolicy': 'Never', 'automountServiceAccountToken': False, 'securityContext': {'runAsUser': 1000, 'runAsGroup': 1000, 'fsGroup': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [{'name': 'seed', 'image': image, 'command': ['/bin/sh', '-ec', 'sleep 110'], 'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}, 'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}, 'volumeMounts': [{'name': 'fixture', 'mountPath': '/fixture'}]}], 'volumes': [{'name': 'fixture', 'persistentVolumeClaim': {'claimName': 'fixture'}}]}}}}
    def k(*command, **kwargs):
        return safety.kube(args.seed, '-n', ns, *command, **kwargs)
    k('create', '-f', '-', data=json.dumps(job).encode(), capacity=True, extra_mib=64)
    try:
        k('wait', '--for=condition=Ready', 'pod', '-l', 'job-name=seed-synthetic-fixture', '--timeout=90s')
        pod = k('get', 'pod', '-l', 'job-name=seed-synthetic-fixture', '-o', 'jsonpath={.items[0].metadata.name}').decode()
        k('exec', '-i', pod, '--', '/bin/sh', '-ec', 'cat > /fixture/proof-tone.wav', data=safety.read_private(path, binary=True))
    finally:
        k('delete', 'job', 'seed-synthetic-fixture', '--wait=true', '--timeout=60s')
    print('Seeded synthetic fixture; scan/playback verification is a separate required step.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Fixture stopped: ' + type(exc).__name__, file=__import__('sys').stderr)
        raise SystemExit(1)
