#!/usr/bin/env python3
"""Offline dedicated synthetic-TMDb CA/leaf Secret; no bootstrap rotation/apply."""
import argparse
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess

safety = importlib.import_module('talos-proof-media-safety')


def generate(state):
    state = safety.private_dir(state)
    names = ('metadata-ca.key', 'metadata-ca.crt', 'metadata-tls.key', 'metadata-tls.csr',
             'metadata-tls.crt', 'metadata-tls.ext', 'metadata-contract-secret.json')
    for name in names:
        if safety.no_symlinks(state / name).exists():
            raise RuntimeError('contract CA output exists; refuse rotation/partial overwrite')
    os.umask(0o077)
    def openssl(*args):
        result = subprocess.run(['openssl', *args], capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError('offline proof CA generation failed; retain partial files for review')
    openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '30', '-subj', '/CN=Synthetic TMDb proof only',
            '-keyout', str(state / 'metadata-ca.key'), '-out', str(state / 'metadata-ca.crt'),
            '-addext', 'basicConstraints=critical,CA:TRUE')
    openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=api.themoviedb.org',
            '-keyout', str(state / 'metadata-tls.key'), '-out', str(state / 'metadata-tls.csr'))
    safety.write_private(state / 'metadata-tls.ext', 'subjectAltName=DNS:api.themoviedb.org\nbasicConstraints=critical,CA:FALSE\n')
    openssl('x509', '-req', '-in', str(state / 'metadata-tls.csr'), '-CA', str(state / 'metadata-ca.crt'),
            '-CAkey', str(state / 'metadata-ca.key'), '-set_serial', '1', '-days', '30',
            '-extfile', str(state / 'metadata-tls.ext'), '-out', str(state / 'metadata-tls.crt'))
    openssl('verify', '-CAfile', str(state / 'metadata-ca.crt'), '-verify_hostname', 'api.themoviedb.org', str(state / 'metadata-tls.crt'))
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'metadata-contract-tls', 'namespace': 'proof-kometa',
              'labels': {'app.kubernetes.io/part-of': 'talos-proof'}}, 'type': 'Opaque', 'data': {}}
    for key, filename in [('ca.crt', 'metadata-ca.crt'), ('tls.crt', 'metadata-tls.crt'), ('tls.key', 'metadata-tls.key')]:
        secret['data'][key] = base64.b64encode(safety.read_private(state / filename, binary=True)).decode()
    safety.write_private(state / 'metadata-contract-secret.json', json.dumps(secret))
    return {'result': 'OFFLINE_CA_ONLY', 'ca_file_sha256': hashlib.sha256(safety.read_private(state / 'metadata-ca.crt', binary=True)).hexdigest(),
            'secret_namespace': 'proof-kometa', 'upstream_provider_auth': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, required=True)
    args = p.parse_args()
    try:
        print(json.dumps(generate(args.state)))
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
