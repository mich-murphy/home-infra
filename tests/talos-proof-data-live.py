#!/usr/bin/env python3
"""Bounded synthetic functional/recovery checks. Called only by lease-gated lifecycle.
Frontend checks use verified integrated TLS Gateway; backend exec/ML uses API.
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
import io
import zipfile

GROUP = STATE = NS = None
CREDS = None
LIFE = None
STATEPATH = None
CURRENT_STAGE = 'lease/private-state validation'
RESULT = None


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
    LIFE.lease(GROUP)
    r = subprocess.run(['kubectl', '-n', NS, *args], input=data, capture_output=True, timeout=660)
    if r.returncode:
        raise RuntimeError('cluster command failed (details withheld to protect credentials)')
    return r.stdout


def execute(app, command, data=None):
    global CURRENT_STAGE
    CURRENT_STAGE = 'exec ' + app + ' ' + command[0]
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
    LIFE.lease(GROUP)
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
    global CURRENT_STAGE
    CURRENT_STAGE = method + ' ' + urllib.parse.urlsplit(base).hostname + path.split('?')[0]
    req = urllib.request.Request(base + path, data=body, headers=h, method=method)
    for attempt in range(30):
        try:
            with OPENER.open(req, timeout=90) as response:
                data = response.read()
            break
        except urllib.error.HTTPError as error:
            if method not in ('GET','PUT','DELETE') or error.code not in (502,503,504) or attempt==29:
                raise
            time.sleep(1)
    else:
        raise RuntimeError('Gateway did not converge within bounded retry window')
    if raw or not data:
        return data
    return json.loads(data)


def save_private(name, data):
    path = LIFE.no_symlinks(STATEPATH / name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
    return path


def scale(app, replicas):
    k('scale', 'deployment/' + app, '--replicas=' + str(replicas))
    if replicas:
        k('rollout', 'status', 'deployment/' + app, '--timeout=600s')
    else:
        k('wait', '--for=delete', 'pod', '-l', 'app.kubernetes.io/name=' + app, '--timeout=180s')


@contextlib.contextmanager
def fresh_pvc(app, dependents=(), bootstrap=False):
    """Sequentially replace one data PVC with a newly provisioned claim, restoring
    the original binding in finally. No concurrent database or duplicate frontend.
    Retain both PVCs for audit; never delete source storage.
    """
    deployment = json.loads(k('get','deployment',app,'-o','json'))
    volumes = deployment['spec']['template']['spec']['volumes']
    index = next(i for i,v in enumerate(volumes) if v.get('name') == 'data' and 'persistentVolumeClaim' in v)
    old = volumes[index]['persistentVolumeClaim']['claimName']
    old_claim = json.loads(k('get','pvc',old,'-o','json'))
    name = app + '-restore-' + uuid.uuid4().hex[:12]
    spec = {key:old_claim['spec'][key] for key in ('accessModes','storageClassName','resources')}
    claim = {'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':name,'namespace':NS,'labels':{'app.kubernetes.io/part-of':'talos-proof','proof-purpose':'clean-restore'}},'spec':spec}
    k('apply','-f','-',data=json.dumps(claim).encode())
    path = '/spec/template/spec/volumes/' + str(index) + '/persistentVolumeClaim/claimName'
    switched = False
    original_container = deployment['spec']['template']['spec']['containers'][0] if bootstrap else None
    runtime_restored = False
    def restore_runtime():
        nonlocal runtime_restored
        if bootstrap and not runtime_restored:
            k('patch','deployment',app,'--type=json','-p',json.dumps([{'op':'replace','path':'/spec/template/spec/containers/0','value':original_container}]))
            k('rollout','status','deployment/'+app,'--timeout=600s')
            runtime_restored = True
    try:
        for frontend in dependents:
            scale(frontend,0)
        scale(app,0)
        k('patch','deployment',app,'--type=json','-p',json.dumps([{'op':'replace','path':path,'value':name}]))
        switched = True
        if bootstrap:
            container = json.loads(json.dumps(original_container))
            container['command'] = ['/bin/sh','-c','sleep 1800']
            container.pop('args',None)
            for probe in ('startupProbe','readinessProbe','livenessProbe'):
                container[probe] = {'exec':{'command':['/bin/sh','-c','test -d '+container['volumeMounts'][0]['mountPath']]},'periodSeconds':2,'timeoutSeconds':2,'failureThreshold':30}
            k('patch','deployment',app,'--type=json','-p',json.dumps([{'op':'replace','path':'/spec/template/spec/containers/0','value':container}]))
        scale(app,1)
        new_claim = json.loads(k('get','pvc',name,'-o','json'))
        check('clean restore uses distinct fresh PVC UID and PV: ' + app,
              new_claim['metadata']['uid'] != old_claim['metadata']['uid'] and
              new_claim['spec'].get('volumeName') and new_claim['spec'].get('volumeName') != old_claim['spec'].get('volumeName'))
        RESULT.setdefault('restore_volumes',[]).append({'app':app,'source_pvc':old,'source_uid':old_claim['metadata']['uid'],'restored_pvc':name,'restored_uid':new_claim['metadata']['uid'],'restored_pv':new_claim['spec']['volumeName']})
        yield restore_runtime
    finally:
        if switched:
            for frontend in dependents:
                scale(frontend,0)
            scale(app,0)
            if bootstrap:
                k('patch','deployment',app,'--type=json','-p',json.dumps([{'op':'replace','path':'/spec/template/spec/containers/0','value':original_container}]))
            k('patch','deployment',app,'--type=json','-p',json.dumps([{'op':'replace','path':path,'value':old}]))
            scale(app,1)
        for frontend in dependents:
            scale(frontend,1)


def postgres_dump(app_user):
    dump = execute('postgres',['pg_dump','-U',app_user,'-d',app_user,'-Fc'])
    save_private(GROUP + '-postgres.dump',dump)
    RESULT['backup_sha256'] = hashlib.sha256(dump).hexdigest()
    return dump


def clean_postgres_restore(app_user, dump):
    # Must run while fresh_pvc(postgres) is active and frontend is stopped.
    count = execute('postgres',['psql','-U',app_user,'-d',app_user,'-Atc',"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"]).decode().strip()
    check('clean PostgreSQL PVC contains no source public tables before restore',count == '0')
    execute('postgres',['pg_restore','-U',app_user,'-d',app_user,'--exit-on-error'],dump)
    check('full PostgreSQL logical backup restores into clean PVC cluster')


def postgres_restore(app_user):
    marker = uuid.uuid4().hex
    execute('postgres', ['psql', '-U', app_user, '-d', app_user, '-v', 'ON_ERROR_STOP=1', '-c', f"CREATE TABLE IF NOT EXISTS proof_roundtrip (marker text PRIMARY KEY); INSERT INTO proof_roundtrip VALUES ('{marker}');"])
    dump = execute('postgres', ['pg_dump', '-U', app_user, '-d', app_user, '-Fc'])
    save_private(GROUP + '-postgres.dump', dump)
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
        content_hash = hashlib.sha256(entries[0]['content'].encode()).hexdigest()
        http(base, '/v1/entries', 'PUT', {'entry_ids':[entry], 'status':'read'}, auth)
        check('Miniflux entry update persists', http(base, f'/v1/entries/{entry}', auth=auth)['status'] == 'read')
    restart('postgres')
    with forwarded('miniflux', 8080) as base:
        check('Miniflux feed survives PostgreSQL pod replacement', http(base, f'/v1/feeds/{feed}', auth=auth)['id'] == feed)
    scale('miniflux',0)
    try:
        dump = postgres_dump('miniflux')
        with fresh_pvc('postgres', ('miniflux',)):
            clean_postgres_restore('miniflux',dump)
            scale('miniflux',1)
            with forwarded('miniflux',8080) as base:
                restored = http(base,f'/v1/entries/{entry}',auth=auth)
                check('Miniflux authenticated application entry/read-state/content SHA256 match after clean-PVC restore', restored['status']=='read' and hashlib.sha256(restored['content'].encode()).hexdigest()==content_hash)
    finally:
        scale('miniflux',1)
    with forwarded('miniflux',8080) as base:
        http(base, f'/v1/feeds/{feed}', 'DELETE', auth=auth)
        http(base, f'/v1/categories/{cat}', 'DELETE', auth=auth)
    check('Miniflux feed/category CRUD completed')


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
    scale('wallabag',0)
    try:
        dump = execute('mariadb',['sh','-ec','exec mariadb-dump --single-transaction --routines --triggers --events -uroot -p"$MYSQL_ROOT_PASSWORD" --databases wallabag'])
        save_private('wallabag-mariadb.sql',dump)
        RESULT['backup_sha256'] = hashlib.sha256(dump).hexdigest()
        with fresh_pvc('mariadb',('wallabag',)):
            execute('mariadb',['sh','-ec','exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD"'],dump)
            scale('wallabag',1)
            execute('wallabag',['sh','-ec','cd /var/www/wallabag; php bin/console wallabag:export wallabag /tmp/proof-export.json --no-interaction'])
            restored = json.loads(execute('wallabag',['php','-r','echo file_get_contents("/tmp/proof-export.json");']))
            check('Wallabag entry title/content survive logical MariaDB restore into clean PVC',any(e.get('title')==marker and 'Synthetic proof content' in e.get('content','') for e in restored))
    finally:
        scale('wallabag',1)
    RESULT['limitations'].append('Wallabag OAuth API/browser login and URL extraction remain separate acceptance gates.')


def couchdb():
    auth = 'proof:' + CREDS['COUCHDB_PASSWORD']
    db = 'proof_' + uuid.uuid4().hex
    marker = uuid.uuid4().hex
    with forwarded('couchdb', 5984) as base:
        try:
            http(base, '/_all_dbs', raw=True)
        except urllib.error.HTTPError as error:
            check('CouchDB unauthenticated database access denied with HTTP401',error.code==401)
        else:
            check('CouchDB rejects unauthenticated database access',False)
        http(base, '/' + db, 'PUT', auth=auth)
        http(base, '/' + db + '/document', 'PUT', {'marker':marker}, auth)
        check('CouchDB authenticated document create/read', http(base, '/' + db + '/document', auth=auth)['marker'] == marker)
    restart('couchdb')
    with forwarded('couchdb', 5984) as base:
        check('CouchDB document survives pod replacement', http(base, '/' + db + '/document', auth=auth)['marker'] == marker)
        rows = http(base,'/' + db + '/_all_docs?include_docs=true',auth=auth)['rows']
        docs = [{k:v for k,v in r['doc'].items() if k!='_rev'} for r in rows]
        backup = json.dumps(docs,sort_keys=True).encode()
        save_private('couchdb-documents.json',backup)
        RESULT['backup_sha256'] = hashlib.sha256(backup).hexdigest()
    with fresh_pvc('couchdb'):
        with forwarded('couchdb',5984) as base:
            databases = http(base,'/_all_dbs',auth=auth)
            check('fresh CouchDB PVC has no source proof database before restore',db not in databases)
            http(base,'/'+db,'PUT',auth=auth)
            responses = http(base,'/'+db+'/_bulk_docs','POST',{'docs':docs},auth=auth)
            check('CouchDB logical bulk document restore has no errors',all(r.get('ok') for r in responses))
            restored = http(base,'/'+db+'/document',auth=auth)
            restored.pop('_rev',None)
            check('CouchDB restored application document exact canonical checksum',hashlib.sha256(json.dumps([restored],sort_keys=True).encode()).hexdigest()==RESULT['backup_sha256'])
        restart('couchdb')
        with forwarded('couchdb',5984) as base:
            check('CouchDB restored clean-PVC document survives second pod replacement',http(base,'/'+db+'/document',auth=auth)['marker']==marker)
    with forwarded('couchdb',5984) as base:
        http(base,'/'+db,'DELETE',auth=auth)


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


def pocket_browser():
    module = os.environ.get('TALOS_PROOF_PLAYWRIGHT_MODULE')
    if not module:
        raise RuntimeError('private pinned playwright-core module path required for virtual WebAuthn/OIDC proof')
    LIFE.lease(GROUP)
    public_pem = subprocess.run(['openssl','x509','-in',CA,'-pubkey','-noout'],capture_output=True,check=True).stdout
    public_der = subprocess.run(['openssl','pkey','-pubin','-outform','DER'],input=public_pem,capture_output=True,check=True).stdout
    pin = base64.b64encode(hashlib.sha256(public_der).digest()).decode()
    payload = {'state':str(STATEPATH),'module':module,'spki':pin,'port':int(os.environ.get('TALOS_PROOF_GATEWAY_PORT','18443'))}
    proc = subprocess.run(['node',str(Path(__file__).with_name('talos-proof-data-browser.mjs'))],input=json.dumps(payload).encode(),capture_output=True,timeout=300)
    result = json.loads(proc.stdout)
    RESULT.setdefault('browser_runs',[]).append(result)
    check('Virtual WebAuthn registration/login and cryptographically verified OIDC code flow',proc.returncode==0 and result.get('status')=='passed')
    return result


def pocket_id():
    with forwarded('pocket-id', 1411) as base:
        doc = http(base, '/.well-known/openid-configuration')
        check('Pocket-ID OIDC discovery has isolated issuer', doc['issuer'] == 'https://pocket-id.proof.invalid')
        check('Pocket-ID advertises authorization/token/JWKS endpoints', all(doc.get(k) for k in ['authorization_endpoint','token_endpoint','jwks_uri']))
        path = urllib.parse.urlsplit(doc['jwks_uri']).path
        check('Pocket-ID public JWKS returns signing keys', bool(http(base, path)['keys']))
    initial = pocket_browser()
    restart('pocket-id')
    after = pocket_browser()
    check('Pocket-ID user and registered passkey survive pod replacement',initial['user_id']==after['user_id'])
    archive = execute('pocket-id',['/app/pocket-id','export','--path','-'])
    with zipfile.ZipFile(io.BytesIO(archive)) as exported:
        check('Pocket-ID logical export contains database.json','database.json' in exported.namelist())
        database_hash = hashlib.sha256(exported.read('database.json')).hexdigest()
    save_private('pocket-id-logical-export.zip',archive)
    RESULT['backup_sha256'] = hashlib.sha256(archive).hexdigest()
    RESULT['database_export_sha256'] = database_hash
    with fresh_pvc('pocket-id', bootstrap=True) as start_runtime:
        # Sleeping bootstrap mounts a genuinely empty PVC without starting the
        # server/Francis host. Never use force-lock against a running instance.
        execute('pocket-id',['/app/pocket-id','import','--path','-','--yes'],archive)
        start_runtime()
        restored = pocket_browser()
        check('Pocket-ID clean-PVC logical restore preserves user/passkey and signed OIDC flow',restored['user_id']==initial['user_id'])

    RESULT['limitations'].append('CDP virtual authenticator proves WebAuthn protocol/cryptography, not human physical-device UX, device recovery or hardware attestation.')


def main():
    global LIFE, CREDS, STATEPATH, GROUP, STATE, NS, RESULT
    GROUP, STATE = sys.argv[1:]
    NS = 'proof-' + GROUP
    RESULT = {'group':GROUP, 'checks':[], 'limitations':['Frontend tests use verified TLS Gateway; backend-only ML ping uses API port-forward. Negative isolation/drop-verdict tests remain a platform acceptance gate.']}
    os.umask(0o077)
    try:
        spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).resolve().parents[1] / 'scripts/talos-proof-data.py')
        life = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(life)
        LIFE = life
        life.LEASE_GROUP = GROUP
        life.lease(GROUP)
        STATEPATH = life.private(STATE)
        credential_path = life.no_symlinks(STATEPATH / 'credentials.json')
        if not credential_path.exists():
            raise RuntimeError('prepared proof credentials required')
        CREDS = life.credentials(STATEPATH)[GROUP]
        if not os.environ.get('TALOS_PROOF_GATEWAY_CA'):
            raise RuntimeError('verified Gateway TLS CA required for integrated frontend tests')
        RESULT['limitations'][0] = 'Frontend tests use verified TLS Gateway; backend-only ML ping uses API port-forward. Negative isolation/drop-verdict tests remain a platform acceptance gate.'
        globals()[GROUP.replace('-', '_')]()
        RESULT['status'] = 'functional-checks-passed-with-limitations'
    except Exception as e:
        RESULT['status'] = 'failed'
        # Error bodies can contain tokens, usernames or secrets. Keep evidence sanitized.
        RESULT['failure_type'] = type(e).__name__
        RESULT['failed_stage'] = CURRENT_STAGE
        if isinstance(e, urllib.error.HTTPError):
            RESULT['http_status'] = e.code
    if STATEPATH is not None:
        path = LIFE.no_symlinks(STATEPATH / (GROUP + '-result.json'))
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(RESULT, f, indent=2)
    print(json.dumps(RESULT, indent=2))
    if RESULT['status'] == 'failed':
        sys.exit(1)


if __name__ == '__main__':
    main()
