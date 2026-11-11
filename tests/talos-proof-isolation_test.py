#!/usr/bin/env python3
"""Synthetic OFFLINE tests. No receipt generated here is live evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock, MagicMock
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'infrastructure/proxmox-proof/verify-isolation.py'
SPEC = importlib.util.spec_from_file_location('isolation', HELPER)
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def policy(family=4, delta=0):
    lines = ['*filter', ':OUTPUT ACCEPT [0:0]', ':' + v.CHAIN + ' - [0:0]',
             f'[{delta}:{60 * delta}] -A OUTPUT -m cgroup --path ' + v.SCOPE + ' -j ' + v.CHAIN]
    rule = 5 if family == 4 else 2  # loopback REJECT / IPv6 final REJECT
    for index, tokens in enumerate(v.expected(family), 1):
        lines.append(f'[{delta if index == rule else 0}:{60 * delta if index == rule else 0}]'
                     + ' -A ' + v.CHAIN + ' ' + ' '.join(tokens))
    return '\n'.join(lines + ['COMMIT'])


def trial(family=4, protocol='TCP', origin='node-tool'):
    address = '127.0.0.1' if family == 4 else '::1'
    f = dict(src=address, dst=address, sport=41000, dport=18081, protocol=protocol)
    rule = 5 if family == 4 else 2
    t = dict(flow=f, origin=origin, token='a' * 32,
             listener=dict(address=address, port=18081, protocol=protocol, owned=True, scoped_receives=0),
             attempt=dict(begin_ms=1000, end_ms=2000, result='denied'),
             policy_before=policy(family), policy_after=policy(family, 1), reject_rule=rule)
    for name, at, port in [('positive_before', 900, 41001), ('positive_after', 2100, 41002)]:
        t[name] = dict(flow={**f, 'sport': port}, outside_scope=True, token=t['token'],
                       listener_received=True, response_received=True, at_ms=at)
    t['trace'] = [dict(at_ms=1100, line=f'TRACE: filter:{chain}:rule:{r} '
                      f'IN= OUT=lo SRC={address} DST={address} PROTO={protocol} SPT=41000 DPT=18081')
                  for chain, r in [('OUTPUT', 1), (v.CHAIN, rule)]]
    return t


def receipt():
    return dict(schema=1, kind='controlled-host-isolation', live_collection_approved=True,
                cleanup_confirmed=True, trials=[trial()])


class ReceiptTests(unittest.TestCase):
    def test_independent_reviewed_policy_shape(self):
        self.assertEqual(v.expected(4), [
            ['-m', 'conntrack', '--ctstate', 'RELATED,ESTABLISHED', '-j', 'ACCEPT'],
            *[['-d', net, '-j', 'REJECT', '--reject-with', 'icmp-port-unreachable']
              for net in ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
                          '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16',
                          '224.0.0.0/4', '240.0.0.0/4')],
            ['-p', 'tcp', '-m', 'multiport', '--dports', '80,443,4460', '-j', 'ACCEPT'],
            ['-p', 'udp', '-m', 'multiport', '--dports', '53,123', '-j', 'ACCEPT'],
            ['-p', 'tcp', '-m', 'tcp', '--dport', '53', '-j', 'ACCEPT'],
            ['-j', 'REJECT', '--reject-with', 'icmp-port-unreachable']])
        t = trial()
        t['policy_before'] = t['policy_before'].replace('RELATED,ESTABLISHED', 'ESTABLISHED,RELATED')
        v.verify_trial(t)

    def test_positive_consistency_not_live_proof(self):
        result = v.verify(receipt())
        self.assertEqual(result['status'], 'receipt-consistent-not-authenticated')
        self.assertEqual(result['claims'][0]['verdict'], 'REJECT')
        self.assertEqual(len(result['remaining_gaps']), 3)

    def test_ipv6_udp_only_child_claim(self):
        for family in (4, 6):
            for protocol in ('TCP', 'UDP'):
                t = trial(family, protocol, 'owned-cgroup-child')
                if protocol == 'UDP':
                    # A port53 case, no DNS query is ever emitted by these tests.
                    for item in (t['flow'], t['positive_before']['flow'], t['positive_after']['flow']):
                        item['dport'] = 53
                    t['listener']['port'] = 53
                    for event in t['trace']:
                        event['line'] = event['line'].replace('DPT=18081', 'DPT=53')
                self.assertEqual(v.verify_trial(t)['claim'], 'owned-child cgroup-filter rejection only')
        with self.assertRaises(ValueError):
            v.verify_trial(trial(6, origin='node-tool'))

    def test_missing_or_weaker_evidence_rejected(self):
        mutations = [
            lambda t: t.update(trace=[]),
            lambda t: t.update(policy_after=t['policy_before']),
            lambda t: t.update(policy_after=t['policy_after'].replace(
                '[1:60] -A OUTPUT', '[0:0] -A OUTPUT')),
            lambda t: t.update(reject_rule=1),
            lambda t: t['attempt'].update(result='timeout-only'),
            lambda t: t['attempt'].update(end_ms=10000),
            lambda t: t['positive_before'].update(response_received=False),
            lambda t: t['positive_after'].update(listener_received=False),
            lambda t: t['positive_before'].update(outside_scope=False),
            lambda t: t['positive_before'].update(token='b' * 32),
            lambda t: t['positive_after'].update(at_ms=1900),
            lambda t: t['positive_before']['flow'].update(dport=22),
            lambda t: t['positive_before']['flow'].update(sport=41000),
            lambda t: t['listener'].update(scoped_receives=1),
            lambda t: t['listener'].update(owned=False),
            lambda t: t['trace'][0].update(at_ms=500),
            lambda t: t['trace'][1].update(line=t['trace'][1]['line'].replace('SPT=41000', 'SPT=41001')),
            lambda t: t['trace'][0].update(line=t['trace'][0]['line'].replace('OUTPUT:rule:1', 'OUTPUT:rule:2')),
        ]
        for change in mutations:
            t = trial(); change(t)
            with self.subTest(change=mutations.index(change)), self.assertRaises(ValueError):
                v.verify_trial(t)

    def test_policy_drift_and_manufactured_deny_rejected(self):
        mutations = [
            lambda s: s.replace('-j REJECT', '-j DROP'),
            lambda s: s.replace('--path qemu.slice/120.scope', '--path qemu.slice/102.scope'),
            lambda s: s.replace('--dports 80,443,4460', '--dports 80,443,4460,8080'),
            lambda s: s.replace(':OUTPUT ACCEPT', ':OUTPUT DROP'),
            lambda s: s.replace('COMMIT', '[0:0] -A TALOS_PROOF_120 -j DROP\nCOMMIT'),
            lambda s: s.replace('COMMIT', '[0:0] -A OUTPUT -j TALOS_PROOF_120\nCOMMIT'),
        ]
        for change in mutations:
            t = trial(); t['policy_after'] = change(t['policy_after'])
            with self.subTest(change=mutations.index(change)), self.assertRaises(ValueError):
                v.verify_trial(t)

    def test_counter_reset_and_safe_destination(self):
        t = trial(); t['policy_before'] = policy(4, 2)
        with self.assertRaises(ValueError): v.verify_trial(t)
        t = trial(); t['flow']['dst'] = '8.8.8.8'
        with self.assertRaises(ValueError): v.verify_trial(t)

    def test_top_level_gates(self):
        for key in ('live_collection_approved', 'cleanup_confirmed'):
            r = receipt(); r[key] = False
            with self.assertRaises(ValueError): v.verify(r)
        for trials in ([], [trial()] * 7):
            r = receipt(); r['trials'] = trials
            with self.assertRaises(ValueError): v.verify(r)

    def test_no_network_or_subprocess_in_verification(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), \
             patch('subprocess.run', side_effect=AssertionError('command forbidden')):
            v.verify(receipt())

    def test_cli_errors_do_not_echo_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text('{DO-NOT-ECHO-PRIVATE-CONTENT')
            result = subprocess.run([sys.executable, '-B', str(HELPER), str(path)],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn('DO-NOT-ECHO', result.stdout + result.stderr)
            path.write_text(json.dumps(receipt()))
            result = subprocess.run([sys.executable, '-B', str(HELPER), str(path)],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)


COLLECT_SPEC = importlib.util.spec_from_file_location('collector', ROOT / 'infrastructure/proxmox-proof/collect-isolation.py')
c = importlib.util.module_from_spec(COLLECT_SPEC)
COLLECT_SPEC.loader.exec_module(c)


def collector_args():
    return SimpleNamespace(address='127.0.0.1', protocol='TCP', port=18081,
                           source_port=41000, run_id='b' * 32)


def instrumented(args, packets=0):
    tokens = c.rule(args)[1:]
    tokens = [args.address + '/32' if t == args.address else t for t in tokens]
    lines = policy().splitlines()
    offset = next(i for i, line in enumerate(lines) if '-d 127.0.0.0/8' in line)
    lines.insert(offset, f'[{packets}:{packets * 60}] -A {v.CHAIN} ' + ' '.join(tokens))
    return '\n'.join(lines)


class CollectorTests(unittest.TestCase):
    def test_targetless_exact_counter_and_adjacency(self):
        a = collector_args()
        self.assertNotIn('-j', c.rule(a))
        clean, packets = c.remove_counter(instrumented(a, 1), a)
        self.assertEqual(packets, 1)
        self.assertEqual(v.snapshot(clean, 4)[0], v.snapshot(policy(), 4)[0])
        for text in (instrumented(a).replace('--dport 18081', '--dport 18082'),
                     instrumented(a).replace('--comment', '-j DROP --comment'),
                     instrumented(a).replace('-s 127.0.0.1/32', '-s 10.0.0.1/32')):
            with self.assertRaises(RuntimeError): c.remove_counter(text, a)
        text = instrumented(a).splitlines()
        index = next(i for i, line in enumerate(text) if 'proof-isolation-' in line)
        text[index], text[index + 1] = text[index + 1], text[index]
        with self.assertRaises(RuntimeError): c.remove_counter('\n'.join(text), a)

    def test_cleanup_exact_only_and_absence_check(self):
        a = collector_args()
        with patch.object(c.subprocess, 'run', side_effect=[Mock(returncode=0), Mock(returncode=1)]) as run, \
             patch.object(c, 'command') as command:
            c.cleanup(a)
            argv = command.call_args.args[0]
            self.assertIn('-D', argv)
            self.assertNotIn('-F', argv)
            self.assertEqual(argv[-len(c.rule(a)):], c.rule(a))
            self.assertEqual(run.call_count, 2)
        with patch.object(c.subprocess, 'run', return_value=Mock(returncode=1)), \
             patch.object(c, 'command') as command:
            c.cleanup(a)
            command.assert_not_called()
        with patch.object(c.subprocess, 'run', return_value=Mock(returncode=2)):
            with self.assertRaises(RuntimeError): c.cleanup(a)

    def test_child_execution_removed_pending_budget_proof(self):
        import inspect
        source = inspect.getsource(c)
        self.assertNotIn('subprocess.Popen', source)
        self.assertNotIn('cgroup.procs', source)
        self.assertNotIn('RLIMIT_AS', source)
        with self.assertRaises(RuntimeError):
            c.collect(SimpleNamespace(mode='child', protocol='TCP', address='127.0.0.1'))

    def test_cleanup_does_not_resolve_disappeared_scope(self):
        a = collector_args()
        def absent_scope(*_args, **_kwargs):
            raise FileNotFoundError('VM scope removed by guard')
        with patch.object(Path, 'stat', side_effect=absent_scope), \
             patch.object(c.subprocess, 'run', side_effect=[Mock(returncode=0), Mock(returncode=1)]) as run, \
             patch.object(c, 'command') as command:
            c.cleanup(a)
            for call in run.call_args_list:
                self.assertNotIn('--path', call.args[0])
                self.assertNotIn('cgroup', call.args[0])
            self.assertNotIn('--path', command.call_args.args[0])
            self.assertIn('-D', command.call_args.args[0])

    def test_private_diagnostics_and_public_fixed_reason(self):
        import contextlib
        import io
        args = collector_args(); args.cleanup = False
        with tempfile.TemporaryDirectory() as directory, patch.object(c, 'DIAGNOSTIC_STATE', Path(directory)):
            c.private_diagnostic(args, 'counter_after', RuntimeError('no predicate instrumentation counter delta'))
            path = next(Path(directory).glob('*.diagnostic.json'))
            record = json.loads(path.read_text())
            self.assertEqual(record['phase'], 'counter_after')
            self.assertEqual(record['reason'], 'isolation_counter_after_failed')
            self.assertIn('no predicate', record['detail'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            c.private_diagnostic(args, 'node_window', subprocess.TimeoutExpired(['PRIVATE-TOKEN'], 2))
            self.assertNotIn('PRIVATE-TOKEN', path.read_text())
        def fail(_args):
            c.PHASE = 'counter_after'
            raise RuntimeError('PRIVATE diagnostic detail')
        stream = io.StringIO()
        with patch.object(c, 'arguments', return_value=args), patch.object(c, 'mark', return_value=True), \
             patch.object(c, 'collect', side_effect=fail), patch.object(c, 'private_diagnostic') as diagnostic, \
             contextlib.redirect_stderr(stream):
            self.assertEqual(c.main(), 1)
            self.assertEqual(diagnostic.call_args.args[1], 'counter_after')
        self.assertIn('isolation_counter_after_failed', stream.getvalue())
        self.assertNotIn('PRIVATE diagnostic', stream.getvalue())

    def test_diagnostic_failure_cannot_prevent_stoppost_cleanup(self):
        args = collector_args(); args.cleanup = True
        with patch.object(c, 'arguments', return_value=args), \
             patch.object(c, 'private_diagnostic', side_effect=OSError('disk full')), \
             patch.object(c, 'cleanup') as cleanup:
            self.assertEqual(c.main(), 0)
            cleanup.assert_called_once_with(args)

    def test_resource_and_swap_abort(self):
        h = Mock(); h.same_process.return_value = True
        base = dict(available_mib=2000, swap_used_kib=28, swap_io_pages=10,
                    monotonic=1, psi_totals=dict(some=0, full=0))
        with patch.object(c, 'command', return_value='active'):
            for updates in ({'available_mib': 1791}, {'swap_used_kib': 29},
                            {'swap_io_pages': 11}, {'psi_totals': dict(some=0, full=10000)}):
                h.sample.return_value = {**base, 'monotonic': 2, **updates}
                with self.assertRaises(RuntimeError): c.host_checks(h, {}, base, base)


WRAPPER_SPEC = importlib.util.spec_from_file_location('node_wrapper', ROOT / 'infrastructure/proxmox-proof/run-node-isolation.py')
n = importlib.util.module_from_spec(WRAPPER_SPEC)
WRAPPER_SPEC.loader.exec_module(n)


def cluster_data():
    return [dict(items=[dict(metadata=dict(uid=n.NODE_UID, name='talos-proof'),
                            status=dict(conditions=[dict(type='Ready', status='True')]))]),
            dict(items=[dict(metadata=dict(namespace='kube-system', name='cilium-test', uid='cilium-uid',
                                           labels={'k8s-app': 'cilium'}),
                             spec=dict(hostNetwork=True, nodeName='talos-proof'),
                             status=dict(phase='Running', containerStatuses=[dict(name='cilium-agent', ready=True)]))]),
            dict(items=[])]


class NodeIntegrationTests(unittest.TestCase):
    def test_actual_node_predicate_narrows_endpoint_without_inventing_sport(self):
        args = collector_args(); args.mode = 'node'; args.address = '10.77.1.100'
        self.assertNotIn('--sport', c.rule(args))
        self.assertNotIn('--path', c.rule(args))
        self.assertNotIn('cgroup', c.rule(args))
        alternate = policy().replace('COMMIT', '[0:0] -A OUTPUT -j TALOS_PROOF_120\nCOMMIT')
        with self.assertRaises(ValueError): v.snapshot(alternate, 4)
        self.assertNotIn('-j', c.rule(args))
        self.assertEqual(c.reject_index(args), 3)
        spec = c.rule(args)[1:]
        spec = [args.address + '/32' if x == args.address else x for x in spec]
        text = policy().replace('[0:0] -A TALOS_PROOF_120 -d 10.0.0.0/8',
                               '[1:60] -A TALOS_PROOF_120 ' + ' '.join(spec) + '\n'
                               '[0:0] -A TALOS_PROOF_120 -d 10.0.0.0/8')
        self.assertEqual(c.remove_counter(text, args)[1], 1)

    def test_idle_cluster_and_cilium_identity(self):
        data = cluster_data()
        with patch.object(n, 'run', side_effect=[Mock(stdout=json.dumps(x)) for x in data]):
            self.assertEqual(n.validate_cluster(Path('/not-read')), ('cilium-test', 'cilium-uid'))
        for mutation in ('wrong-node', 'not-hostnetwork', 'app-pod', 'replicas', 'cronjob'):
            data = cluster_data()
            if mutation == 'wrong-node': data[0]['items'][0]['metadata']['uid'] = 'wrong'
            if mutation == 'not-hostnetwork': data[1]['items'][0]['spec']['hostNetwork'] = False
            if mutation == 'app-pod': data[1]['items'].append(dict(metadata=dict(namespace='proof-nextcloud'), status=dict(phase='Pending')))
            if mutation == 'replicas': data[2]['items'].append(dict(kind='Deployment', metadata=dict(namespace='proof-media'), spec=dict(replicas=1)))
            if mutation == 'cronjob': data[2]['items'].append(dict(kind='CronJob', metadata=dict(namespace='proof-media'), spec={}))
            with self.subTest(mutation=mutation), \
                 patch.object(n, 'run', side_effect=[Mock(stdout=json.dumps(x)) for x in data]), \
                 self.assertRaises(RuntimeError):
                n.validate_cluster(Path('/not-read'))

    def test_wrapper_exactly_one_attempt_and_safe_output(self):
        import contextlib
        import io
        stream = io.StringIO()
        with patch.object(n, 'validate_cluster', return_value=('cilium-test', 'uid')), \
             patch.object(n, 'ssh', side_effect=[Mock(stdout=''),
                          Mock(stdout='ActiveState=inactive\nResult=success\nExecMainStatus=0\n'),
                          Mock(stdout='a' * 64 + ' private-path')]), \
             patch.object(n, 'phase', side_effect=['armed', 'armed', 'complete']), \
             patch.object(n, 'marker') as marker, \
             patch.object(n, 'run_node', return_value=Mock(returncode=2)) as run, \
             patch.object(n.time, 'sleep'), contextlib.redirect_stdout(stream):
            n.execute(Path('/not-read'))
            run.assert_called_once()
            self.assertEqual([call.args[1] for call in marker.call_args_list], ['producer', 'claim', 'done'])
            self.assertEqual(marker.call_args_list[1].args[1:], ('claim', 'one'))
            self.assertEqual(marker.call_args_list[2].args[1:], ('done', 'denied'))
        self.assertNotIn('private-path', stream.getvalue())
        self.assertNotIn('SYNTHETIC', stream.getvalue())
        self.assertEqual(n.PERL.count('IO::Socket::INET->new'), 1)
        self.assertNotIn('while', n.PERL)

    def test_perl_alarm_precedes_only_constructor_and_is_not_denial(self):
        command = n.node_command(Path('/not-read'), 'pod', 25001, 'token')
        self.assertNotIn('exec timeout', ' '.join(command))
        self.assertIn('ulimit -v 12288 && ulimit -t 1 && ulimit -n 16 && exec perl', ' '.join(command))
        self.assertLess(n.PERL.index('alarm 3'), n.PERL.index('IO::Socket::INET->new'))
        self.assertEqual(n.PERL.count('IO::Socket::INET->new'), 1)
        self.assertIn('exit 124', n.PERL_DEADLINE)
        import contextlib
        import io
        with patch.object(n, 'validate_cluster', return_value=('pod', 'uid')), \
             patch.object(n, 'ssh'), patch.object(n, 'phase', return_value='armed'), \
             patch.object(n, 'marker') as marker, patch.object(n, 'run_node', return_value=Mock(returncode=124)), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError): n.execute(Path('/not-read'))
            self.assertEqual(marker.call_args.args[1:], ('done', 'failed'))

    def test_node_private_exit_stderr_retained_before_failure_classification(self):
        for code in (2, 124, 127):
            with tempfile.TemporaryDirectory() as directory, \
                 patch.object(n.subprocess, 'run', return_value=Mock(returncode=code, stderr='fixed diagnostic', stdout='PRIVATE STDOUT')):
                result = n.run_node(['PRIVATE-ARGV'], Path(directory))
                self.assertEqual(result.returncode, code)
                path = next(Path(directory).glob('node-isolation-command-*.json'))
                record = json.loads(path.read_text())
                self.assertEqual(record['returncode'], code)
                self.assertEqual(record['stderr'], 'fixed diagnostic')
                self.assertNotIn('PRIVATE', path.read_text())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(n.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['PRIVATE'], 5, stderr=b'bounded stderr')):
            with self.assertRaises(RuntimeError): n.run_node(['PRIVATE'], Path(directory))
            record = json.loads(next(Path(directory).glob('node-isolation-command-*.json')).read_text())
            self.assertTrue(record['transport_timeout'])
            self.assertEqual(record['stderr'], 'bounded stderr')

    def test_wrapper_never_launches_when_apps_active(self):
        with patch.object(n, 'validate_cluster', side_effect=RuntimeError('busy')), \
             patch.object(n, 'ssh') as ssh:
            with self.assertRaises(RuntimeError): n.execute(Path('/not-read'))
            ssh.assert_not_called()

    def test_unit_budgets_cleanup_and_no_supervisor_lock(self):
        import inspect
        command = n.launch_command('a' * 32, 25001)
        self.assertIn('--property=MemoryMax=32M', command)
        self.assertIn('--property=RuntimeMaxSec=40', command)
        self.assertIn('--property=TimeoutStopSec=10', command)
        self.assertTrue(any('ExecStopPost=' in x and '--cleanup' in x and '--mode node' in x for x in command))
        self.assertNotIn('/isolation.lock', inspect.getsource(c.collect))
        self.assertIn('controlled-host-isolation.lock', inspect.getsource(c.collect))
        self.assertIn('ulimit -v 12288', ' '.join(n.node_command(Path('/not-read'), 'pod', 25001, 'token')))

    def test_host_waits_for_claim_and_done_and_fails_closed_on_mac_loss(self):
        args = collector_args()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'claim').write_text('one'); (work / 'done').write_text('denied')
            (work / 'producer').write_text(json.dumps(dict(node_uid=n.NODE_UID, all_proof_app_pods_zero=True, host_network=True)))
            with patch.object(c.select, 'select', return_value=([], [], [])), \
                 patch.object(c, 'host_checks', return_value={'safe': True}):
                result, _ = c.await_node(args, object(), work, Mock(), {}, {}, {})
                self.assertEqual(result['node_connect_calls'], 1)
                self.assertEqual(result['slirp_source_port'], 'unknown')
            with patch.object(c.time, 'monotonic', side_effect=[0, 0, 21]):
                with self.assertRaises(RuntimeError): c.await_node(args, object(), work, Mock(), {}, {}, {})
            with patch.object(c.select, 'select', return_value=([object()], [], [])):
                with self.assertRaises(RuntimeError): c.await_node(args, object(), work, Mock(), {}, {}, {})

    def test_unit_rejects_wrong_deadlines_or_stoppost_predicate(self):
        args = collector_args(); args.mode = 'node'; args.address = '10.77.1.100'
        args.control_before = 20001; args.control_after = 20002
        import shlex
        stop = ['/usr/bin/python3', '-B', str(ROOT / 'infrastructure/proxmox-proof/collect-isolation.py'),
                '--cleanup', '--approve', c.APPROVAL, '--mode', 'node', '--address', args.address,
                '--protocol', 'TCP', '--port', str(args.port),
                '--control-before', '20001', '--control-after', '20002', '--run-id', args.run_id]
        props = ('Transient=yes\nActiveState=active\nMemoryMax=33554432\nRuntimeMaxUSec=40s\n'
                 'TimeoutStopUSec=10s\nCPUQuotaPerSecUSec=100ms\nTasksMax=8\nLimitNOFILE=32\n'
                 'KillMode=control-group\nExecStopPost={ argv[]=' + shlex.join(stop) + ' ; }')
        c.validate_unit(props, args)
        for wrong in (props.replace('40s', '50s'), props.replace('33554432', '67108864'),
                      props.replace('--port 18081', '--port 180810'),
                      props.replace('--mode node', '--mode child')):
            with self.assertRaises(RuntimeError): c.validate_unit(wrong, args)

    def test_node_controls_use_one_inprocess_socket_and_known_source(self):
        args = collector_args()
        client, connection, listener = MagicMock(), MagicMock(), Mock()
        client.__enter__.return_value = client
        connection.__enter__.return_value = connection
        client.recv.return_value = connection.recv.return_value = args.run_id.encode()
        listener.accept.return_value = (connection, (args.address, args.source_port))
        with patch.object(c.socket, 'socket', return_value=client) as socket, \
             patch.object(c.select, 'select', side_effect=[([listener], [], []), ([], [], [])]), \
             patch.object(c.subprocess, 'Popen', side_effect=AssertionError('no Python worker')):
            result = c.local_control(args, listener)
            self.assertEqual(result['acceptances'], 1)
            socket.assert_called_once()
            client.bind.assert_called_once_with((args.address, args.source_port))
        client.connect.side_effect = OSError('occupied or unreachable')
        with patch.object(c.socket, 'socket', return_value=client) as socket:
            with self.assertRaises(OSError): c.local_control(args, listener)
            socket.assert_called_once()  # never fallback/retry

    def test_mac_private_error_diagnostic_does_not_store_command_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            n.private_failure(subprocess.TimeoutExpired(['PRIVATE-TOKEN'], 2), Path(directory))
            path = Path(directory) / 'node-isolation-last-error.json'
            self.assertNotIn('PRIVATE-TOKEN', path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn('reason', json.loads(path.read_text()))

    def test_persistent_endpoint_reservation_refuses_reuse(self):
        args = collector_args(); args.control_before = 20001; args.control_after = 20002
        with tempfile.TemporaryDirectory() as directory:
            c.reserve_endpoint(args, Path(directory))
            with self.assertRaises(FileExistsError): c.reserve_endpoint(args, Path(directory))


if __name__ == '__main__':
    unittest.main()
