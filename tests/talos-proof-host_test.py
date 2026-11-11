#!/usr/bin/env python3
"""Offline-only lifecycle regression tests. All host/VM operations are mocked."""
import copy
import importlib.util
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('host', ROOT / 'infrastructure/proxmox-proof/host_lifecycle.py')
h = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(h)


def config():
    return {'name': 'talos-proof', 'memory': '2560', 'balloon': '0', 'cores': '2',
            'cpu': 'x86-64-v2-AES', 'machine': 'q35', 'bios': 'ovmf', 'onboot': '0',
            'agent': '0', 'scsihw': 'virtio-scsi-pci', 'boot': 'order=scsi0;ide2',
            'serial0': 'socket', 'vga': 'std', 'ostype': 'l26', 'smbios1': 'uuid=' + h.UUID,
            'scsi0': 'local-zfs:vm-120-disk-1,discard=on,size=32G',
            'scsi1': 'local-zfs:vm-120-disk-2,discard=on,size=64G',
            'efidisk0': 'local-zfs:vm-120-disk-0,efitype=4m,pre-enrolled-keys=0,size=1M',
            'ide2': 'local:iso/talos-proof-v1.14.5-amd64.iso,media=cdrom,size=355660K',
            'args': '-S -netdev user,id=proofnet,net=172.31.250.0/24,dhcpstart=172.31.250.10,ipv6=off,'
                    'hostfwd=tcp:127.0.0.1:50120-172.31.250.10:50000,'
                    'hostfwd=tcp:127.0.0.1:64120-172.31.250.10:6443,'
                    'hostfwd=tcp:127.0.0.1:18080-172.31.250.10:30659,'
                    'hostfwd=tcp:127.0.0.1:18443-172.31.250.10:30310 '
                    '-device virtio-net-pci,netdev=proofnet,mac=02:00:00:00:01:20'}


def sample(t=0, available=5000, swap=24, io=9, some=0, full=0):
    return dict(monotonic=t, available_mib=available, swap_used_kib=swap,
                swap_io_pages=io, psi_totals={'some': some, 'full': full})


class ConfigTests(unittest.TestCase):
    def test_approved_profiles_and_dynamic_ports(self):
        for ram in ('2560', '3072'):
            c = config(); c['memory'] = ram
            self.assertEqual(h.validate_config(c)[18080], 30659)

    def test_unsafe_fields(self):
        mutations = [('name', 'other'), ('smbios1', 'uuid=other'), ('memory', '4096'),
                     ('memory', '3584'), ('cores', '3'), ('cpu', 'host'), ('onboot', '1'),
                     ('net0', 'virtio,bridge=vmbr0'), ('hostpci0', '0000:01:00'),
                     ('hookscript', 'local:snippets/test.pl'), ('scsi1', 'local-zfs:vm-101-disk-0'),
                     ('balloon', '1024'), ('usb0', 'host=1234:5678')]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                c = config(); c[key] = value
                with self.assertRaises(RuntimeError): h.validate_config(c)

    def test_unsafe_slirp(self):
        original = config()['args']
        mutations = [original.replace('-S ', ''), original + ' -net nic',
                     original.replace('ipv6=off', 'ipv6=on'),
                     original.replace('127.0.0.1:18080', '0.0.0.0:18080'),
                     original.replace(':30659', ':22'),
                     original.replace(':50000', ':6443'),
                     original.replace('30310', '30659'),
                     original.replace(',ipv6=off', ',ipv6=off,smb=/root'),
                     original.replace(',ipv6=off', ',ipv6=off,guestfwd=tcp:1.2.3.4:22-cmd:sh')]
        for args in mutations:
            with self.subTest(args=args):
                c = config(); c['args'] = args
                with self.assertRaises(RuntimeError): h.validate_config(c)

    def test_config_digest_changes_with_mapping(self):
        c = config(); d = copy.deepcopy(c); d['args'] = d['args'].replace('30659', '30080')
        self.assertNotEqual(h.config_digest(c), h.config_digest(d))

    def test_empty_pending_marker_accepted(self):
        self.assertEqual(h.parse_config('name: talos-proof\n[PENDING]\n'), {'name': 'talos-proof'})

    def test_approved_pending_overlay_validated(self):
        c = config()
        text = ''.join(k + ': ' + v + '\n' for k, v in c.items())
        result = h.parse_config(text + '[PENDING]\nmemory: 3072\n')
        h.validate_config(result)
        self.assertEqual(result['memory'], '3072')
        with self.assertRaises(RuntimeError):
            h.validate_config(h.parse_config(text + '[PENDING]\nmemory: 4096\n'))

    def test_pending_and_duplicate_rejected(self):
        for text in ('name: talos-proof\n[PENDING]\nnet0: bridge=vmbr0', 'name: a\nname: b'):
            with self.assertRaises(RuntimeError): h.parse_config(text)


class ResourceTests(unittest.TestCase):
    def test_hard_memory_margin(self):
        h.ResourceCheck(24).check(sample(available=1536))
        with self.assertRaises(RuntimeError): h.ResourceCheck(24).check(sample(available=1535))

    def test_fresh_admission_profiles(self):
        for ram in (2560, 3072):
            needed = ram + 1536 + 384
            h.ResourceCheck(24).check(sample(available=needed), needed)
            with self.assertRaises(RuntimeError):
                h.ResourceCheck(24).check(sample(available=needed-1), needed)

    def test_swap_baseline_and_growth(self):
        h.ResourceCheck(24).check(sample(swap=24 + 65536))
        with self.assertRaises(RuntimeError): h.ResourceCheck(24).check(sample(swap=24 + 65537))
        for bad in (-1, None, '24'):
            with self.assertRaises(RuntimeError): h.ResourceCheck(bad)

    def test_actual_psi_30_seconds(self):
        for kind, rate in (('full', 1), ('some', 5)):
            check = h.ResourceCheck(24)
            check.check(sample())
            for t in range(5, 30, 5):
                check.check(sample(t=t, **{kind: t * 10000 * rate}))
            with self.assertRaises(RuntimeError):
                check.check(sample(t=30, **{kind: 30 * 10000 * rate}))

    def test_pressure_resets_after_safe_interval(self):
        check = h.ResourceCheck(24)
        for t in range(0, 70, 5):
            check.check(sample(t=t, full=min(t, 20) * 10000))

    def test_three_swap_io_intervals(self):
        check = h.ResourceCheck(24)
        for i in range(3): check.check(sample(t=i*5, io=9+i))
        with self.assertRaises(RuntimeError): check.check(sample(t=15, io=12))

    def test_sampling_hang_and_counter_reset(self):
        check = h.ResourceCheck(24); check.check(sample())
        with self.assertRaises(RuntimeError): check.check(sample(t=16))
        check = h.ResourceCheck(24); check.check(sample(full=100))
        with self.assertRaises(RuntimeError): check.check(sample(t=5, full=0))


class IdentityTests(unittest.TestCase):
    def test_proc_stat_with_spaces_parentheses(self):
        self.assertEqual(h.proc_start('123 (qemu ) worker) S ' + '0 '*18 + '456 0'), 456)

    def test_replaced_pid_or_boot_never_signalled(self):
        with patch.object(h, 'same_process', return_value=False), patch.object(h.os, 'pidfd_open', create=True) as opened:
            h.stop_incarnation({'pid': 123})
            opened.assert_not_called()

    def test_pidfd_recheck_closes_without_signal(self):
        with patch.object(h, 'same_process', side_effect=[True, False]), \
             patch.object(h.os, 'pidfd_open', return_value=99, create=True), \
             patch.object(h.os, 'close') as close:
            with self.assertRaises(RuntimeError): h.open_incarnation({'pid': 123})
            close.assert_called_once_with(99)

    def test_stop_signals_only_pinned_fd_with_bounded_escalation(self):
        with patch.object(h, 'same_process', return_value=True), \
             patch.object(h, 'open_incarnation', return_value=99), \
             patch.object(h.signal, 'pidfd_send_signal', create=True) as send, \
             patch.object(h.select, 'select', side_effect=[([], [], []), ([99], [], [])]), \
             patch.object(h.os, 'close'), patch.object(h, 'run') as command:
            h.stop_incarnation({'pid': 123})
            self.assertEqual(send.call_args_list[0].args, (99, signal.SIGTERM))
            self.assertEqual(send.call_args_list[1].args, (99, signal.SIGKILL))
            command.assert_not_called()  # no VMID-addressed qm stop race

    def test_private_receipt_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d, patch.object(h, 'STATE', Path(d)):
            (Path(d)/'target').write_text('{}')
            (Path(d)/'identity.json').symlink_to('target')
            with self.assertRaises(OSError): h.load_private('identity.json')

    def test_completed_start_cleanup_never_targets_running_vm(self):
        with patch.dict(os.environ, {'SERVICE_RESULT': 'exit-code'}), \
             patch.object(h, 'load_private', return_value={'boot_id': 'boot', 'complete': True}), \
             patch.object(h, 'boot_id', return_value='boot'), patch.object(h, 'capture') as capture:
            h.startup_cleanup(); capture.assert_not_called()


class GuardTests(unittest.TestCase):
    def guard_case(self, safe=True):
        receipt = {'config_sha256': 'hash', 'swap_baseline_kib': 24}
        events = []
        with patch.object(h, 'lock', return_value=99), \
             patch.object(h, 'approved_config', return_value=({}, receipt)), \
             patch.object(h, 'load_private', return_value={'config_sha256': 'hash'}), \
             patch.object(h, 'same_process', side_effect=[True, False]), \
             patch.object(h, 'sample', return_value=sample(available=5000 if safe else 1000)), \
             patch.object(h, 'notify', side_effect=events.append):
            if safe: h.guard()
            else:
                with self.assertRaises(RuntimeError): h.guard()
        return events

    def test_no_ack_on_unsafe_first_sample(self): self.assertEqual(self.guard_case(False), [])
    def test_ack_after_safe_identity_and_first_sample(self):
        self.assertTrue(self.guard_case()[0].startswith('READY=1\nWATCHDOG=1'))

    def test_missing_baseline_receipt_never_acknowledges(self):
        with patch.object(h, 'lock', return_value=99), \
             patch.object(h, 'approved_config', side_effect=FileNotFoundError), \
             patch.object(h, 'notify') as notify:
            with self.assertRaises(FileNotFoundError): h.guard()
            notify.assert_not_called()

    def test_duplicate_guard_never_acknowledges(self):
        with patch.object(h, 'lock', side_effect=BlockingIOError), patch.object(h, 'notify') as notify:
            with self.assertRaises(BlockingIOError): h.guard()
            notify.assert_not_called()

    def test_units_supervise_crash_hang_and_wrapper_death(self):
        guard = (h.HERE/'talos-proof-guard.service').read_text()
        start = (h.HERE/'talos-proof-start.service').read_text()
        for setting in ('Type=notify', 'WatchdogSec=15s', 'ExecStopPost=', 'Restart=no', 'TimeoutStartSec=25s'):
            self.assertIn(setting, guard)
        self.assertIn('start-cleanup', start)
        self.assertNotIn('\n[Install]', guard + start)



class StartupTests(unittest.TestCase):
    def exercise(self, *, failure=None, available=5000):
        calls = []
        identity = {'config_sha256': 'hash', 'swap_baseline_kib': 24}
        def command(*args, **kwargs):
            calls.append(args)
            if failure and args[:len(failure)] == failure:
                raise RuntimeError('injected failure')
            if args[:2] == ('qm', 'status'): return 'qmpstatus: prelaunch\n'
            if args[:2] == ('systemctl', 'show'):
                return 'active' if any(c[:2] == ('systemctl', 'start') for c in calls) else 'inactive'
            return ''
        with patch.dict(os.environ, {'INVOCATION_ID': 'test-start'}), \
             patch.object(h, 'lock', return_value=99), \
             patch.object(h, 'approved_config', return_value=(config(), identity)), \
             patch.object(h.Path, 'exists', return_value=False), \
             patch.object(h.Path, 'read_text', return_value='1000.0 0'), \
             patch.object(h, 'boot_id', return_value='boot'), \
             patch.object(h, 'sample', return_value=sample(available=available)), \
             patch.object(h, 'run', side_effect=command), \
             patch.object(h, 'capture', return_value={'pid': 123}), \
             patch.object(h, 'same_process', return_value=True), \
             patch.object(h, 'save_private') as save, \
             patch.object(h, 'stop_incarnation') as stop, \
             patch.object(h.os, 'pidfd_open', create=True), \
             patch.object(h.signal, 'pidfd_send_signal', create=True):
            if failure or available < 4480:
                with self.assertRaises(RuntimeError): h.start()
            else:
                h.start()
            return calls, stop.call_count, save.call_args_list

    def test_resume_only_after_isolation_and_guard_ready(self):
        calls, stopped, saved = self.exercise()
        self.assertLess(calls.index(('bash', str(h.HERE/'isolation.sh'))),
                        calls.index(('systemctl', 'start', h.UNIT)))
        self.assertLess(calls.index(('systemctl', 'start', h.UNIT)),
                        calls.index(('qm', 'resume', '120')))
        self.assertEqual(stopped, 0)
        self.assertTrue(saved[-1].args[1]['complete'])

    def test_guard_ack_failure_stops_and_never_resumes(self):
        calls, stopped, _ = self.exercise(failure=('systemctl', 'start'))
        self.assertEqual(stopped, 1)
        self.assertNotIn(('qm', 'resume', '120'), calls)

    def test_isolation_failure_stops_and_never_resumes(self):
        calls, stopped, _ = self.exercise(failure=('bash',))
        self.assertEqual(stopped, 1)
        self.assertNotIn(('qm', 'resume', '120'), calls)

    def test_admission_failure_never_starts(self):
        calls, stopped, _ = self.exercise(available=4479)
        self.assertNotIn(('qm', 'start', '120'), calls)
        self.assertEqual(stopped, 0)

    def test_old_invocation_cleanup_never_targets_new_process(self):
        with patch.dict(os.environ, {'SERVICE_RESULT': 'signal', 'INVOCATION_ID': 'new'}), \
             patch.object(h, 'load_private', return_value={'boot_id': 'boot', 'invocation_id': 'old'}), \
             patch.object(h, 'boot_id', return_value='boot'), patch.object(h, 'capture') as capture:
            h.startup_cleanup(); capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
