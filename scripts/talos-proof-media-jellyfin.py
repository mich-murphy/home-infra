#!/usr/bin/env python3
"""Exact v12.4 offline-prepared video lifecycle/ACL/recovery gates. No activation.

Only parent-issued standalone Jellyfin receipt. Setup writes proof settings/users;
verify reads existing durable state BEFORE playback/configuration writes. New
receipts are exclusive; credentials.json and legacy fixtures/archives untouched.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import secrets
import sys
import time
import urllib.error
import urllib.parse
import uuid

s = importlib.import_module('talos-proof-media-safety')
API = importlib.import_module('talos-proof-media-http').API
DEVICE = 'proof-jellyfin-decoder'
PREPARED = 'jellyfin-browser-prepared.json'
BROWSER_FIXTURE = 'Proof Browser Fixture (2000).mp4'


def expect(ok, message):
    if not ok:
        raise RuntimeError(message)


def check():
    s.lease('jellyfin')
    s.exclusivity('jellyfin')


def api_for(ca, device=DEVICE):
    headers = {'Authorization': f'MediaBrowser Client="TalosProof", Device="LocalChrome", DeviceId="{device}", Version="1"'}
    return API('https://jellyfin.proof.invalid:18443', headers, service='jellyfin', ca=s.private_file(ca))


def login(api, credentials):
    check()
    auth = api.call('/Users/AuthenticateByName', 'POST', {'Username': credentials['username'], 'Pw': credentials['password']})
    api.headers['X-Emby-Token'] = auth['AccessToken']
    # Native12.4 prioritizes the MediaBrowser Authorization header. Preserve
    # client/device identity AND include the issued token there; an otherwise
    # tokenless Authorization header shadows X-Emby-Token and yields401.
    api.headers['Authorization'] += ', Token="' + auth['AccessToken'] + '"'
    expect(api.call('/Users/Me')['Id'] == auth['User']['Id'], 'authenticated user identity mismatch')
    return auth['User']['Id']


def owner(state, ca):
    api = api_for(ca)
    uid = login(api, json.loads(s.read_private(state / 'credentials.json'))['jellyfin'])
    return api, uid


def read_record(state, name):
    path = Path(name)
    expect(path.name == str(name) and path.suffix == '.json', 'record must be an exact private-state basename')
    return json.loads(s.read_private(state / path))


def deny(call):
    try:
        call()
    except urllib.error.HTTPError as exc:
        # An authenticated outsider can receive hidden404 or forbidden403, NOT401.
        expect(exc.code in (403, 404), 'outsider denial was not an authenticated ACL denial')
        return
    raise RuntimeError('restricted item unexpectedly readable')


def acl(api, ca, state, marker):
    policy = api.call('/Users/' + marker['outsider_id'])['Policy']
    expect(not policy['IsAdministrator'] and not policy['EnableAllFolders'] and not policy['EnabledFolders']
           and policy['EnableMediaPlayback'], 'persisted folder ACL differs; playback must not be globally disabled')
    other = api_for(ca, 'proof-jellyfin-outsider')
    uid = login(other, read_record(state, marker['outsider_credentials']))
    expect(uid == marker['outsider_id'], 'outsider identity changed')
    items = other.call('/Items?Recursive=true&IncludeItemTypes=Movie&EnableUserData=true')['Items']
    expect(not any(x['Id'] == marker['item_id'] for x in items), 'restricted item leaked into outsider library')
    deny(lambda: other.call('/Items/' + marker['item_id']))
    deny(lambda: other.call('/Items/' + marker['item_id'] + '/PlaybackInfo'))
    deny(lambda: other.call(marker['media_path'], raw=True))
    deny(lambda: other.call('/Items/' + marker['item_id'] + '/PlaybackInfo?userId=' + marker['owner_id']))


def stream(api, marker, fixture):
    expected = s.read_private(fixture, binary=True)
    digest = hashlib.sha256(expected).hexdigest()
    expect(digest == marker['fixture_sha256'], 'private fixture identity changed')
    actual = api.call(marker['media_path'], raw=True)
    expect(hashlib.sha256(actual).hexdigest() == digest, 'actual server video differs from fixture')
    chunk = api.call(marker['media_path'], raw=True, headers={'Range': 'bytes=44-107'})
    expect(api.last_status == 206 and chunk == expected[44:108], 'actual byte-range mismatch')


def setup(state, ca, fixture):
    check()
    expect(fixture.name == BROWSER_FIXTURE, 'immutable twelve-second browser fixture required')
    expect(not (state / PREPARED).exists(), 'existing setup marker must be verified, not rewritten')
    credential = json.loads(s.read_private(state / 'credentials.json'))['jellyfin']
    api = api_for(ca)
    public = api.call('/System/Info/Public')
    expect(public['Version'].split('.')[:2] == ['12', '4'], 'native API version differs from reviewed v12.4 source')
    if not public['StartupWizardCompleted']:
        check()
        api.call('/Startup/Configuration', 'POST', {'UICulture':'en-US','MetadataCountryCode':'US','PreferredMetadataLanguage':'en'})
        api.call('/Startup/User', 'POST', {'Name':credential['username'],'Password':credential['password']})
        api.call('/Startup/RemoteAccess', 'POST', {'EnableRemoteAccess':False,'EnableAutomaticPortMapping':False})
        api.call('/Startup/Complete', 'POST')
    uid = login(api, credential)
    config = api.call('/System/Configuration')
    before = {key:config[key] for key in ('MinResumeDurationSeconds','MinResumePct','MaxResumePct')}
    # v12.4 defaults300 seconds would mark this tiny clip completed, not resumable.
    # Change ONLY the proof duration floor, not the near-end/percentage safeguards.
    config['MinResumeDurationSeconds'] = 1
    s.write_private(state / ('jellyfin-resume-config-attempt-' + uuid.uuid4().hex + '.json'), json.dumps({'before':before,'duration_floor_seconds':1}))
    check()
    api.call('/System/Configuration', 'POST', config)
    libraries = api.call('/Library/VirtualFolders')
    expect(not libraries, 'fresh single-fixture video workflow refuses existing libraries')
    options = {'PathInfos':[{'Path':'/data/media'}], 'EnableRealtimeMonitor':False, 'MetadataSavers':[],
               'TypeOptions':[{'Type':'Movie','MetadataFetchers':[],'ImageFetchers':[]}]}
    check()
    api.call('/Library/VirtualFolders?name=Proof%20Browser&collectionType=movies&refreshLibrary=true', 'POST', {'LibraryOptions':options})
    items = []
    for _ in range(30):
        check()
        items = api.call('/Items?Recursive=true&IncludeItemTypes=Movie&Fields=Path,MediaSources,MediaStreams&EnableUserData=true')['Items']
        if items:
            break
        time.sleep(2)
    expect(len(items) == 1 and Path(items[0]['Path']).name == BROWSER_FIXTURE, 'expected ONLY new browser video in fresh proof library')
    item = items[0]
    expect(100000000 <= item['RunTimeTicks'] <= 150000000, 'unexpected native media duration')
    outsider_path = state / 'jellyfin-outsider.json'
    if not outsider_path.exists():
        s.write_private(outsider_path, json.dumps({'username':'proof-outsider','password':secrets.token_urlsafe(32)}))
    outsider = read_record(state, outsider_path.name)
    users = api.call('/Users')
    existing = [x for x in users if x['Name'] == outsider['username']]
    check()
    user = existing[0] if len(existing) == 1 else api.call('/Users/New', 'POST', {'Name':outsider['username'],'Password':outsider['password']})
    policy = user['Policy']
    policy.update(IsAdministrator=False, EnableAllFolders=False, EnabledFolders=[], EnableMediaPlayback=True)
    api.call('/Users/' + user['Id'] + '/Policy', 'POST', policy)
    libraries = api.call('/Library/VirtualFolders')
    expect(len(libraries) == 1, 'unexpected library count')
    marker = {'owner_id':uid,'outsider_id':user['Id'],'outsider_credentials':outsider_path.name,
              'library_id':libraries[0]['ItemId'],'item_id':item['Id'],'runtime_ticks':item['RunTimeTicks'],
              'media_path':'/Videos/' + item['Id'] + '/stream.mp4?static=true',
              'fixture_sha256':hashlib.sha256(s.read_private(fixture,binary=True)).hexdigest(),
              'resume_settings':{key:config[key] for key in before}}
    try:
        api.anonymous().call(marker['media_path'], raw=True)
    except urllib.error.HTTPError as exc:
        expect(exc.code in (401,403), 'anonymous media denial returned unexpected status')
    else:
        raise RuntimeError('anonymous video unexpectedly readable')
    stream(api, marker, fixture)
    acl(api, ca, state, marker)
    s.write_private(state / PREPARED, json.dumps(marker))
    return marker


def prepare_bridge(state, ca, fixture, resume_record=None):
    check()
    marker = verify(state, ca, fixture, resume_record) if resume_record else read_record(state, PREPARED)
    api, uid = owner(state, ca)
    expect(uid == marker['owner_id'], 'owner identity changed')
    info = api.call('/Items/' + marker['item_id'] + '/PlaybackInfo', 'POST',
                    {'UserId':uid,'StartTimeTicks':marker.get('resume_ticks',0),'EnableDirectPlay':True,'EnableDirectStream':True,'EnableTranscoding':False})
    expect(not info.get('ErrorCode') and info.get('PlaySessionId'), 'native playback-info session unavailable')
    sources = info['MediaSources']
    expect(len(sources) == 1 and sources[0].get('Id'), 'ambiguous native playback media source')
    name = 'jellyfin-decoder-session-' + uuid.uuid4().hex + '.json'
    session = {'marker':marker,'headers':api.headers,'media_source':sources[0]['Id'], 'play_session':info['PlaySessionId']}
    s.write_private(state / name, json.dumps(session))
    return {'service':'jellyfin','group':'jellyfin','state':str(state),'ca':str(ca),'session_file':name,'resume_seconds':marker.get('resume_ticks',0)/10000000 if resume_record else 0}


def session_headers(state, bridge):
    return read_record(state, bridge['session_file'])['headers']


def callback(bridge, event):
    expect(bridge['group'] == 'jellyfin', 'Jellyfin lifecycle must use standalone receipt')
    check()
    state = s.private_dir(Path(bridge['state']))
    session = read_record(state, bridge['session_file'])
    marker = session['marker']
    phase = event['phase']
    expect(phase in ('start','progress','stop') and event['state'] == ('stopped' if phase == 'stop' else 'playing') and 0 <= event['time'] < event['duration'] <= 15000, 'invalid real decoder event')
    path = state / (bridge['session_file'] + '.' + phase + '.json')
    if phase != 'start':
        s.read_private(state / (bridge['session_file'] + '.start.json'))
    if phase == 'stop':
        s.read_private(state / (bridge['session_file'] + '.progress.json'))
    payload = {'ItemId':marker['item_id'],'MediaSourceId':session['media_source'], 'PlaySessionId':session['play_session'],
               'PositionTicks':int(event['time'] * 10000),'CanSeek':True,'IsPaused':False,'IsMuted':True,'PlayMethod':'DirectPlay'}
    if phase == 'stop':
        payload = {k:v for k,v in payload.items() if k in ('ItemId','MediaSourceId','PlaySessionId','PositionTicks')}
    api = api_for(Path(bridge['ca']))
    api.headers = session['headers']
    endpoint = {'start':'','progress':'/Progress','stop':'/Stopped'}[phase]
    api.call('/Sessions/Playing' + endpoint, 'POST', payload)
    expect(api.last_status == 204, 'native lifecycle did not accept event')
    sessions = api.call('/Sessions?' + urllib.parse.urlencode({'deviceId':DEVICE}))
    own = [x for x in sessions if x.get('DeviceId') == DEVICE and x.get('UserId') == marker['owner_id']]
    active = any((x.get('NowPlayingItem') or {}).get('Id') == marker['item_id']
                 and not (x.get('PlayState') or {}).get('IsPaused', True) for x in own)
    expect((not active) if phase == 'stop' else active, 'native session active/stopped state differs from decoder')
    # Multiple progress callbacks are append-only, never truncate prior observations.
    if phase == 'progress' and path.exists():
        path = state / (bridge['session_file'] + '.progress-' + uuid.uuid4().hex + '.json')
    s.write_private(path, json.dumps({'event':event,'position_ticks':payload['PositionTicks']}))
    return {'stopped':True} if phase == 'stop' else {'active':active}


def verify(state, ca, fixture, record):
    check()
    marker = read_record(state, record)
    api, uid = owner(state, ca)
    expect(uid == marker['owner_id'], 'durable owner identity changed')
    settings = api.call('/System/Configuration')
    expect(all(settings[k] == v for k,v in marker['resume_settings'].items()), 'durable resume configuration changed')
    libraries = api.call('/Library/VirtualFolders')
    expect(any(x['ItemId'] == marker['library_id'] for x in libraries), 'durable library identity lost')
    item = api.call('/Items/' + marker['item_id'])
    expect(item['UserData']['Played'] is False and item['UserData']['PlaybackPositionTicks'] == marker['resume_ticks'], 'actual persisted resume position/played status lost')
    resumed = api.call('/UserItems/Resume?EnableUserData=true')['Items']
    expect(any(x['Id'] == marker['item_id'] and x['UserData']['PlaybackPositionTicks'] == marker['resume_ticks'] for x in resumed), 'resume list lacks exact persisted item/position')
    stream(api, marker, fixture)
    acl(api, ca, state, marker)
    return marker


def finish(state, ca, fixture, bridge, decoder):
    expect(decoder['timeline_activity_observed'] and decoder['timeline_stopped'], 'real concurrent lifecycle absent')
    session = read_record(state, bridge['session_file'])
    stop = read_record(state, bridge['session_file'] + '.stop.json')
    marker = dict(session['marker'], resume_ticks=stop['position_ticks'], decoder=decoder)
    ticks = marker['resume_ticks']
    expect(0 < ticks < marker['runtime_ticks'] - 10000000 and ticks < marker['runtime_ticks'] * 0.9,
           'decoder stopped too near end for a genuine resumable fixture')
    name = 'jellyfin-browser-functional-' + uuid.uuid4().hex + '.json'
    # Preserve the candidate even if readback/ACL fails. Only verification verdict
    # can accept it; a filename or exit-zero decoder does not imply lifecycle PASS.
    s.write_private(state / name, json.dumps(marker))
    verify(state, ca, fixture, name)
    return name


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['setup','verify'])
    p.add_argument('--state', required=True, type=Path)
    p.add_argument('--ca', required=True, type=Path)
    p.add_argument('--fixture', required=True, type=Path)
    p.add_argument('--record', help='exact immutable completed browser functional JSON basename for verify')
    args = p.parse_args()
    state = s.private_dir(args.state)
    if args.action == 'setup':
        setup(state, args.ca, args.fixture)
        print(json.dumps({'result':'PREPARED_ONLY','next_gate':'actual browser --jellyfin-lifecycle'}))
    else:
        expect(args.record is not None, 'verify requires explicit existing browser functional record')
        verify(state, args.ca, args.fixture, args.record)
        print(json.dumps({'result':'PASS','scope':'existing resume/identity/ACL/video bytes checked before playback/configuration writes'}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'result':'FAIL','error_type':type(exc).__name__,'http_status':getattr(exc,'code',None),
                          'check':str(exc) if isinstance(exc,RuntimeError) else None}))
        raise SystemExit(1)
