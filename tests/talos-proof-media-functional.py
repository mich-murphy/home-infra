#!/usr/bin/env python3
"""Offline proof-only API checks. Port-forward to loopback; never print tokens/bodies.

These tests fail on incompatible API behavior. A pass covers only the named checks,
not historical-data restore, downloads, metadata lookups or integration readiness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse


import importlib
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
safety = importlib.import_module('talos-proof-media-safety')
API = importlib.import_module('talos-proof-media-http').API
services = importlib.import_module('talos-proof-media-services')


def arr(api, service, credential):
    version = 'v1' if service in ('prowlarr', 'lidarr') else 'v3'
    prefix = '/api/' + version
    # API credentials must actually be checked; "External" is only UI auth delegation.
    rejected = False
    try:
        api.anonymous().call(prefix + '/tag')
    except urllib.error.HTTPError as exc:
        rejected = exc.code in (401, 403)
    assert rejected, 'unauthenticated API did not reject the request'
    api.headers['X-Api-Key'] = credential['api_key']
    api.call(prefix + '/system/status')
    label = 'proof-crud-' + str(time.time_ns())
    tag = api.call(prefix + '/tag', 'POST', {'label': label})
    ident = tag['id']
    try:
        assert api.call(prefix + f'/tag/{ident}')['label'] == label
        api.call(prefix + f'/tag/{ident}', 'PUT', {'id': ident, 'label': label + '-updated'})
        assert api.call(prefix + f'/tag/{ident}')['label'] == label + '-updated'
    finally:
        api.call(prefix + f'/tag/{ident}', 'DELETE')
    assert all(x['id'] != ident for x in api.call(prefix + '/tag'))
    # Root-folder settings exercise local filesystem mapping without lookup/search/download.
    if service in ('radarr', 'sonarr'):
        roots = api.call(prefix + '/rootfolder')
        assert not roots, 'fresh-state rootfolder test requires no existing roots'
        root = api.call(prefix + '/rootfolder', 'POST', {'path': '/data'})
        try:
            assert any(x['id'] == root['id'] for x in api.call(prefix + '/rootfolder'))
        finally:
            api.call(prefix + '/rootfolder/' + str(root['id']), 'DELETE')
    return ['API denies missing key', 'tag create/read/update/delete', 'local rootfolder settings' if service in ('radarr', 'sonarr') else 'system status version']


def sab(api, credential):
    def call(mode, **extra):
        return api.call('/api?' + urllib.parse.urlencode({'apikey': credential['api_key'], 'output': 'json', 'mode': mode, **extra}))
    assert call('queue')['queue']['noofslots'] == 0
    before = call('get_config', section='misc', keyword='refresh_rate')['config']['misc']['refresh_rate']
    changed = 2 if int(before) != 2 else 3
    try:
        assert call('set_config', section='misc', keyword='refresh_rate', value=changed)['status']
        assert int(call('get_config', section='misc', keyword='refresh_rate')['config']['misc']['refresh_rate']) == changed
    finally:
        call('set_config', section='misc', keyword='refresh_rate', value=before)
    return ['empty download queue', 'API settings write/read/restore']


def jellyfin(api, credential, fixture, state):
    public = api.call('/System/Info/Public')
    if not public['StartupWizardCompleted']:
        api.call('/Startup/Configuration', 'POST', {'UICulture': 'en-US', 'MetadataCountryCode': 'US', 'PreferredMetadataLanguage': 'en'})
        api.call('/Startup/User', 'POST', {'Name': credential['username'], 'Password': credential['password']})
        api.call('/Startup/RemoteAccess', 'POST', {'EnableRemoteAccess': False, 'EnableAutomaticPortMapping': False})
        api.call('/Startup/Complete', 'POST')
    auth = api.call('/Users/AuthenticateByName', 'POST', {'Username': credential['username'], 'Pw': credential['password']}, headers={'Authorization': 'MediaBrowser Client="TalosProof", Device="Loopback", DeviceId="proof-functional", Version="1"'})
    api.headers['X-Emby-Token'] = auth['AccessToken']
    uid = auth['User']['Id']
    safety.write_private(state / 'jellyfin-session.json', json.dumps({'token': auth['AccessToken'], 'user_id': uid}), replace=True)
    libraries = api.call('/Library/VirtualFolders')
    if not any(x['Name'] == 'Proof' for x in libraries):
        api.call('/Library/VirtualFolders?name=Proof&collectionType=music&refreshLibrary=true', 'POST', {'LibraryOptions': {'PathInfos': [{'Path': '/data/media'}], 'EnableInternetProviders': False, 'EnableRealtimeMonitor': False, 'SaveLocalMetadata': False, 'EnableAutomaticSeriesGrouping': False, 'MetadataSavers': [], 'DisabledLocalMetadataReaders': []}})
    api.call('/Library/Refresh', 'POST')
    items = []
    for _ in range(30):
        items = api.call(f'/Users/{uid}/Items?Recursive=true&IncludeItemTypes=Audio')['Items']
        if items:
            break
        time.sleep(2)  # Bounded application indexing, not CI polling.
    assert len(items) == 1, 'expected exactly one generated audio fixture'
    item = items[0]['Id']
    payload = api.call(f'/Audio/{item}/stream?static=true', raw=True)
    expected = safety.read_private(fixture, binary=True)
    assert hashlib.sha256(payload).digest() == hashlib.sha256(expected).digest(), 'stream bytes differ from synthetic fixture'
    # HTTP byte ranges establish a real seek/read, not just an HTTP 200 health check.
    chunk = api.call(f'/Audio/{item}/stream?static=true', raw=True, headers={'Range': 'bytes=44-107'})
    assert chunk == expected[44:108], 'seek range not honored'
    api.call(f'/Users/{uid}/PlayedItems/{item}', 'POST')
    assert api.call(f'/Users/{uid}/Items/{item}')['UserData']['Played'] is True
    return ['fresh admin setup/login', 'offline fixture library scan', 'stream SHA256 matches', 'byte-range seek', 'persisted played flag (restart still required)']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('service', choices=['radarr', 'sonarr', 'lidarr', 'prowlarr', 'qbittorrent', 'sabnzbd', 'jellyfin', 'audiobookshelf', 'pinchflat', 'qbitwebui', 'plex'])
    p.add_argument('--base', required=True)
    p.add_argument('--phase', choices=['exercise', 'verify'], default='exercise')
    p.add_argument('--group', choices=['media-pipeline'], help='explicit integration profile lease')
    p.add_argument('--pair', choices=safety.PIPELINE_PAIRS)
    p.add_argument('--state-dir', required=True, type=Path)
    p.add_argument('--fixture', type=Path)
    p.add_argument('--ca', required=True, type=Path, help='private trusted proof Gateway CA PEM')
    args = p.parse_args()
    state = safety.private_dir(args.state_dir)
    credentials = json.loads(safety.read_private(state / 'credentials.json'))[args.service]
    group = args.group or args.service
    if args.group:
        safety.select_pipeline(args.pair)
        if args.service not in safety.PIPELINE_MEMBERS:
            p.error('functional service must belong to selected pipeline pair')
    elif args.pair:
        p.error('--pair requires --group media-pipeline')
    safety.lease(group)
    safety.exclusivity(group)
    ca = safety.private_file(args.ca)
    api = API(args.base, service=('pipeline-' if args.group else '') + args.service, ca=ca)
    try:
        if args.service in ('audiobookshelf', 'pinchflat', 'qbitwebui', 'qbittorrent', 'plex'):
            checks = getattr(services, args.service)(api, credentials, args.fixture, state, args.phase)
        elif args.phase != 'exercise':
            p.error('persistence verification phase not implemented for this service yet')
        elif args.service in ('radarr', 'sonarr', 'lidarr', 'prowlarr'):
            checks = arr(api, args.service, credentials)
        elif args.service == 'sabnzbd':
            checks = sab(api, credentials)
        else:
            if not args.fixture:
                p.error('Jellyfin requires --fixture for exact playback verification')
            checks = jellyfin(api, credentials, args.fixture, state)
    except Exception as exc:
        # HTTP exception text can include URL credentials/query strings; never print it.
        print(json.dumps({'service': args.service, 'result': 'FAIL', 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None),
                          'check': str(exc) if isinstance(exc, (RuntimeError, AssertionError)) else None}))
        raise SystemExit(1)
    print(json.dumps({'service': args.service, 'result': 'PASS', 'checks': checks}))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None),
                          'check': str(exc) if isinstance(exc, (RuntimeError, AssertionError)) else None}))
        raise SystemExit(1)
