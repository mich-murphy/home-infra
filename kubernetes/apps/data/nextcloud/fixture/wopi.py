#!/usr/bin/env python3
"""Bounded, single-document WOPI host fixture. NOT Nextcloud or WOPI conformance.
No request logging: access tokens are query parameters in the WOPI protocol.
"""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit

MAX_BYTES = 1024 * 1024
INITIAL = b'Synthetic WOPI proof document\n'


class Host:
    def __init__(self, root, token):
        if not token:
            raise ValueError('fresh private proof token required')
        self.token = token
        self.path = Path(root) / 'proof.txt'
        if not self.path.exists():
            self.path.write_bytes(INITIAL)
        self.lock = ''
        self.lock_expires = 0
        self.events = []

    def event(self, name):
        self.events.append(name)
        self.events = self.events[-128:]

    def current_lock(self):
        if time.monotonic() > self.lock_expires:
            self.lock = ''
        return self.lock

    def version(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def handler(host):
    class WOPI(BaseHTTPRequestHandler):
        server_version = 'ProofWOPI'

        def log_message(self, *args):
            pass

        def reply(self, status, body=b'', headers=None):
            if isinstance(body, dict):
                body = json.dumps(body).encode()
                headers = dict(headers or {}, **{'Content-Type':'application/json'})
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            query = parse_qs(urlsplit(self.path).query)
            supplied = query.get('access_token', [''])[0]
            return hmac.compare_digest(supplied, host.token)

        def conflict(self):
            host.event('lock-conflict')
            self.reply(409, headers={'X-WOPI-Lock':host.current_lock()})

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/healthz':
                return self.reply(200, b'ok')
            if not self.authorized():
                return self.reply(401)
            if path == '/wopi/files/proof':
                host.event('CheckFileInfo')
                return self.reply(200, {
                    'BaseFileName':'proof.txt', 'OwnerId':'synthetic-owner',
                    'UserId':'synthetic-editor', 'UserFriendlyName':'Synthetic Editor',
                    'Size':host.path.stat().st_size, 'Version':host.version(),
                    'UserCanWrite':True, 'ReadOnly':False, 'SupportsUpdate':True,
                    'SupportsLocks':True, 'SupportsGetLock':True,
                    'PostMessageOrigin':'https://collabora.proof.invalid',
                })
            if path == '/wopi/files/proof/contents':
                host.event('GetFile')
                return self.reply(200, host.path.read_bytes(), {'X-WOPI-ItemVersion':host.version()})
            if path == '/proof/evidence':
                return self.reply(200, {'events':host.events, 'sha256':host.version(),
                                        'bytes':host.path.stat().st_size})
            return self.reply(404)

        def do_POST(self):
            if not self.authorized():
                return self.reply(401)
            path = urlsplit(self.path).path
            op = self.headers.get('X-WOPI-Override', '')
            lock = self.headers.get('X-WOPI-Lock', '')
            active = host.current_lock()
            if path == '/wopi/files/proof/contents':
                # PutFile on an existing nonempty file requires the held lock.
                if not active or lock != active:
                    return self.conflict()
                try:
                    length = int(self.headers.get('Content-Length', '-1'))
                except ValueError:
                    return self.reply(400)
                if not 0 <= length <= MAX_BYTES:
                    return self.reply(413)
                data = self.rfile.read(length)
                if len(data) != length:
                    return self.reply(400)
                temporary = host.path.with_suffix('.partial')
                temporary.write_bytes(data)
                temporary.replace(host.path)
                host.event('PutFile')
                return self.reply(200, headers={'X-WOPI-ItemVersion':host.version()})
            if path != '/wopi/files/proof':
                return self.reply(404)
            if op == 'GET_LOCK':
                host.event('GetLock')
                return self.reply(200, headers={'X-WOPI-Lock':active})
            if op not in ('LOCK','REFRESH_LOCK','UNLOCK'):
                return self.reply(501)
            if not lock or len(lock) > 1024:
                return self.reply(400)
            old = self.headers.get('X-WOPI-OldLock')
            if op == 'LOCK':
                if old is not None:
                    if active != old:
                        return self.conflict()
                elif active and active != lock:
                    return self.conflict()
                host.lock = lock
                host.lock_expires = time.monotonic() + 1800
            elif not active or active != lock:
                return self.conflict()
            elif op == 'UNLOCK':
                host.lock = ''
                host.lock_expires = 0
            else:
                host.lock_expires = time.monotonic() + 1800
            host.event(op)
            return self.reply(200)
    return WOPI


if __name__ == '__main__':
    os.umask(0o077)
    host = Host('/data', os.environ['NEXTCLOUD_ADMIN_PASSWORD'])
    HTTPServer(('0.0.0.0',8082),handler(host)).serve_forever()
