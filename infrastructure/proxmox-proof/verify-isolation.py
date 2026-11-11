#!/usr/bin/env python3
"""Offline receipt consistency checker. Never opens sockets or invokes host tools.

Receipts are operator-supplied observations, NOT authenticated proof. See
 docs/talos-proof-host-isolation.md for collection requirements and limitations.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import shlex
import sys

CHAIN = 'TALOS_PROOF_120'
SCOPE = 'qemu.slice/120.scope'
PRIVATE = ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
           '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16',
           '224.0.0.0/4', '240.0.0.0/4')
GAPS = ['Actual guest IPv6 transport (disabled in slirp).',
        'Slirp DNS proxy forwarding and public/alternate resolver bypass.',
        'Production readiness, root-operator bypass and exhaustive isolation.']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, minimum=0, maximum=2**63 - 1):
    require(type(value) is int and minimum <= value <= maximum, 'invalid integer')
    return value


def expected(family):
    rules = [['-m', 'conntrack', '--ctstate', 'RELATED,ESTABLISHED', '-j', 'ACCEPT']]
    if family == 4:
        rules += [['-d', cidr, '-j', 'REJECT', '--reject-with', 'icmp-port-unreachable']
                  for cidr in PRIVATE]
        rules += [['-p', 'tcp', '-m', 'multiport', '--dports', '80,443,4460', '-j', 'ACCEPT'],
                  ['-p', 'udp', '-m', 'multiport', '--dports', '53,123', '-j', 'ACCEPT'],
                  ['-p', 'tcp', '-m', 'tcp', '--dport', '53', '-j', 'ACCEPT']]
    rules += [['-j', 'REJECT', '--reject-with',
               'icmp-port-unreachable' if family == 4 else 'icmp6-port-unreachable']]
    return rules


def snapshot(text, family):
    """Parse a sanitized iptables-save -c *filter section; fail closed on drift.

    Accept only the reviewed chain, not a permissive semantic approximation.
    Unrelated rules are retained in the structural before/after comparison.
    """
    require(family in (4, 6), 'invalid family')
    require(type(text) is str and len(text) < 262144, 'invalid policy text')
    rules, counters, structure = {}, {}, []
    in_filter = False
    completed = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line == '*filter':
            require(not in_filter and not completed, 'duplicate filter table')
            in_filter = True
            continue
        if line == 'COMMIT':
            require(in_filter, 'unexpected COMMIT')
            in_filter, completed = False, True
            continue
        require(in_filter, 'supply only the filter table')
        if line.startswith(':'):
            structure.append(re.sub(r'\[\d+:\d+\]$', '[COUNTERS]', line))
            continue
        match = re.fullmatch(r'\[(\d+):(\d+)\] -A (\S+) (.+)', line)
        require(match is not None, 'expected counted iptables-save rule')
        packets, byte_count, chain, tail = match.groups()
        tokens = shlex.split(tail)
        # iptables versions may print either ordering of these identical states.
        tokens = ['RELATED,ESTABLISHED' if x == 'ESTABLISHED,RELATED' else x for x in tokens]
        rules.setdefault(chain, []).append(tokens)
        counters.setdefault(chain, []).append((int(packets), int(byte_count)))
        structure.append((chain, tokens))
    require(completed, 'incomplete filter snapshot')
    require(rules.get(CHAIN) == expected(family), 'proof chain differs from reviewed policy')
    jump = ['-m', 'cgroup', '--path', SCOPE, '-j', CHAIN]
    output = rules.get('OUTPUT', [])
    require(output and output[0] == jump, 'scope jump must be first OUTPUT rule')
    require(sum(CHAIN in rule for entries in rules.values() for rule in entries) == 1,
            'duplicate or alternate proof-chain entry')
    return structure, counters


def flow(value):
    require(set(value) == {'src', 'dst', 'sport', 'dport', 'protocol'}, 'invalid flow keys')
    src, dst = ipaddress.ip_address(value['src']), ipaddress.ip_address(value['dst'])
    require(src.version == dst.version, 'mixed address families')
    require(value['protocol'] in ('TCP', 'UDP'), 'invalid protocol')
    integer(value['sport'], 1024, 65535)
    integer(value['dport'], 1, 65535)
    return src, dst


def trace_matches(line, wanted, chain, rule):
    """Legacy iptables TRACE only; nft trace needs a separately reviewed adapter."""
    require(type(line) is str and len(line) < 4096, 'invalid trace line')
    if not re.search(r'\bTRACE: filter:' + re.escape(chain) + r':rule:' + str(rule) + r'\s', line):
        return False
    pairs = dict(re.findall(r'\b(SRC|DST|PROTO|SPT|DPT)=([^\s]+)', line))
    try:
        return (ipaddress.ip_address(pairs['SRC']) == ipaddress.ip_address(wanted['src']) and
                ipaddress.ip_address(pairs['DST']) == ipaddress.ip_address(wanted['dst']) and
                pairs['PROTO'] == wanted['protocol'] and
                int(pairs['SPT']) == wanted['sport'] and int(pairs['DPT']) == wanted['dport'])
    except (KeyError, ValueError):
        return False


def verify_trial(trial):
    src, dst = flow(trial['flow'])
    family = dst.version
    require(trial['origin'] in ('node-tool', 'owned-cgroup-child'), 'unsupported origin')
    require(trial['origin'] != 'node-tool' or
            (family == 4 and trial['flow']['protocol'] == 'TCP'), 'unsupported guest transport claim')
    # Explicit RFC1918/loopback only, not ipaddress.is_private's documentation ranges.
    safe = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8') if family == 4 else ('::1/128',)
    require(any(dst in ipaddress.ip_network(net) for net in safe), 'not a bounded synthetic destination')
    require(trial['listener']['address'] == str(dst) and
            trial['listener']['port'] == trial['flow']['dport'] and
            trial['listener']['protocol'] == trial['flow']['protocol'] and
            trial['listener']['owned'] is True, 'listener mismatch')
    require(trial['listener']['scoped_receives'] == 0, 'scoped request reached listener')
    require(re.fullmatch(r'[a-f0-9]{32}', trial['token']) is not None, 'invalid synthetic token')
    begin, end = trial['attempt']['begin_ms'], trial['attempt']['end_ms']
    integer(begin); integer(end)
    require(0 < end - begin <= 5000 and trial['attempt']['result'] == 'denied', 'unbounded or successful attempt')
    ports = {trial['flow']['sport']}
    for control, earlier in ((trial['positive_before'], True), (trial['positive_after'], False)):
        require(control['outside_scope'] is True and control['token'] == trial['token'] and
                control['listener_received'] is True and control['response_received'] is True,
                'missing same-endpoint positive control')
        # Controls differ only in source port and scope, not endpoint/protocol.
        flow(control['flow'])
        require(all(control['flow'][key] == trial['flow'][key]
                    for key in ('src', 'dst', 'dport', 'protocol')), 'control endpoint/source mismatch')
        require(control['flow']['sport'] not in ports, 'flow port reused')
        ports.add(control['flow']['sport'])
        at = integer(control['at_ms'])
        require(0 < (begin - at if earlier else at - end) <= 10000, 'control not bracketing attempt')
    before, counts_before = snapshot(trial['policy_before'], family)
    after, counts_after = snapshot(trial['policy_after'], family)
    require(before == after, 'filter structure changed during trial')
    rule = integer(trial['reject_rule'], 1, len(expected(family)))
    wanted_rule = expected(family)[rule - 1]
    require('REJECT' in wanted_rule, 'attributed rule is not an existing REJECT')
    if '-d' in wanted_rule:
        require(dst in ipaddress.ip_network(wanted_rule[1]), 'wrong destination rule')
    else:
        require(family == 6, 'IPv4 private flow must hit private-destination rule')
    for chain, old in counts_before.items():
        require(all(a >= b and c >= d for (a, c), (b, d) in zip(counts_after[chain], old)),
                'counters reset or decreased')
    require(counts_after['OUTPUT'][0][0] > counts_before['OUTPUT'][0][0], 'no scoped jump counter delta')
    require(counts_after[CHAIN][rule - 1][0] > counts_before[CHAIN][rule - 1][0], 'no reject counter delta')
    events = trial['trace']
    require(type(events) is list and len(events) <= 100, 'unbounded trace')
    jump_times, reject_times = [], []
    for event in events:
        at = integer(event['at_ms'])
        require(begin <= at <= end, 'trace outside attempt window')
        if trace_matches(event['line'], trial['flow'], 'OUTPUT', 1):
            jump_times.append(at)
        if trace_matches(event['line'], trial['flow'], CHAIN, rule):
            reject_times.append(at)
    require(any(j <= r for j in jump_times for r in reject_times), 'missing exact-flow scope/reject trace')
    return {'origin': trial['origin'], 'family': family, 'protocol': trial['flow']['protocol'],
            'claim': 'node-origin private TCP rejection' if trial['origin'] == 'node-tool'
                     else 'owned-child cgroup-filter rejection only', 'verdict': 'REJECT'}


def verify(receipt):
    require(receipt['schema'] == 1 and receipt['kind'] == 'controlled-host-isolation', 'unsupported receipt')
    require(receipt['live_collection_approved'] is True, 'no collection approval recorded')
    require(receipt['cleanup_confirmed'] is True, 'cleanup not confirmed')
    require(type(receipt['trials']) is list and 1 <= len(receipt['trials']) <= 6, 'invalid trial count')
    return {'status': 'receipt-consistent-not-authenticated',
            'claims': [verify_trial(t) for t in receipt['trials']], 'remaining_gaps': GAPS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path, help='sanitized JSON receipt (read locally only)')
    args = parser.parse_args()
    try:
        require(args.receipt.stat().st_size <= 2_000_000, 'receipt too large')
        result = verify(json.loads(args.receipt.read_text()))
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        # Do not echo untrusted receipt contents (which might contain private data).
        print(json.dumps({'status': 'rejected', 'error_type': type(exc).__name__}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
