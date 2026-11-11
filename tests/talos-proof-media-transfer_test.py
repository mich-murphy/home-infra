#!/usr/bin/env python3
"""Offline transfer integration contracts; not real-client acceptance."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
s = importlib.import_module('talos-proof-media-safety')
t = importlib.import_module('talos-proof-media-transfer')


class Transfer(unittest.TestCase):
    def test_explicit_lease_and_full_576_admission_no_shrink(self):
        receipt = {'available_mib': 575, 'measured_at': 0}
        node = {'status': {'allocatable': {'memory': '3000000Ki'}}}
        with patch.object(s, 'lease', return_value=(receipt, node)):
            with self.assertRaisesRegex(RuntimeError, 'explicitly authorize'):
                s.protocol_guard('qbittorrent')
        receipt.update(protocol_fixture='download-protocols', measured_at=100)
        for svc in ('qbittorrent', 'sabnzbd'):
            with patch.object(s, 'lease', return_value=(receipt, node)), patch.object(s, 'exclusivity'), \
                 patch.object(s.time, 'time', return_value=101), patch.object(s, 'kubectl_read', return_value='{"items": []}'):
                receipt['available_mib'] = 575
                with self.assertRaisesRegex(RuntimeError, 'headroom'):
                    s.protocol_guard(svc)
                receipt['available_mib'] = 576
                s.protocol_guard(svc)

    def test_basic_activation_charges_desired_or_terminating_fixture(self):
        receipt = {'available_mib': 575, 'measured_at': 100, 'protocol_fixture': 'download-protocols'}
        node = {'status': {'allocatable': {'memory': '3000000Ki'}}}
        controller = {'metadata': {'namespace': 'proof-qbittorrent', 'name': 'download-protocols'}, 'spec': {'replicas': 1}}
        pod = {'metadata': {'namespace': 'proof-qbittorrent', 'deletionTimestamp': 'now', 'labels': {'app.kubernetes.io/name': 'download-protocols'}}, 'status': {'phase': 'Running'}}
        for controllers, pods in [([controller], []), ([], [pod])]:
            def read(*args):
                return json.dumps({'items': controllers if args[1] == 'deployments,statefulsets' else pods})
            with patch.object(s, 'lease', return_value=(receipt, node)), patch.object(s, 'exclusivity'), \
                 patch.object(s.time, 'time', return_value=101), patch.object(s, 'kubectl_read', side_effect=read):
                with self.assertRaisesRegex(RuntimeError, 'headroom'):
                    s.guard('qbittorrent')
                receipt['available_mib'] = 576
                s.guard('qbittorrent')
                with self.assertRaisesRegex(RuntimeError, 'stop and delete'):
                    s.guard('qbittorrent', budget_mib=128)
                receipt['available_mib'] = 575

    def test_profiles_are_zero_no_client_volume_or_broad_peers(self):
        for svc in ('qbittorrent', 'sabnzbd'):
            data = subprocess.check_output(['kubectl', 'kustomize', str(ROOT / 'kubernetes/apps/media' / ('protocol-' + svc))])
            subprocess.run([sys.executable, str(ROOT / 'tests/kubernetes-proof.py')], input=data, check=True, stdout=subprocess.PIPE)
            docs = list(yaml.safe_load_all(data))
            dep = next(d for d in docs if d['kind'] == 'Deployment')
            self.assertEqual(dep['spec']['replicas'], 0)
            pod = dep['spec']['template']['spec']
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertFalse(any('persistentVolumeClaim' in v or 'hostPath' in v for v in pod['volumes']))
            self.assertEqual(pod['containers'][0]['resources']['limits']['memory'], '128Mi')
            self.assertIn('/payload/synthetic-proof.wav', pod['containers'][0]['args'])
            for policy in [d for d in docs if d['kind'] == 'NetworkPolicy']:
                for direction, peers in [('ingress', 'from'), ('egress', 'to')]:
                    for rule in policy['spec'].get(direction, []):
                        for peer in rule[peers]:
                            self.assertIn('namespaceSelector', peer)
                            self.assertIn('podSelector', peer)
                            self.assertNotIn('ipBlock', peer)

    def test_zero_counters_or_hash_drift_never_pass(self):
        before = {'sha256': 'same', 'infohash': 'same', 'counters': dict(tracker_announces=0, peer_handshakes=0, piece_requests=0, piece_bytes=0)}
        after = json.loads(json.dumps(before))
        with self.assertRaisesRegex(RuntimeError, 'positive'):
            t.counters(before, after, 'qbittorrent', 10)
        after['counters'].update(tracker_announces=1, peer_handshakes=1, piece_requests=1, piece_bytes=10)
        self.assertEqual(t.counters(before, after, 'qbittorrent', 10)['piece_bytes'], 10)
        after['sha256'] = 'different'
        with self.assertRaisesRegex(RuntimeError, 'identity'):
            t.counters(before, after, 'qbittorrent', 10)

    def test_verify_existing_completed_qbit_without_fixture_or_submission(self):
        marker = {'infohash': 'abc', 'size': 10, 'sha256': 'abc', 'destination': '/data/torrents/protocol-test'}
        def call(path, *args, **kw):
            if path.endswith('login'): return b'Ok.'
            if path.endswith('preferences'): return dict(dht=False, pex=False, lsd=False)
            if path.startswith('/api/v2/torrents/info?'): return [dict(progress=1, completed=10, amount_left=0)]
            raise AssertionError('unexpected mutation or request: ' + path)
        api = Mock(last_status=200); api.call.side_effect = call
        with patch.object(s, 'read_private', return_value=json.dumps(marker)), patch.object(t, 'output_hash') as output, \
             patch.object(t, 'fixture_get', side_effect=AssertionError('verify must not read fixture')), \
             patch.object(t, 'empty_destination', side_effect=AssertionError('verify must not create output')):
            self.assertEqual(t.qbit(api, 'qbittorrent', dict(username='proof', password='offline'), Path('/unused'), 'verify'), marker)
            output.assert_called_once_with('qbittorrent', '/data/torrents/protocol-test/' + t.NAME, marker)

    def test_output_checksum_rejects_wrong_size_or_preexisting_destination(self):
        marker = {'size': 10, 'sha256': 'abc'}
        for output in (b'9\nabc file\n', b'10\nwrong file\n'):
            with patch.object(t, 'remote', return_value=output):
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    t.output_hash('qbittorrent', '/data/torrents/test/' + t.NAME, marker)
        with patch.object(t, 'remote') as remote:
            t.empty_destination('qbittorrent', '/data/torrents/protocol-test')
            self.assertIn('test ! -e "$1"', remote.call_args.args[1])
            self.assertNotIn('rm ', remote.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
