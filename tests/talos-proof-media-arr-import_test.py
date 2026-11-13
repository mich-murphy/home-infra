#!/usr/bin/env python3
"""Offline API contract doubles and REAL temp-FS oracle; NOT app acceptance."""
import copy
import hashlib
import importlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
a = importlib.import_module('talos-proof-media-arr-import')


class ArrImport(unittest.TestCase):
    def test_all_operational_entry_points_fail_before_api_or_observer(self):
        api = Mock()
        for fn, args in ((a.configure_import, (api, 'offline-key')),
                         (a.wait_command, (api, 1)),
                         (a.configure_client, (api, {}, 'proof-test')),
                         (a.create_movie, (api, 1, Mock())),
                         (a.submit_torrent, (api, b'', {}, 'proof-test', Mock())),
                         (a.verify_completion, (api, {}, {}, {}, Mock())),
                         (a.process_completed, (api, '/data/torrents/x', 'hash')),
                         (a.manual_fallback, (api, 1, '/data/torrents/x', 'hash', []))):
            with self.subTest(fn=fn.__name__), self.assertRaisesRegex(RuntimeError, 'owner must wire'):
                fn(*args)
        with self.assertRaisesRegex(RuntimeError, 'owner must wire'):
            a.verify_import(api, 1, 'hash', '/data/torrents/x', {}, Mock(), mode='default-automatic')
        api.call.assert_not_called()

    def test_native_settings_and_command_failure_are_hard_gates(self):
        api = Mock()
        host = dict(proxyEnabled=False, proxyType='http', proxyHostname='', proxyPort=0,
                    proxyUsername='', proxyPassword='', proxyBypassFilter='', proxyBypassLocalAddresses=False)
        download = {'enableCompletedDownloadHandling': False}
        media = {'copyUsingHardlinks': False}
        stored = {'/api/v3/config/host':host, '/api/v3/config/downloadclient':download,
                  '/api/v3/config/mediamanagement':media}
        def call(path, method='GET', value=None):
            if method == 'PUT': stored[path] = copy.deepcopy(value)
            return copy.deepcopy(stored[path])
        api.call.side_effect = call
        with patch.object(a, 'require_owner_wiring'):
            a.configure_import(api, 'offline-fixture-key')
        self.assertTrue(stored['/api/v3/config/mediamanagement']['copyUsingHardlinks'])
        self.assertFalse(any('quality' in c.args[0] for c in api.call.call_args_list))
        api.call.side_effect = [{'status':'failed'}]
        with patch.object(a, 'require_owner_wiring'), self.assertRaisesRegex(RuntimeError, 'command failed'):
            a.wait_command(api, 1, interval=0)
        api.call.side_effect = [{'status':'started'}]
        with patch.object(a, 'require_owner_wiring'), self.assertRaisesRegex(RuntimeError, 'no manual fallback'):
            a.wait_command(api, 1, attempts=1, interval=0)

    def test_submission_has_private_immutable_attempt_and_no_output_write(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            api = Mock(); api.last_status=204
            api.call.side_effect = [[], dict(dht=False,pex=False,lsd=False), b'']
            marker = dict(destination='/data/torrents/unique',sha256='offline-hash',size=4,infohash='offline-hash')
            absent = Mock(return_value=True)
            with patch.object(a, 'require_owner_wiring'):
                attempt = a.submit_torrent(api,b'offline-torrent-bytes',marker,'proof-category',absent,state=state)
            self.assertTrue(attempt.is_file())
            self.assertEqual(attempt.stat().st_mode & 0o777, 0o600)
            self.assertEqual(api.call.call_args.args[:2],('/api/v2/torrents/add','POST'))
            self.assertEqual(list(state.iterdir()),[attempt])  # No downloaded/final bytes fabricated.
            api.reset_mock()
            with patch.object(a, 'require_owner_wiring'), self.assertRaisesRegex(RuntimeError,'already exists'):
                a.submit_torrent(api,b'',marker,'proof-category',lambda p:False,state=state)
            api.call.assert_not_called()

    def test_schema_test_before_create_and_native_defaults_preserved(self):
        schema = dict(implementation='QBittorrent', configContract='QBittorrentSettings',
                      fields=[dict(name=n, value='old') for n in ['host','port','useSsl','username','password','movieCategory','unrelatedDefault']])
        api = Mock()
        api.call.side_effect = [[], [schema], None, {'id': 12}]
        with patch.object(a, 'require_owner_wiring'):
            self.assertEqual(a.configure_client(api, dict(username='offline-user', password='offline-only'), 'proof-fixture'), 12)
        test, create = api.call.call_args_list[-2:]
        self.assertEqual(test.args[:2], ('/api/v3/downloadclient/test', 'POST'))
        self.assertEqual(create.args[:2], ('/api/v3/downloadclient', 'POST'))
        self.assertEqual(test.args[2], create.args[2])
        self.assertEqual(next(x['value'] for x in create.args[2]['fields'] if x['name']=='unrelatedDefault'), 'old')
        self.assertEqual(schema['fields'][0]['value'], 'old')
        api.reset_mock(); api.call.side_effect = [[], [schema], RuntimeError('native validation failed')]
        with patch.object(a, 'require_owner_wiring'), self.assertRaisesRegex(RuntimeError, 'native validation'):
            a.configure_client(api, dict(username='u', password='p'), 'proof-x')
        self.assertEqual(api.call.call_count, 3)  # Never create after test failure.

    def test_movie_requires_real_native_row_and_provider_counter(self):
        api = Mock()
        movie = dict(id=9, tmdbId=a.TMDB, title='Proof Fixture', hasFile=False)
        api.call.side_effect = [[], [{'id': 1}], [{'path':'/data/media/movies'}], movie, movie]
        evidence = Mock(side_effect=[{'requests': {}}, {'requests': {'/v1/movie/900000001': 1}}])
        with patch.object(a, 'require_owner_wiring'):
            self.assertEqual(a.create_movie(api, 1, evidence)['id'], 9)
        posted = api.call.call_args_list[-2].args[2]
        self.assertFalse(posted['addOptions']['searchForMovie'])
        api.call.side_effect = [[], [{'id': 1}], [{'path':'/data/media/movies'}], movie, movie]
        with patch.object(a, 'require_owner_wiring'), self.assertRaisesRegex(RuntimeError, 'metadata request'):
            a.create_movie(api, 1, lambda: {'requests': {}})

    def test_real_filesystem_hardlink_and_copy_corruption_negatives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = root/'source.mp4'; imported = root/'import.mp4'
            source.write_bytes(b'procedural offline bytes'); imported.hardlink_to(source)
            expected = dict(size=source.stat().st_size, sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertTrue(a.hardlink_oracle(a.observe_file(source), a.observe_file(imported), expected)['same_device_inode'])
            copied = root/'copied.mp4'; shutil.copyfile(source, copied)
            with self.assertRaises(RuntimeError): a.hardlink_oracle(a.observe_file(source), a.observe_file(copied), expected)
            corrupted = dict(a.observe_file(imported), sha256='corrupted')
            with self.assertRaisesRegex(RuntimeError, 'bytes differ'): a.hardlink_oracle(a.observe_file(source), corrupted, expected)
            wrong_device = dict(a.observe_file(imported), device=source.stat().st_dev+1)
            with self.assertRaisesRegex(RuntimeError, 'same-filesystem'): a.hardlink_oracle(a.observe_file(source), wrong_device, expected)
            link = root/'symlink'; link.symlink_to(source)
            with self.assertRaisesRegex(RuntimeError, 'symlink'): a.observe_file(link)

    def test_import_requires_file_row_history_and_download_linkage(self):
        movie = dict(id=9, tmdbId=a.TMDB, hasFile=True, movieFile={'id': 10})
        file = dict(id=10, movieId=9, size=4, path='/data/media/movies/Proof/import.mp4', mediaInfo={'videoCodec':'h264'})
        history = dict(records=[dict(id=11, movieId=9, eventType='downloadFolderImported', downloadId='abc', data={'importedPath':file['path']})])
        observed = dict(device=1, inode=2, links=2, regular=True, size=4, sha256='expected')
        for mutation in (None, 'history', 'download', 'file', 'movie', 'media'):
            m, f, h = map(copy.deepcopy, (movie, file, history))
            if mutation == 'history': h['records'] = []
            if mutation == 'download': h['records'][0]['downloadId'] = 'unrelated'
            if mutation == 'file': f['movieId'] = 99
            if mutation == 'movie': m['hasFile'] = False
            if mutation == 'media': f['mediaInfo'] = {}
            api = Mock(); api.call.side_effect = [m,f,h]
            with self.subTest(mutation=mutation), patch.object(a, 'require_owner_wiring'):
                call = lambda: a.verify_import(api, 9, 'abc', '/data/torrents/x/import.mp4',
                    dict(size=4,sha256='expected'), lambda p: observed, mode='completed-download-explicit-scan')
                if mutation is None:
                    result = call(); self.assertFalse(result['playback_proven']); self.assertFalse(result['production_automatic_parity'])
                    self.assertEqual(result['history_ids'], [11])
                else:
                    with self.assertRaises(RuntimeError): call()
            self.assertTrue(all(len(c.args)==1 for c in api.call.call_args_list))  # Read before writes.

    def test_explicit_scan_not_automatic_scheduler_claim_and_manual_separate(self):
        api = Mock(); api.call.return_value = {'id': 5}
        with patch.object(a, 'require_owner_wiring'):
            self.assertEqual(a.process_completed(api, '/data/torrents/run', 'abc'), 5)
        self.assertEqual(api.call.call_args.args[2]['name'], 'DownloadedMoviesScan')
        candidate = dict(path='/data/torrents/run/file.mp4', quality={'quality':{'id':1}}, languages=[{'id':1}])
        selected = dict(candidate, movieId=9, downloadId='abc')
        api.call.side_effect = [[candidate], {'id': 6}]
        with patch.object(a, 'require_owner_wiring'):
            result = a.manual_fallback(api, 9, '/data/torrents/run', 'abc', [selected])
        self.assertEqual(result['mode'], 'manual-import-with-reviewed-selections')
        self.assertFalse(result['production_automatic_parity'])
        self.assertEqual(api.call.call_args.args[2]['importMode'], 'Copy')
        selected['quality'] = {'quality':{'id':999}}
        api.call.side_effect = [[candidate]]
        with patch.object(a, 'require_owner_wiring'), self.assertRaisesRegex(RuntimeError, 'native candidate'):
            a.manual_fallback(api, 9, '/data/torrents/run', 'abc', [selected])

    def test_transfer_incomplete_or_zero_protocol_counters_rejected(self):
        api = Mock()
        marker = dict(infohash='abc', destination='/data/torrents/run', size=4, sha256='hash')
        row = dict(content_path='/data/torrents/run/file.mp4', progress=1, amount_left=0, completed=4, state='pausedUP')
        baseline = dict(sha256='hash', infohash='abc', counters=dict(tracker_announces=0, peer_handshakes=0, piece_requests=0, piece_bytes=0))
        after = copy.deepcopy(baseline); after['counters'] = dict(tracker_announces=1, peer_handshakes=1, piece_requests=1, piece_bytes=4)
        observe = lambda p: dict(size=4, sha256='hash')
        with patch.object(a, 'require_owner_wiring'):
            api.call.return_value=[row]
            self.assertEqual(a.verify_completion(api, marker, baseline, after, observe)[0], row['content_path'])
            with self.assertRaisesRegex(RuntimeError, 'positive'): a.verify_completion(api, marker, baseline, baseline, observe)
            api.call.return_value=[dict(row, progress=0.5)]
            with self.assertRaisesRegex(RuntimeError, 'incomplete'): a.verify_completion(api, marker, baseline, after, observe)


if __name__ == '__main__': unittest.main()
