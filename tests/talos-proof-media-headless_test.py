#!/usr/bin/env python3
"""Offline unit contracts only; mocks are NOT runtime application evidence."""
import hashlib
from email.message import Message
import io
import os
import tempfile
import threading
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import importlib
h = importlib.import_module('talos-proof-media-headless')


class StreamTests(unittest.TestCase):
    def test_exact_and_corruption(self):
        data = b'new synthetic bytes'
        check = h.StreamCheck(len(data), hashlib.sha256(data).hexdigest())
        check.feed(data)
        check.finish()
        for bad in (b'wrong synthetic!!!!', data[:-1]):
            check = h.StreamCheck(len(data), hashlib.sha256(data).hexdigest())
            with self.assertRaises(h.Rejected):
                check.feed(bad)
                check.finish()

    def test_bounds(self):
        check = h.StreamCheck(2, hashlib.sha256(b'ab').hexdigest())
        with self.assertRaises(h.Rejected):
            check.feed(b'abc')
        with self.assertRaises(h.Rejected):
            h.StreamCheck(h.FIXTURE_BYTES + 1)
        with self.assertRaises(h.Rejected):
            h.StreamCheck().feed(b'x' * (h.CHUNK + 1))

    def test_partial_progress_nonadvance_and_regression(self):
        parser = h.ProgressParser()
        self.assertEqual(parser.feed(b'frame=1\nout_time_us='), [])
        self.assertEqual(parser.feed(b'1000\nprogress=continue\n'), [h.Progress(1, 1000)])
        self.assertEqual(parser.feed(b'frame=1\nout_time_us=1000\nprogress=continue\n'), [])
        with self.assertRaises(h.Rejected):
            parser.feed(b'frame=0\nout_time_us=900\nprogress=end\n')

    def test_missing_fields_and_output_bound(self):
        for payload in (b'progress=end\n', b'x' * (h.MAX_OUTPUT + 1)):
            with self.assertRaises(h.Rejected):
                h.ProgressParser().feed(payload)

    def test_command_is_fixed_decode_not_copy(self):
        with patch.object(Path, 'is_file', return_value=True), patch.object(h.os, 'access', return_value=True):
            cmd = h.command('/nix/store/' + 'a' * 32 + '-ffmpeg/bin/ffmpeg')
        self.assertIn('wrapped_avframe', cmd)
        self.assertEqual(cmd[cmd.index('-protocol_whitelist') + 1], 'pipe')
        self.assertEqual(cmd[cmd.index('-i') + 1], 'pipe:0')
        self.assertNotIn('copy', cmd)
        self.assertNotIn('lavfi', cmd)
        for forbidden in ('https://example/ffmpeg', '/bin/ffmpeg', '/tmp/ffmpeg',
                          '/nix/store/../../tmp/bin/ffmpeg'):
            with self.assertRaises(h.Rejected):
                h.command(forbidden)

    def test_cli_fail_closed_no_state_access(self):
        result = subprocess.run([sys.executable, '-I', '-S', str(ROOT / 'scripts/talos-proof-media-headless.py')],
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'BLOCKED', result.stderr)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.identity = h.Identity('test-client', 'test-session', '123')
        self.life = h.Lifecycle(self.identity, ['old'])
        self.rows = [{'rating_key': '123', 'machine_id': 'test-client', 'state': 'playing'}]
        self.history = [{'row_id': 'new', 'rating_key': '123', 'machine_id': 'test-client', 'duration': 3}]

    def playing(self):
        self.life.advanced(h.Progress(1, 1000), True, False)
        self.life.advanced(h.Progress(2, 2000), True, True)
        self.life.playing(self.identity, True, True)

    def concurrent(self):
        self.playing()
        self.life.activity(self.rows, True, h.Progress(3, 3000))
        self.life.advanced(h.Progress(4, 4000), True, True)

    def test_complete_ordered_offline_contract(self):
        self.concurrent()
        self.life.stopped(self.identity, False, 0, True)
        self.life.history(self.history)
        self.assertEqual(self.life.stage, 'complete')

    def test_nonadvance_postexit_and_unverified(self):
        for progress, alive in ((h.Progress(0, 0), True), (h.Progress(2, 2000), False)):
            with self.assertRaises(h.Rejected):
                self.life.advanced(progress, alive, True)
        self.life.advanced(h.Progress(1, 1000), True, False)
        self.life.advanced(h.Progress(2, 2000), True, False)
        with self.assertRaises(h.Rejected):
            self.life.playing(self.identity, True, False)

    def test_identity_mismatch(self):
        self.life.advanced(h.Progress(1, 1000), True, True)
        self.life.advanced(h.Progress(2, 2000), True, True)
        with self.assertRaises(h.Rejected):
            self.life.playing(h.Identity('other', 'test-session', '123'), True, True)
        self.playing_reset_for_activity()
        with self.assertRaises(h.Rejected):
            self.life.activity([dict(self.rows[0], machine_id='other')], True, h.Progress(3, 3000))

    def playing_reset_for_activity(self):
        self.life = h.Lifecycle(self.identity, ['old'])
        self.playing()

    def test_activity_requires_later_live_frames(self):
        self.playing()
        self.life.activity(self.rows, True, h.Progress(3, 3000))
        with self.assertRaises(h.Rejected):
            self.life.advanced(h.Progress(3, 3000), True, True)
        with self.assertRaises(h.Rejected):
            self.life.advanced(h.Progress(4, 4000), False, True)
        with self.assertRaises(h.Rejected):
            self.life.stopped(self.identity, False, 0, True)

    def test_activity_postexit(self):
        self.playing()
        with self.assertRaises(h.Rejected):
            self.life.activity(self.rows, False, h.Progress(3, 3000))

    def test_stop_requires_success_and_native_stop(self):
        self.concurrent()
        for alive, rc, native in ((True, 0, True), (False, 1, True), (False, 0, False)):
            with self.assertRaises(h.Rejected):
                self.life.stopped(self.identity, alive, rc, native)

    def test_stale_duplicate_zero_wrong_history(self):
        self.concurrent()
        self.life.stopped(self.identity, False, 0, True)
        for rows in ([], self.history * 2, [dict(self.history[0], row_id='old')],
                     [dict(self.history[0], duration=0)], [dict(self.history[0], machine_id='other')]):
            with self.assertRaises(h.Rejected):
                self.life.history(rows)


class ProcessContractTests(unittest.TestCase):
    """Owned pipe/process doubles are unit tests, not decoder/runtime evidence."""
    def fake_process(self, returncode=None):
        class Process:
            pid = 999999999
            def __init__(self):
                self.returncode = returncode
                self.extras = []
                read, write = os.pipe()
                self.stdin = os.fdopen(write, 'wb', buffering=0)
                self.extras.append(read)
                for name in ('stdout', 'stderr'):
                    read, write = os.pipe()
                    setattr(self, name, os.fdopen(read, 'rb', buffering=0))
                    self.extras.append(write)
            def poll(self):
                return self.returncode
            def terminate(self):
                self.returncode = -15
            def kill(self):
                self.returncode = -9
            def wait(self, timeout):
                return self.returncode
        process = Process()
        self.addCleanup(lambda: [os.close(fd) for fd in process.extras])
        return process

    def run_double(self, process, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = io.BytesIO(b'x')
            with patch.object(h, 'command', return_value=['unit-only']), \
                 patch.object(h.subprocess, 'Popen', return_value=process), \
                 patch.object(h.MemoryWatch, 'check'):
                try:
                    h.decode(source, 'unit-only', root, size=1,
                             digest=hashlib.sha256(b'x').hexdigest(), **kwargs)
                finally:
                    self.assertTrue(source.closed)
                    self.assertFalse(list(root.rglob('home-*')))
                    self.assertTrue(process.stdin.closed)
                    self.assertTrue(process.stdout.closed)
                    self.assertTrue(process.stderr.closed)

    def test_cancellation_terminates_only_owned_process(self):
        process = self.fake_process()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(h.Rejected, 'cancelled'):
            self.run_double(process, cancel=cancel)
        self.assertEqual(process.returncode, -15)

    def test_decoder_postexit_is_rejected(self):
        process = self.fake_process(returncode=1)
        with self.assertRaisesRegex(h.Rejected, 'exited before'):
            self.run_double(process)

    def test_walltime_cleanup(self):
        process = self.fake_process()
        with self.assertRaisesRegex(h.Rejected, 'wall-time'):
            self.run_double(process, seconds=0.05)
        self.assertEqual(process.returncode, -15)


class HTTPTests(unittest.TestCase):
    def test_plain_or_wrong_api_rejected_without_network(self):
        with self.assertRaises(h.Rejected):
            h.open_plex_stream(object(), '/library/parts/1/2/file.mp4', h.Identity('c', 's', '1'))

    def test_exact_api_request_identity_and_response(self):
        api_type = importlib.import_module('talos-proof-media-http').API
        api = object.__new__(api_type)  # no CA/state/network access in this unit test
        api.service, api.allow_http, api.ca = 'plex', False, 'unit-only-ca'
        api.base, api.headers = 'https://plex.proof.invalid:18443', {'X-Plex-Token': 'unit-only'}
        path = '/library/parts/1/2/file.mp4'
        class Response(io.BytesIO):
            status = 200
            headers = Message()
            headers['Content-Length'] = str(h.FIXTURE_BYTES)
            def geturl(self):
                return api.base + path
        response = Response()
        class Opener:
            def open(self, request, timeout):
                self.request = request
                return response
        api.opener = Opener()
        identity = h.Identity('c', 's', '1')
        self.assertIs(h.open_plex_stream(api, path, identity), response)
        self.assertEqual(api.opener.request.get_header('X-plex-client-identifier'), 'c')
        self.assertEqual(api.opener.request.get_header('X-plex-session-identifier'), 's')
        api.headers.update({'X-Plex-Client-Identifier': 'other'})
        with self.assertRaises(h.Rejected):
            h.open_plex_stream(api, path, identity)
        api.headers = {}
        for bad in ('https://other/', '//other/file.mp4', path + '?token=x'):
            with self.assertRaises(h.Rejected):
                h.open_plex_stream(api, bad, identity)
        response.status = 206
        with self.assertRaises(h.Rejected):
            h.open_plex_stream(api, path, identity)
        self.assertTrue(response.closed)


if __name__ == '__main__':
    unittest.main()
