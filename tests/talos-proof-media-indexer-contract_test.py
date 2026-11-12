#!/usr/bin/env python3
"""OFFLINE ONLY: real loopback HTTP plus a fail-closed outbound socket guard."""
import contextlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import socket
import threading
import unittest
from unittest import mock
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('indexer_contract', ROOT / 'kubernetes/apps/media/fixtures/indexer-contract/server.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
KEY = 'OfflineSyntheticKey42'


class ContractTests(unittest.TestCase):
    def setUp(self):
        # HTTP artifact engine and provider share exactly one Fixture, not two payloads.
        self.fixture = m.protocols.Fixture()
        self.artifact = m.protocols.HTTPServer(('127.0.0.1', 0), self.fixture, ('127.0.0.1', 6881))
        self.base = 'http://127.0.0.1:' + str(self.artifact.server_address[1])
        self.fixture = m.protocols.Fixture(announce=self.base + '/announce')
        self.artifact.fixture = self.fixture
        self.contract = m.Contract(self.fixture, self.base, KEY)
        self.provider = m.Server(('127.0.0.1', 0), self.contract)
        self.threads = []
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.out)
        self.stderr = contextlib.redirect_stderr(self.err)
        self.stdout.__enter__()
        self.stderr.__enter__()
        owner_thread = threading.get_ident()
        original_connect = socket.socket.connect
        allowed = {self.provider.server_address, self.artifact.server_address}
        self.forbidden_attempts = []

        def guarded_connect(sock, address):
            if threading.get_ident() != owner_thread or address not in allowed:
                self.forbidden_attempts.append('connect')
                raise AssertionError('outbound forwarding forbidden')
            return original_connect(sock, address)

        self.guard = mock.patch.object(socket.socket, 'connect', guarded_connect)
        self.guard.start()
        # The provider never needs a resolver, even for a malicious destination.
        def deny_dns(*args, **kwargs):
            self.forbidden_attempts.append('dns')
            raise AssertionError('DNS forbidden')
        self.dns = mock.patch('socket.getaddrinfo', side_effect=deny_dns)
        self.dns.start()
        for server in (self.artifact, self.provider):
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
            thread.start()
            self.threads.append(thread)

    def tearDown(self):
        for server in (self.provider, self.artifact):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(2)
        self.guard.stop()
        self.dns.stop()
        self.stdout.__exit__(None, None, None)
        self.stderr.__exit__(None, None, None)
        self.assertEqual(self.out.getvalue(), '')
        self.assertEqual(self.err.getvalue(), '')
        self.assertEqual(self.forbidden_attempts, [])

    def request(self, path='/torznab/api', params=None, method='GET', headers=None, port=None):
        params = {'apikey': KEY, 't': 'search', **(params or {})}
        sock = socket.socket()
        sock.settimeout(4)
        sock.connect(('127.0.0.1', port or self.provider.server_address[1]))
        query = urllib.parse.urlencode(params)
        target = path + ('?' + query if params else '')
        extra = ''.join(f'{k}: {v}\r\n' for k, v in (headers or {}).items())
        sock.sendall(f'{method} {target} HTTP/1.1\r\nHost: attacker.invalid\r\n{extra}\r\n'.encode())
        response = http.client.HTTPResponse(sock)
        response.begin()
        status, body = response.status, response.read()
        self.assertEqual(int(response.getheader('Content-Length')), len(body))
        response.close()
        sock.close()
        self.assertLessEqual(len(body), m.MAX_RESPONSE)
        return status, body

    def test_authenticated_caps_both_protocols_and_compatible_extra_fields(self):
        for route in ('/torznab/api', '/newznab/api'):
            status, body = self.request(route, dict(t='caps', extended='1', limit='100', offset='0',
                                                   cat='2000,2040', configured='1', apikey=KEY))
            self.assertEqual(status, 200)
            root = ET.fromstring(body)
            self.assertEqual(root.tag, 'caps')
            self.assertEqual(root.find('searching/movie-search').get('supportedParams'), 'q,imdbid,tmdbid')
            self.assertEqual(root.find('categories/category/subcat').get('id'), '2040')
            self.assertNotIn(KEY.encode(), body)
        for key in ('wrongKey', ''):
            status, body = self.request(params=dict(t='caps', apikey=key))
            self.assertEqual(status, 403)
            self.assertEqual(ET.fromstring(body).get('code'), '100')
            self.assertNotIn(b'wrongKey', body)

    def test_real_rss_namespaces_guid_and_shared_artifacts(self):
        for protocol, extension in (('torznab', 'torrent'), ('newznab', 'nzb')):
            params = dict(t='movie', q='Proof Fixture', tmdbid=m.TMDB, imdbid='tt' + m.IMDB,
                          cat='2000,2040', extended='1', limit='100', offset='0',
                          attrs='category,size,seeders', rid='ignored-extension')
            status, body = self.request('/' + protocol + '/api', params)
            self.assertEqual(status, 200)
            self.assertEqual(body, self.request('/' + protocol + '/api', params)[1])
            root = ET.fromstring(body)
            channel = root.find('channel')
            self.assertEqual(channel.find('{' + m.NS[protocol] + '}response').get('total'), '1')
            item = channel.find('item')
            self.assertEqual(item.findtext('title'), m.RELEASE)
            self.assertEqual(item.find('guid').get('isPermaLink'), 'false')
            enclosure = item.find('enclosure')
            self.assertEqual(enclosure.get('url'), self.base + '/artifact.' + extension)
            self.assertNotIn('attacker', body.decode())
            attrs = {e.get('name'): e.get('value') for e in item.findall('{' + m.NS[protocol] + '}attr')}
            self.assertEqual(attrs['category'], '2040')
            self.assertEqual(attrs['tmdbid'], m.TMDB)
            if protocol == 'torznab':
                self.assertEqual(attrs['infohash'], self.fixture.infohash.hex())
                self.assertEqual(attrs['seeders'], '1')
            # Exact pre-existing engine artifact endpoint, not an API mock or arbitrary file.
            sock = socket.socket()
            sock.settimeout(2)
            sock.connect(self.artifact.server_address)
            sock.sendall(f'GET /artifact.{extension} HTTP/1.0\r\n\r\n'.encode())
            response = http.client.HTTPResponse(sock)
            response.begin()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), getattr(self.fixture, extension))
            sock.close()

    def test_empty_test_search_unknown_query_id_category_and_page(self):
        self.assertIsNotNone(ET.fromstring(self.request()[1]).find('channel/item'))
        for params in (dict(q='unknown-RAW_SECRET'), dict(tmdbid='1'), dict(imdbid='tt1'),
                       dict(cat='5000'), dict(offset='1'), dict(limit='0')):
            status, body = self.request(params=params)
            self.assertEqual(status, 200)
            root = ET.fromstring(body)
            self.assertIsNone(root.find('channel/item'))
            self.assertNotIn(b'RAW_SECRET', body)

    def test_forbidden_destinations_unknown_routes_and_operations(self):
        for destination in ('http://169.254.169.254/latest/meta-data', 'https://example.com',
                            'file:///etc/passwd', 'http://127.0.0.1:1', 'data:base64,SECRET'):
            for field in ('url', 'destination', 'redirect', 'path'):
                status, body = self.request(params={field: destination})
                self.assertEqual(status, 400)
                self.assertNotIn(destination.encode(), body)
        self.assertEqual(self.request('/api/v1/indexer')[0], 404)
        self.assertEqual(self.request('/artifact.torrent')[0], 404)
        self.assertEqual(self.request(params=dict(t='get', id='../secret'))[0], 400)
        self.assertEqual(self.request(method='POST')[0], 405)
        self.assertEqual(self.request(headers={'Content-Length': '1'})[0], 405)
        self.assertEqual(self.request(headers={'Transfer-Encoding': 'chunked'})[0], 405)
        self.assertEqual(self.request('http://example.com/torznab/api')[0], 400)
        self.assertEqual(self.request(params=dict(offset='RAW_SECRET'))[0], 400)
        # Arbitrary extension fields are inert, not reflected or guessed-invalid.
        self.assertEqual(self.request(params=dict(futureField='RAW_SECRET'))[0], 200)

    def raw(self, request):
        sock = socket.socket()
        sock.settimeout(4)
        sock.connect(self.provider.server_address)
        sock.sendall(request)
        data = bytearray()
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
        except ConnectionResetError:
            pass
        finally:
            sock.close()
        return bytes(data)

    def test_request_header_field_response_and_counter_bounds(self):
        self.assertIn(b'414', self.raw(b'GET /' + b'x' * 2100 + b' HTTP/1.0\r\n\r\n'))
        self.assertIn(b'431', self.raw(b'GET / HTTP/1.1\r\nX: ' + b'x' * 2050 + b'\r\n\r\n'))
        headers = b'X: ' + b'x' * 1000 + b'\r\n'
        self.assertIn(b'431', self.raw(b'GET / HTTP/1.1\r\n' + headers * 9 + b'\r\n'))
        duplicate = f'GET /torznab/api?apikey={KEY}&t=caps&t=caps HTTP/1.0\r\n\r\n'.encode()
        self.assertIn(b'400', self.raw(duplicate))
        self.assertEqual(self.request(params={f'f{i}': 'x' for i in range(33)})[0], 400)
        self.assertEqual(self.request(params=dict(q='x' * 257))[0], 400)
        self.contract.counters['caps'] = m.MAX_COUNTER
        self.request(params=dict(t='caps'))
        self.assertEqual(self.contract.counters['caps'], m.MAX_COUNTER)
        status, body = self.request('/stats')
        self.assertEqual(status, 200)
        counters = json.loads(body)
        self.assertEqual(set(counters), {'requests', 'caps', 'searches', 'results', 'rejected', 'busy'})
        self.assertGreater(counters['rejected'], 0)
        self.assertNotIn(KEY, body.decode())

    def test_timeout_concurrency_and_no_keepalive(self):
        sockets = []
        reached = threading.Event()
        original_count = self.contract.count
        def count(key):
            original_count(key)
            if key == 'requests' and self.contract.counters['requests'] == m.CONCURRENCY:
                reached.set()
        self.contract.count = count
        try:
            for _ in range(m.CONCURRENCY):
                sock = socket.socket()
                sock.settimeout(5)
                sock.connect(self.provider.server_address)
                sock.sendall(b'GET / HTTP/1.1\r\nX: incomplete')
                sockets.append(sock)
            self.assertTrue(reached.wait(1))
            extra = socket.socket()
            extra.settimeout(1)
            extra.connect(self.provider.server_address)
            self.assertEqual(extra.recv(1), b'')
            extra.close()
            self.assertEqual(self.contract.counters['busy'], 1)
            for sock in sockets:
                self.assertEqual(sock.recv(1), b'')  # bounded header timeout
        finally:
            for sock in sockets:
                sock.close()
        request = f'GET /torznab/api?apikey={KEY}&t=caps HTTP/1.1\r\nConnection: keep-alive\r\n\r\n'.encode()
        self.assertEqual(self.raw(request * 2).count(b'HTTP/1.0 200'), 1)

    def test_fail_closed_configuration_and_same_skyhook_identity(self):
        for base in ('http://example.com:80', 'http://169.254.169.254:80', 'http://127.0.0.1',
                     'http://127.0.0.1:80/', 'http://user:pass@127.0.0.1:80',
                     'http://127.0.0.1:80?url=secret', 'http://[::1]:80'):
            with self.assertRaises(ValueError):
                m.canonical_base(base)
        with self.assertRaises(ValueError):
            m.Contract(self.fixture, 'http://127.0.0.1:1', KEY)
        with self.assertRaises(ValueError):
            m.Server(('0.0.0.0', 0), self.contract)
        skyhook = json.loads((ROOT / 'kubernetes/apps/media/fixtures/skyhook-contract.json').read_text())
        movie = skyhook['/v1/movie/' + m.TMDB]
        self.assertEqual(movie['title'], m.TITLE)
        self.assertEqual(movie['imdbId'], 'tt' + m.IMDB)
        self.assertEqual(m.protocols.MAX_PAYLOAD, 2 * 1024 * 1024)


if __name__ == '__main__':
    # These are socket/thread-only fixtures (no child processes). Preserve thread
    # stacks and terminate this owned test process if shutdown ever stalls; a
    # previous aggregate-gate timeout had no stack and is not a proven root cause.
    import faulthandler
    faulthandler.dump_traceback_later(60, exit=True)
    try:
        unittest.main()
    finally:
        faulthandler.cancel_dump_traceback_later()
