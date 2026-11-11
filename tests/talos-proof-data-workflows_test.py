#!/usr/bin/env python3
"""Offline workflow regression tests; fakes are not live application evidence."""
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import hashlib
import subprocess
import shutil
import struct
import zlib
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('data_live', Path(__file__).with_name('talos-proof-data-live.py'))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class Workflows(unittest.TestCase):
    def setUp(self):
        live.RESULT = {'checks':[], 'limitations':[]}
        live.CREDS = {'COUCHDB_PASSWORD':'offline-only', 'ADMIN_PASSWORD':'offline-only'}

    def test_immich_fixture_real_exif_and_valid_png_chunks(self):
        image=live.immich_fixture(); offset=8; chunks={}
        while offset<len(image):
            length=struct.unpack('!I',image[offset:offset+4])[0]
            name=image[offset+4:offset+8]; value=image[offset+8:offset+8+length]
            crc=struct.unpack('!I',image[offset+8+length:offset+12+length])[0]
            self.assertEqual(crc,zlib.crc32(name+value)&0xffffffff)
            chunks[name]=value; offset+=length+12
        self.assertIn(b'eXIf',chunks)
        if shutil.which('exiftool'):
            data=json.loads(subprocess.run(['exiftool','-j','-'],input=image,capture_output=True,check=True).stdout)[0]
            self.assertEqual((data['Make'],data['Model'],data['DateTimeOriginal']),('ProofCamera','SyntheticModel','2026:01:02 03:04:05'))
            self.assertEqual((data['ImageWidth'],data['ImageHeight']),(224,224))
            self.assertNotIn('Warning',data)

    def test_immich_upload_uses_exact_v3_fields(self):
        with patch.object(live,'http',return_value={'id':'asset'}) as http:
            self.assertEqual(live.immich_upload('https://immich.proof.invalid',{'Authorization':'private'},b'image','proof.png','image/png'),'asset')
        body=http.call_args.args[3]
        self.assertIn(b'name="fileCreatedAt"',body)
        self.assertIn(b'name="assetData"',body)
        self.assertNotIn(b'deviceId',body)
        self.assertNotIn(b'deviceAssetId',body)

    def test_immich_negative_checks_require_exact_status(self):
        for actual in (400,401,500):
            error=urllib.error.HTTPError('https://proof.invalid',actual,'private error body',{},None)
            with patch.object(live,'http',side_effect=error):
                if actual==400: live.immich_deny('denied','https://proof.invalid','/api/assets/id',{})
                else:
                    with self.assertRaises(RuntimeError): live.immich_deny('denied','https://proof.invalid','/api/assets/id',{})

    def test_immich_backup_quiesces_workers_and_restores_spec_without_starting(self):
        original={'name':'immich','command':['original'],'volumeMounts':[{'name':'data','mountPath':'/data'}]}
        calls=[]
        def kube(*args,**kwargs):
            calls.append(('k',args))
            if args[0]=='get':return json.dumps({'spec':{'template':{'spec':{'containers':[original]}}}}).encode()
            return b''
        with patch.object(live,'k',side_effect=kube),patch.object(live,'scale',side_effect=lambda *a:calls.append(('scale',a))):
            with live.immich_quiesced(): calls.append(('backup',()))
        self.assertEqual([a for kind,a in calls if kind=='scale'],[('immich',0),('immich',1),('immich',0)])
        patch_calls=[a for kind,a in calls if kind=='k' and a[0]=='patch']
        self.assertEqual(json.loads(patch_calls[0][-1])[0]['value']['command'],['/bin/sh','-c','sleep 1800'])
        self.assertEqual(json.loads(patch_calls[-1][-1])[0]['value'],original)
        self.assertLess(next(i for i,c in enumerate(calls) if c==('scale',('immich',0))),next(i for i,c in enumerate(calls) if c[0]=='backup'))

    def test_immich_coordinated_restore_orders_pg_files_then_runtime_and_fails_closed(self):
        for corrupt in (False,True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as directory:
                live.CREDS={'PROOF_ADMIN_PASSWORD':'offline-only'}
                live.RESULT={'checks':[],'limitations':[]}; live.STAGE='app'
                specs={app:{'containers':[{'name':app}],'volumes':[{'name':'data','persistentVolumeClaim':{'claimName':app+'-source'}}]} for app in ('immich','postgres')}
                order=[]
                def kube(*args,**kwargs):
                    if args[0]=='get':return json.dumps({'spec':{'template':{'spec':specs[args[2]]}}}).encode()
                    raise AssertionError(args)
                def http(base,path,method='GET',body=None,**kwargs):
                    if path=='/api/auth/login':return {'accessToken':'private'}
                    if path=='/api/admin/config':return {'job':{'thumbnail':{'concurrency':1}},'machineLearning':{'enabled':False}}
                    if path=='/api/admin/users':return {'id':'viewer-id'}
                    if path=='/api/albums':return {'id':'album'}
                    if path=='/api/shared-links':return {'id':'link','key':'private-key'}
                    if path.startswith('/api/assets/image/thumbnail'):return b'x'*40
                    if path=='/api/assets/image':return {'exifInfo':{'make':'ProofCamera'}}
                    if path=='/api/assets/video':return {'type':'VIDEO','duration':1000}
                    if '/original?key=' in path:return live.immich_fixture()
                    return {}
                def execute(app,command,data=None):
                    if command[0]=='find':return b''
                    if command[0]=='tar':
                        if '-czpf' in command:return b'private-archive'
                        order.append('restore-files');return b''
                    return b'video'
                @contextlib.contextmanager
                def fresh(app,dependents=(),bootstrap=False,resume=True):
                    self.assertFalse(resume)
                    self.assertEqual(bootstrap,app=='immich')
                    old=copy.deepcopy(specs[app])
                    specs[app]['volumes'][0]['persistentVolumeClaim']['claimName']=app+'-fresh'
                    order.append('fresh-'+app)
                    try: yield lambda:order.append('start-restored-app')
                    finally:
                        if not (corrupt and app=='immich'):specs[app]=old
                        order.append('rollback-'+app)
                def save(name,data):
                    path=Path(directory)/name;path.write_bytes(data);return path
                with patch.object(live,'k',side_effect=kube),patch.object(live,'http',side_effect=http),patch.object(live,'forwarded',side_effect=lambda *a:contextlib.nullcontext('https://immich.proof.invalid')),patch.object(live,'execute',side_effect=execute),patch.object(live,'bounded_immich_config',side_effect=lambda c,i:c),patch.object(live,'immich_upload',side_effect=['image','video']),patch.object(live,'immich_assert_state') as verify,patch.object(live,'immich_deny'),patch.object(live,'restart'),patch.object(live,'immich_quiesced',side_effect=lambda:contextlib.nullcontext()),patch.object(live,'postgres_dump',return_value=b'dump'),patch.object(live,'clean_postgres_restore',side_effect=lambda *a:order.append('restore-pg')),patch.object(live,'fresh_pvc',side_effect=fresh),patch.object(live,'save_private_new',side_effect=save),patch.object(live,'scale',side_effect=lambda a,n:order.append('scale-'+a+'-'+str(n))):
                    if corrupt:
                        with self.assertRaises(RuntimeError):live.immich()
                        self.assertNotIn('scale-immich-1',order)
                        self.assertNotIn('scale-postgres-1',order)
                    else:
                        live.immich()
                        self.assertEqual(verify.call_count,4)
                        self.assertLess(order.index('restore-pg'),order.index('restore-files'))
                        self.assertLess(order.index('restore-files'),order.index('start-restored-app'))
                        self.assertLess(order.index('rollback-postgres'),order.index('scale-postgres-1'))
                        self.assertLess(order.index('scale-postgres-1'),order.index('scale-immich-1'))

    def test_forensics_keeps_logs_private_and_strips_messages(self):
        spec=importlib.util.spec_from_file_location('forensic_life',Path(__file__).resolve().parents[1]/'scripts/talos-proof-data.py')
        life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
        pod={'metadata':{'uid':'pod-uid','name':'proof-pod'},'status':{'phase':'Running','containerStatuses':[{'name':'app','restartCount':2,'state':{'running':{'startedAt':'now'}},'lastState':{'terminated':{'reason':'Error','exitCode':1,'signal':0,'startedAt':'before','finishedAt':'then','message':'SECRET-MESSAGE'}}}]}}
        with tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').exists() else None) as directory:
            Path(directory).chmod(0o700)
            with patch.object(life,'STATE_DIR',Path(directory)),patch.object(life,'LEASE_GROUP','immich'),patch.object(life,'lease'),patch.object(life.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,json.dumps({'items':[pod]}).encode()),subprocess.CompletedProcess([],0,b'SECRET-CURRENT'),subprocess.CompletedProcess([],0,b'SECRET-LOG')]):
                public=life.capture_forensics('proof-immich','before deletion')
            self.assertEqual(set(public),{'phase','sha256'})
            metadata=list(Path(directory).glob('pod-forensics-*.json'))[0]
            self.assertEqual(public['sha256'],hashlib.sha256(metadata.read_bytes()).hexdigest())
            self.assertNotIn('SECRET',metadata.read_text())
            record=json.loads(metadata.read_text()); terminated=record['pods'][0]['containers'][0]['lastState']['terminated']
            self.assertEqual(terminated['exitCode'],1)
            log=list(Path(directory).glob('previous-log-*.txt'))[0]
            self.assertEqual(log.read_bytes(),b'SECRET-LOG')
            self.assertEqual(stat.S_IMODE(log.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(metadata.stat().st_mode),0o600)
            current=list(Path(directory).glob('current-log-*.txt'))[0]
            self.assertEqual(current.read_bytes(),b'SECRET-CURRENT')
            self.assertEqual(stat.S_IMODE(current.stat().st_mode),0o600)

    def test_wallabag_local_image_fetch_and_hash_checks(self):
        svg=b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="#ff0000"/></svg>'
        article={'content':'<img src="https://wallabag.proof.invalid/assets/images/a/b/proof.svg">'}
        with patch.object(live,'http',return_value=svg) as http:
            digest=live.wallabag_image('https://wallabag.proof.invalid',article,{'Authorization':'private'})
            self.assertEqual(digest,hashlib.sha256(svg).hexdigest())
            self.assertEqual(http.call_args.args[1],'/assets/images/a/b/proof.svg')
            with self.assertRaises(RuntimeError):live.wallabag_image('https://wallabag.proof.invalid',article,{},'wrong-hash')
        for content in ('<img src="http://fixture.proof-wallabag.svc.cluster.local:8080/proof-image.svg">','<img src="https://other.invalid/assets/images/proof.svg">'):
            with self.assertRaises(RuntimeError):live.wallabag_image('https://wallabag.proof.invalid',{'content':content},{})

    def test_wallabag_actual_worker_order_and_no_fabricated_job_push(self):
        events=[]; url=None
        def execute(app,command,data=None):
            nonlocal url
            if command[0]=='timeout':
                self.assertEqual(command[1],'45')
                self.assertIn('wallabag:import:redis-worker',command)
                self.assertIn('--maxIterations=1',command)
                events.append('worker');return b'private worker output'
            code=command[-1]
            self.assertNotIn('lpush',code.lower())
            if 'setProducer' in code:
                payload=json.loads(data);url=payload[0]['url']
                self.assertEqual(payload[0]['tags'],['proof-queue'])
                self.assertIn('->import()',code)
                events.append('producer');return b'{"queued":1,"imported":0}'
            if 'llen' in code:
                return json.dumps([0,0,0,0] if 'worker' in events else [1,0,0,0]).encode()
            raise AssertionError('unknown PHP operation')
        def http(base,query,**kwargs):
            self.assertIn('tags=proof-queue',query)
            self.assertNotIn('title=',query)
            events.append('http-after' if 'worker' in events else 'http-before')
            return {'_embedded':{'items':[{'id':7,'url':url,'content':'Synthetic queued proof content','is_archived':1,'is_starred':1}] if 'worker' in events else []}}
        with patch.object(live,'execute',side_effect=execute),patch.object(live,'http',side_effect=http),patch.object(live,'save_private_new'):
            self.assertEqual(live.wallabag_queue('https://wallabag.proof.invalid',{},'proof-queue'),7)
        self.assertEqual(events,['producer','http-before','worker','http-after'])

    def test_couch_runtime_limitations_do_not_claim_unrun(self):
        import ast
        tree=ast.parse(Path(__file__).with_name('talos-proof-data-live.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='couchdb')
        wording=[n.value for n in ast.walk(function) if isinstance(n,ast.Constant) and isinstance(n.value,str) and 'recovery only.' in n.value]
        self.assertEqual(len(wording),1)
        self.assertNotIn('unrun',wording[0].lower())
        self.assertNotIn('prepared',wording[0].lower())

    def test_pocket_browser_network_boundaries_precede_navigation(self):
        source=Path(__file__).with_name('talos-proof-data-browser.mjs').read_text()
        first_navigation=source.index('await page.goto(')
        for boundary in ("context.route('**/*'", "context.routeWebSocket('**/*', ws => ws.close())", "serviceWorkers:'block'"):
            self.assertLess(source.index(boundary),first_navigation)
        self.assertIn('u.origin === issuer',source)
        self.assertNotIn("'--ignore-certificate-errors'",source)
        self.assertLess(source.index('!credentialFile && input.requireExistingPasskey'),source.index("await api('/api/signup/setup'"))
        self.assertNotIn('fs.constants.O_TRUNC',source)
        self.assertIn('fs.constants.O_EXCL',source)

    def test_pocket_spki_comes_from_ca_verified_actual_leaf(self):
        import inspect
        source=inspect.getsource(live.pocket_browser)
        self.assertIn("ssl.create_default_context(cafile=CA)",source)
        self.assertIn('getpeercert(binary_form=True)',source)
        self.assertIn("'-inform','DER'",source)
        self.assertNotIn("'-in',CA",source)
        self.assertIn("TALOS_PROOF_REQUIRE_EXISTING_PASSKEY",source)

    def test_wopi_single_attempt_and_append_only_output_contract(self):
        source=(Path(__file__).resolve().parents[1]/'scripts/talos-proof-data-wopi-run.py').read_text()
        self.assertIn('maximum not in (1,2) or args.attempt>maximum',source)
        self.assertIn('os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW',source)
        self.assertNotIn('O_TRUNC',source)
        self.assertIn("actual!={'collabora':768,'wopi-fixture':64}",source)
        self.assertIn("'memory.current','memory.peak','memory.events','memory.stat'",source)
        self.assertIn("negative!={'bad-token':401,'wrong-lock':409}",source)

    def test_wopi_format_warning_fix_is_exact_and_plain_text_only(self):
        source=Path(__file__).with_name('talos-proof-data-wopi.mjs').read_text()
        self.assertIn("if(input.mode!=='office')",source)
        self.assertIn("name:'Continue editing',exact:true",source)
        self.assertIn('This document may contain formatting or content that cannot be saved in the current file format.',source)
        self.assertNotIn("'wopi-failure.png'",source)
        self.assertIn('crypto.randomUUID()',source)

    def test_private_archive_is_exclusive_and_mode0600(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(live, 'STATEPATH', Path(directory)), patch.object(live, 'LIFE') as life:
                life.no_symlinks.side_effect = lambda path:path
                path = live.save_private_new('archive.json', b'first')
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                with self.assertRaises(FileExistsError):
                    live.save_private_new('archive.json', b'overwritten')
                self.assertEqual(path.read_bytes(), b'first')

    def test_negative_requires_exact_http_status(self):
        for status in (401, 403, 409):
            error = urllib.error.HTTPError('https://proof.invalid', status, '', {}, None)
            with patch.object(live, 'http', side_effect=error):
                live.expect_http('expected', status, 'https://proof.invalid', '/')
                with self.assertRaises(RuntimeError):
                    live.expect_http('wrong', 404, 'https://proof.invalid', '/')
        with patch.object(live, 'http', return_value={}):
            with self.assertRaises(RuntimeError):
                live.expect_http('no denial', 403, 'https://proof.invalid', '/')

    def test_replication_is_loopback_bounded_and_nonpersistent(self):
        db = 'proof_' + 'a'*32
        payload = live.couch_replication(db, db+'_replica', 'user:private')
        self.assertFalse(payload['continuous'])
        self.assertFalse(payload['create_target'])
        self.assertEqual(payload['doc_ids'], ['document', 'deleted'])
        for endpoint in ('source','target'):
            self.assertTrue(payload[endpoint]['url'].startswith('http://127.0.0.1:5984/proof_'))
            self.assertIn('Authorization', payload[endpoint]['headers'])
        for invalid in ('production', 'http://example.com', db+'/../other'):
            with self.assertRaises(RuntimeError):
                live.couch_replication(invalid, db+'_replica', 'private')

    def test_couch_documents_normalizes_only_revision_and_sorts_design(self):
        docs = [{'_id':'z', '_rev':'1-a', 'nested':{'_rev':'preserve'}}, {'_id':'_design/proof', '_rev':'2-b', 'views':{}}]
        with patch.object(live, 'http', return_value={'rows':[{'doc':d} for d in docs]}):
            actual = live.couch_documents('https://proof.invalid', 'proof_db', 'private')
        self.assertEqual(actual, [{'_id':'_design/proof', 'views':{}}, {'_id':'z', 'nested':{'_rev':'preserve'}}])

    def test_miniflux_workflow_preserves_star_preferences_and_content(self):
        entry = {'id':7, 'title':'Proof article', 'content':'Synthetic proof content', 'status':'unread', 'starred':False}
        user = {'id':1, 'theme':'light_serif', 'entries_per_page':100}
        original = copy.deepcopy(user)
        calls = []
        def http(base, path, method='GET', body=None, auth=None, **kwargs):
            calls.append((path,method,copy.deepcopy(body)))
            if path=='/healthcheck': return b'OK'
            if path=='/v1/categories': return {'id':2}
            if path=='/v1/feeds': return {'feed_id':3}
            if path=='/v1/feeds/3/entries': return {'entries':[copy.deepcopy(entry)]}
            if path=='/v1/me': return copy.deepcopy(user)
            if path=='/v1/users/1':
                self.assertIn(body['theme'], ('dark_serif','light_serif'))
                user.update(body)
                return copy.deepcopy(user)
            if path=='/v1/entries/7/bookmark': entry['starred']=not entry['starred']; return b''
            if path=='/v1/entries': entry['status']=body['status']; return b''
            if path=='/v1/entries/7': return copy.deepcopy(entry)
            if path=='/v1/feeds/3': return {'id':3}
            if path=='/v1/categories/2' and method=='DELETE': return b''
            raise AssertionError((path,method))
        saved = {}
        def dump(_):
            saved.update(entry=copy.deepcopy(entry), user=copy.deepcopy(user))
            return b'offline-dump'
        @contextlib.contextmanager
        def fresh(*args):
            source_entry, source_user = copy.deepcopy(entry), copy.deepcopy(user)
            entry.clear(); user.clear()
            yield
            entry.clear(); entry.update(source_entry)
            user.clear(); user.update(source_user)
        def restore(*args):
            entry.update(saved['entry']); user.update(saved['user'])
        with patch.object(live, 'http', side_effect=http), patch.object(live, 'forwarded', side_effect=lambda *a:contextlib.nullcontext('https://miniflux.proof.invalid')), patch.object(live, 'restart'), patch.object(live, 'scale'), patch.object(live, 'fresh_pvc', side_effect=fresh), patch.object(live, 'postgres_dump', side_effect=dump), patch.object(live, 'clean_postgres_restore', side_effect=restore), patch.object(live, 'authenticated_recovery', side_effect=http):
            live.miniflux()
        self.assertEqual(user, original)
        self.assertTrue(saved['entry']['starred'])
        self.assertNotEqual(saved['user']['theme'], original['theme'])
        self.assertIn('Miniflux theme/page-size preferences match after clean-PVC restore', live.RESULT['checks'])
        self.assertEqual(sum(path.endswith('/bookmark') for path,_,_ in calls),1)


if __name__ == '__main__':
    unittest.main()
