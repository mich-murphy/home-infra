#!/usr/bin/env python3
"""Offline tests only; never connect to a cluster."""
import argparse
import hashlib
import importlib.util
import json
import copy
import os
import time
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
    def identity_fixture(self, directory):
        state = Path(directory)
        config = state / 'kubeconfig'
        config.write_text('private fixture')
        config.chmod(0o600)
        receipt = state / 'lease.json'
        receipt.write_text(json.dumps({'group': 'operations', 'context': 'proof',
            'endpoint': ops.ENDPOINT, 'node_uid': ops.NODE_UID, 'expires': time.time() + 600,
            'available_mib': 1200, 'measured_at': time.time()}))
        receipt.chmod(0o600)
        cfg = {'current-context': 'proof', 'contexts': [{'name': 'proof', 'context': {'cluster': 'proof', 'user': 'proof'}}],
               'clusters': [{'name': 'proof', 'cluster': {'server': ops.ENDPOINT}}],
               'users': [{'name': 'proof', 'user': {}}]}
        node = {'metadata': {'name': 'talos-proof', 'uid': ops.NODE_UID,
                'labels': {'kubernetes.io/hostname': 'talos-proof'}},
                'status': {'addresses': [{'type': 'InternalIP', 'address': '172.31.250.10'}]}}
        return config, receipt, cfg, node

    def test_identity_mutants_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
            config, receipt, cfg, node = self.identity_fixture(d)
            mutants = [('server', 'https://production.invalid'), ('tls', True), ('context', 'production'),
                       ('cluster', 'wrong'), ('uid', 'wrong'), ('name', 'other'), ('hostname', 'other'),
                       ('ip', '10.0.0.1'), ('count', 2), ('proxy', 'http://localhost:8080'), ('exec', {'command': 'arbitrary'}), ('user', 'wrong')]
            with patch.object(ops, 'STATE', Path(d)), patch.dict(os.environ, {
                    'KUBECONFIG': str(config), 'TALOS_PROOF_OPERATIONS_LEASE': str(receipt)}):
                for kind, val in mutants:
                    c, n = copy.deepcopy(cfg), copy.deepcopy(node)
                    if kind == 'exec': c['users'][0]['user']['exec'] = val
                    if kind == 'user': c['contexts'][0]['context']['user'] = val
                    if kind == 'server': c['clusters'][0]['cluster']['server'] = val
                    if kind == 'tls': c['clusters'][0]['cluster']['insecure-skip-tls-verify'] = val
                    if kind == 'proxy': c['clusters'][0]['cluster']['proxy-url'] = val
                    if kind == 'context': c['current-context'] = val
                    if kind == 'cluster': c['contexts'][0]['context']['cluster'] = val
                    if kind in ('uid', 'name'): n['metadata'][kind] = val
                    if kind == 'hostname': n['metadata']['labels']['kubernetes.io/hostname'] = val
                    if kind == 'ip': n['status']['addresses'][0]['address'] = val
                    with self.subTest(kind=kind), patch.object(ops, 'raw_kube', side_effect=[
                            json.dumps(c), json.dumps({'items': [n] * (val if kind == 'count' else 1)})]):
                        with self.assertRaises(RuntimeError): ops.gate()
                with patch.object(ops, 'raw_kube', side_effect=[json.dumps(cfg), json.dumps({'items': [node]})]):
                    self.assertEqual(ops.gate()['metadata']['uid'], ops.NODE_UID)
                # Consistently wrong config AND matching receipt context/endpoint still fails.
                r = json.loads(receipt.read_text()); r.update(context='production', endpoint='https://production.invalid')
                receipt.write_text(json.dumps(r))
                with patch.object(ops, 'raw_kube') as raw:
                    with self.assertRaises(RuntimeError): ops.gate()
                    raw.assert_not_called()

    def test_receipt_and_private_path_mutants(self):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
            config, receipt, cfg, node = self.identity_fixture(d)
            original = json.loads(receipt.read_text())
            with patch.object(ops, 'STATE', Path(d)), patch.dict(os.environ, {
                    'KUBECONFIG': str(config), 'TALOS_PROOF_OPERATIONS_LEASE': str(receipt)}):
                for key, val in [('group', 'media'), ('expires', 0), ('node_uid', 'other'),
                                 ('measured_at', 0), ('available_mib', 0)]:
                    receipt.write_text(json.dumps({**original, key: val}))
                    with self.subTest(key=key), self.assertRaises(RuntimeError): ops.gate()
                receipt.write_text(json.dumps(original)); receipt.chmod(0o644)
                with self.assertRaises(RuntimeError): ops.gate()
                receipt.chmod(0o600)
                link = Path(d) / 'link'; link.symlink_to(config)
                with self.assertRaises(RuntimeError): ops.private_file(link)
                ancestor = Path(d) / 'linked-dir'; ancestor.symlink_to(d, target_is_directory=True)
                with self.assertRaises(RuntimeError): ops.private_file(ancestor / 'kubeconfig')

    def test_every_mutation_exec_and_cleanup_regates(self):
        for args in [('apply', '-f', '-'), ('exec', 'source', '--', 'true'), ('delete', 'pod', 'source'),
                     ('patch', 'configmap', 'fixture'), ('get', 'pods')]:
            with self.subTest(args=args), patch.object(ops, 'gate', side_effect=RuntimeError('expired')), \
                    patch.object(ops, 'raw_kube') as raw:
                with self.assertRaises(RuntimeError): ops.kube(*args)
                raw.assert_not_called()

    def test_recovery_refuses_existing_namespace_without_mutation(self):
        with patch.object(ops, 'obj', return_value={'items': [{'metadata': {'name': ops.NS}}]}), \
                patch.object(ops, 'kube') as kube:
            with self.assertRaises(RuntimeError): ops.recovery(Path('/unused'))
            kube.assert_not_called()

    def test_recovery_partial_apply_cleans_pods_not_pvcs(self):
        calls = []
        def kube(*args, **kwargs):
            calls.append(args)
            if args[0] == 'apply': raise RuntimeError('partial apply')
        with patch.object(ops, 'obj', return_value={'items': []}), patch.object(ops, 'kube', side_effect=kube):
            with self.assertRaises(RuntimeError): ops.recovery(Path('/unused'))
        self.assertEqual(calls[-1][2:4], ('delete', 'pod'))
        self.assertFalse(any('pvc' in c or 'pv' in c for c in calls))


    def recovery_fixture(self, out, mutant=None):
        claims = [{'metadata': {'name': name, 'uid': name + '-uid'}, 'spec': {'volumeName': name + '-pv'}}
                  for name in ('source', 'restored')]
        if mutant == 'same-pv': claims[1]['spec']['volumeName'] = 'source-pv'
        if mutant == 'same-uid': claims[1]['metadata']['uid'] = 'source-uid'
        calls = []
        def obj(*args):
            if args[:2] == ('get', 'namespaces'): return {'items': []}
            if 'pods' in args: return {'items': [{'metadata': {'name': 'source'},
                'status': {'containerStatuses': [{'name': 'fixture', 'image': 'pinned-image',
                    'imageID': 'digest-fixture', 'restartCount': 0}]}}]}
            if 'pvc' in args: return {'items': claims}
            if 'pv' in args:
                name = args[2].removesuffix('-pv')
                return {'spec': {'persistentVolumeReclaimPolicy': 'Delete' if mutant == 'delete-pv' else 'Retain',
                                 'claimRef': {'uid': name + '-uid'}}}
            raise AssertionError(args)
        def kube(*args, **kw):
            calls.append(args)
            if mutant == 'nonempty' and 'test -z "$(ls -A /data)"' in args:
                raise RuntimeError('nonempty')
            if 'tar' in args and '-cf' in args: kw['stdout'].write(b'archive fixture')
            if args[-2:] == ('cat', '/data/fixture.txt'):
                return b'talos-proof isolated off-node recovery fixture v1\n'
            return b''
        return calls, obj, kube

    def test_recovery_mutants_and_retained_cleanup(self):
        for mutant in ('same-pv', 'same-uid', 'delete-pv', 'nonempty'):
            with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
                calls, obj, kube = self.recovery_fixture(Path(d), mutant)
                with self.subTest(mutant=mutant), patch.object(ops, 'obj', side_effect=obj), \
                        patch.object(ops, 'kube', side_effect=kube):
                    with self.assertRaises(RuntimeError): ops.recovery(Path(d))
                self.assertIn('delete', calls[-1]); self.assertIn('pod', calls[-1])
                self.assertFalse(any('cat > /data/fixture.txt' in ' '.join(c) for c in calls))
                self.assertFalse(any('pvc' in c or 'pv' in c for c in calls))

    def test_recovery_success_no_overwrite_source_deleted_before_restore(self):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
            out = Path(d)
            calls, obj, kube = self.recovery_fixture(out)
            with patch.object(ops, 'obj', side_effect=obj), patch.object(ops, 'kube', side_effect=kube):
                ops.recovery(out)
            metadata = json.loads((out / 'recovery.json').read_text())
            self.assertTrue(metadata['retained_pvs']); self.assertTrue(metadata['restored_checksum_matches'])
            self.assertTrue(metadata['source_empty_before_write'])
            self.assertTrue(metadata['destination_empty_before_restore'])
            self.assertEqual(metadata['runtime_images'][0]['containers'][0]['imageID'], 'digest-fixture')
            deletion = next(i for i,c in enumerate(calls) if 'delete' in c)
            extraction = next(i for i,c in enumerate(calls) if '-xkf' in c)
            self.assertLess(deletion, extraction)
            self.assertTrue(any('set -C; cat > /data/fixture.txt' in c for c in calls))
            self.assertEqual(calls[-1][2:6], ('delete', 'pod', 'source', 'restored'))
            # Existing workstation archive is not overwritten, even in otherwise clean cluster.
            calls, obj, kube = self.recovery_fixture(out)
            with patch.object(ops, 'obj', side_effect=obj), patch.object(ops, 'kube', side_effect=kube):
                with self.assertRaises(FileExistsError): ops.recovery(out)
            self.assertEqual((out / 'fixture.tar').read_bytes(), b'archive fixture')

    def test_snapshot_fixed_target_binary_version_and_config(self):
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
            state = Path(d); (state / 'bin').mkdir()
            binary = state / 'bin/talosctl'; binary.write_text('test fixture not executed'); binary.chmod(0o700)
            config = state / 'talosconfig'
            good = {'context': 'proof', 'contexts': {'proof': {'endpoints': ['127.0.0.1:50120'], 'nodes': ['172.31.250.10']}}}
            config.write_text(yaml.safe_dump(good)); config.chmod(0o600)
            out = state / 'out'; out.mkdir()
            calls = []
            def run(args, **kw):
                calls.append(args)
                if 'version' in args: return b'Client: v1.14.5\n'
                Path(args[-1]).write_bytes(b'private snapshot fixture')
            with patch.object(ops, 'STATE', state), patch.dict(os.environ, {'TALOSCONFIG': str(config)}), \
                    patch.object(ops, 'gate'), patch.object(ops, 'run', side_effect=run):
                ops.snapshot(out)
                self.assertEqual(calls[-1][0], str(binary))
                self.assertIn('127.0.0.1:50120', calls[-1]); self.assertIn('172.31.250.10', calls[-1])
                self.assertFalse(json.loads((out / 'snapshot.json').read_text())['restore_tested'])
                with self.assertRaises(RuntimeError): ops.snapshot(out)
                config.write_text(yaml.safe_dump({'context': 'prod', 'contexts': {'prod': {
                    'endpoints': ['production.invalid'], 'nodes': ['10.0.0.1']}}}))
                with self.assertRaises(RuntimeError): ops.snapshot(out)
                config.write_text(yaml.safe_dump(good))
                with patch.object(ops, 'run', return_value=b'Client: v1.14.4'):
                    with self.assertRaises(RuntimeError): ops.snapshot(out)


    def test_flux_partial_cleanup_and_lease_denial(self):
        spec = importlib.util.spec_from_file_location('flux_guard_test', ROOT / 'scripts/talos-proof-operations-flux.py')
        flux = importlib.util.module_from_spec(spec); spec.loader.exec_module(flux)
        from unittest.mock import Mock
        denied = Mock(); denied.gate.side_effect = RuntimeError('no lease')
        with patch.object(flux, 'operations', return_value=denied):
            with self.assertRaises(RuntimeError): flux.live(argparse.Namespace(action='run'))
        denied.kube.assert_not_called()
        partial = Mock(); partial.kube.side_effect = [RuntimeError('no Kustomization yet'), b'']
        with self.assertRaises(RuntimeError): flux.cleanup(partial)
        self.assertEqual(partial.kube.call_count, 2)
        self.assertIn('delete', partial.kube.call_args.args)
        self.assertIn('deployment', partial.kube.call_args.args)
        self.assertNotIn('namespace', partial.kube.call_args.args)
        self.assertNotIn('crd', partial.kube.call_args.args)


    def test_flux_low_headroom_refuses_before_apply(self):
        spec = importlib.util.spec_from_file_location('flux_admission_test', ROOT / 'scripts/talos-proof-operations-flux.py')
        flux = importlib.util.module_from_spec(spec); spec.loader.exec_module(flux)
        from unittest.mock import Mock
        for available in (0, 710 * 1024**2, 896 * 1024**2 - 1):
            with tempfile.TemporaryDirectory() as d:
                guarded = Mock()
                guarded.private_dir.return_value = Path(d)
                guarded.obj.return_value = {'node': {'memory': {'availableBytes': available}}}
                with patch.object(flux, 'operations', return_value=guarded):
                    with self.assertRaisesRegex(RuntimeError, '384Mi'):
                        flux.live(argparse.Namespace(action='run', revision='a' * 40))
                guarded.kube.assert_not_called()
                evidence = json.loads((Path(d) / 'flux-admission.json').read_text())
                self.assertFalse(evidence['admitted'])
                self.assertEqual(evidence['available_bytes'], available)

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
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
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
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as d:
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
