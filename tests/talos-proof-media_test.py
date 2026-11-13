#!/usr/bin/env python3
"""Offline contract tests; deliberately not runtime functional acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / 'kubernetes/apps/media'


class Contract(unittest.TestCase):
    def test_every_current_compose_service_exact_digest(self):
        expected = {}
        for source in ['arrs', 'downloads', 'plex', 'jellyfin', 'jellyplex-watched', 'audiobookshelf', 'pinchflat', 'recyclarr']:
            for name, service in yaml.safe_load((ROOT / f'docker/{source}/compose.yml').read_text())['services'].items():
                expected[name] = service['image']
        actual = {}
        for path in MEDIA.glob('*/resources.yaml'):
            for d in yaml.safe_load_all(path.read_text()):
                if d['kind'] not in ['Deployment', 'CronJob']:
                    continue
                pod = d['spec']['template']['spec'] if d['kind'] == 'Deployment' else d['spec']['jobTemplate']['spec']['template']['spec']
                actual[d['metadata']['name']] = pod['containers'][0]['image']
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 16)

    def test_isolated_admission_charges_every_container_memory_ceiling(self):
        import importlib
        sys.path.insert(0, str(ROOT / 'scripts'))
        safety = importlib.import_module('talos-proof-media-safety')
        for path in MEDIA.glob('*/resources.yaml'):
            for d in yaml.safe_load_all(path.read_text()):
                if d['kind'] == 'Deployment':
                    pod = d['spec']['template']['spec']
                elif d['kind'] == 'CronJob':
                    pod = d['spec']['jobTemplate']['spec']['template']['spec']
                else:
                    continue
                cost = sum(int(c['resources']['limits']['memory'].removesuffix('Mi')) for c in pod['containers'] + [c for c in pod.get('initContainers', []) if c.get('restartPolicy') == 'Always'])
                self.assertEqual(safety.BUDGET[d['metadata']['name']], cost)

    def test_render_safety_and_denies(self):
        rendered = subprocess.check_output(['kubectl', 'kustomize', str(MEDIA)])
        subprocess.run([sys.executable, str(ROOT / 'tests/kubernetes-proof.py')], input=rendered, check=True, stdout=subprocess.PIPE)
        docs = list(yaml.safe_load_all(rendered))
        for ns in [d['metadata']['name'] for d in docs if d['kind'] == 'Namespace']:
            policies = [d['spec'] for d in docs if d['kind'] == 'NetworkPolicy' and d['metadata']['namespace'] == ns]
            self.assertTrue(any(p['podSelector'] == {} and set(p['policyTypes']) == {'Ingress', 'Egress'} and not p.get('ingress') and not p.get('egress') for p in policies))
            for policy in policies:
                for rule in policy.get('egress', []):
                    self.assertTrue(rule['ports'])
                    for peer in rule['to']:
                        self.assertNotIn('ipBlock', peer)  # no Internet or private address exceptions
                        self.assertIn('namespaceSelector', peer)
                        self.assertIn('podSelector', peer)

    def test_offline_secrets_are_private_and_not_printed(self):
        with tempfile.TemporaryDirectory(prefix='talos-proof-media-test-') as tmp:
            state = Path(tmp).resolve() / 'private'
            out = subprocess.check_output([sys.executable, str(ROOT / 'scripts/talos-proof-media-bootstrap.py'), '--state-dir', str(state)])
            credentials = json.loads((state / 'credentials.json').read_text())
            self.assertEqual(len(credentials), 16)
            for path in state.iterdir():
                self.assertEqual(path.stat().st_mode & 0o077, 0)
            self.assertEqual(state.stat().st_mode & 0o777, 0o700)
            for credential in credentials.values():
                self.assertNotIn(credential['password'].encode(), out)
                self.assertNotIn(credential['api_key'].encode(), out)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/talos-proof-media-bootstrap.py'), '--state-dir', str(state)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)  # never silently rotate an initialized PVC's credentials

    def test_fixture_is_deterministic(self):
        with tempfile.TemporaryDirectory(prefix='talos-proof-media-fixture-') as tmp:
            command = [sys.executable, str(ROOT / 'scripts/talos-proof-media-fixture.py'), '--state-dir', str(Path(tmp).resolve())]
            first = json.loads(subprocess.check_output(command))
            second = json.loads(subprocess.check_output(command))
            self.assertEqual(first, second)
            self.assertEqual(first['bytes'], 32044)

    def test_helper_execution_is_bounded_not_success_placeholder(self):
        for name in ['kometa', 'recyclarr', 'jellyplex-watched']:
            cron = next(d for d in yaml.safe_load_all((MEDIA / name / 'resources.yaml').read_text()) if d['kind'] == 'CronJob')
            self.assertTrue(cron['spec']['suspend'])
            job = cron['spec']['jobTemplate']['spec']
            self.assertEqual(job['backoffLimit'], 0)
            self.assertLessEqual(job['activeDeadlineSeconds'], 180)
            container = job['template']['spec']['containers'][0]
            self.assertNotIn('command', container)  # no echo/true masquerading as application success
            if name == 'jellyplex-watched':
                env = {e['name']: e.get('value') for e in container['env']}
                self.assertEqual(env['DRYRUN'], 'True')
                self.assertEqual(env['RUN_ONLY_ONCE'], 'True')
            elif name == 'recyclarr':
                self.assertEqual(container['args'], ['sync', '--preview'])

if __name__ == '__main__':
    unittest.main()
