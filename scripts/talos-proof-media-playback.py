#!/usr/bin/env python3
"""Private decoder/timeline bridge. Actual server compatibility is a live gate.

No credentials in IPC/results. The same client/session identifiers accompany
original media GET and native timeline calls. Never invent an active session.
"""
import importlib
import json
from pathlib import Path
import secrets
import sys
import time
import uuid
import urllib.parse

s = importlib.import_module('talos-proof-media-safety')
d = importlib.import_module('talos-proof-media-dependencies')


def tautulli_call(api, credential, command, **params):
    response = api.call('/api/v2', 'POST', form={'apikey': credential['api_key'], 'cmd': command, **params})['response']
    d.expect(response['result'] == 'success', 'Tautulli command failed')
    return response['data']


def prepare(state, ca, group):
    d.expect(group == 'media-plex-tautulli', 'playback requires exact Plex/Tautulli group')
    credentials = json.loads(s.read_private(state / 'credentials.json'))
    marker = json.loads(s.read_private(state / 'plex-functional.json'))
    api = d.api_for('tautulli', ca, credentials)
    d.rejected(lambda: api.anonymous().call('/api/v2?cmd=get_activity'))
    settings = tautulli_call(api, credentials['tautulli'], 'get_settings')
    d.expect(str(settings['Monitoring']['logging_ignore_interval']) == '0', 'tiny clip needs explicit zero history ignore threshold')
    rows = tautulli_call(api, credentials['tautulli'], 'get_history', rating_key=marker['item_id'], include_activity=0)['data']
    d.expect(not rows, 'retain previous history; first decoder run requires no existing item history')
    return {'state': str(state), 'ca': str(ca), 'group': group, 'item': marker['item_id'],
            'client': 'proof-decoder-' + secrets.token_hex(8), 'session': 'proof-session-' + secrets.token_hex(8)}


def callback(payload):
    """Called while video is active, or immediately after its explicit pause."""
    bridge, event = payload['bridge'], payload['event']
    if bridge.get('service') == 'jellyfin':
        return importlib.import_module('talos-proof-media-jellyfin').callback(bridge, event)
    d.expect(bridge['group'] == 'media-plex-tautulli', 'wrong playback group')
    importlib.import_module('talos-proof-media-browser').check_lease('plex', bridge['group'])
    state = s.private_dir(Path(bridge['state']))
    ca = s.private_file(Path(bridge['ca']))
    credentials = json.loads(s.read_private(state / 'credentials.json'))
    marker = json.loads(s.read_private(state / 'plex-functional.json'))
    d.expect(bridge['item'] == marker['item_id'], 'playback item changed')
    d.expect(event['state'] in ('playing', 'stopped') and 0 <= event['time'] <= event['duration'] <= 15000,
             'invalid decoder timeline')
    plex = d.api_for('plex', ca, credentials)
    plex.headers.update({'X-Plex-Client-Identifier': bridge['client'], 'X-Plex-Session-Identifier': bridge['session']})
    query = {'ratingKey': bridge['item'], 'key': '/library/metadata/' + bridge['item'],
             'state': event['state'], 'time': int(event['time']), 'duration': int(event['duration']),
             'session': bridge['session'], 'X-Plex-Client-Identifier': bridge['client']}
    plex.call('/:/timeline?' + urllib.parse.urlencode(query), raw=True)
    if event['state'] == 'stopped':
        sessions = d.xml(plex, '/status/sessions')
        d.expect(not any(player.get('machineIdentifier') == bridge['client'] and player.get('state') == 'playing'
                         for player in sessions.iter('Player')), 'same client remains playing after stopped timeline')
        return {'stopped': True}
    sessions = tautulli_call(d.api_for('tautulli', ca, credentials), credentials['tautulli'], 'get_activity').get('sessions', [])
    # Require THIS client/item, not a stale or unrelated playing session.
    active = any(str(x.get('rating_key')) == bridge['item'] and x.get('machine_id') == bridge['client']
                 and x.get('state') == 'playing' for x in sessions)
    return {'active': active}


def finish(state, ca, bridge, decoder):
    d.expect(decoder['timeline_activity_observed'] and decoder['timeline_stopped'], 'missing actual concurrent activity/stopped gates')
    credentials = json.loads(s.read_private(state / 'credentials.json'))
    api = d.api_for('tautulli', ca, credentials)
    rows = []
    for _ in range(15):
        importlib.import_module('talos-proof-media-browser').check_lease('plex', bridge['group'])
        rows = tautulli_call(api, credentials['tautulli'], 'get_history', rating_key=bridge['item'], include_activity=0)['data']
        if rows:
            break
        time.sleep(2)
    d.expect(len(rows) == 1 and str(rows[0]['rating_key']) == bridge['item'] and
             rows[0].get('machine_id') == bridge['client'] and int(rows[0]['duration']) > 0,
             'no unique durable history for this actual decoder client')
    s.write_private(state / ('tautulli-decoder-' + uuid.uuid4().hex + '.json'), json.dumps({
        'history_id': rows[0]['row_id'], 'rating_key': bridge['item'], 'client': bridge['client'],
        'session': bridge['session'], 'decoder': decoder, 'history_ignore_seconds': 0}))


if __name__ == '__main__':
    payload = None
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(callback(payload)))
    except Exception as exc:
        failure = {'failed': True, 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None)}
        if payload:
            try:
                state = s.private_dir(Path(payload['bridge']['state']))
                s.write_private(state / ('playback-callback-failure-' + uuid.uuid4().hex + '.json'), json.dumps(failure))
                if isinstance(exc, urllib.error.HTTPError):
                    s.write_private(state / ('playback-private-http-failure-' + uuid.uuid4().hex + '.log'), exc.read())
            except Exception:
                pass  # Never hide original failure or emit secret-bearing details.
        print(json.dumps(failure))
        raise SystemExit(1)
