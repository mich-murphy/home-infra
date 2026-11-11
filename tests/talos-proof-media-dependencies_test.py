#!/usr/bin/env python3
"""Offline dependency and strict multi-provider contract tests, not live success."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
s = importlib.import_module('talos-proof-media-safety')
d = importlib.import_module('talos-proof-media-dependencies')
seerr = importlib.import_module('talos-proof-media-seerr')
spec = importlib.util.spec_from_file_location('metadata_dependency_test', ROOT / 'kubernetes/apps/media/fixtures/metadata-proxy.py')
proxy = importlib.util.module_from_spec(spec); spec.loader.exec_module(proxy)


class Dependencies(unittest.TestCase):
    def test_fixed_exact_groups_and_full_budgets(self):
        costs = {group: sum(s.BUDGET[name] for name in names) + 192 for group, names in s.DEPENDENCY_BATCHES.items()}
        self.assertEqual(costs, {'media-plex-tautulli': 896, 'media-plex-kometa': 1152, 'media-plex-jellyplex': 1344,
                                 'media-seerr-login': 1216, 'media-seerr-request': 1216})
        self.assertEqual(s.group_namespaces('media-seerr-request'), {'proof-seerr', 'proof-radarr'})
        self.assertNotIn('proof-jellyfin', s.group_namespaces('media-seerr-request'))

    def test_bundled_key_not_auth_without_fresh_proxy_credential(self):
        fixtures = json.loads((ROOT / 'kubernetes/apps/media/fixtures/tmdb-contract.json').read_text())
        c = proxy.Contract(fixtures, 'OFFLINE-FRESH-KEY', client='seerr')
        path = '/3/movie/900000001?api_key=bundled-not-proof&language=en&append_to_response=credits,external_ids,videos,keywords,release_dates,watch/providers&include_video_language=en'
        self.assertEqual(c.lookup('GET', path)[0], 401)
        with patch('socket.create_connection', side_effect=AssertionError('no upstream socket')):
            status, body = c.lookup('GET', path, proxy_authenticated=True)
        self.assertEqual(status, 200); self.assertEqual(body['id'], 900000001)
        self.assertEqual(c.lookup('GET', path.replace('900000001', '1'), proxy_authenticated=True)[0], 501)
        self.assertEqual(c.evidence()['upstream_connections'], 0)

    def test_radarr_contract_is_only_metadata_not_arr_api(self):
        data = json.loads((ROOT / 'kubernetes/apps/media/fixtures/skyhook-contract.json').read_text())
        c = proxy.Contract({}, 'OFFLINE-FRESH-KEY', client='radarr', skyhook=data)
        self.assertEqual(c.lookup('GET', '/v1/movie/900000001', host='api.radarr.video')[0], 501)
        status, movie = c.lookup('GET', '/v1/movie/900000001', host='api.radarr.video', proxy_authenticated=True)
        self.assertEqual(status, 200); self.assertEqual(movie['tmdbId'], 900000001)
        for method, path, host in [('POST', '/v1/movie/900000001', 'api.radarr.video'), ('GET', '/api/v3/movie', 'radarr.proof-radarr.svc'),
                                    ('GET', '/v1/movie/1', 'api.radarr.video'), ('GET', '/v1/movie/900000001?arbitrary=1', 'api.radarr.video')]:
            self.assertEqual(c.lookup(method, path, host=host, proxy_authenticated=True)[0], 501)

    def test_actual_kometa_requires_nonempty_and_second_same_id(self):
        for drift in (False, True):
            replies = [b'<MediaContainer/>', b'<MediaContainer><Directory title="Proof Synthetic Collection" ratingKey="9"/></MediaContainer>',
                b'<MediaContainer><Video ratingKey="7"/></MediaContainer>',
                ('<MediaContainer><Directory title="Proof Synthetic Collection" ratingKey="' + ('10' if drift else '9') + '"/></MediaContainer>').encode(),
                b'<MediaContainer><Video ratingKey="7"/></MediaContainer>']
            plex = Mock(); plex.call.side_effect = replies
            with tempfile.TemporaryDirectory() as tmp, patch.object(s, 'read_private', return_value=json.dumps({'library_id':'1','item_id':'7'})), \
                 patch.object(d, 'run_job', return_value='sanitized-log-hash') as job:
                if drift:
                    with self.assertRaisesRegex(RuntimeError, 'drifted'):
                        d.kometa('media-plex-kometa', Mock(), Path(tmp).resolve(), plex)
                else:
                    d.kometa('media-plex-kometa', Mock(), Path(tmp).resolve(), plex)
                self.assertEqual(job.call_count, 2)
                self.assertIn('--collections-only', job.call_args.kwargs['args'])
                self.assertNotIn('--dry-run', job.call_args.kwargs['args'])

    def test_seerr_recovery_verifies_actual_request_and_radarr_ids_without_configuration_writes(self):
        api = Mock(); arr = Mock()
        api.call.side_effect = [{'id':1}, {'id':1}, {'status':2,'requestedBy':{'id':3}}]
        arr.call.return_value = {'id':8,'tmdbId':900000001}
        with patch.object(s, 'read_private', side_effect=[json.dumps({'owner_id':1,'requester_id':3}),json.dumps({'request_id':4,'radarr_id':8})]):
            seerr.request_phase(api, arr, {'password':'fresh-offline'}, Path('/unused'), verify=True)
        self.assertEqual([c.args[0] for c in api.call.call_args_list], ['/api/v1/auth/local','/api/v1/auth/me','/api/v1/request/4'])
        arr.call.assert_called_once_with('/api/v3/movie/8')


if __name__ == '__main__': unittest.main()
