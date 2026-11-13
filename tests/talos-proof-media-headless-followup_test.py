#!/usr/bin/env python3
"""New synthetic loopback adapter bytes only; no Gateway/application evidence."""
import copy
import io
import os
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import importlib
i = importlib.import_module('talos-proof-media-headless-integration')
h = i.h
spec = importlib.util.spec_from_file_location('prepared_proxy', ROOT / 'kubernetes/apps/media/plex/plex-unclaimed-proxy.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class Framing(unittest.TestCase):
    def test_reject_ambiguous_upstream_before_forwarding(self):
        for headers in [[('Content-Length', '3'), ('Content-Length', '3')],
                        [('Content-Length', '3, 3')], [('Content-Length', '-1')],
                        [('Content-Length', '+3')], [('Content-Length', ' 3')],
                        [('Transfer-Encoding', 'chunked')],
                        [('Transfer-Encoding', 'identity'), ('Content-Length', '3')],
                        [('Connection', 'Content-Length'), ('Content-Length', '3')]]:
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                proxy.framing(headers)

    def test_actual_adapter_preserves_valid_length_and_rejects_conflicts(self):
        class Upstream(BaseHTTPRequestHandler):
            fields = [('Content-Length', '3')]
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200)
                for k, v in self.fields: self.send_header(k, v)
                self.end_headers()
                self.wfile.write(b'NEW')
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        adapter = ThreadingHTTPServer(('127.0.0.1', 0), proxy.Handler)
        adapter.access_key, adapter.password = 'new-test-key', 'new-test-password'
        threads = [threading.Thread(target=s.serve_forever) for s in (upstream, adapter)]
        for t in threads: t.start()
        original = http.client.HTTPConnection
        def connection(host, port, **kwargs):
            return original(host, upstream.server_port if port == 32400 else port, **kwargs)
        try:
            with patch.object(proxy.http.client, 'HTTPConnection', connection):
                c = original('127.0.0.1', adapter.server_port, timeout=2)
                c.request('GET', '/unit', headers={'X-Plex-Token': 'new-test-key'})
                r = c.getresponse()
                self.assertEqual(r.getheaders().count(('Content-Length', '3')), 1)
                self.assertEqual(r.read(), b'NEW')
                c.close()
                Upstream.fields = [('Content-Length', '3'), ('Transfer-Encoding', 'chunked')]
                c = original('127.0.0.1', adapter.server_port, timeout=2)
                c.request('GET', '/unit', headers={'X-Plex-Token': 'new-test-key'})
                with self.assertRaises(http.client.RemoteDisconnected): c.getresponse()
                c.close()
        finally:
            for server in (adapter, upstream): server.shutdown(); server.server_close()
            for t in threads: t.join(timeout=2); self.assertFalse(t.is_alive())


class Backlog(unittest.TestCase):
    @staticmethod
    def block(n):
        return f'frame={n}\nout_time_us={n * 100000}\nprogress=continue\n'.encode()

    def test_actual_pipe_backlog_and_partial_parser_boundary(self):
        read, write = os.pipe()
        with os.fdopen(read, 'rb', buffering=0) as reader, os.fdopen(write, 'wb', buffering=0) as writer:
            os.set_blocking(reader.fileno(), False)
            parser = h.ProgressParser()
            parser.feed(b'frame=1\nout_time_')
            backlog = b'us=100000\nprogress=continue\n' + self.block(2) + b'frame=3\n'
            writer.write(backlog)
            log = io.BytesIO()
            self.assertEqual(h.progress_barrier(reader, parser, log, 0), len(backlog))
            self.assertEqual(log.getvalue(), backlog)
            with self.assertRaises(BlockingIOError): os.read(reader.fileno(), 1)
            # Rest of a potentially pre-boundary producer block cannot count.
            writer.write(b'out_time_us=300000\nprogress=continue\n' + self.block(4))
            reports = parser.feed(os.read(reader.fileno(), h.CHUNK))
            self.assertEqual([(p.frame, p.epoch) for p in reports], [(4, 1)])

    def test_partial_block_is_quarantined_across_boundary(self):
        parser = h.ProgressParser()
        parser.feed(b'frame=1\nout_time_')
        parser.barrier()
        self.assertEqual(parser.feed(b'us=100000\nprogress=continue\n'), [])
        reports = parser.feed(self.block(2))
        self.assertEqual([(p.frame, p.epoch) for p in reports], [(2, 1)])

    def test_two_old_records_in_single_delayed_batch_cannot_prove_concurrency(self):
        worker = type('Worker', (), {'poll': lambda s: None})()
        pump = i.Pump(worker, h.Identity('c', 's', '12'), [], float('inf'))
        pump.life.stage = 'playing'
        pump.process = type('Process', (), {'poll': lambda s: None})()
        pump.ready_activity = [{'rating_key': '12', 'machine_id': 'c', 'state': 'playing'}]
        pump.wait_watermark, pump.required_epoch = True, 1
        parser = h.ProgressParser()
        # Records parsed before drain belong to old epoch, regardless delivery order.
        for report in parser.feed(self.block(1) + self.block(2)):
            pump.observe(report, True, True)
        self.assertEqual(pump.life.stage, 'playing')
        parser.barrier()
        parser.feed(self.block(3))  # quarantine
        for report in parser.feed(self.block(4) + self.block(5)):
            pump.observe(report, True, True)
        self.assertEqual(pump.life.stage, 'activity')
        for report in parser.feed(self.block(6)):
            pump.observe(report, True, True)
        self.assertEqual(pump.life.stage, 'concurrent')  # parser contract ONLY


class Aggregate(unittest.TestCase):
    def setUp(self):
        self.controllers, self.pods = [], []
        for name, limit in i.LIMITS.items():
            metadata = {'name': name, 'namespace': 'proof-' + name}
            spec = {'containers': [{'name': name, 'resources': {'limits': {'cpu': '1', 'memory': f'{limit}Mi'}}}]}
            self.controllers.append({'kind': 'Deployment', 'metadata': metadata,
                'spec': {'replicas': 1, 'strategy': {'type': 'Recreate'}, 'template': {'spec': spec}}})
            self.pods.append({'metadata': {**metadata, 'ownerReferences': [{'controller': True}]}, 'spec': spec})

    def test_exact_snapshot_and_duplicate_terminal_or_terminating_rejected(self):
        i.aggregate_admission(self.controllers, self.pods)
        for extra in ({}, {'deletionTimestamp': 'now'}, {'phase': 'Succeeded'}):
            pod = copy.deepcopy(self.pods[0]); pod['metadata'].update(extra)
            with self.assertRaises(h.Rejected):
                i.aggregate_admission(self.controllers, self.pods + [pod])

    def test_replicas_surge_and_actual_448_256_not_interchangeable(self):
        for mutation in ({'replicas': 2}, {'strategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxSurge': 1}}}):
            controllers = copy.deepcopy(self.controllers)
            controllers[0]['spec'].update(mutation)
            with self.assertRaises(h.Rejected): i.aggregate_admission(controllers, self.pods)
        self.pods[0]['spec']['containers'][0]['resources']['limits']['memory'] = '448Mi'
        self.pods[1]['spec']['containers'][0]['resources']['limits']['memory'] = '256Mi'
        with self.assertRaises(h.Rejected): i.aggregate_admission(self.controllers, self.pods)

    def test_run_holds_before_any_guard_state_or_network(self):
        with patch.object(i, 'guard', side_effect=AssertionError('must not access')):
            with self.assertRaisesRegex(h.Rejected, 'HOLD'): i.run({}, None, None)


if __name__ == '__main__': unittest.main()
