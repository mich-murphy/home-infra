#!/usr/bin/env python3
"""Synthetic OFFLINE tests. No receipt generated here is live evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
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
        for text in (instrumented(a).replace('--sport 41000', '--sport 41001'),
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

    def test_worker_failure_pidfd_cleanup(self):
        worker = Mock()
        worker.poll.return_value = None
        with patch.object(c.subprocess, 'Popen', return_value=worker), \
             patch.object(c.os, 'pidfd_open', return_value=9, create=True), \
             patch.object(c.signal, 'pidfd_send_signal', create=True) as send, \
             patch.object(c.os, 'close') as close:
            owned = c.OwnedChild(['offline-worker'])
            owned.stop()
            send.assert_called_once_with(9, c.signal.SIGKILL)
            worker.wait.assert_called_once_with(timeout=2)
            close.assert_called_once_with(9)

    def test_exited_worker_never_signalled(self):
        worker = Mock(); worker.poll.return_value = 1
        with patch.object(c.subprocess, 'Popen', return_value=worker), \
             patch.object(c.os, 'pidfd_open', return_value=9, create=True), \
             patch.object(c.signal, 'pidfd_send_signal', create=True) as send, \
             patch.object(c.os, 'close'):
            c.OwnedChild(['offline-worker']).stop()
            send.assert_not_called()

    def test_pidfd_failure_kills_only_unreleased_popen_child(self):
        worker = Mock()
        with patch.object(c.subprocess, 'Popen', return_value=worker), \
             patch.object(c.os, 'pidfd_open', side_effect=OSError(), create=True):
            with self.assertRaises(OSError): c.OwnedChild(['offline-worker'])
            worker.kill.assert_called_once()
            worker.wait.assert_called_once_with(timeout=2)
            worker.stdin.write.assert_not_called()

    def test_supervisor_death_child_kernel_contract(self):
        # Offline ordering check: PDEATHSIG and wall alarm precede GO, cgroup
        # movement and socket creation. Integration kill test requires Linux.
        import inspect
        source = inspect.getsource(c.arm_child)
        child_source = inspect.getsource(c.child)
        self.assertIn('libc.prctl(1, signal.SIGKILL', source)
        self.assertIn('signal.alarm(4)', source)
        self.assertIn('os.getppid() == parent', source)
        self.assertLess(child_source.index('arm_child()'), child_source.index('sys.stdin.buffer.read'))
        self.assertLess(child_source.index('cgroup.procs'), child_source.index('with socket.socket'))

    @unittest.skipUnless(sys.platform == 'linux', 'Linux kernel PDEATHSIG integration')
    def test_supervisor_crash_reaps_escaped_child_without_network(self):
        # Child inherits stdout: communicate cannot finish until PDEATHSIG closes
        # that descriptor. No sockets, cgroups, host access or signals to guests.
        script = r"""
import importlib.util, os, signal, sys
spec = importlib.util.spec_from_file_location('c', sys.argv[1])
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
r,w = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(r); c.arm_child(); os.write(w,b'A'); os.close(w)
    signal.pause()
else:
    os.close(w); assert os.read(r,1) == b'A'; os.close(r)
    os._exit(7)
"""
        result = subprocess.run([sys.executable, '-B', '-c', script,
                                 str(ROOT / 'infrastructure/proxmox-proof/collect-isolation.py')],
                                capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 7)

    def test_resource_and_swap_abort(self):
        h = Mock(); h.same_process.return_value = True
        base = dict(available_mib=2000, swap_used_kib=28, swap_io_pages=10,
                    monotonic=1, psi_totals=dict(some=0, full=0))
        with patch.object(c, 'command', return_value='active'):
            for updates in ({'available_mib': 1791}, {'swap_used_kib': 29},
                            {'swap_io_pages': 11}, {'psi_totals': dict(some=0, full=10000)}):
                h.sample.return_value = {**base, 'monotonic': 2, **updates}
                with self.assertRaises(RuntimeError): c.host_checks(h, {}, base, base)


if __name__ == '__main__':
    unittest.main()
