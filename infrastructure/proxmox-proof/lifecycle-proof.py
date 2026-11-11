#!/usr/bin/env python3
"""Owner-leased cold-start/fault-injection harness. NEVER run without outage lease.

No network probes, guest exec, host reboot, other-VM operations or filter changes
beyond the reviewed start wrapper. Output is a sanitized lifecycle receipt.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import time

import host_lifecycle as h


def counters():
    results = {}
    for tool in ('iptables', 'ip6tables'):
        output = h.run(tool, '-w', '-nvxL', 'OUTPUT')
        jumps = [line.split() for line in output.splitlines()
                 if 'TALOS_PROOF_120' in line]
        h.require(len(jumps) == 1 and 'qemu.slice/120.scope' in ' '.join(jumps[0]),
                  'expected exactly one current scope jump')
        results[tool] = int(jumps[0][0])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['checkpoint', 'cold-start', 'kill-guard', 'hang-guard'])
    args = parser.parse_args()
    h.private_dir()
    h.require(os.environ.get('APPROVE_PROOF_LIFECYCLE_TEST') == h.UUID,
              'explicit parent outage lease required')
    if args.action == 'checkpoint':
        # Run before the coordinator-authorized stop to compare recreated scope inode.
        h.approved_config()
        receipt = h.capture()
        h.save_private('proof-before.json', receipt)
        print(json.dumps({'action': 'checkpoint', **receipt}))
        return
    if args.action == 'cold-start':
        before = h.load_private('proof-before.json')
        h.run('systemctl', 'start', 'talos-proof-start.service', timeout=210)
        after = h.load_private('incarnation.json')
        h.require(h.same_process(after), 'new incarnation absent')
        h.require(after['cgroup_inode'] != before['cgroup_inode'], 'scope not recreated')
        h.require((after['pid'], after['start_ticks']) != (before['pid'], before['start_ticks']),
                  'QEMU process not recreated')
        h.require(h.run('systemctl', 'show', h.UNIT, '-p', 'ActiveState', '--value').strip() == 'active',
                  'guard not active')
        first = counters()
        # Observe ordinary node traffic only. No production/network experiment.
        time.sleep(10)
        second = counters()
        print(json.dumps({'action': 'cold-start', 'old_scope_inode': before['cgroup_inode'],
                          'new_scope_inode': after['cgroup_inode'], 'pid': after['pid'],
                          'jump_packets_before': first, 'jump_packets_after': second,
                          'resource': h.sample(),
                          'counter_rebind_demonstrated': second['iptables'] > first['iptables']}))
        h.require(second['iptables'] > first['iptables'],
                  'no observed traffic: rebind remains unproved; use separate read-only API GET')
        return
    receipt = h.load_private('incarnation.json')
    h.require(h.same_process(receipt), 'proof incarnation absent before injection')
    sig = signal.SIGKILL if args.action == 'kill-guard' else signal.SIGSTOP
    h.run('systemctl', 'kill', '--kill-whom=main', '--signal=' + sig.name, h.UNIT)
    deadline = time.monotonic() + 45
    while h.same_process(receipt, scope=False) and time.monotonic() < deadline:
        time.sleep(1)
    stopped = not h.same_process(receipt, scope=False)
    print(json.dumps({'action': args.action, 'original_proof_process_exited': stopped,
                      'guard_result': h.run('systemctl', 'show', h.UNIT, '-p', 'Result', '--value').strip(),
                      'resource': h.sample()}))
    h.require(stopped, 'guard injection did not stop original proof QEMU within deadline')


if __name__ == '__main__':
    main()
