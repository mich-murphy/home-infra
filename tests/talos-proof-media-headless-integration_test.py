#!/usr/bin/env python3
"""Offline contracts/owned IPC only. NO mocked application acceptance claim."""
import copy
import hashlib
import importlib
import io
import json
import os
import select
import signal
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
i = importlib.import_module('talos-proof-media-headless-integration')
h = i.h


def ipc_only(connection, binding):
    """New local IPC bytes, no app API or state access."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        connection.recv(4096)
        if binding['case'] == 'partial':
            connection.sendall(b'["ok",')
            time.sleep(5)
        elif binding['case'] == 'hang':
            connection.sendall(b'["ok",')
            time.sleep(5)
        else:
            connection.sendall(b'["ok", true]\n')
            time.sleep(5)
    finally:
        connection.close()


def identity():
    return {'pid': os.getpid(), 'ppid': os.getppid(),
            'sid': os.getsid(0), 'pgid': os.getpgrp()}


def tree_leader(connection):
    """Synthetic only; all descendants retain the owned IPC endpoint."""
    binding = i.worker_binding(connection)
    connection.recv(4096)  # wait until the test has registered exit observation
    read_fd, write_fd = os.pipe()
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--tree-child',
                      str(connection.fileno()), str(write_fd)],
                     pass_fds=(connection.fileno(), write_fd), close_fds=True)
    os.close(write_fd)
    with os.fdopen(read_fd, 'rb') as reports:
        rows = [identity(), json.loads(reports.readline()), json.loads(reports.readline())]
    connection.sendall(json.dumps(['ok', rows]).encode() + b'\n')
    if binding['case'] == 'exit':
        os._exit(0)
    time.sleep(30)


def tree_descendant(role, connection_fd, report_fd):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.write(report_fd, json.dumps(identity()).encode() + b'\n')
    if role == '--tree-child':
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--tree-grandchild',
                          str(connection_fd), str(report_fd)],
                         pass_fds=(connection_fd, report_fd), close_fds=True)
    os.close(report_fd)
    time.sleep(30)


class Receipt(unittest.TestCase):
    def setUp(self):
        self.templates = {name: {'spec': {'containers': [{'name': name, 'resources': {
            'limits': {'cpu': '1', 'memory': str(limit) + 'Mi'}}}]}}
            for name, limit in i.LIMITS.items()}
        self.binding = {'client': 'new-client', 'session': 'new-session', 'item': '12',
                        'media_path': '/library/parts/1/2/file.mp4',
                        'ffmpeg': '/nix/store/' + 'a' * 32 + '-ffmpeg/bin/ffmpeg',
                        'decoder_sha256': hashlib.sha256(b'NEW decoder test bytes').hexdigest()}
        self.receipt = {'group': i.GROUP, 'expires': 200, 'headless': {
            'mode': i.MODE, **{k: self.binding[k] for k in ('client', 'session', 'item', 'media_path')},
            'fixture_sha256': h.FIXTURE_SHA256, 'fixture_bytes': h.FIXTURE_BYTES,
            'decoder_path': self.binding['ffmpeg'], 'decoder_sha256': self.binding['decoder_sha256'],
            'expires': 200, 'limits_mib': i.LIMITS, 'reserve_mib': 192, 'total_mib': 896,
            'pod_templates_sha256': {k: i.canonical_sha(v) for k, v in self.templates.items()},
            'darwin_rss_watchdog_not_hard_ceiling': True}}

    def validate(self):
        with patch.object(h, 'command', return_value=[self.binding['ffmpeg']]), \
             patch('builtins.open', return_value=io.BytesIO(b'NEW decoder test bytes')):
            i.validate_receipt(self.receipt, self.binding, self.templates, now=100)

    def test_exact_proposed_receipt_contract(self):
        self.validate()

    def test_old_browser_or_other_receipts_never_authorize(self):
        for key, value in [('mode', 'browser'), ('client', 'old-client'), ('session', 'old'),
                           ('item', '13'), ('fixture_sha256', '0' * 64), ('fixture_bytes', 1),
                           ('decoder_path', '/bin/ffmpeg'), ('decoder_sha256', '0' * 64),
                           ('expires', 201), ('total_mib', 897), ('reserve_mib', 0),
                           ('darwin_rss_watchdog_not_hard_ceiling', False)]:
            with self.subTest(key=key):
                original = copy.deepcopy(self.receipt)
                self.receipt['headless'][key] = value
                with self.assertRaises(h.Rejected):
                    self.validate()
                self.receipt = original
        del self.receipt['headless']
        with self.assertRaises(h.Rejected):
            self.validate()

    def test_expiry_and_template_drift(self):
        self.receipt['expires'] = 99
        with self.assertRaises(h.Rejected):
            self.validate()
        self.receipt['expires'] = 200
        self.templates['plex']['metadata'] = {'annotations': {'changed': 'yes'}}
        with self.assertRaises(h.Rejected):
            self.validate()

    def test_full_template_init_sidecar_ceiling(self):
        self.templates['plex']['spec']['initContainers'] = [{'name': 'extra', 'restartPolicy': 'Always',
            'resources': {'limits': {'cpu': '1', 'memory': '1Mi'}}}]
        self.receipt['headless']['pod_templates_sha256'] = {
            k: i.canonical_sha(v) for k, v in self.templates.items()}
        with self.assertRaises(h.Rejected):
            self.validate()

    def test_exact_decoder_hash(self):
        self.binding['decoder_sha256'] = '0' * 64
        self.receipt['headless']['decoder_sha256'] = '0' * 64
        with self.assertRaises(h.Rejected):
            self.validate()


class FakeWorker:
    def __init__(self):
        self.reply, self.actions = None, []
    def poll(self):
        result, self.reply = self.reply, None
        return result
    def submit(self, action, payload=None):
        self.actions.append((action, payload))


class Process:
    pid = 123456789
    def __init__(self):
        self.rc = None
    def poll(self):
        return self.rc


class Watermark(unittest.TestCase):
    def setUp(self):
        self.worker, self.process = FakeWorker(), Process()
        self.identity = h.Identity('client', 'session', '12')
        self.pump = i.Pump(self.worker, self.identity, [], time.time() + 60)
        self.pump.tick(self.process, h.Progress(0, 0), True)
        self.pump.observe(h.Progress(1, 100000), True, True)
        self.pump.observe(h.Progress(2, 200000), True, True)
        self.rows = [{'rating_key': '12', 'machine_id': 'client', 'state': 'playing'}]

    def response(self):
        self.worker.reply = ('playing', True)
        self.pump.tick(self.process, h.Progress(2, 200000), True)
        self.worker.reply = ('activity', self.rows)
        self.pump.tick(self.process, h.Progress(2, 200000), True)

    def test_first_after_response_report_is_only_watermark(self):
        self.response()
        self.assertEqual(self.pump.life.stage, 'playing')
        self.pump.observe(h.Progress(3, 300000, 1, 1), True, True)
        self.assertEqual(self.pump.life.stage, 'activity')
        self.pump.observe(h.Progress(4, 400000, 2, 1), True, True)
        self.assertEqual(self.pump.life.stage, 'concurrent')
        self.assertEqual(self.worker.actions[0][1]['media_us'], 200000)
        self.assertEqual([a[0] for a in self.worker.actions], ['playing', 'activity'])

    def test_queued_before_response_never_earns_concurrency(self):
        self.pump.observe(h.Progress(3, 300000), True, True)
        self.pump.observe(h.Progress(4, 400000), True, True)
        self.response()
        self.pump.observe(h.Progress(5, 500000, 1, 1), True, True)
        self.assertEqual(self.pump.life.stage, 'activity')
        with self.assertRaises(h.Rejected):
            self.pump.observe(h.Progress(6, 600000), False, True)

    def test_liveness_recheck_after_activity_and_before_playing(self):
        self.process.rc = 0
        self.worker.reply = ('activity', self.rows)
        with self.assertRaises(h.Rejected):
            self.pump.tick(self.process, h.Progress(2, 200000), True)
        other = i.Pump(FakeWorker(), self.identity, [], time.time() + 60)
        other.process = self.process
        other.observe(h.Progress(1, 100000), True, True)
        with self.assertRaises(h.Rejected):
            other.observe(h.Progress(2, 200000), True, True)

    def test_expiry_checked_without_api_on_pump(self):
        self.pump.expires = 0
        with self.assertRaises(h.Rejected):
            self.pump.tick(self.process, h.Progress(2, 200000), True)


class BoundedTransport(unittest.TestCase):
    def test_existing_verified_transport_body_bound_and_close(self):
        api = object.__new__(importlib.import_module('talos-proof-media-http').API)
        api.base, api.headers = 'https://plex.proof.invalid:18443', {}
        class Response(io.BytesIO):
            status, headers = 200, {}
            def geturl(self):
                return api.base + '/unit'
        class Opener:
            def open(self, request, timeout):
                self.timeout = timeout
                self.response = Response(b'x' * 32769)
                return self.response
        api.opener = Opener()
        with self.assertRaisesRegex(ValueError, 'response exceeded'):
            i.BoundedAPI(api).call('/unit', raw=True)
        self.assertEqual(api.opener.timeout, 1)
        self.assertTrue(api.opener.response.closed)

    def test_launcher_rejects_other_decoder_arguments(self):
        result = subprocess.run([sys.executable, '-I', '-S',
                                 str(ROOT / 'scripts/talos-proof-media-headless-exec.py'),
                                 '/nix/store/' + 'a' * 32 + '-ffmpeg/bin/ffmpeg',
                                 '-i', 'https://not-allowed.invalid/'],
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'fixed stdin-only', result.stderr)


class OwnedIPC(unittest.TestCase):
    def worker(self, case):
        with patch.object(i, 'worker_command', lambda fd: [sys.executable, str(Path(__file__).resolve()), '--ipc-worker', str(fd)]):
            worker = i.Worker({'case': case})
        self.addCleanup(worker.close)
        return worker

    def test_serial_small_reply_and_reap(self):
        worker = self.worker('ok')
        worker.submit('unit')
        with self.assertRaises(h.Rejected):
            worker.submit('overlap')
        self.assertTrue(worker.wait())
        worker.close()
        self.assertIsNotNone(worker._process.poll())

    def test_partial_ipc_reply_does_not_block_pump(self):
        worker = self.worker('partial')
        worker.submit('unit')
        deadline = time.monotonic() + 2
        while not worker.buffer and time.monotonic() < deadline:
            before = time.monotonic()
            self.assertIsNone(worker.poll())
            self.assertLess(time.monotonic() - before, 0.1)
            time.sleep(0.01)
        self.assertTrue(worker.buffer)
        worker.pending = ('unit', time.monotonic() - 1)
        with self.assertRaisesRegex(h.Rejected, 'unknown outcome'):
            worker.poll()
        worker.close()
        self.assertIsNotNone(worker._process.poll())

    def test_hung_worker_deadline_and_no_orphan(self):
        worker = self.worker('hang')
        worker.submit('unit')
        # Synthetic fixture readiness, not an application response.
        deadline = time.monotonic() + 2
        while not worker.buffer and time.monotonic() < deadline:
            worker.poll()
            time.sleep(0.01)
        self.assertTrue(worker.buffer)
        worker.pending = ('unit', time.monotonic() - 1)
        with self.assertRaises(h.Rejected):
            worker.wait()
        worker.close()
        self.assertIsNotNone(worker._process.poll())

    def test_cli_blocked_without_state_or_network(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/talos-proof-media-headless-integration.py')],
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'unsupported', result.stderr)
        self.assertIn(b'BLOCKED', result.stderr)


class WorkerContainment(unittest.TestCase):
    def make_worker(self, case='tree', tree=True):
        mode = '--tree-leader' if tree else '--ipc-worker'
        with patch.object(i, 'worker_command', lambda fd: [
                sys.executable, str(Path(__file__).resolve()), mode, str(fd)]):
            worker = i.Worker({'case': case})
        # Independent bounded fallback, registered before any assertion. It
        # retains exclusive waiter ownership too; never signal after reaping.
        def fallback():
            try:
                worker.connection.close()
            finally:
                if worker._process.returncode is None:
                    if not getattr(worker, '_test_final_kill', False):
                        worker._require_signal_ownership()
                        os.killpg(worker._process.pid, signal.SIGKILL)
                    worker._process.wait(timeout=2)
        self.addCleanup(fallback)
        return worker

    def observe_exit(self, process):
        if sys.platform == 'darwin':
            # Register before submitting the action that permits fixture exit.
            queue = select.kqueue()
            self.addCleanup(queue.close)
            queue.control([select.kevent(process.pid, filter=select.KQ_FILTER_PROC,
                                         flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                                         fflags=select.KQ_NOTE_EXIT)], 0, 0)

            def observed():
                events = queue.control([], 1, 2)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].ident, process.pid)
                self.assertTrue(events[0].fflags & select.KQ_NOTE_EXIT)
                self.assertIsNone(process.returncode)
            return observed
        if sys.platform == 'linux':
            return lambda: self.observe_linux_exit(process)
        self.fail('nonreaping exit observation unsupported on ' + sys.platform)

    def observe_linux_exit(self, process):
        # Exact owned child only. WNOWAIT observes but MUST NOT release the
        # leader identity before final group KILL. No Popen.poll/wait here.
        deadline = time.monotonic() + 2
        while True:
            self.assertIsNone(process.returncode)
            event = os.waitid(os.P_PID, process.pid,
                              os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if event is not None:
                self.assertEqual(event.si_pid, process.pid)
                self.assertEqual(event.si_code, os.CLD_EXITED)
                self.assertEqual(event.si_status, 0)
                self.assertIsNone(process.returncode)
                return
            remaining = deadline - time.monotonic()
            self.assertGreater(remaining, 0, 'owned leader exit observation timed out')
            time.sleep(min(0.01, remaining))  # bounded local observation, not CI polling

    def test_linux_nonreaping_observer_contract(self):
        # Branch/identity/options/timeout contracts on Darwin too; NOT evidence
        # of a real Linux waitid run. Real Linux coverage belongs to CI.
        process = SimpleNamespace(pid=12345, returncode=None)
        constants = {'P_PID': 1, 'WEXITED': 4, 'WNOHANG': 8,
                     'WNOWAIT': 16, 'CLD_EXITED': 1}
        good = SimpleNamespace(si_pid=process.pid, si_code=1, si_status=0)
        with patch.object(sys, 'platform', 'linux'), \
             patch.multiple(os, create=True, **constants), \
             patch.object(os, 'waitid', create=True) as observe, \
             patch.object(time, 'sleep'):
            observer = self.observe_exit(process)
            observe.assert_not_called()  # construction does not reap/observe
            observe.side_effect = [None, good]
            observer()
            self.assertEqual(observe.call_count, 2)
            observe.assert_called_with(1, process.pid, 4 | 8 | 16)
            for bad in (SimpleNamespace(si_pid=999, si_code=1, si_status=0),
                        SimpleNamespace(si_pid=process.pid, si_code=2, si_status=0),
                        SimpleNamespace(si_pid=process.pid, si_code=1, si_status=1)):
                with self.subTest(event=bad):
                    observe.side_effect = [bad]
                    with self.assertRaises(AssertionError):
                        observer()
            observe.side_effect = [None]
            with patch.object(time, 'monotonic', side_effect=[10, 12.1]):
                with self.assertRaisesRegex(AssertionError, 'timed out'):
                    observer()
            self.assertIsNone(process.returncode)

    def test_unsupported_exit_observer_fails_not_skips(self):
        with patch.object(sys, 'platform', 'unsupported-test-platform'):
            with self.assertRaisesRegex(AssertionError, 'unsupported'):
                self.observe_exit(SimpleNamespace(pid=12345, returncode=None))

    def exercise_tree(self, exited=False, broken_ipc=False):
        self.assertEqual(signal.getsignal(signal.SIGCHLD), signal.SIG_DFL)
        worker = self.make_worker('exit' if exited else 'tree')
        process = worker._process
        exit_observed = self.observe_exit(process) if exited else None
        witness = worker.connection.dup()
        witness.settimeout(3)
        self.addCleanup(witness.close)
        events = []
        real_killpg, real_wait = os.killpg, process.wait

        def group_signal(pid, sig):
            self.assertIsNone(process.returncode)
            self.assertEqual(pid, process.pid)
            real_killpg(pid, sig)
            events.append(sig)
            if sig == signal.SIGKILL:
                worker._test_final_kill = True

        def reap(timeout=None):
            self.assertEqual(events, [signal.SIGTERM, signal.SIGKILL])
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, i.WORKER_CLEANUP_SECONDS)
            result = real_wait(timeout=timeout)
            events.append('reaped')
            return result

        with patch.object(process, 'poll', side_effect=AssertionError('premature poll')), \
             patch.object(process, 'communicate', side_effect=AssertionError('premature communicate')), \
             patch.object(process, 'wait', side_effect=reap), \
             patch.object(i.os, 'killpg', side_effect=group_signal):
            worker.submit('synthetic')
            rows = worker.wait()
            self.assertEqual(len(rows), 3)
            leader, child, grandchild = rows
            self.assertEqual(leader['pid'], process.pid)
            self.assertEqual(leader['ppid'], os.getpid())
            self.assertEqual(child['ppid'], leader['pid'])
            self.assertEqual(grandchild['ppid'], child['pid'])
            self.assertEqual(len({r['pid'] for r in rows}), 3)
            for row in rows:
                self.assertEqual(row['sid'], process.pid)
                self.assertEqual(row['pgid'], process.pid)
            if exited:
                exit_observed()
                self.assertIsNone(process.returncode)
            start = time.monotonic()
            if broken_ipc:
                class BrokenClose:
                    def close(self):
                        raise OSError('synthetic close failure')
                original = worker.connection
                try:
                    worker.connection = BrokenClose()
                    with self.assertRaisesRegex(h.Rejected, 'cleanup UNKNOWN'):
                        worker.close()
                finally:
                    worker.connection = original
                    original.close()
            else:
                worker.close()
                worker.close()  # idempotent: no post-reap signal
            self.assertLess(time.monotonic() - start, i.WORKER_CLEANUP_SECONDS + 0.5)
            self.assertEqual(events, [signal.SIGTERM, signal.SIGKILL, 'reaped'])
            self.assertIsNotNone(process.returncode)
            self.assertEqual(witness.recv(1), b'')
            if broken_ipc:
                with self.assertRaisesRegex(h.Rejected, 'cleanup UNKNOWN'):
                    worker.close()

    def test_child_grandchild_and_term_resistance(self):
        self.exercise_tree()

    def test_exited_unreaped_leader_still_contains_descendants(self):
        self.exercise_tree(exited=True)

    def test_ipc_close_failure_does_not_skip_group_cleanup(self):
        self.exercise_tree(broken_ipc=True)

    def test_unsafe_sigchld_rejected_before_spawn(self):
        for policy in (signal.SIG_IGN, lambda *_: None):
            with self.subTest(policy=policy), \
                 patch.object(i.signal, 'getsignal', return_value=policy), \
                 patch.object(i.subprocess, 'Popen') as spawn, \
                 patch.object(i.socket, 'socketpair') as pair:
                with self.assertRaisesRegex(h.Rejected, 'SIGCHLD'):
                    i.Worker({})
                spawn.assert_not_called()
                pair.assert_not_called()

    def test_known_reaped_leader_never_signalled(self):
        worker = self.make_worker('ok', tree=False)
        # Deliberate ownership violation in a fixture with NO descendants.
        worker._process.kill()
        worker._process.wait(timeout=2)
        with patch.object(i.os, 'killpg') as group_signal, \
             patch.object(worker._process, 'wait') as wait:
            with self.assertRaisesRegex(h.Rejected, 'cleanup UNKNOWN'):
                worker.close()
            with self.assertRaisesRegex(h.Rejected, 'cleanup UNKNOWN'):
                worker.close()
            group_signal.assert_not_called()
            wait.assert_not_called()

    def test_changed_sigchld_policy_never_signalled(self):
        worker = self.make_worker('hang', tree=False)
        with patch.object(i.signal, 'getsignal', return_value=signal.SIG_IGN), \
             patch.object(i.os, 'killpg') as group_signal, \
             patch.object(worker._process, 'wait') as wait:
            with self.assertRaisesRegex(h.Rejected, 'cleanup UNKNOWN'):
                worker.close()
            group_signal.assert_not_called()
            wait.assert_not_called()

    def test_identity_failure_neither_signals_nor_waits(self):
        worker = self.make_worker('hang', tree=False)
        with patch.object(worker, '_require_signal_ownership', side_effect=h.Rejected('lost')), \
             patch.object(i.os, 'killpg') as group_signal, \
             patch.object(worker._process, 'wait') as wait:
            with self.assertRaisesRegex(h.Rejected, 'cleanup UNKNOWN'):
                worker.close()
            group_signal.assert_not_called()
            wait.assert_not_called()
        self.assertIsNone(worker._process.returncode)

    def test_serialization_failure_owns_no_resources(self):
        with patch.object(i.subprocess, 'Popen') as spawn, \
             patch.object(i.socket, 'socketpair') as pair:
            with self.assertRaises(TypeError):
                i.Worker({'not_json': object()})
            spawn.assert_not_called()
            pair.assert_not_called()

    def test_spawn_failure_closes_both_owned_sockets(self):
        endpoints = socket.socketpair()
        try:
            with patch.object(i.socket, 'socketpair', return_value=endpoints), \
                 patch.object(i.subprocess, 'Popen', side_effect=OSError('synthetic spawn failure')):
                with self.assertRaisesRegex(OSError, 'synthetic spawn failure'):
                    i.Worker({})
            self.assertEqual([endpoint.fileno() for endpoint in endpoints], [-1, -1])
        finally:
            for endpoint in endpoints:
                endpoint.close()

    def test_signal_failure_still_reaps_and_reports_unknown(self):
        worker = self.make_worker('ok', tree=False)
        worker.submit('unit')
        self.assertTrue(worker.wait())
        real_killpg = os.killpg
        def signal_failure(pid, sig):
            if sig == signal.SIGTERM:
                raise PermissionError('synthetic denied TERM')
            real_killpg(pid, sig)
            worker._test_final_kill = True
        with patch.object(i.os, 'killpg', side_effect=signal_failure):
            before = time.monotonic()
            with self.assertRaisesRegex(h.Rejected, 'cleanup UNKNOWN'):
                worker.close()
            self.assertLess(time.monotonic() - before, i.WORKER_CLEANUP_SECONDS + 0.5)
        self.assertIsNotNone(worker._process.returncode)

    def test_entrypoints_block_before_any_access(self):
        forbidden = AssertionError('blocked entrypoint attempted access')
        with patch.object(i, 'guard', side_effect=forbidden), \
             patch.object(i, 'Worker', side_effect=forbidden), \
             patch.object(i.s, 'read_private', side_effect=forbidden), \
             patch.object(i.s, 'private_dir', side_effect=forbidden), \
             patch.object(i.h, 'open_plex_stream', side_effect=forbidden), \
             patch('builtins.open', side_effect=forbidden), \
             patch.object(i.socket, 'socket', side_effect=forbidden), \
             patch.object(i.subprocess, 'Popen', side_effect=forbidden):
            with self.assertRaisesRegex(h.Rejected, 'HOLD'):
                i.run(None, None, None)
            with self.assertRaisesRegex(SystemExit, 'BLOCKED'):
                i.main()
            with self.assertRaisesRegex(SystemExit, 'BLOCKED'):
                h.main()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--ipc-worker':
        connection = socket.socket(fileno=int(sys.argv[2]))
        ipc_only(connection, i.worker_binding(connection))
    elif len(sys.argv) == 3 and sys.argv[1] == '--tree-leader':
        tree_leader(socket.socket(fileno=int(sys.argv[2])))
    elif len(sys.argv) == 4 and sys.argv[1] in ('--tree-child', '--tree-grandchild'):
        tree_descendant(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    else:
        unittest.main()
