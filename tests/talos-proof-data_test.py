#!/usr/bin/env python3
"""Offline contract tests. No cluster access or production data."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle', ROOT / 'scripts/talos-proof-data.py')
life = importlib.util.module_from_spec(spec)
spec.loader.exec_module(life)
DOCS = list(yaml.safe_load_all(subprocess.check_output(['kubectl', 'kustomize', str(ROOT / 'kubernetes/apps/data')], text=True)))


class DataContract(unittest.TestCase):
    def test_parent_safety_validator(self):
        render = yaml.safe_dump_all(DOCS)
        subprocess.run(['python3', str(ROOT / 'tests/kubernetes-proof.py')], input=render, text=True, check=True, capture_output=True)

    def test_exact_trust_namespaces(self):
        self.assertEqual({d['metadata']['name'] for d in DOCS if d['kind'] == 'Namespace'}, {'proof-' + g for g in life.GROUPS})

    def test_current_images_only(self):
        current = set()
        for g in life.GROUPS:
            p = ROOT / 'docker' / ('init' if g == 'pocket-id' else g) / 'compose.yml'
            current.update(s['image'] for s in yaml.safe_load(p.read_text())['services'].values())
        for d in DOCS:
            if d['kind'] == 'Deployment':
                for c in d['spec']['template']['spec']['containers']:
                    self.assertIn(c['image'], current)
                    self.assertNotIn('owncloud', c['image'])

    def test_immich_v3_mount(self):
        d = next(d for d in DOCS if d['kind'] == 'Deployment' and d['metadata']['name'] == 'immich')
        self.assertEqual(d['spec']['template']['spec']['containers'][0]['volumeMounts'][0]['mountPath'], '/data')

    def test_postgres18_mount(self):
        for d in DOCS:
            if d['kind'] == 'Deployment' and d['metadata']['name'] == 'postgres' and d['metadata']['namespace'] in ('proof-nextcloud', 'proof-miniflux'):
                self.assertEqual(d['spec']['template']['spec']['containers'][0]['volumeMounts'][0]['mountPath'], '/var/lib/postgresql')

    def test_every_namespace_default_denied(self):
        for g in life.GROUPS:
            p = next(d for d in DOCS if d['kind'] == 'NetworkPolicy' and d['metadata']['name'] == 'default-deny' and d['metadata']['namespace'] == 'proof-' + g)
            self.assertEqual(p['spec']['podSelector'], {})
            self.assertEqual(set(p['spec']['policyTypes']), {'Ingress', 'Egress'})
            self.assertNotIn('ingress', p['spec'])
            self.assertNotIn('egress', p['spec'])

    def test_memory_budgets_match_render(self):
        for g, budget in life.BUDGET.items():
            actual = sum(int(c['resources']['limits']['memory'][:-2]) for d in DOCS if d['kind'] == 'Deployment' and d['metadata']['namespace'] == 'proof-' + g for c in d['spec']['template']['spec']['containers'])
            self.assertEqual(actual, budget, g)

    def test_no_committed_secret(self):
        self.assertFalse(any(d['kind'] == 'Secret' for d in DOCS))

    def test_fresh_private_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            a = life.credentials(p)
            self.assertEqual(stat.S_IMODE((p / 'credentials.json').stat().st_mode), 0o600)
            self.assertEqual(a, life.credentials(p))
            self.assertEqual(set(a), set(life.GROUPS))
            self.assertNotEqual(a['nextcloud']['POSTGRES_PASSWORD'], a['immich']['POSTGRES_PASSWORD'])
            self.assertNotEqual(a['nextcloud']['POSTGRES_PASSWORD'], a['nextcloud']['NEXTCLOUD_ADMIN_PASSWORD'])

    def test_reject_repository_private_state(self):
        with self.assertRaises(RuntimeError):
            life.private(ROOT / 'private-state-must-not-exist')

    def test_reject_world_readable_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            life.credentials(p)
            (p / 'credentials.json').chmod(0o644)
            with self.assertRaises(RuntimeError):
                life.credentials(p)

    def test_no_implicit_cluster_credentials(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            life.lease('couchdb')

    def test_expired_lease_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'lease.json'
            p.write_text(json.dumps({'group':'couchdb','context':'proof','expires':time.time()-1}))
            with patch.dict(os.environ, {'KUBECONFIG':'fake','TALOS_PROOF_DATA_LEASE':str(p)}), patch.object(life, 'kube', return_value='proof\n'), self.assertRaises(RuntimeError):
                life.lease('couchdb')

    def test_guard_rejects_stale_memory(self):
        def kube(*args, **kwargs):
            if args[1] == 'pods':
                return '{"items":[]}'
            if args[1] == 'nodes':
                return '{"items":[{"status":{"allocatable":{"memory":"2400000Ki"}}}]}'
            raise RuntimeError('metrics unavailable')
        with patch.object(life, 'kube', side_effect=kube), patch.object(life, 'lease', return_value={'measured_at':0,'available_mib':2000}), self.assertRaises(RuntimeError):
            life.guard('couchdb')

    def test_guard_rejects_over_budget(self):
        def kube(*args, **kwargs):
            if args[1] == 'pods':
                return '{"items":[]}'
            if args[1] == 'nodes':
                return '{"items":[{"status":{"allocatable":{"memory":"2400000Ki"}}}]}'
            raise RuntimeError('metrics unavailable')
        with patch.object(life, 'kube', side_effect=kube), patch.object(life, 'lease', return_value={'measured_at':time.time(),'available_mib':1000}), self.assertRaises(RuntimeError):
            life.guard('immich')


if __name__ == '__main__':
    unittest.main()
