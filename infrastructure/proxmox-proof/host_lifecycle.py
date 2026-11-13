#!/usr/bin/env python3
"""Proof VM120 lifecycle. Linux/root only. No other VM or host tuning operations.

Private enrollment authorizes an exact configuration, not merely a reusable VMID.
Failure cleanup uses pidfd signals, never VMID-addressed stop (which has a restart
TOCTOU race). QEMU exit is handled by Proxmox's existing qmeventd cleanup.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import signal
import socket
import stat
import subprocess
import sys
import time

STATE = Path('/root/.local/state/home-infra/talos-proof')
HERE = Path(__file__).resolve().parent
CONFIG = Path('/etc/pve/qemu-server/120.conf')
UNIT = 'talos-proof-guard.service'
UUID = '555e8603-58e6-4fb6-a190-378a3f11c257'
MARGIN_MIB = 1536
OVERHEAD_MIB = 384
MAX_SWAP_GROWTH_KIB = 65536


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(*args, timeout=20):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.CalledProcessError as exc:
        # Command identity only; never print captured config/output/credentials.
        raise RuntimeError('command ' + ' '.join(args[:2]) + ' failed, exit=' + str(exc.returncode)) from None


def private_dir():
    require(os.geteuid() == 0, 'root required')
    require(not STATE.is_symlink(), 'state directory symlink forbidden')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = STATE.stat()
    require(s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o700,
            'state directory must be root:0700')


def load_private(name):
    fd = os.open(STATE / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd) as f:
        s = os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and s.st_uid == 0
                and stat.S_IMODE(s.st_mode) == 0o600 and s.st_nlink == 1,
                'receipt must be root:0600 regular single-link file')
        return json.load(f)


def save_private(name, value):
    # State directory is private; O_EXCL avoids following stale temporary links.
    temp = STATE / (name + '.tmp-' + str(os.getpid()))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, STATE / name)
        d = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        temp.unlink(missing_ok=True)


def lock(name):
    fd = os.open(STATE / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    require(os.fstat(fd).st_uid == 0 and stat.S_ISREG(os.fstat(fd).st_mode),
            'unsafe lock')
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def parse_config(text):
    conf, pending = {}, {}
    in_pending = False
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        if line == '[PENDING]' and not in_pending:
            in_pending = True
            continue
        require(not line.startswith('['), 'snapshot/duplicate sections require review')
        key, sep, value = line.partition(': ')
        target = pending if in_pending else conf
        require(sep and key not in target, 'invalid/duplicate configuration key')
        if in_pending:
            require(key in ('args', 'memory') and key in conf,
                    'unapproved pending configuration field')
        target[key] = value
    # qm start consumes these approved pending values; digest is stable afterward.
    # Both enrollment and every startup validate the entire effective profile.
    conf.update(pending)
    return conf


def validate_config(c):
    fixed = {'name': 'talos-proof', 'balloon': '0', 'cores': '2',
             'cpu': 'x86-64-v2-AES', 'machine': 'q35', 'bios': 'ovmf', 'onboot': '0',
             'agent': '0', 'scsihw': 'virtio-scsi-pci', 'boot': 'order=scsi0;ide2',
             'serial0': 'socket', 'vga': 'std', 'ostype': 'l26',
             'smbios1': 'uuid=' + UUID}
    for key, value in fixed.items():
        require(c.get(key) == value, 'unsafe proof setting: ' + key)
    require(c.get('memory') in ('2560', '3072'), 'unapproved RAM size')
    allowed = set(fixed) | {'memory'} | {'scsi0', 'scsi1', 'efidisk0', 'ide2', 'args', 'meta', 'vmgenid'}
    require(not set(c) - allowed, 'unreviewed VM setting (NIC/GPU/hook/etc.)')
    disks = {'scsi0': r'local-zfs:vm-120-disk-1,discard=on,size=32G',
             'scsi1': r'local-zfs:vm-120-disk-2,discard=on,size=64G',
             'efidisk0': r'local-zfs:vm-120-disk-0,efitype=4m,pre-enrolled-keys=0,size=1M',
             'ide2': r'local:iso/talos-proof-v1\.14\.5-amd64\.iso,media=cdrom,size=\d+K'}
    for key, pattern in disks.items():
        require(re.fullmatch(pattern, c.get(key, '')), 'unapproved proof disk: ' + key)
    args = shlex.split(c.get('args', ''))
    require(len(args) == 5 and args[:2] == ['-S', '-netdev'] and args[3] == '-device'
            and args[4] == 'virtio-net-pci,netdev=proofnet,mac=02:00:00:00:01:20',
            'unsafe QEMU arguments')
    parts = args[2].split(',')
    require(parts[:5] == ['user', 'id=proofnet', 'net=172.31.250.0/24',
                         'dhcpstart=172.31.250.10', 'ipv6=off'], 'unsafe slirp network')
    forwards = {}
    for item in parts[5:]:
        m = re.fullmatch(r'hostfwd=tcp:127\.0\.0\.1:(\d+)-172\.31\.250\.10:(\d+)', item)
        require(m is not None, 'non-loopback/unapproved slirp option')
        host, guest = map(int, m.groups())
        require(host not in forwards, 'duplicate host forward')
        forwards[host] = guest
    require(set(forwards) == {50120, 64120, 18080, 18443}
            and forwards[50120] == 50000 and forwards[64120] == 6443
            and all(30000 <= forwards[p] <= 32767 for p in (18080, 18443))
            and forwards[18080] != forwards[18443], 'unsafe host forward ports')
    return forwards


def config_digest(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()


def approved_config():
    receipt = load_private('identity.json')
    require(receipt['uuid'] == UUID, 'wrong enrolled UUID')
    c = parse_config(CONFIG.read_text())
    validate_config(c)
    require(config_digest(c) == receipt['config_sha256'], 'configuration changed: reapproval required')
    return c, receipt


def proc_start(text):
    # comm may contain spaces or ')' characters. starttime is field 22.
    return int(text[text.rfind(')') + 2:].split()[19])


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def process_identity(pid, scope=True):
    p = Path('/proc') / str(pid)
    cmd = (p / 'cmdline').read_bytes().split(b'\0')
    require(any(b'uuid=' + UUID.encode() in a or a == UUID.encode() for a in cmd),
            'QEMU UUID mismatch')
    require(b'-id' in cmd and cmd[cmd.index(b'-id') + 1] == b'120', 'QEMU VMID mismatch')
    if scope:
        require((p / 'cgroup').read_text() == '0::/qemu.slice/120.scope\n', 'QEMU cgroup mismatch')
    require(Path(os.readlink(p / 'exe')).name in ('qemu-system-x86_64', 'kvm'),
            'not proof QEMU executable')
    result = {'pid': pid, 'start_ticks': proc_start((p / 'stat').read_text()),
              'boot_id': boot_id(), 'uuid': UUID}
    if scope:
        result['cgroup_inode'] = Path('/sys/fs/cgroup/qemu.slice/120.scope').stat().st_ino
    return result


def capture():
    pid = int(Path('/run/qemu-server/120.pid').read_text())
    return process_identity(pid)


def same_process(receipt, scope=True):
    if receipt.get('boot_id') != boot_id() or receipt.get('uuid') != UUID:
        return False
    try:
        keys = ('pid', 'start_ticks', 'boot_id', 'uuid') + (('cgroup_inode',) if scope else ())
        return process_identity(receipt['pid'], scope=scope) == {k: receipt[k] for k in keys}
    except (FileNotFoundError, ProcessLookupError):
        return False


def open_incarnation(receipt):
    # pidfd pins the original process even if numeric PID is subsequently recycled.
    require(same_process(receipt, scope=False), 'proof incarnation no longer matches')
    fd = os.pidfd_open(receipt['pid'])
    try:
        require(same_process(receipt, scope=False), 'proof incarnation changed while opening pidfd')
    except BaseException:
        os.close(fd)
        raise
    return fd


def stop_incarnation(receipt):
    if not same_process(receipt, scope=False):
        print('STOP skipped: enrolled incarnation is gone', flush=True)
        return
    fd = open_incarnation(receipt)
    try:
        for sig, wait in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
            try:
                signal.pidfd_send_signal(fd, sig)
            except ProcessLookupError:
                return
            if select.select([fd], [], [], wait)[0]:
                print('STOP confirmed: original proof QEMU exited', flush=True)
                return
        raise RuntimeError('proof QEMU did not exit after bounded pidfd stop')
    finally:
        os.close(fd)


def sample():
    mem = {l.split(':')[0]: int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()}
    vm = dict(l.split() for l in Path('/proc/vmstat').read_text().splitlines())
    psi = {l.split()[0]: int(l.split()[-1].split('=')[1])
           for l in Path('/proc/pressure/memory').read_text().splitlines()}
    return {'monotonic': time.monotonic(), 'available_mib': mem['MemAvailable'] // 1024,
            'swap_used_kib': mem['SwapTotal'] - mem['SwapFree'],
            'swap_io_pages': int(vm['pswpin']) + int(vm['pswpout']), 'psi_totals': psi}


class ResourceCheck:
    def __init__(self, baseline):
        require(isinstance(baseline, int) and baseline >= 0, 'invalid swap baseline')
        self.baseline = baseline
        self.previous = None
        self.swap_samples = 0
        self.pressure_since = None

    def check(self, s, admission_mib=None):
        require(s['available_mib'] >= (admission_mib or MARGIN_MIB), 'host memory margin breached')
        require(s['swap_used_kib'] - self.baseline <= MAX_SWAP_GROWTH_KIB,
                'host swap growth breached')
        rates = {'some': 0.0, 'full': 0.0}
        if self.previous:
            elapsed = s['monotonic'] - self.previous['monotonic']
            require(0 < elapsed <= 15, 'guard sampling deadline missed')
            self.swap_samples = self.swap_samples + 1 if s['swap_io_pages'] > self.previous['swap_io_pages'] else 0
            for kind in rates:
                delta = s['psi_totals'][kind] - self.previous['psi_totals'][kind]
                require(delta >= 0, 'PSI counters reset')
                rates[kind] = delta / elapsed / 10000
            if rates['full'] >= 1 or rates['some'] >= 5:
                if self.pressure_since is None:
                    self.pressure_since = self.previous['monotonic']
            else:
                self.pressure_since = None
        self.previous = s
        require(self.swap_samples < 3, 'sustained host swap IO')
        require(self.pressure_since is None or s['monotonic'] - self.pressure_since < 30,
                'sustained host memory PSI')
        return rates


def notify(message):
    target = os.environ.get('NOTIFY_SOCKET')
    require(target, 'systemd notify socket required')
    if target.startswith('@'):
        target = '\0' + target[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
        s.connect(target)
        s.sendall(message.encode())


def guard():
    guard_lock = lock('supervised-guard.lock')
    require(guard_lock >= 0, 'guard lock unavailable')
    _, identity = approved_config()
    incarnation = load_private('incarnation.json')
    require(incarnation['config_sha256'] == identity['config_sha256'], 'incarnation/config mismatch')
    require(same_process(incarnation), 'guard target incarnation absent')
    check = ResourceCheck(identity['swap_baseline_kib'])
    rates = check.check(sample())
    notify('READY=1\nWATCHDOG=1\nSTATUS=VM120 identity and initial resource sample verified')
    print('READY: proof incarnation verified; initial sample safe', flush=True)
    while same_process(incarnation):
        rates = check.check(sample())
        print(json.dumps({'event': 'sample', 'time': time.time(),
                          'available_mib': check.previous['available_mib'],
                          'swap_used_kib': check.previous['swap_used_kib'],
                          'psi_delta_percent': rates}), flush=True)
        notify('WATCHDOG=1')
        time.sleep(5)
    print('Original proof incarnation gone; monitor exiting', flush=True)


def enroll(approval):
    require(approval == UUID, 'explicit approved UUID required')
    c = parse_config(CONFIG.read_text())
    forwards = validate_config(c)
    # Preserve the original proof baseline; do not normalize new host swap growth.
    baseline_path = STATE / 'swap-baseline-kib'
    require(not baseline_path.is_symlink(), 'baseline symlink forbidden')
    baseline = int(baseline_path.read_text())
    ResourceCheck(baseline).check(sample())
    save_private('identity.json', {'uuid': UUID, 'config_sha256': config_digest(c),
                 'swap_baseline_kib': baseline, 'memory_mib': int(c['memory']),
                 'forwards': forwards, 'enrolled_at': time.time()})
    print('Enrolled approved VM120 configuration and original swap baseline; no service activation')


def start():
    invocation = os.environ.get('INVOCATION_ID')
    require(invocation, 'startup must run under talos-proof-start.service')
    startup_lock = lock('lifecycle.lock')
    require(startup_lock >= 0, 'lifecycle lock unavailable')
    c, identity = approved_config()
    require(not Path('/run/qemu-server/120.pid').exists(), 'VM already running or stale PID file: review required')
    require(run('systemctl', 'show', UNIT, '-p', 'ActiveState', '--value').strip() in ('inactive', 'failed'),
            'guard must be inactive')
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd support required')
    ResourceCheck(identity['swap_baseline_kib']).check(
        sample(), int(c['memory']) + MARGIN_MIB + OVERHEAD_MIB)
    attempt = {'boot_id': boot_id(), 'uuid': UUID,
               'min_start_ticks': int(float(Path('/proc/uptime').read_text().split()[0]) * os.sysconf('SC_CLK_TCK')),
               'attempt_id': os.urandom(16).hex(), 'invocation_id': invocation}
    save_private('startup.json', attempt)
    incarnation = None
    try:
        run('qm', 'start', '120', timeout=90)
        incarnation = capture()
        incarnation['attempt_id'] = attempt['attempt_id']
        incarnation['config_sha256'] = identity['config_sha256']
        save_private('incarnation.json', incarnation)
        # qm status only queries QMP; no guest execution or packet experiments.
        status = run('qm', 'status', '120', '--verbose')
        require(re.search(r'^qmpstatus: (paused|prelaunch)$', status, re.MULTILINE),
                'QEMU not paused/prelaunch')
        approved_config()
        run('bash', str(HERE / 'isolation.sh'), timeout=90)
        # Type=notify start does not complete until identity + first safe sample ACK.
        run('systemctl', 'start', UNIT, timeout=45)
        require(run('systemctl', 'show', UNIT, '-p', 'ActiveState', '--value').strip() == 'active',
                'guard did not acknowledge readiness')
        require(same_process(incarnation), 'QEMU changed before resume')
        approved_config()
        run('qm', 'resume', '120')
        attempt['complete'] = True
        save_private('startup.json', attempt)
        print('VM120 resumed only after isolation and supervised guard READY acknowledgement')
    except BaseException:
        if incarnation is not None:
            stop_incarnation(incarnation)
        else:
            # A failed qm start may leave a QEMU behind. Capture only the approved UUID.
            try:
                leftover = capture()
            except FileNotFoundError:
                leftover = None
            if leftover:
                stop_incarnation(leftover)
        raise



def startup_cleanup():
    # The oneshot supervisor covers wrapper death, including SIGKILL during qm start.
    if os.environ.get('SERVICE_RESULT') == 'success':
        return
    try:
        attempt = load_private('startup.json')
    except FileNotFoundError:
        return  # failed before this operation could start QEMU
    if (attempt['boot_id'] != boot_id() or attempt.get('complete')
            or attempt.get('invocation_id') != os.environ.get('INVOCATION_ID')):
        return
    try:
        receipt = load_private('incarnation.json')
    except FileNotFoundError:
        receipt = None
    if receipt and receipt.get('attempt_id') == attempt['attempt_id']:
        stop_incarnation(receipt)
        return
    # Death between qm start and capture: accept only a QEMU born in this attempt.
    try:
        candidate = capture()
    except FileNotFoundError:
        return
    if candidate['start_ticks'] >= attempt['min_start_ticks']:
        stop_incarnation(candidate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enroll', 'start', 'guard', 'stop-post', 'start-cleanup'])
    parser.add_argument('--approve-uuid')
    args = parser.parse_args()
    private_dir()
    if args.action == 'enroll':
        enroll(args.approve_uuid)
    elif args.action == 'start':
        start()
    elif args.action == 'guard':
        guard()
    elif args.action == 'start-cleanup':
        startup_cleanup()
    else:
        # Do not require a healthy baseline/config here: they may have caused failure.
        stop_incarnation(load_private('incarnation.json'))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never dump subprocess stderr/config/credentials into supervisor logs.
        print('Proof lifecycle failed: ' + type(exc).__name__ + ': ' +
              (str(exc) if isinstance(exc, RuntimeError) else 'operation failed'), file=sys.stderr)
        sys.exit(1)
