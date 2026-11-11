#!/usr/bin/env python3
"""Offline admission/preservation contracts, never proof-runtime calls."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
s = importlib.import_module('talos-proof-media-safety')
p = importlib.import_module('talos-proof-media-pinchflat-provider')
r = importlib.import_module('talos-proof-media-resources')


def base():
    return next(x for x in yaml.safe_load_all((ROOT/'kubernetes/apps/media/pinchflat/resources.yaml').read_text()) if x['kind']=='Deployment')


def profile():
    d=base(); t=d['spec']['template']
    t['metadata']['annotations']={'talos-proof.home/provider-fixture':'pinchflat-rss','talos-proof.home/pinchflat-main-memory-mib':'384'}
    t['spec']['containers'][0]['resources']['limits']['memory']='384Mi'
    fixture=yaml.safe_load((ROOT/'kubernetes/apps/media/pinchflat-rss/provider.yaml').read_text())['spec']['template']['spec']['containers'][1]
    t['spec']['containers'].append(fixture)
    return d


class Budget(unittest.TestCase):
    def setUp(self):
        self.receipt={'provider_fixture':'pinchflat-rss','pinchflat_main_memory_mib':384,'available_mib':704,'measured_at':s.time.time()}
        self.controllers=[profile()]
        self.pods=[]
        self.node={'status':{'allocatable':{'memory':'2400000Ki'}}}
    def read(self,*args):
        if args[:2]==('get','deployment'):return json.dumps(self.controllers[0])
        return json.dumps({'items':self.pods if args[1]=='pods' else self.controllers})
    def guard(self,**kw):
        with patch.object(s,'lease',return_value=(self.receipt,self.node)),patch.object(s,'exclusivity'),patch.object(s,'kubectl_read',side_effect=self.read):
            return s.guard('pinchflat',**kw)
    def test_plain_activation_charges_persistent_profile_full_704(self):
        self.guard()
        self.receipt['available_mib']=703
        with self.assertRaisesRegex(RuntimeError,'insufficient'):self.guard()
        self.receipt['available_mib']=576
        with self.assertRaises(RuntimeError):self.guard()
        self.receipt['available_mib']=704
        for value in (None,256,'384',True):
            self.receipt['pinchflat_main_memory_mib']=value
            with self.assertRaises(RuntimeError):self.guard()
    def test_base_remains_256_and_profile_drift_fails(self):
        self.assertEqual(r.pinchflat_budget(base()['spec']['template'],{}),256)
        t=profile()['spec']['template']
        changes=[lambda x:x['metadata']['annotations'].pop('talos-proof.home/provider-fixture'),
                 lambda x:x['metadata']['annotations'].pop('talos-proof.home/pinchflat-main-memory-mib'),
                 lambda x:x['spec']['containers'][0]['resources']['limits'].update(memory='256Mi'),
                 lambda x:x['spec']['containers'][1]['resources']['limits'].update(memory='129Mi'),
                 lambda x:x['spec']['containers'][0]['resources']['requests'].update(memory='127Mi'),
                 lambda x:x['spec'].update(overhead={'memory':'1Mi'}),
                 lambda x:x['spec'].update(initContainers=[dict(name='init',resources={'limits':{'cpu':'1','memory':'1Gi'}})]),
                 lambda x:x['spec'].update(initContainers=[dict(name='side',restartPolicy='Always',resources={'limits':{'cpu':'1','memory':'1Mi'}})])]
        for change in changes:
            v=copy.deepcopy(t);change(v)
            with self.assertRaises(RuntimeError):r.pinchflat_budget(v,self.receipt)
    def test_bad_marker_or_limit_never_reaches_mutating_subprocess(self):
        for change in ('marker','limit'):
            d=profile()
            if change=='marker':d['spec']['template']['metadata']['annotations'].clear()
            else:d['spec']['template']['spec']['containers'][0]['resources']['limits']['memory']='385Mi'
            self.controllers=[d]
            with patch.object(s,'lease',return_value=(self.receipt,self.node)),patch.object(s,'exclusivity'),patch.object(s,'kubectl_read',side_effect=self.read),patch.object(s.subprocess,'run') as run:
                with self.assertRaises(RuntimeError):s.kube('pinchflat','scale','deployment','pinchflat','--replicas=1',capacity=True)
                run.assert_not_called()
    def test_prepare_preserves_every_nonprofile_field_and_atomic_spec_test(self):
        d=base()
        for v in d['spec']['template']['spec']['volumes']:
            if 'persistentVolumeClaim' in v:v['persistentVolumeClaim']['claimName']='restored-'+v['name']
        original=copy.deepcopy(d)
        calls=[]
        def kube(*args,**kw):
            calls.append((args,kw))
            if args[:2]==('get','pods'):return b'{"items":[]}'
            if args[0]=='get':return json.dumps(d).encode()
            if args[0]=='patch':
                ops=json.loads(args[-1]);self.assertEqual(ops[0],{'op':'test','path':'/spec','value':original['spec']})
                d['spec']=ops[1]['value']
            return b''
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp).resolve()/p.INPUT;f.write_bytes(b'offline');f.chmod(0o600)
            with patch.object(p,'check'),patch.object(s,'require_helpers_deleted'),patch.object(s,'guard') as guard,patch.object(s,'lease',return_value=(self.receipt,self.node)),patch.object(p,'kube',side_effect=kube),patch.object(p,'INPUT_SHA',p.hashlib.sha256(b'offline').hexdigest()):
                result=p.prepare(f.parent,f)
                guard.assert_called_once()
        self.assertEqual(result['result'],'PREPARED_STOPPED_ONLY')
        old=original['spec']['template']['spec'];new=d['spec']['template']['spec']
        self.assertEqual(old['containers'][0]['env'],new['containers'][0]['env'][:len(old['containers'][0]['env'])])
        self.assertEqual(old['volumes'],[v for v in new['volumes'] if not v['name'].startswith('rss-')])
        for k in old['containers'][0]:
            if k not in ('env','resources'):self.assertEqual(old['containers'][0][k],new['containers'][0][k])
        self.assertEqual(d['spec']['replicas'],0)
        self.assertFalse(any('-k' in args for args,kw in calls))
    def test_first_known_termination_or_restart_is_not_retried(self):
        r.pinchflat_no_restart([{'status':{'containerStatuses':[{'restartCount':0,'state':{'running':{}}}]}}])
        for status in ({'restartCount':1},{'lastState':{'terminated':{'reason':'OOMKilled','exitCode':137}}},{'state':{'terminated':{'reason':'OOMKilled'}}}):
            with self.assertRaisesRegex(RuntimeError,'STOP'):
                r.pinchflat_no_restart([{'status':{'containerStatuses':[status]}}])
        batch=(ROOT/'scripts/talos-proof-media-batch.py').read_text()
        self.assertIn('pinchflat_no_restart(pods)',batch)
        self.assertIn("kube('scale','deployment','pinchflat','--replicas=0')",Path(p.__file__).read_text())

    def test_prospective_admission_rejects_live_pods_or_replicas(self):
        self.controllers=[base()]
        self.guard(provider_selected=True,preparation_template=profile()['spec']['template'])
        self.controllers[0]['spec']['replicas']=1
        with self.assertRaises(RuntimeError):self.guard(provider_selected=True,preparation_template=profile()['spec']['template'])
        self.controllers[0]['spec']['replicas']=0
        self.pods=[{'metadata':{'namespace':'proof-pinchflat'}}]
        with self.assertRaises(RuntimeError):self.guard(provider_selected=True,preparation_template=profile()['spec']['template'])


if __name__=='__main__':unittest.main()
