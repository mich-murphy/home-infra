#!/usr/bin/env python3
"""Version-specific offline-workflow tests for fresh proof-only media services.

exercise records durable markers; verify checks existing values before writing any
application data. Both modes require the caller's exact-target coordinator lease.
"""
import base64
from html.parser import HTMLParser
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
safety = importlib.import_module('talos-proof-media-safety')


def expect(condition, message):
    if not condition:
        raise RuntimeError(message)


def reject_anonymous(api, path):
    try:
        api.anonymous().call(path, raw=True)
    except urllib.error.HTTPError as exc:
        expect(exc.code in (401, 403), 'anonymous request failed with unexpected status')
        return
    raise RuntimeError('anonymous access unexpectedly allowed')


def record(state, service, marker):
    safety.write_private(state / (service + '-functional.json'), json.dumps(marker), replace=True)


def existing(state, service):
    return json.loads(safety.read_private(state / (service + '-functional.json')))


def audio_checksum(api, path, fixture):
    parsed = urllib.parse.urlsplit(path)
    expect(not parsed.netloc and path.startswith('/') and not path.startswith('//'), 'stream URL escaped proof origin')
    expected = safety.read_private(fixture, binary=True)
    actual = api.call(path, raw=True)
    expect(hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest(), 'playback bytes do not match synthetic fixture')
    seek = api.call(path, raw=True, headers={'Range': 'bytes=44-107'})
    expect(api.last_status == 206 and seek == expected[44:108], 'playback seek did not return exact HTTP byte range')
    return hashlib.sha256(actual).hexdigest()


def audiobookshelf(api, credential, fixture, state, phase):
    expect(fixture is not None, 'ABS requires generated --fixture')
    if not api.call('/status')['isInit']:
        expect(phase == 'exercise', 'fresh server encountered during persistence verification')
        api.call('/init', 'POST', {'newRoot': {'username': credential['username'], 'password': credential['password']}}, raw=True)
    reject_anonymous(api, '/api/libraries')
    auth = api.call('/login', 'POST', {'username': credential['username'], 'password': credential['password']})
    api.headers['Authorization'] = 'Bearer ' + auth['user']['accessToken']
    libraries = api.call('/api/libraries')['libraries']
    if phase == 'verify':
        marker = existing(state, 'audiobookshelf')
        expect(any(x['id'] == marker['library_id'] and x['name'] == 'Proof' for x in libraries), 'ABS library lost across restart/restore')
        item = marker['item_id']
        progress = api.call('/api/me/progress/' + item)
        expect(abs(progress['currentTime'] - 0.5) < 0.01, 'ABS persisted playback position differs')
        bookmarks = api.call('/api/me/bookmarks/' + item)['bookmarks']
        expect(any(x['title'] == 'proof-bookmark-updated' and x['time'] == 0.25 for x in bookmarks), 'ABS durable bookmark lost')
    else:
        library = next((x for x in libraries if x['name'] == 'Proof'), None)
        if library is None:
            library = api.call('/api/libraries', 'POST', {'name': 'Proof', 'folders': [{'fullPath': '/data/audiobooks'}], 'mediaType': 'book', 'settings': {'disableWatcher': True, 'autoScanCronExpression': None, 'skipMatchingMediaWithAsin': True}})
        library_id = library['id']
        api.call('/api/libraries/' + library_id + '/scan', 'POST', raw=True)
        items = []
        for _ in range(30):
            items = api.call('/api/libraries/' + library_id + '/items')['results']
            if items:
                break
            time.sleep(2)
        expect(len(items) == 1, 'ABS expected exactly one synthetic audiobook')
        item = items[0]['id']
        api.call('/api/me/progress/' + item, 'PATCH', {'currentTime': 0.5, 'duration': 2, 'progress': 0.25, 'isFinished': False}, raw=True)
        expect(abs(api.call('/api/me/progress/' + item)['currentTime'] - 0.5) < 0.01, 'ABS progress roundtrip failed')
        api.call('/api/me/item/' + item + '/bookmark', 'POST', {'time': 0.25, 'title': 'proof-bookmark'}, raw=True)
        api.call('/api/me/item/' + item + '/bookmark', 'PATCH', {'time': 0.25, 'title': 'proof-bookmark-updated'}, raw=True)
        # A second temporary bookmark exercises deletion without deleting durable evidence.
        api.call('/api/me/item/' + item + '/bookmark', 'POST', {'time': 0.75, 'title': 'proof-delete'}, raw=True)
        api.call('/api/me/item/' + item + '/bookmark/0.75', 'DELETE', raw=True)
        bookmarks = api.call('/api/me/bookmarks/' + item)['bookmarks']
        expect(any(x['title'] == 'proof-bookmark-updated' for x in bookmarks) and not any(x['title'] == 'proof-delete' for x in bookmarks), 'ABS bookmark CRUD failed')
        marker = {'library_id': library_id, 'item_id': item}
    session = api.call('/api/items/' + item + '/play', 'POST', {'deviceInfo': {'deviceId': 'talos-proof', 'clientName': 'TalosProof'}, 'supportedMimeTypes': ['audio/wav', 'audio/x-wav'], 'mediaPlayer': 'html5', 'forceDirectPlay': True, 'forceTranscode': False})
    try:
        expect(len(session['audioTracks']) == 1, 'ABS unexpected playback track count')
        marker['stream_sha256'] = audio_checksum(api, session['audioTracks'][0]['contentUrl'], fixture)
    finally:
        api.call('/api/session/' + session['id'] + '/close', 'POST', raw=True)
    if phase == 'exercise':
        record(state, 'audiobookshelf', marker)
    return ['fresh local login', 'anonymous API rejected', 'offline audiobook scan', 'direct playback SHA256 and range seek', 'progress and bookmark CRUD' if phase == 'exercise' else 'existing library/progress/bookmark verified before writes']


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name'):
            self.inputs[attrs['name']] = attrs.get('value', '')


def csrf(page):
    parser = Inputs()
    parser.feed(page.decode())
    token = parser.inputs.get('_csrf_token')
    expect(bool(token), 'Pinchflat CSRF token missing')
    return token


def pinchflat(api, credential, fixture, state, phase):
    reject_anonymous(api, '/media_profiles')
    token = base64.b64encode((credential['username'] + ':' + credential['password']).encode()).decode()
    api.headers['Authorization'] = 'Basic ' + token
    if phase == 'verify':
        marker = existing(state, 'pinchflat')
        page = api.call('/media_profiles/' + marker['id'], raw=True)
        expect(b'proof-profile-persistent' in page, 'Pinchflat profile lost across restart/restore')
        return ['fresh Basic authentication', 'existing nonempty profile verified before writes']
    page = api.call('/media_profiles/new', raw=True)
    form = {'_csrf_token': csrf(page), 'media_profile[name]': 'proof-profile-create',
            'media_profile[output_path_template]': 'proof/{{ title }}.{{ ext }}'}
    api.call('/media_profiles', 'POST', form=form, raw=True)
    # Onboarding may redirect to home; index then identifies only our unique name.
    page = api.call('/media_profiles', raw=True).decode()
    match = re.search(r'href="/media_profiles/(\d+)"[^>]*>\s*proof-profile-create\s*<', page)
    if match is None:
        # Phoenix markup may nest the display label inside elements. Use a bounded row.
        match = re.search(r'href="/media_profiles/(\d+)"(?:(?!</tr>).){0,1500}?proof-profile-create', page, re.S)
    expect(match is not None, 'Pinchflat created profile not found in index')
    ident = match.group(1)
    page = api.call('/media_profiles/' + ident + '/edit', raw=True)
    api.call('/media_profiles/' + ident, 'POST', form={'_method': 'put', '_csrf_token': csrf(page), 'media_profile[name]': 'proof-profile-persistent', 'media_profile[output_path_template]': 'proof-updated/{{ title }}.{{ ext }}'}, raw=True)
    page = api.call('/media_profiles/' + ident, raw=True)
    expect(b'proof-profile-persistent' in page and b'proof-updated/' in page, 'Pinchflat update/readback failed')
    record(state, 'pinchflat', {'id': ident})
    # Exercise deletion on a second profile, retaining the durable fixture profile.
    page = api.call('/media_profiles/new', raw=True)
    api.call('/media_profiles', 'POST', form={'_csrf_token': csrf(page), 'media_profile[name]': 'proof-profile-delete', 'media_profile[output_path_template]': 'delete/{{ title }}.{{ ext }}'}, raw=True)
    page = api.call('/media_profiles', raw=True).decode()
    temporary = re.search(r'href="/media_profiles/(\d+)"(?:(?!</tr>).){0,1500}?proof-profile-delete', page, re.S)
    expect(temporary is not None, 'Pinchflat temporary delete profile not found')
    temporary_id = temporary.group(1)
    page = api.call('/media_profiles/' + temporary_id + '/edit', raw=True)
    api.call('/media_profiles/' + temporary_id, 'POST', form={'_method': 'delete', '_csrf_token': csrf(page)}, raw=True)
    expect(b'proof-profile-delete' not in api.call('/media_profiles', raw=True), 'Pinchflat deleted profile still listed')
    # Deliberately keep this real, nonempty profile for restart verification. No Source exists.
    sources = api.call('/sources', raw=True)
    expect(b'proof.invalid/youtube' not in sources, 'unexpected proof download source')
    return ['fresh Basic authentication', 'anonymous access rejected', 'CSRF-protected profile create/read/update/delete', 'durable nonempty profile retained; no source/download created']


def qbitwebui(api, credential, fixture, state, phase):
    reject_anonymous(api, '/api/auth/me')
    auth = api.call('/api/auth/login', 'POST', {'username': credential['username'], 'password': credential['password']})
    expect(auth['username'] == 'proof', 'qbitwebui fresh user login mismatch')
    expect(api.call('/api/auth/me')['username'] == 'proof', 'qbitwebui session failed')
    all_credentials = json.loads(safety.read_private(state / 'credentials.json'))
    qbit = all_credentials['qbittorrent']
    if phase == 'verify':
        marker = existing(state, 'qbitwebui')
        instances = api.call('/api/instances/')
        expect(any(x['id'] == marker['instance_id'] and x['label'] == 'proof-qbit-persistent' for x in instances), 'qbitwebui durable connection lost')
    else:
        expect(api.call('/api/instances/') == [], 'qbitwebui fresh test requires empty instance state')
        payload = {'label': 'proof-qbit-create', 'url': 'http://qbittorrent:8080', 'qbt_username': qbit['username'], 'qbt_password': qbit['password'], 'skip_auth': False, 'agent_enabled': False}
        # This target exists only in the explicit proof-media-pipeline integration profile.
        instance = api.call('/api/instances/', 'POST', payload)
        marker = {'instance_id': instance['id']}
        api.call('/api/instances/' + str(instance['id']), 'PUT', {'label': 'proof-qbit-persistent'})
        temporary = api.call('/api/instances/', 'POST', {**payload, 'label': 'proof-qbit-delete'})
        api.call('/api/instances/' + str(temporary['id']), 'DELETE')
        instances = api.call('/api/instances/')
        expect(len(instances) == 1 and instances[0]['label'] == 'proof-qbit-persistent', 'qbitwebui instance CRUD failed')
    result = api.call('/api/instances/' + str(marker['instance_id']) + '/test', 'POST')
    expect(result.get('success') is True and bool(result.get('version')), 'qbitwebui stored proof qBittorrent credentials did not connect')
    stats = api.call('/api/instances/stats')
    match = next((x for x in stats if x['id'] == marker['instance_id']), None)
    expect(match is not None and match['online'] and match['total'] == 0, 'qbitwebui did not read empty proof downloader queue')
    if phase == 'exercise':
        record(state, 'qbitwebui', marker)
    return ['fresh preseeded login/session', 'anonymous access rejected', 'instance CRUD' if phase == 'exercise' else 'existing instance persistence before writes', 'stored encrypted proof credentials connect to real qBittorrent', 'live proof empty queue stats']
