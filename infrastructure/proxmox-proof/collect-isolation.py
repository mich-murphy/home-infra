#!/usr/bin/env python3
"""APPROVAL-GATED host collector. No action without --approve and a bounded unit.

Actual-node TCP only; child/UDP/IPv6 execution is disabled pending budget proof. Run only through the
reviewed transient unit shown in docs. No existing service is controlled.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('verify_isolation', HERE / 'verify-isolation.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
APPROVAL = '555e8603-58e6-4fb6-a190-378a3f11c257'
DIAGNOSTIC_STATE = Path('/root/.local/state/home-infra/talos-proof')


PHASE = 'preflight'
PHASES = {'preflight', 'unit_validation', 'identity_admission', 'listener_bind',
          'positive_before', 'counter_insert', 'counter_before', 'node_window',
          'counter_after', 'positive_after', 'cleanup', 'policy_final', 'receipt_write', 'complete'}


def private_diagnostic(args, phase, error=None):
    require(phase in PHASES, 'invalid diagnostic phase')
    suffix = 'cleanup' if args.cleanup else 'collector'
    path = DIAGNOSTIC_STATE / ('isolation-' + args.run_id + '.' + suffix + '.diagnostic.json')
    value = {'phase': phase, 'status': 'error' if error else ('complete' if phase == 'complete' else 'in-progress'),
             'reason': 'isolation_' + phase + '_failed' if error else 'none',
             'monotonic': time.monotonic()}
    if error:
        value['error_type'] = type(error).__name__
        # Never preserve subprocess argv/output/configs. Our RuntimeError checks
        # have fixed diagnostic messages; other errors retain type/errno only.
        value['detail'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        if isinstance(error, OSError):
            value['errno'] = error.errno
    temp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def mark(args, phase):
    global PHASE
    PHASE = phase
    try:
        private_diagnostic(args, phase)
        return True
    except OSError:
        return False  # diagnostics must NEVER prevent exact-rule cleanup


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def command(args, timeout=2):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, 'bounded host command failed: ' + ' '.join(args[:2]) + ' exit=' + str(result.returncode))
    require(len(result.stdout) <= 262144, 'host output too large')
    return result.stdout


def rule(args):
    # Attribution is inherited from the verified SOLE scoped OUTPUT entry.
    # Never re-resolve the cgroup path here: StopPost must still delete this
    # exact rule after guard stop removes the scope. No inner cgroup match.
    return [v.CHAIN, '-s', args.address, '-d', args.address,
            '-p', args.protocol.lower(), '-m', args.protocol.lower(),
            '--dport', str(args.port), '-m', 'comment',
            '--comment', 'proof-isolation-' + args.run_id]


def reject_index(args):
    if ipaddress.ip_address(args.address).version == 6:
        return 2
    for index, entry in enumerate(v.expected(4), 1):
        if '-d' in entry and ipaddress.ip_address(args.address) in ipaddress.ip_network(entry[1]):
            return index
    raise RuntimeError('no matching private REJECT')


def remove_counter(text, args):
    """Require exact parsed test rule immediately before original REJECT."""
    import re
    import shlex
    found = []
    lines = text.splitlines()
    prefix = 32 if ipaddress.ip_address(args.address).version == 4 else 128
    expected = rule(args)[1:]
    expected = [args.address + '/' + str(prefix) if x == args.address else x for x in expected]
    chain_rules = 0
    instrument_packets = None
    for line in lines:
        match = re.fullmatch(r'\[(\d+):(\d+)\] -A (\S+) (.+)', line)
        if match and match[3] == v.CHAIN:
            chain_rules += 1
        if 'proof-isolation-' + args.run_id in line:
            require(match is not None and match[3] == v.CHAIN and
                    chain_rules == reject_index(args) and shlex.split(match[4]) == expected,
                    'instrumentation not exactly adjacent to existing REJECT')
            require(instrument_packets is None, 'duplicate instrumentation')
            instrument_packets = int(match[1])
        else:
            found.append(line)
    require(instrument_packets is not None, 'missing instrumentation snapshot')
    clean = '\n'.join(found)
    v.snapshot(clean, ipaddress.ip_address(args.address).version)
    return clean, instrument_packets


def tool(args):
    return 'iptables' if ipaddress.ip_address(args.address).version == 4 else 'ip6tables'


def cleanup(args):
    """Idempotent exact-rule deletion; safe after worker OR supervisor death.

    Called also as systemd ExecStopPost, outside the failed worker. Never flushes
    chains or removes another run's rule. A failure remains a failure, not a pass.
    """
    check = subprocess.run([tool(args), '-w', '1', '-t', 'filter', '-C', *rule(args)],
                           capture_output=True, timeout=2)
    if check.returncode == 1:
        return
    require(check.returncode == 0, 'cannot check instrumentation cleanup')
    command([tool(args), '-w', '1', '-t', 'filter', '-D', *rule(args)])
    check = subprocess.run([tool(args), '-w', '1', '-t', 'filter', '-C', *rule(args)],
                           capture_output=True, timeout=2)
    require(check.returncode == 1, 'instrumentation remains')



def local_control(args, listener):
    """Node-mode positive control: no second Python interpreter or threads.

    Collector is outside the proof cgroup. Endpoint/ports are already reserved;
    failure never causes fallback to another address, service or source port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(.5)
        client.bind((args.address, args.source_port))
        client.connect((args.address, args.port))
        require(select.select([listener], [], [], .5)[0], 'control listener not ready')
        client.sendall(args.run_id.encode())
        connection, peer = listener.accept()
        with connection:
            connection.settimeout(.5)
            require(peer[0] == args.address and peer[1] == args.source_port, 'control source mismatch')
            payload = connection.recv(128)
            require(payload == args.run_id.encode(), 'control token mismatch')
            connection.sendall(payload)
        require(client.recv(128) == args.run_id.encode(), 'control response mismatch')
        require(not select.select([listener], [], [], 0)[0], 'unexpected extra acceptance')
        return {'sport': args.source_port, 'result': 'response',
                'listener_received': True, 'acceptances': 1, 'outside_proof_cgroup': True}


def host_checks(h, incarnation, baseline, previous):
    h.approved_config()
    require(h.same_process(incarnation), 'VM incarnation changed')
    require(command(['systemctl', 'is-active', h.UNIT]).strip() == 'active', 'guard inactive')
    current = h.sample()
    require(current['available_mib'] >= 1792, 'host below approved test floor')
    require(current['swap_used_kib'] == baseline['swap_used_kib'] and
            current['swap_io_pages'] == baseline['swap_io_pages'], 'swap changed')
    elapsed = current['monotonic'] - previous['monotonic']
    require(0 < elapsed <= 15, 'sampling deadline')
    for key in ('some', 'full'):
        delta = current['psi_totals'][key] - previous['psi_totals'][key]
        require(0 <= delta < elapsed * (10000 if key == 'full' else 50000), 'PSI pressure')
    return current


def validate_ports(args):
    low, high = map(int, Path('/proc/sys/net/ipv4/ip_local_port_range').read_text().split())
    ports = (args.control_before, args.control_after)
    require(all(1024 <= p < low for p in ports) and len(set(ports)) == 2,
            'control/source ports must be distinct below ephemeral range')
    require(args.port not in ports, 'endpoint conflicts with source port')


def reserve_endpoint(args, state):
    # Persistent reservation means this collector never reuses its own listener
    # endpoint or positive-control source ports. No conntrack deletion/reuse.
    for suffix in ('endpoint-' + args.address.replace(':', '_') + '-' + str(args.port),
                   'control-' + str(args.control_before), 'control-' + str(args.control_after)):
        path = state / ('isolation-reserved-' + suffix)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(hashlib.sha256(args.run_id.encode()).hexdigest())


def await_node(args, listener, work, h, incarnation, baseline, previous):
    # No test processes or probes are launched here. Mac may make exactly one
    # claimed attempt. Loss of Mac is a deadline failure, never inferred denial.
    (work / 'phase').write_text('armed\n')
    claimed_at = None
    deadline = time.monotonic() + 20
    next_check = time.monotonic()
    while time.monotonic() < deadline:
        readable, _, _ = select.select([listener], [], [], .1)
        require(not readable, 'unexpected listener acceptance during node window')
        now = time.monotonic()
        if now >= next_check:
            previous = host_checks(h, incarnation, baseline, previous)
            next_check = now + 1
        if (work / 'claim').exists() and claimed_at is None:
            require((work / 'claim').read_text() == 'one', 'invalid node claim')
            require((work / 'producer').stat().st_size <= 4096, 'producer receipt too large')
            producer = json.loads((work / 'producer').read_text())
            require(producer['node_uid'] == '4845bfd5-3bdb-453d-8503-83b43edb7a1e' and
                    producer['all_proof_app_pods_zero'] is True and
                    producer['host_network'] is True, 'invalid Mac producer assertions')
            claimed_at = now
            deadline = min(deadline, now + 6)
        if (work / 'done').exists():
            require(claimed_at is not None and (work / 'done').read_text() == 'denied',
                    'missing claim or non-denial node result')
            require(not select.select([listener], [], [], 0)[0], 'node reached listener')
            return {'result': 'denied', 'listener_received': False, 'node_connect_calls': 1,
                    'slirp_source_port': 'unknown', 'mac_producer_assertions': producer, 'window_ms': int((now - claimed_at) * 1000)}, previous
    raise RuntimeError('Mac/node attempt deadline expired')


def validate_unit(properties, args):
    fields = dict(line.split('=', 1) for line in properties.splitlines() if '=' in line)
    expected_fields = {'Transient': 'yes', 'ActiveState': 'active', 'MemoryMax': '33554432',
                       'RuntimeMaxUSec': '40s', 'TimeoutStopUSec': '10s',
                       'CPUQuotaPerSecUSec': '100ms', 'TasksMax': '8', 'LimitNOFILE': '32',
                       'KillMode': 'control-group'}
    require(all(fields.get(key) == value for key, value in expected_fields.items()),
            'bounded cleanup unit missing')
    import re
    import shlex
    stop_line = next((line for line in properties.splitlines() if line.startswith('ExecStopPost=')), '')
    commands = re.findall(r'argv\[\]=(.*?);', stop_line)
    expected = ['/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--cleanup',
                '--approve', APPROVAL, '--mode', args.mode, '--address', args.address,
                '--protocol', args.protocol, '--port', str(args.port),
                '--control-before', str(args.control_before),
                '--control-after', str(args.control_after), '--run-id', args.run_id]
    require(len(commands) == 1 and shlex.split(commands[0]) == expected,
            'StopPost does not match exact run arguments')


def collect(args):
    require(args.mode == 'node' and args.protocol == 'TCP' and args.address == '10.77.1.100',
            'child/UDP/IPv6 execution disabled pending budget proof')
    require(os.geteuid() == 0, 'root required')
    # Must be enclosed by the separately reviewed systemd unit. This environment
    # marker alone is not authority: verify the actual transient unit properties.
    # Do NOT retain the supervisor/isolation flock: guard-stop/lifecycle cleanup
    # must never wait for a test. Concurrent changes invalidate the capture.
    # Test-only lock, unrelated to lifecycle/isolation locks; never delays guard.
    lock_fd = os.open('/root/.local/state/home-infra/talos-proof/controlled-host-isolation.lock',
                      os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    unit = 'talos-proof-isolation-' + args.run_id + '.service'
    mark(args, 'unit_validation')
    properties = command(['systemctl', 'show', unit, '--property=Transient,ActiveState,MemoryMax,RuntimeMaxUSec,TimeoutStopUSec,CPUQuotaPerSecUSec,TasksMax,LimitNOFILE,KillMode,ExecStopPost'])
    validate_unit(properties, args)
    require(unit in Path('/proc/self/cgroup').read_text(), 'collector outside bounded unit')
    mark(args, 'identity_admission')
    import host_lifecycle as h
    h.approved_config()
    incarnation = h.load_private('incarnation.json')
    require(h.same_process(incarnation), 'identity mismatch')
    baseline = h.sample()
    previous = baseline
    started = time.monotonic()
    version = command([tool(args), '--version']).strip()
    require('(legacy)' in version, 'backend differs from read-only reviewed host')
    # Preserve the inspected backend; no logger/module/backend changes.
    installed = False
    before = command([tool(args) + '-save', '-c', '-t', 'filter'])
    family = ipaddress.ip_address(args.address).version
    v.snapshot(before, family)
    work = Path('/root/.local/state/home-infra/talos-proof') / ('isolation-' + args.run_id)
    work.mkdir(mode=0o700)  # exclusive per-run; never resume/reuse a prior endpoint
    validate_ports(args)
    reserve_endpoint(args, work.parent)
    output = {'kind': 'controlled-host-isolation-capture', 'schema': 1,
              'origin': 'node-perl',
              'attribution': 'endpoint counter inheriting sole scoped OUTPUT entry; not TRACE or authenticated attestation',
              'backend': version, 'endpoint': {'address': args.address, 'port': args.port},
              'claims': [], 'policy_before': before, 'run_id': args.run_id,
              'test_start_resources': baseline,
              'historical_enrollment_baseline_note': 'original swap24KiB retained; latest parent report28KiB/IO10 reflects historical4KiB/1page growth, not reset'}
    try:
        previous = host_checks(h, incarnation, baseline, previous)
        fam = socket.AF_INET if family == 4 else socket.AF_INET6
        kind = socket.SOCK_STREAM if args.protocol == 'TCP' else socket.SOCK_DGRAM
        mark(args, 'listener_bind')
        with socket.socket(fam, kind) as listener:
            if family == 6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((args.address, args.port))  # no REUSE*, occupancy fails
            if kind == socket.SOCK_STREAM:
                listener.listen(1)
            mark(args, 'positive_before')
            args.source_port = args.control_before
            output['positive_before'] = local_control(args, listener)
            require(output['positive_before']['result'] == 'response', 'positive control failed')
            # Unit StopPost owns this exact rule even if supervisor dies here.
            mark(args, 'counter_insert')
            spec = rule(args)
            command([tool(args), '-w', '1', '-t', 'filter', '-I', spec[0],
                     str(reject_index(args)), *spec[1:]])
            installed = True
            mark(args, 'counter_before')
            during_before = command([tool(args) + '-save', '-c', '-t', 'filter'])
            normalized, count = remove_counter(during_before, args)
            require(count == 0 and v.snapshot(normalized, family)[0] == v.snapshot(before, family)[0],
                    'pre-attempt instrumentation or policy drift')
            mark(args, 'node_window')
            output['attempt'], previous = await_node(args, listener, work, h, incarnation, baseline, previous)
            mark(args, 'counter_after')
            during_after = command([tool(args) + '-save', '-c', '-t', 'filter'])
            normalized_after, count = remove_counter(during_after, args)
            require(count > 0, 'no predicate instrumentation counter delta')
            old_structure, old_counts = v.snapshot(normalized, family)
            new_structure, new_counts = v.snapshot(normalized_after, family)
            require(old_structure == new_structure, 'policy changed around attempt')
            reject = reject_index(args) - 1
            require(new_counts['OUTPUT'][0][0] > old_counts['OUTPUT'][0][0], 'no scoped OUTPUT jump delta')
            require(new_counts[v.CHAIN][reject][0] - old_counts[v.CHAIN][reject][0] >= count,
                    'existing REJECT delta smaller than adjacent predicate count')
            output['instrumented_before'] = during_before
            output['instrumented_after'] = during_after
            output['predicate_packets'] = count
            require(output['attempt']['result'] == 'denied' and
                    not output['attempt']['listener_received'], 'scoped traffic reached listener')
            mark(args, 'positive_after')
            args.source_port = args.control_after
            output['positive_after'] = local_control(args, listener)
            require(output['positive_after']['result'] == 'response', 'post-control failed')
            previous = host_checks(h, incarnation, baseline, previous)
    finally:
        if installed:
            original_phase = PHASE
            mark(args, 'cleanup')
            cleanup(args)
            mark(args, original_phase)
    mark(args, 'policy_final')
    output['policy_after'] = command([tool(args) + '-save', '-c', '-t', 'filter'])
    require(v.snapshot(before, family)[0] == v.snapshot(output['policy_after'], family)[0],
            'existing filter policy changed')
    require(time.monotonic() - started <= 35, 'collection deadline exceeded')
    output['cleanup_confirmed'] = True
    output['status'] = 'adjacent-counter-capture-pending-human-review'
    output['remaining_gaps'] = ['owned-child UDP53/IPv6 disabled pending budget proof', *v.GAPS]
    output['memory_peak_bytes'] = command(['systemctl', 'show', unit, '--property=MemoryPeak', '--value']).strip()
    mark(args, 'receipt_write')
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(output, stream)
        stream.write('\n')
    mark(args, 'complete')
    (work / 'phase').write_text('complete\n')


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--approve', required=True, choices=[APPROVAL])
    p.add_argument('--mode', choices=['node'], default='node')
    p.add_argument('--address', required=True, choices=['10.77.1.100'])
    p.add_argument('--protocol', choices=['TCP'], default='TCP')
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--control-before', type=int, default=20001)
    p.add_argument('--control-after', type=int, default=20002)
    p.add_argument('--run-id', required=True)
    p.add_argument('--output', default='/root/.local/state/home-infra/talos-proof/isolation-capture.json')
    p.add_argument('--cleanup', action='store_true')
    args = p.parse_args()
    require(len(args.run_id) == 32 and all(c in '0123456789abcdef' for c in args.run_id), 'invalid run id')
    require(20000 <= args.port <= 29999, 'node synthetic port outside reviewed range')
    require(len({args.control_before, args.control_after, args.port}) == 3, 'ports not distinct')
    require(args.port == 53 or 1024 <= args.port <= 65535, 'invalid synthetic port')
    require(not (args.protocol == 'TCP' and args.port == 53), 'TCP53 not in scope')
    return args


def main():
    args = None
    try:
        args = arguments()
        if args.cleanup:
            mark(args, 'cleanup')
            cleanup(args)
            mark(args, 'complete')
        else:
            require(mark(args, 'preflight'), 'private diagnostic unavailable before admission')
            collect(args)
        return 0
    except Exception as exc:
        recorded = False
        if args is not None:
            try:
                private_diagnostic(args, PHASE, exc)
                recorded = True
            except OSError:
                pass
        print(json.dumps({'status': 'failed-no-acceptance', 'reason': 'isolation_' + PHASE + '_failed',
                          'private_diagnostic_written': recorded}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
