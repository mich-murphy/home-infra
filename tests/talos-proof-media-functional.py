#!/usr/bin/env python3
"""Offline proof-only API checks. Port-forward to loopback; never print tokens/bodies.

These tests fail on incompatible API behavior. A pass covers only the named checks,
not historical-data restore, downloads, metadata lookups or integration readiness.
"""
import argparse
import hashlib
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


class API:
    def __init__(self, base, headers=None):
        parsed = urllib.parse.urlparse(base)
        if parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.scheme != 'http':
            raise ValueError('only loopback HTTP port forwards accepted')
        self.base, self.headers = base.rstrip('/'), headers or {}
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, method='GET', data=None, form=None, raw=False, headers=None):
        hdr = {**self.headers, **(headers or {})}
        if data is not None:
            payload = json.dumps(data).encode()
            hdr['Content-Type'] = 'application/json'
        elif form is not None:
            payload = urllib.parse.urlencode(form).encode()
            hdr['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            payload = None
        req = urllib.request.Request(self.base + path, data=payload, method=method, headers=hdr)
        with self.opener.open(req, timeout=30) as response:
            body = response.read()
        if raw:
            return body
        return json.loads(body) if body else None


def arr(api, service, credential):
    version = 'v1' if service in ('prowlarr', 'lidarr') else 'v3'
    prefix = '/api/' + version
    # API credentials must actually be checked; "External" is only UI auth delegation.
    rejected = False
    try:
        API(api.base).call(prefix + '/tag')
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


def qbit(api, credential):
    result = api.call('/api/v2/auth/login', 'POST', form={'username': credential['username'], 'password': credential['password']}, raw=True)
    assert result == b'Ok.', 'fresh qBittorrent credential rejected'
    assert api.call('/api/v2/torrents/info') == [], 'proof must have no actual torrents'
    prefs = api.call('/api/v2/app/preferences')
    assert not prefs['dht'] and not prefs['pex'] and not prefs['lsd'], 'discovery must remain disabled'
    old = prefs['max_active_downloads']
    try:
        api.call('/api/v2/app/setPreferences', 'POST', form={'json': json.dumps({'max_active_downloads': 1 if old != 1 else 2})}, raw=True)
        assert api.call('/api/v2/app/preferences')['max_active_downloads'] != old
    finally:
        api.call('/api/v2/app/setPreferences', 'POST', form={'json': json.dumps({'max_active_downloads': old})}, raw=True)
    return ['fresh credential login', 'empty torrent queue', 'discovery disabled', 'settings write/read/restore']


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
    (state / 'jellyfin-session.json').write_text(json.dumps({'token': auth['AccessToken'], 'user_id': uid}))
    (state / 'jellyfin-session.json').chmod(0o600)
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
    expected = fixture.read_bytes()
    assert hashlib.sha256(payload).digest() == hashlib.sha256(expected).digest(), 'stream bytes differ from synthetic fixture'
    # HTTP byte ranges establish a real seek/read, not just an HTTP 200 health check.
    chunk = api.call(f'/Audio/{item}/stream?static=true', raw=True, headers={'Range': 'bytes=44-107'})
    assert chunk == expected[44:108], 'seek range not honored'
    api.call(f'/Users/{uid}/PlayedItems/{item}', 'POST')
    assert api.call(f'/Users/{uid}/Items/{item}')['UserData']['Played'] is True
    return ['fresh admin setup/login', 'offline fixture library scan', 'stream SHA256 matches', 'byte-range seek', 'persisted played flag (restart still required)']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('service', choices=['radarr', 'sonarr', 'lidarr', 'prowlarr', 'qbittorrent', 'sabnzbd', 'jellyfin'])
    p.add_argument('--base', required=True)
    p.add_argument('--state-dir', required=True, type=Path)
    p.add_argument('--fixture', type=Path)
    args = p.parse_args()
    state = args.state_dir.expanduser().resolve()
    credentials = json.loads((state / 'credentials.json').read_text())[args.service]
    api = API(args.base)
    try:
        if args.service in ('radarr', 'sonarr', 'lidarr', 'prowlarr'):
            checks = arr(api, args.service, credentials)
        elif args.service == 'qbittorrent':
            checks = qbit(api, credentials)
        elif args.service == 'sabnzbd':
            checks = sab(api, credentials)
        else:
            if not args.fixture:
                p.error('Jellyfin requires --fixture for exact playback verification')
            checks = jellyfin(api, credentials, args.fixture, state)
    except Exception as exc:
        # HTTP exception text can include URL credentials/query strings; never print it.
        print(json.dumps({'service': args.service, 'result': 'FAIL', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
    print(json.dumps({'service': args.service, 'result': 'PASS', 'checks': checks}))

if __name__ == '__main__':
    main()
