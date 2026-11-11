#!/usr/bin/env python3
"""Offline tests only; never connect to a cluster."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('operations', ROOT / 'scripts/talos-proof-operations.py')
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class Operations(unittest.TestCase):
    def test_actual_measurements_and_allowlist(self):
        node = {'metadata': {'name': 'proof'}, 'status': {'capacity': {'memory': '2560Mi'}, 'allocatable': {'memory': '2200Mi'}}}
        summary = {'node': {'memory': {'availableBytes': 400 * 1024**2}, 'fs': {'capacityBytes': 100}},
                   'pods': [{'podRef': {'namespace': 'proof-test', 'name': 'fixture'}, 'memory': {'workingSetBytes': 12},
                             'volume': [{'name': 'data', 'usedBytes': 4, 'private': 'not-exported'}]}]}
        pods = {'items': [{'metadata': {'namespace': 'proof-test', 'name': 'fixture', 'secret': 'not-exported'},
                           'status': {'containerStatuses': [{'name': 'fixture', 'restartCount': 1}]}}]}
        sample = ops.summarize(node, summary, pods)
        self.assertEqual(sample['pods'][0]['memory']['workingSetBytes'], 12)
        self.assertNotIn('not-exported', json.dumps(sample))
        self.assertEqual([a['rule'] for a in ops.alerts(sample, 512 * 1024**2, True)],
                         ['NodeMemoryHeadroomLow', 'ContainerRestartObserved', 'ProofDeliveryTest'])
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'receipts.json'
            events = ops.alerts(sample, 512 * 1024**2, True)
            ops.deliver(events, out)
            self.assertEqual(json.loads(out.read_text())['received'], events)

    def test_missing_memory_not_silently_green(self):
        with self.assertRaises(RuntimeError):
            ops.alerts({'memory': {}, 'restarts': []}, 512)

    def test_recovery_distinct_restricted_no_api_no_network(self):
        docs = list(yaml.safe_load_all((ROOT / 'kubernetes/operations/recovery/recovery.yaml').read_text()))
        pods = [o for o in docs if o['kind'] == 'Pod']
        self.assertEqual({p['spec']['volumes'][0]['persistentVolumeClaim']['claimName'] for p in pods}, {'source', 'restored'})
        for p in pods:
            self.assertFalse(p['spec']['automountServiceAccountToken'])
            self.assertTrue(p['spec']['securityContext']['runAsNonRoot'])
            self.assertNotIn('hostNetwork', p['spec'])
            self.assertIn('@sha256:', p['spec']['containers'][0]['image'])
        policy = next(o for o in docs if o['kind'] == 'CiliumNetworkPolicy')
        self.assertEqual(policy['spec']['egress'], [])

    def test_flux_scoped_rbac_and_controller_flags(self):
        spec = importlib.util.spec_from_file_location('flux_render', ROOT / 'scripts/talos-proof-operations-flux.py')
        flux = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(flux)
        lock = json.loads((ROOT / 'kubernetes/operations/gitops/artifacts.lock.json').read_text())
        upstream = [{'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': name},
                     'spec': {'template': {'spec': {'priorityClassName': 'system-cluster-critical',
                         'containers': [{'args': ['--watch-all-namespaces', '--events-addr=unused']} ]}}}}
                    for name in lock['images']]
        raw = yaml.safe_dump_all(upstream).encode()
        lock['sha256'] = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / 'upstream.yaml'
            cache.write_bytes(raw)
            with patch.object(Path, 'read_text', return_value=json.dumps(lock)):
                docs = flux.manifest(argparse.Namespace(install_yaml=str(cache), revision='a' * 40))
        self.assertFalse(any(o['kind'] in ('ClusterRole', 'ClusterRoleBinding') for o in docs))
        for o in docs:
            if o['kind'] != 'Deployment':
                continue
            c = o['spec']['template']['spec']['containers'][0]
            self.assertIn('@sha256:', c['image'])
            self.assertIn('--watch-all-namespaces=false', c['args'])
            if o['metadata']['name'] == 'source-controller':
                self.assertFalse(any(a.startswith('--no-cross-namespace-refs') for a in c['args']))
        fixture_role = next(o for o in docs if o['kind'] == 'Role' and o['metadata']['name'] == 'fixture-only')
        self.assertEqual(fixture_role['rules'][0]['resources'], ['configmaps'])
        self.assertEqual(fixture_role['metadata']['namespace'], 'proof-operations-gitops')

    def test_fixtures_only_configmaps(self):
        for version in (1, 2):
            o = yaml.safe_load((ROOT / f'kubernetes/operations/gitops/fixture-v{version}/fixture.yaml').read_text())
            self.assertEqual(o['kind'], 'ConfigMap')
            self.assertEqual(o['data']['revision'], str(version))
            self.assertEqual(o['metadata']['namespace'], 'proof-operations-gitops')


if __name__ == '__main__':
    unittest.main()
