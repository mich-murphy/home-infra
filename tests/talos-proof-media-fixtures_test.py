#!/usr/bin/env python3
"""Offline metadata contract, unclaimed-adapter auth and recovery archive mutants."""
import base64
import http.client
import importlib
import importlib.util
import io
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
recovery = importlib.import_module('talos-proof-media-recovery')

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

proxy = load('proof_metadata_proxy', ROOT / 'kubernetes/apps/media/fixtures/metadata-proxy.py')
adapter = load('proof_plex_adapter', ROOT / 'kubernetes/apps/media/plex/plex-unclaimed-proxy.py')
FIXTURES = json.loads((ROOT / 'kubernetes/apps/media/fixtures/tmdb-contract.json').read_text())
KEY = 'OFFLINE-FAKE-SYNTHETIC-KEY'


class Contracts(unittest.TestCase):
    def test_known_contract_and_no_upstream_connection(self):
        contract = proxy.Contract(FIXTURES, KEY)
        with patch('socket.create_connection', side_effect=AssertionError('unexpected upstream network')):
            status, body = contract.lookup('GET', '/3/movie/900000001?api_key=' + KEY)
        self.assertEqual(status, 200)
        self.assertEqual(body['title'], 'Proof Fixture')
        self.assertEqual(contract.evidence()['upstream_connections'], 0)
        self.assertEqual(contract.evidence()['requests']['/3/movie/900000001'], 1)

    def test_unknown_hosts_endpoints_methods_parameters_denied(self):
        contract = proxy.Contract(FIXTURES, KEY)
        for method, url in [('POST', '/3/configuration?api_key=' + KEY),
                            ('GET', 'https://production.invalid/3/configuration?api_key=' + KEY),
                            ('GET', '/3/movie/1?api_key=' + KEY),
                            ('GET', '/3/configuration?api_key=' + KEY + '&unexpected=1'),
                            ('GET', '/3/search/movie?api_key=' + KEY + '&query=real+film'),
                            ('GET', '/3/configuration?api_key=' + KEY + '&api_key=duplicate')]:
            self.assertEqual(contract.lookup(method, url)[0], 501)
        self.assertEqual(contract.evidence()['denied'], 6)
        self.assertEqual(contract.lookup('GET', '/3/configuration?api_key=WRONG')[0], 401)

    def test_fresh_adapter_key_or_basic_required(self):
        self.assertTrue(adapter.authorized({'X-Plex-Token': KEY}, '', KEY, 'OFFLINE-PASSWORD'))
        self.assertTrue(adapter.authorized({}, 'X-Plex-Token=' + KEY, KEY, 'OFFLINE-PASSWORD'))
        basic = base64.b64encode(b'proof:OFFLINE-PASSWORD').decode()
        self.assertTrue(adapter.authorized({'Authorization': 'Basic ' + basic}, '', KEY, 'OFFLINE-PASSWORD'))
        for headers in [{}, {'X-Plex-Token': 'production-looking-token'}, {'Authorization': 'Basic !!!'}]:
            self.assertFalse(adapter.authorized(headers, '', KEY, 'OFFLINE-PASSWORD'))

    def test_stopped_archive_checks(self):
        def archive(name, link=None, kind=None):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w') as handle:
                info = tarfile.TarInfo(name)
                if link:
                    info.type, info.linkname = tarfile.SYMTYPE, link
                elif kind:
                    info.type = kind
                else:
                    info.size = 5
                handle.addfile(info, io.BytesIO(b'proof') if info.isreg() else None)
            return stream.getvalue()
        recovery.safe_archive(archive('./config/proof.db'))
        for payload in [archive('../escape'), archive('/absolute'), archive('link', '/etc/passwd'), archive('link', '../../escape'), archive('fifo', kind=tarfile.FIFOTYPE)]:
            with self.assertRaises(RuntimeError):
                recovery.safe_archive(payload)


class LocalProxyTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='talos-proof-metadata-tls-')
        cls.path = Path(cls.temp.name).resolve()
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=api.themoviedb.org', '-addext', 'subjectAltName=DNS:api.themoviedb.org',
                        '-keyout', str(cls.path / 'key'), '-out', str(cls.path / 'cert')],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.server = proxy.ThreadingHTTPServer(('127.0.0.1', 0), proxy.Handler)
        cls.server.contract = proxy.Contract(FIXTURES, KEY)
        cls.server.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.server.tls.load_cert_chain(cls.path / 'cert', cls.path / 'key')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def test_real_connect_tls_stays_local_and_returns_fixture(self):
        context = ssl.create_default_context(cafile=str(self.path / 'cert'))
        connection = http.client.HTTPSConnection('127.0.0.1', self.server.server_port, context=context, timeout=5)
        connection.set_tunnel('api.themoviedb.org', 443)
        try:
            connection.request('GET', '/3/configuration?api_key=' + KEY)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('images', json.loads(response.read()))
        finally:
            connection.close()

    def test_other_connect_host_denied_not_forwarded(self):
        connection = http.client.HTTPSConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.set_tunnel('production.invalid', 443)
        try:
            with self.assertRaises(OSError):
                connection.request('GET', '/')
        finally:
            connection.close()

if __name__ == '__main__':
    unittest.main()
