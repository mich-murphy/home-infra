#!/usr/bin/env python3
"""Offline fail-closed tests; never calls a cluster or mutates host mounts."""
import copy, json, subprocess, tempfile, unittest
from pathlib import Path
import yaml
import proof_guard as guard
class TargetTests(unittest.TestCase):
    def setUp(self):
        self.config={'clusters':[{'cluster':{'server':guard.TARGET['server'],'certificate-authority-data':'synthetic'}}]}
        self.nodes={'items':[{'metadata':{'name':guard.TARGET['nodeName'],'uid':guard.TARGET['nodeUID']},'status':{'addresses':[{'type':'InternalIP','address':guard.TARGET['nodeIP']}]}}]}
    def test_valid(self): guard.validate_config(self.config);guard.validate_nodes(self.nodes)
    def test_consistently_wrong_config_and_server(self):
        # A caller changing both config and expected server must not authorize production.
        import os
        from unittest.mock import patch
        self.config['clusters'][0]['cluster']['server']='https://production.invalid:6443'
        with self.assertRaises(ValueError): guard.validate_config(self.config)
        with patch.dict(os.environ,{'KUBECONFIG':'wrong','PROOF_CONTEXT':'wrong','PROOF_API_SERVER':'https://production.invalid:6443'}):
            with self.assertRaises(ValueError):guard.check()
    def test_no_tls_skip(self):
        self.config['clusters'][0]['cluster']['insecure-skip-tls-verify']=True
        with self.assertRaises(ValueError):guard.validate_config(self.config)
    def test_node_identity(self):
        for part in ['name','uid']:
            n=copy.deepcopy(self.nodes);n['items'][0]['metadata'][part]='wrong'
            with self.assertRaises(ValueError):guard.validate_nodes(n)
        self.nodes['items'][0]['status']['addresses'][0]['address']='192.168.1.2'
        with self.assertRaises(ValueError):guard.validate_nodes(self.nodes)
    def test_multiple_nodes(self):
        self.nodes['items']*=2
        with self.assertRaises(ValueError):guard.validate_nodes(self.nodes)
class MountTests(unittest.TestCase):
    def test_mount_gate(self):
        docs=yaml.safe_load_all(Path(__file__).parents[1].joinpath('platform/storage/storage.yaml').read_text())
        setup=next(d['data']['setup'] for d in docs if d['kind']=='ConfigMap')
        # Isolate only the actual pre-mkdir guard; no mkdir or host paths are touched.
        guard_script=setup.split('case "$VOL_DIR"')[0]
        cases=[('',False),('1 2 8:4 / /var/mnt/proof rw - xfs /dev/sda4 rw\n',False),('1 2 8:17 /some-dir /var/mnt/proof rw - xfs /dev/sdb1 rw\n',False),('1 2 8:17 / /var/mnt/proof rw - xfs /dev/sdb1 rw\n',True)]
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'mountinfo'
            for text,expected in cases:
                p.write_text(text)
                r=subprocess.run(['sh','-c',guard_script.replace('/proc/self/mountinfo',str(p))],capture_output=True)
                self.assertEqual(r.returncode==0,expected)
if __name__=='__main__':unittest.main()
