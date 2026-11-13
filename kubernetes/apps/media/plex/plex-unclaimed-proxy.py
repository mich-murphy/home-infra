#!/usr/bin/env python3
"""Fresh-key adapter for genuine localhost-only unclaimed Plex APIs.

NOT a Plex account/token emulator. An independent proof access key authorizes the
adapter, then is stripped before localhost forwarding. No upstream host can be
selected. Cloud claim/account/registration are absent. Tiny proof fixtures only.
"""
import argparse
import base64
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import select
import re
import socket
import urllib.parse

HOP_HEADERS = {'connection', 'proxy-connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'proxy-authorization'}
MAX_BODY = 1024 * 1024


def framing(headers):
    """Validate raw field multiplicity BEFORE http.client normalizes framing.

    No TE is supported (including TE+CL); never turn ambiguous upstream bytes
    into a seemingly valid fixed-length decoder response. Missing CL remains
    close-delimited and cannot satisfy the strict decoder contract.
    """
    lengths = [v for k, v in headers if k.lower() == 'content-length']
    if any(k.lower() == 'transfer-encoding' for k, _ in headers):
        raise ValueError('unsupported transfer encoding')
    if len(lengths) > 1 or (lengths and not re.fullmatch(r'[0-9]+', lengths[0])):
        raise ValueError('invalid or duplicate content length')
    nominated = {v.strip().lower() for k, value in headers if k.lower() == 'connection'
                 for v in value.split(',')}
    if 'content-length' in nominated:
        raise ValueError('connection nominates framing')
    return lengths[0] if lengths else None


def authorized(headers, query, key, password):
    params = urllib.parse.parse_qs(query)
    token = headers.get('X-Plex-Token', '') or params.get('X-Plex-Token', [''])[0]
    if token and hmac.compare_digest(token, key):
        return True
    basic = headers.get('Authorization', '')
    if basic.startswith('Basic '):
        try:
            supplied = base64.b64decode(basic[6:], validate=True).decode()
            return hmac.compare_digest(supplied, 'proof:' + password)
        except (ValueError, UnicodeError):
            pass
    return False


def native_agent_discovery(method, parsed):
    return (method == 'GET' and parsed.path == '/system/agents'
            and urllib.parse.parse_qs(parsed.query, keep_blank_values=True) == {'mediaType': ['1']})


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        pass

    def error(self, status):
        self.send_response(status)
        if status == 401:
            self.send_header('WWW-Authenticate', 'Basic realm="isolated-local-unclaimed-proof"')
        self.send_header('Content-Length', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

    def forward(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith('/') or parsed.path.startswith('//'):
            self.error(400)
            return
        if parsed.path == '/proof-health' and self.command == 'GET':
            target, headers, payload = '/identity', {}, None
        else:
            if not authorized(self.headers, parsed.query, self.server.access_key, self.server.password):
                self.error(401)
                return
            # Narrow read-only native agent discovery; no agent/plugin writes.
            discovery = native_agent_discovery(self.command, parsed)
            if parsed.path.startswith(('/myplex', '/updater', '/system/agents', '/:/plugins')) and not discovery:
                self.error(403)
                return
            params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            params = [(k, v) for k, v in params if k.lower() != 'x-plex-token']
            target = parsed.path + ('?' + urllib.parse.urlencode(params) if params else '')
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS | {'host', 'authorization', 'x-plex-token', 'forwarded', 'x-forwarded-for', 'x-real-ip'}}
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                self.error(400)
                return
            if not 0 <= length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                self.error(413)
                return
            payload = self.rfile.read(length) if length else None
            if self.headers.get('Upgrade', '').lower() == 'websocket':
                self.websocket(target, headers)
                return
        connection = http.client.HTTPConnection('127.0.0.1', 32400, timeout=30)
        try:
            connection.request(self.command, target, body=payload, headers=headers)
            response = connection.getresponse()
            length = framing(response.getheaders())
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS | {'x-plex-token', 'content-length'}:
                    self.send_header(key, value)
            if length is not None:
                self.send_header('Content-Length', length)
            self.send_header('Connection', 'close')
            self.end_headers()
            while True:
                block = response.read(65536)
                if not block:
                    break
                self.wfile.write(block)
        except (OSError, ValueError, http.client.HTTPException):
            self.close_connection = True
        finally:
            connection.close()
        self.close_connection = True

    def websocket(self, target, headers):
        # Local-only WebSocket tunnel lets Tautulli observe genuine Plex notifications.
        # Fixed destination and 180s idle bound; never forwards proof auth upstream.
        upstream = socket.create_connection(('127.0.0.1', 32400), timeout=15)
        try:
            headers.update({'Host': '127.0.0.1:32400', 'Connection': 'Upgrade', 'Upgrade': 'websocket'})
            request = 'GET ' + target + ' HTTP/1.1\r\n' + ''.join(k + ': ' + v + '\r\n' for k, v in headers.items()) + '\r\n'
            upstream.sendall(request.encode())
            self.wfile.flush()
            for _ in range(360):
                ready, _, _ = select.select([self.connection, upstream], [], [], 0.5)
                for source in ready:
                    payload = source.recv(65536)
                    if not payload:
                        return
                    (upstream if source is self.connection else self.connection).sendall(payload)
        finally:
            upstream.close()
            self.close_connection = True

    do_GET = forward
    do_POST = forward
    do_PUT = forward
    do_DELETE = forward
    do_PATCH = forward
    do_HEAD = forward


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--password-file', required=True, type=Path)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('0.0.0.0', 33240), Handler)
    server.access_key = args.key_file.read_text().strip()
    server.password = args.password_file.read_text().strip()
    server.serve_forever()


if __name__ == '__main__':
    main()
