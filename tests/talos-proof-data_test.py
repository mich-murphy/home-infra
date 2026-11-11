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
        with tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').exists() else None) as tmp:
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
        with tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').exists() else None) as tmp:
            p = Path(tmp)
            life.credentials(p)
            (p / 'credentials.json').chmod(0o644)
            with self.assertRaises(RuntimeError):
                life.credentials(p)

    def test_no_implicit_cluster_credentials(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            life.lease('couchdb')

    def test_expired_lease_rejected(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').exists() else None) as tmp:
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

    def target_fake(self, server='https://127.0.0.1:64120', name='talos-proof', uid='node-123', insecure=False):
        def kube(*args, **kwargs):
            if args[0] == 'config':
                return json.dumps({'clusters':[{'cluster':{'server':server,'insecure-skip-tls-verify':insecure}}]})
            return json.dumps({'items':[{'metadata':{'name':name,'uid':uid,'labels':{'kubernetes.io/hostname':name}}}]})
        return kube

    def test_exact_endpoint_and_node_accepted(self):
        with patch.object(life, 'kube', side_effect=self.target_fake()):
            life.target_identity({'endpoint':life.EXPECTED_ENDPOINT, 'node_uid':'node-123'})

    def test_other_endpoint_rejected_before_node_request(self):
        for server in ('https://127.0.0.1:6443','https://production.invalid:64120','http://127.0.0.1:64120','https://localhost:64120'):
            with self.subTest(server=server), patch.object(life, 'kube', side_effect=self.target_fake(server=server)) as mock, self.assertRaises(RuntimeError):
                life.target_identity({'endpoint':life.EXPECTED_ENDPOINT,'node_uid':'node-123'})
            self.assertEqual(mock.call_count, 1)

    def test_receipt_endpoint_required(self):
        with patch.object(life, 'kube', side_effect=self.target_fake()), self.assertRaises(RuntimeError):
            life.target_identity({'node_uid':'node-123'})

    def test_node_name_uid_and_tls_verification(self):
        for params in ({'name':'other-node'}, {'uid':'replacement-node'}, {'insecure':True}):
            with self.subTest(params=params), patch.object(life, 'kube', side_effect=self.target_fake(**params)), self.assertRaises(RuntimeError):
                life.target_identity({'endpoint':life.EXPECTED_ENDPOINT,'node_uid':'node-123'})

    def test_missing_recorded_node_uid(self):
        with patch.object(life, 'kube', side_effect=self.target_fake()), self.assertRaises(RuntimeError):
            life.target_identity({'endpoint':life.EXPECTED_ENDPOINT})

    def test_symlink_private_directory_and_ancestor_rejected(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').exists() else None) as tmp:
            root = Path(tmp)
            (root / 'real').mkdir(mode=0o700)
            (root / 'link').symlink_to(root / 'real', target_is_directory=True)
            for path in (root / 'link', root / 'link' / 'nested'):
                with self.subTest(path=str(path)), self.assertRaises(RuntimeError):
                    life.private(path)

    def test_symlink_credentials_rejected_before_read(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').exists() else None) as tmp:
            root = Path(tmp)
            (root / 'actual.json').write_text('{}')
            (root / 'actual.json').chmod(0o600)
            (root / 'credentials.json').symlink_to(root / 'actual.json')
            with self.assertRaises(RuntimeError):
                life.credentials(root)

    def test_mutation_wrapper_rechecks_receipt(self):
        with patch.object(life, 'LEASE_GROUP', 'couchdb'), patch.object(life, 'lease', side_effect=RuntimeError('denied')), patch.object(life.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                life.kube('-n','proof-couchdb','scale','deployment','--all','--replicas=1')
            run.assert_not_called()

    def test_gateway_entity_ports_are_frontend_only(self):
        permitted = {'nextcloud':80,'collabora':9980,'immich':2283,'miniflux':8080,'wallabag':80,'couchdb':5984,'pocket-id':1411}
        policies = [d for d in DOCS if d['kind']=='CiliumNetworkPolicy']
        self.assertEqual(len(policies), 7)
        for d in policies:
            name = d['spec']['endpointSelector']['matchLabels']['app.kubernetes.io/name']
            self.assertIn(name, permitted)
            self.assertEqual(d['spec']['ingress'], [{'fromEntities':['ingress'], 'toPorts':[{'ports':[{'port':str(permitted[name]),'protocol':'TCP'}]}]}])

    def test_clean_pvc_failure_restores_source_binding(self):
        live_spec = importlib.util.spec_from_file_location('live',ROOT / 'tests/talos-proof-data-live.py')
        live = importlib.util.module_from_spec(live_spec)
        live_spec.loader.exec_module(live)
        live.NS = 'proof-miniflux'
        live.RESULT = {'checks':[]}
        calls = []
        def k(*args, **kwargs):
            calls.append(args)
            if args[:2] == ('get','deployment'):
                return json.dumps({'spec':{'template':{'spec':{'volumes':[{'name':'data','persistentVolumeClaim':{'claimName':'postgres-data'}}]}}}}).encode()
            if args[:2] == ('get','pvc'):
                source = args[2]=='postgres-data'
                return json.dumps({'metadata':{'uid':'source-uid' if source else 'fresh-uid'},'spec':{'accessModes':['ReadWriteOnce'],'storageClassName':'proof-local','resources':{'requests':{'storage':'4Gi'}},'volumeName':'source-pv' if source else 'fresh-pv'}}).encode()
            return b''
        with patch.object(live,'k',side_effect=k), patch.object(live,'scale') as scale:
            with self.assertRaisesRegex(RuntimeError,'synthetic failure'):
                with live.fresh_pvc('postgres',('miniflux',)):
                    raise RuntimeError('synthetic failure')
            patches = [json.loads(c[-1]) for c in calls if c[0]=='patch']
            self.assertEqual(patches[-1][0]['value'],'postgres-data')
            self.assertTrue(patches[0][0]['value'].startswith('postgres-restore-'))
            self.assertEqual(scale.call_args_list[-2].args,('postgres',1))
            self.assertEqual(scale.call_args_list[-1].args,('miniflux',1))
            self.assertEqual(live.RESULT['restore_volumes'][0]['restored_uid'],'fresh-uid')

    def test_clean_restore_rejects_nonempty_pg_cluster(self):
        live_spec = importlib.util.spec_from_file_location('live_restore',ROOT / 'tests/talos-proof-data-live.py')
        live = importlib.util.module_from_spec(live_spec)
        live_spec.loader.exec_module(live)
        live.RESULT = {'checks':[]}
        with patch.object(live,'execute',return_value=b'42\n') as execute, self.assertRaises(RuntimeError):
            live.clean_postgres_restore('miniflux',b'dump')
        self.assertEqual(execute.call_count,1)


if __name__ == '__main__':
    unittest.main()
