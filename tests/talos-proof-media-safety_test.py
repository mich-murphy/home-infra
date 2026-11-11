#!/usr/bin/env python3
"""Offline negative mutants: no test contacts or mutates the real proof API."""
import copy
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
safety = importlib.import_module('talos-proof-media-safety')
http = importlib.import_module('talos-proof-media-http')


class Safety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='talos-proof-media-safety-')
        self.state = Path(self.temp.name).resolve()
        self.receipt = {'group': 'radarr', 'context': 'fake-proof-context', 'endpoint': safety.ENDPOINT,
                        'node_uid': 'OFFLINE-FAKE-UID', 'expires': time.time() + 600,
                        'available_mib': 1800, 'measured_at': time.time()}
        self.config = {'current-context': 'fake-proof-context', 'clusters': [{'cluster': {
            'server': safety.ENDPOINT, 'certificate-authority-data': 'OFFLINE-FAKE-CA'}}]}
        self.node = {'metadata': {'name': 'talos-proof', 'uid': 'OFFLINE-FAKE-UID',
                                 'labels': {'kubernetes.io/hostname': 'talos-proof'}},
                     'status': {'allocatable': {'memory': '2400000Ki'}}}
        self.nodes = [self.node]
        self.pods, self.controllers = [], []
        self.path = safety.write_private(self.state / 'lease.json', json.dumps(self.receipt))
        self.env = patch.dict(os.environ, {'TALOS_PROOF_MEDIA_LEASE': str(self.path)})
        self.env.start()
        self.read = patch.object(safety, 'kubectl_read', side_effect=self.fake_read)
        self.read.start()

    def tearDown(self):
        self.read.stop()
        self.env.stop()
        self.temp.cleanup()

    def fake_read(self, *args):
        if args[0] == 'config':
            return json.dumps(self.config)
        if args[:2] == ('get', 'nodes'):
            return json.dumps({'items': self.nodes})
        if args[:2] == ('get', 'pods'):
            return json.dumps({'items': self.pods})
        if args[:2] == ('get', 'deployments,statefulsets'):
            return json.dumps({'items': self.controllers})
        raise AssertionError('unexpected mocked read')

    def test_failed_kube_keeps_diagnostics_private_without_changing_failure(self):
        outcome = safety.subprocess.CompletedProcess([],137,stdout=b'PRIVATE-OUT',stderr=b'PRIVATE-ERR')
        with patch.object(safety,'lease'),patch.object(safety,'exclusivity'), \
             patch.object(safety,'private_file',return_value=self.state/'kubeconfig'), \
             patch.dict(os.environ,{'KUBECONFIG':str(self.state/'kubeconfig')}), \
             patch.object(safety.subprocess,'run',return_value=outcome):
            with self.assertRaisesRegex(RuntimeError,'details withheld') as caught:
                safety.kube('pinchflat','exec','proof-pod','--','false')
        self.assertEqual(caught.exception.private_stdout,b'PRIVATE-OUT')
        self.assertEqual(caught.exception.private_stderr,b'PRIVATE-ERR')
        self.assertNotIn('PRIVATE',str(caught.exception))

    def rewrite_receipt(self):
        safety.write_private(self.path, json.dumps(self.receipt), replace=True)

    def test_pinchflat_optional_profile_requires_marker_and_full_576(self):
        self.receipt.update(group='pinchflat',provider_fixture='pinchflat-rss',available_mib=575)
        self.rewrite_receipt()
        with self.assertRaisesRegex(RuntimeError,'insufficient'):
            safety.pinchflat_provider_guard()
        self.receipt['available_mib']=576;self.rewrite_receipt()
        safety.pinchflat_provider_guard()
        self.controllers=[{'metadata':{'namespace':'proof-pinchflat','name':'pinchflat'},'spec':{'replicas':0,'template':{
            'metadata':{'annotations':{'talos-proof.home/provider-fixture':'pinchflat-rss'}},
            'spec':{'containers':[{'name':'pinchflat'},{'name':'rss-fixture'}]}}}}]
        safety.guard('pinchflat')
        self.receipt.pop('provider_fixture');self.rewrite_receipt()
        with self.assertRaisesRegex(RuntimeError,'exact parent receipt'):
            safety.guard('pinchflat')

    def test_wrong_or_inconsistent_provider_profile_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'exact pinchflat group'):
            safety.guard('radarr',provider_selected=True)
        self.receipt.update(group='pinchflat',provider_fixture='WRONG');self.rewrite_receipt()
        with self.assertRaisesRegex(RuntimeError,'authorize'):
            safety.pinchflat_provider_guard()
        self.receipt['provider_fixture']='pinchflat-rss';self.rewrite_receipt()
        for annotation,names in [('unknown',['pinchflat','rss-fixture']),('pinchflat-rss',['pinchflat'])]:
            self.controllers=[{'metadata':{'namespace':'proof-pinchflat','name':'pinchflat'},'spec':{'replicas':0,'template':{
                'metadata':{'annotations':{'talos-proof.home/provider-fixture':annotation}},
                'spec':{'containers':[{'name':name} for name in names]}}}}]
            with self.assertRaisesRegex(RuntimeError,'inconsistent'):
                safety.guard('pinchflat')

    def test_valid_fake_receipt(self):
        safety.guard('radarr')

    def test_wrong_server_tls_context_node_mutants(self):
        mutations = [
            lambda: self.config['clusters'][0]['cluster'].update(server='https://production.invalid:6443'),
            lambda: self.config['clusters'][0]['cluster'].update(server='http://127.0.0.1:64120'),
            lambda: self.config['clusters'][0]['cluster'].update(**{'insecure-skip-tls-verify': True}),
            lambda: self.config.update(**{'current-context': 'production'}),
            lambda: self.node['metadata'].update(name='production'),
            lambda: self.node['metadata']['labels'].update(**{'kubernetes.io/hostname': 'random-host'}),
            lambda: self.node['metadata'].update(uid='CHANGED-UID'),
            lambda: self.nodes.append(copy.deepcopy(self.node)),
            lambda: self.config.update(users=[{'user': {'exec': {'command': 'evil'}}}]),
        ]
        pristine_config, pristine_node = copy.deepcopy(self.config), copy.deepcopy(self.node)
        for mutate in mutations:
            self.config, self.node = copy.deepcopy(pristine_config), copy.deepcopy(pristine_node)
            self.nodes = [self.node]
            mutate()
            with self.assertRaises(RuntimeError), patch.object(safety.subprocess, 'run') as execution:
                safety.kube('radarr', 'apply', '-f', '-')
            execution.assert_not_called()

    def test_invalid_receipt_mutants(self):
        for field, value in [('endpoint', 'https://production.invalid'), ('group', 'immich'), ('node_uid', ''),
                             ('expires', 0), ('expires', float('nan')), ('context', 'wrong')]:
            saved = self.receipt[field]
            self.receipt[field] = value
            self.rewrite_receipt()
            with self.assertRaises(RuntimeError):
                safety.lease('radarr')
            self.receipt[field] = saved
        self.rewrite_receipt()

    def test_data_and_unlabelled_other_groups_excluded(self):
        for namespace in ['proof-immich', 'proof-nextcloud', 'proof-jellyfin', 'proof-unknown']:
            self.pods = [{'metadata': {'namespace': namespace}, 'status': {'phase': 'Pending'}}]
            with self.assertRaises(RuntimeError):
                safety.exclusivity('radarr')
        self.pods = []
        self.controllers = [{'metadata': {'namespace': 'proof-wallabag'}, 'spec': {'replicas': 1}}]
        with self.assertRaises(RuntimeError):
            safety.exclusivity('radarr')

    def test_stale_or_insufficient_memory(self):
        for field, value in [('measured_at', 0), ('measured_at', time.time() + 300),
                             ('available_mib', 500), ('available_mib', 999999), ('available_mib', -1)]:
            saved = self.receipt[field]
            self.receipt[field] = value
            self.rewrite_receipt()
            with self.assertRaises(RuntimeError):
                safety.guard('radarr')
            self.receipt[field] = saved

    def test_recovery_budget_only_when_every_service_controller_and_pod_stopped(self):
        safety.guard('radarr', budget_mib=128)
        self.controllers = [{'metadata': {'namespace': 'proof-radarr', 'name': 'radarr'}, 'spec': {'replicas': 1}}]
        with self.assertRaises(RuntimeError):
            safety.guard('radarr', budget_mib=128)
        self.controllers = []
        self.pods = [{'metadata': {'namespace': 'proof-radarr'}, 'status': {'phase': 'Pending'}}]
        with self.assertRaises(RuntimeError):
            safety.guard('radarr', budget_mib=128)
        self.pods = []
        with self.assertRaises(RuntimeError):
            safety.guard('radarr', budget_mib=1)

    def test_symlink_and_modes_rejected(self):
        link = self.state / 'link'
        link.symlink_to(self.path)
        with self.assertRaises(RuntimeError):
            safety.read_private(link)
        directory_link = self.state / 'dirlink'
        directory_link.symlink_to(self.state, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            safety.private_file(directory_link / 'lease.json')
        self.path.chmod(0o644)
        with self.assertRaises(RuntimeError):
            safety.read_private(self.path)
        self.state.chmod(0o755)
        with self.assertRaises(RuntimeError):
            safety.private_dir(self.state)

    def test_untrusted_http_targets_rejected(self):
        for base in ['http://127.0.0.1:8080', 'https://production.invalid:18443',
                     'https://radarr.proof.invalid:443', 'https://user:pass@radarr.proof.invalid:18443',
                     'https://radarr.proof.invalid:18443?token=secret']:
            with self.assertRaises((ValueError, FileNotFoundError)):
                http.API(base, service='radarr', ca='/nonexistent')


if __name__ == '__main__':
    unittest.main()
