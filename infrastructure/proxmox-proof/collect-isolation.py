#!/usr/bin/env python3
"""APPROVAL-GATED host collector. No action without --approve and a bounded unit.

Owned-child tests ONLY: not actual node/guest transport. Run only through the
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
import resource
import select
import signal
import socket
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('verify_isolation', HERE / 'verify-isolation.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
SCOPE = Path('/sys/fs/cgroup/qemu.slice/120.scope')
APPROVAL = '555e8603-58e6-4fb6-a190-378a3f11c257'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def command(args, timeout=2):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, 'bounded host command failed')
    require(len(result.stdout) <= 262144, 'host output too large')
    return result.stdout


def rule(args):
    # Targetless counting rule: continue immediately to the existing REJECT.
    # Source port is fresh and used by ONLY the one scoped child.
    return [v.CHAIN, '-s', args.address, '-d', args.address,
            '-p', args.protocol.lower(), '-m', 'cgroup', '--path', v.SCOPE,
            '-m', args.protocol.lower(), '--sport', str(args.source_port),
            '--dport', str(args.port), '-m', 'comment',
            '--comment', 'proof-isolation-' + args.run_id]


def reject_index(args):
    return 5 if ipaddress.ip_address(args.address).version == 4 else 2


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


class OwnedChild:
    """Pidfd pins only a Popen child. No numeric-PID or cgroup-wide signals."""
    def __init__(self, argv):
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL)
        try:
            self.fd = os.pidfd_open(self.process.pid)
        except BaseException:
            # Child has not received GO and cannot join/create sockets. Popen
            # retains its unreaped child identity until wait; fail closed.
            self.process.kill()
            self.process.wait(timeout=2)
            raise

    def stop(self):
        try:
            if self.process.poll() is None:
                try:
                    signal.pidfd_send_signal(self.fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # exited after poll; still reap our own child below
            self.process.wait(timeout=2)
        finally:
            os.close(self.fd)


def arm_child():
    """Linux death/deadline protection, also unit-testable without networking."""
    # Kernel parent-death kill plus wall alarm remain effective after this child
    # leaves the transient unit's cgroup. No dependence on the dead supervisor's
    # pidfd surviving. Check parent again after prctl to close the death race.
    import ctypes
    parent = os.getppid()
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0, 'PDEATHSIG unavailable')
    require(parent != 1 and os.getppid() == parent, 'parent disappeared')
    signal.alarm(4)


def child(args):
    """Fresh child waits for parent's pidfd acquisition before cgroup join."""
    arm_child()
    require(sys.stdin.buffer.read(1) == b'G', 'no child release')
    resource.setrlimit(resource.RLIMIT_AS, (32 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
    resource.setrlimit(resource.RLIMIT_NOFILE, (24, 24))
    if args.scoped:
        unit = 'talos-proof-isolation-' + args.run_id + '.service'
        require(unit in Path('/proc/self/cgroup').read_text(), 'child not in test unit')
        import host_lifecycle as h
        h.approved_config()
        incarnation = h.load_private('incarnation.json')
        digest = hashlib.sha256(json.dumps(incarnation, sort_keys=True).encode()).hexdigest()
        require(digest == args.incarnation_hash and h.same_process(incarnation), 'child identity changed')
        # Pin the approved directory inode; a recreated scope cannot receive this
        # child even if lifecycle changes between the membership checks.
        directory = os.open(SCOPE, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(os.fstat(directory).st_ino == incarnation['cgroup_inode'], 'child scope replaced')
            membership = os.open('cgroup.procs', os.O_WRONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                os.write(membership, str(os.getpid()).encode())
            finally:
                os.close(membership)
            require(h.same_process(incarnation), 'incarnation changed at child join')
        finally:
            os.close(directory)
    family = socket.AF_INET if ipaddress.ip_address(args.address).version == 4 else socket.AF_INET6
    kind = socket.SOCK_STREAM if args.protocol == 'TCP' else socket.SOCK_DGRAM
    # Socket is created AFTER membership, so xt_cgroup sees the intended scope.
    with socket.socket(family, kind) as client:
        client.settimeout(1)
        client.bind((args.address, args.source_port if args.scoped else 0))
        port = client.getsockname()[1]
        result = 'denied'
        try:
            client.connect((args.address, args.port))
            client.sendall(args.run_id.encode())
            if client.recv(128) == args.run_id.encode():
                result = 'response'
        except (OSError, TimeoutError):
            pass
        print(json.dumps({'sport': port, 'result': result}), flush=True)


def run_client(args, scoped, listener):
    argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--child',
            '--approve', APPROVAL, '--address', args.address, '--port', str(args.port),
            '--protocol', args.protocol, '--run-id', args.run_id,
            '--source-port', str(args.source_port)]
    if scoped:
        argv += ['--scoped', '--incarnation-hash', args.incarnation_hash]
    owned = OwnedChild(argv)
    received = False
    try:
        owned.process.stdin.write(b'G'); owned.process.stdin.flush()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            ready, _, _ = select.select([listener, owned.process.stdout], [], [],
                                        max(0, deadline - time.monotonic()))
            if listener in ready:
                if args.protocol == 'TCP':
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(.25)
                        payload = connection.recv(128)
                        received = payload == args.run_id.encode()
                        if received:
                            connection.sendall(payload)
                else:
                    payload, peer = listener.recvfrom(128)
                    received = payload == args.run_id.encode()
                    if received:
                        listener.sendto(payload, peer)
            if owned.process.stdout in ready:
                raw = owned.process.stdout.readline(1024)
                require(raw and len(raw) < 1024, 'child failed')
                observation = json.loads(raw)
                observation['listener_received'] = received
                return observation
        raise RuntimeError('client deadline')
    finally:
        owned.stop()


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


def collect(args):
    require(os.geteuid() == 0, 'root required')
    # Must be enclosed by the separately reviewed systemd unit. This environment
    # marker alone is not authority: verify the actual transient unit properties.
    lock_fd = os.open('/root/.local/state/home-infra/talos-proof/isolation.lock',
                      os.O_RDWR | os.O_NOFOLLOW)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    unit = 'talos-proof-isolation-' + args.run_id + '.service'
    properties = command(['systemctl', 'show', unit, '--property=Transient,ActiveState,MemoryMax,RuntimeMaxUSec,KillMode,ExecStopPost'])
    require('Transient=yes' in properties and 'ActiveState=active' in properties and
            'MemoryMax=33554432' in properties and 'RuntimeMaxUSec=50s' in properties and
            'KillMode=control-group' in properties and '--cleanup' in properties and
            args.run_id in properties, 'bounded cleanup unit missing')
    require(unit in Path('/proc/self/cgroup').read_text(), 'collector outside bounded unit')
    import host_lifecycle as h
    h.approved_config()
    incarnation = h.load_private('incarnation.json')
    require(h.same_process(incarnation), 'identity mismatch')
    args.incarnation_hash = hashlib.sha256(json.dumps(incarnation, sort_keys=True).encode()).hexdigest()
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
    output = {'kind': 'controlled-host-isolation-capture', 'schema': 1,
              'origin': 'owned-cgroup-child', 'backend': version,
              'claims': [], 'policy_before': before, 'run_id': args.run_id}
    try:
        previous = host_checks(h, incarnation, baseline, previous)
        fam = socket.AF_INET if family == 4 else socket.AF_INET6
        kind = socket.SOCK_STREAM if args.protocol == 'TCP' else socket.SOCK_DGRAM
        with socket.socket(fam, kind) as listener:
            if family == 6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((args.address, args.port))  # no REUSE*, occupancy fails
            if kind == socket.SOCK_STREAM:
                listener.listen(1)
            output['positive_before'] = run_client(args, False, listener)
            require(output['positive_before']['result'] == 'response', 'positive control failed')
            # Unit StopPost owns this exact rule even if supervisor dies here.
            spec = rule(args)
            command([tool(args), '-w', '1', '-t', 'filter', '-I', spec[0],
                     str(reject_index(args)), *spec[1:]])
            installed = True
            during_before = command([tool(args) + '-save', '-c', '-t', 'filter'])
            normalized, count = remove_counter(during_before, args)
            require(count == 0 and v.snapshot(normalized, family)[0] == v.snapshot(before, family)[0],
                    'pre-attempt instrumentation or policy drift')
            output['attempt'] = run_client(args, True, listener)
            during_after = command([tool(args) + '-save', '-c', '-t', 'filter'])
            normalized_after, count = remove_counter(during_after, args)
            require(count > 0, 'no exact-flow instrumentation counter delta')
            old_structure, old_counts = v.snapshot(normalized, family)
            new_structure, new_counts = v.snapshot(normalized_after, family)
            require(old_structure == new_structure, 'policy changed around attempt')
            reject = reject_index(args) - 1
            require(new_counts[v.CHAIN][reject][0] - old_counts[v.CHAIN][reject][0] >= count,
                    'existing REJECT delta smaller than adjacent exact-flow count')
            output['instrumented_before'] = during_before
            output['instrumented_after'] = during_after
            output['exact_flow_packets'] = count
            require(output['attempt']['result'] == 'denied' and
                    not output['attempt']['listener_received'], 'scoped traffic reached listener')
            output['positive_after'] = run_client(args, False, listener)
            require(output['positive_after']['result'] == 'response', 'post-control failed')
            previous = host_checks(h, incarnation, baseline, previous)
    finally:
        if installed:
            cleanup(args)
    output['policy_after'] = command([tool(args) + '-save', '-c', '-t', 'filter'])
    require(v.snapshot(before, family)[0] == v.snapshot(output['policy_after'], family)[0],
            'existing filter policy changed')
    require(time.monotonic() - started <= 45, 'collection deadline exceeded')
    output['cleanup_confirmed'] = True
    output['status'] = 'adjacent-counter-capture-pending-human-review'
    output['remaining_gaps'] = ['actual node transport', *v.GAPS]
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(output, stream)
        stream.write('\n')


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--approve', required=True, choices=[APPROVAL])
    p.add_argument('--address', required=True, choices=['127.0.0.1', '::1'])
    p.add_argument('--protocol', choices=['TCP', 'UDP'], default='TCP')
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--source-port', type=int, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--output', default='/root/.local/state/home-infra/talos-proof/isolation-capture.json')
    p.add_argument('--cleanup', action='store_true')
    p.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--scoped', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--incarnation-hash', help=argparse.SUPPRESS)
    args = p.parse_args()
    require(len(args.run_id) == 32 and all(c in '0123456789abcdef' for c in args.run_id), 'invalid run id')
    require(1024 <= args.source_port <= 65535 and args.source_port != args.port, 'invalid source port')
    require(args.port == 53 or 1024 <= args.port <= 65535, 'invalid synthetic port')
    require(not (args.protocol == 'TCP' and args.port == 53), 'TCP53 not in scope')
    return args


def main():
    try:
        args = arguments()
        if args.cleanup:
            cleanup(args)
        elif args.child:
            child(args)
        else:
            collect(args)
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed-no-acceptance', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
