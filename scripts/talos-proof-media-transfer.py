#!/usr/bin/env python3
"""Explicit parent-leased qBit/BEP3 or SAB/NNTP transfer; no external provider.

Fixture has no client PVC. Only real app downloads can populate output. Verify
reads existing completion/hash without submission or destination initialization.
"""
import argparse
import base64
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import secrets
import sys
import time
import urllib.parse

safety = importlib.import_module('talos-proof-media-safety')
API = importlib.import_module('talos-proof-media-http').API
NAME = 'synthetic-proof.wav'


def expect(ok, message):
    if not ok:
        raise RuntimeError(message)


def multipart(fields, field, filename, payload):
    boundary = 'proof-' + secrets.token_hex(16)
    chunks = []
    for key, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
               payload, f'\r\n--{boundary}--\r\n'.encode()]
    return b''.join(chunks), {'Content-Type': 'multipart/form-data; boundary=' + boundary}


def pod_name(service, app):
    pods = json.loads(safety.kube(service, '-n', 'proof-' + service, 'get', 'pods', '-l',
                                'app.kubernetes.io/name=' + app, '-o', 'json'))['items']
    active = [p for p in pods if not p['metadata'].get('deletionTimestamp') and p.get('status', {}).get('phase') == 'Running']
    expect(len(active) == 1, 'expected one selected running pod')
    return active[0]['metadata']['name']


def fixture_get(service, path):
    expect(path in ('/stats', '/artifact.torrent', '/artifact.nzb'), 'unexpected fixture endpoint')
    return safety.kube(service, '-n', 'proof-' + service, 'exec', pod_name(service, 'download-protocols'), '--',
                       'python3', '-c', 'import sys,urllib.request; sys.stdout.buffer.write(urllib.request.urlopen("http://127.0.0.1:8080"+sys.argv[1],timeout=5).read())', path)


def remote(service, script, *args):
    return safety.kube(service, '-n', 'proof-' + service, 'exec', pod_name(service, service), '--',
                       '/bin/sh', '-ec', script, 'proof', *args)


def empty_destination(service, path):
    expect(path.startswith('/data/') and '..' not in PurePosixPath(path).parts, 'unsafe proof output path')
    # Exclusive directory creation is a prerequisite, not a cleanup of a preexisting output.
    remote(service, 'test ! -e "$1"; mkdir -p "$(dirname "$1")"; mkdir "$1"; test -z "$(ls -A "$1")"', path)


def output_hash(service, path, marker):
    p = PurePosixPath(path)
    expect(p.is_absolute() and str(p).startswith('/data/') and '..' not in p.parts and p.name == NAME, 'output escaped proof destination')
    values = remote(service, 'test -f "$1"; test ! -L "$1"; wc -c < "$1"; sha256sum "$1"', str(p)).decode().splitlines()
    expect(len(values) == 2 and int(values[0]) == marker['size'] and values[1].split()[0] == marker['sha256'], 'completed output checksum/size differs from fixture')


def counters(before, after, service, size):
    expect(before['sha256'] == after['sha256'] and before['infohash'] == after['infohash'], 'fixture process/payload identity changed')
    keys = ('tracker_announces', 'peer_handshakes', 'piece_requests', 'piece_bytes') if service == 'qbittorrent' else ('nntp_auth', 'nntp_body_requests', 'nntp_payload_bytes')
    delta = {k: after['counters'][k] - before['counters'][k] for k in keys}
    expect(all(v > 0 for v in delta.values()), 'no genuine positive protocol transfer counters')
    expect(delta[keys[-1]] >= size, 'fixture sent fewer bytes than payload size')
    return delta


def qbit(api, service, credentials, state, phase):
    expect(api.call('/api/v2/auth/login', 'POST', form={'username': credentials['username'], 'password': credentials['password']}, raw=True) == b'Ok.', 'qBit login rejected')
    prefs = api.call('/api/v2/app/preferences')
    expect(not prefs['dht'] and not prefs['pex'] and not prefs['lsd'], 'qBit discovery must remain disabled')
    if phase == 'exercise':
        expect(api.call('/api/v2/torrents/info') == [], 'qBit transfer requires empty queue')
        before = json.loads(fixture_get(service, '/stats'))
        marker = {k: before[k] for k in ('name', 'size', 'sha256', 'infohash')}
        marker['destination'] = '/data/torrents/protocol-' + secrets.token_hex(6)
        empty_destination(service, marker['destination'])
        safety.write_private(state / (service + '-transfer-attempt.json'), json.dumps(marker))
        body, headers = multipart({'savepath': marker['destination'], 'autoTMM': 'false'}, 'torrents', 'proof.torrent', fixture_get(service, '/artifact.torrent'))
        expect(api.call('/api/v2/torrents/add', 'POST', payload=body, headers=headers, raw=True) == b'Ok.', 'torrent submission rejected')
    else:
        marker = json.loads(safety.read_private(state / (service + '-transfer.json')))
    torrent = None
    for attempt in range(60 if phase == 'exercise' else 1):
        matches = api.call('/api/v2/torrents/info?hashes=' + marker['infohash'])
        if len(matches) == 1 and matches[0]['progress'] == 1:
            torrent = matches[0]
            break
        if phase == 'exercise':
            time.sleep(2)
    expect(torrent is not None and torrent['amount_left'] == 0 and torrent['completed'] == marker['size'], 'qBit did not report actual completed payload')
    output_hash(service, marker['destination'] + '/' + NAME, marker)
    if phase == 'exercise':
        after = json.loads(fixture_get(service, '/stats'))
        marker['protocol_delta'] = counters(before, after, service, marker['size'])
        marker['fixture_before'], marker['fixture_after'] = before, after
    return marker


def sab_call(api, credential, mode, **values):
    return api.call('/api', 'POST', form={'apikey': credential['api_key'], 'output': 'json', 'mode': mode, **values})


def sab(api, service, credential, state, phase):
    call = lambda mode, **kw: sab_call(api, credential, mode, **kw)
    if phase == 'exercise':
        expect(call('queue')['queue']['noofslots'] == 0, 'SAB transfer requires empty queue')
        expect(not call('history')['history']['slots'], 'SAB transfer requires fresh history')
        servers = call('get_config', section='servers')['config']['servers']
        expect(not servers, 'refuse to alter existing SAB provider configuration')
        before = json.loads(fixture_get(service, '/stats'))
        marker = {k: before[k] for k in ('name', 'size', 'sha256', 'infohash')}
        marker['destination'] = '/data/usenet/protocol-' + secrets.token_hex(6)
        empty_destination(service, marker['destination'])
        # Preserve misc config privately; restore in a separately explicit cleanup action.
        marker['original_misc'] = call('get_config', section='misc')['config']['misc']
        safety.write_private(state / (service + '-transfer-attempt.json'), json.dumps(marker))
        for key, value in [('download_dir', marker['destination'] + '/incomplete'), ('complete_dir', marker['destination'] + '/complete')]:
            call('set_config', section='misc', keyword=key, value=value)
        call('set_config', section='servers', keyword='proof-fixture', host='download-protocols', port=8119,
             username='fixture', password='fixture-public', ssl=0, enable=1, connections=2, retention=0, send_group=0)
        configured = call('get_config', section='servers')['config']['servers']
        expect(len(configured) == 1, 'SAB must have exactly one fixture server')
        body, headers = multipart({'apikey': credential['api_key'], 'output': 'json', 'mode': 'addfile', 'pp': '0', 'script': 'None', 'nzbname': 'synthetic-proof'},
                                  'nzbfile', 'proof.nzb', fixture_get(service, '/artifact.nzb'))
        submission = api.call('/api', 'POST', payload=body, headers=headers)
        expect(submission['status'] and len(submission['nzo_ids']) == 1, 'SAB NZB submission rejected')
        marker['nzo_id'] = submission['nzo_ids'][0]
    else:
        marker = json.loads(safety.read_private(state / (service + '-transfer.json')))
    complete = None
    for attempt in range(90 if phase == 'exercise' else 1):
        slots = call('history')['history']['slots']
        complete = next((x for x in slots if x['nzo_id'] == marker['nzo_id']), None)
        if complete is not None:
            break
        if phase == 'exercise':
            time.sleep(2)
    expect(complete is not None and complete['status'] == 'Completed' and not complete.get('fail_message'), 'SAB did not report successful completed history')
    storage = PurePosixPath(complete['storage'])
    expect(str(storage).startswith(marker['destination'] + '/'), 'SAB output escaped unique empty destination')
    output = str(storage) if storage.name == NAME else str(storage / NAME)
    output_hash(service, output, marker)
    marker['output'] = output
    if phase == 'exercise':
        after = json.loads(fixture_get(service, '/stats'))
        marker['protocol_delta'] = counters(before, after, service, marker['size'])
        marker['fixture_before'], marker['fixture_after'] = before, after
    return marker


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['start-fixture', 'stop-fixture', 'exercise', 'verify', 'cleanup-settings'])
    p.add_argument('service', choices=['qbittorrent', 'sabnzbd'])
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--ca', type=Path)
    args = p.parse_args()
    state = safety.private_dir(args.state)
    svc, ns = args.service, 'proof-' + args.service
    safety.lease(svc)
    safety.exclusivity(svc)
    def kube(*cmd, **kw):
        return safety.kube(svc, '-n', ns, *cmd, **kw)
    if args.action == 'stop-fixture':
        # Stop remains possible even if admission memory has since fallen.
        importlib.import_module('talos-proof-media-observe').capture(svc, state)
        kube('scale', 'deployment', 'download-protocols', '--replicas=0')
        kube('wait', '--for=delete', 'pod', '-l', 'app.kubernetes.io/name=download-protocols', '--timeout=180s')
        kube('delete', 'networkpolicy', 'protocol-fixture-only', 'to-protocol-fixture-only', '--ignore-not-found=true')
        print(json.dumps({'service': svc, 'fixture': 'STOPPED_AND_PODS_DELETED'}))
        return
    if args.action == 'start-fixture':
        safety.protocol_guard(svc)
        payload = safety.read_private(state / 'proof-tone.wav', binary=True)
        expect(len(payload) == 32044 and hashlib.sha256(payload).hexdigest() == '3efcae84508fce7c87b5366774aa9cc25b54281a4b5f9301761c270c90b12562', 'only generated synthetic WAV is authorized')
        safety.require_helpers_deleted(svc)
        config = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'protocol-payload', 'namespace': ns,
                  'labels': {'app.kubernetes.io/part-of': 'talos-proof'}}, 'immutable': True,
                  'binaryData': {NAME: base64.b64encode(payload).decode()}}
        kube('apply', '-f', '-', data=json.dumps(config).encode())
        kube('apply', '-k', str(safety.ROOT / 'kubernetes/apps/media' / ('protocol-' + svc)))
        safety.protocol_guard(svc)
        kube('scale', 'deployment', 'download-protocols', '--replicas=1')
        kube('rollout', 'status', 'deployment/download-protocols', '--timeout=120s')
        stats = json.loads(fixture_get(svc, '/stats'))
        expect(stats['sha256'] == hashlib.sha256(payload).hexdigest(), 'fixture content identity differs')
        print(json.dumps({'service': svc, 'fixture': 'STARTED', 'source': stats}))
        return
    expect(args.ca is not None, 'trusted Gateway CA required')
    if args.action == 'exercise':
        safety.protocol_guard(svc)
        expect(not (state / (svc + '-transfer.json')).exists(), 'refuse to overwrite retained transfer evidence')
    else:
        # Verify can run with fixture OFF during restart/restore; reads no fixture endpoints.
        safety.guard(svc)
    credential = json.loads(safety.read_private(state / 'credentials.json'))[svc]
    api = API('https://' + svc + '.proof.invalid:18443', service=svc, ca=safety.private_file(args.ca))
    api.wait_ready('/')
    if args.action == 'cleanup-settings':
        expect(svc == 'sabnzbd', 'only SAB temporary provider settings need cleanup')
        marker_path = state / (svc + '-transfer.json')
        if not marker_path.exists():
            marker_path = state / (svc + '-transfer-attempt.json')
        retained = json.loads(safety.read_private(marker_path))
        sab_call(api, credential, 'del_config', section='servers', keyword='proof-fixture')
        for key in ('download_dir', 'complete_dir'):
            sab_call(api, credential, 'set_config', section='misc', keyword=key, value=retained['original_misc'][key])
        expect(not sab_call(api, credential, 'get_config', section='servers')['config']['servers'], 'temporary server not removed')
        print(json.dumps({'service': svc, 'result': 'TEMPORARY_PROVIDER_REMOVED', 'outputs_retained': True}))
        return
    marker = (qbit if svc == 'qbittorrent' else sab)(api, svc, credential, state, args.action)
    if args.action == 'exercise':
        safety.write_private(state / (svc + '-transfer.json'), json.dumps(marker))
    print(json.dumps({'service': svc, 'result': 'PASS', 'scope': 'protocol transfer completion+output checksum' if args.action == 'exercise' else 'existing completed state+output checksum before writes',
                      'sha256': marker['sha256'], 'size': marker['size'], 'protocol_delta': marker['protocol_delta']}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None),
                          'check': str(exc) if isinstance(exc, RuntimeError) else None}))
        raise SystemExit(1)
