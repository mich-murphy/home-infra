#!/usr/bin/env python3
"""Offline only: no kubectl, Talos, SSH, image, PHP or other native execution."""
import importlib.util
import hashlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

cron = load('cron', 'scripts/talos-proof-nextcloud-cron.py')
life = load('life', 'scripts/talos-proof-data.py')

class NativeCron(unittest.TestCase):
    def setUp(self):
        # Any accidental subprocess, including discovery/version commands, fails.
        self.no_commands = patch.object(subprocess, 'run', side_effect=AssertionError('offline test attempted command'))
        self.no_commands.start()
        self.addCleanup(self.no_commands.stop)

    def test_run_unconditionally_blocked_before_external_work(self):
        with patch.object(sys, 'argv', ['cron', 'run']), self.assertRaisesRegex(RuntimeError, 'live integration blocked'):
            cron.main()

    def test_lifecycle_old_acceptance_cannot_activate_or_generate_credentials(self):
        for action in ('apply', 'activate', 'deactivate', 'run', 'test'):
            with self.subTest(action=action), patch.object(sys, 'argv', ['data', action, '--group', 'nextcloud', '--stage', 'cron', '--state', '/nonexistent']), patch.object(life, 'credentials', side_effect=AssertionError('credential mutation')), patch.object(life, 'kube', side_effect=AssertionError('API access')), self.assertRaisesRegex(RuntimeError, 'BLOCKED'):
                life.main()

    def test_daily_interval_strict_and_no_reservation_or_future_check(self):
        now = 200000
        row = dict(id=1, **{'class':cron.CLASS}, last_run=now-86401, reserved_at=0, last_checked=now)
        self.assertTrue(cron.due(row, now))
        for changes in [dict(last_run=now-86400), dict(last_run=now), dict(last_run=-1),
                        dict(reserved_at=1), dict(last_checked=now+1), dict(last_checked=-1),
                        dict(id=0), dict(last_run='0'), {'class':'fake'}]:
            with self.subTest(changes=changes):
                self.assertFalse(cron.due({**row, **changes}, now))

    def test_every_job_pod_blocks_even_unlabelled_completed_or_terminating(self):
        for phase in ('Pending', 'Running', 'Succeeded', 'Failed'):
            for namespace in ('proof-nextcloud', 'proof-validation', 'proof-couchdb'):
                pod = dict(metadata=dict(namespace=namespace, name='old', deletionTimestamp='now',
                    ownerReferences=[dict(kind='Job')]), status=dict(phase=phase))
                with self.subTest(phase=phase, namespace=namespace), self.assertRaises(RuntimeError):
                    cron.barrier([pod])
        cron.barrier([dict(metadata=dict(namespace='proof-nextcloud', labels={'app.kubernetes.io/name':n})) for n in ('postgres','redis')])
        for app in ('nextcloud','collabora','wopi-fixture',None):
            with self.assertRaises(RuntimeError):
                cron.barrier([dict(metadata=dict(namespace='proof-nextcloud', labels={'app.kubernetes.io/name':app}))])

    def test_bundle_limits_identity_and_no_admission(self):
        bundle = cron.compile_bundle()
        self.assertEqual(bundle['status'], 'OFFLINE_COMPILED_NOT_ADMITTED')
        self.assertEqual(bundle['budget_mib']['total'], 832)
        self.assertEqual(sum(v for k,v in bundle['budget_mib'].items() if k != 'total'),832)
        self.assertEqual(len(bundle['jobs']), 6)
        for job in bundle['jobs']:
            self.assertEqual(job['metadata']['namespace'],'proof-nextcloud')
            self.assertEqual(job['spec']['backoffLimit'], 0)
            self.assertEqual(job['spec']['activeDeadlineSeconds'],180)
            pod = job['spec']['template']['spec']
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertEqual(pod['securityContext']['runAsUser'],33)
            self.assertNotIn('initContainers',pod)
            self.assertEqual(len(pod['containers']),1)
            container = pod['containers'][0]
            self.assertEqual(container['image'],cron.IMAGE)
            self.assertEqual(container['resources']['limits']['memory'],'192Mi')
            self.assertNotIn('apache', ' '.join(container['command']).lower())
        self.assertTrue(bundle['jobs'][0]['spec']['template']['spec']['containers'][0]['volumeMounts'][0]['readOnly'])
        self.assertGreaterEqual(len(cron.payload_sources()),20)

    def test_artifacts_exclusive_private_uuid_and_no_stdout_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp).resolve() / (str(uuid.uuid4()) + '.json')
            with patch.object(sys,'argv',['cron','compile','--output',str(target)]), patch('sys.stdout',new_callable=io.StringIO) as stdout:
                cron.main()
                self.assertNotIn('native.php', stdout.getvalue())
                self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
                with self.assertRaises(FileExistsError): cron.main()
            alias = Path(temp).resolve() / (str(uuid.uuid4()) + '.json')
            alias.symlink_to(target)
            with patch.object(sys,'argv',['cron','compile','--output',str(alias)]), self.assertRaisesRegex(RuntimeError,'symlink'):
                cron.main()

    def test_native_contract_synthetic_age_no_global_ttl_or_job_spoof(self):
        php = (ROOT / 'scripts/talos-proof-nextcloud-cron.php').read_text()
        self.assertNotIn('MUTATION_INTEGRATION_READY',php)
        self.assertIn("'proof', 'proof', null, $token['name']",php)
        self.assertIn("time() - (int)$job['last_run'] > 86400",php)
        self.assertIn("['memory.current', 'memory.peak', 'memory.events', 'memory.stat']",php)
        self.assertIn("exclusive($journal . '/before.json', $state)",php)
        self.assertIn('$entity->setLastActivity(',php)
        self.assertIn('$mapper->update($entity)',php)
        self.assertNotIn("setSystemValue('session_lifetime'",php)
        self.assertNotIn('invalidateOldTokens(',php)
        self.assertNotIn('->insert(',php)
        self.assertNotIn('setLastRun',php)
        self.assertIn('maintenance:install',php)
        self.assertIn('out-of-scope token eligible',php)
        self.assertIn("case 'before'",php)

    def test_cron_wrapper_precheck_is_sequential_and_parent_never_bootstraps_core(self):
        php=(ROOT/'scripts/talos-proof-nextcloud-cron.php').read_text()
        body=php.split("case 'cron':",1)[1].split("case 'assert-restore':",1)[0]
        precheck="nativeCommand(['php',__FILE__,'cron-precheck',$run],$journal.'/cron-precheck.log');"
        native="nativeCommand(['php','-f','/var/www/html/cron.php','--',CLEANUP_CLASS],$journal.'/cron.log');"
        self.assertLess(body.index(precheck),body.index(native))
        self.assertLess(body.index(native),body.index("'native_cron_exit_zero'=>true"))
        self.assertEqual(body.count('nativeCommand('),2)
        for forbidden in ('nativeContext(', 'cleanupRow(', 'due(', 'require', 'include', 'proc_open(', 'try', 'catch'):
            self.assertNotIn(forbidden,body)
        child=php.split("case 'cron-precheck':",1)[1].split("case 'cron':",1)[0]
        self.assertIn("need(getenv('PROOF_PHASE') === 'cron', 'internal cron precheck only')",child)
        self.assertIn('nativeContext(); due(cleanupRow());',child)

    def test_internal_precheck_failure_cannot_reach_second_native_command(self):
        php=(ROOT/'scripts/talos-proof-nextcloud-cron.php').read_text()
        command=php.split('function nativeCommand(',1)[1].split('function installOrVerify(',1)[0]
        self.assertIn("fopen($log,'x')",command)
        self.assertIn('chmod($log,0600)',command)
        self.assertIn('$started = is_resource($p); $exit = $started ? proc_close($p) : null;',command)
        self.assertIn("need($started && $exit===0, 'native process failed; preserve partial state', $context)",command)
        self.assertLess(command.index('fflush($f) && fsync($f)'),command.index('need($started && $exit===0'))
        self.assertIn("'private_child_log'=>substr($log,0,256),'exit_code'=>$exit",command)
        self.assertIn('fflush($f) && fsync($f)',command)
        self.assertNotIn('catch',command)
        # Synchronous proc_close + throwing need + no parent catch between the
        # two statements means a failed precheck cannot launch native cron.
        need=php.split('function need(',1)[1].split('function exclusive(',1)[0]
        self.assertIn('throw new GateFailure($gate, $context)',need)
        self.assertIn("'status'=>'BLOCKED_OR_FAILED'",php)
        self.assertIn('exit(1)',php)

    def test_internal_precheck_has_no_public_job_phase_or_receipt_admission(self):
        self.assertEqual(cron.PHASES,('preflight','install-or-verify','fixture','before','cron','assert-restore'))
        with self.assertRaises(ValueError):cron.job('cron-precheck',str(uuid.uuid4()))
        bundle=cron.compile_bundle()
        phases=[job['spec']['template']['spec']['containers'][0]['env'][0]['value'] for job in bundle['jobs']]
        self.assertEqual(phases,list(cron.PHASES))
        self.assertNotIn('cron-precheck',phases)

    def test_packaged_version_bridge_exact_artifact_only_original_indexes_unchanged(self):
        bridge=cron.packaged_metadata()
        self.assertEqual(bridge['image'],cron.IMAGE)
        self.assertEqual(bridge['manifest_digest'],'sha256:3139d734aa878e9da89b610112734056c0df55279dd6a4578573c0803c293ef3')
        self.assertEqual(bridge['platform'],{'os':'linux','architecture':'amd64'})
        original=json.loads((ROOT/'docs/evidence/talos-data/nextcloud-cron-source-review-97384394-9c9c-47d4-8d17-50e63b9b62fd.json').read_text())
        before={s['path']:s['sha256'] for s in original['sources'] if not s['path'].startswith('docker/')}
        after=cron.payload_sources()
        self.assertEqual({name for name in before if before[name]!=after[name]},{'version.php'})
        self.assertEqual(before['version.php'],bridge['overrides']['version.php']['git_sha256'])
        self.assertEqual(after['version.php'],bridge['overrides']['version.php']['packaged_sha256'])
        payload=cron.compile_bundle()['payload']['data']
        self.assertEqual(payload['packaged-metadata.json'],cron.PACKAGED_METADATA.read_text())
        self.assertEqual(json.loads(payload['core-hashes.json']),after)

    def test_packaged_bridge_extra_override_image_index_or_evidence_drift_rejects(self):
        bridge=cron.packaged_metadata()
        with patch.object(cron,'IMAGE','different-image'):
            with self.assertRaises(RuntimeError):cron.packaged_metadata()
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'bridge.json'
            for fault in ('hash','extra','index','image','public-evidence'):
                bad=copy.deepcopy(bridge)
                if fault=='extra':bad['overrides']['lib/base.php']=copy.deepcopy(bad['overrides']['version.php'])
                elif fault=='index':bad['evidence_sha256']['docs/evidence/talos-data/nextcloud-cron-source-review-97384394-9c9c-47d4-8d17-50e63b9b62fd.json']='0'*64
                elif fault=='image':bad['image']='different-image'
                elif fault=='public-evidence':bad['evidence_sha256']['docs/evidence/talos-data/nextcloud-public-image-parity-412faf37-f124-44b2-b52a-418ad71f9cd0.json']='0'*64
                target.write_text(json.dumps(bad))
                approved=cron.PACKAGED_METADATA_SHA256 if fault=='hash' else hashlib.sha256(target.read_bytes()).hexdigest()
                with self.subTest(fault=fault),patch.object(cron,'PACKAGED_METADATA',target),patch.object(cron,'PACKAGED_METADATA_SHA256',approved):
                    with self.assertRaises(RuntimeError):cron.packaged_metadata()

    def test_php_private_failure_context_bounded_redacted_no_trace_or_environment_dump(self):
        php=(ROOT/'scripts/talos-proof-nextcloud-cron.php').read_text()
        detail=php.split('function privateError(',1)[1].split('function hashCheck(',1)[0]
        self.assertIn('substr($message,0,1024)',detail)
        self.assertIn("substr(basename($error->getFile()),0,128)",detail)
        self.assertIn("str_replace($secret, '[redacted]'",detail)
        self.assertIn('[opaque-redacted]',detail)
        self.assertIn("['POSTGRES_PASSWORD','NEXTCLOUD_ADMIN_PASSWORD','REDIS_HOST_PASSWORD']",detail)
        for forbidden in ('getTrace','getTraceAsString','$_ENV','getenv()'):
            self.assertNotIn(forbidden,detail)
        for field in ('source_relative','expected_sha256','actual_sha256','private_child_log','exit_code'):
            self.assertIn(field,php)
        self.assertIn("'private_error'=>privateError($e)",php)
        self.assertIn('hashCheck($root,$relative,$hash',php)
        self.assertIn("hashCheck('/usr/src/nextcloud',$path,$hash",php)
        self.assertIn("hashCheck('/var/www/html',$path,$hash",php)

    def test_diagnostic_php_requires_empty_html_before_db_cache_no_retained_bootstrap(self):
        php=(ROOT/'scripts/talos-proof-nextcloud-cron.php').read_text()
        body=php.split('function preflight(bool $emptyOnly = false)',1)[1].split('function nativeCommand(',1)[0]
        gate="if ($emptyOnly) { need($volume['empty'], 'diagnostic requires empty HTML; no retained core bootstrap'); }"
        self.assertLess(body.index(gate),body.index('new PDO'))
        self.assertLess(body.index(gate),body.index('new Redis'))
        self.assertIn('SET default_transaction_read_only = on',body)
        for forbidden in ('->set(', '->flush', 'maintenance:install', 'fixture(', 'cron.php'):
            self.assertNotIn(forbidden,body)
        dispatch=php.split("case 'diagnose-preflight':",1)[1].split("case 'install-or-verify':",1)[0]
        self.assertIn('$result=preflight(true)',dispatch)
        self.assertNotIn('nativeContext()',dispatch)
        with self.assertRaises(ValueError):cron.job('diagnose-preflight',str(uuid.uuid4()))

    def test_completed_current_previous_logs_and_raw_laststate_saved_before_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            os.chmod(temp,0o700)
            pod = dict(metadata=dict(uid='test',name='cli-test'),status=dict(phase='Failed',containerStatuses=[
                dict(name='cli',restartCount=1,state=dict(terminated=dict(exitCode=1)),
                     lastState=dict(terminated=dict(exitCode=137,reason='OOMKilled')))]))
            def run(args, **kwargs):
                data = json.dumps(dict(items=[pod])).encode() if 'get' in args else b'private synthetic log'
                return subprocess.CompletedProcess(args,0,stdout=data,stderr=b'')
            with patch.object(life,'LEASE_GROUP','nextcloud'), patch.object(life,'STATE_DIR',Path(temp).resolve()), patch.object(life,'lease',return_value={}), patch.object(subprocess,'run',side_effect=run) as commands:
                life.capture_forensics('proof-nextcloud','before deletion')
            self.assertEqual(len(commands.call_args_list),3)
            files = list(Path(temp).iterdir())
            self.assertEqual(len(files),4)
            self.assertTrue(any(p.name.startswith('current-log-') for p in files))
            self.assertTrue(any(p.name.startswith('previous-log-') for p in files))
            raw = next(p for p in files if p.name.startswith('pod-status-'))
            self.assertEqual(json.loads(raw.read_text())['items'][0]['status']['containerStatuses'][0]['lastState']['terminated']['exitCode'],137)
            for path in files: self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

if __name__ == '__main__': unittest.main()
