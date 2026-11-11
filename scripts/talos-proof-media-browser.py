#!/usr/bin/env python3
"""Lease-gated private Chrome runner; no live execution without parent grant.

Verify the exact Gateway leaf with the independent private CA before extracting
its SPKI. Chrome trusts only that key, never a global certificate exception.
"""
import argparse
import base64
import hashlib
import importlib
import json
import secrets
from pathlib import Path
import socket
import ssl
import subprocess
import sys

safety = importlib.import_module('talos-proof-media-safety')


def verified_spki(ca, host):
    if host not in ('qbittorrent.proof.invalid', 'plex.proof.invalid', 'jellyfin.proof.invalid'):
        raise ValueError('unsupported browser proof host')
    context = ssl.create_default_context(cafile=str(safety.private_file(ca)))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection(('127.0.0.1', 18443), timeout=15) as tcp:
        with context.wrap_socket(tcp, server_hostname=host) as tls:
            certificate = tls.getpeercert(binary_form=True)
    public = subprocess.run(['openssl', 'x509', '-inform', 'DER', '-pubkey', '-noout'],
                            input=certificate, capture_output=True, timeout=10, check=True).stdout
    der = subprocess.run(['openssl', 'pkey', '-pubin', '-outform', 'DER'],
                         input=public, capture_output=True, timeout=10, check=True).stdout
    return base64.b64encode(hashlib.sha256(der).digest()).decode()


def lease_group(service, group=None):
    """Validate membership before any target connection; never expand exclusivity."""
    if service not in ('qbittorrent', 'plex', 'jellyfin'):
        raise ValueError('unsupported browser service')
    group = group or service
    if group != service:
        if service == 'qbittorrent' or service not in safety.DEPENDENCY_BATCHES.get(group, ()):
            raise ValueError('browser service is not a member of the exact dependency lease')
    return group


def check_lease(service, group=None):
    group = lease_group(service, group)
    safety.lease(group)
    safety.exclusivity(group)
    return group


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=['qbittorrent', 'plex', 'jellyfin'])
    parser.add_argument('--require-secure-cookie', action='store_true', help='qBit security followup gate; no app settings changed by runner')
    parser.add_argument('--jellyfin-lifecycle', action='store_true', help='real native start/progress/stop, resume and outsider denial')
    parser.add_argument('--resume-record', help='explicit prior Jellyfin functional basename; consume actual server resume')
    parser.add_argument('--tautulli', action='store_true', help='concurrent real decoder/timeline/activity/history gate')
    parser.add_argument('--group', help='exact existing dependency lease group; never a second lease')
    parser.add_argument('--media-path', help='exact same-origin MP4 path from real server scan')
    parser.add_argument('--fixture', type=Path, help='new immutable twelve-second H264 fixture')
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--ca', type=Path, required=True)
    parser.add_argument('--module', type=Path, required=True, help='installed Playwright module, no install/download')
    args = parser.parse_args()
    state = safety.private_dir(args.state)
    group = check_lease(args.service, args.group)
    if args.tautulli and (args.service != 'plex' or group != 'media-plex-tautulli'):
        raise ValueError('Tautulli decoder requires exact dependency group and Plex member')
    if args.jellyfin_lifecycle and (args.service != 'jellyfin' or group != 'jellyfin'):
        raise ValueError('Jellyfin lifecycle requires exact standalone receipt')
    if args.resume_record and not args.jellyfin_lifecycle:
        raise ValueError('resume requires real Jellyfin lifecycle')
    if args.require_secure_cookie and args.service != 'qbittorrent':
        raise ValueError('Secure-cookie followup is qBit-only')
    credentials = json.loads(safety.read_private(state / 'credentials.json'))[args.service]
    payload = {'service': args.service, 'group': group, 'state': str(state), 'module': str(args.module.resolve()),
               'requireSecureCookie': args.require_secure_cookie, 'spki': verified_spki(args.ca, args.service + '.proof.invalid'), **credentials}
    if args.service != 'qbittorrent':
        import re
        allowed = (r'/library/parts/[0-9]+/[0-9]+/file\.mp4' if args.service == 'plex'
                   else r'/Videos/[a-fA-F0-9-]+/stream\.mp4\?static=true')
        if not args.media_path or not re.fullmatch(allowed, args.media_path):
            raise ValueError('exact scanned original MP4 path required; no arbitrary query/URL')
        if args.fixture is None or args.fixture.name != 'Proof Browser Fixture (2000).mp4':
            raise ValueError('new immutable browser fixture required')
        if args.jellyfin_lifecycle:
            jellyfin = importlib.import_module('talos-proof-media-jellyfin')
            bridge = jellyfin.prepare_bridge(state, args.ca, args.fixture, args.resume_record)
            headers = jellyfin.session_headers(state, bridge)
            payload['bridge'] = bridge
        else:
            headers = {'X-Plex-Token': credentials['api_key']} if args.service == 'plex' else {
                'X-Emby-Token': json.loads(safety.read_private(state / 'jellyfin-session.json'))['token']}
        api = importlib.import_module('talos-proof-media-http').API(
            'https://' + args.service + '.proof.invalid:18443', headers, service=args.service, ca=args.ca)
        expected = safety.read_private(args.fixture, binary=True)
        if hashlib.sha256(api.call(args.media_path, raw=True)).digest() != hashlib.sha256(expected).digest():
            raise RuntimeError('actual server stream is not the new immutable fixture')
        if args.tautulli:
            playback = importlib.import_module('talos-proof-media-playback')
            bridge = playback.prepare(state, args.ca, group)
            headers.update({'X-Plex-Client-Identifier': bridge['client'], 'X-Plex-Session-Identifier': bridge['session']})
            payload['bridge'] = bridge
        payload.update(mediaPath=args.media_path, headers=headers)
    process = subprocess.run(['node', str(safety.ROOT / 'tests/talos-proof-media-browser.mjs')],
                             input=json.dumps(payload).encode(), capture_output=True, timeout=150)
    # Child deliberately emits only fixed check names/status; never forward stderr.
    result = json.loads(process.stdout)
    if args.tautulli and not process.returncode and result.get('status') == 'PASS':
        try:
            playback.finish(state, args.ca, bridge, result['decoder'])
            result['checks'].append('same-client actual Tautulli activity and durable history')
        except Exception as exc:
            result.update(status='FAIL', failed_stage='Tautulli durable history', failure_type=type(exc).__name__)
    if args.jellyfin_lifecycle and not process.returncode and result.get('status') == 'PASS':
        try:
            result['functional_record'] = jellyfin.finish(state, args.ca, args.fixture, bridge, result['decoder'])
            result['checks'].append('actual Jellyfin lifecycle/resume readback and authenticated outsider denial')
        except Exception as exc:
            result.update(status='FAIL', failed_stage='Jellyfin lifecycle/resume/ACL readback', failure_type=type(exc).__name__)
    # Retain every safe browser verdict, including failures; never credentials,
    # DOM, raw child stderr, cookies or exception messages.
    safety.write_private(state / ('browser-attempt-' + secrets.token_hex(8) + '.json'), json.dumps(result))
    print(json.dumps(result))
    if process.returncode or result.get('status') != 'PASS':
        raise RuntimeError('browser checks failed; no acceptance')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Browser stopped: ' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
