#!/usr/bin/env python3
"""OFFLINE: runtime subprocesses forbidden; private fixtures only."""
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
spec=importlib.util.spec_from_file_location('preflight',ROOT/'scripts/talos-proof-nextcloud-preflight.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name).resolve()/str(uuid.uuid4());self.state.mkdir(mode=0o700)
        for p in (patch.object(m.s.life,'CANONICAL_DATA_STATE',self.state),
                  patch.object(subprocess,'run',side_effect=AssertionError('OFFLINE runtime forbidden')),
                  patch.object(subprocess,'Popen',side_effect=AssertionError('OFFLINE runtime forbidden'))):
            p.start();self.addCleanup(p.stop)
        self.run=str(uuid.uuid4());self.i=m.Preflight(self.state,self.run)
        self.path=self.state/'active';p=patch.dict(os.environ,TALOS_PROOF_DATA_LEASE=str(self.path));p.start();self.addCleanup(p.stop)
        self.r=dict(action='release-preflight',phases=['release-preflight'],group='nextcloud',stage='cron',run_id=self.run,
            authorization_id=str(uuid.uuid4()),issued=time.time()-1,expires=time.time()+3000,
            state_dir=str(self.state),namespace=m.s.NS,context='proof',endpoint=m.s.life.EXPECTED_ENDPOINT,
            namespace_uid='namespace-owned',node_uid='node-owned',budget_mib=832,synthetic_age=False,cleanup_authorized=True,
            selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'],html_claim='nextcloud-data',
            reviewed_source_sha256={name:m.digest((ROOT/name).read_bytes()) for name in m.SOURCES},
            reviewed_artifact_sha256={name:m.digest((ROOT/name).read_bytes()) for name in m.ARTIFACTS},object_uids={},backend_images={})
        self.cache={'namespace/'+m.s.NS:{'metadata':{'uid':self.r['namespace_uid']}}}
        for name in ('nextcloud','postgres','redis','nextcloud-cron'):
            d=copy.deepcopy(self.i.approved(name));kind='cronjob' if name=='nextcloud-cron' else 'deployment'
            d['metadata'].update(uid=str(uuid.uuid4()),namespace=m.s.NS);self.cache[kind+'/'+name]=d
            self.r['object_uids'][kind+'/'+name]=d['metadata']['uid']
            if name in ('postgres','redis'):self.r['backend_images'][name]=d['spec']['template']['spec']['containers'][0]['image']
        uid=str(uuid.uuid4());self.r['object_uids']['secret/proof-credentials']=uid;self.cache['secret/proof-credentials']={'metadata':{'uid':uid,'name':'proof-credentials','namespace':m.s.NS}}
        for name in ('nextcloud-data','postgres-data','redis-data'):
            puid=str(uuid.uuid4());vuid=str(uuid.uuid4());pv='pvc-'+puid
            self.r['object_uids']['pvc/'+name]=puid;self.r['object_uids']['pv/'+pv]=vuid
            self.cache['pvc/'+name]=dict(metadata=dict(name=name,namespace=m.s.NS,uid=puid),status=dict(phase='Bound'),spec=dict(storageClassName='proof-local',volumeName=pv))
            self.cache['pv/'+pv]=dict(metadata=dict(name=pv,uid=vuid),spec=dict(storageClassName='proof-local',claimRef=dict(name=name,namespace=m.s.NS,uid=puid)))
        names={'default-deny','dns','nextcloud-to-postgres-ingress','nextcloud-to-postgres-egress','nextcloud-to-redis-ingress','nextcloud-to-redis-egress'}
        self.r['network_policy_uids']={}
        for d in m.s.yaml.safe_load_all((ROOT/'kubernetes/apps/data/nextcloud/networkpolicy.yaml').read_text()):
            if d['metadata']['name'] not in names:continue
            name=d['metadata']['name'];uid=str(uuid.uuid4());d['metadata'].update(namespace=m.s.NS,uid=uid)
            self.cache['networkpolicy/'+name]=d;self.r['network_policy_uids'][name]=uid
        self.i.scope='release-preflight';self.origin_fixture();self.write()

    def write(self):
        if not self.path.exists():
            fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        self.path.write_text(json.dumps(self.r));self.path.chmod(0o600)

    def artifact(self,name,d):
        p=self.state/name
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps(d))
        return str(p),m.digest(p.read_bytes())

    def origin_fixture(self):
        self.old_php='<?php /* ORIGINAL private payload, not new code */'
        old_sources={name:('a'*64) for name in m.SOURCES[:-1]}
        old_sources['scripts/talos-proof-nextcloud-cron.php']=m.digest(self.old_php.encode())
        old_sources['scripts/talos-proof-nextcloud-cron.py']=m.digest(Path(m.s.cron.__file__).read_bytes())
        old={**copy.deepcopy(self.r),'action':'run','phases':list(m.s.cron.PHASES),'synthetic_age':True,
             'issued':time.time()-5000,'expires':time.time()-1000,'reviewed_source_sha256':old_sources}
        old.pop('authorization_id')
        self.r['origin_receipt_path'],self.r['origin_receipt_sha256']=self.artifact(str(uuid.uuid4()),old)
        self.r['origin_source_sha256']=old_sources
        job=m.s.cron.job('preflight',self.run);self.name=job['metadata']['name'];self.uid=str(uuid.uuid4())
        self.r['preflight_job_uid']=self.uid
        self.r['origin_preflight_document_sha256']=m.digest(json.dumps(job,sort_keys=True,separators=(',',':')).encode())
        pod=dict(metadata=dict(name=self.name+'-pod',namespace=m.s.NS,uid=str(uuid.uuid4()),ownerReferences=[dict(kind='Job',name=self.name,uid=self.uid)]),
            spec=copy.deepcopy(job['spec']['template']['spec']),status=dict(phase='Failed',containerStatuses=[dict(name='cli',restartCount=0,state={'terminated':{'exitCode':1,'finishedAt':m.s.datetime.datetime.fromtimestamp(time.time()-1000,m.s.datetime.timezone.utc).isoformat()}})]))
        history=[dict(event='pending',run_id=self.run,intent=m.s.cron.intent(self.run)),
            dict(event='backend-start-intent',run_id=self.run),dict(event='phase-intent',run_id=self.run,phase='preflight',job=job),
            dict(event='phase-created',run_id=self.run,name=self.name,uid=self.uid),
            dict(event='pods',run_id=self.run,job=self.name,pods={'items':[pod]}),
            dict(event='private-log',run_id=self.run,job=self.name,pod=pod['metadata']['name'],container='cli',log=json.dumps({'status':'BLOCKED_OR_FAILED','error_type':'RuntimeException'})),
            dict(event='blocked-pending-cleanup',run_id=self.run,active=None),dict(event='stop-intent',run_id=self.run),
            dict(event='stop-pods',run_id=self.run,pods={'items':[]})]
        history.extend(dict(event='memory',run_id=self.run,kubelet=900,talos=900,at=time.time()-2000) for _ in range(3))
        self.r['origin_journal_sha256']={}
        for e in history:
            p=self.i.save(e);self.r['origin_journal_sha256'][p.name]=m.digest(p.read_bytes())
        stopped=dict(at=time.time()-500,namespace=dict(metadata=dict(uid=self.r['namespace_uid'])),nodes=[dict(metadata=dict(uid=self.r['node_uid']))],pods={'items':[]},controllers={'items':[copy.deepcopy(self.cache[k]) for k in self.r['object_uids'] if k.startswith(('deployment/','cronjob/'))]})
        self.r['origin_stop_snapshot_path'],self.r['origin_stop_snapshot_sha256']=self.artifact(str(uuid.uuid4()),stopped)
        uid=str(uuid.uuid4());self.r['payload_configmap_uid']=uid
        cm=dict(kind='ConfigMap',metadata=dict(name='nextcloud-cron-payload-'+self.run,namespace=m.s.NS,uid=uid),data={'native.php':self.old_php})
        self.cache['configmap/'+cm['metadata']['name']]=cm

    def obj(self,*args):
        if args==('get','pods','-A') or args==('get','deployments,statefulsets,daemonsets,cronjobs,jobs','-A'):return {'items':[]}
        return copy.deepcopy(self.cache[args[-2]+'/'+args[-1]])

    def test_release_positive_readonly_original_expiry_inert_one_clean_no_native_acceptance(self):
        original={name:(self.state/name).read_bytes() for name in self.r['origin_journal_sha256']}
        with patch.object(m.s.life,'lease'),patch.object(self.i,'obj',side_effect=self.obj),patch.object(m.s.life,'kube',side_effect=AssertionError('no runtime mutation in fixture')):
            self.i.release_preflight()
        for name,raw in original.items():self.assertEqual((self.state/name).read_bytes(),raw)
        self.assertFalse(self.i.pending())
        events=m.s.life.native_cron_events(self.state)
        self.assertEqual(sum(e['event']=='pending' for e in events),1);self.assertEqual(sum(e['event']=='clean' for e in events),1)
        obs=next(e for e in events if e['event']=='preflight-release-observation')
        self.assertFalse(obs['native_acceptance']);self.assertEqual(obs['historical_failure_gate'],'unknown')
        with self.assertRaises(RuntimeError):self.i.release_preflight()

    def test_release_hash_source_uid_namespace_or_original_receipt_drift_blocks_before_api(self):
        baseline=copy.deepcopy(self.r)
        for changes in (dict(origin_receipt_sha256='0'*64),dict(origin_journal_sha256={}),dict(preflight_job_uid='foreign'),
                        dict(namespace_uid='foreign'),dict(origin_source_sha256={}),dict(reviewed_source_sha256={}),dict(reviewed_artifact_sha256={}),
                        dict(origin_journal_sha256={'../other.json':'0'*64}),dict(phases=['preflight']),dict(action='run')):
            self.r={**copy.deepcopy(baseline),**changes};self.write()
            with self.subTest(changes=changes),patch.object(m.s.life,'lease',side_effect=AssertionError('no API before provenance')):
                with self.assertRaises((RuntimeError,ValueError)):self.i.release_preflight()
            self.i.original=None
        self.r=baseline

    def test_release_later_unknown_unconfirmed_foreign_pending_and_duplicate_history_block(self):
        for event in (dict(event='phase-intent',phase='fixture'),dict(event='phase-created',name='nc-cron-'+self.run,uid='foreign'),
                      dict(event='cleanup-intent'),dict(event='stop-unconfirmed'),dict(event='unknown'),
                      dict(event='pending',run_id=str(uuid.uuid4())),
                      dict(event='phase-created',name=self.name,uid=self.uid)):
            p=self.i.save({'run_id':self.run,**event})
            with self.subTest(event=event),self.assertRaises(RuntimeError):self.i.release_provenance(self.r)
            p.unlink()  # fixture isolation only, never runtime history mutation

    def test_release_changed_history_even_rehashed_nonreadonly_job_or_stop_not_confirmed_blocks(self):
        for fault in ('rw','env','command','stop'):
            name=next(n for n in self.r['origin_journal_sha256'] if json.loads((self.state/n).read_text())['event']=='phase-intent')
            p=self.state/name;before=p.read_bytes();oldhash=self.r['origin_journal_sha256'][name]
            if fault!='stop':
                e=json.loads(before);pod=e['job']['spec']['template']['spec']
                if fault=='rw':pod['containers'][0]['volumeMounts'][0]['readOnly']=False
                elif fault=='env':pod['containers'][0]['env'][0]['value']='fixture'
                else:pod['containers'][0]['command']=['php','/var/www/html/occ']
                p.write_text(json.dumps(e));self.r['origin_journal_sha256'][name]=m.digest(p.read_bytes())
            else:
                stop=Path(self.r['origin_stop_snapshot_path']);raw=stop.read_bytes();data=json.loads(raw)
                data['pods']['items']=[dict(metadata=dict(namespace=m.s.NS))];stop.write_text(json.dumps(data))
                self.r['origin_stop_snapshot_sha256']=m.digest(stop.read_bytes())
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):self.i.release_provenance(self.r)
            p.write_bytes(before);self.r['origin_journal_sha256'][name]=oldhash
            if fault=='stop':stop.write_bytes(raw);self.r['origin_stop_snapshot_sha256']=m.digest(raw)

    def test_release_current_retained_uid_payload_and_global_helpers_drift_never_clean(self):
        for fault in ('pvc','pv','namespace','policy','payload','helper'):
            saved=copy.deepcopy(self.cache)
            if fault=='pvc':self.cache['pvc/nextcloud-data']['metadata']['uid']='foreign'
            elif fault=='pv':self.cache[next(key for key in self.cache if key.startswith('pv/'))]['metadata']['uid']='foreign'
            elif fault=='namespace':self.cache['namespace/'+m.s.NS]['metadata']['uid']='foreign'
            elif fault=='policy':self.cache['networkpolicy/dns']['spec']['egress']=[{}]
            elif fault=='payload':self.cache['configmap/nextcloud-cron-payload-'+self.run]['data']['native.php']='new code'
            def obj(*args):
                if fault=='helper' and args==('get','pods','-A'):return {'items':[dict(metadata=dict(namespace='proof-validation'))]}
                return self.obj(*args)
            with self.subTest(fault=fault),patch.object(m.s.life,'lease'),patch.object(self.i,'obj',side_effect=obj):
                with self.assertRaises(RuntimeError):self.i.release_preflight()
            self.assertEqual(self.i.pending(),{self.run});self.cache=saved
            # Each new grant is explicit; no same-ID invocation replay.
            self.r['authorization_id']=str(uuid.uuid4());self.write();self.i.original=None

    def test_release_call_rejects_every_mutator_and_app_command(self):
        for verb in ('create','patch','delete','exec','run','cp','port-forward','logs','config'):
            with self.subTest(verb=verb),patch.object(m.s.life,'kube',side_effect=AssertionError('no calls')):
                with self.assertRaisesRegex(RuntimeError,'read-only'):self.i.call(verb,'anything')

    def diagnostic_fixture(self):
        # A different new transaction, after independently authorized release.
        self.i.run=str(uuid.uuid4());self.i.scope='diagnose-preflight';self.r.update(run_id=self.i.run,action='diagnose-preflight',phases=['diagnose-preflight'],authorization_id=str(uuid.uuid4()))
        for key in list(self.r):
            if key.startswith('origin_') or key in ('preflight_job_uid','payload_configmap_uid'):self.r.pop(key)
        self.r['backend_forensics_profile']=m.BACKEND_PROFILE
        self.write();self.r['document_sha256']=self.i.document_hashes();self.write()
        return self.r

    def backend_fixture(self):
        self.diagnostic_fixture();self.trace=[];self.backend_pods={};self.rs={}
        for name in ('postgres','redis'):
            spec=copy.deepcopy(self.i.approved(name)['spec']['template']['spec']);spec['nodeName']='talos-proof'
            rsname=name+'-rs'
            self.rs[rsname]=dict(metadata=dict(name=rsname,namespace=m.s.NS,uid=rsname+'-uid',ownerReferences=[dict(kind='Deployment',name=name,uid=self.r['object_uids']['deployment/'+name],controller=True)]))
            self.backend_pods[name]=dict(metadata=dict(name=name+'-pod',namespace=m.s.NS,uid=name+'-uid',labels={'app.kubernetes.io/name':name},ownerReferences=[dict(kind='ReplicaSet',name=rsname,uid=rsname+'-uid',controller=True)]),spec=spec,status=dict(phase='Running',containerStatuses=[dict(name=spec['containers'][0]['name'],containerID='containerd://'+name,ready=True,restartCount=0,lastState={},state={'running':{}})]))
        self.metrics={'memory.current':'1024\n','memory.peak':'2048\n','memory.events':'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n','memory.stat':'anon 1024\nfile 0\n'}

    def backend_kube(self,*args,data=None):
        self.trace.append(args)
        if args[:3]==('get','namespace',m.s.NS): return json.dumps(self.cache['namespace/'+m.s.NS])
        if args[:2]==('get','nodes'):return json.dumps({'items':[{'metadata':{'name':'talos-proof','uid':self.r['node_uid']}}]})
        if 'replicaset' in args:return json.dumps(self.rs[args[4]])
        if 'pod' in args and 'get' in args:return json.dumps(next(p for p in self.backend_pods.values() if p['metadata']['name']==args[4]))
        if 'pods' in args:return json.dumps({'items':list(self.backend_pods.values())})
        if 'exec' in args:return self.metrics[args[-1].split('/')[-1]]
        if 'logs' in args:return 'private backend log'
        if 'patch' in args:return '{}'
        if 'wait' in args:return '{}'
        if 'deployments,statefulsets,daemonsets,cronjobs,jobs' in args:return json.dumps({'items':[]})
        raise AssertionError(args)

    def test_backend_actual_capture_current_and_previous_and_strict_envelope(self):
        for fault in (None,'restart','resources','terminating','duplicate'):
            self.backend_fixture()
            p=self.backend_pods['postgres']
            if fault=='restart':p['status']['containerStatuses'][0].update(restartCount=1,lastState={'terminated':{'reason':'OOMKilled'}})
            if fault=='resources':p['spec']['containers'][0]['resources']['limits']['memory']='999Mi'
            if fault=='terminating':p['metadata']['deletionTimestamp']='now'
            if fault=='duplicate':
                other=copy.deepcopy(p);other['metadata'].update(name='postgres-replacement',uid='replacement');self.backend_pods['extra']=other
            with self.subTest(fault=fault),patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=self.backend_kube):
                if fault is None:self.i.backend_forensics('postgres')
                else:
                    with self.assertRaises(RuntimeError):self.i.backend_forensics('postgres')
            logs=[a for a in self.trace if 'logs' in a];execs=[a for a in self.trace if 'exec' in a]
            self.assertEqual(any('--previous' in a for a in logs),fault=='restart')
            self.assertEqual(len(execs),8 if fault=='duplicate' else 4)
            self.assertTrue(logs)

    def test_backend_actual_identity_drift_refuses_exec(self):
        for fault in ('node','owner','uid','container'):
            self.backend_fixture();bound=copy.deepcopy(self.backend_pods['postgres'])
            if fault=='node':self.backend_pods['postgres']['spec']['nodeName']='other'
            elif fault=='owner':self.rs['postgres-rs']['metadata']['ownerReferences'][0]['uid']='unknown'
            elif fault=='uid':self.backend_pods['postgres']['metadata']['uid']='replacement'
            else:self.backend_pods['postgres']['status']['containerStatuses'][0]['containerID']='replacement'
            self.i.backend_exec_binding=bound
            args=('-n',m.s.NS,'exec','postgres-pod','-c',bound['spec']['containers'][0]['name'],'--request-timeout=5s','--','/usr/bin/timeout','2','/bin/cat','/sys/fs/cgroup/memory.current')
            with self.subTest(fault=fault),patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=self.backend_kube):
                with self.assertRaises(RuntimeError):self.i.call(*args)
            self.assertFalse(any('exec' in a for a in self.trace))

    def test_backend_exact_exec_allowlist_and_post_identity_check(self):
        self.backend_fixture();bound=copy.deepcopy(self.backend_pods['postgres']);self.i.backend_exec_binding=bound
        args=('-n',m.s.NS,'exec','postgres-pod','-c',bound['spec']['containers'][0]['name'],'--request-timeout=5s','--','/usr/bin/timeout','2','/bin/cat','/sys/fs/cgroup/memory.current')
        bad=[args+('-i',),args[:-1]+('/etc/passwd',),args[:-2]+('sh','/sys/fs/cgroup/memory.current'),args[:4]+('-c','other')+args[6:],args[:3]+('deployment/postgres',)+args[4:]]
        with patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=self.backend_kube):
            for command in bad:
                with self.assertRaises(RuntimeError):self.i.call(*command)
        self.assertEqual(self.trace,[])
        def kube(*a,data=None):
            result=self.backend_kube(*a,data=data)
            if 'exec' in a:self.backend_pods['postgres']['metadata']['uid']='changed-after-read'
            return result
        with patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=kube):
            with self.assertRaises(RuntimeError):self.i.call(*args)

    def test_backend_metrics_missing_malformed_and_oom_never_zero(self):
        self.backend_fixture();m.Preflight.backend_metrics(self.metrics,'postgres')
        for key,value in (('memory.current',''),('memory.current','0'),('memory.peak','999999999999'),('memory.events','oom 0\noom_kill 0'),('memory.stat','anon -1\nfile 0'),('memory.stat','anon 1\nanon 2\nfile 0'),('memory.events',self.metrics['memory.events'].replace('oom 0','oom 1')),('memory.events',self.metrics['memory.events'].replace('max 0','max 1'))):
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):m.Preflight.backend_metrics({**self.metrics,key:value},'postgres')
        with self.assertRaises(RuntimeError):m.Preflight.backend_metrics({},'redis')

    def test_backend_capture_failure_independent_stop_and_helper_retirement(self):
        self.backend_fixture();name='nc-preflight-'+self.i.run
        self.i.save(dict(event='phase-created',run_id=self.i.run,name=name,uid='helper-uid'))
        def kube(*a,data=None):
            if 'exec' in a and a[3]=='postgres-pod':raise RuntimeError('capture failed')
            return self.backend_kube(*a,data=data)
        with (patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=kube),
              patch.object(self.i,'forensics',return_value=({'items':[]},{},[])),patch.object(self.i,'delete_own_job') as retire,
              patch.object(self.i,'require_stopped'),patch.object(self.i,'stopped_world')):
            with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.i.stop()
        retire.assert_called_once_with(name)
        for backend in ('postgres','redis'):
            patch_index=next(j for j,a in enumerate(self.trace) if 'patch' in a and a[4]==backend)
            self.assertTrue(any('logs' in a and a[3]==backend+'-pod' for a in self.trace[:patch_index]))
        self.assertTrue(any('exec' in a and a[3]=='redis-pod' for a in self.trace))
        self.assertFalse(any(e.get('event')=='clean' for e in m.s.life.native_cron_events(self.state)))

    def test_backend_missing_logs_and_counter_output_remain_capture_gaps(self):
        for fault in ('logs','counter','unknown-owner','vanished-lifetime'):
            self.backend_fixture()
            if fault=='counter':self.metrics['memory.events']='oom not-a-number'
            if fault=='unknown-owner':self.rs['postgres-rs']['metadata']['ownerReferences'][0]['uid']='unknown'
            if fault=='vanished-lifetime':
                old=copy.deepcopy(self.backend_pods['postgres']);old['metadata'].update(name='old-postgres',uid='old-uid')
                self.i.save(dict(event='backend-observed-pod',run_id=self.i.run,backend='postgres',pod=old))
            def kube(*a,data=None):
                if fault=='logs' and 'logs' in a:raise RuntimeError('logs unavailable')
                return self.backend_kube(*a,data=data)
            with self.subTest(fault=fault),patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=kube):
                with self.assertRaises(RuntimeError):self.i.backend_forensics('postgres')
            if fault=='unknown-owner':self.assertFalse(any('exec' in a for a in self.trace))
            events=[e for e in m.s.life.native_cron_events(self.state) if e.get('run_id')==self.i.run]
            self.assertTrue(any(e.get('event')=='backend-capture-gap' for e in events))
            self.assertTrue(any(e.get('event')=='backend-capture-pod' for e in events))
            self.assertFalse(any(e.get('event')=='clean' for e in events))

    def test_stop_captures_both_before_patches_then_intentional_pg_absence(self):
        self.backend_fixture()
        def kube(*a,data=None):
            result=self.backend_kube(*a,data=data)
            if 'patch' in a and a[4]=='postgres':self.backend_pods.pop('postgres')
            return result
        with (patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=kube),
              patch.object(self.i,'require_stopped'),patch.object(self.i,'stopped_world')):
            self.i.stop()
        first_patch=next(j for j,a in enumerate(self.trace) if 'patch' in a)
        for name in ('postgres','redis'):
            self.assertEqual(sum('exec' in a and a[3]==name+'-pod' for a in self.trace[:first_patch]),4)
        self.assertNotIn('postgres',self.backend_pods)
        self.assertFalse(getattr(self.i,'cleanup_uncertainty',[]))

    def test_stop_auxiliary_journal_failures_do_not_suppress_owned_cleanup(self):
        for fault in ('stop-intent','failure-handler','all-writes'):
            self.backend_fixture();name='nc-preflight-'+self.i.run
            self.i.save(dict(event='pending',run_id=self.i.run,scope='diagnose-preflight'))
            self.i.save(dict(event='phase-created',run_id=self.i.run,name=name,uid='helper-uid'))
            helper=dict(metadata=dict(name='helper-pod',namespace=m.s.NS,uid='helper-pod-uid',ownerReferences=[dict(kind='Job',name=name,uid='helper-uid')]),
                spec=dict(containers=[dict(name='cli')]),status=dict(containerStatuses=[dict(name='cli',restartCount=0)]))
            original_save=self.i.save;retired=[];helper_reads=[]
            def save(value):
                if fault=='all-writes' or value['event']==('stop-intent' if fault=='stop-intent' else 'diagnostic-cleanup-failed'):
                    raise OSError('journal unavailable')
                return original_save(value)
            def kube(*a,data=None):
                if 'exec' in a and a[3]=='postgres-pod' and fault=='failure-handler':raise RuntimeError('capture failure')
                if '-l' in a:
                    helper_reads.append(a);return json.dumps({'items':[helper]})
                if 'job' in a and 'get' in a:return json.dumps({'metadata':{'uid':'helper-uid'}})
                if a[:2]==('delete','--raw'):retired.append(a);return '{}'
                if 'jobs' in a:return json.dumps({'items':[]})
                return self.backend_kube(*a,data=data)
            with (self.subTest(fault=fault),patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=kube),
                  patch.object(self.i,'save',side_effect=save),patch.object(self.i,'require_stopped'),patch.object(self.i,'stopped_world')):
                with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.i.stop()
            self.assertEqual([a[4] for a in self.trace if 'patch' in a],['postgres','redis'])
            self.assertTrue(helper_reads)
            self.assertEqual(bool(retired),fault!='all-writes')
            self.assertIn(self.i.run,self.i.pending())
            self.assertTrue(self.i.cleanup_uncertainty)

    def test_exec_execution_drift_refused_but_all_known_container_logs_attempted(self):
        for fault in ('image','PATH','volume','security','extra','init','missing-status','resources'):
            self.backend_fixture();pod=self.backend_pods['postgres'];c=pod['spec']['containers'][0]
            if fault=='image':c['image']='unreviewed:image'
            if fault=='PATH':c.setdefault('env',[]).append(dict(name='PATH',value='/hostile'))
            if fault=='volume':pod['spec'].setdefault('volumes',[]).append(dict(name='unreviewed',emptyDir={}))
            if fault=='security':c['securityContext']={'privileged':True}
            if fault=='resources':c['resources']['limits']['memory']='999Mi'
            if fault=='extra':pod['spec']['containers'].append(dict(name='unexpected',image='unreviewed:image'))
            if fault=='init':
                pod['spec']['initContainers']=[dict(name='unexpected-init',image='unreviewed:image')]
                pod['status']['initContainerStatuses']=[dict(name='unexpected-init',restartCount=1,lastState={'terminated':{'exitCode':1}})]
            if fault=='missing-status':pod['status']['containerStatuses']=[]
            self.i.backend_exec_binding=copy.deepcopy(pod)
            args=('-n',m.s.NS,'exec','postgres-pod','-c',c['name'],'--request-timeout=5s','--','/usr/bin/timeout','2','/bin/cat','/sys/fs/cgroup/memory.current')
            with (self.subTest(fault=fault),patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=self.backend_kube)):
                if fault!='resources':
                    with self.assertRaises(RuntimeError):self.i.call(*args)
                    self.assertFalse(any('exec' in a for a in self.trace))
                with self.assertRaises(RuntimeError):self.i.backend_forensics('postgres')
            logs=[a for a in self.trace if 'logs' in a]
            self.assertTrue(any(a[5]==c['name'] for a in logs))
            if fault in ('extra','init'):
                extra='unexpected' if fault=='extra' else 'unexpected-init'
                self.assertTrue(any(a[5]==extra for a in logs))
                self.assertEqual(any(a[5]==extra and '--previous' in a for a in logs),fault=='init')
            self.assertEqual(sum('exec' in a for a in self.trace),4 if fault=='resources' else 0)

    def test_exec_live_execution_envelope_drift_pre_and_post_read(self):
        for when in ('pre','post'):
            self.backend_fixture();self.i.backend_exec_binding=copy.deepcopy(self.backend_pods['postgres'])
            def drift():self.backend_pods['postgres']['spec']['containers'][0].setdefault('env',[]).append(dict(name='PATH',value='/changed'))
            if when=='pre':drift()
            def kube(*a,data=None):
                result=self.backend_kube(*a,data=data)
                if when=='post' and 'exec' in a:drift()
                return result
            args=('-n',m.s.NS,'exec','postgres-pod','-c',self.backend_pods['postgres']['spec']['containers'][0]['name'],'--request-timeout=5s','--','/usr/bin/timeout','2','/bin/cat','/sys/fs/cgroup/memory.current')
            with self.subTest(when=when),patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=kube):
                with self.assertRaises(RuntimeError):self.i.call(*args)
            self.assertEqual(sum('exec' in a for a in self.trace),int(when=='post'))
            events=[e for e in m.s.life.native_cron_events(self.state) if e.get('run_id')==self.i.run]
            self.assertEqual(any(e.get('event')=='backend-cgroup' for e in events),when=='post')

    def test_backend_profile_missing_rejects_before_api(self):
        self.diagnostic_fixture();self.r.pop('backend_forensics_profile');self.write()
        with patch.object(m.s.life,'kube',side_effect=AssertionError('no API')):
            with self.assertRaisesRegex(RuntimeError,'exact separate'):self.i.authorize(start=True)

    def test_release_complete_memory_multiplicity_and_nonvacuous_snapshot(self):
        self.i.release_provenance(self.r)
        name=next(n for n in self.r['origin_journal_sha256'] if json.loads((self.state/n).read_text())['event']=='memory')
        raw=(self.state/name).read_bytes();sha=self.r['origin_journal_sha256'].pop(name);(self.state/name).unlink()
        with self.assertRaisesRegex(RuntimeError,'twelve-event'):self.i.release_provenance(self.r)
        (self.state/name).write_bytes(raw);(self.state/name).chmod(0o600);self.r['origin_journal_sha256'][name]=sha
        path=Path(self.r['origin_stop_snapshot_path']);baseline=json.loads(path.read_bytes())
        for fault in ('empty','missing','sparse','uid','active','unsuspended'):
            data=copy.deepcopy(baseline)
            if fault=='empty':data['controllers']['items']=[]
            elif fault=='missing':data['controllers']['items'].pop()
            elif fault=='sparse':data['controllers']['items']=[{'kind':'Deployment','metadata':{'namespace':m.s.NS},'spec':{'replicas':0}}]
            elif fault=='uid':data['controllers']['items'][0]['metadata']['uid']='foreign'
            elif fault=='active':data['controllers']['items'][0]['spec']['replicas']=1
            else:next(c for c in data['controllers']['items'] if c['kind']=='CronJob')['spec']['suspend']=False
            path.write_text(json.dumps(data));self.r['origin_stop_snapshot_sha256']=m.digest(path.read_bytes())
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):self.i.release_provenance(self.r)

    def test_actual_diagnostic_admission_global_jobs_ds_and_backend_ownership(self):
        self.diagnostic_fixture();self.i.consume()
        objects=[];pods=[]
        def obj(*args):
            if args==('get','jobs,daemonsets','-A'):return {'items':objects}
            if args==('get','pods','-A'):return {'items':pods}
            if args==('get','deployments,statefulsets','-A'):return {'items':[self.cache['deployment/'+n] for n in ('postgres','redis','nextcloud')]}
            if args==('get','cronjobs','-A'):return {'items':[self.cache['cronjob/nextcloud-cron']]}
            return self.obj(*args)
        with patch.object(self.i,'obj',side_effect=obj),patch.object(self.i,'memory_admission'),patch.object(m.s.life,'lease'):
            self.i.admission()  # actual identities/envelopes/policies/controller barriers
            for kind in ('Job','DaemonSet'):
                for ns in (m.s.NS,'proof-other'):
                    for spec in ({'suspend':True},{'replicas':0},{}):
                        objects[:]=[dict(kind=kind,metadata=dict(namespace=ns),spec=spec,status={'succeeded':1})]
                        with self.subTest(kind=kind,ns=ns,spec=spec),self.assertRaises(RuntimeError):self.i.admission()
            objects.clear()
            for app in ('postgres','redis'):
                spec=copy.deepcopy(self.i.approved(app)['spec']['template']['spec'])
                pods.append(dict(metadata=dict(namespace=m.s.NS,labels={'app.kubernetes.io/name':app},ownerReferences=[dict(kind='ReplicaSet',name=app+'-rs',uid=app+'-rs-owned',controller=True)]),spec=spec,
                    status=dict(phase='Running',conditions=[dict(type='Ready',status='True')],containerStatuses=[dict(name=c['name'],ready=True,restartCount=0,state={'running':{}}) for c in spec['containers']])))
                self.cache['replicaset/'+app+'-rs']=dict(metadata=dict(namespace=m.s.NS,uid=app+'-rs-owned',ownerReferences=[dict(kind='Deployment',name=app,uid=self.r['object_uids']['deployment/'+app],controller=True)]))
            with self.assertRaisesRegex(RuntimeError,'before'):self.i.admission()
            self.i.backends_started=True;self.i.admission()  # two ordinary Running/Ready healthy Pods
            healthy=copy.deepcopy(pods)
            for fault in ('duplicate','terminating-replacement','terminal','unknown-phase','pending','unready','restart','oom','envelope','missing'):
                pods[:]=copy.deepcopy(healthy)
                if fault=='duplicate':pods.append(copy.deepcopy(pods[0]))
                elif fault=='terminating-replacement':
                    pods.append(copy.deepcopy(pods[0]));pods[0]['metadata']['deletionTimestamp']='2026-11-12T00:00:00Z'
                elif fault=='terminal':pods[0]['status']['phase']='Failed'
                elif fault=='unknown-phase':pods[0]['status'].pop('phase')
                elif fault=='pending':pods[0]['status']['phase']='Pending'
                elif fault=='unready':pods[0]['status']['containerStatuses'][0]['ready']=False
                elif fault=='restart':pods[0]['status']['containerStatuses'][0]['restartCount']=1
                elif fault=='oom':pods[0]['status']['containerStatuses'][0]['lastState']={'terminated':{'reason':'OOMKilled'}}
                elif fault=='envelope':pods[0]['spec']['containers'][0]['resources']['limits']['memory']='385Mi'
                else:pods.pop()
                with self.subTest(fault=fault),self.assertRaisesRegex(RuntimeError,'memory budget' if fault=='duplicate' else '.'):
                    self.i.admission()
            pods[:]=copy.deepcopy(healthy)
            self.cache['replicaset/postgres-rs']['metadata']['ownerReferences'][0]['uid']='foreign'
            with self.assertRaisesRegex(RuntimeError,'ownership'):self.i.admission()
            self.cache['replicaset/postgres-rs']['metadata']['ownerReferences'][0]['uid']=self.r['object_uids']['deployment/postgres']
            self.cache['deployment/nextcloud']['spec']['replicas']=1
            with self.assertRaisesRegex(RuntimeError,'unselected'):self.i.admission()
            self.cache['deployment/nextcloud']['spec']['replicas']=0
            self.cache['cronjob/nextcloud-cron']['spec']['suspend']=False
            with self.assertRaises(RuntimeError):self.i.admission()

    def test_actual_stop_independent_guarded_backends_and_helper_failures(self):
        self.diagnostic_fixture()
        name='nc-preflight-'+self.i.run
        self.i.save(dict(event='phase-created',run_id=self.i.run,name=name,uid='helper-owned'))
        self.i.save(dict(event='pending',run_id=self.i.run,scope='diagnose-preflight'))
        for fault in ('postgres','redis','capture','retire','drift','owner','uid',None):
            operations=[];self.i.jobs={};self.i.helper_cleanup_attempted=set();self.i.cleanup_uncertainty=[]
            if fault=='drift':self.i.save(dict(event='diagnostic-failed',run_id=self.i.run,error_type='RuntimeException'))
            def kube(*args,data=None):
                if 'patch' in args:
                    backend=args[4];operations.append(backend)
                    patchdoc=json.loads(args[7]);self.assertEqual(patchdoc[0]['value'],self.r['object_uids']['deployment/'+backend]);self.assertEqual(patchdoc[1]['value'],0)
                    if fault==backend:raise RuntimeError('patch failure')
                    return '{}'
                if args[:3]==('get','namespace',m.s.NS):return json.dumps(self.cache['namespace/'+m.s.NS])
                if 'logs' in args:
                    operations.append('capture')
                    if fault=='capture':raise RuntimeError('capture failed')
                    return 'bounded log'
                if args[:3]==('-n',m.s.NS,'get') and args[3]=='job':return json.dumps({'metadata':{'uid':'foreign' if fault=='uid' else 'helper-owned'}})
                if args[:2]==('delete','--raw'):
                    operations.append('retire');self.assertEqual(json.loads(data)['preconditions'],{'uid':'helper-owned'})
                    if fault=='retire':raise RuntimeError('retirement failed')
                    return '{}'
                if 'pods' in args:
                    if '-l' in args and 'retire' not in operations:
                        spec=copy.deepcopy(self.i.documents()[1]['spec']['template']['spec'])
                        if fault=='drift':spec['containers'][0]['resources']['limits']['memory']='999Mi'
                        return json.dumps({'items':[dict(metadata=dict(name='helper-pod',namespace=m.s.NS,ownerReferences=[dict(kind='Job',name=name,uid='foreign' if fault=='owner' else 'helper-owned')]),spec=spec)]})
                    return json.dumps({'items':[]})
                if 'jobs' in args:return json.dumps({'items':[]})
                if 'deployments,statefulsets,daemonsets,cronjobs,jobs' in args:return json.dumps({'items':[]})
                if 'deployment' in args:return json.dumps({'spec':{'replicas':0}})
                if 'wait' in args:return '{}'
                raise AssertionError(args)
            with self.subTest(fault=fault),patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=kube):
                if fault in (None,'drift'):
                    with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.i.stop()
                else:
                    with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.i.stop()
            self.assertIn(self.i.run,self.i.pending())
            self.assertEqual(operations[:2],['postgres','redis'])
            self.assertIn('capture',operations)
            if fault in ('capture','owner','uid'):self.assertNotIn('retire',operations)
            else:self.assertLess(operations.index('capture'),operations.index('retire'))
            events=[e for e in m.s.life.native_cron_events(self.state) if e.get('run_id')==self.i.run]
            self.assertFalse(any(e.get('event') in ('clean','diagnostic-result') for e in events))
            if fault=='drift':
                self.assertTrue(any(e.get('event')=='diagnostic-failed' for e in events))
                self.assertTrue(any(e.get('event')=='pods' and e['pods']['items'][0]['spec']['containers'][0]['resources']['limits']['memory']=='999Mi' for e in events))

    def test_diagnostic_exact_readonly_documents_no_public_phase_no_cross_authority(self):
        self.diagnostic_fixture();cm,job=self.i.documents();pod=job['spec']['template']['spec'];c=pod['containers'][0]
        self.assertTrue(c['volumeMounts'][0]['readOnly']);self.assertTrue(c['securityContext']['readOnlyRootFilesystem']);self.assertEqual(c['env'][0]['value'],'diagnose-preflight')
        self.assertEqual(c['resources']['limits']['memory'],'192Mi');self.assertNotIn('intent.json',cm['data'])
        self.assertNotIn('diagnose-preflight',m.s.cron.PHASES)
        with self.assertRaises(ValueError):m.s.cron.job('diagnose-preflight',self.i.run)
        self.i.authorize(start=True)
        self.r['action']='run';self.write()
        with self.assertRaises(RuntimeError):self.i.authorize(start=True)

    def test_diagnostic_mutation_boundary_no_extra_job_adoption_or_backend_patch(self):
        self.diagnostic_fixture();cm,job=self.i.documents()
        with patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=AssertionError('no mutation')):
            for verb in ('exec','run','apply','replace','port-forward','config'):
                with self.assertRaises(RuntimeError):self.i.call(verb,'anything')
            for doc in ({'kind':'Secret'}, {**job,'metadata':{'name':'foreign'}},cm):
                with self.assertRaises(RuntimeError):self.i.call('create','-f','-','-o','json',data=json.dumps(doc))
            with self.assertRaises(RuntimeError):self.i.call('delete','--raw','foreign','-f','-',data='{}')
            with self.assertRaises(RuntimeError):self.i.call('-n',m.s.NS,'patch','deployment','nextcloud','--type=json','-p','[]')
        self.i.save(dict(event='diagnostic-payload-intent',run_id=self.i.run,document=cm))
        self.i.save(dict(event='diagnostic-payload-created',run_id=self.i.run,name=cm['metadata']['name'],uid='own'))
        with patch.object(self.i,'authorize',return_value=self.r),patch.object(m.s.life,'kube',side_effect=AssertionError('no replay')):
            with self.assertRaisesRegex(RuntimeError,'single diagnostic'):self.i.call('create','-f','-','-o','json',data=json.dumps(cm))

    def test_diagnostic_failure_can_clean_only_after_confirmed_stop_no_fixture_authority(self):
        self.diagnostic_fixture()
        # Original fixture remains pending, so entry must first fail locally.
        with self.assertRaisesRegex(RuntimeError,'pending'):self.i.diagnose_preflight()
        for stop_fails in (False,True):
            self.i.run=str(uuid.uuid4());self.r.update(run_id=self.i.run,authorization_id=str(uuid.uuid4()));self.write()
            self.r['document_sha256']=self.i.document_hashes();self.write();self.i.original=None
            with (patch.object(self.i,'pending',return_value=set()),patch.object(self.i,'admission',side_effect=RuntimeError('diagnostic failed')),
                  patch.object(self.i,'stop',side_effect=RuntimeError('unreachable') if stop_fails else None),
                  patch.object(self.i,'require_stopped'),patch.object(self.i,'stopped_world')):
                with self.assertRaises(RuntimeError):self.i.diagnose_preflight()
            events=[e for e in m.s.life.native_cron_events(self.state) if e.get('run_id')==self.i.run]
            self.assertEqual(any(e['event']=='clean' for e in events),not stop_fails)
            if not stop_fails:self.assertFalse(next(e for e in events if e['event']=='diagnostic-result')['success'])
            else:self.assertTrue(any(e['event']=='stop-unconfirmed' for e in events))
            with self.assertRaisesRegex(RuntimeError,'reused'):self.i.diagnose_preflight()

    def test_diagnostic_capture_before_uid_retirement_and_unknown_uid_reject(self):
        self.diagnostic_fixture();cm,job=self.i.documents();events=[]
        with (patch.object(self.i,'admission'),patch.object(self.i,'call',return_value=json.dumps({'metadata':{'uid':'own'}})),
              patch.object(self.i,'forensics',side_effect=lambda n:(events.append('raw') or ({'items':[]},{},[]))),
              patch.object(self.i,'validate_forensics',side_effect=RuntimeError('payload failure')),
              patch.object(self.i,'delete_own_job',side_effect=lambda n:events.append('delete-own'))):
            with self.assertRaisesRegex(RuntimeError,'payload failure'):self.i.diagnostic_helper(job)
        self.assertEqual(events,['raw','delete-own'])
        self.i.jobs={}
        with patch.object(self.i,'authorize',return_value=self.r),patch.object(self.i,'call',side_effect=AssertionError('no unknown deletion')):
            with self.assertRaisesRegex(RuntimeError,'UID'):self.i.delete_own_job('nc-preflight-'+self.i.run)


    def test_diagnostic_positive_one_readonly_helper_then_confirmed_clean(self):
        self.diagnostic_fixture();events=[]
        def helper(job):
            self.assertTrue(job['spec']['template']['spec']['containers'][0]['volumeMounts'][0]['readOnly'])
            self.assertEqual(job['spec']['template']['spec']['containers'][0]['env'][0]['value'],'diagnose-preflight')
            events.append('readonly-helper')
        with (patch.object(self.i,'pending',return_value=set()),patch.object(self.i,'admission'),patch.object(self.i,'require_stopped'),
              patch.object(self.i,'scale_backends',side_effect=lambda n:events.append(('scale',n))),
              patch.object(self.i,'call',return_value=json.dumps({'metadata':{'uid':'cm-own'}})),
              patch.object(self.i,'diagnostic_helper',side_effect=helper),patch.object(self.i,'stop',side_effect=lambda:events.append('stop')),
              patch.object(self.i,'stopped_world',side_effect=lambda:events.append('absence'))):
            self.i.diagnose_preflight()
        self.assertEqual(events,[('scale',1),'readonly-helper','stop','absence'])
        found=[e for e in m.s.life.native_cron_events(self.state) if e.get('run_id')==self.i.run]
        self.assertTrue(next(e for e in found if e['event']=='diagnostic-result')['success'])
        self.assertEqual(sum(e['event']=='clean' for e in found),1)

    def test_diagnostic_helper_capture_failure_still_attempts_recorded_uid_stop(self):
        self.diagnostic_fixture();events=[]
        def helper(job):
            self.i.jobs[job['metadata']['name']]='observed-own'
            self.i.save(dict(event='phase-created',run_id=self.i.run,name=job['metadata']['name'],uid='observed-own'))
            events.append('capture-failed');raise RuntimeError('API capture unreachable')
        with (patch.object(self.i,'pending',return_value=set()),patch.object(self.i,'admission'),patch.object(self.i,'require_stopped'),
              patch.object(self.i,'scale_backends'),patch.object(self.i,'call',return_value=json.dumps({'metadata':{'uid':'cm-own'}})),
              patch.object(self.i,'diagnostic_helper',side_effect=helper),patch.object(self.i,'stop',side_effect=lambda:events.append('guarded-stop')),
              patch.object(self.i,'stopped_world')):
            with self.assertRaisesRegex(RuntimeError,'capture unreachable'):self.i.diagnose_preflight()
        self.assertEqual(events,['capture-failed','guarded-stop'])
        result=next(e for e in m.s.life.native_cron_events(self.state) if e.get('run_id')==self.i.run and e['event']=='diagnostic-result')
        self.assertFalse(result['success'])

    def test_diagnostic_actual_pod_owner_envelope_counters_and_backend_result_required(self):
        self.diagnostic_fixture();cm,job=self.i.documents()
        for fault in (None,'owner','namespace','rw','empty','db','redis','counters'):
            pod=dict(metadata=dict(name='cli-pod',namespace=m.s.NS,ownerReferences=[dict(kind='Job',name=job['metadata']['name'],uid='own')]),
                spec=copy.deepcopy(job['spec']['template']['spec']),status=dict(containerStatuses=[dict(name='cli',restartCount=0,state={'terminated':{'exitCode':0}})]))
            observation=dict(phase='diagnose-preflight',result=dict(empty=True,db_tables=0,redis_authenticated=True),
                cgroups={'memory.current':'1','memory.peak':'2','memory.events':'oom 0\noom_kill 0','memory.stat':'anon 1\nfile 0'})
            if fault=='owner':pod['metadata']['ownerReferences'][0]['uid']='unknown'
            elif fault=='namespace':pod['metadata']['namespace']='foreign'
            elif fault=='rw':pod['spec']['containers'][0]['volumeMounts'][0]['readOnly']=False
            elif fault=='empty':observation['result']['empty']=False
            elif fault=='db':observation['result']['db_tables']=False
            elif fault=='redis':observation['result']['redis_authenticated']=False
            elif fault=='counters':observation['cgroups']['memory.events']='oom 0'
            evidence=({'items':[pod]},{('cli-pod','cli'):json.dumps(observation)},[]);events=[]
            with (self.subTest(fault=fault),patch.object(self.i,'admission'),patch.object(self.i,'call',return_value=json.dumps({'metadata':{'uid':'own'}})),
                  patch.object(self.i,'forensics',side_effect=lambda n:(events.append('capture') or evidence)),
                  patch.object(self.i,'delete_own_job',side_effect=lambda n:events.append('uid-retire'))):
                if fault is None:self.i.diagnostic_helper(job)
                else:
                    with self.assertRaises(RuntimeError):self.i.diagnostic_helper(job)
            self.assertEqual(events,['capture','uid-retire'])

    def test_parent_review_missing_or_changed_blocks_before_consumption_or_runtime(self):
        self.diagnostic_fixture()
        review=m.s.cron.ROOT/m.s.cron.PARENT_REVIEW
        read=Path.read_bytes
        for missing in (False,True):
            def changed(path):
                if path==review:
                    if missing:raise FileNotFoundError('missing review')
                    return b'changed review'
                return read(path)
            with self.subTest(missing=missing),patch.object(Path,'read_bytes',changed),patch.object(m.s.life,'kube',side_effect=AssertionError('no runtime')):
                with self.assertRaises((RuntimeError,FileNotFoundError)):self.i.consume()
            self.assertFalse(any(e.get('event')=='preflight-authorized' and e.get('run_id')==self.i.run for e in m.s.life.native_cron_events(self.state)))
        self.i.consume()
        with patch.object(Path,'read_bytes',changed),patch.object(m.s.life,'kube',side_effect=AssertionError('no runtime after drift')):
            with self.assertRaises(FileNotFoundError):self.i.call('get','namespace',m.s.NS)

    def test_diagnostic_requires_exact_compiler_packaged_and_index_hash_bindings(self):
        self.diagnostic_fixture();baseline=copy.deepcopy(self.r)
        changes=[('reviewed_source_sha256','scripts/talos-proof-nextcloud-cron.py')]+[
            ('reviewed_artifact_sha256',name) for name in m.ARTIFACTS]
        for field,name in changes:
            self.r=copy.deepcopy(baseline);self.r[field][name]='0'*64;self.write()
            with self.subTest(field=field,name=name),patch.object(m.s.life,'lease',side_effect=AssertionError('no API before exact bindings')):
                with self.assertRaisesRegex(RuntimeError,'drift'):self.i.authorize(start=True)

if __name__=='__main__':unittest.main()
