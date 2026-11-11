#!/usr/bin/env python3
"""Synthetic OFFLINE tests. No receipt generated here is live evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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


if __name__ == '__main__':
    unittest.main()
