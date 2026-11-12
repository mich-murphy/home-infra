#!/usr/bin/env python3
"""OFFLINE only: no kubectl/Talos/VM/image/native runtime execution permitted."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('initializer',ROOT/'scripts/talos-proof-nextcloud-initialize.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def api_deployment(doc):
    d=copy.deepcopy(doc);p=d['spec']['template']['spec']
    p.update(dnsPolicy='ClusterFirst',restartPolicy='Always',schedulerName='default-scheduler',terminationGracePeriodSeconds=30)
    for c in p.get('containers',[])+p.get('initContainers',[]):
        c.update(imagePullPolicy='IfNotPresent',terminationMessagePath='/dev/termination-log',terminationMessagePolicy='File')
        for name in ('startupProbe','readinessProbe','livenessProbe'):
            if name not in c:continue
            probe=c[name]
            for k,v in dict(initialDelaySeconds=0,timeoutSeconds=1,periodSeconds=10,successThreshold=1,failureThreshold=3).items():probe.setdefault(k,v)
            if 'httpGet' in probe:probe['httpGet'].setdefault('scheme','HTTP')
        for e in c.get('env',[]):
            if 'fieldRef' in e.get('valueFrom',{}):e['valueFrom']['fieldRef'].setdefault('apiVersion','v1')
    for v in p.get('volumes',[]):
        if 'configMap' in v:v['configMap'].setdefault('defaultMode',420)
    return d


class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name).resolve();self.state.chmod(0o700)
        p=patch.object(m.s.life,'CANONICAL_DATA_STATE',self.state);p.start();self.addCleanup(p.stop)
        for name in ('run','Popen'):
            p=patch.object(subprocess,name,side_effect=AssertionError('OFFLINE: runtime forbidden'));p.start();self.addCleanup(p.stop)
        self.run=str(uuid.uuid4());self.i=m.Initializer(self.state,self.run)
        self.docs=m.declarations('nextcloud-data')
        self.r=dict(group='nextcloud',stage='cron',action='initialize',run_id=self.run,state_dir=str(self.state),budget_mib=832,
            cleanup_authorized=True,selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'],
            phases=['stopped-objects','readonly-binding'],namespace=m.NS,namespace_uid='ns-uid',storage_device='/dev/sdb1',storage_device_id='8:17',
            context='proof',node_uid='node-uid',endpoint=m.s.life.EXPECTED_ENDPOINT,expires=time.time()+2000,
            document_sha256=m.document_hashes(self.docs),html_claim='nextcloud-data',allowed_missing_resources=sorted(self.docs),existing_uids={'secret/proof-credentials':'secret-uid'})
        self.receipt=self.state/'receipt';self.write()
        p=patch.dict(os.environ,TALOS_PROOF_DATA_LEASE=str(self.receipt));p.start();self.addCleanup(p.stop)
        self.secret=dict(kind='Secret',metadata=dict(name='proof-credentials',uid='secret-uid'),type='Opaque',data={k:'offline-placeholder' for k in ('POSTGRES_PASSWORD','NEXTCLOUD_ADMIN_PASSWORD','REDIS_HOST_PASSWORD')})

    def write(self):
        self.receipt.write_text(json.dumps(self.r));self.receipt.chmod(0o600)

    def fixture(self,key):
        d=copy.deepcopy(self.docs[key]);d['metadata']['uid']='uid-'+key
        return d

    def test_exact_separate_receipt_before_any_api(self):
        for change in [dict(action='run'),dict(phases=['cron']),dict(budget_mib=352),dict(namespace_uid=''),dict(storage_device='/dev/sda1'),dict(expires=0),dict(allowed_missing_resources=['secret/proof-credentials']),dict(existing_uids={}),dict(endpoint='production')]:
            old=copy.deepcopy(self.r);self.r.update(change);self.write()
            with patch.object(m.s.life,'lease',side_effect=AssertionError('API before local grant')),self.assertRaises(RuntimeError):self.i.authorize()
            self.r=old

    def test_receipt_immutable_and_no_implicit_refresh(self):
        with patch.object(m.s.life,'lease'):
            self.i.authorize(start=True);self.r['expires']+=1;self.write()
            with self.assertRaisesRegex(RuntimeError,'immutable'):self.i.authorize()

    def test_832_conservative_not_352_and_approved_image(self):
        with patch.object(m.s.life,'lease'):self.assertEqual(self.i.authorize()['budget_mib'],832)
        claims=['nextcloud-data','postgres-data','redis-data']
        job=self.i.binding_job(claims,{n:str(uuid.uuid4()) for n in claims},'8:17')
        p=job['spec']['template']['spec'];c=p['containers'][0]
        self.assertEqual(c['image'],m.HELPER['image']);self.assertIn('@sha256:',c['image'])
        self.assertEqual(c['resources']['limits']['memory'],'64Mi')
        self.assertEqual(m.HELPER['resources']['limits']['memory'],'32Mi')
        self.assertNotIn('fsGroup',p['securityContext']);self.assertNotIn('initContainers',p)
        self.assertTrue(all(v['persistentVolumeClaim']['readOnly'] for v in p['volumes']))
        self.assertTrue(all(v['readOnly'] for v in c['volumeMounts']))
        for banned in ('python','chown','maintenance:install','pg_ctl','redis-server'):self.assertNotIn(banned,c['command'][2])
        self.assertIn('/dev/sdb1',c['command'][2]);self.assertIn('$4 == root',c['command'][2]);self.assertIn('mindepth 1',c['command'][2])

    def test_pending_and_replay_nomutation(self):
        with patch.object(self.i,'authorize'),patch.object(self.i,'inventory',side_effect=AssertionError('inventory')),patch.object(self.i,'call',side_effect=AssertionError('mutation')):
            self.i.save(dict(event='pending',run_id=self.run,scope='initialize'))
            with self.assertRaisesRegex(RuntimeError,'pending'):self.i.initialize()
            self.i.save(dict(event='clean',run_id=self.run))
            with self.assertRaisesRegex(RuntimeError,'reused'):self.i.initialize()

    def test_inventory_missing_secret_no_creation(self):
        with patch.object(self.i,'target',return_value=self.r),patch.object(self.i,'obj',return_value={'items':[]}),patch.object(self.i,'call',side_effect=AssertionError('mutation')):
            with self.assertRaisesRegex(RuntimeError,'missing existing secret'):self.i.inventory()

    def test_preserve_existing_wopi_secrets_and_stopped_web(self):
        web=self.fixture('deployment/nextcloud');self.r['allowed_missing_resources'].remove('deployment/nextcloud');self.r['existing_uids']['deployment/nextcloud']=web['metadata']['uid']
        ignored=dict(kind='ConfigMap',metadata=dict(name='wopi-fixture',uid='untouched'),data={'preserve':'existing'})
        items=[web,self.secret,ignored];before=copy.deepcopy(items)
        with patch.object(self.i,'target',return_value=self.r),patch.object(self.i,'obj',return_value={'items':items}),patch.object(self.i,'call',side_effect=AssertionError('mutation')):
            self.i.inventory()
        self.assertEqual(items,before)
        self.assertNotIn('secret/proof-credentials',self.docs)

    def test_changed_image_and_security_reject_before_create(self):
        for fault in ('image','replicas','security','unknown'):
            web=self.fixture('deployment/nextcloud')
            r=copy.deepcopy(self.r);r['allowed_missing_resources'].remove('deployment/nextcloud');r['existing_uids']['deployment/nextcloud']=web['metadata']['uid']
            if fault=='image':web['spec']['template']['spec']['containers'][0]['image']='busybox:latest'
            elif fault=='replicas':web['spec']['replicas']=1
            elif fault=='security':web['spec']['template']['spec']['securityContext']['fsGroup']=33
            else:web['spec']['surpriseDefault']=True
            with patch.object(self.i,'target',return_value=r),patch.object(self.i,'obj',return_value={'items':[web,self.secret]}),patch.object(self.i,'call',side_effect=AssertionError('mutation')):
                with self.assertRaises(RuntimeError):self.i.inventory()

    def test_existing_partial_or_retained_pvc_blocks_without_touch(self):
        for phase in ('Pending','Bound'):
            pvc=self.fixture('pvc/postgres-data');pvc['status']={'phase':phase}
            with patch.object(self.i,'target',return_value=self.r),patch.object(self.i,'obj',return_value={'items':[pvc,self.secret]}),patch.object(self.i,'call',side_effect=AssertionError('mutation')):
                with self.assertRaisesRegex(RuntimeError,'partial'):self.i.inventory()
            r=copy.deepcopy(self.r);r['allowed_missing_resources'].remove('pvc/postgres-data');r['existing_uids']['pvc/postgres-data']=pvc['metadata']['uid']
            with patch.object(self.i,'target',return_value=r),patch.object(self.i,'obj',return_value={'items':[pvc,self.secret]}):
                with self.assertRaisesRegex(RuntimeError,'three explicitly missing'):self.i.inventory()

    def test_foreign_pods_even_completed_or_terminating_block(self):
        for ns in ('proof-nextcloud','proof-validation','proof-media','local-path-storage'):
            p=dict(metadata=dict(name='foreign',namespace=ns,deletionTimestamp='now'),status=dict(phase='Succeeded'))
            with patch.object(self.i,'target'),patch.object(self.i,'obj',return_value={'items':[p]}),patch.object(self.i,'provisioner_pod',return_value=False),patch.object(self.i,'call',side_effect=AssertionError('mutation')):
                with self.assertRaisesRegex(RuntimeError,'foreign/helper'):self.i.barriers()

    def test_partial_creation_preserves_everything_and_pending(self):
        created=[]
        def call(*a,**kw):
            self.assertEqual(a[0],'create');d=json.loads(kw['data']);created.append(d)
            if len(created)==2:raise RuntimeError('create failure')
            return json.dumps({'metadata':{'uid':'new-uid'}})
        with patch.object(self.i,'authorize',return_value=self.r),patch.object(self.i,'inventory',return_value=self.docs),patch.object(self.i,'storage'),patch.object(self.i,'barriers'),patch.object(self.i,'memory_admission'),patch.object(self.i,'call',side_effect=call):
            with self.assertRaisesRegex(RuntimeError,'create failure'):self.i.initialize()
        self.assertEqual(len(created),2);self.assertEqual(self.i.pending(),{self.run})
        self.assertTrue(any(e.get('event')=='initialization-created' for e in m.s.life.native_cron_events(self.state)))

    def test_wrong_created_pvc_uid_or_spec_or_partial_bound_reject(self):
        key='pvc/postgres-data';doc=self.docs[key]
        for fault in ('uid','image-equivalent-storage','partial'):
            obj=self.fixture(key)
            if fault=='uid':obj['metadata']['uid']='foreign'
            if fault=='image-equivalent-storage':obj['spec']['storageClassName']='wrong'
            if fault=='partial':obj['spec']['volumeName']='retained';obj['status']={'phase':'Bound'}
            with patch.object(self.i,'target',return_value=self.r),patch.object(self.i,'obj',return_value=obj),patch.object(self.i,'call',side_effect=AssertionError('mutation')):
                with self.assertRaises(RuntimeError):self.i.verify_created({key:doc},{key:'uid-'+key},before_binding=True)

    def evidence(self):
        p=dict(metadata={'name':'binding-pod'},status={'containerStatuses':[dict(name='binding',restartCount=0,state={'terminated':{'exitCode':0}})]})
        log='PROOF_BINDING_EMPTY_READONLY\nCGROUP memory.current\n12\nCGROUP memory.peak\n123\nCGROUP memory.events\noom 0\noom_kill 0\nCGROUP memory.stat\nanon 1\n'
        return {'items':[p]},{('binding-pod','binding'):log},[]

    def test_actual_directory_failure_memory_and_capture_gap_reject(self):
        self.i.validate_binding_evidence(self.evidence())
        for fault in ('nonempty','memory','oom','gap','exit'):
            e=self.evidence()
            if fault=='nonempty':e[1][('binding-pod','binding')]=e[1][('binding-pod','binding')].replace('PROOF_BINDING_EMPTY_READONLY','')
            if fault=='memory':e[1][('binding-pod','binding')]=e[1][('binding-pod','binding')].replace('\n123\n','\n999999999\n')
            if fault=='oom':e[1][('binding-pod','binding')]=e[1][('binding-pod','binding')].replace('oom 0','oom 1')
            if fault=='gap':e[2].append('gap')
            if fault=='exit':e[0]['items'][0]['status']['containerStatuses'][0]['state']['terminated']['exitCode']=1
            with self.assertRaises(RuntimeError):self.i.validate_binding_evidence(e)

    def test_storage_class_and_helper_config_no_policy_mutation(self):
        sc=dict(provisioner='rancher.io/local-path',volumeBindingMode='WaitForFirstConsumer',reclaimPolicy='Retain')
        for fault in ('Immediate','Delete','config'):
            a=copy.deepcopy(sc);config={'data':copy.deepcopy(m.STORAGE_CONFIG)}
            if fault=='Immediate':a['volumeBindingMode']='Immediate'
            elif fault=='Delete':a['reclaimPolicy']='Delete'
            else:config['data']['helperPod.yaml']='wrong image or memory'
            with patch.object(self.i,'obj',side_effect=[a,config]),patch.object(self.i,'call',side_effect=AssertionError('policy mutation')):
                with self.assertRaises(RuntimeError):self.i.storage()

    def test_cleanup_pending_only_never_main_rerun_or_storage_delete(self):
        self.i.save(dict(event='pending',run_id=self.run,scope='initialize'))
        name='nc-binding-'+self.run
        self.i.save(dict(event='initialization-binding-created',run_id=self.run,name=name,uid='own'))
        events=[]
        with patch.object(self.i,'target'),patch.object(self.i,'obj',return_value={'items':[dict(metadata=dict(name=name,uid='own'))]}),patch.object(self.i,'provisioner_forensics',side_effect=lambda:events.append('provisioners')),patch.object(self.i,'forensics',side_effect=lambda n:(events.append('raw') or ({'items':[]},{},[]))),patch.object(self.i,'delete_binding',side_effect=lambda n,u:events.append('delete-own')),patch.object(self.i,'barriers',side_effect=lambda:events.append('absent')),patch.object(self.i,'call',side_effect=AssertionError('no create/scale/storage delete')):
            self.i.cleanup_only()
        self.assertEqual(events,['provisioners','raw','delete-own','absent']);self.assertFalse(self.i.pending())
        self.assertEqual(self.i.scope,'initialization-cleanup')

    def test_full_mocked_binding_create_only_new_scope_and_capture_before_delete(self):
        objects={'secret/proof-credentials':copy.deepcopy(self.secret)};events=[];binding={}
        def call(*args,**kwargs):
            if args[0]=='create':
                d=json.loads(kwargs['data']);uid=str(uuid.uuid4());d['metadata']['uid']=uid
                if d['kind']=='Job':
                    events.append('helper-create');binding.update(d)
                    for n in ('nextcloud-data','postgres-data','redis-data'):
                        pvc=objects['pvc/'+n];pvname='pvc-'+pvc['metadata']['uid'];pvc['spec']['volumeName']=pvname;pvc['status']={'phase':'Bound'}
                        objects['pv/'+pvname]=dict(metadata=dict(name=pvname,uid=str(uuid.uuid4())),spec=dict(
                            storageClassName='proof-local',persistentVolumeReclaimPolicy='Retain',accessModes=['ReadWriteOnce'],capacity=dict(storage=pvc['spec']['resources']['requests']['storage']),
                            claimRef=dict(name=n,namespace=m.NS,uid=pvc['metadata']['uid']),
                            hostPath=dict(path='/var/mnt/proof/'+pvname+'_'+m.NS+'_'+n),
                            nodeAffinity={'required':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'kubernetes.io/hostname','operator':'In','values':['talos-proof']}]}]}}))
                else:
                    key=m.KINDS[d['kind']]+'/'+d['metadata']['name'];objects[key]=api_deployment(d) if d['kind']=='Deployment' else d;events.append(key)
                return json.dumps(d)
            self.assertIn('wait',args);return ''
        def obj(*args):
            if args[-1]=='proof-local':return dict(provisioner='rancher.io/local-path',volumeBindingMode='WaitForFirstConsumer',reclaimPolicy='Retain')
            if args[-1]=='local-path-config':return {'data':copy.deepcopy(m.STORAGE_CONFIG)}
            if args[-1]=='local-path-provisioner':return api_deployment(next(d for d in m.STORAGE_DOCS if d['kind']=='Deployment'))
            return copy.deepcopy(objects[args[-2]+'/'+args[-1]])
        def forensics(name):
            events.append('raw-before-delete');e=self.evidence();e[0]['items'][0]['spec']=copy.deepcopy(binding['spec']['template']['spec']);return e
        with patch.object(self.i,'authorize',return_value=self.r),patch.object(self.i,'target',return_value=self.r),patch.object(self.i,'inventory',return_value=self.docs),patch.object(self.i,'barriers'),patch.object(self.i,'memory_admission',side_effect=lambda:events.append('dual832')),patch.object(self.i,'call',side_effect=call),patch.object(self.i,'obj',side_effect=obj),patch.object(self.i,'provisioner_forensics'),patch.object(self.i,'forensics',side_effect=forensics),patch.object(self.i,'delete_binding',side_effect=lambda n,u:events.append('delete-own')):
            self.i.initialize()
        self.assertLess(events.index('raw-before-delete'),events.index('delete-own'))
        self.assertTrue(events.index('dual832')<events.index('helper-create'))
        self.assertFalse(self.i.pending())
        journal=m.s.life.native_cron_events(self.state)
        stopped=next(e for e in journal if e.get('event')=='initialization-stopped-bound')
        self.assertFalse(stopped['full_run_authorized']);self.assertFalse(stopped['provisioner_forensics_complete'])
        self.assertEqual(objects['secret/proof-credentials'],self.secret)

    def test_api_shaped_provisioner_web_backends_and_approved_init(self):
        docs=[next(d for d in m.STORAGE_DOCS if d['kind']=='Deployment')]+[self.docs['deployment/'+n] for n in ('nextcloud','postgres','redis')]
        for doc in docs:
            approved=copy.deepcopy(doc)
            approved['spec']['template']['spec']['initContainers']=[copy.deepcopy(approved['spec']['template']['spec']['containers'][0])]
            approved['spec']['template']['spec'].setdefault('volumes',[]).append(dict(name='downward',downwardAPI=dict(items=[dict(path='namespace',fieldRef=dict(fieldPath='metadata.namespace'))])))
            actual=api_deployment(approved)
            down=actual['spec']['template']['spec']['volumes'][-1]['downwardAPI']
            down['defaultMode']=420;down['items'][0]['fieldRef']['apiVersion']='v1'
            a=actual['spec']['template']['spec'];b=approved['spec']['template']['spec']
            self.i.envelope(a,b)
            for fault in ('scheme','mode','fieldref','probe','unknown','init-security','init-resource'):
                bad=copy.deepcopy(a)
                if fault=='scheme':bad['containers'][0].setdefault('readinessProbe',{}).setdefault('httpGet',{})['scheme']='HTTPS'
                elif fault=='mode':bad.setdefault('volumes',[]).append(dict(name='foreign',configMap=dict(name='x',defaultMode=511)))
                elif fault=='fieldref':bad['containers'][0].setdefault('env',[]).append(dict(name='foreign',valueFrom=dict(fieldRef=dict(apiVersion='v2',fieldPath='metadata.name'))))
                elif fault=='probe':bad['containers'][0]['readinessProbe']['successThreshold']=2
                elif fault=='unknown':bad['containers'][0]['unknownDefault']=True
                elif fault=='init-security':bad['initContainers'][0].setdefault('securityContext',{})['privileged']=True
                else:bad['initContainers'][0]['resources']['limits']['memory']='1Gi'
                with self.assertRaisesRegex(RuntimeError,'envelope'):self.i.envelope(bad,b)

    def test_document_hash_dirty_drift_and_independent_stopped_policy(self):
        for fault in ('image','replicas','suspend','namespace','secret'):
            docs=copy.deepcopy(self.docs)
            if fault=='image':docs['deployment/postgres']['spec']['template']['spec']['containers'][0]['image']='changed'
            elif fault=='replicas':docs['deployment/postgres']['spec']['replicas']=1
            elif fault=='suspend':docs['cronjob/nextcloud-cron']['spec']['suspend']=False
            elif fault=='namespace':docs['service/postgres']['metadata']['namespace']='foreign'
            else:docs['secret/foreign']=dict(kind='Secret',metadata=dict(name='foreign',namespace=m.NS))
            # Even an updated hash must not authorize active/foreign/Secret declarations.
            if fault!='image':self.r['document_sha256']=m.document_hashes(docs);self.write()
            with patch.object(m,'declarations',return_value=docs),patch.object(m.s.life,'lease',side_effect=AssertionError('API before local reject')):
                with self.assertRaises(RuntimeError):self.i.authorize()

    def test_dirty_manifest_drift_before_create_and_no_secret_create(self):
        for args in [('apply','-f','-'),('patch','deployment','postgres'),('delete','secret','proof-credentials')]:
            with patch.object(m.s.life,'kube',side_effect=AssertionError('mutation')):
                with self.assertRaises(RuntimeError):self.i.call(*args,data='{}')
        document=copy.deepcopy(self.docs['deployment/postgres'])
        drift=copy.deepcopy(self.docs);drift['deployment/postgres']['spec']['template']['spec']['containers'][0]['image']='dirty-image'
        with patch.object(m,'declarations',return_value=drift),patch.object(m.s.life,'lease'),patch.object(m.s.life,'kube',side_effect=AssertionError('mutation')):
            with self.assertRaisesRegex(RuntimeError,'hash drift'):self.i.call('create','-f','-',data=json.dumps(document))
        with patch.object(m.s.life,'lease'),patch.object(m.s.life,'kube',side_effect=AssertionError('mutation')):
            with self.assertRaisesRegex(RuntimeError,'explicitly authorized'):
                self.i.call('create','-f','-',data=json.dumps(dict(kind='Secret',metadata=dict(name='proof-credentials',namespace=m.NS))))

    def test_aux_list_failure_still_captures_and_uid_retires_binding(self):
        name='nc-binding-'+self.run
        self.i.save(dict(event='pending',run_id=self.run,scope='initialize'))
        self.i.save(dict(event='initialization-binding-created',run_id=self.run,name=name,uid='own'))
        pod=dict(metadata=dict(name='binding-pod'),spec=dict(containers=[dict(name='binding')]))
        events=[]
        def obj(*args):
            if 'local-path-storage' in args:events.append('aux-failed');raise RuntimeError('aux API unavailable')
            if 'jobs' in args:return {'items':[dict(metadata=dict(name=name,uid='own'))]} if '--field-selector' not in args else {'items':[]}
            if 'job' in args:return dict(metadata=dict(uid='own'))
            if 'pods' in args:return {'items':[pod]} if not events or 'delete' not in events else {'items':[]}
            raise AssertionError(args)
        def call(*args,**kw):
            if 'logs' in args:events.append('raw');return 'raw-private'
            if 'delete' in args:
                self.assertEqual(json.loads(kw['data'])['preconditions'],{'uid':'own'});events.append('delete');return ''
            if 'wait' in args:return ''
            raise AssertionError(args)
        with patch.object(self.i,'target'),patch.object(self.i,'obj',side_effect=obj),patch.object(self.i,'call',side_effect=call),patch.object(self.i,'barriers'):
            with self.assertRaisesRegex(RuntimeError,'owned helper retired'):self.i.retire_binding()
        self.assertEqual(events,['aux-failed','raw','delete'])
        self.assertEqual(self.i.pending(),{self.run})
        self.assertTrue(any(e.get('event')=='initialization-provisioner-capture-gap' for e in m.s.life.native_cron_events(self.state)))

    def test_delete_uid_precondition_and_all_helper_absence(self):
        name='nc-binding-'+self.run
        with patch.object(self.i,'obj',side_effect=[dict(metadata=dict(uid='own')),{'items':[]},{'items':[]}]),patch.object(self.i,'call') as call:
            self.i.delete_binding(name,'own')
            self.assertEqual(json.loads(call.call_args_list[0].kwargs['data'])['preconditions'],{'uid':'own'})
        with patch.object(self.i,'obj',return_value=dict(metadata=dict(uid='foreign'))),patch.object(self.i,'call',side_effect=AssertionError('delete')):
            with self.assertRaisesRegex(RuntimeError,'UID'):self.i.delete_binding(name,'own')

if __name__=='__main__':unittest.main()
