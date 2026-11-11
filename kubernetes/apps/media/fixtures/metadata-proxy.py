#!/usr/bin/env python3
"""Fail-closed synthetic TMDb-contract proxy: NO upstream network forwarding.

Intended as an explicitly scoped helper sidecar on loopback. CONNECT performs a
local TLS server handshake with a dedicated proof-only api.themoviedb.org cert;
GET absolute HTTPS proxy requests also remain local. Unknown routes/methods,
query parameters, keys or destinations fail closed and increment denial count.
This is not evidence of compatibility with real TMDb accounts or data.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import threading
import urllib.parse


class Contract:
    def __init__(self, fixtures, key):
        self.fixtures, self.key = fixtures, key
        self.lock = threading.Lock()
        self.requests = {}
        self.denied = 0

    def deny(self):
        with self.lock:
            self.denied += 1
        return 501, {'proof_contract_error': 'unexpected request; no upstream forwarding exists'}

    def lookup(self, method, url, *, host='api.themoviedb.org', headers=None):
        if method != 'GET':
            return self.deny()
        parsed = urllib.parse.urlsplit(url)
        if parsed.netloc:
            if parsed.scheme != 'https' or parsed.hostname != 'api.themoviedb.org' or parsed.port not in (None, 443) or parsed.username or parsed.password:
                return self.deny()
        elif host not in ('api.themoviedb.org', 'api.themoviedb.org:443'):
            return self.deny()
        if parsed.fragment:
            return self.deny()
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if any(len(v) != 1 for v in query.values()) or set(query) - {'api_key', 'language', 'region', 'append_to_response', 'include_image_language', 'query', 'page', 'include_adult'}:
            return self.deny()
        authorization = (headers or {}).get('Authorization', '')
        supplied = query.get('api_key', [''])[0]
        if not (hmac.compare_digest(supplied, self.key) or hmac.compare_digest(authorization, 'Bearer ' + self.key)):
            self.deny()
            return 401, {'status_code': 7, 'status_message': 'synthetic proof key required', 'success': False}
        if query.get('language', ['en-US'])[0] not in ('en', 'en-US') or query.get('region', ['US'])[0] != 'US':
            return self.deny()
        if query.get('include_adult', ['false'])[0] != 'false' or query.get('include_image_language', ['en,null'])[0] not in ('en', 'en,null'):
            return self.deny()
        if query.get('query', ['Proof Fixture'])[0] != 'Proof Fixture' or query.get('page', ['1'])[0] != '1':
            return self.deny()
        # Only explicit fixture response variants are accepted; no wildcard provider.
        suffix = query.get('append_to_response', [''])[0]
        route = parsed.path + ('?append_to_response=' + suffix if suffix else '')
        if route not in self.fixtures:
            return self.deny()
        with self.lock:
            self.requests[route] = self.requests.get(route, 0) + 1
        return 200, self.fixtures[route]

    def evidence(self):
        with self.lock:
            return {'requests': dict(self.requests), 'denied': self.denied, 'upstream_connections': 0}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        pass  # No URLs/query credentials in logs.

    def send_json(self, status, body):
        payload = json.dumps(body, sort_keys=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_CONNECT(self):
        if self.path != 'api.themoviedb.org:443':
            status, body = self.server.contract.deny()
            self.send_json(status, body)
            return
        self.send_response(200, 'Proof-local TLS only')
        self.end_headers()
        self.wfile.flush()
        try:
            with self.server.tls.wrap_socket(self.connection, server_side=True) as connection:
                Handler(connection, self.client_address, self.server)
        except (OSError, ssl.SSLError):
            self.server.contract.deny()
        self.close_connection = True

    def do_GET(self):
        if self.path == '/proof-contract-evidence' and self.headers.get('Host') in ('127.0.0.1:18081', 'localhost:18081'):
            self.send_json(200, self.server.contract.evidence())
            return
        status, body = self.server.contract.lookup('GET', self.path, host=self.headers.get('Host', ''), headers=self.headers)
        self.send_json(status, body)

    def do_POST(self):
        self.send_json(*self.server.contract.deny())
    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST
    do_HEAD = do_POST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', required=True, type=Path)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--certificate', required=True, type=Path)
    parser.add_argument('--private-key', required=True, type=Path)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 18081), Handler)
    server.contract = Contract(json.loads(args.fixtures.read_text()), args.key_file.read_text().strip())
    server.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.tls.minimum_version = ssl.TLSVersion.TLSv1_2
    server.tls.load_cert_chain(args.certificate, args.private_key)
    server.serve_forever()


if __name__ == '__main__':
    main()
