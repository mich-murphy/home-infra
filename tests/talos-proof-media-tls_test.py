#!/usr/bin/env python3
"""Real local TLS handshake tests using ephemeral test certificates, no cluster API."""
import http.server
import importlib
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
client = importlib.import_module('talos-proof-media-http')


class Quiet(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'https://production.invalid/')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"proof":true}')

    def log_message(self, *args):
        pass


class GatewayTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='talos-proof-media-tls-')
        cls.state = Path(cls.temp.name).resolve()
        for name in ['trusted', 'wrong']:
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-subj', '/CN=radarr.proof.invalid', '-addext', 'subjectAltName=DNS:radarr.proof.invalid',
                            '-keyout', str(cls.state / f'{name}.key'), '-out', str(cls.state / f'{name}.crt')],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.server = http.server.HTTPServer(('127.0.0.1', 0), Quiet)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.state / 'trusted.crt', cls.state / 'trusted.key')
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def connect(self, address, timeout=45, source_address=None):
        self.assertEqual(address[1], 18443)
        return socket.create_connection(('127.0.0.1', self.server.server_port), timeout, source_address)

    def test_trusted_hostname_and_sni_without_dns(self):
        with patch.object(client.LoopbackTLS, 'loopback_connection', staticmethod(self.connect)):
            api = client.API('https://radarr.proof.invalid:18443', service='radarr', ca=self.state / 'trusted.crt')
            self.assertEqual(api.call('/'), {'proof': True})

    def test_wrong_ca_rejected(self):
        with patch.object(client.LoopbackTLS, 'loopback_connection', staticmethod(self.connect)):
            api = client.API('https://radarr.proof.invalid:18443', service='radarr', ca=self.state / 'wrong.crt')
            with self.assertRaises(urllib.error.URLError):
                api.call('/')

    def test_wrong_certificate_hostname_rejected(self):
        with patch.object(client.LoopbackTLS, 'loopback_connection', staticmethod(self.connect)):
            api = client.API('https://sonarr.proof.invalid:18443', service='sonarr', ca=self.state / 'trusted.crt')
            with self.assertRaises(urllib.error.URLError):
                api.call('/')

    def test_cross_origin_redirect_rejected(self):
        with patch.object(client.LoopbackTLS, 'loopback_connection', staticmethod(self.connect)):
            api = client.API('https://radarr.proof.invalid:18443', service='radarr', ca=self.state / 'trusted.crt')
            with self.assertRaises(ValueError):
                api.call('/redirect')

if __name__ == '__main__':
    unittest.main()
