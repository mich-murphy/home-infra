#!/usr/bin/env python3
"""Offline-prepared Radarr/qBit contracts, NOT an authorized live runner.

Provider metadata is synthetic Skyhook, not provider parity. ManualImport is an
explicit alternative result, never automatic Completed Download Handling proof.
No database writes, synthetic completion rows, or destination seeding exist here.
Owner must wire profiles, receipt/exclusivity and all-container charging first.
"""
import hashlib
import importlib
import json
from pathlib import PurePosixPath
import stat
import time
import urllib.parse

transfer = importlib.import_module('talos-proof-media-transfer')
safety = importlib.import_module('talos-proof-media-safety')
TMDB = 900000001


def require_owner_wiring():
    # Deliberately no env flag/token/private receipt shortcut. Current pipeline
    # rejects the fixture and lacks Skyhook; existing safety must not be bypassed.
    raise RuntimeError('BLOCKED: owner must wire Skyhook512 + qBit192 + fixture128 + reserve192; existing pipeline grant is insufficient')


def expect(condition, message):
    if not condition:
        raise RuntimeError(message)


def data_path(path):
    p = PurePosixPath(path)
    expect(p.is_absolute() and str(p).startswith('/data/') and '..' not in p.parts,
           'path must remain inside shared /data')
    return str(p)


def observe_file(path):
    """Local filesystem oracle; owner may execute equivalent inside bounded pod.

    Never use host observations as proof of a cluster filesystem. No symlink
    components, open/read races, or content-only pseudo-hardlinks accepted.
    """
    from pathlib import Path
    p = Path(path)
    expect(p.is_absolute() and '..' not in p.parts, 'absolute canonical path required')
    for part in (p, *p.parents):
        expect(not part.is_symlink(), 'symlink forbidden')
    before = p.stat()
    expect(stat.S_ISREG(before.st_mode), 'regular file required')
    with p.open('rb') as stream:
        import os
        opened = os.fstat(stream.fileno())
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
    expect(identity(before) == identity(opened) == identity(after) == identity(p.stat()), 'file changed during observation')
    return dict(device=after.st_dev, inode=after.st_ino, links=after.st_nlink,
                size=after.st_size, sha256=digest, regular=True)


def hardlink_oracle(source, imported, expected):
    for value in (source, imported):
        expect(value.get('regular') is True, 'regular files required')
        expect(value['size'] == expected['size'] and value['sha256'] == expected['sha256'], 'imported bytes differ')
        expect(value['links'] >= 2, 'hardlink count below two')
    expect((source['device'], source['inode']) == (imported['device'], imported['inode']), 'not a same-filesystem hardlink')
    return {'same_device_inode': True, 'sha256': expected['sha256'], 'size': expected['size']}


def configure_client(radarr, credential, category):
    """Use native schema, preserve defaults, test before creating actual client."""
    require_owner_wiring()
    expect(category.startswith('proof-'), 'explicit proof category required')
    existing = radarr.call('/api/v3/downloadclient')
    expect(not existing, 'refuse to replace existing clients')
    schemas = [x for x in radarr.call('/api/v3/downloadclient/schema') if x.get('implementation') == 'QBittorrent']
    expect(len(schemas) == 1, 'native QBittorrent schema missing/ambiguous')
    payload = json.loads(json.dumps(schemas[0]))
    payload.pop('id', None)
    fields = {x['name']: x for x in payload['fields']}
    values = dict(host='qbittorrent', port=8080, useSsl=False,
                  username=credential['username'], password=credential['password'], movieCategory=category)
    expect(set(values) <= fields.keys(), 'pinned native client schema differs')
    for key, value in values.items():
        fields[key]['value'] = value
    payload.update(name='Proof qBit import', enable=True, priority=1)
    radarr.call('/api/v3/downloadclient/test', 'POST', payload)
    created = radarr.call('/api/v3/downloadclient', 'POST', payload)
    expect(created.get('id', 0) > 0, 'client creation has no native ID')
    return created['id']


def configure_import(radarr, proxy_key):
    """Native settings read/update; no fixture quality/size overrides hidden here."""
    require_owner_wiring()
    expect(bool(proxy_key), 'existing private Skyhook proxy key required')
    updates = [('/api/v3/config/host', dict(proxyEnabled=True, proxyType='http',
        proxyHostname='127.0.0.1', proxyPort=18081, proxyUsername='proof',
        proxyPassword=proxy_key, proxyBypassFilter='*.svc', proxyBypassLocalAddresses=True)),
        ('/api/v3/config/downloadclient', {'enableCompletedDownloadHandling': True}),
        ('/api/v3/config/mediamanagement', {'copyUsingHardlinks': True})]
    for path, changes in updates:
        current = radarr.call(path)
        expect(set(changes) <= current.keys(), 'pinned native settings schema differs')
        current.update(changes)
        radarr.call(path, 'PUT', current)
        actual = radarr.call(path)
        expect(all(actual[k] == v for k, v in changes.items() if k != 'proxyPassword'), 'settings readback differs')


def wait_command(radarr, command_id, *, attempts=30, interval=2):
    """Command completion is necessary, never sufficient for import acceptance."""
    require_owner_wiring()
    expect(0 < attempts <= 60 and 0 <= interval <= 5, 'bounded application polling required')
    for attempt in range(attempts):
        value = radarr.call('/api/v3/command/' + str(command_id))
        expect(value['status'] not in ('failed', 'aborted', 'cancelled'), 'native import command failed')
        if value['status'] == 'completed':
            return
        if attempt + 1 < attempts:
            time.sleep(interval)
    raise RuntimeError('native import command timed out; preserve attempt, no manual fallback automatically')


def create_movie(radarr, profile_id, skyhook_evidence):
    require_owner_wiring()
    expect(not radarr.call('/api/v3/movie'), 'fresh movie state required')
    expect(any(x['id'] == profile_id for x in radarr.call('/api/v3/qualityprofile')), 'unknown real quality profile')
    root = '/data/media/movies'
    if not any(x['path'] == root for x in radarr.call('/api/v3/rootfolder')):
        radarr.call('/api/v3/rootfolder', 'POST', {'path': root})
    before = skyhook_evidence()['requests'].get('/v1/movie/900000001', 0)
    movie = radarr.call('/api/v3/movie', 'POST', dict(tmdbId=TMDB, title='Proof Fixture',
        qualityProfileId=profile_id, rootFolderPath=root, monitored=True,
        minimumAvailability='released', addOptions={'searchForMovie': False}))
    actual = radarr.call('/api/v3/movie/' + str(movie['id']))
    expect(actual['id'] > 0 and actual['tmdbId'] == TMDB and actual['title'] == 'Proof Fixture', 'native movie identity differs')
    expect(not actual.get('hasFile'), 'final file must not be preseeded')
    expect(skyhook_evidence()['requests'].get('/v1/movie/900000001', 0) > before, 'real metadata request not observed')
    return actual


def submit_torrent(qbit, artifact, marker, category, destination_absent, *, state=None):
    require_owner_wiring()
    expect(category.startswith('proof-'), 'explicit proof category required')
    destination = data_path(marker['destination'])
    expect(destination.startswith('/data/torrents/'), 'torrent destination must be under torrents')
    expect(destination_absent(destination), 'destination already exists; preserve evidence')
    expect(not qbit.call('/api/v2/torrents/info'), 'fresh downloader queue required')
    prefs = qbit.call('/api/v2/app/preferences')
    expect(all(prefs[k] is False for k in ('dht', 'pex', 'lsd')), 'discovery must remain disabled')
    # Exclusive immutable attempt precedes submission; never overwrite prior runs.
    import uuid
    from pathlib import Path
    expect(state is not None, 'private attempt state required before submission')
    state = safety.private_dir(state)
    attempt = Path(state) / ('radarr-transfer-attempt-' + uuid.uuid4().hex + '.json')
    safety.write_private(attempt, json.dumps(dict(marker, category=category, provider='synthetic-Skyhook')))
    body, headers = transfer.multipart({'savepath': destination, 'category': category, 'autoTMM': 'false'},
                                        'torrents', 'proof.torrent', artifact)
    response = qbit.call('/api/v2/torrents/add', 'POST', payload=body, headers=headers, raw=True)
    expect((qbit.last_status == 204 and response == b'') or (qbit.last_status == 200 and response == b'Ok.'), 'native submission rejected')
    return attempt


def verify_completion(qbit, marker, before, after, observe):
    require_owner_wiring()
    rows = qbit.call('/api/v2/torrents/info?hashes=' + urllib.parse.quote(marker['infohash'], safe=''))
    expect(len(rows) == 1, 'actual torrent missing/ambiguous')
    row = rows[0]
    expect(row['progress'] == 1 and row['amount_left'] == 0 and row['completed'] == marker['size']
           and row['state'] not in ('error', 'missingFiles', 'unknown'), 'actual transfer incomplete')
    path = data_path(row['content_path'])
    expect(PurePosixPath(path).parent == PurePosixPath(marker['destination']), 'torrent output escaped unique destination')
    actual = observe(path)
    expect(actual['sha256'] == marker['sha256'] and actual['size'] == marker['size'], 'download checksum differs')
    expect(before['sha256'] == marker['sha256'] and before['infohash'] == marker['infohash'], 'fixture does not match immutable transfer marker')
    delta = transfer.counters(before, after, 'qbittorrent', marker['size'])
    return path, delta


def process_completed(radarr, download_path, infohash):
    """Supported explicit scan trigger; NOT evidence of default scheduler timing."""
    require_owner_wiring()
    command = radarr.call('/api/v3/command', 'POST', {'name': 'DownloadedMoviesScan',
        'path': data_path(download_path), 'downloadClientId': infohash, 'importMode': 'Auto'})
    expect(command.get('id', 0) > 0, 'scan command has no native ID')
    return command['id']


def manual_fallback(radarr, movie_id, folder, infohash, selections):
    """Native manual candidate/command contract, explicit override result only.

    Selections must be reviewed native candidate resources, including quality and
    languages. No invented quality defaults or automatic fallback on failure.
    """
    require_owner_wiring()
    candidates = radarr.call('/api/v3/manualimport?' + urllib.parse.urlencode(dict(
        folder=data_path(folder), downloadId=infohash, movieId=movie_id, filterExistingFiles='true')))
    expect(bool(selections), 'explicit reviewed native manual selections required')
    for selected in selections:
        expect(any(x['path'] == selected['path'] and x['quality'] == selected['quality']
                   and x.get('languages') == selected.get('languages') for x in candidates), 'selection differs from native candidate')
        expect(selected['movieId'] == movie_id and selected['downloadId'] == infohash, 'manual linkage differs')
        expect(PurePosixPath(data_path(folder)) in PurePosixPath(data_path(selected['path'])).parents, 'manual selection escaped folder')
    result = radarr.call('/api/v3/command', 'POST', {'name': 'ManualImport', 'files': selections, 'importMode': 'Copy'})
    expect(result.get('id', 0) > 0, 'manual command has no native ID')
    return {'mode': 'manual-import-with-reviewed-selections', 'command_id': result['id'], 'production_automatic_parity': False}


def verify_import(radarr, movie_id, infohash, source, expected, observe, *, mode):
    """Read-only postcondition; no file creation, scan, client or settings writes."""
    require_owner_wiring()
    expect(mode in ('completed-download-explicit-scan', 'default-automatic', 'manual-import-with-reviewed-selections'), 'explicit import mode required')
    source = data_path(source)
    expect(source.startswith('/data/torrents/'), 'source must remain in torrent tree')
    movie = radarr.call('/api/v3/movie/' + str(movie_id))
    expect(movie['id'] == movie_id and movie['tmdbId'] == TMDB and movie['hasFile'], 'movie/file linkage absent')
    file = radarr.call('/api/v3/moviefile/' + str(movie['movieFile']['id']))
    expect(file['movieId'] == movie_id and file['id'] == movie['movieFile']['id'] and file['size'] == expected['size'], 'native file record differs')
    path = data_path(file['path'])
    expect(path.startswith('/data/media/movies/') and path != source, 'imported file outside final movie tree')
    expect(bool(file.get('mediaInfo')), 'native imported media information missing')
    history = radarr.call('/api/v3/history?' + urllib.parse.urlencode(dict(movieId=movie_id, page=1, pageSize=100, sortKey='date', sortDirection='descending')))
    matches = [x for x in history['records'] if x.get('eventType') == 'downloadFolderImported'
               and x.get('movieId') == movie_id and x.get('downloadId', '').lower() == infohash.lower()
               and x.get('data', {}).get('importedPath') == path]
    expect(bool(matches), 'actual import history/download linkage absent')
    proof = hardlink_oracle(observe(source), observe(path), expected)
    return dict(proof, movie_id=movie_id, file_id=file['id'], history_ids=[x['id'] for x in matches],
                path=path, mode=mode, provider='synthetic-Skyhook', playback_proven=False,
                production_automatic_parity=False)


if __name__ == '__main__':
    # No operational CLI until owner transfers and wires safety. Even --help
    # cannot accidentally inspect a cluster or private state.
    raise SystemExit('OFFLINE PREPARATION ONLY; live orchestration blocked pending owner wiring')
