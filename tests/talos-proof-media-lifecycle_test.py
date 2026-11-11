#!/usr/bin/env python3
"""Offline no-scale/HTTP convergence/memory collector regression tests."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
safety = importlib.import_module('talos-proof-media-safety')
batch = importlib.import_module('talos-proof-media-batch')
http = importlib.import_module('talos-proof-media-http')
memory = importlib.import_module('talos-proof-media-memory')


class Lifecycle(unittest.TestCase):
    def test_no_activation_scale_while_any_helper_pod_remains(self):
        secret = {'kind': 'Secret', 'metadata': {'namespace': 'proof-qbittorrent', 'name': 'bootstrap'}}
        for action in ('activate', 'start', 'restart'):
            for phase in ('Pending', 'Running', 'Succeeded', 'Failed'):
                pod = {'metadata': {'namespace': 'proof-qbittorrent', 'deletionTimestamp': 'now',
                       'ownerReferences': [{'kind': 'Job', 'name': 'volume-recovery'}]}, 'status': {'phase': phase}}
                with self.subTest(action=action, phase=phase), patch.object(sys, 'argv', ['batch', action, 'qbittorrent', '/private/offline']), \
                     patch.object(safety, 'private_dir', return_value=Path('/private/offline')), \
                     patch.object(safety, 'read_private', side_effect=[json.dumps({'qbittorrent': {}}), json.dumps(secret)]), \
                     patch.object(safety, 'lease'), patch.object(safety, 'guard'), \
                     patch.object(safety, 'kubectl_read', return_value=json.dumps({'items': [pod]})), \
                     patch.object(safety, 'kube') as execute:
                    with self.assertRaisesRegex(RuntimeError, 'helper pod still exists'):
                        batch.main()
                    execute.assert_not_called()  # No apply, rollout or scale-up while pod remains.
        with patch.object(safety, 'kubectl_read', return_value='{"items": []}'):
            safety.require_helpers_deleted('qbittorrent')

    def test_gateway_503_only_retries_readiness_get(self):
        api = object.__new__(http.API)
        probe = Mock(last_status=200)
        probe.call.side_effect = [urllib.error.HTTPError('proof', 503, '', {}, None), b'ready']
        with patch.object(api, 'anonymous', return_value=probe), patch.object(http.time, 'sleep') as wait:
            self.assertEqual(api.wait_ready('/healthcheck')['gateway_503_attempts'], 1)
            self.assertEqual(probe.call.call_args.args, ('/healthcheck',))
            wait.assert_called_once_with(2)
        for code in (401, 403, 404, 500):
            probe.call.reset_mock()
            probe.call.side_effect = urllib.error.HTTPError('proof', code, '', {}, None)
            with patch.object(api, 'anonymous', return_value=probe), patch.object(http.time, 'sleep') as wait:
                with self.assertRaises(urllib.error.HTTPError):
                    api.wait_ready()
                self.assertEqual(probe.call.call_count, 1)
                wait.assert_not_called()
        probe.call.reset_mock()
        probe.call.side_effect = urllib.error.HTTPError('proof', 503, '', {}, None)
        with patch.object(api, 'anonymous', return_value=probe), patch.object(http.time, 'sleep'):
            with self.assertRaises(urllib.error.HTTPError):
                api.wait_ready(attempts=3)
            self.assertEqual(probe.call.call_count, 3)

    def test_memory_reads_exact_endpoint_no_fallback_or_identity_edit(self):
        original = {'group': 'qbittorrent', 'expires': 9999999999, 'node_uid': 'offline', 'kubelet_available_mib': 10, 'talos_available_mib': 9}
        summary = json.dumps({'node': {'memory': {'availableBytes': 600 * 1048576}}})
        with patch.dict(os.environ, {'TALOSCONFIG': '/private/talosconfig', 'TALOS_PROOF_MEDIA_LEASE': '/private/lease'}), \
             patch.object(safety, 'lease', side_effect=lambda group: (original.copy(), {})), \
             patch.object(safety, 'private_file', return_value=Path('/private/talosconfig')), \
             patch.object(safety, 'kubectl_read', return_value=summary), \
             patch.object(safety, 'write_private') as write, \
             patch.object(memory.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'MemAvailable: 512000 kB\n')) as run:
            result = memory.refresh('qbittorrent', Path('/private/talosctl'))
            self.assertEqual(result['admission_mib'], 500)
            command = run.call_args.args[0]
            self.assertEqual(command, ['/private/talosctl', '--talosconfig', '/private/talosconfig', '-e', '127.0.0.1:50120', '-n', '172.31.250.10', 'read', '/proc/meminfo'])
            written = json.loads(write.call_args.args[1])
            self.assertEqual({k: v for k, v in written.items() if k not in ('kubelet_available_mib', 'talos_available_mib', 'measured_at')},
                             {k: v for k, v in original.items() if k not in ('kubelet_available_mib', 'talos_available_mib')})
            self.assertEqual(written['kubelet_available_mib'], 600)
            self.assertEqual(written['talos_available_mib'], 500)
            write.reset_mock()
            run.return_value = subprocess.CompletedProcess([], 1, b'')
            with self.assertRaises(RuntimeError):
                memory.refresh('qbittorrent', Path('/private/talosctl'))
            write.assert_not_called()

    def test_qbit_route_rewrites_host_not_tls_authority(self):
        for file, hostname in [('qbittorrent/httproute.yaml', 'qbittorrent.proof.invalid'),
                               ('integration/qbittorrent.yaml', 'pipeline-qbittorrent.proof.invalid')]:
            route = next(d for d in yaml.safe_load_all((ROOT / 'kubernetes/apps/media' / file).read_text()) if d['kind'] == 'HTTPRoute')
            self.assertEqual(route['spec']['hostnames'], [hostname])
            self.assertEqual(route['spec']['rules'][0]['filters'][0], {'type': 'URLRewrite', 'urlRewrite': {'hostname': hostname}})
        self.assertIn('HostHeaderValidation=true', (ROOT / 'scripts/talos-proof-media-bootstrap.py').read_text())
        self.assertIn('CSRFProtection=true', (ROOT / 'scripts/talos-proof-media-bootstrap.py').read_text())


if __name__ == '__main__':
    unittest.main()
