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

    def test_wrong_retained_uid_and_wrong_image_block(self):
        with patch.object(self.s,'authorize',return_value={'object_uids':{'pvc/nextcloud-data':'expected'}}),patch.object(self.s,'obj',return_value={'metadata':{'uid':'wrong'}}):
            with self.assertRaisesRegex(RuntimeError,'UID'): self.s.identities()
        r=dict(object_uids={'pvc/nextcloud-data':'p','pv/pv':'pv','secret/proof-credentials':'s','deployment/postgres':'d'},backend_images={'postgres':'pinned'})
        objects=[dict(metadata={'uid':'p'},status={'phase':'Bound'},spec={'volumeName':'pv'}),
                 dict(metadata={'uid':'pv','name':'pv'},spec={'claimRef':{'uid':'p'}}),dict(metadata={'uid':'s'}),
                 dict(metadata={'uid':'d'},spec={'template':{'spec':{'containers':[{'image':'wrong','resources':{'limits':{'memory':'384Mi'}}}]}}})]
        with patch.object(self.s,'authorize',return_value=r),patch.object(self.s,'obj',side_effect=objects):
            with self.assertRaisesRegex(RuntimeError,'image'): self.s.identities()

    def test_active_helper_blocks_before_measurement_or_creation(self):
        pod=dict(metadata=dict(namespace='proof-validation',name='unlabelled'))
        with patch.object(self.s,'identities'),patch.object(self.s,'obj',return_value={'items':[pod]}):
            with self.assertRaisesRegex(RuntimeError,'pod'):self.s.admission()

    def test_forensics_gap_prevents_delete_and_next_phase(self):
        with patch.object(self.s,'admission'),patch.object(self.s,'call') as call,patch.object(self.s,'forensics',side_effect=RuntimeError('capture gap')):
            with self.assertRaisesRegex(RuntimeError,'capture gap'):self.s.phase('fixture')
            self.assertFalse(any('delete' in c.args for c in call.call_args_list))
            self.assertIsNotNone(self.s.active)

    def test_serial_forensics_then_delete_then_absence_before_return(self):
        events=[]
        def call(*args,**kw):events.append(args[0] if args[0]!='-n' else args[2])
        def forensic(name):events.append('forensic');return {'status':{'containerStatuses':[{'state':{'terminated':{'exitCode':0}}}]}}
        with patch.object(self.s,'admission'),patch.object(self.s,'call',side_effect=call),patch.object(self.s,'forensics',side_effect=forensic),patch.object(self.s,'obj',return_value={'items':[]}):
            self.s.phase('fixture')
        self.assertEqual(events,['create','wait','forensic','delete']);self.assertIsNone(self.s.active)

if __name__=='__main__':unittest.main()
