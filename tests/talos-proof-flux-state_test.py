#!/usr/bin/env python3
"""Offline fixtures only; no cluster, private files, or runtime operations."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('flux_state', ROOT / 'scripts/talos-proof-flux-state.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
GIT = 'source.toolkit.fluxcd.io/v1/gitrepositories'
KUST = 'kustomize.toolkit.fluxcd.io/v1/kustomizations'
DEPLOY = 'apps/v1/deployments'
POD = 'core/v1/pods'


def uid(number):
    return f'00000000-0000-0000-0000-{number:012x}'


def obj(gvr, kind, name, number, spec=None, namespace='proof-operations-system'):
    group, version, _ = gvr.split('/')
    return {'apiVersion': version if group == 'core' else group + '/' + version,
            'kind': kind, 'metadata': {'name': name, 'namespace': namespace, 'uid': uid(number)},
            'spec': {} if spec is None else spec}


def identity(gvr, resource, native=False):
    result = {'gvr': gvr, 'kind': resource['kind'],
              **{k: resource['metadata'][k] for k in ('namespace', 'name', 'uid')}}
    if native:
        bound = {'spec': resource['spec'], 'ownerReferences': resource['metadata'].get('ownerReferences', [])}
        result['execution_sha256'] = hashlib.sha256(json.dumps(
            bound, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    return result


def capture(items, scope='all-namespaces'):
    return {'status': 'success', 'complete': True, 'scope': scope,
            'list': {'apiVersion': 'v1', 'kind': 'List', 'metadata': {}, 'items': items}}


def crd(gvr, kind, number):
    group, version, plural = gvr.split('/')
    return {'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition',
            'metadata': {'name': plural + '.' + group, 'uid': uid(number)},
            'spec': {'group': group, 'scope': 'Namespaced', 'names': {'plural': plural, 'kind': kind},
                     'versions': [{'name': version, 'served': True, 'storage': True}]}}


def fixture():
    git = obj(GIT, 'GitRepository', 'proof-fixture', 1)
    kust = obj(KUST, 'Kustomization', 'proof-fixture', 2, {'suspend': True})
    platform = obj(DEPLOY, 'Deployment', 'coredns', 3,
                   {'replicas': 2, 'template': {'spec': {'containers': [{'name': 'dns', 'image': 'dns:v1'}]}}},
                   'kube-system')
    pod = obj(POD, 'Pod', 'coredns-abc', 4,
              {'containers': [{'name': 'dns', 'image': 'dns:v1'}]}, 'kube-system')
    pod['metadata']['ownerReferences'] = [dict(apiVersion='apps/v1', kind='Deployment',
                                             name='coredns', uid=uid(3), controller=True)]
    native = {gvr: [] for gvr in m.NATIVE_GVRS}
    native[DEPLOY] = [platform]; native[POD] = [pod]
    return {'schema_version': 1,
            'baseline': {'flux': [identity(GIT, git), identity(KUST, kust)],
                         'native': [identity(DEPLOY, platform, True), identity(POD, pod, True)]},
            'captures': {'crds': capture([crd(GIT, 'GitRepository', 100), crd(KUST, 'Kustomization', 101)], 'cluster'),
                         'flux': [{'gvr': GIT, 'capture': capture([git])},
                                  {'gvr': KUST, 'capture': capture([kust])}],
                         'native': [{'gvr': gvr, 'capture': capture(items)} for gvr, items in native.items()]}}


def records(bundle, group, gvr):
    return next(r['capture'] for r in bundle['captures'][group] if r['gvr'] == gvr)


def resource(bundle, group, gvr):
    return records(bundle, group, gvr)['list']['items'][0]


def codes(report, category):
    return {x['code'] for x in report[category]}


class FluxStateTests(unittest.TestCase):
    def test_inert_git_missing_false_true_and_kustomization_true(self):
        for state in ('absent', False, True):
            with self.subTest(state=state):
                b = fixture()
                if state != 'absent':
                    resource(b, 'flux', GIT)['spec']['suspend'] = state
                report = m.evaluate(b)
                self.assertEqual(report['status'], 'OK')
                self.assertTrue(report['complete'])
                expected = ('FETCH_INTENT_SUSPENDED' if state is True else
                            'FETCH_INTENT_CONDITIONALLY_INERT_NOT_DURABLY_SUSPENDED')
                self.assertIn(expected, codes(report, 'observations'))
                self.assertIn('APPLY_INTENT_SUSPENDED', codes(report, 'observations'))
                self.assertTrue(report['offline_only'])
                self.assertFalse(report['runtime_authorization'])

    def test_kustomization_false_and_absent_are_typed_blocking(self):
        for absent in (False, True):
            b = fixture()
            spec = resource(b, 'flux', KUST)['spec']
            if absent:
                spec.pop('suspend')
            else:
                spec['suspend'] = False
            report = m.evaluate(b)
            self.assertEqual(report['status'], 'BLOCKED')
            self.assertIn('APPLY_INTENT_NOT_SUSPENDED', codes(report, 'blocked'))
            self.assertTrue(report['complete'])

    def test_native_flux_machinery_any_namespace_terminal_and_terminating(self):
        for gvr, kind in ((DEPLOY, 'Deployment'), (POD, 'Pod')):
            for phase in ('Running', 'Succeeded', 'Failed'):
                for terminating in (False, True):
                    with self.subTest(gvr=gvr, phase=phase, terminating=terminating):
                        b = fixture()
                        machine = obj(gvr, kind, 'source-controller-abc', 15,
                                      {'containers': [{'name': 'controller', 'image': 'ghcr.io/fluxcd/source-controller:v1'}]},
                                      'elsewhere')
                        machine['status'] = {'phase': phase}
                        if terminating:
                            machine['metadata']['deletionTimestamp'] = '2026-01-01T00:00:00Z'
                        records(b, 'native', gvr)['list']['items'].append(machine)
                        # A declared exception cannot bless recognizable Flux machinery.
                        b['baseline']['native'].append(identity(gvr, machine, True))
                        report = m.evaluate(b)
                        self.assertEqual(report['status'], 'BLOCKED')
                        self.assertIn('FLUX_MACHINERY_PRESENT', codes(report, 'blocked'))
                        self.assertIn('FETCH_INERTNESS_UNCONFIRMED', codes(report, 'gaps'))

    def test_flux_image_or_owner_even_with_unrelated_name(self):
        for mechanism in ('image', 'owner', 'label'):
            b = fixture()
            p = resource(b, 'native', POD)
            if mechanism == 'image':
                p['spec']['containers'][0]['image'] = 'registry.example/fluxcd/helm-controller@sha256:abc'
            elif mechanism == 'owner':
                p['metadata']['ownerReferences'][0]['name'] = 'kustomize-controller-abc'
            else:
                p['metadata']['labels'] = {'app.kubernetes.io/name': 'source-controller'}
            report = m.evaluate(b)
            self.assertIn('FLUX_MACHINERY_PRESENT', codes(report, 'blocked'))

    def test_registry_port_flux_image_with_innocuous_metadata_and_matching_baseline(self):
        for image in ('registry.example:5000/fluxcd/source-controller:tag',
                      'registry.example:5000/fluxcd/source-controller@sha256:abc'):
            b = fixture()
            pod = resource(b, 'native', POD)
            pod['spec']['containers'][0]['image'] = image
            b['baseline']['native'][1] = identity(POD, pod, True)
            report = m.evaluate(b)
            self.assertEqual(report['status'], 'BLOCKED')
            self.assertIn('FLUX_MACHINERY_PRESENT', codes(report, 'blocked'))
            self.assertIn('FETCH_INERTNESS_UNCONFIRMED', codes(report, 'gaps'))

    def test_malformed_consumed_native_shapes_keep_other_findings(self):
        mutations = (
            lambda p: p.update(spec=None),
            lambda p: p['spec'].update(containers=None),
            lambda p: p['spec'].update(containers={}),
            lambda p: p['spec'].update(containers=[None]),
            lambda p: p['spec']['containers'][0].update(name=[]),
            lambda p: p['spec']['containers'][0].update(image={}),
            lambda p: p['spec'].update(initContainers='not-a-list'),
            lambda p: p['spec'].update(ephemeralContainers=[{'name': 'x', 'image': None}]),
            lambda p: p['metadata'].update(ownerReferences=None),
            lambda p: p['metadata'].update(ownerReferences=[None]),
            lambda p: p['metadata']['ownerReferences'][0].update(kind=[]),
            lambda p: p['metadata']['ownerReferences'][0].update(uid={}),
            lambda p: p['metadata']['ownerReferences'][0].update(controller='true'),
            lambda p: p['metadata']['ownerReferences'][0].update(apiVersion=None),
            lambda p: p['metadata'].update(labels=[]),
            lambda p: p['metadata'].update(labels={'app': []}),
        )
        for mutate in mutations:
            b = fixture(); pod = resource(b, 'native', POD); mutate(pod)
            # Bind the malformed content to prove a matching digest is insufficient.
            b['baseline']['native'][1] = identity(POD, pod, True)
            resource(b, 'flux', KUST)['spec']['suspend'] = False
            report = m.evaluate(b)
            self.assertIn('NATIVE_OBJECT_MALFORMED', codes(report, 'gaps'))
            self.assertIn('FETCH_INERTNESS_UNCONFIRMED', codes(report, 'gaps'))
            self.assertIn('APPLY_INTENT_NOT_SUSPENDED', codes(report, 'blocked'))
        for bad in (None, [], 'secret', 1, True):
            b = fixture(); deployment = resource(b, 'native', DEPLOY)
            deployment['spec']['template'] = bad
            b['baseline']['native'][0] = identity(DEPLOY, deployment, True)
            self.assertIn('NATIVE_OBJECT_MALFORMED', codes(m.evaluate(b), 'gaps'))
            cron = obj('batch/v1/cronjobs', 'CronJob', 'maintenance', 45, {'jobTemplate': bad}, 'elsewhere')
            records(b, 'native', 'batch/v1/cronjobs')['list']['items'] = [cron]
            self.assertIn('NATIVE_OBJECT_MALFORMED', codes(m.evaluate(b), 'gaps'))

    def test_unknown_unbound_native_or_modified_exception_is_incomplete(self):
        for variant in ('unbound', 'spec', 'owner', 'uid', 'namespace', 'baseline-missing'):
            with self.subTest(variant=variant):
                b = fixture()
                p = resource(b, 'native', POD)
                if variant == 'unbound':
                    records(b, 'native', POD)['list']['items'].append(obj(POD, 'Pod', 'unreviewed', 20))
                elif variant == 'spec':
                    p['spec']['containers'][0]['image'] = 'unreviewed:v2'
                elif variant == 'owner':
                    p['metadata']['ownerReferences'][0]['uid'] = uid(21)
                elif variant == 'uid':
                    p['metadata']['uid'] = uid(21)
                elif variant == 'namespace':
                    p['metadata']['namespace'] = 'elsewhere'
                else:
                    records(b, 'native', POD)['list']['items'] = []
                report = m.evaluate(b)
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertIn('FETCH_INERTNESS_UNCONFIRMED', codes(report, 'gaps'))

    def test_missing_later_kustomization_list_is_not_empty_or_inferred(self):
        b = fixture()
        b['captures']['flux'].pop()
        report = m.evaluate(b)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertIn('LIST_MISSING', codes(report, 'gaps'))
        self.assertIn('EXPECTED_OBJECT_MISSING', codes(report, 'gaps'))
        self.assertNotIn('APPLY_INTENT_SUSPENDED', codes(report, 'observations'))
        self.assertIn('SUSPEND_FIELD_ABSENT', codes(report, 'observations'))
        self.assertIn('FETCH_INTENT_CONDITIONALLY_INERT_NOT_DURABLY_SUSPENDED',
                      codes(report, 'observations'))

    def test_every_native_gvr_is_required(self):
        for gvr in m.NATIVE_GVRS:
            b = fixture()
            b['captures']['native'] = [r for r in b['captures']['native'] if r['gvr'] != gvr]
            report = m.evaluate(b)
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertIn('FETCH_INERTNESS_UNCONFIRMED', codes(report, 'gaps'))

    def test_failed_missing_partial_paginated_malformed_captures(self):
        variants = [
            ('status', 'failed', 'LIST_FAILED'), ('status', 'missing', 'LIST_MISSING'),
            ('complete', False, 'LIST_PARTIAL'), ('complete', 'true', 'LIST_PARTIAL'),
            ('scope', 'namespace', 'LIST_SCOPE_MISMATCH'), ('list', None, 'LIST_MALFORMED')]
        for group, gvr in (('flux', KUST), ('native', POD)):
            for field, val, code in variants:
                with self.subTest(group=group, field=field, val=val):
                    b = fixture(); records(b, group, gvr)[field] = val
                    report = m.evaluate(b)
                    self.assertNotEqual(report['status'], 'OK')
                    self.assertIn(code, codes(report, 'gaps'))
            for metadata in ({'continue': 'sensitive-token'}, {'remainingItemCount': 1},
                             {'remainingItemCount': True}, {'continue': 0}):
                b = fixture(); records(b, group, gvr)['list']['metadata'] = metadata
                self.assertNotEqual(m.evaluate(b)['status'], 'OK')

    def test_unknown_empty_kind_is_empty_unknown_nonempty_not_suspend_failure(self):
        unknown = 'source.toolkit.fluxcd.io/v1/buckets'
        for nonempty in (False, True):
            b = fixture()
            b['captures']['crds']['list']['items'].append(crd(unknown, 'Bucket', 102))
            items = [obj(unknown, 'Bucket', 'unreviewed', 25)] if nonempty else []
            b['captures']['flux'].append({'gvr': unknown, 'capture': capture(items)})
            report = m.evaluate(b)
            self.assertEqual(report['status'], 'INCOMPLETE' if nonempty else 'OK')
            self.assertFalse(report['blocked'])
            if nonempty:
                self.assertIn('FLUX_KIND_UNSUPPORTED', codes(report, 'gaps'))
            else:
                self.assertIn('FLUX_LIST_EMPTY', codes(report, 'observations'))

    def test_flux_identity_drift_and_missing_expected(self):
        for field, val in (('uid', uid(30)), ('namespace', 'another'), ('name', 'another')):
            b = fixture(); resource(b, 'flux', GIT)['metadata'][field] = val
            self.assertEqual(m.evaluate(b)['status'], 'INCOMPLETE')
        b = fixture(); records(b, 'flux', GIT)['list']['items'] = []
        self.assertIn('EXPECTED_OBJECT_MISSING', codes(m.evaluate(b), 'gaps'))

    def test_nonboolean_suspend_is_not_policy_false(self):
        for gvr in (GIT, KUST):
            for value in (None, 0, 1, 'true', [], {}):
                b = fixture(); resource(b, 'flux', gvr)['spec']['suspend'] = value
                report = m.evaluate(b)
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertIn('SUSPEND_NOT_BOOLEAN', codes(report, 'gaps'))
                self.assertFalse(report['blocked'])

    def test_duplicates_inventory_versions_and_wrong_types(self):
        for variant in ('record', 'item', 'baseline', 'crd', 'version', 'inventory-missing',
                        'kind', 'api', 'unserved', 'multiple-version-lists', 'native-record'):
            with self.subTest(variant=variant):
                b = fixture()
                if variant == 'record':
                    b['captures']['flux'].append(copy.deepcopy(b['captures']['flux'][0]))
                elif variant == 'native-record':
                    b['captures']['native'].append(copy.deepcopy(b['captures']['native'][0]))
                elif variant == 'item':
                    records(b, 'flux', GIT)['list']['items'] *= 2
                elif variant == 'baseline':
                    b['baseline']['flux'].append(copy.deepcopy(b['baseline']['flux'][0]))
                elif variant == 'crd':
                    b['captures']['crds']['list']['items'] *= 2
                elif variant == 'version':
                    b['captures']['crds']['list']['items'][0]['spec']['versions'] *= 2
                elif variant == 'inventory-missing':
                    b['captures']['crds']['list']['items'].pop(0)
                elif variant == 'kind':
                    resource(b, 'flux', GIT)['kind'] = 'Kustomization'
                elif variant == 'api':
                    resource(b, 'flux', GIT)['apiVersion'] = 'source.toolkit.fluxcd.io/v99'
                elif variant == 'unserved':
                    b['captures']['crds']['list']['items'][0]['spec']['versions'][0]['served'] = False
                else:
                    b['captures']['flux'].append({'gvr': GIT.replace('/v1/', '/v2/'), 'capture': capture([])})
                self.assertNotEqual(m.evaluate(b)['status'], 'OK')

    def test_malformed_mappings_and_untrusted_absence_bool(self):
        for mutation in (
            lambda b: b.update(controllers_absent=True),
            lambda b: b['baseline'].update(native=True),
            lambda b: b['captures'].update(native=True),
            lambda b: b['captures']['flux'].append(None),
            lambda b: b['captures']['crds'].update(list=[]),
            lambda b: resource(b, 'flux', GIT).update(metadata={'name': 'URL/secret'}),
            lambda b: resource(b, 'flux', GIT).update(spec=[]),
            lambda b: records(b, 'flux', GIT)['list'].update(items={}),
        ):
            b = fixture(); mutation(b)
            self.assertEqual(m.evaluate(b)['status'], 'INCOMPLETE')
        for value in (None, [], True, 'secret', 1, {}):
            self.assertEqual(m.evaluate(value)['status'], 'INCOMPLETE')

    def test_valid_deep_json_is_incomplete_without_exception_details(self):
        code, report, raw = self.cli(b'[' * 2000 + b']' * 2000)
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertNotIn('Traceback', raw)

    def test_malformed_native_owner_references_cannot_establish_absence(self):
        b = fixture()
        pod = resource(b, 'native', POD)
        pod['metadata']['ownerReferences'] = {'controller': True}
        b['baseline']['native'][1] = identity(POD, pod, True)
        report = m.evaluate(b)
        self.assertIn('NATIVE_OBJECT_MALFORMED', codes(report, 'gaps'))
        self.assertIn('FETCH_INERTNESS_UNCONFIRMED', codes(report, 'gaps'))

    def test_findings_and_gaps_accumulate_no_first_assert_abort(self):
        b = fixture()
        resource(b, 'flux', KUST)['spec']['suspend'] = False
        b['captures']['native'].pop()
        records(b, 'flux', GIT)['list']['metadata']['continue'] = 'redact-me'
        report = m.evaluate(b)
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertFalse(report['complete'])
        self.assertIn('APPLY_INTENT_NOT_SUSPENDED', codes(report, 'blocked'))
        self.assertTrue({'LIST_MISSING', 'LIST_PAGINATED'} <= codes(report, 'gaps'))

    def test_purity_determinism_no_io_and_sanitized_output(self):
        b = fixture()
        resource(b, 'flux', GIT)['spec'].update(url='https://secret.invalid', secretRef={'name': 'sensitive'})
        before = copy.deepcopy(b)
        with patch('builtins.open', side_effect=AssertionError('IO forbidden')), \
             patch.object(Path, 'open', side_effect=AssertionError('IO forbidden')), \
             patch.object(subprocess, 'run', side_effect=AssertionError('runtime forbidden')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('runtime forbidden')), \
             patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            first = m.evaluate(b)
            self.assertEqual(first, m.evaluate(b))
        self.assertEqual(before, b)
        serialized = json.dumps(first)
        for sensitive in ('https://', 'secret.invalid', 'sensitive', 'secretRef', 'spec', 'Traceback'):
            self.assertNotIn(sensitive, serialized)

    def cli(self, data, limit=None):
        stdin = type('Input', (), {'buffer': io.BytesIO(data)})()
        output = io.StringIO()
        with patch.object(sys, 'stdin', stdin), patch.object(sys, 'stdout', output), \
             patch.object(m, 'MAX_INPUT_BYTES', m.MAX_INPUT_BYTES if limit is None else limit):
            result = m.main()
        return result, json.loads(output.getvalue()), output.getvalue()

    def test_cli_success_blocked_incomplete_and_bounded_read(self):
        b = fixture()
        self.assertEqual(self.cli(json.dumps(b).encode())[0], 0)
        resource(b, 'flux', KUST)['spec']['suspend'] = False
        self.assertEqual(self.cli(json.dumps(b).encode())[0], 1)
        self.assertEqual(self.cli(b'{}')[0], 2)
        code, report, _ = self.cli(b'x' * 20, limit=10)
        self.assertEqual(code, 2)
        self.assertIn('INPUT_TOO_LARGE', codes(report, 'gaps'))

    def test_cli_parse_duplicate_nonfinite_deep_and_error_redaction(self):
        for data in (b'{"secret-url":', b'{"secret":1,"secret":2}', b'NaN', b'Infinity',
                     b'\xff', b'[' * 2000):
            code, report, raw = self.cli(data)
            self.assertEqual(code, 2)
            self.assertIn('JSON_INVALID', codes(report, 'gaps'))
            self.assertNotIn('secret', raw)
            self.assertNotIn('Traceback', raw)


if __name__ == '__main__':
    unittest.main()
