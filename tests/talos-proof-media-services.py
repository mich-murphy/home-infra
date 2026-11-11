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
import xml.etree.ElementTree as ET

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


def qbittorrent(api, credential, fixture, state, phase):
    reject_anonymous(api, '/api/v2/app/preferences')
    result = api.call('/api/v2/auth/login', 'POST', form={'username': credential['username'], 'password': credential['password']}, raw=True)
    expect((api.last_status == 204 and result == b'') or (api.last_status == 200 and result == b'Ok.'), 'fresh qBittorrent credential rejected')
    torrents = api.call('/api/v2/torrents/info')
    transfer_path = state / 'qbittorrent-transfer.json'
    if phase == 'verify' and transfer_path.exists():
        transfer = json.loads(safety.read_private(transfer_path))
        expect(len(torrents) == 1 and torrents[0]['hash'] == transfer['infohash'], 'unexpected torrent state during durable settings verification')
    else:
        expect(torrents == [], 'settings-only proof requires empty torrent queue')
    prefs = api.call('/api/v2/app/preferences')
    expect(not prefs['dht'] and not prefs['pex'] and not prefs['lsd'], 'discovery must remain disabled')
    if phase == 'verify':
        marker = existing(state, 'qbittorrent')
        expect(prefs['max_active_downloads'] == marker['max_active_downloads'], 'qBittorrent durable preference lost across restart/restore')
        return ['fresh login', 'anonymous preferences rejected', 'discovery disabled', 'existing durable preference verified before writes; no transfer claim']
    changed = 1 if prefs['max_active_downloads'] != 1 else 2
    api.call('/api/v2/app/setPreferences', 'POST', form={'json': json.dumps({'max_active_downloads': changed})}, raw=True)
    expect(api.call('/api/v2/app/preferences')['max_active_downloads'] == changed, 'qBittorrent preference write/read failed')
    record(state, 'qbittorrent', {'max_active_downloads': changed})
    return ['fresh login', 'anonymous preferences rejected', 'empty torrent queue; no transfer claim', 'discovery disabled', 'nondefault durable preference write/read retained']


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


def plex_xml(api, path, method='GET'):
    return ET.fromstring(api.call(path, method, raw=True))


def plex(api, credential, fixture, state, phase):
    expect(fixture is not None and fixture.suffix == '.mp4', 'Plex requires locally generated synthetic MP4')
    reject_anonymous(api, '/library/sections')
    # This key authenticates ONLY the proof-local adapter, not any Plex cloud account.
    api.headers.update({'X-Plex-Token': credential['api_key'], 'X-Plex-Client-Identifier': 'talos-proof-player',
                        'X-Plex-Product': 'TalosProof', 'X-Plex-Version': '1', 'X-Plex-Device': 'Proof'})
    identity = plex_xml(api, '/identity')
    expect(identity.get('claimed') in ('0', None), 'proof Plex must remain unclaimed')
    machine = identity.get('machineIdentifier')
    expect(bool(machine), 'fresh Plex machine identity absent')
    sections = plex_xml(api, '/library/sections')
    if phase == 'verify':
        marker = existing(state, 'plex')
        expect(machine == marker['machine_id'], 'Plex machine identity lost in restart/restore')
        library = next((x for x in sections.findall('Directory') if x.get('key') == marker['library_id']), None)
        expect(library is not None and library.get('title') == 'Proof', 'Plex durable library lost')
        item = marker['item_id']
        metadata = plex_xml(api, '/library/metadata/' + item)
        video = metadata.find('Video')
        expect(video is not None and int(video.get('viewCount', '0')) >= 1, 'Plex durable watched state lost')
    else:
        library = next((x for x in sections.findall('Directory') if x.get('title') == 'Proof'), None)
        if library is None:
            query = urllib.parse.urlencode({'name': 'Proof', 'type': 'movie', 'agent': 'com.plexapp.agents.none',
                     'scanner': 'Plex Movie Scanner', 'language': 'en-US', 'location': '/data/media'})
            plex_xml(api, '/library/sections?' + query, 'POST')
            library = next((x for x in plex_xml(api, '/library/sections').findall('Directory') if x.get('title') == 'Proof'), None)
        expect(library is not None, 'Plex personal-media library creation failed')
        library_id = library.get('key')
        api.call('/library/sections/' + library_id + '/refresh?force=1', raw=True)
        videos = []
        for _ in range(30):
            videos = plex_xml(api, '/library/sections/' + library_id + '/all').findall('Video')
            if videos:
                break
            time.sleep(2)
        expect(len(videos) == 1, 'Plex expected exactly one synthetic movie')
        item = videos[0].get('ratingKey')
        metadata = plex_xml(api, '/library/metadata/' + item)
        video = metadata.find('Video')
        api.call('/:/unscrobble?' + urllib.parse.urlencode({'key': item, 'identifier': 'com.plexapp.plugins.library'}), raw=True)
        expect(int(plex_xml(api, '/library/metadata/' + item).find('Video').get('viewCount', '0')) == 0, 'Plex unplayed write/read failed')
        api.call('/:/scrobble?' + urllib.parse.urlencode({'key': item, 'identifier': 'com.plexapp.plugins.library'}), raw=True)
        expect(int(plex_xml(api, '/library/metadata/' + item).find('Video').get('viewCount', '0')) >= 1, 'Plex watched write/read failed')
        marker = {'machine_id': machine, 'library_id': library_id, 'item_id': item}
    part = video.find('./Media/Part')
    expect(part is not None and bool(part.get('key')), 'Plex scanned fixture has no media part')
    marker['stream_sha256'] = audio_checksum(api, part.get('key') + '?download=1', fixture)
    if phase == 'exercise':
        record(state, 'plex', marker)
    return ['fresh adapter key required; no Plex cloud claim', 'real Plex personal-media library scan',
            'exact synthetic video SHA256 and byte-range seek', 'real watched-state write/read' if phase == 'exercise' else 'existing library/machine/watched state before writes']
