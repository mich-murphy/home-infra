#!/usr/bin/env python3
"""Offline effective rendered-pod resource oracle; no kubectl/cluster calls.

Accepts already rendered Pod specs. Explicit integration replicas are also tested
from checked-in YAML (no claim this substitutes for owner's final render test).
All quantities are exact integer bytes/millicores; unsupported shapes fail closed.
"""
import copy
import importlib
from pathlib import Path
import re
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
safety = importlib.import_module('talos-proof-media-safety')
MIB = 1024 * 1024


def quantity(value, resource):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('unsupported resource quantity')
    value = str(value)
    pattern = r'([0-9]+)(Ki|Mi|Gi|Ti)?' if resource == 'memory' else r'([0-9]+)(m)?'
    match = re.fullmatch(pattern, value)
    if not match or int(match[1]) <= 0:
        raise ValueError('unsupported or nonpositive ' + resource + ' quantity')
    if resource == 'memory':
        return int(match[1]) * {None: 1, 'Ki': 1024, 'Mi': MIB, 'Gi': 1024**3, 'Ti': 1024**4}[match[2]]
    return int(match[1]) * (1 if match[2] == 'm' else 1000)


def effective_limits(pod):
    if any(k in pod for k in ('overhead', 'resources', 'ephemeralContainers')):
        raise ValueError('unsupported pod-level/ephemeral resources; review explicitly')
    containers = pod.get('containers', [])
    if not containers:
        raise ValueError('regular container required')
    names = set()
    def limits(c, init=False):
        if not c.get('name') or c['name'] in names:
            raise ValueError('missing/duplicate container name')
        names.add(c['name'])
        if ('restartPolicy' in c and (not init or c['restartPolicy'] != 'Always')):
            raise ValueError('unsupported container restart policy')
        try:
            values = c['resources']['limits']
            if set(values) != {'cpu', 'memory'}:
                raise ValueError('unsupported or missing limits')
            return {r: quantity(values[r], r) for r in ('cpu', 'memory')}
        except KeyError as exc:
            raise ValueError('every container/init needs explicit cpu+memory limits') from exc
    regular = [limits(c) for c in containers]
    steady = {r: sum(c[r] for c in regular) for r in ('cpu', 'memory')}
    prefix = dict(cpu=0, memory=0)
    peak = dict(cpu=0, memory=0)
    for c in pod.get('initContainers', []):
        current = limits(c, init=True)
        for r in peak:
            # All prior restartable init sidecars are concurrent with this init.
            peak[r] = max(peak[r], prefix[r] + current[r])
        if c.get('restartPolicy') == 'Always':
            for r in prefix:
                prefix[r] += current[r]
    return {r: max(peak[r], steady[r] + prefix[r]) for r in peak}


def assert_charge(pod, charged_mib):
    actual = effective_limits(pod)['memory']
    if actual > charged_mib * MIB:
        raise ValueError('undercharged effective pod memory')
    return actual


def pod_for(path, kind='Deployment'):
    doc = next(d for d in yaml.safe_load_all(path.read_text()) if d and d['kind'] == kind)
    spec = doc['spec']
    if kind == 'CronJob':
        spec = spec['jobTemplate']['spec']
    return spec['template']['spec']


class Resources(unittest.TestCase):
    def test_every_current_integration_container_and_init_is_charged(self):
        for name, charge in safety.PIPELINE_LIMITS.items():
            with self.subTest(name=name):
                pod = pod_for(ROOT / f'kubernetes/apps/media/integration/{name}.yaml',
                              'CronJob' if name == 'recyclarr' else 'Deployment')
                self.assertEqual(assert_charge(pod, charge), charge * MIB)

    def test_actual_isolated_skyhook_is_512_not_pipeline_384(self):
        pod = pod_for(ROOT / 'kubernetes/apps/media/radarr/resources.yaml')
        self.assertEqual(effective_limits(pod)['memory'], 512 * MIB)
        with self.assertRaisesRegex(ValueError, 'undercharged'):
            assert_charge(pod, 384)
        assert_charge(pod, safety.BUDGET['radarr'])

    def test_future_integration_skyhook_and_fixture_are_not_free(self):
        pod = pod_for(ROOT / 'kubernetes/apps/media/integration/radarr.yaml')
        side = next(c for c in pod_for(ROOT / 'kubernetes/apps/media/radarr/resources.yaml')['initContainers']
                    if c['name'] == 'metadata-contract')
        pod['initContainers'].insert(0, copy.deepcopy(side))
        with self.assertRaisesRegex(ValueError, 'undercharged'):
            assert_charge(pod, safety.PIPELINE_LIMITS['radarr'])
        self.assertEqual(assert_charge(pod, 512), 512 * MIB)
        fixture = pod_for(ROOT / 'kubernetes/apps/media/fixtures/download-protocols/resources.yaml')
        self.assertEqual(effective_limits(fixture)['memory'], 128 * MIB)
        self.assertEqual(512 + 192 + 128 + 192, 1024)  # proposed, NOT a grant
        self.assertEqual(128 + 192, 320)  # stopped helper only, NOT a grant

    def test_sequential_init_max_and_concurrent_sidecar_prefix(self):
        def c(name, memory, side=False):
            result = dict(name=name, resources={'limits': {'cpu': '100m', 'memory': str(memory) + 'Mi'}})
            if side:
                result['restartPolicy'] = 'Always'
            return result
        pod = dict(containers=[c('main', 100), c('second-main', 50)],
                   initContainers=[c('early', 600), c('side', 128, True), c('late', 500), c('side2', 64, True)])
        self.assertEqual(effective_limits(pod), dict(memory=628*MIB, cpu=400))
        pod['initContainers'][0]['resources']['limits']['memory'] = '1Gi'
        self.assertEqual(effective_limits(pod)['memory'], 1024*MIB)

    def test_missing_limits_and_unsupported_shapes_fail(self):
        good = dict(containers=[dict(name='main', resources={'limits': {'cpu': '1', 'memory': '384Mi'}})])
        for mutate in (lambda p: p['containers'].append({'name': 'uncharged'}),
                       lambda p: p.update(initContainers=[{'name': 'init'}]),
                       lambda p: p.update(overhead={'memory': '1Mi'}),
                       lambda p: p.update(ephemeralContainers=[]),
                       lambda p: p['containers'][0].update(restartPolicy='Always'),
                       lambda p: p['containers'][0]['resources']['limits'].update(memory='0'),
                       lambda p: p['containers'][0]['resources']['limits'].update(memory='1.5Gi')):
            pod = copy.deepcopy(good); mutate(pod)
            with self.assertRaises(ValueError): effective_limits(pod)


if __name__ == '__main__':
    unittest.main()
