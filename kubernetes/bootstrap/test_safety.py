#!/usr/bin/env python3
"""Offline fail-closed tests; never calls a cluster or mutates host mounts."""
import copy, json, os, subprocess, sys, tempfile, unittest
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
        with patch.dict(os.environ,{'KUBECONFIG':'wrong','PROOF_CONTEXT':'wrong','PROOF_API_SERVER':'https://production.invalid:6443'}, clear=True):
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
class OverrideCLITests(unittest.TestCase):
    """Real guard/installer processes, only synthetic mock executables on PATH."""
    def setUp(self):
        TargetTests.setUp(self)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / 'calls.jsonl'
        self.config['clusters'][0]['cluster']['certificate-authority-data'] = 'synthetic'
        self.nodes['items'][0]['status']['nodeInfo'] = {'kubeletVersion': 'v1.36.5'}
        self.env = {
            'PATH': str(self.root) + os.pathsep + os.defpath,
            'KUBECONFIG': str(self.root / 'synthetic-config'),
            'PROOF_CONTEXT': 'synthetic-proof', 'PROOF_API_SERVER': guard.TARGET['server'],
            'PROOF_DISK_MOUNT_CONFIRMED': 'yes', 'PROOF_ARTIFACT_CACHE': str(self.root),
        }
        (self.root / 'config.json').write_text(json.dumps(self.config))
        (self.root / 'nodes.json').write_text(json.dumps(self.nodes))
        self.script('kubectl', f"""
import json, sys
from pathlib import Path
root = Path({str(self.root)!r})
a = sys.argv[1:]
with (root / 'calls.jsonl').open('a') as f:
    f.write(json.dumps(['kubectl'] + a) + '\\n')
if 'config' in a and 'view' in a:
    if any(x.startswith('jsonpath=') for x in a):
        print({guard.TARGET['server']!r})
    else:
        print((root / 'config.json').read_text())
elif 'get' in a and 'nodes' in a:
    print((root / 'nodes.json').read_text())
""")
        self.script('helm', f"""
import json, sys
from pathlib import Path
with Path({str(self.log)!r}).open('a') as f:
    f.write(json.dumps(['helm'] + sys.argv[1:]) + '\\n')
""")
        # Installer runs the real guard but never downloads artifacts.
        self.script('python3', f"""
import os, sys
if sys.argv[1].endswith('/fetch.py'):
    sys.exit(0)
os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])
""")
    def script(self, name, body):
        path = self.root / name
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o700)
    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
    def run_guard(self, args, env=None):
        return subprocess.run([sys.executable, str(Path(guard.__file__)), *args],
                              env=env or self.env, capture_output=True, text=True)
    def test_override_forms_never_execute_cli(self):
        forms = [
            ['-s', 'https://other.invalid'], ['-shttps://other.invalid'],
            ['-s=https://other.invalid'], ['-itshttps://other.invalid'],
            ['-itAs', 'https://other.invalid'], ['-its=https://other.invalid'],
            ['--context', 'other'], ['--context=other'], ['--context'],
        ]
        for flag in guard.FORBIDDEN_FLAGS:
            forms += [[flag, 'synthetic-secret'], [flag + '=synthetic-secret'],
                      ['--' + flag[2:].replace('-', '_') + '=synthetic-secret']]
        for form in forms:
            for args in ([*form, 'apply', '-f', 'synthetic.yaml'],
                         ['apply', '-f', 'synthetic.yaml', *form]):
                with self.subTest(args=args):
                    result = self.run_guard(args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('synthetic-secret', result.stderr)
                    self.assertEqual(self.calls(), [])
    def test_container_arguments_after_separator_allowed(self):
        args = ['-nproof-test', 'exec', '-it', 'pod', '--', 'curl', '-s',
                '--server=https://container.invalid', '--token=synthetic']
        result = self.run_guard(args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[-1][-len(args):], args)
        self.assertEqual(len(self.calls()), 3)
    def test_environment_overrides_prevent_all_installer_mutations(self):
        names = sorted(guard.ENV_OVERRIDES) + [
            'HELM_KUBEAPISERVER', 'HELM_KUBEINSECURE_SKIP_TLS_VERIFY',
            'HELM_KUBECAFILE', 'HELM_KUBETLS_SERVER_NAME', 'HELM_KUBETOKEN',
            'HELM_KUBEASUSER', 'HELM_KUBEASGROUPS', 'HELM_KUBECONTEXT',
            'HELM_KUBETLS_SERVERNAME', 'HELM_KUBECONFIG',
            'HELM_KUBEFUTURE_OVERRIDE', 'KUBECTL_KUBERC',
        ]
        for name in names:
            for value in ('synthetic-secret', ''):
                with self.subTest(name=name, value=value):
                    result = subprocess.run(['bash', str(Path(guard.__file__).with_name('install.sh'))],
                        env={**self.env, name: value}, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('synthetic-secret', result.stderr)
                    self.assertEqual(self.calls(), [])
    def test_installer_pins_actual_helm_transport(self):
        result = subprocess.run(['bash', str(Path(guard.__file__).with_name('install.sh'))],
            env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        helm = next(call for call in self.calls() if call[0] == 'helm')
        for flag, value in [('--kubeconfig', self.env['KUBECONFIG']),
                            ('--kube-context', self.env['PROOF_CONTEXT']),
                            ('--kube-apiserver', guard.TARGET['server'])]:
            self.assertEqual(helm[helm.index(flag) + 1], value)
        self.assertIn('--kube-insecure-skip-tls-verify=false', helm)
    def test_config_transport_overrides_block_mutator(self):
        for field in ('proxy-url', 'tls-server-name', 'server', 'insecure-skip-tls-verify'):
            with self.subTest(field=field):
                config = copy.deepcopy(self.config)
                config['clusters'][0]['cluster'][field] = True if field == 'insecure-skip-tls-verify' else 'synthetic-other'
                (self.root / 'config.json').write_text(json.dumps(config))
                self.log.unlink(missing_ok=True)
                result = self.run_guard(['apply', '-f', 'synthetic.yaml'])
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any('apply' in call or call[0] == 'helm' for call in self.calls()))

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
