#!/usr/bin/env python3
"""Explicit, separately leased dependency workflows. No all-service startup.

Real helper/API failures are hard gates. Unclaimed Plex adapter authentication
is not Plex cloud/account authentication; never fake cloud responses to pass.
"""
import argparse
import base64
import hashlib
import importlib
import json
from pathlib import Path
import secrets
import sys
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET

s = importlib.import_module('talos-proof-media-safety')
API = importlib.import_module('talos-proof-media-http').API
HELPERS = ('kometa', 'jellyplex-watched')


def expect(ok, message):
    if not ok:
        raise RuntimeError(message)


def rejected(call):
    try:
        call()
    except urllib.error.HTTPError as exc:
        expect(exc.code in (401, 403), 'permission denial returned unexpected HTTP status')
        return
    raise RuntimeError('restricted operation unexpectedly allowed')


def api_for(name, ca, credentials):
    api = API('https://' + name + '.proof.invalid:18443', service=name, ca=ca)
    if name == 'plex':
        api.headers.update({'X-Plex-Token': credentials[name]['api_key'], 'X-Plex-Client-Identifier': 'talos-proof-workflow',
                            'X-Plex-Product': 'TalosProof', 'X-Plex-Version': '1', 'X-Plex-Device': 'Proof'})
    elif name == 'radarr':
        api.headers['X-Api-Key'] = credentials[name]['api_key']
    return api


def xml(api, path):
    return ET.fromstring(api.call(path, raw=True))


def run_job(group, name, kube, state, env=None, args=None):
    s.guard(group)
    s.require_helpers_deleted(group)
    ns = 'proof-' + name
    cron = json.loads(kube('-n', ns, 'get', 'cronjob', name, '-o', 'json'))
    spec = json.loads(json.dumps(cron['spec']['jobTemplate']['spec']))
    container = spec['template']['spec']['containers'][0]
    if args is not None:
        container['args'] = args
    for key, value in (env or {}).items():
        container['env'] = [v for v in container.get('env', []) if v['name'] != key] + [{'name': key, 'value': value}]
    job_name = name + '-actual-' + secrets.token_hex(4)
    job = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': job_name, 'namespace': ns,
           'labels': {'app.kubernetes.io/part-of': 'talos-proof'}}, 'spec': spec}
    kube('create', '-f', '-', data=json.dumps(job).encode(), capacity=True)
    try:
        kube('-n', ns, 'wait', '--for=condition=complete', 'job/' + job_name, '--timeout=210s')
    finally:
        try:
            logs = kube('-n', ns, 'logs', 'job/' + job_name)
            s.write_private(state / (job_name + '.log'), logs)
            pods = json.loads(kube('-n', ns, 'get', 'pods', '-l', 'job-name=' + job_name, '-o', 'json'))
            observe = importlib.import_module('talos-proof-media-observe')
            s.write_private(state / (job_name + '-pods.json'), json.dumps([observe.summarize(p) for p in pods['items']]))
        finally:
            kube('-n', ns, 'delete', 'job', job_name, '--wait=true', '--timeout=60s')
            kube('-n', ns, 'wait', '--for=delete', 'pod', '-l', 'job-name=' + job_name, '--timeout=180s')
    return hashlib.sha256(logs).hexdigest()


def kometa(group, kube, state, plex):
    marker = json.loads(s.read_private(state / 'plex-functional.json'))
    prefix = '/library/sections/' + marker['library_id']
    def collection():
        values = xml(plex, prefix + '/collections').findall('Directory')
        return [x for x in values if x.get('title') == 'Proof Synthetic Collection']
    expect(not collection(), 'first Kometa mutation requires proof collection absent; preserve prior evidence')
    results, first = [], None
    for run in (1, 2):
        results.append(run_job(group, 'kometa', kube, state,
            args=['--run', '--read-only-config', '--collections-only', '--run-collections', 'Proof Synthetic Collection', '--config', '/config/config.yml']))
        values = collection()
        expect(len(values) == 1, 'actual Kometa run did not create exactly one proof collection')
        key = values[0].get('ratingKey')
        expect(bool(key), 'Plex collection has no durable ID')
        children = xml(plex, '/library/collections/' + key + '/children').findall('Video')
        identities = sorted(x.get('ratingKey') for x in children)
        expect(identities == [marker['item_id']], 'Kometa collection is empty or contains unexpected media')
        snapshot = {'collection_id': key, 'members': identities}
        if run == 1:
            first = snapshot
        else:
            expect(snapshot == first, 'second Kometa run drifted collection ID or membership')
    s.write_private(state / 'kometa-functional.json', json.dumps(first))
    return {'checks': ['real Plex collection with exactly synthetic item', 'second actual Kometa run stable ID+membership'], 'log_sha256': results}


def jellyfin_login(api, credential):
    auth = api.call('/Users/AuthenticateByName', 'POST', {'Username': credential['username'], 'Pw': credential['password']},
                    headers={'Authorization': 'MediaBrowser Client="TalosProof", Device="Loopback", DeviceId="proof-workflows", Version="1"'})
    api.headers['X-Emby-Token'] = auth['AccessToken']
    return auth


def jellyplex(group, kube, state, plex, jellyfin, credential):
    marker = json.loads(s.read_private(state / 'plex-functional.json'))
    if not jellyfin.call('/System/Info/Public')['StartupWizardCompleted']:
        jellyfin.call('/Startup/Configuration', 'POST', {'UICulture':'en-US','MetadataCountryCode':'US','PreferredMetadataLanguage':'en'})
        jellyfin.call('/Startup/User', 'POST', {'Name':credential['username'],'Password':credential['password']})
        jellyfin.call('/Startup/RemoteAccess', 'POST', {'EnableRemoteAccess':False,'EnableAutomaticPortMapping':False})
        jellyfin.call('/Startup/Complete', 'POST')
    auth = jellyfin_login(jellyfin, credential)
    libraries = jellyfin.call('/Library/VirtualFolders')
    if not any(x['Name'] == 'Proof' for x in libraries):
        jellyfin.call('/Library/VirtualFolders?name=Proof&collectionType=movies&refreshLibrary=true', 'POST',
            {'LibraryOptions': {'PathInfos':[{'Path':'/data/media'}], 'EnableRealtimeMonitor':False, 'EnableInternetProviders':False, 'MetadataSavers':[]}})
    jellyfin.call('/Library/Refresh', 'POST')
    uid = auth['User']['Id']
    videos = []
    for _ in range(30):
        videos = jellyfin.call('/Users/' + uid + '/Items?Recursive=true&IncludeItemTypes=Movie')['Items']
        if videos:
            break
        time.sleep(2)
    expect(len(videos) == 1 and videos[0]['Name'] == 'Proof Fixture', 'mapped proof movie library must contain one matching synthetic video')
    item = videos[0]['Id']
    # Create a real divergence using each real server API; never edit either database.
    plex.call('/:/scrobble?' + urllib.parse.urlencode({'key': marker['item_id'], 'identifier': 'com.plexapp.plugins.library'}), raw=True)
    jellyfin.call('/Users/' + uid + '/PlayedItems/' + item, 'DELETE')
    expect(jellyfin.call('/Users/' + uid + '/Items/' + item)['UserData']['Played'] is False, 'failed to establish target divergence')
    expect(int(xml(plex, '/library/metadata/' + marker['item_id']).find('Video').get('viewCount', '0')) > 0, 'source divergence missing')
    # Pass fresh adapter key and real proof-issued Jellyfin token ONLY in Secret payload.
    secret = json.loads(s.read_private(state / 'jellyplex-watched-secret.json'))
    secret['data']['plex-token'] = base64.b64encode(plex.headers['X-Plex-Token'].encode()).decode()
    secret['data']['jellyfin-token'] = base64.b64encode(auth['AccessToken'].encode()).decode()
    kube('apply', '-f', '-', data=json.dumps(secret).encode())
    result = run_job(group, 'jellyplex-watched', kube, state,
        env={'DRYRUN': 'False', 'RUN_ONLY_ONCE': 'True', 'SYNC_FROM_PLEX_TO_JELLYFIN': 'True',
             'SYNC_FROM_JELLYFIN_TO_PLEX': 'False', 'USER_MAPPING': '{"proof":"proof"}'})
    expect(jellyfin.call('/Users/' + uid + '/Items/' + item)['UserData']['Played'] is True, 'real helper did not apply mapped watched state')
    expect(int(xml(plex, '/library/metadata/' + marker['item_id']).find('Video').get('viewCount', '0')) > 0, 'one-way helper unexpectedly cleared source state')
    # Second actual helper run must leave real target watched state stable.
    second = run_job(group, 'jellyplex-watched', kube, state,
        env={'DRYRUN': 'False', 'SYNC_FROM_PLEX_TO_JELLYFIN': 'True', 'SYNC_FROM_JELLYFIN_TO_PLEX': 'False'})
    expect(jellyfin.call('/Users/' + uid + '/Items/' + item)['UserData']['Played'] is True, 'second helper run drifted watched state')
    s.write_private(state / 'jellyplex-functional.json', json.dumps({'user_id': uid, 'item_id': item, 'plex_item': marker['item_id']}))
    return {'checks': ['real source/target divergence', 'actual non-dry-run mapped watched mutation', 'second actual run stable target'], 'log_sha256': [result, second]}


def tautulli(api, plex, credential, state, fixture):
    marker = json.loads(s.read_private(state / 'plex-functional.json'))
    def call(command, **params):
        response = api.call('/api/v2', 'POST', form={'apikey': credential['api_key'], 'cmd': command, **params})['response']
        expect(response['result'] == 'success', 'Tautulli API command failed')
        return response['data']
    rejected(lambda: api.anonymous().call('/api/v2?cmd=get_activity'))
    settings = call('get_settings')
    expect(str(settings['Monitoring']['logging_ignore_interval']) == '0', 'short synthetic playback requires explicit zero ignore interval')
    history = call('get_history', rating_key=marker['item_id'], include_activity=0)['data']
    expect(not history, 'first playback-history exercise requires no previous synthetic history')
    session = 'proof-session-' + secrets.token_hex(5)
    query = {'path': '/library/metadata/' + marker['item_id'], 'mediaIndex': 0, 'partIndex': 0, 'protocol': 'http',
             'directPlay': 1, 'directStream': 1, 'session': session, 'X-Plex-Client-Identifier': 'talos-proof-workflow'}
    actual = plex.call('/video/:/transcode/universal/start?' + urllib.parse.urlencode(query), raw=True)
    expect(hashlib.sha256(actual).digest() == hashlib.sha256(s.read_private(fixture, binary=True)).digest(), 'actual Plex session stream differs from fixture')
    seen = False
    for offset in (0, 500, 1000, 1500):
        plex.call('/:/timeline?' + urllib.parse.urlencode({'ratingKey': marker['item_id'], 'key': '/library/metadata/' + marker['item_id'],
                  'state': 'playing', 'time': offset, 'duration': 2128, 'session': session}), raw=True)
        activity = call('get_activity')
        seen |= any(str(x.get('rating_key')) == marker['item_id'] for x in activity.get('sessions', []))
        time.sleep(1)
    expect(seen, 'Tautulli never observed genuine Plex playback activity')
    plex.call('/:/timeline?' + urllib.parse.urlencode({'ratingKey': marker['item_id'], 'key': '/library/metadata/' + marker['item_id'],
              'state': 'stopped', 'time': 2128, 'duration': 2128, 'session': session}), raw=True)
    rows = []
    for _ in range(30):
        rows = call('get_history', rating_key=marker['item_id'], include_activity=0)['data']
        if rows:
            break
        time.sleep(2)
    expect(len(rows) == 1 and str(rows[0]['rating_key']) == marker['item_id'] and int(rows[0]['duration']) > 0,
           'no unique durable Tautulli history from actual playback')
    s.write_private(state / 'tautulli-functional.json', json.dumps({'history_id': rows[0]['row_id'], 'rating_key': marker['item_id']}))
    return {'checks': ['fresh API authentication', 'actual Plex bytes SHA256', 'real observed playing activity', 'durable nonempty playback history']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'start', 'stop', 'kometa', 'jellyplex', 'tautulli'])
    p.add_argument('--group', required=True, choices=s.DEPENDENCY_BATCHES)
    p.add_argument('--service', choices=s.SERVICES)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--ca', type=Path)
    p.add_argument('--fixture', type=Path)
    args = p.parse_args()
    state = s.private_dir(args.state)
    credentials = json.loads(s.read_private(state / 'credentials.json'))
    s.lease(args.group)
    s.exclusivity(args.group)
    members = s.DEPENDENCY_BATCHES[args.group]
    def kube(*command, **kwargs):
        return s.kube(args.group, *command, **kwargs)
    if args.action == 'stop':
        for name in members:
            if name not in HELPERS:
                kube('-n', 'proof-' + name, 'scale', 'deployment', name, '--replicas=0')
        for name in members:
            kube('-n', 'proof-' + name, 'wait', '--for=delete', 'pod', '--all', '--timeout=180s')
        print(json.dumps({'group': args.group, 'result': 'STOPPED_ALL_SELECTED_PODS_DELETED'}))
        return
    s.guard(args.group)
    s.require_helpers_deleted(args.group)
    if args.action == 'prepare':
        expect(args.service in members and args.service in HELPERS, 'prepare requires exact selected suspended helper')
        secret = s.read_private(state / (args.service + '-secret.json')).encode()
        tls = None
        if args.service == 'kometa':
            tls = json.loads(s.read_private(state / 'metadata-contract-secret.json'))
        kube('apply', '-k', str(s.ROOT / 'kubernetes/apps/media' / args.service))
        kube('apply', '-f', '-', data=secret)
        if tls:
            kube('apply', '-f', '-', data=json.dumps(tls).encode())
        print(json.dumps({'service': args.service, 'result': 'PREPARED_SUSPENDED_ONLY'}))
        return
    if args.action == 'start':
        expect(args.service in members and args.service not in HELPERS, 'start requires one explicit selected Deployment')
        name = args.service
        existing = json.loads(s.kubectl_read('get', 'deployments,statefulsets', '-A', '-o', 'json'))['items']
        if not any(x['metadata']['namespace'] == 'proof-' + name and x['metadata']['name'] == name for x in existing):
            secret = json.loads(s.read_private(state / (name + '-secret.json')))
            tls = None
            if name in ('seerr', 'radarr'):
                tls = json.loads(s.read_private(state / 'metadata-contract-secret.json'))
                tls['metadata']['namespace'] = 'proof-' + name
            if name == 'tautulli':
                marker = json.loads(s.read_private(state / 'plex-functional.json'))
                seed = ('[General]\napi_enabled = 1\napi_key = ' + credentials['tautulli']['api_key'] +
                    '\nfirst_run_complete = 1\nsystem_analytics = 0\nlaunch_browser = 0\n' +
                    '[PMS]\npms_ip = plex.proof-plex.svc\npms_port = 32401\npms_ssl = 0\npms_url_manual = 1\n' +
                    'pms_url = http://plex.proof-plex.svc:32401\npms_identifier = ' + marker['machine_id'] +
                    '\npms_token = ' + credentials['plex']['api_key'] + '\n' +
                    '[Monitoring]\nlogging_ignore_interval = 0\n[Advanced]\npms_timeout = 3\ncheck_github = 0\nmonitor_pms_updates = 0\n')
                secret['data']['seed'] = base64.b64encode(seed.encode()).decode()
            kube('apply', '-k', str(s.ROOT / 'kubernetes/apps/media' / name))
            kube('apply', '-f', '-', data=json.dumps(secret).encode())
            if tls:
                kube('apply', '-f', '-', data=json.dumps(tls).encode())
        # Existing Deployment is not reapplied: retain any clean-PVC recovery references.
        kube('-n', 'proof-' + name, 'scale', 'deployment', name, '--replicas=1', capacity=True)
        kube('-n', 'proof-' + name, 'rollout', 'status', 'deployment/' + name, '--timeout=300s')
        print(json.dumps({'service': name, 'result': 'STARTUP_ONLY'}))
        return
    expected = {'kometa': 'media-plex-kometa', 'jellyplex': 'media-plex-jellyplex', 'tautulli': 'media-plex-tautulli'}[args.action]
    expect(args.group == expected and args.ca is not None, 'workflow requires exact dependency group and trusted CA')
    ca = s.private_file(args.ca)
    plex = api_for('plex', ca, credentials)
    if args.action == 'kometa':
        result = kometa(args.group, kube, state, plex)
    elif args.action == 'jellyplex':
        result = jellyplex(args.group, kube, state, plex, api_for('jellyfin', ca, credentials), credentials['jellyfin'])
    else:
        expect(args.fixture is not None, 'Tautulli workflow requires actual synthetic MP4')
        result = tautulli(api_for('tautulli', ca, credentials), plex, credentials['tautulli'], state, args.fixture)
    print(json.dumps({'group': args.group, 'result': 'PASS', **result}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None),
                          'check': str(exc) if isinstance(exc, RuntimeError) else None}))
        raise SystemExit(1)
