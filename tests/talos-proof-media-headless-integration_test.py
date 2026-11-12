#!/usr/bin/env python3
"""Offline contracts/owned IPC only. NO mocked application acceptance claim."""
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
i = importlib.import_module('talos-proof-media-headless-integration')
h = i.h


def ipc_only(connection, binding):
    """New local IPC bytes, no app API or state access."""
    try:
        connection.recv(4096)
        if binding['case'] == 'partial':
            connection.sendall(b'["ok",')
            time.sleep(5)
        elif binding['case'] == 'hang':
            time.sleep(5)
        else:
            connection.sendall(b'["ok", true]\n')
            time.sleep(5)
    finally:
        connection.close()


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
        self.assertIsNotNone(worker.process.poll())

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
        self.assertIsNotNone(worker.process.poll())

    def test_hung_worker_deadline_and_no_orphan(self):
        worker = self.worker('hang')
        worker.submit('unit')
        worker.pending = ('unit', time.monotonic() - 1)
        with self.assertRaises(h.Rejected):
            worker.wait()
        worker.close()
        self.assertIsNotNone(worker.process.poll())

    def test_cli_blocked_without_state_or_network(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/talos-proof-media-headless-integration.py')],
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'unsupported', result.stderr)
        self.assertIn(b'BLOCKED', result.stderr)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--ipc-worker':
        connection = socket.socket(fileno=int(sys.argv[2]))
        ipc_only(connection, i.worker_binding(connection))
    else:
        unittest.main()
