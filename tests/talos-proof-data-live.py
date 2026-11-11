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
import math
import re
import xml.etree.ElementTree as ET
import zipfile

GROUP = STATE = NS = None
CREDS = None
LIFE = None
STATEPATH = None
CURRENT_STAGE = 'lease/private-state validation'
RESULT = None
STAGE = None


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
    memory_snapshot(app, "before replacement")
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


def memory_snapshot(app, reason):
    """Read cgroup v2 before deleting each observed container; no cache/anon conflation."""
    try:
        raw = k('exec', 'deployment/' + app, '--', 'sh', '-ec',
                'for f in memory.current memory.peak memory.events memory.stat; do '
                'echo "FILE:$f"; test ! -r /sys/fs/cgroup/$f || head -c 16384 /sys/fs/cgroup/$f; done')
        sections = {}
        current = None
        for line in raw.decode().splitlines():
            if line.startswith('FILE:'):
                current = line[5:]
                sections[current] = {}
            elif current:
                fields = line.split()
                if len(fields) == 1:
                    sections[current]['bytes'] = int(fields[0])
                elif len(fields) == 2:
                    sections[current][fields[0]] = int(fields[1])
        pods = json.loads(k('get','pods','-l','app.kubernetes.io/name='+app,'-o','json'))['items']
        RESULT.setdefault('memory_observations', []).append({
            'app':app, 'reason':reason, 'time':time.time(), 'cgroup':sections,
            'pods':[{'uid':p['metadata']['uid'],'containers':[{key:c[key] for key in ('name','image','imageID','containerID','restartCount','ready','started') if key in c} for c in p.get('status',{}).get('containerStatuses',[])]} for p in pods]})
    except Exception as error:
        RESULT.setdefault('memory_observation_gaps', []).append({'app':app,'reason':reason,'error':type(error).__name__})


def scale(app, replicas):
    if not replicas:
        memory_snapshot(app, 'before scale0')
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
                container[probe] = {'exec':{'command':['/bin/sh','-c','test -d '+next(m['mountPath'] for m in container['volumeMounts'] if m['name']=='data')]},'periodSeconds':2,'timeoutSeconds':2,'failureThreshold':30}
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


def authenticated_recovery(base,path,auth=None,headers=None):
    """Explicit positive recovery check after a known database/server replacement.
    Never used by denial assertions or as a blanket authentication retry.
    """
    transients=[]
    for attempt in range(30):
        try:
            value=http(base,path,auth=auth,headers=headers)
            if transients:
                RESULT.setdefault('recovery_transients',[]).append({'path':path,'statuses':transients,'recovered_within_seconds':attempt})
            return value
        except urllib.error.HTTPError as error:
            if error.code not in (401,500,502,503,504) or attempt==29:
                raise
            transients.append(error.code)
            time.sleep(1)
    raise RuntimeError('authenticated application did not recover within bounded window')


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


def wopi_browser():
    module = os.environ.get('TALOS_PROOF_PLAYWRIGHT_MODULE')
    if not module:
        raise RuntimeError('private pinned playwright-core module required')
    with forwarded('collabora',9980) as base:
        discovery = ET.fromstring(http(base,'/hosting/discovery',raw=True))
    actions = [a for a in discovery.iter('action') if a.get('name')=='edit' and a.get('ext')=='txt']
    check('real CODE discovery offers editable txt action',bool(actions))
    action = actions[0].attrib['urlsrc']
    # WOPI discovery uses optional <key=value&> substitution templates. Only
    # remove optional templates; never invent an editor URL or change its origin.
    action = re.sub(r'<[^<>]*>', '', action)
    check('discovered CODE editor retains exact public HTTPS origin',urllib.parse.urlsplit(action).scheme=='https' and urllib.parse.urlsplit(action).netloc=='collabora.proof.invalid')
    pem = subprocess.run(['openssl','x509','-in',CA,'-pubkey','-noout'],capture_output=True,check=True).stdout
    der = subprocess.run(['openssl','pkey','-pubin','-outform','DER'],input=pem,capture_output=True,check=True).stdout
    marker = 'WOPI-SAVED-' + uuid.uuid4().hex
    payload = {'state':str(STATEPATH),'module':module,'spki':base64.b64encode(hashlib.sha256(der).digest()).decode(),
        'port':int(os.environ.get('TALOS_PROOF_GATEWAY_PORT','18443')),'action':action,
        'source':'http://wopi-fixture.proof-nextcloud.svc.cluster.local:8082/wopi/files/proof',
        'token':CREDS['NEXTCLOUD_ADMIN_PASSWORD'],'marker':marker}
    proc = subprocess.run(['node',str(Path(__file__).with_name('talos-proof-data-wopi.mjs'))],
        input=json.dumps(payload).encode(),capture_output=True,timeout=240)
    browser = json.loads(proc.stdout)
    RESULT['wopi_browser'] = browser
    check('real CODE browser editor accepted input/save dispatch',proc.returncode==0)
    deadline = time.monotonic()+90
    while True:
        evidence = json.loads(execute('wopi-fixture',['python','-c',
            "import os,urllib.request,json,hashlib; from pathlib import Path; "
            "p=Path('/data/proof.txt').read_bytes(); "
            "r=json.load(urllib.request.urlopen('http://127.0.0.1:8082/proof/evidence?access_token='+os.environ['NEXTCLOUD_ADMIN_PASSWORD'])); "
            "r['marker_present']="+repr(marker)+".encode() in p; print(json.dumps(r))"]))
        if evidence['marker_present'] and 'PutFile' in evidence['events']:
            break
        if time.monotonic()>=deadline:
            check('real WOPI callback must save browser-entered marker',False)
        time.sleep(1)
    check('real CODE CheckFileInfo/GetFile/LOCK/PutFile callbacks save browser marker',
        all(event in evidence['events'] for event in ('CheckFileInfo','GetFile','LOCK','PutFile')))
    RESULT['wopi_saved_document'] = evidence
    RESULT['limitations'].append('Faithful single-file WOPI fixture + real CODE/browser edit/save ONLY, not Nextcloud/richdocuments integration, account authorization, multieditor, ODF formatting or production capacity.')


def nextcloud_ocs(base,path,auth,method='GET',fields=None):
    payload = urllib.parse.urlencode(fields).encode() if fields is not None else None
    response = http(base,'/ocs/v2.php/'+path+('\u0026' if '?' in path else '?')+'format=json',method,payload,auth,
        {'OCS-APIRequest':'true','Content-Type':'application/x-www-form-urlencoded'})['ocs']
    check('Nextcloud OCS '+method+' request accepted',response['meta']['statuscode'] in (100,200))
    return response['data']


def nextcloud_share(base,path,data,auth,users=None):
    if users is None:
        users = ['reader'+uuid.uuid4().hex[:12], 'outsider'+uuid.uuid4().hex[:12]]
        for user in users:
            password = hashlib.sha256((CREDS['NEXTCLOUD_ADMIN_PASSWORD']+user).encode()).hexdigest()
            nextcloud_ocs(base,'cloud/users',auth,'POST',{'userid':user,'password':password})
        nextcloud_ocs(base,'apps/files_sharing/api/v1/shares',auth,'POST',
            {'path':'/'+path.rsplit('/',1)[1],'shareType':0,'shareWith':users[0],'permissions':1})
    for index,user in enumerate(users):
        password=hashlib.sha256((CREDS['NEXTCLOUD_ADMIN_PASSWORD']+user).encode()).hexdigest()
        identity=nextcloud_ocs(base,'cloud/user',user+':'+password)
        check('distinct proof account authenticates independently',identity['id']==user)
        target='/remote.php/dav/files/'+user+'/'+path.rsplit('/',1)[1]
        if index==0:
            check('second proof user reads shared file exact bytes',http(base,target,auth=user+':'+password,raw=True)==data)
        else:
            for denied in (target,path):
                try: http(base,denied,auth=user+':'+password,raw=True)
                except urllib.error.HTTPError as error: check('authenticated third user denied private/shared file',error.code in (403,404))
                else: check('third-user ACL must deny access',False)
    return users


def nextcloud_maintenance(enabled):
    execute('nextcloud',['su','-s','/bin/sh','www-data','-c',
        'php /var/www/html/occ maintenance:mode --'+('on' if enabled else 'off')])


def nextcloud():
    if STAGE == 'wopi':
        wopi_browser()
        return
    if STAGE == 'collabora':
        with forwarded('collabora', 9980) as base:
            discovery = http(base, '/hosting/discovery', raw=True)
            check('Collabora WOPI discovery advertises actions', b'<action' in discovery)
        RESULT['limitations'].append('Discovery ONLY: no WOPI editing/callback or Nextcloud integration proved.')
        return
    if STAGE == 'cron':
        # Use the actual suspended declarative CronJob, not a web-container exec.
        job = 'nextcloud-cron-proof'
        try:
            k('create','job',job,'--from=cronjob/nextcloud-cron')
            k('wait','--for=condition=complete','job/'+job,'--timeout=200s')
            status = json.loads(k('get','job',job,'-o','json'))['status']
            check('bounded standalone CronJob succeeds with web stopped',status.get('succeeded') == 1 and not status.get('failed'))
            marker = execute('postgres',['psql','-U','nextcloud','-d','nextcloud','-Atc',
                "SELECT configvalue FROM oc_appconfig WHERE appid='core' AND configkey='lastcron'"]).decode().strip()
            check('cron updates persistent Nextcloud lastcron timestamp',marker.isdigit() and 0 <= time.time()-int(marker) < 240)
        finally:
            k('delete','job',job,'--ignore-not-found=true','--wait=true','--timeout=180s')
        return
    data = b'Synthetic proof WebDAV payload\n' + uuid.uuid4().hex.encode()
    path = '/remote.php/dav/files/proof/proof-' + uuid.uuid4().hex + '.txt'
    auth = 'proof:' + CREDS['NEXTCLOUD_ADMIN_PASSWORD']
    with forwarded('nextcloud', 80) as base:
        http(base, path, 'PUT', data, auth=auth, raw=True)
        check('authenticated WebDAV PUT/GET exact bytes', http(base, path, auth=auth, raw=True) == data)
        users = nextcloud_share(base,path,data,auth)
    restart('nextcloud')
    with forwarded('nextcloud', 80) as base:
        check('WebDAV content survives Nextcloud pod replacement', http(base, path, auth=auth, raw=True) == data)
    # Coordinated synthetic recovery point: maintenance stops HTTP mutations,
    # cron is suspended, then full HTML/config/apps/files archive + logical DB dump.
    nextcloud_maintenance(True)
    try:
        dump = postgres_dump('nextcloud')
        archive = execute('nextcloud',['tar','-czpf','-','-C','/var/www/html','.'])
        save_private('nextcloud-html-files.tar.gz',archive)
        RESULT['html_files_backup_sha256']=hashlib.sha256(archive).hexdigest()
        scale('nextcloud',0)
        with fresh_pvc('postgres', ('nextcloud',)):
            clean_postgres_restore('nextcloud',dump)
            with fresh_pvc('nextcloud',bootstrap=True) as start_runtime:
                empty=execute('nextcloud',['sh','-ec','test ! -e /var/www/html/config/config.php && test ! -e /var/www/html/data/.ocdata && echo clean'])
                check('clean independent HTML/files PVC has no source config/data',empty.strip()==b'clean')
                execute('nextcloud',['tar','-xzpf','-','-C','/var/www/html'],archive)
                start_runtime()
                nextcloud_maintenance(False)
                with forwarded('nextcloud',80) as base:
                    check('coordinated clean DB AND clean HTML/config/files PVCs restore exact WebDAV bytes',http(base,path,auth=auth,raw=True)==data)
                    nextcloud_share(base,path,data,auth,users)
    finally:
        scale('nextcloud',1)
        nextcloud_maintenance(False)
    restart('postgres')
    with forwarded('nextcloud',80) as base:
        check('source database reattached with same authenticated WebDAV bytes',http(base,path,auth=auth,raw=True)==data)
        http(base,path,'DELETE',auth=auth,raw=True)
        for user in users: nextcloud_ocs(base,'cloud/users/'+user,auth,'DELETE')
    RESULT['limitations'].append('Prepared coordinated synthetic DB+HTML/files clean-PVC restore, not historical production data or VM/disk-loss recovery. Version restore, trash recovery/rename, Redis contention and Nextcloud WOPI remain unimplemented acceptance gates. Cron requires its separate explicitly leased stage.')
    if STAGE == 'full':
        RESULT['limitations'].append('Full controller availability does not itself prove interactive Collabora editing.')


def miniflux():
    auth = 'proof:' + CREDS['ADMIN_PASSWORD']
    with forwarded('miniflux', 8080) as base:
        http(base, '/healthcheck', raw=True)
        cat = http(base, '/v1/categories', 'POST', {'title': 'Proof-' + uuid.uuid4().hex}, auth)['id']
        feed = http(base, '/v1/feeds', 'POST', {'feed_url':'http://fixture:8081/feed.xml?proof='+uuid.uuid4().hex, 'category_id':cat}, auth)['feed_id']
        entries = http(base, f'/v1/feeds/{feed}/entries', auth=auth)['entries']
        check('Miniflux fetches synthetic RSS over explicitly allowed fixture flow', any(e['title'] == 'Proof article' for e in entries))
        entry = entries[0]['id']
        content_hash = hashlib.sha256(entries[0]['content'].encode()).hexdigest()
        http(base, '/v1/entries', 'PUT', {'entry_ids':[entry], 'status':'read'}, auth)
        check('Miniflux entry update persists', http(base, f'/v1/entries/{entry}', auth=auth)['status'] == 'read')
    restart('postgres')
    with forwarded('miniflux', 8080) as base:
        check('Miniflux feed survives PostgreSQL pod replacement', authenticated_recovery(base, f'/v1/feeds/{feed}', auth=auth)['id'] == feed)
    scale('miniflux',0)
    try:
        dump = postgres_dump('miniflux')
        with fresh_pvc('postgres', ('miniflux',)):
            clean_postgres_restore('miniflux',dump)
            scale('miniflux',1)
            with forwarded('miniflux',8080) as base:
                restored = authenticated_recovery(base,f'/v1/entries/{entry}',auth=auth)
                check('Miniflux authenticated application entry/read-state/content SHA256 match after clean-PVC restore', restored['status']=='read' and hashlib.sha256(restored['content'].encode()).hexdigest()==content_hash)
    finally:
        scale('miniflux',1)
    with forwarded('miniflux',8080) as base:
        http(base, f'/v1/feeds/{feed}', 'DELETE', auth=auth)
        http(base, f'/v1/categories/{cat}', 'DELETE', auth=auth)
    check('Miniflux feed/category CRUD completed')


def wallabag():
    RESULT['limitations'].extend(['Proof-only exact fixture FQDN extractor private-IP exception; no general subnet/Internet exemption.', 'Synchronous capture tested; Redis queue/import-worker integration not claimed.'])
    execute('wallabag', ['sh', '-ec', 'cd /var/www/wallabag; php bin/console --env=prod fos:user:change-password wallabag "$PROOF_ADMIN_PASSWORD" --no-interaction'])
    client_path = LIFE.no_symlinks(STATEPATH/'wallabag-client.json')
    if client_path.exists():
        client=json.loads(client_path.read_text())
    else:
        # FOS's generic create-client CLI is incompatible with Wallabag's required
        # User constructor. Use the app's own Doctrine entity/owner, never SQL
        # schema guesses. Only this bootstrap is CLI; all functional CRUD is HTTP.
        code=r"""chdir('/var/www/wallabag'); require 'vendor/autoload.php'; require_once 'app/AppKernel.php'; $k=new AppKernel('prod',false);$k->boot();$e=$k->getContainer()->get('doctrine')->getManager();$u=$e->getRepository(\Wallabag\UserBundle\Entity\User::class)->findOneByUsername('wallabag');$c=new \Wallabag\ApiBundle\Entity\Client($u);$c->setName('Isolated proof');$c->setRedirectUris(['https://wallabag.proof.invalid/proof-callback']);$c->setAllowedGrantTypes(['password','refresh_token']);$e->persist($c);$e->flush();echo json_encode(['id'=>$c->getPublicId(),'secret'=>$c->getSecret()]);"""
        client=json.loads(execute('wallabag',['php','-r',code]))
        save_private('wallabag-client.json',json.dumps(client).encode())
    def login(base):
        payload=urllib.parse.urlencode({'grant_type':'password','client_id':client['id'],'client_secret':client['secret'],'username':'wallabag','password':CREDS['PROOF_ADMIN_PASSWORD']})
        token=http(base,'/oauth/v2/token','POST',payload,headers={'Content-Type':'application/x-www-form-urlencoded'})
        return {'Authorization':'Bearer '+token['access_token']}
    def api(base,path,method='GET',body=None,headers=None):
        h=dict(headers or {})
        if body is not None:
            body=urllib.parse.urlencode(body)
            h['Content-Type']='application/x-www-form-urlencoded'
        return http(base,path,method,body,headers=h)
    marker='proof-'+uuid.uuid4().hex
    with forwarded('wallabag',80) as base:
        http(base,'/api/info',raw=True)
        headers=login(base)
        created=api(base,'/api/entries.json','POST',{'url':'http://fixture.proof-wallabag.svc.cluster.local:8080/article.html?proof='+marker},headers)
        entry=created['id']
        original=api(base,f'/api/entries/{entry}.json',headers=headers)
        check('Wallabag OAuth password login and live fixture URL capture/extraction via trusted TLS Gateway','Synthetic proof content' in original['content'] and 'Proof article' in original['title'])
        content_hash=hashlib.sha256(original['content'].encode()).hexdigest()
        RESULT['article_content_sha256']=content_hash
        changed=api(base,f'/api/entries/{entry}.json','PATCH',{'archive':1,'starred':1,'title':marker},headers)
        check('Wallabag HTTP update/archive/star operations persist',changed['is_archived']==1 and changed['is_starred']==1 and changed['title']==marker)
    execute('wallabag',['sh','-ec','cd /var/www/wallabag; php bin/console --env=prod wallabag:export wallabag /tmp/proof-export.json --no-interaction'])
    exported=json.loads(execute('wallabag',['php','-r','echo file_get_contents("/tmp/proof-export.json");']))
    check('Wallabag export contains the HTTP-captured article and exact content SHA256',any(e.get('id')==entry and hashlib.sha256(e.get('content','').encode()).hexdigest()==content_hash for e in exported))
    restart('mariadb')
    with forwarded('wallabag',80) as base:
        restored=authenticated_recovery(base,f'/api/entries/{entry}.json',headers=headers)
        check('Wallabag HTTP article survives MariaDB pod replacement',restored['title']==marker)
    scale('wallabag',0)
    try:
        dump=execute('mariadb',['sh','-ec','exec mariadb-dump --single-transaction --routines --triggers --events -uroot -p"$MYSQL_ROOT_PASSWORD" --databases wallabag'])
        save_private('wallabag-mariadb.sql',dump)
        RESULT['backup_sha256']=hashlib.sha256(dump).hexdigest()
        with fresh_pvc('mariadb',('wallabag',)):
            execute('mariadb',['sh','-ec','exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD"'],dump)
            execute('mariadb',['sh','-ec',"mariadb -uroot -p\"$MYSQL_ROOT_PASSWORD\" -e \"CREATE USER IF NOT EXISTS 'wallabag'@'%' IDENTIFIED BY '$MARIADB_PASSWORD'; GRANT ALL PRIVILEGES ON wallabag.* TO 'wallabag'@'%';\""])
            scale('wallabag',1)
            with forwarded('wallabag',80) as base:
                http(base,'/api/info',raw=True)
                restored_headers=login(base)
                restored=authenticated_recovery(base,f'/api/entries/{entry}.json',headers=restored_headers)
                check('Wallabag existing user OAuth relogin and captured article/archive/content SHA256 survive clean MariaDB PVC restore',restored['title']==marker and restored['is_archived']==1 and hashlib.sha256(restored['content'].encode()).hexdigest()==content_hash)
                api(base,f'/api/entries/{entry}.json','DELETE',headers=restored_headers)
                try:
                    api(base,f'/api/entries/{entry}.json',headers=restored_headers)
                except urllib.error.HTTPError as error:
                    check('Wallabag HTTP delete confirmed by404 on restored instance',error.code==404)
                else:
                    check('Wallabag deleted entry must not remain readable',False)
    finally:
        scale('wallabag',1)
    with forwarded('wallabag',80) as base:
        http(base,'/api/info',raw=True)
        source_headers=login(base)
        api(base,f'/api/entries/{entry}.json','DELETE',headers=source_headers)
    check('Wallabag source article cleaned up through authenticated HTTP API')


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


def multipart(fields, files=()):
    boundary = 'proof' + uuid.uuid4().hex
    chunks = []
    for key, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    for key, filename, content_type, data in files:
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()+data+b'\r\n')
    return b''.join(chunks) + f'--{boundary}--\r\n'.encode(), {'Content-Type':'multipart/form-data; boundary='+boundary}


def embedding(response):
    value = response['clip']
    values = json.loads(value) if isinstance(value,str) else value
    if not isinstance(values,list) or len(values)!=512 or not all(type(v) in (int,float) and math.isfinite(v) for v in values):
        raise RuntimeError('CLIP must return exactly512 finite embedding values')
    norm = math.sqrt(sum(v*v for v in values))
    if norm < 1e-6:
        raise RuntimeError('CLIP zero embedding is not inference proof')
    return values


def immich_ml():
    # Public model artifacts only; preload verifies hashes before the leased copy.
    subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/talos-proof-data-models.py'),
                    'preload','--state',str(STATEPATH),'--stage',STAGE],check=True,timeout=660)
    providers = json.loads(execute('ml',['python','-c','import onnxruntime as o,json; print(json.dumps(o.get_available_providers()))']))
    check('CPU-only ONNX runtime available; no GPU providers', 'CPUExecutionProvider' in providers and set(providers)<= {'CPUExecutionProvider','AzureExecutionProvider'})
    vectors = {}
    # TTL expires the worker between models; never assume both model sessions fit concurrently.
    for mode in ('visual','textual'):
        fields = {'entries':json.dumps({'clip':{mode:{'modelName':'ViT-B-32__openai'}}})}
        if mode == 'textual': fields['text']='a red and green image'
        body, headers = multipart(fields,[('image','proof.png','image/png',png())] if mode=='visual' else [])
        with forwarded('ml',3003) as base:
            vectors[mode] = embedding(http(base,'/predict','POST',body,headers=headers))
        check('real CPU ONNX CLIP '+mode+' inference returns512 finite nonzero values')
        memory_snapshot('ml','after '+mode+' inference')
        if mode == 'visual': time.sleep(15)  # declared10s TTL +2s poll, not a CI watcher
    RESULT['clip_inference'] = {'model':'ViT-B-32__openai','dimensions':512,
        'providers':providers,'vectors_sha256':hashlib.sha256(json.dumps(vectors,sort_keys=True).encode()).hexdigest()}
    RESULT['limitations'].append('Standalone real image/text CPU inference ONLY; no Immich indexing/search integration, ranking quality, face/OCR/GPU or production capacity claim.')


def immich_search(asset,headers):
    deadline = time.monotonic()+240
    uuid.UUID(asset)  # reject any non-UUID API value before read-only SQL
    while True:
        count = execute('postgres',['psql','-U','immich','-d','immich','-Atc',
            "SELECT count(*) FROM smart_search WHERE \"assetId\"='"+asset+"'"]).decode().strip()
        if count == '1': break
        if time.monotonic() >= deadline: check('Immich own worker must persist uploaded-asset CLIP embedding',False)
        time.sleep(2)
    check('Immich own worker persisted uploaded-asset embedding; no harness SQL writes')
    memory_snapshot('ml','after app image indexing')
    time.sleep(15)  # release visual model before real query textual model
    with forwarded('immich',2283) as base:
        deadline = time.monotonic() + 240
        while True:
            found = http(base,'/api/search/smart','POST',{'query':'a red and green image'},headers=headers)
            if any(item['id']==asset for item in found.get('assets',{}).get('items',[])):
                check('Immich real smart text search returns uploaded asset after CLIP inference')
                break
            if time.monotonic() >= deadline:
                check('Immich CLIP indexing/text search did not complete within bounded window',False)
            time.sleep(2)


def bounded_immich_config(config, integrated):
    config = json.loads(json.dumps(config))
    for settings in config['job'].values(): settings['concurrency'] = 1
    ml = config['machineLearning']
    ml['enabled'] = integrated
    ml['urls'] = ['http://ml:3003']
    ml['clip'].update(enabled=integrated,modelName='ViT-B-32__openai')
    for key in ('facialRecognition','ocr','duplicateDetection'): ml[key]['enabled'] = False
    ml['availabilityChecks']['enabled'] = False
    config['newVersionCheck']['enabled'] = False
    config['map']['enabled'] = False
    config['reverseGeocoding']['enabled'] = False
    return config


def immich():
    if STAGE == 'ml':
        immich_ml()
        return
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
        config = http(base,'/api/admin/config',headers=headers)
        config = bounded_immich_config(config, STAGE == 'full')
        applied = http(base,'/api/admin/config','PUT',config,headers=headers)
        check('Immich supported admin API applies single-job concurrency and CLIP-only proof profile',
            applied['machineLearning']['enabled'] == (STAGE=='full') and
            all(v['concurrency']==1 for v in applied['job'].values()))
        if STAGE == 'full':
            subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/talos-proof-data-models.py'),
                'preload','--state',str(STATEPATH),'--stage','full'],check=True,timeout=660)
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
    # Check generated thumbnail, not merely original storage or /ping.
    with forwarded('immich', 2283) as base:
        deadline = time.monotonic() + 180
        while True:
            try:
                thumbnail = http(base, '/api/assets/' + asset + '/thumbnail?size=preview', headers=headers, raw=True)
                check('Immich generated nonempty image thumbnail',len(thumbnail)>32 and (thumbnail.startswith(b'\xff\xd8') or thumbnail[8:12]==b'WEBP'))
                break
            except urllib.error.HTTPError as error:
                if error.code not in (400,404,500) or time.monotonic() >= deadline:
                    raise
                time.sleep(2)
    if STAGE == 'full': immich_search(asset,headers)
    scale('immich',0)
    try:
        dump = postgres_dump('immich')
        with fresh_pvc('postgres',('immich',)):
            clean_postgres_restore('immich',dump)
            scale('immich',1)
            with forwarded('immich',2283) as base:
                check('Immich authenticated original survives clean vector PostgreSQL PVC restore',http(base,'/api/assets/'+asset+'/original',headers=headers,raw=True)==payload)
            if STAGE == 'full':
                immich_search(asset,headers)
                check('Immich own restored asset embedding and text search survive distinct clean vector-PG PVC restore')
    finally:
        scale('immich',1)
    if STAGE != 'full':
        RESULT['limitations'].append('App-only stage: ML indexing and integrated smart text search NOT proved. Retains original /data PVC during database recovery; no file-volume disaster recovery claim.')


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
    global LIFE, CREDS, STATEPATH, GROUP, STATE, NS, RESULT, STAGE
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('group')
    parser.add_argument('state')
    parser.add_argument('--stage')
    args = parser.parse_args()
    GROUP, STATE, STAGE = args.group, args.state, args.stage
    NS = 'proof-' + GROUP
    RESULT = {'group':GROUP, 'stage':STAGE, 'checks':[], 'limitations':['Frontend tests use verified TLS Gateway; backend-only ML ping uses API port-forward. Negative isolation/drop-verdict tests remain a platform acceptance gate.']}
    os.umask(0o077)
    try:
        spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).resolve().parents[1] / 'scripts/talos-proof-data.py')
        life = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(life)
        LIFE = life
        life.LEASE_GROUP = GROUP
        life.LEASE_STAGE = STAGE
        life.selection(GROUP)
        life.lease(GROUP)
        life.participants(GROUP)
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
        names, _ = LIFE.selection(GROUP)
        for name in names or ():
            memory_snapshot(name, 'suite final observation')
        for observation in RESULT.get('memory_observations', []):
            events = observation['cgroup'].get('memory.events', {})
            if events.get('oom', 0) or events.get('oom_kill', 0):
                RESULT['status'] = 'failed'
                RESULT['resource_failure'] = 'observed cgroup OOM; retained even if functional checks passed'
        # Never discard earlier failures when a later attempt succeeds.
        history = GROUP + '-' + (STAGE or 'group') + '-' + str(time.time_ns()) + '-result.json'
        save_private(history, json.dumps(RESULT, indent=2).encode())
        path = LIFE.no_symlinks(STATEPATH / (GROUP + '-result.json'))
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(RESULT, f, indent=2)
    print(json.dumps(RESULT, indent=2))
    if RESULT['status'] == 'failed':
        sys.exit(1)


if __name__ == '__main__':
    main()
