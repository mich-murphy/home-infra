#!/usr/bin/env python3
"""Offline child-only OOM, fail-stop control and strict previous-Pod deletion."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
w=importlib.import_module('talos-proof-media-pinchflat-watch')
p=importlib.import_module('talos-proof-media-pinchflat-provider')
s=w.s


def payload(oom=0,kill=0):
    return f'FILE memory.current\n1234\nFILE memory.peak\n5678\nFILE memory.stat\nanon 100\nFILE memory.events\nlow 0\nhigh 0\nmax 0\noom {oom}\noom_kill {kill}\noom_group_kill 0\n'


def pod():
    return {'metadata':{'namespace':'proof-pinchflat','uid':'offline-pod','name':'pinchflat-offline'},
            'spec':{'containers':[{'name':'pinchflat'},{'name':'rss-fixture'}]},
            'status':{'phase':'Running','containerStatuses':[
                {'name':name,'restartCount':0,'containerID':'offline-'+name,'state':{'running':{}}}
                for name in ('pinchflat','rss-fixture')]}}


class Watch(unittest.TestCase):
    def test_child_only_oom_or_kill_with_restart_zero_is_fatal_and_retained(self):
        for oom,kill in ((1,0),(0,1),(1,1)):
            with tempfile.TemporaryDirectory() as tmp:
                state=Path(tmp).resolve()
                with patch.object(s,'kube',return_value=payload(oom,kill).encode()) as kube:
                    with self.assertRaisesRegex(RuntimeError,'child-only OOM'):w.sample(state,[pod()],require_running=True)
                    self.assertEqual(kube.call_count,1)
                    self.assertEqual(kube.call_args.args[-3:],('/bin/sh','-c',w.o.CGROUP))
                records=list(state.glob('pinchflat-oom-check-*.json'))
                receipt=json.loads(records[0].read_text())
                self.assertEqual(receipt['pods'][0]['containers'][0]['events']['oom'],oom)
                self.assertEqual(receipt['result'],'STOP')
                self.assertEqual(records[0].stat().st_mode&0o777,0o600)
                self.assertEqual(len(list(state.glob('pinchflat-oom-stop-*.json'))),1)
                with patch.object(s,'kube') as kube:
                    with self.assertRaisesRegex(RuntimeError,'no rerun'):w.sample(state,[pod()])
                    kube.assert_not_called()
    def test_zero_counters_all_containers_are_collected_without_fixture_python(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(s,'kube',return_value=payload().encode()) as kube:
            result=w.sample(Path(tmp).resolve(),[pod()],require_running=True)
            self.assertEqual(len(result['pods'][0]['containers']),2)
            self.assertEqual(kube.call_count,2)
            for call in kube.call_args_list:
                self.assertEqual(call.args[-3:],('/bin/sh','-c',w.o.CGROUP))
                self.assertNotIn('python',call.args[-1])
    def test_unreadable_or_missing_events_fail_closed(self):
        for raw in (payload().replace('oom 0\n',''),payload().replace('oom_kill 0','oom_kill invalid'),payload().replace('1234','UNAVAILABLE'),payload()+'FILE memory.events\n'):
            with self.assertRaises(RuntimeError):w.events(raw)
    def test_remote_checks_before_after_and_does_not_retry_exec137(self):
        order=[]
        with patch.object(w,'checkpoint',side_effect=lambda:order.append('sample')),patch.object(p,'pod',return_value='offline'),patch.object(p,'kube',side_effect=lambda *a,**kw:order.append('control') or b'ok'):
            self.assertEqual(p.remote('pinchflat','fixed-command'),b'ok')
            self.assertEqual(order,['sample','control','sample'])
        with patch.object(w,'checkpoint',side_effect=RuntimeError('known OOM')),patch.object(p,'kube') as kube:
            with self.assertRaises(RuntimeError):p.remote('pinchflat','fixed-command')
            kube.assert_not_called()
        failure=RuntimeError('exec137');failure.private_stderr=b'private test error'
        with patch.object(w,'checkpoint',return_value={}) as check,patch.object(p,'pod',return_value='offline'),patch.object(p,'kube',side_effect=failure) as kube:
            with self.assertRaisesRegex(RuntimeError,'exec137') as caught:p.remote('pinchflat','fixed-command')
            self.assertIs(caught.exception,failure)
            self.assertEqual(check.call_count,2)
            self.assertEqual(kube.call_count,1)
    def test_exec137_latches_stop_even_when_followup_counters_would_be_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp).resolve();monitor=w.Monitor(state)
            failure=RuntimeError('exec137');failure.private_stderr=b'private-137'
            with patch.object(w,'ACTIVE',monitor),patch.object(w,'sample',return_value={}) as sample,patch.object(p,'pod',return_value='offline'),patch.object(p,'kube',side_effect=failure) as kube:
                with self.assertRaisesRegex(RuntimeError,'exec137'):p.remote('pinchflat','fixed-command')
                self.assertEqual(kube.call_count,1)
                self.assertEqual(sample.call_count,1)
                self.assertIs(monitor.failure,failure)
                self.assertEqual(len(list(state.glob('pinchflat-oom-stop-*.json'))),1)
                with self.assertRaisesRegex(RuntimeError,'latched STOP'):monitor.checkpoint()
                kube.assert_called_once()

    def test_periodic_monitor_stops_while_control_could_still_be_blocked(self):
        stopped=threading.Event()
        with patch.object(w,'sample',side_effect=[{},RuntimeError('child OOM')]) as sample,patch.object(w,'stop',side_effect=lambda state:stopped.set()) as stop:
            with self.assertRaises(RuntimeError):
                with w.monitoring(Path('/offline-unused')) as monitor:
                    self.assertTrue(stopped.wait(3))
                    with self.assertRaisesRegex(RuntimeError,'latched STOP'):monitor.checkpoint()
            self.assertIsNone(w.ACTIVE)
            self.assertEqual(sample.call_count,2)
            stop.assert_called_once()
    def test_finish_waits_for_exact_owned_watcher_and_never_parallel_scales(self):
        watcher=Mock();watcher.poll.return_value=None;watcher.wait.return_value=0
        with patch.object(w,'stop') as stop:
            w.finish_window(Path('/offline-unused'),watcher)
            watcher.send_signal.assert_called_once()
            watcher.wait.assert_called_once_with(timeout=210)
            stop.assert_not_called()
        watcher.wait.side_effect=TimeoutError('bounded owned watcher failure')
        with patch.object(w,'stop') as stop,self.assertRaises(TimeoutError):
            w.finish_window(Path('/offline-unused'),watcher)
        stop.assert_called_once()

    def test_intentional_shutdown_joins_outer_sampling_before_scale_zero(self):
        shutdown=threading.Event();shutdown.set()
        monitors=[];original=w.Monitor
        order=[]
        def make(*args,**kwargs):
            monitor=original(*args,**kwargs);monitors.append(monitor);return monitor
        def stopped(state):
            self.assertFalse(monitors[0].thread.is_alive())
            self.assertTrue(monitors[0].done.is_set())
            self.assertIsNone(w.ACTIVE)
            order.append('scale0')
        with patch.object(w,'Monitor',side_effect=make),patch.object(w,'sample',side_effect=lambda *a,**kw:order.append('sample') or {}),patch.object(w,'stop',side_effect=stopped):
            w.window(Path('/offline-unused'),30,shutdown)
        self.assertEqual(order,['sample','sample','scale0'])

    def test_stop_scales_zero_before_any_extra_observation_exec(self):
        order=[]
        with patch.object(s,'kube',side_effect=lambda *args,**kwargs:order.append('scale' if 'scale' in args else 'wait')),patch.object(w.o,'capture',side_effect=lambda *args:order.append('observation')):
            w.stop(Path('/offline-unused'))
        self.assertEqual(order,['scale','observation','wait'])

    def test_persistent_stop_blocks_batch_before_any_activation_mutation(self):
        batch=importlib.import_module('talos-proof-media-batch')
        secret={'kind':'Secret','metadata':{'namespace':'proof-pinchflat','name':'bootstrap'}}
        for action in ('start','activate','restart'):
            with tempfile.TemporaryDirectory() as tmp:
                state=Path(tmp).resolve()
                s.write_private(state/'pinchflat-oom-stop-offline.json','{}')
                with patch.object(sys,'argv',['batch',action,'pinchflat',str(state)]),patch.object(s,'private_dir',return_value=state),patch.object(s,'read_private',side_effect=[json.dumps({'pinchflat':{}}),json.dumps(secret)]),patch.object(s,'lease'),patch.object(s,'kube') as kube:
                    with self.assertRaisesRegex(RuntimeError,'no rerun'):batch.main()
                    kube.assert_not_called()


class Exclusivity(unittest.TestCase):
    def check(self,pods,controllers=()):
        def read(*args):return json.dumps({'items':pods if args[1]=='pods' else list(controllers)})
        with patch.object(s,'kubectl_read',side_effect=read):s.exclusivity('pinchflat')
    def test_all_other_proof_pods_must_be_deleted_without_namespace_exception(self):
        for ns in ('proof-validation','proof-gateway','proof-qbittorrent','proof-nextcloud','proof-unknown'):
            for phase in ('Pending','Running','Succeeded','Failed'):
                other={'metadata':{'namespace':ns,'deletionTimestamp':'offline','ownerReferences':[{'kind':'Job','name':'fixture'}]},'status':{'phase':phase}}
                with self.subTest(namespace=ns,phase=phase),self.assertRaisesRegex(RuntimeError,'ALL previous'):self.check([other])
        self.check([pod(),{'metadata':{'namespace':'kube-system'},'status':{'phase':'Running'}}])
    def test_foreign_positive_controllers_cannot_hide_without_pods(self):
        for ns in ('proof-validation','proof-gateway','proof-qbittorrent'):
            with self.assertRaises(RuntimeError):self.check([],[{'metadata':{'namespace':ns},'spec':{'replicas':1}}])
    def test_unselected_pipeline_terminal_pod_is_not_exempt(self):
        other={'metadata':{'namespace':'proof-media-pipeline','labels':{'app.kubernetes.io/name':'sonarr'}},'status':{'phase':'Succeeded'}}
        with patch.object(s,'PIPELINE_MEMBERS',frozenset(('qbittorrent','radarr'))),patch.object(s,'kubectl_read',return_value=json.dumps({'items':[other]})):
            with self.assertRaisesRegex(RuntimeError,'unselected application pod'):s.exclusivity('media-pipeline')


if __name__=='__main__':unittest.main()
