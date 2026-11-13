#!/usr/bin/env python3
"""Offline integration-profile/functional-test logic checks; not live app evidence."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
safety = importlib.import_module('talos-proof-media-safety')
services = importlib.import_module('talos-proof-media-services')


class Anonymous:
    def call(self, *args, **kwargs):
        raise urllib.error.HTTPError('https://offline.invalid', 401, 'Unauthorized', {}, None)


class QbitUI:
    def __init__(self):
        self.instances, self.headers, self.writes = [], {}, []
        self.ident = 0
    def anonymous(self):
        return Anonymous()
    def call(self, path, method='GET', data=None, **kwargs):
        if method != 'GET':
            self.writes.append((path, method))
        if path in ['/api/auth/login', '/api/auth/me']:
            return {'username': 'proof'}
        if path == '/api/instances/' and method == 'GET':
            return self.instances
        if path == '/api/instances/' and method == 'POST':
            self.ident += 1
            item = {'id': self.ident, **data}
            self.instances.append(item)
            return item
        if path == '/api/instances/stats':
            return [{'id': x['id'], 'online': True, 'total': 0} for x in self.instances]
        if path.endswith('/test'):
            return {'success': True, 'version': 'offline-fake-version'}
        ident = int(path.rsplit('/', 1)[1])
        if method == 'PUT':
            next(x for x in self.instances if x['id'] == ident).update(data)
            return {}
        if method == 'DELETE':
            self.instances = [x for x in self.instances if x['id'] != ident]
            return {}
        raise AssertionError('unexpected fake request')


class Integration(unittest.TestCase):
    def test_explicit_shared_filesystem_and_zero_defaults(self):
        rendered = subprocess.check_output(['kubectl', 'kustomize', str(ROOT / 'kubernetes/apps/media/integration')])
        subprocess.run([sys.executable, str(ROOT / 'tests/kubernetes-proof.py')], input=rendered, check=True, stdout=subprocess.PIPE)
        docs = list(yaml.safe_load_all(rendered))
        deployments = [d for d in docs if d['kind'] == 'Deployment']
        self.assertEqual(len(deployments), 7)
        self.assertEqual([d['metadata']['name'] for d in docs if d['kind'] == 'Namespace'], ['proof-media-pipeline'])
        for d in deployments:
            self.assertEqual(d['spec']['replicas'], 0)
            name = d['metadata']['name']
            pod = d['spec']['template']['spec']
            claims = [v['persistentVolumeClaim']['claimName'] for v in pod['volumes'] if 'persistentVolumeClaim' in v]
            self.assertIn(name + '-config', claims)
            self.assertEqual(pod['containers'][0]['resources']['limits']['memory'], str(safety.PIPELINE_LIMITS[name]) + 'Mi')
            if name != 'prowlarr':
                self.assertIn('data', claims)
            self.assertNotIn('fixture', claims)
        for route in [d for d in docs if d['kind'] == 'HTTPRoute']:
            self.assertEqual(route['spec']['hostnames'], ['pipeline-' + route['metadata']['name'] + '.proof.invalid'])

    def test_recyclarr_preview_uses_nonempty_local_resources_without_default_git(self):
        docs = list(yaml.safe_load_all((ROOT / 'kubernetes/apps/media/recyclarr/resources.yaml').read_text()))
        cm = next(x for x in docs if x['kind'] == 'ConfigMap')
        settings = yaml.safe_load(cm['data']['settings.yml'])
        replacements = {x['type'] for x in settings['resource_providers'] if x.get('replace_default')}
        self.assertEqual(replacements, {'trash-guides', 'config-templates'})
        self.assertTrue(all('path' in x and 'clone_url' not in x for x in settings['resource_providers']))
        fmt = json.loads(cm['data']['proof-format.json'])
        self.assertEqual(fmt['name'], 'Proof-Synthetic-Title')
        self.assertTrue(fmt['specifications'])

    def test_pipeline_requires_pair_and_rejects_third_active_controller(self):
        safety.select_pipeline('qbittorrent+qbitwebui')
        controller = {'metadata': {'namespace': 'proof-media-pipeline', 'name': 'radarr'}, 'spec': {'replicas': 1}}
        def read(*args):
            return json.dumps({'items': [] if args[1] == 'pods' else [controller]})
        with patch.object(safety, 'kubectl_read', side_effect=read):
            with self.assertRaises(RuntimeError):
                safety.exclusivity('media-pipeline')
        with self.assertRaises(RuntimeError):
            safety.select_pipeline('all')
        safety.PIPELINE_MEMBERS = None

    def test_qbitwebui_exercise_and_verify_read_existing_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve()
            safety.write_private(state / 'credentials.json', json.dumps({'qbittorrent': {'username': 'proof', 'password': 'OFFLINE-FAKE-PASSWORD'}}))
            api = QbitUI()
            credential = {'username': 'proof', 'password': 'OFFLINE-FAKE-PASSWORD'}
            services.qbitwebui(api, credential, None, state, 'exercise')
            self.assertEqual(len(api.instances), 1)
            api.writes.clear()
            services.qbitwebui(api, credential, None, state, 'verify')
            self.assertFalse(any(method in ('PUT', 'DELETE') or path == '/api/instances/' for path, method in api.writes))
            api.instances = []
            with self.assertRaises(RuntimeError):
                services.qbitwebui(api, credential, None, state, 'verify')

    def test_pinchflat_csrf_parser_and_missing_token(self):
        self.assertEqual(services.csrf(b'<input value="escaped&amp;token" name="_csrf_token">'), 'escaped&token')
        with self.assertRaises(RuntimeError):
            services.csrf(b'<html>No token</html>')

    def test_fixture_stream_requires_exact_bytes_and_partial_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve()
            fixture = safety.write_private(state / 'fixture.wav', b'header' * 30)
            class Fake:
                last_status = 200
                def call(self, path, **kwargs):
                    self.last_status = 206 if kwargs.get('headers') else 200
                    data = fixture.read_bytes()
                    return data[44:108] if kwargs.get('headers') else data
            self.assertTrue(services.audio_checksum(Fake(), '/public/session/fake/track/1', fixture))
            with self.assertRaises(RuntimeError):
                services.audio_checksum(Fake(), 'https://production.invalid/audio', fixture)

if __name__ == '__main__':
    unittest.main()
