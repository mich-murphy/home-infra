#!/usr/bin/env python3
"""Generate fresh proof secrets offline; output paths only, never secret values."""
import argparse
import base64
import hashlib
import json
import importlib
import os
from pathlib import Path
import secrets

SERVICES = ('radarr sonarr lidarr prowlarr qbittorrent qbitwebui sabnzbd plex '
            'tautulli seerr kometa jellyfin jellyplex-watched audiobookshelf pinchflat recyclarr').split()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    safety = importlib.import_module('talos-proof-media-safety')
    os.umask(0o077)
    root = safety.private_dir(args.state_dir, create=True)
    if (root / 'credentials.json').exists():
        parser.error('credentials already exist; refuse rotation that could desynchronize PVCs')
    credentials = {}
    manifests = []
    for name in SERVICES:
        key, password = secrets.token_hex(16), secrets.token_urlsafe(30)
        credentials[name] = {'api_key': key, 'username': 'proof', 'password': password}
        data = {'api-key': key, 'password': password, 'encryption-key': secrets.token_hex(32),
                'plex-token': 'UNCONFIGURED-PROOF-ONLY', 'jellyfin-token': 'UNCONFIGURED-PROOF-ONLY'}
        if name in ('radarr', 'sonarr', 'lidarr', 'prowlarr'):
            port = dict(radarr=7878, sonarr=8989, lidarr=8686, prowlarr=9696)[name]
            data['seed'] = (f'<Config><Port>{port}</Port><BindAddress>*</BindAddress><ApiKey>{key}</ApiKey>'
                            '<AuthenticationMethod>External</AuthenticationMethod>'
                            '<AuthenticationRequired>Enabled</AuthenticationRequired>'
                            '<LaunchBrowser>False</LaunchBrowser><AnalyticsEnabled>False</AnalyticsEnabled>'
                            '<UpdateMechanism>External</UpdateMechanism></Config>')
        elif name == 'qbittorrent':
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac('sha512', password.encode(), salt, 100000)
            encoded = ':'.join(base64.b64encode(x).decode() for x in (salt, digest))
            data['seed'] = ('[Preferences]\nWebUI\\Username=proof\n'
                            f'WebUI\\Password_PBKDF2="@ByteArray({encoded})"\n'
                            'WebUI\\Address=*\nWebUI\\LocalHostAuth=true\n'
                            'WebUI\\CSRFProtection=true\nWebUI\\HostHeaderValidation=true\n'
                            '[BitTorrent]\nSession\\DHTEnabled=false\nSession\\PeXEnabled=false\n'
                            'Session\\LSDEnabled=false\nSession\\DefaultSavePath=/data/torrents\n')
        elif name == 'sabnzbd':
            data['seed'] = (f'[misc]\nhost = 0.0.0.0\nport = 8080\napi_key = {key}\n'
                            'inet_exposure = 5\nenable_https = 0\n'
                            'download_dir = /data/usenet/incomplete\ncomplete_dir = /data/usenet/complete\n')
        elif name == 'kometa':
            data['seed'] = ('libraries:\n  Proof:\n    collection_files:\n      - file: /proof-fixtures/collections.yml\n'
                            'plex:\n  url: http://plex.proof-plex.svc:32401\n'
                            f'  token: {credentials["plex"]["api_key"]}\n'
                            f'tmdb:\n  apikey: {key}\n')
        elif name == 'recyclarr':
            # Local profiles only. No production config includes or upstream templates.
            data['seed'] = ('radarr:\n  proof:\n    base_url: http://radarr.proof-radarr.svc:7878\n'
                            f'    api_key: {credentials["radarr"]["api_key"]}\n'
                            '    custom_formats:\n      - trash_ids: ["11111111111111111111111111111111"]\n'
                            'sonarr:\n  proof:\n    base_url: http://sonarr.proof-sonarr.svc:8989\n'
                            f'    api_key: {credentials["sonarr"]["api_key"]}\n')
        manifests.append({'apiVersion': 'v1', 'kind': 'Secret',
                          'metadata': {'name': 'bootstrap', 'namespace': 'proof-' + name,
                                       'labels': {'app.kubernetes.io/part-of': 'talos-proof'}},
                          'type': 'Opaque', 'data': {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}})
    # Validate all output paths before creating any file; refuse links/partial rotations.
    for name in ['credentials.json', *(f'{service}-secret.json' for service in SERVICES)]:
        output = safety.no_symlinks(root / name)
        if output.exists():
            parser.error('bootstrap output already exists; refuse partial rotation')
    safety.write_private(root / 'credentials.json', json.dumps(credentials))
    for name, manifest in zip(SERVICES, manifests):
        safety.write_private(root / f'{name}-secret.json', json.dumps(manifest))
    print(f'Generated private bootstrap state in {root}; no cluster changes.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Bootstrap stopped: ' + type(exc).__name__, file=__import__('sys').stderr)
        raise SystemExit(1)
