#!/usr/bin/env python3
"""Offline regression checks for first-batch durable state and failure evidence."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
observe = importlib.import_module('talos-proof-media-observe')
services = importlib.import_module('talos-proof-media-services')


class QbitAPI:
    def __init__(self, preference=7):
        self.preference = preference
        self.writes = 0
    def anonymous(self):
        class Anonymous:
            def call(self, *args, **kwargs):
                raise urllib.error.HTTPError('https://proof.invalid', 403, 'Forbidden', {}, None)
        return Anonymous()
    def call(self, path, method='GET', **kwargs):
        if path.endswith('/auth/login'):
            return b'Ok.'
        if path.endswith('/torrents/info'):
            return []
        if path.endswith('/app/preferences'):
            return {'max_active_downloads': self.preference, 'dht': False, 'pex': False, 'lsd': False}
        if path.endswith('/app/setPreferences'):
            self.writes += 1
            self.preference = json.loads(kwargs['form']['json'])['max_active_downloads']
            return b''
        raise AssertionError('unexpected API path')


class FirstBatch(unittest.TestCase):
    def test_qbit_verify_reads_before_writes_and_fails_on_lost_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve()
            credential = {'username': 'proof', 'password': 'fresh-private'}
            api = QbitAPI()
            services.qbittorrent(api, credential, None, state, 'exercise')
            self.assertEqual(api.writes, 1)
            marker = json.loads((state / 'qbittorrent-functional.json').read_text())
            api.writes = 0
            services.qbittorrent(api, credential, None, state, 'verify')
            self.assertEqual(api.writes, 0)
            api.preference = marker['max_active_downloads'] + 1
            with self.assertRaisesRegex(RuntimeError, 'durable preference lost'):
                services.qbittorrent(api, credential, None, state, 'verify')
            self.assertEqual(api.writes, 0)

    def test_failed_history_survives_latest_restart_zero_without_secret_messages(self):
        pod = {'metadata': {'name': 'qbit-old', 'uid': 'old-uid'}, 'status': {'phase': 'Failed',
            'containerStatuses': [{'name': 'qbittorrent', 'imageID': 'sha256:old', 'restartCount': 3,
                'state': {'terminated': {'reason': 'OOMKilled', 'exitCode': 137, 'message': 'secret-password'}},
                'lastState': {'terminated': {'reason': 'OOMKilled', 'exitCode': 137}}}]}}
        current = {'metadata': {'name': 'qbit-new', 'uid': 'new-uid'}, 'status': {'phase': 'Running',
            'containerStatuses': [{'name': 'qbittorrent', 'restartCount': 0, 'state': {'running': {'startedAt': 'now'}}}]}}
        def kube(group, *args):
            if 'get' in args:
                return json.dumps({'items': [pod, current]}).encode()
            return b'FILE memory.current\n1024\nFILE memory.peak\n4096\nFILE memory.events\noom_kill 0\n'
        with tempfile.TemporaryDirectory() as tmp, patch.object(observe.safety, 'lease'), patch.object(observe.safety, 'exclusivity'), patch.object(observe.safety, 'kube', side_effect=kube):
            state = Path(tmp).resolve()
            with patch('builtins.print'):
                first = observe.capture('qbittorrent', state)
                observe.capture('qbittorrent', state)
            self.assertEqual(len(list(state.glob('*-observation-*.json'))), 2)
            self.assertNotIn('secret-password', json.dumps(first))
            self.assertEqual(first['pods'][0]['containers'][0]['state']['terminated']['reason'], 'OOMKilled')
            self.assertEqual(first['pods'][1]['containers'][0]['restartCount'], 0)
            self.assertIn('4096', first['pods'][1]['containers'][0]['cgroup'])

    def test_counter_output_filter(self):
        for line in ['FILE memory.stat', 'anon 123', 'oom_kill 2', '4096', 'UNAVAILABLE']:
            self.assertTrue(observe.valid_line(line))
        for line in ['password=secret', 'message secret password', 'FILE /etc/passwd', '']:
            self.assertFalse(observe.valid_line(line))


if __name__ == '__main__':
    unittest.main()
