#!/usr/bin/env python3
"""Bounded synthetic functional/recovery checks. Called only by lease-gated lifecycle.
Port-forward intentionally tests functionality, NOT NetworkPolicy or gateway acceptance.
"""
import base64
import contextlib
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import importlib.util
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

GROUP, STATE = sys.argv[1:]
NS = 'proof-' + GROUP
CREDS = json.loads((Path(STATE) / 'credentials.json').read_text())[GROUP]
RESULT = {'group': GROUP, 'checks': [], 'limitations': ['Functional HTTP uses local API port-forward; does not prove NetworkPolicy or gateway routing.']}


class ProofTLSConnection(http.client.HTTPSConnection):
    def connect(self):
        if not self.host.endswith('.proof.invalid'):
            raise RuntimeError('non-proof TLS target forbidden')
        sock = socket.create_connection(('127.0.0.1', int(os.environ.get('TALOS_PROOF_GATEWAY_PORT', '18443'))), timeout=self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class ProofTLSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(ProofTLSConnection, req, context=self._context)


CA = os.environ.get('TALOS_PROOF_GATEWAY_CA')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), ProofTLSHandler(context=ssl.create_default_context(cafile=CA) if CA else ssl.create_default_context()))

def k(*args, data=None):
    r = subprocess.run(['kubectl', '-n', NS, *args], input=data, capture_output=True, timeout=660)
    if r.returncode:
        raise RuntimeError('cluster command failed (details withheld to protect credentials)')
    return r.stdout


def execute(app, command, data=None):
    return k('exec', '-i', 'deployment/' + app, '--', *command, data=data)


def check(label, condition=True):
    if not condition:
        raise RuntimeError(label)
    RESULT['checks'].append(label)


def restart(app):
    k('rollout', 'restart', 'deployment/' + app)
    k('rollout', 'status', 'deployment/' + app, '--timeout=600s')


@contextlib.contextmanager
def forwarded(app, target):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    if os.environ.get('TALOS_PROOF_GATEWAY_CA') and app in ('nextcloud','collabora','immich','miniflux','wallabag','couchdb','pocket-id'):
        RESULT['checks'].append('TLS Gateway route selected: ' + app + '.proof.invalid')
        yield 'https://' + app + '.proof.invalid'
        return
    p = subprocess.Popen(['kubectl', '-n', NS, 'port-forward', 'service/' + app, f'{port}:{target}', '--address=127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                if p.poll() is not None:
                    raise RuntimeError('port-forward failed')
                time.sleep(.1)
        else:
            raise RuntimeError('port-forward timeout')
        yield f'http://127.0.0.1:{port}'
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def http(base, path, method='GET', body=None, auth=None, headers=None, raw=False):
    h = dict(headers or {})
    if auth:
        h['Authorization'] = 'Basic ' + base64.b64encode(auth.encode()).decode()
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
        h['Content-Type'] = 'application/json'
    if isinstance(body, str):
        body = body.encode()
    req = urllib.request.Request(base + path, data=body, headers=h, method=method)
    with OPENER.open(req, timeout=90) as response:
        data = response.read()
    if raw or not data:
        return data
    return json.loads(data)


def postgres_restore(app_user):
    marker = uuid.uuid4().hex
    execute('postgres', ['psql', '-U', app_user, '-d', app_user, '-v', 'ON_ERROR_STOP=1', '-c', f"CREATE TABLE IF NOT EXISTS proof_roundtrip (marker text PRIMARY KEY); INSERT INTO proof_roundtrip VALUES ('{marker}');"])
    dump = execute('postgres', ['pg_dump', '-U', app_user, '-d', app_user, '-Fc'])
    path = Path(STATE) / (GROUP + '-postgres.dump')
    with open(path, 'wb') as f:
        os.chmod(path, 0o600)
        f.write(dump)
    execute('postgres', ['dropdb', '-U', app_user, '--if-exists', 'proof_restore'])
    execute('postgres', ['createdb', '-U', app_user, 'proof_restore'])
    execute('postgres', ['pg_restore', '-U', app_user, '-d', 'proof_restore', '--exit-on-error'], dump)
    value = execute('postgres', ['psql', '-U', app_user, '-d', 'proof_restore', '-Atc', f"SELECT marker FROM proof_roundtrip WHERE marker='{marker}'"]).decode().strip()
    check('full PostgreSQL dump restored into independent proof_restore database with exact sentinel', value == marker)
    execute('postgres', ['dropdb', '-U', app_user, 'proof_restore'])
    RESULT['backup_sha256'] = hashlib.sha256(dump).hexdigest()


def nextcloud():
    data = b'Synthetic proof WebDAV payload\n' + uuid.uuid4().hex.encode()
    path = '/remote.php/dav/files/proof/proof-' + uuid.uuid4().hex + '.txt'
    auth = 'proof:' + CREDS['NEXTCLOUD_ADMIN_PASSWORD']
    with forwarded('nextcloud', 80) as base:
        http(base, path, 'PUT', data, auth=auth, raw=True)
        check('authenticated WebDAV PUT/GET exact bytes', http(base, path, auth=auth, raw=True) == data)
    restart('nextcloud')
    with forwarded('nextcloud', 80) as base:
        check('WebDAV content survives Nextcloud pod replacement', http(base, path, auth=auth, raw=True) == data)
        http(base, path, 'DELETE', auth=auth, raw=True)
    postgres_restore('nextcloud')
    restart('postgres')
    with forwarded('nextcloud', 80) as base:
        check('Nextcloud remains installed after PostgreSQL pod replacement', http(base, '/status.php')['installed'])
    # One bounded execution, not an unsuspended recurring schedule.
    execute('nextcloud', ['su', '-s', '/bin/sh', 'www-data', '-c', 'php -f /var/www/html/cron.php'])
    check('Nextcloud cron.php completes under proof credentials')
    with forwarded('collabora', 9980) as base:
        discovery = http(base, '/hosting/discovery', raw=True)
        check('Collabora WOPI discovery advertises actions', b'<action' in discovery)
    RESULT['limitations'].append('Collabora discovery is not an interactive document editing proof; richdocuments app is not fetched from Internet. WOPI edit/callback remains untested.')


def miniflux():
    auth = 'proof:' + CREDS['ADMIN_PASSWORD']
    with forwarded('miniflux', 8080) as base:
        cat = http(base, '/v1/categories', 'POST', {'title': 'Proof-' + uuid.uuid4().hex}, auth)['id']
        feed = http(base, '/v1/feeds', 'POST', {'feed_url':'http://fixture:8081/feed.xml', 'category_id':cat}, auth)['feed_id']
        entries = http(base, f'/v1/feeds/{feed}/entries', auth=auth)['entries']
        check('Miniflux fetches synthetic RSS over explicitly allowed fixture flow', any(e['title'] == 'Proof article' for e in entries))
        entry = entries[0]['id']
        http(base, '/v1/entries', 'PUT', {'entry_ids':[entry], 'status':'read'}, auth)
        check('Miniflux entry update persists', http(base, f'/v1/entries/{entry}', auth=auth)['status'] == 'read')
    restart('postgres')
    with forwarded('miniflux', 8080) as base:
        check('Miniflux feed survives PostgreSQL pod replacement', http(base, f'/v1/feeds/{feed}', auth=auth)['id'] == feed)
        http(base, f'/v1/feeds/{feed}', 'DELETE', auth=auth)
        http(base, f'/v1/categories/{cat}', 'DELETE', auth=auth)
    check('Miniflux feed/category CRUD completed')
    postgres_restore('miniflux')


def wallabag():
    # The image initially creates wallabag/wallabag. Rotate before functional test.
    execute('wallabag', ['sh', '-ec', 'cd /var/www/wallabag; php bin/console fos:user:change-password wallabag "$PROOF_ADMIN_PASSWORD" --no-interaction'])
    marker = 'proof-' + uuid.uuid4().hex
    fixture = [{'is_archived':0, 'is_starred':0, 'title':marker, 'url':'http://fixture:8081/article.html?' + marker,
                'content':'<p>Synthetic proof content</p>', 'tags':[], 'created_at':'2026-01-01T00:00:00+00:00'}]
    execute('wallabag', ['sh', '-ec', 'umask 077; cat > /tmp/proof-import.json'], json.dumps(fixture).encode())
    execute('wallabag', ['sh', '-ec', 'cd /var/www/wallabag; php bin/console wallabag:import wallabag /tmp/proof-import.json --importer=v2 --disableContentUpdate --no-interaction; php bin/console wallabag:export wallabag /tmp/proof-export.json --no-interaction'])
    exported = json.loads(execute('wallabag', ['php', '-r', 'echo file_get_contents("/tmp/proof-export.json");']))
    check('Wallabag imports synthetic entry and exports exact title/content', any(e.get('title') == marker and 'Synthetic proof content' in e.get('content','') for e in exported))
    restart('mariadb')
    execute('wallabag', ['sh', '-ec', 'cd /var/www/wallabag; php bin/console wallabag:export wallabag /tmp/proof-export.json --no-interaction'])
    exported = json.loads(execute('wallabag', ['php', '-r', 'echo file_get_contents("/tmp/proof-export.json");']))
    check('Wallabag entry survives MariaDB pod replacement', any(e.get('title') == marker for e in exported))
    RESULT['limitations'].append('Wallabag CLI import/export is tested; OAuth API/browser login and URL extraction are separate untested acceptance gates.')


def couchdb():
    auth = 'proof:' + CREDS['COUCHDB_PASSWORD']
    db = 'proof_' + uuid.uuid4().hex
    marker = uuid.uuid4().hex
    with forwarded('couchdb', 5984) as base:
        http(base, '/' + db, 'PUT', auth=auth)
        http(base, '/' + db + '/document', 'PUT', {'marker':marker}, auth)
        check('CouchDB authenticated document create/read', http(base, '/' + db + '/document', auth=auth)['marker'] == marker)
    restart('couchdb')
    with forwarded('couchdb', 5984) as base:
        check('CouchDB document survives pod replacement', http(base, '/' + db + '/document', auth=auth)['marker'] == marker)
        http(base, '/' + db, 'DELETE', auth=auth)


def png():
    def chunk(t, b):
        return struct.pack('!I', len(b)) + t + b + struct.pack('!I', zlib.crc32(t+b) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 2, 2, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\x00\xff\x00' * 2)) + chunk(b'IEND', b'')


def immich():
    password = CREDS['PROOF_ADMIN_PASSWORD']
    payload = png()
    with forwarded('immich', 2283) as base:
        try:
            login = http(base, '/api/auth/login', 'POST', {'email':'proof@example.invalid', 'password':password})
        except urllib.error.HTTPError as e:
            if e.code not in (400, 401):
                raise
            http(base, '/api/auth/admin-sign-up', 'POST', {'email':'proof@example.invalid','password':password,'name':'Synthetic Proof'})
            login = http(base, '/api/auth/login', 'POST', {'email':'proof@example.invalid', 'password':password})
        headers = {'Authorization':'Bearer ' + login['accessToken']}
        boundary = 'proof' + uuid.uuid4().hex
        body = bytearray()
        for key, value in {'deviceAssetId':uuid.uuid4().hex, 'deviceId':'proof', 'fileCreatedAt':'2026-01-01T00:00:00.000Z', 'fileModifiedAt':'2026-01-01T00:00:00.000Z', 'isFavorite':'false'}.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="assetData"; filename="proof.png"\r\nContent-Type: image/png\r\n\r\n'.encode())
        body.extend(payload + f'\r\n--{boundary}--\r\n'.encode())
        asset = http(base, '/api/assets', 'POST', bytes(body), headers=dict(headers, **{'Content-Type':'multipart/form-data; boundary='+boundary}))['id']
        check('Immich synthetic PNG upload/original download exact bytes', http(base, '/api/assets/' + asset + '/original', headers=headers, raw=True) == payload)
    restart('immich')
    with forwarded('immich', 2283) as base:
        check('Immich original survives pod replacement on /data PVC', http(base, '/api/assets/' + asset + '/original', headers=headers, raw=True) == payload)
    postgres_restore('immich')
    with forwarded('ml', 3003) as base:
        check('Immich ML ping responds', bool(http(base, '/ping', raw=True)))
    RESULT['limitations'].append('ML inference/model downloads, facial recognition and GPU acceleration are NOT proved; Internet egress intentionally denied and cache initially empty.')


def pocket_id():
    with forwarded('pocket-id', 1411) as base:
        doc = http(base, '/.well-known/openid-configuration')
        check('Pocket-ID OIDC discovery has isolated issuer', doc['issuer'] == 'https://pocket-id.proof.invalid')
        check('Pocket-ID advertises authorization/token/JWKS endpoints', all(doc.get(k) for k in ['authorization_endpoint','token_endpoint','jwks_uri']))
        path = urllib.parse.urlsplit(doc['jwks_uri']).path
        check('Pocket-ID public JWKS returns signing keys', bool(http(base, path)['keys']))
    restart('pocket-id')
    with forwarded('pocket-id', 1411) as base:
        check('Pocket-ID discovery survives SQLite PVC pod replacement', http(base, '/.well-known/openid-configuration')['issuer'] == doc['issuer'])
    RESULT['limitations'].append('Interactive administrator bootstrap, WebAuthn/passkey enrollment, OIDC authorization-code/token flow and user persistence require human browser ceremony; NOT proved by discovery/JWKS.')


def main():
    os.umask(0o077)
    try:
        spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).resolve().parents[1] / 'scripts/talos-proof-data.py')
        life = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(life)
        life.lease(GROUP)
        if not os.environ.get('TALOS_PROOF_GATEWAY_CA'):
            raise RuntimeError('verified Gateway TLS CA required for integrated frontend tests')
        RESULT['limitations'][0] = 'Frontend tests use verified TLS Gateway; backend-only ML ping uses API port-forward. Negative isolation/drop-verdict tests remain a platform acceptance gate.'
        globals()[GROUP.replace('-', '_')]()
        RESULT['status'] = 'functional-checks-passed-with-limitations'
    except Exception as e:
        RESULT['status'] = 'failed'
        # Error bodies can contain tokens, usernames or secrets. Keep evidence sanitized.
        RESULT['failure_type'] = type(e).__name__
    path = Path(STATE) / (GROUP + '-result.json')
    path.write_text(json.dumps(RESULT, indent=2) + '\n')
    os.chmod(path, 0o600)
    print(json.dumps(RESULT, indent=2))
    if RESULT['status'] == 'failed':
        sys.exit(1)


if __name__ == '__main__':
    main()
