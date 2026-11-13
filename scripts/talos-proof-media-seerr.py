#!/usr/bin/env python3
"""Staged real Seerr/Jellyfin login and real Radarr request/permission workflow.

Requires separate exact dependency leases. TMDb/Skyhook fixtures are metadata
contracts only; Radarr itself must be the real pinned proof service, not a stub.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

s = importlib.import_module('talos-proof-media-safety')
d = importlib.import_module('talos-proof-media-dependencies')
TMDB = 900000001


def requester_password(credential):
    return hashlib.sha256((credential['password'] + ':seerr-requester').encode()).hexdigest()


def local_login(api, email, password):
    user = api.call('/api/v1/auth/local', 'POST', {'email': email, 'password': password})
    d.expect(user['id'] == api.call('/api/v1/auth/me')['id'], 'Seerr local cookie session identity differs')
    return user


def login_phase(api, credentials, state):
    d.rejected(lambda: api.anonymous().call('/api/v1/auth/me'))
    # This phase MUST use actual fresh proof Jellyfin authentication, never Plex/cloud.
    owner = api.call('/api/v1/auth/jellyfin', 'POST', {'username': credentials['jellyfin']['username'],
        'password': credentials['jellyfin']['password'], 'hostname': 'jellyfin.proof-jellyfin.svc', 'port': 8096,
        'useSsl': False, 'serverType': 2, 'email': 'owner@proof.invalid'})
    d.expect(owner['id'] == 1, 'Seerr fresh Jellyfin owner was not initialized as owner')
    api.call('/api/v1/user/1/settings/password', 'POST', {'newPassword': credentials['seerr']['password']}, raw=True)
    api.call('/api/v1/settings/main', 'POST', {'localLogin': True, 'mediaServerLogin': True, 'versionCheck': False,
        'applicationUrl': 'https://seerr.proof.invalid:18443', 'locale': 'en', 'defaultPermissions': 0})
    requester = api.call('/api/v1/user', 'POST', {'email': 'requester@proof.invalid', 'username': 'proof-requester',
        'password': requester_password(credentials['seerr'])})
    path = '/api/v1/user/' + str(requester['id']) + '/settings/permissions'
    api.call(path, 'POST', {'permissions': 32})  # REQUEST only; no auto-approve/manage/admin.
    d.expect(api.call(path)['permissions'] == 32, 'requester permissions differ')
    api.call('/api/v1/auth/logout', 'POST', raw=True)
    local_login(api, 'owner@proof.invalid', credentials['seerr']['password'])
    # Local owner login makes it possible to stop Jellyfin before request phase.
    marker = {'owner_id': 1, 'requester_id': requester['id'], 'jellyfin_authenticated': True}
    s.write_private(state / 'seerr-login.json', json.dumps(marker))
    return ['real proof Jellyfin owner authentication', 'fresh local owner password/session', 'requester REQUEST-only permission persisted']


def request_phase(api, radarr, credential, state, verify=False):
    login = json.loads(s.read_private(state / 'seerr-login.json'))
    owner = local_login(api, 'owner@proof.invalid', credential['password'])
    d.expect(owner['id'] == login['owner_id'], 'owner identity lost')
    if verify:
        marker = json.loads(s.read_private(state / 'seerr-functional.json'))
        request = api.call('/api/v1/request/' + str(marker['request_id']))
        d.expect(request['status'] == 2 and request['requestedBy']['id'] == login['requester_id'], 'existing approved request lost')
        movie = radarr.call('/api/v3/movie/' + str(marker['radarr_id']))
        d.expect(movie['tmdbId'] == TMDB and movie['id'] == marker['radarr_id'], 'real Radarr object lost')
        return ['existing approved request/requester verified before writes', 'same actual Radarr object ID/TMDbID retained']
    d.expect(api.call('/api/v1/request')['results'] == [], 'fresh request workflow requires empty request history')
    d.expect(not radarr.call('/api/v3/movie'), 'fresh request workflow requires no existing Radarr movie')
    host = radarr.call('/api/v3/config/host')
    host.update(proxyEnabled=True, proxyType='http', proxyHostname='127.0.0.1', proxyPort=18081,
                proxyUsername='proof', proxyPassword=radarr.headers['X-Api-Key'], proxyBypassFilter='*.svc', proxyBypassLocalAddresses=True)
    radarr.call('/api/v3/config/host', 'PUT', host)
    profiles = radarr.call('/api/v3/qualityprofile')
    d.expect(bool(profiles), 'real Radarr has no usable profile')
    roots = radarr.call('/api/v3/rootfolder')
    if not any(x['path'] == '/data' for x in roots):
        radarr.call('/api/v3/rootfolder', 'POST', {'path': '/data'})
    settings = {'name': 'Proof Radarr', 'hostname': 'radarr.proof-radarr.svc', 'port': 7878, 'useSsl': False,
        'apiKey': radarr.headers['X-Api-Key'], 'baseUrl': '', 'activeProfileId': profiles[0]['id'],
        'activeDirectory': '/data', 'is4k': False, 'isDefault': True, 'minimumAvailability': 'released',
        'tags': [], 'syncEnabled': False, 'preventSearch': True, 'tagRequests': False}
    test = api.call('/api/v1/settings/radarr/test', 'POST', settings)
    d.expect(any(x['id'] == profiles[0]['id'] for x in test['profiles']), 'Seerr did not authenticate against actual Radarr API')
    d.expect(api.call('/api/v1/settings/radarr') == [], 'refuse to replace existing arr configuration')
    api.call('/api/v1/settings/radarr', 'POST', settings)
    # Fixture-only authenticated proxy, bypass ONLY proof .svc traffic to real Arr/Jellyfin.
    api.call('/api/v1/settings/network', 'POST', {'csrfProtection': True, 'proxy': {'enabled': True,
        'hostname': '127.0.0.1', 'port': 18081, 'useSsl': False, 'user': 'proof', 'password': credential['api_key'],
        'bypassLocalAddresses': True, 'bypassFilter': '*.svc'}})
    requester = api.anonymous()
    account = local_login(requester, 'requester@proof.invalid', requester_password(credential))
    d.expect(account['id'] == login['requester_id'], 'requester identity lost')
    d.rejected(lambda: requester.call('/api/v1/settings/main', 'POST', {'defaultPermissions': 2}))
    d.rejected(lambda: requester.call('/api/v1/user/' + str(login['requester_id']) + '/settings/permissions', 'POST', {'permissions': 2}))
    request = requester.call('/api/v1/request', 'POST', {'mediaType': 'movie', 'mediaId': TMDB, 'is4k': False})
    d.expect(request['status'] == 1 and request['requestedBy']['id'] == login['requester_id'], 'request must remain genuinely pending without auto-approval')
    ident = request['id']
    s.write_private(state / 'seerr-request-attempt.json', json.dumps({'request_id': ident, 'requester_id': login['requester_id']}))
    d.rejected(lambda: requester.call('/api/v1/request/' + str(ident) + '/approve', 'POST'))
    d.expect(requester.call('/api/v1/request/' + str(ident))['status'] == 1, 'denied approval changed request status')
    api.call('/api/v1/request/' + str(ident) + '/approve', 'POST')
    movie = None
    for _ in range(30):
        current = api.call('/api/v1/request/' + str(ident))
        d.expect(current['status'] != 5, 'Seerr asynchronous real Arr submission failed; approval response alone is not success')
        matches = [x for x in radarr.call('/api/v3/movie') if x['tmdbId'] == TMDB]
        if current['status'] == 2 and len(matches) == 1:
            movie = matches[0]
            break
        time.sleep(2)
    d.expect(movie is not None and movie['id'] > 0 and movie['title'] == 'Proof Fixture', 'approval did not create genuine synthetic movie in actual Radarr')
    marker = {'request_id': ident, 'requester_id': login['requester_id'], 'radarr_id': movie['id'], 'tmdb_id': TMDB}
    s.write_private(state / 'seerr-functional.json', json.dumps(marker))
    return ['REQUEST-only user denied settings/self-escalation/approval', 'pending real request retained after denial',
            'authorized owner approval', 'actual pinned Radarr object created asynchronously; no search/download claim']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['login', 'request', 'verify'])
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--ca', type=Path, required=True)
    args = p.parse_args()
    group = 'media-seerr-login' if args.phase == 'login' else 'media-seerr-request'
    s.lease(group); s.exclusivity(group); s.guard(group)
    state = s.private_dir(args.state)
    credentials = json.loads(s.read_private(state / 'credentials.json'))
    ca = s.private_file(args.ca)
    api = d.api_for('seerr', ca, credentials)
    api.wait_ready('/api/v1/status')
    if args.phase == 'login':
        checks = login_phase(api, credentials, state)
    else:
        checks = request_phase(api, d.api_for('radarr', ca, credentials), credentials['seerr'], state, args.phase == 'verify')
    print(json.dumps({'service': 'seerr', 'phase': args.phase, 'result': 'PASS', 'checks': checks,
                      'metadata_scope': 'synthetic no-forwarding contract; NOT upstream account integration'}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None),
                          'check': str(exc) if isinstance(exc, RuntimeError) else None}))
        raise SystemExit(1)
