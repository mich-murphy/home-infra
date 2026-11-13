#!/usr/bin/env python3
"""Offline nonempty sync/idempotence and Kometa contract wiring checks."""
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
pipeline = importlib.import_module('talos-proof-media-pipeline')
ca = importlib.import_module('talos-proof-media-contract-ca')


class Helpers(unittest.TestCase):
    def test_real_recyclarr_two_syncs_nonempty_and_no_drift(self):
        for drift in (False, True):
            api = Mock()
            cf = {'id': 9, 'name': 'Proof-Synthetic-Title', 'specifications': [{'name': 'Proof', 'fields': [{'value': 'PROOF_FIXTURE'}]}]}
            api.call.side_effect = [[], [cf], [dict(cf, id=10) if drift else cf]]
            jobs = []
            def kube(*args, **kwargs):
                if 'cronjob' in args:
                    return json.dumps({'spec': {'jobTemplate': {'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 180,
                         'template': {'spec': {'containers': [{'args': ['sync', '--preview']}]}}}}}}).encode()
                if args[0] == 'create':
                    jobs.append(json.loads(kwargs['data']))
                if 'logs' in args: return b'bounded private synthetic log'
                if 'get' in args: return b'{"items": []}'
                return b''
            with tempfile.TemporaryDirectory() as tmp, patch.object(pipeline.safety, 'guard'), \
                 patch.object(pipeline.safety, 'require_helpers_deleted'), patch('builtins.print'):
                if drift:
                    with self.assertRaisesRegex(RuntimeError, 'drifted'):
                        pipeline.sync_recyclarr(kube, api, Path(tmp).resolve())
                else:
                    pipeline.sync_recyclarr(kube, api, Path(tmp).resolve())
                self.assertEqual(len(jobs), 2)
                for job in jobs:
                    self.assertEqual(job['spec']['template']['spec']['containers'][0]['args'], ['sync'])
                    self.assertEqual(job['spec']['backoffLimit'], 0)

    def test_native_kometa_contract_sidecar_and_no_global_ca_override(self):
        rendered = subprocess.check_output(['kubectl', 'kustomize', str(ROOT / 'kubernetes/apps/media/kometa')])
        docs = list(yaml.safe_load_all(rendered))
        cron = next(d for d in docs if d['kind'] == 'CronJob')
        self.assertTrue(cron['spec']['suspend'])
        pod = cron['spec']['jobTemplate']['spec']['template']['spec']
        side = next(c for c in pod['initContainers'] if c['name'] == 'metadata-contract')
        self.assertEqual(side['restartPolicy'], 'Always')  # Stops with main process; Job can complete.
        self.assertEqual(side['resources']['limits']['memory'], '128Mi')
        self.assertTrue(side['securityContext']['readOnlyRootFilesystem'])
        main = pod['containers'][0]
        env = {x['name']: x['value'] for x in main['env']}
        self.assertEqual(env['HTTPS_PROXY'], 'http://127.0.0.1:18081')
        self.assertIn('.svc', env['NO_PROXY'])
        self.assertEqual(env['REQUESTS_CA_BUNDLE'], '/proof-contract-tls/ca.crt')
        self.assertFalse(any('hostAliases' in p for p in [pod]))
        self.assertNotIn('hostNetwork', pod)
        self.assertFalse(any(d['kind'] == 'Secret' for d in docs))

    def test_private_offline_ca_verifies_and_refuses_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve()
            result = ca.generate(state)
            self.assertEqual(result['result'], 'OFFLINE_CA_ONLY')
            for file in state.iterdir():
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            secret = json.loads((state / 'metadata-contract-secret.json').read_text())
            self.assertEqual(secret['metadata']['namespace'], 'proof-kometa')
            self.assertNotIn('metadata-ca.key', secret['data'])
            with self.assertRaises(RuntimeError):
                ca.generate(state)


if __name__ == '__main__':
    unittest.main()
