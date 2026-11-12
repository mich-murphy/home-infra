#!/usr/bin/env python3
"""No API, VM, image, or production runtime calls: every command forbidden/mocked."""
import importlib.util
import copy
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
            selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'],synthetic_age=True,cleanup_authorized=True,state_dir=str(self.s.state),expires=time.time()+3000,namespace_uid='ns-own',context='proof',node_uid='own',endpoint=m.life.EXPECTED_ENDPOINT)
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
        with patch.object(self.s,'authorize'),patch.object(self.s,'scale_backends',side_effect=lambda n:self.s.call('scale')),patch.object(self.s,'obj',return_value={'items':[]}),patch.object(self.s,'call') as call:
            self.s.stop()
            self.assertTrue(any('scale' in c.args for c in call.call_args_list))
        self.s.save(dict(event='clean',run_id=self.run));self.assertFalse(self.s.pending())

    def test_legacy_activation_sees_pending_and_stop_does_not_use_it(self):
        self.s.save(dict(event='pending',run_id=self.run))
        self.assertEqual(m.life.pending_native_cron(self.s.state),{self.run})
        self.s.save(dict(event='clean',run_id=self.run))
        self.assertEqual(m.life.pending_native_cron(self.s.state),set())

    def test_wrong_retained_uid_blocks(self):
        with patch.object(self.s,'target',return_value={'object_uids':{}}),patch.object(self.s,'obj',return_value={'metadata':{'uid':'wrong'}}):
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

    def native_cgroup_evidence(self,changes=None):
        # Untouched four native kernel observations retained from the read-only
        # binding helper, NOT a Nextcloud native runtime/capacity observation.
        cg={'memory.current': '1900544', 'memory.peak': '3973120', 'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0', 'memory.stat': 'anon 282624\nfile 0\nkernel 581632\nkernel_stack 32768\npagetables 319488\nsec_pagetables 0\npercpu 336\nsock 0\nvmalloc 36864\nshmem 0\nzswap 0\nzswapped 0\nfile_mapped 0\nfile_dirty 0\nfile_writeback 0\nswapcached 0\nanon_thp 0\nfile_thp 0\nshmem_thp 0\ninactive_anon 0\nactive_anon 176128\ninactive_file 0\nactive_file 0\nunevictable 0\nslab_reclaimable 70976\nslab_unreclaimable 105024\nslab 176000\nworkingset_refault_anon 0\nworkingset_refault_file 0\nworkingset_activate_anon 0\nworkingset_activate_file 0\nworkingset_restore_anon 0\nworkingset_restore_file 0\nworkingset_nodereclaim 0\npgdemote_kswapd 0\npgdemote_direct 0\npgdemote_khugepaged 0\npgdemote_proactive 0\npgscan 0\npgsteal 0\npswpin 0\npswpout 0\npgscan_kswapd 0\npgscan_direct 0\npgscan_khugepaged 0\npgscan_proactive 0\npgsteal_kswapd 0\npgsteal_direct 0\npgsteal_khugepaged 0\npgsteal_proactive 0\npgfault 2616\npgmajfault 0\npgrefill 0\npgactivate 0\npgdeactivate 0\npglazyfree 0\npglazyfreed 0\nswpin_zero 0\nswpout_zero 0\nzswpin 0\nzswpout 0\nzswpwb 0\nthp_fault_alloc 0\nthp_collapse_alloc 0\nthp_swpout 0\nthp_swpout_fallback 0'}
        cg.update(changes or {})
        pod=dict(metadata=dict(name='own'),status=dict(containerStatuses=[dict(
            name='cli',state={'terminated':{'exitCode':0}})]))
        return {'items':[pod]},{('own','cli'):json.dumps({'cgroups':cg})},[]

    def test_native_kernel_counter_example_and_sequential_reads(self):
        self.s.validate_forensics(self.native_cgroup_evidence())
        # Sequential kernel reads need not obey peak >= current.
        self.s.validate_forensics(self.native_cgroup_evidence({'memory.current':'10','memory.peak':'1'}))
        self.s.validate_forensics(self.native_cgroup_evidence({'memory.current':str(192*1048576),'memory.peak':str(192*1048576),
            'memory.stat':'anon 0\nfile 0','memory.events':'oom 0\noom_kill 0\nfuture_counter 3'}))

    def test_native_events_require_actual_oom_counters_and_strict_records(self):
        bad=['','oom 0','oom_kill 0','low 0\nhigh 0',
            'oom 0\noom_kill 0\noom 0','oom 0\noom_kill 0\nother 0\nother 0',
            'oom -1\noom_kill 0','oom 0\noom_kill -1','oom 0\noom_kill 0\nother -1',
            'oom 0\noom_kill 0\nmalformed','oom 0\noom_kill 0 extra',
            'oom 0\n\noom_kill 0','oom 0\noom_kill 1','oom 1\noom_kill 0',
            'oom 0\noom_kill 0\nother 1.5','oom +0\noom_kill 0']
        for value in bad:
            with self.subTest(events=value),self.assertRaises(RuntimeError):
                self.s.validate_forensics(self.native_cgroup_evidence({'memory.events':value}))

    def test_native_stat_requires_anon_file_and_strict_nonnegative_records(self):
        bad=['','anon 0','file 0','other 0','anon -1\nfile 0','anon 0\nfile -1',
            'anon 0\nfile 0\nother -1','anon 0\nfile 0\nanon 0',
            'anon 0\nfile 0\nother 0\nother 0','anon 0\nfile 0 extra',
            'anon 0\nfile 0\nmalformed','anon 0\n\nfile 0','anon 0.1\nfile 0']
        for value in bad:
            with self.subTest(stat=value),self.assertRaises(RuntimeError):
                self.s.validate_forensics(self.native_cgroup_evidence({'memory.stat':value}))

    def test_native_current_and_peak_are_positive_integer_bytes_under_ceiling(self):
        for name in ('memory.current','memory.peak'):
            for value in ('','0','-1','+1','1.5','1e6',' 1','1 ','1\n2',str(192*1048576+1),None,1):
                with self.subTest(name=name,value=value),self.assertRaises(RuntimeError):
                    self.s.validate_forensics(self.native_cgroup_evidence({name:value}))

    def test_native_source_read_gaps_cannot_be_accepted(self):
        for name in ('memory.current','memory.peak','memory.events','memory.stat'):
            for value in ({'gap':'unavailable'},None):
                with self.subTest(name=name,value=value),self.assertRaisesRegex(RuntimeError,'measurement gap'):
                    self.s.validate_forensics(self.native_cgroup_evidence({name:value}))
            evidence=self.native_cgroup_evidence();observation=json.loads(evidence[1][('own','cli')]);del observation['cgroups'][name]
            evidence[1][('own','cli')]=json.dumps(observation)
            with self.assertRaisesRegex(RuntimeError,'measurement gap'):self.s.validate_forensics(evidence)
        php=(ROOT/'scripts/talos-proof-nextcloud-cron.php').read_text()
        capture=php.split('function cgroups(): array {',1)[1].split('function parity(',1)[0]
        self.assertIn("['memory.current', 'memory.peak', 'memory.events', 'memory.stat']",capture)
        self.assertIn("@file_get_contents('/sys/fs/cgroup/' . $file)",capture)
        self.assertIn("$value === false ? ['gap' => 'unavailable'] : trim($value)",capture)

    def network_policy_fixture(self):
        names={'default-deny','dns','nextcloud-to-postgres-ingress',
               'nextcloud-to-postgres-egress','nextcloud-to-redis-ingress','nextcloud-to-redis-egress'}
        policies={d['metadata']['name']:copy.deepcopy(d) for d in m.yaml.safe_load_all(
            (ROOT/'kubernetes/apps/data/nextcloud/networkpolicy.yaml').read_text()) if d['metadata']['name'] in names}
        uids={name:str(uuid.uuid4()) for name in names}
        for name,d in policies.items():d['metadata'].update(namespace=m.NS,uid=uids[name])
        return {**self.receipt,'network_policy_uids':uids},policies

    def test_network_policy_exact_declarations_pass_before_backend_patches(self):
        r,policies=self.network_policy_fixture();events=[]
        r['object_uids']={'deployment/postgres':'pg-own','deployment/redis':'redis-own'}
        def obj(*a):events.append(a[-1]);return copy.deepcopy(policies[a[-1]])
        with patch.object(self.s,'target',return_value=r),patch.object(self.s,'obj',side_effect=obj),patch.object(self.s,'call',side_effect=lambda *a:events.append('patch')):
            self.s.scale_backends(1)
        self.assertEqual(set(events[:6]),set(policies));self.assertEqual(events[6:],['patch','patch'])

    def test_network_policy_missing_bindings_or_live_policy_reject_without_mutation(self):
        r,policies=self.network_policy_fixture()
        for bindings in (None,{},dict(list(r['network_policy_uids'].items())[:-1]),
                         {**r['network_policy_uids'],'extra':'foreign'},
                         {**r['network_policy_uids'],'dns':''}):
            with self.subTest(bindings=bindings),patch.object(self.s,'target',return_value={**r,'network_policy_uids':bindings}),patch.object(self.s,'obj',side_effect=AssertionError('no policy reads before exact bindings')),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
                with self.assertRaisesRegex(RuntimeError,'six network policy'):self.s.scale_backends(1)
        with patch.object(self.s,'target',return_value=r),patch.object(self.s,'obj',side_effect=RuntimeError('missing policy')),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
            with self.assertRaisesRegex(RuntimeError,'missing policy'):self.s.scale_backends(1)

    def test_network_policy_uid_namespace_name_and_full_spec_drift_reject(self):
        r,policies=self.network_policy_fixture()
        for fault in ('uid','namespace','name','terminating','broader','default-deny','dns','unknown-spec'):
            bad=copy.deepcopy(policies)
            if fault in ('uid','namespace','name'):bad['default-deny']['metadata'][fault]='foreign'
            elif fault=='terminating':bad['default-deny']['metadata']['deletionTimestamp']='now'
            elif fault=='broader':bad['nextcloud-to-postgres-ingress']['spec']['ingress']=[{}]
            elif fault=='default-deny':bad['default-deny']['spec']['policyTypes']=['Ingress']
            elif fault=='dns':bad['dns']['spec']['egress']=[{}]
            else:bad['default-deny']['spec']['unknownDefault']=True
            with self.subTest(fault=fault),patch.object(self.s,'target',return_value=r),patch.object(self.s,'obj',side_effect=lambda *a:bad[a[-1]]),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
                with self.assertRaisesRegex(RuntimeError,'identity/spec'):self.s.scale_backends(1)

    def test_admission_checks_policies_before_memory_and_cleanup_before_activation(self):
        events=[]
        with patch.object(self.s,'identities'),patch.object(self.s,'obj',return_value={'items':[]}),patch.object(self.s,'network_policies',side_effect=lambda:events.append('policies')),patch.object(self.s,'memory_admission',side_effect=lambda:events.append('memory')):
            self.s.admission()
        self.assertEqual(events,['policies','memory']);events=[]
        self.s.save(dict(event='pending',run_id=self.run))
        r={**self.receipt,'action':'cleanup','phases':['cleanup']}
        with (patch.object(self.s,'authorize',return_value=r),patch.object(self.s,'target',return_value=r),
              patch.object(self.s,'identities'),patch.object(self.s,'require_stopped'),
              patch.object(self.s,'obj',return_value={'items':[]}),patch.object(self.s,'retire_prior_jobs',side_effect=lambda:events.append('retire')),
              patch.object(self.s,'stop',side_effect=lambda:events.append('stop')),
              patch.object(self.s,'call',side_effect=AssertionError('no backend mutation without policies')),
              patch.object(self.s,'memory_admission',side_effect=AssertionError('policy check first'))):
            with self.assertRaisesRegex(RuntimeError,'six network policy'):self.s.cleanup_only()
        self.assertEqual(events,['retire','stop'])

    def test_owned_helper_retirement_does_not_require_network_policy(self):
        name='nc-fixture-'+self.run;self.s.jobs[name]='own'
        with (patch.object(self.s,'network_policies',side_effect=AssertionError('retirement is policy independent')),
              patch.object(self.s,'obj',side_effect=[{'metadata':{'uid':'own'}},{'items':[]},{'items':[]}]),
              patch.object(self.s,'call') as call):
            self.s.delete_own_job(name)
        self.assertEqual(json.loads(call.call_args_list[0].kwargs['data'])['preconditions'],{'uid':'own'})

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

    def test_exact_canonical_cpu_and_memory_equivalence_but_changed_limits_reject(self):
        import copy
        for name in ('postgres','redis','nextcloud-cron'):
            d=self.s.approved(name)['spec']
            approved=(d['jobTemplate']['spec']['template'] if name=='nextcloud-cron' else d['template'])['spec']
            actual=copy.deepcopy(approved)
            r=actual['containers'][0]['resources']
            for section in ('requests','limits'):
                r[section]['cpu']=str(m.quantity(r[section]['cpu'])) if section=='limits' and name!='nextcloud-cron' else r[section]['cpu']
                r[section]['memory']=str(int(m.quantity(r[section]['memory'])))
            # 1000m becomes 1 in actual API; 500m becomes 0.5 in CronJob.
            if name=='nextcloud-cron':r['limits']['cpu']='0.5'
            self.s.envelope(actual,approved)
            self.s.envelope(actual,approved,actual_pod=True)
            for key,value in [('cpu','2'),('memory','999Mi')]:
                bad=copy.deepcopy(actual);bad['containers'][0]['resources']['limits'][key]=value
                with self.assertRaisesRegex(RuntimeError,'envelope'):self.s.envelope(bad,approved)
            bad=copy.deepcopy(actual);bad['containers'][0]['resources']['limits']['unknown']='1'
            with self.assertRaisesRegex(RuntimeError,'envelope'):self.s.envelope(bad,approved)
            bad=copy.deepcopy(actual);bad['unknownAPIDefault']=True
            with self.assertRaisesRegex(RuntimeError,'envelope'):self.s.envelope(bad,approved)

    def test_explicit_custom_service_account_alias_preserves_identity(self):
        import copy
        approved=dict(containers=[],serviceAccountName='reviewed-custom-account')
        actual={**approved,'serviceAccount':'reviewed-custom-account'}
        for actual_pod in (False,True):
            with self.subTest(actual_pod=actual_pod):
                before=copy.deepcopy(actual)
                self.s.envelope(actual,approved,actual_pod=actual_pod)
                self.assertEqual(actual,before)
                for change in (
                    {'serviceAccount':'foreign-account'},
                    {'serviceAccount':'default'},
                    {'serviceAccountName':'foreign-account'},
                    {'serviceAccount':'foreign-account','serviceAccountName':'foreign-account'},
                    {'serviceAccount':'default','serviceAccountName':'default'},
                    {'unknownServiceAccountDefault':True},
                ):
                    with self.subTest(change=change),self.assertRaisesRegex(RuntimeError,'envelope'):
                        self.s.envelope({**actual,**change},approved,actual_pod=actual_pod)
        # An alias alone is not proof of an explicit matching canonical name,
        # even when its value is the ordinary default service account.
        for alias in ('default','reviewed-custom-account'):
            with self.subTest(alias=alias),self.assertRaisesRegex(RuntimeError,'envelope'):
                self.s.envelope(dict(containers=[],serviceAccount=alias),dict(containers=[]))

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
        with patch.object(m.life,'lease'),patch.object(self.s,'scale_backends',side_effect=lambda n:events.append('scale')),patch.object(self.s,'identities',side_effect=lambda:events.append('identities')),patch.object(self.s,'retire_prior_jobs',side_effect=lambda:events.append('retire')),patch.object(self.s,'admission',side_effect=lambda:events.append('832')),patch.object(self.s,'require_stopped'),patch.object(self.s,'call',side_effect=lambda *a,**k:events.append('scale' if 'scale' in a else 'wait')),patch.object(self.s,'phase',side_effect=lambda p:events.append(p)),patch.object(self.s,'stop',side_effect=lambda:events.append('stop')):
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
        with patch.object(self.s,'authorize'),patch.object(self.s,'scale_backends',side_effect=lambda n:self.s.call('scale')),patch.object(self.s,'obj',return_value={'items':[]}),patch.object(self.s,'call',side_effect=lambda *a,**k:events.append('scale' if 'scale' in a else 'wait')),patch.object(self.s,'retire_prior_jobs',side_effect=lambda:events.append('retire')):
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
        with patch.object(self.s,'target',return_value=r),patch.object(self.s,'obj',side_effect=obj),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
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

    def test_real_kube_failed_completed_process_preserved_privately(self):
        pod=dict(metadata={'name':'own'},spec={'containers':[{'name':'cli'}]},status={})
        failed=subprocess.CompletedProcess(['kubectl','fresh-secret-in-argv'],1,stdout='private-out',stderr='private-err')
        with patch.object(self.s,'authorize'),patch.object(self.s,'obj',return_value={'items':[pod]}),patch.object(subprocess,'run',return_value=failed):
            evidence=self.s.forensics('own')
            self.assertTrue(evidence[2])
            with self.assertRaises(m.life.KubeFailure) as caught:m.life.kube('get','fresh-secret-in-argv')
        for public in (str(caught.exception),repr(caught.exception),str(caught.exception.args)):
            for secret in ('private-out','private-err','fresh-secret-in-argv'):self.assertNotIn(secret,public)
        gaps=[e for e in m.life.native_cron_events(self.s.state) if e.get('event')=='capture-gap']
        self.assertEqual((gaps[-1]['stdout'],gaps[-1]['stderr']),('private-out','private-err'))
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in self.s.state.glob('*.json')))
        with patch.object(m.uuid,'uuid4',return_value=uuid.UUID(next(self.s.state.glob('*.json')).stem)):
            with self.assertRaises(FileExistsError):self.s.save({'event':'overwrite'})

    def test_native_namespace_receipt_and_atomic_stop_uid_patch_without_envelope(self):
        self.write({'namespace_uid':''})
        with patch.object(m.life,'lease',side_effect=AssertionError('API')):
            with self.assertRaisesRegex(RuntimeError,'identity'):self.s.authorize()
        r={**self.receipt,'object_uids':{'deployment/postgres':'pg-own','deployment/redis':'redis-own'}}
        patches=[]
        with patch.object(self.s,'authorize',return_value=r),patch.object(self.s,'obj',return_value={'metadata':{'uid':'replacement'}}),patch.object(self.s,'call',side_effect=AssertionError('mutation')):
            with self.assertRaisesRegex(RuntimeError,'namespace UID'):self.s.scale_backends(0)
        def call(*a,**kw):
            patchdoc=json.loads(a[-1]);patches.append(patchdoc)
            self.assertEqual(patchdoc[0]['op'],'test');self.assertEqual(patchdoc[0]['path'],'/metadata/uid')
            if patchdoc[0]['value']=='pg-own':raise RuntimeError('atomic UID test failed on replacement')
        with patch.object(self.s,'target',return_value=r),patch.object(self.s,'call',side_effect=call),patch.object(self.s,'identities',side_effect=AssertionError('stop must not require full envelope')):
            with self.assertRaisesRegex(RuntimeError,'atomic UID'):self.s.scale_backends(0)
        self.assertEqual(len(patches),1)
        with patch.object(self.s,'target',return_value=r),patch.object(self.s,'call') as mutation:
            self.s.scale_backends(0)
            self.assertEqual(mutation.call_count,2)
            self.assertEqual(json.loads(mutation.call_args.args[-1])[1],dict(op='replace',path='/spec/replicas',value=0))

    def test_full_stop_accepts_bad_spec_only_for_own_namespace_and_atomic_uids(self):
        r={**self.receipt,'object_uids':{'deployment/postgres':'pg-own','deployment/redis':'redis-own'}}
        mutations=[];namespace=['ns-own']
        def kube(*args,**kw):
            if 'namespace' in args:return json.dumps({'metadata':{'uid':namespace[0]}})
            if 'patch' in args:
                patchdoc=json.loads(args[-1]);mutations.append((args[4],patchdoc))
                self.assertEqual(patchdoc[0]['value'],r['object_uids']['deployment/'+args[4]])
                return '{}'
            if 'get' in args:return json.dumps({'items':[]})
            if 'wait' in args:return ''
            raise AssertionError(args)
        # No full retained spec/resource envelope is read or required by stop.
        with patch.object(self.s,'authorize',return_value=r),patch.object(m.life,'kube',side_effect=kube),patch.object(self.s,'identities',side_effect=AssertionError('activation envelope')),patch.object(self.s,'network_policies',side_effect=AssertionError('stop is policy independent')):
            self.s.stop()
            self.assertEqual([x[0] for x in mutations],['postgres','redis'])
            mutations.clear();namespace[0]='replacement'
            with self.assertRaisesRegex(RuntimeError,'namespace UID'):self.s.stop()
            self.assertEqual(mutations,[])

    def test_api_unreachable_failure_records_pending_and_stop_unconfirmed(self):
        self.s.html='restored-html'
        with patch.object(self.s,'authorize'),patch.object(self.s,'admission'),patch.object(self.s,'require_stopped'),patch.object(self.s,'call',side_effect=RuntimeError('API unreachable')),patch.object(self.s,'stop',side_effect=RuntimeError('API unreachable')):
            with self.assertRaisesRegex(RuntimeError,'unreachable'):self.s.run_sequence()
        self.assertEqual(self.s.pending(),{self.run})
        self.assertTrue(any(e.get('event')=='stop-unconfirmed' for e in m.life.native_cron_events(self.s.state)))

class WorkstationSerializationTests(unittest.TestCase):
    """Real bounded child processes; no cluster, host, lease, or runtime calls."""
    def test_legacy_check_to_mutation_serializes_with_initializer_pending(self):
        import select
        import sys
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp).resolve();state.chmod(0o700)
            code = """
import importlib.util,json,os,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('life',sys.argv[1]);life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
state=Path(sys.argv[2]);life.CANONICAL_DATA_STATE=state
life.kube=lambda *a,**k: (_ for _ in ()).throw(AssertionError('NO API'))
life.credentials=lambda *a: (_ for _ in ()).throw(AssertionError('mutation reached'))
sys.argv=['legacy','activate','--group','nextcloud','--stage','web','--state',str(state)]
print('READY',flush=True)
try:life.main()
except RuntimeError as e:
    assert str(e)=='pending native cron cleanup blocks unsafe activation', str(e)
    print('PENDING_BLOCKED',flush=True)
"""
            with patch.object(m.life,'CANONICAL_DATA_STATE',state):
                supervisor=m.Supervisor(state,str(uuid.uuid4()))
            child=subprocess.Popen([sys.executable,'-c',code,str(ROOT/'scripts/talos-proof-data.py'),str(state)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertTrue(select.select([child.stdout],[],[],5)[0]);self.assertEqual(child.stdout.readline().strip(),'READY')
                self.assertFalse(select.select([child.stdout],[],[],0.2)[0])
                self.assertIsNone(child.poll())
                # Legacy is already entering main, but cannot pass the check until
                # initializer has written PENDING and released the same OS lock.
                supervisor.save(dict(event='pending',scope='initialize',run_id=supervisor.run))
                os.close(supervisor.lock_fd);del supervisor.lock_fd
                out,err=child.communicate(timeout=5)
                self.assertEqual(child.returncode,0,err);self.assertEqual(out.strip(),'PENDING_BLOCKED')
                # Process exit auto-frees the directory lock; no inode is unlinked.
                fd=m.life.operation_lock(state,blocking=False);os.close(fd)
            finally:
                if child.poll() is None:child.kill();child.communicate(timeout=5)

    def test_legacy_holds_operation_lock_from_check_through_mutation(self):
        import select
        import sys
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp).resolve();state.chmod(0o700)
            code="""
import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('life',sys.argv[1]);life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
state=Path(sys.argv[2]);life.CANONICAL_DATA_STATE=state
life.kube=lambda *a,**k: (_ for _ in ()).throw(AssertionError('NO API'))
def credentials(*a):
    print('AFTER_CHECK_BEFORE_MUTATION',flush=True)
    assert sys.stdin.readline().strip()=='RELEASE'
    raise RuntimeError('offline boundary')
life.credentials=credentials
sys.argv=['legacy','activate','--group','nextcloud','--stage','web','--state',str(state)]
try:life.main()
except RuntimeError as e:assert str(e)=='offline boundary'
"""
            child=subprocess.Popen([sys.executable,'-c',code,str(ROOT/'scripts/talos-proof-data.py'),str(state)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertTrue(select.select([child.stdout],[],[],5)[0]);self.assertEqual(child.stdout.readline().strip(),'AFTER_CHECK_BEFORE_MUTATION')
                with patch.object(m.life,'CANONICAL_DATA_STATE',state):
                    with self.assertRaisesRegex(RuntimeError,'another data operation'):m.Supervisor(state,str(uuid.uuid4()))
                out,err=child.communicate('RELEASE\n',timeout=5);self.assertEqual(child.returncode,0,err)
                fd=m.life.operation_lock(state,blocking=False);os.close(fd)
            finally:
                if child.poll() is None:child.kill();child.communicate(timeout=5)

if __name__=='__main__':unittest.main()
