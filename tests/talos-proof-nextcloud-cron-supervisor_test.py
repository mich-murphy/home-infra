#!/usr/bin/env python3
"""No API, VM, image, or production runtime calls: every command forbidden/mocked."""
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
spec=importlib.util.spec_from_file_location('supervisor',ROOT/'scripts/talos-proof-nextcloud-cron-supervisor.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        os.chmod(self.temp.name,0o700)
        p=patch.object(m.life,'CANONICAL_DATA_STATE',Path(self.temp.name).resolve());p.start();self.addCleanup(p.stop)
        self.run=str(uuid.uuid4()); self.s=m.Supervisor(Path(self.temp.name).resolve(),self.run)
        for name in ('run','Popen'):
            p=patch.object(subprocess,name,side_effect=AssertionError('offline command forbidden'))
            p.start();self.addCleanup(p.stop)
        self.path=Path(self.temp.name).resolve()/'receipt'
        self.receipt=dict(group='nextcloud',stage='cron',run_id=self.run,phases=list(m.cron.PHASES),budget_mib=832,
            selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'],synthetic_age=True,cleanup_authorized=True,state_dir=str(self.s.state),expires=time.time()+3000,context='proof',node_uid='own',endpoint=m.life.EXPECTED_ENDPOINT)
        self.env=patch.dict(os.environ,TALOS_PROOF_DATA_LEASE=str(self.path));self.env.start();self.addCleanup(self.env.stop)

    def write(self,changes=None):
        self.path.write_text(json.dumps({**self.receipt,**(changes or {})})); self.path.chmod(0o600)

    def test_no_api_before_exact_unexpired_receipt(self):
        for changes in [dict(stage='web'),dict(group='immich'),dict(expires=0),dict(run_id=str(uuid.uuid4())),
                        dict(phases=['cron']),dict(budget_mib=640),dict(endpoint='production'),dict(context=''),
                        dict(cleanup_authorized=False),dict(synthetic_age=False)]:
            self.write(changes)
            with patch.object(m.life,'lease',side_effect=AssertionError('API before lease')),self.assertRaises(RuntimeError):
                self.s.authorize()

    def test_receipt_is_immutable_and_full_window_required(self):
        self.write()
        with patch.object(m.life,'lease',return_value=self.receipt):
            self.s.authorize(start=True)
            self.write(dict(expires=time.time()+4000))
            with self.assertRaisesRegex(RuntimeError,'immutable'): self.s.authorize()
        self.s.original=None;self.write(dict(expires=time.time()+100))
        with self.assertRaisesRegex(RuntimeError,'window'): self.s.authorize(start=True)

    def test_private_immutable_uuid_journal_and_pending_blocks_run_not_stop(self):
        path=self.s.save(dict(event='pending',run_id=self.run))
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        with patch.object(self.s,'authorize'),patch.object(self.s,'admission',side_effect=AssertionError('pending activation')):
            with self.assertRaisesRegex(RuntimeError,'pending'): self.s.run_sequence()
        with patch.object(self.s,'authorize'),patch.object(self.s,'obj',return_value={'items':[]}),patch.object(self.s,'call') as call:
            self.s.stop()
            self.assertTrue(any('scale' in c.args for c in call.call_args_list))
        self.s.save(dict(event='clean',run_id=self.run));self.assertFalse(self.s.pending())

    def test_legacy_activation_sees_pending_and_stop_does_not_use_it(self):
        self.s.save(dict(event='pending',run_id=self.run))
        self.assertEqual(m.life.pending_native_cron(self.s.state),{self.run})
        self.s.save(dict(event='clean',run_id=self.run))
        self.assertEqual(m.life.pending_native_cron(self.s.state),set())

    def test_wrong_retained_uid_blocks(self):
        with patch.object(self.s,'authorize',return_value={'object_uids':{}}),patch.object(self.s,'obj',return_value={'metadata':{'uid':'wrong'}}):
            with self.assertRaisesRegex(RuntimeError,'UID'): self.s.identities()

    def test_active_helper_blocks_before_measurement_or_creation(self):
        pod=dict(metadata=dict(namespace='proof-validation',name='unlabelled'))
        with patch.object(self.s,'identities'),patch.object(self.s,'obj',return_value={'items':[pod]}):
            with self.assertRaisesRegex(RuntimeError,'pod'):self.s.admission()

    def phase_mocks(self, evidence=None):
        self.s.html='restored-html'
        return patch.object(self.s,'call',side_effect=lambda *a,**k: json.dumps({'metadata':{'uid':'own-job'}}) if a[0]=='create' else '')

    def test_forensics_gap_prevents_delete_and_next_phase(self):
        with patch.object(self.s,'admission'),self.phase_mocks(),patch.object(self.s,'forensics',side_effect=RuntimeError('capture gap')),patch.object(self.s,'delete_own_job') as delete:
            with self.assertRaisesRegex(RuntimeError,'capture gap'):self.s.phase('fixture')
            delete.assert_not_called();self.assertIsNotNone(self.s.active)

    def test_validation_failure_deletes_after_raw_capture(self):
        for error in (RuntimeError('BLOCKED'),ValueError('invalid JSON'),RuntimeError('OOM')):
            events=[]
            with patch.object(self.s,'admission'),self.phase_mocks(),patch.object(self.s,'forensics',side_effect=lambda n:events.append('raw')),patch.object(self.s,'validate_forensics',side_effect=error),patch.object(self.s,'delete_own_job',side_effect=lambda n:events.append('delete')):
                with self.assertRaises(type(error)):self.s.phase('fixture')
            self.assertEqual(events,['raw','delete'])

    def test_raw_previous_logs_captured_before_blocked_json_oom_validation(self):
        pod=dict(metadata={'name':'own'},spec={'containers':[{'name':'cli'}]},status={'containerStatuses':[{'name':'cli','restartCount':1}]})
        for raw in ('invalid JSON',json.dumps({'status':'BLOCKED_OR_FAILED'}),json.dumps({'cgroups':{'memory.peak':'1','memory.current':'1','memory.stat':'','memory.events':'oom 1'}})):
            with patch.object(self.s,'obj',return_value={'items':[pod]}),patch.object(self.s,'call',return_value=raw) as call:
                evidence=self.s.forensics('own')
                self.assertEqual(call.call_count,2)
                self.assertIn('--previous',call.call_args_list[1].args)
                with self.assertRaises((RuntimeError,ValueError)):self.s.validate_forensics(evidence)
        self.assertTrue(any(e['event']=='private-previous-log' for e in m.life.native_cron_events(self.s.state)))

    def test_capture_current_gap_still_attempts_previous(self):
        pod=dict(metadata={'name':'own'},spec={'containers':[{'name':'cli'}]},status={'containerStatuses':[{'name':'cli','restartCount':1}]})
        with patch.object(self.s,'obj',return_value={'items':[pod]}),patch.object(self.s,'call',side_effect=[RuntimeError('API gap'),'previous']) as call:
            evidence=self.s.forensics('own')
            with self.assertRaisesRegex(RuntimeError,'capture gap'):self.s.validate_forensics(evidence)
            self.assertEqual(call.call_count,2)

    def test_log_gap_and_unreachable_api_preserves_raw_error_and_blocks_delete(self):
        pod=dict(metadata={'name':'own'},spec={'containers':[{'name':'cli'}]},status={})
        error=subprocess.CalledProcessError(1,['offline'],output='raw-current',stderr='private-error')
        with patch.object(self.s,'obj',side_effect=[{'items':[pod]},RuntimeError('unreachable')]),patch.object(self.s,'call',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'API unreachable'):self.s.forensics('own')
        gaps=[e for e in m.life.native_cron_events(self.s.state) if e.get('event')=='capture-gap']
        self.assertEqual(gaps[-1]['stdout'],'raw-current');self.assertEqual(gaps[-1]['stderr'],'private-error')

    def test_shared_scope_rejects_alternate_directory_before_api(self):
        with self.assertRaisesRegex(RuntimeError,'canonical'):m.Supervisor(Path(self.temp.name).resolve()/'hidden',str(uuid.uuid4()))
        with patch.object(m.life,'private',side_effect=AssertionError('must not create alternate dir')):
            with self.assertRaisesRegex(RuntimeError,'canonical'):m.life.shared_data_state(Path(self.temp.name).resolve()/'hidden')

    def test_only_uuid_journals_and_run_replay(self):
        (self.s.state/'credentials.json').write_text('not JSON or a journal')
        self.assertEqual(self.s.pending(),set())
        self.s.save(dict(event='pending',run_id=self.run));self.s.save(dict(event='clean',run_id=self.run))
        with patch.object(self.s,'authorize'),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
            with self.assertRaisesRegex(RuntimeError,'reused'):self.s.run_sequence()
        self.s.save(dict(event='pending',run_id=self.run))
        self.assertEqual(self.s.pending(),{self.run})
        self.assertEqual(m.life.pending_native_cron(self.s.state),{self.run})

    def test_entire_backend_envelope_rejects_pod_limit_overhead_init_and_resources(self):
        approved=self.s.approved('postgres')['spec']['template']['spec']
        import copy
        for field,value in [('overhead',{'memory':'1Mi'}),('resources',{'limits':{'memory':'1Gi'}}),('initContainers',[{'name':'hidden'}])]:
            bad=copy.deepcopy(approved);bad[field]=value
            with self.assertRaisesRegex(RuntimeError,'envelope'):self.s.envelope(bad,approved)
        bad=copy.deepcopy(approved);bad['containers'][0]['resources']['limits']['cpu']='2000m'
        with self.assertRaisesRegex(RuntimeError,'envelope'):self.s.envelope(bad,approved)

    def test_cron_security_fails_before_fixture_mutation(self):
        approved=self.s.approved('nextcloud-cron')['spec']['jobTemplate']['spec']['template']['spec']
        import copy
        for field,value in [('initContainers',[{'name':'hidden'}]),('automountServiceAccountToken',True),('overhead',{'memory':'1Mi'})]:
            bad=copy.deepcopy(approved);bad[field]=value
            with self.assertRaisesRegex(RuntimeError,'envelope'):self.s.envelope(bad,approved)

    def test_bound_pvc_rejects_missing_wrong_class_or_claimref_before_mutation(self):
        pvc=dict(metadata={'uid':'p'},status={'phase':'Bound'},spec={'volumeName':'pv','storageClassName':'proof-local'})
        pv=dict(metadata={'uid':'v','name':'pv'},spec={'storageClassName':'proof-local','claimRef':{'uid':'wrong','name':'html','namespace':m.NS}})
        with patch.object(self.s,'obj',side_effect=[pvc,pv]),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
            with self.assertRaisesRegex(RuntimeError,'claim UID'):self.s.bound_claim('html',{'pvc/html':'p','pv/pv':'v'})
        pvc['spec']['storageClassName']='other'
        with patch.object(self.s,'obj',return_value=pvc):
            with self.assertRaisesRegex(RuntimeError,'proof-local'):self.s.bound_claim('html',{'pvc/html':'p'})

    def test_cleanup_order_no_main_phases_and_new_receipt(self):
        self.s.save(dict(event='pending',run_id=self.run));events=[]
        r={**self.receipt,'action':'cleanup','phases':['cleanup']};self.path.write_text(json.dumps(r));self.path.chmod(0o600)
        with patch.object(m.life,'lease'),patch.object(self.s,'identities',side_effect=lambda:events.append('identities')),patch.object(self.s,'retire_prior_jobs',side_effect=lambda:events.append('retire')),patch.object(self.s,'admission',side_effect=lambda:events.append('832')),patch.object(self.s,'require_stopped'),patch.object(self.s,'call',side_effect=lambda *a,**k:events.append('scale' if 'scale' in a else 'wait')),patch.object(self.s,'phase',side_effect=lambda p:events.append(p)),patch.object(self.s,'stop',side_effect=lambda:events.append('stop')):
            self.s.cleanup_only()
        self.assertEqual(events,['identities','retire','832','scale','wait','cleanup','stop'])
        self.assertFalse(self.s.pending())

    def test_cleanup_rejects_old_run_receipt_and_short_new_window(self):
        self.s.scope='cleanup';self.write()
        with self.assertRaisesRegex(RuntimeError,'receipt'):self.s.authorize()
        self.write(dict(action='cleanup',phases=['cleanup'],expires=time.time()+100))
        with patch.object(m.life,'lease'),self.assertRaisesRegex(RuntimeError,'window'):self.s.cleanup_only()

    def test_stop_retires_own_failed_job_before_waiting_all_pods(self):
        events=[]
        with patch.object(self.s,'authorize'),patch.object(self.s,'obj',return_value={'items':[]}),patch.object(self.s,'call',side_effect=lambda *a,**k:events.append('scale' if 'scale' in a else 'wait')),patch.object(self.s,'retire_prior_jobs',side_effect=lambda:events.append('retire')):
            self.s.stop()
        self.assertEqual(events,['scale','retire','wait'])

    def identity_fixture(self):
        import copy
        objects={}
        receipt=dict(object_uids={},backend_images={},html_claim='restored-html')
        for kind,name in [('secret','proof-credentials'),('deployment','nextcloud'),('deployment','postgres'),('deployment','redis'),('cronjob','nextcloud-cron')]:
            obj=copy.deepcopy(self.s.approved(name)) if name not in ('proof-credentials',) else {}
            obj['metadata']={'uid':name+'-uid'}
            receipt['object_uids'][kind+'/'+name]=obj['metadata']['uid'];objects[(kind,name)]=obj
        for name in ('nextcloud','nextcloud-cron'):
            spec=objects[('deployment' if name=='nextcloud' else 'cronjob',name)]['spec']
            pod=spec['template']['spec'] if name=='nextcloud' else spec['jobTemplate']['spec']['template']['spec']
            for v in pod['volumes']:
                if 'persistentVolumeClaim' in v:v['persistentVolumeClaim']['claimName']='restored-html'
        for name in ('postgres','redis'):
            receipt['backend_images'][name]=objects[('deployment',name)]['spec']['template']['spec']['containers'][0]['image']
        for name in ('restored-html','postgres-data','redis-data'):
            receipt['object_uids']['pvc/'+name]=name+'-uid';receipt['object_uids']['pv/'+name]=name+'-pv-uid'
            objects[('pvc',name)]=dict(metadata={'uid':name+'-uid'},spec={'storageClassName':'proof-local','volumeName':name},status={'phase':'Bound'})
            objects[('pv',name)]=dict(metadata={'uid':name+'-pv-uid','name':name},spec={'storageClassName':'proof-local','claimRef':{'uid':name+'-uid','name':name,'namespace':m.NS}})
        return receipt,objects

    def test_all_desired_claims_validated_before_any_mutation(self):
        r,objects=self.identity_fixture();seen=[]
        def obj(*args):
            seen.append(args[-2:]);return objects[args[-2:]]
        with patch.object(self.s,'authorize',return_value=r),patch.object(self.s,'obj',side_effect=obj),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
            self.s.identities()
        self.assertEqual(self.s.html,'restored-html')
        self.assertTrue(all(('pvc',name) in seen for name in ('restored-html','postgres-data','redis-data')))
        self.assertNotIn(('pvc','nextcloud-data'),seen)

    def test_alias_mismatch_and_missing_backend_pvc_block_without_stop_mutation(self):
        for fault in ('alias','missing-pvc','cron-init','cron-resource'):
            r,objects=self.identity_fixture()
            if fault=='alias': r['html_claim']='old-html'
            elif fault=='missing-pvc': del objects[('pvc','postgres-data')]
            else:
                pod=objects[('cronjob','nextcloud-cron')]['spec']['jobTemplate']['spec']['template']['spec']
                if fault=='cron-init':pod['initContainers']=[{'name':'unreviewed'}]
                else:pod['containers'][0]['resources']['limits']['cpu']='2000m'
            with patch.object(self.s,'authorize',return_value=r),patch.object(self.s,'obj',side_effect=lambda *a:objects[a[-2:]]),patch.object(self.s,'call',side_effect=AssertionError('mutation')),patch.object(self.s,'stop',side_effect=AssertionError('preflight must not stop')):
                with self.assertRaises((RuntimeError,KeyError)):self.s.run_sequence()

    def test_uid_precondition_and_absence_required_for_own_job_deletion(self):
        name='nc-fixture-'+self.run;self.s.jobs[name]='own'
        with patch.object(self.s,'obj',side_effect=[{'metadata':{'uid':'own'}},{'items':[]},{'items':[]}]),patch.object(self.s,'call') as call:
            self.s.delete_own_job(name)
            self.assertEqual(json.loads(call.call_args_list[0].kwargs['data'])['preconditions'],{'uid':'own'})
        with patch.object(self.s,'obj',return_value={'metadata':{'uid':'other'}}),patch.object(self.s,'call',side_effect=AssertionError('delete')):
            with self.assertRaisesRegex(RuntimeError,'UID mismatch'):self.s.delete_own_job(name)

    def test_api_unreachable_failure_records_pending_and_stop_unconfirmed(self):
        self.s.html='restored-html'
        with patch.object(self.s,'authorize'),patch.object(self.s,'admission'),patch.object(self.s,'require_stopped'),patch.object(self.s,'call',side_effect=RuntimeError('API unreachable')),patch.object(self.s,'stop',side_effect=RuntimeError('API unreachable')):
            with self.assertRaisesRegex(RuntimeError,'unreachable'):self.s.run_sequence()
        self.assertEqual(self.s.pending(),{self.run})
        self.assertTrue(any(e.get('event')=='stop-unconfirmed' for e in m.life.native_cron_events(self.s.state)))

if __name__=='__main__':unittest.main()
