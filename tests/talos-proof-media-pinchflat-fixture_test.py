#!/usr/bin/env python3
"""Real loopback socket protocol tests; no codecs, yt-dlp or Pinchflat claim."""
import contextlib
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/talos-proof-media-pinchflat-fixture.py"
SPEC = importlib.util.spec_from_file_location("pinchflat_fixture", SCRIPT)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)
# Deliberately NOT playable media. Tests establish HTTP protocol only.
MEDIA = b"\x00\x00\x00\x18ftypisom" + bytes(range(256)) * 4


@contextlib.contextmanager
def running(**kwargs):
    with fixture.Fixture(MEDIA, **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=3)
            if thread.is_alive():
                raise AssertionError("server did not stop")


def request(server, path, method="GET", headers=None):
    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    try:
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        client.close()


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        # Enforced on every test: actual sockets may connect ONLY to this loopback
        # origin. No proxies, environment/config handling, DNS or upstream calls.
        self.allowed_port = None
        original = socket.socket.connect

        def guarded(sock, address):
            if address != ("127.0.0.1", self.allowed_port):
                raise AssertionError(f"non-fixture socket forbidden: {address!r}")
            return original(sock, address)

        self.guard = patch.object(socket.socket, "connect", guarded)
        self.guard.start()
        self.addCleanup(self.guard.stop)

    @contextlib.contextmanager
    def origin(self, **kwargs):
        with running(**kwargs) as server:
            self.allowed_port = server.server_port
            yield server

    def test_download_phase_coverage_does_not_reuse_metadata_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            phase=Path(temp)/'phase';evidence=Path(temp)/'latest.json'
            with self.origin(phase_file=phase) as server:
                request(server,'/media/proof-001.mp4')
                self.assertEqual(server.snapshot()['phases']['download']['media_unique_bytes'],0)
                phase.write_text('download')
                server.publish(evidence)
                baseline=json.loads(evidence.read_text())
                self.assertEqual(baseline['phase'],'download')
                self.assertEqual(baseline['phases']['metadata']['media_unique_bytes'],len(MEDIA))
                self.assertEqual(baseline['phases']['download']['media_body_bytes'],0)
                request(server,'/media/proof-001.mp4')
                server.publish(evidence)
                after=json.loads(evidence.read_text())
                self.assertEqual(after['instance_id'],baseline['instance_id'])
                self.assertEqual(after['phases']['download']['media_unique_bytes'],len(MEDIA))
                self.assertEqual(after['phases']['metadata'],baseline['phases']['metadata'])
                phase.write_text('metadata')
                with self.assertRaises(ValueError):server.update_phase()

    def test_feed_is_single_collection_pointing_to_html_not_mp4(self):
        with self.origin() as server:
            status, headers, body = request(server, "/feed.xml")
            self.assertEqual(status, 200)
            self.assertEqual(int(headers["Content-Length"]), len(body))
            root = ET.fromstring(body)
            self.assertEqual(root.findtext("channel/title"), "Offline synthetic proof collection")
            self.assertEqual(root.findtext("channel/link"), server.origin + "/feed.xml")
            items = root.findall("channel/item")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].findtext("link"), server.origin + "/video/proof-001")
            self.assertIsNone(items[0].find("enclosure"))

    def test_html_independently_contains_metadata_and_video(self):
        with self.origin() as server:
            first = request(server, "/video/proof-001")[2]
            second = request(server, "/video/proof-001", headers={"Host": "evil.example"})[2]
            self.assertEqual(first, second)
            metadata = json.loads(re.search(rb'<script type="application/ld\+json">(.*?)</script>', first)[1])
            self.assertEqual(metadata["identifier"], "proof-001")
            self.assertEqual(metadata["name"], fixture.TITLE)
            self.assertEqual(metadata["uploadDate"], fixture.UPLOAD_DATE)
            self.assertEqual(metadata["duration"], "PT12S")
            self.assertEqual(metadata["contentUrl"], server.origin + "/media/proof-001.mp4")
            self.assertIn(b"<video controls>", first)
            self.assertNotIn(b"evil.example", first)
            # schema.org is a JSON-LD vocabulary identifier, not an import/script.
            self.assertNotIn(b'<script src=', first)

    def test_head_has_same_headers_no_body_or_coverage(self):
        with self.origin() as server:
            for path in fixture.PATHS:
                status, headers, body = request(server, path, "HEAD")
                self.assertEqual(status, 200)
                self.assertEqual(body, b"")
                self.assertEqual(int(headers["Content-Length"]), len(server.resources[path][1]))
            self.assertEqual(server.snapshot()["sent_body_bytes"], 0)
            self.assertEqual(server.snapshot()["media_unique_bytes"], 0)

    def test_full_media_hash_and_coverage(self):
        with self.origin() as server:
            status, headers, body = request(server, fixture.PATHS[2])
            self.assertEqual(status, 200)
            self.assertEqual(body, MEDIA)
            self.assertEqual(headers["Content-Type"], "video/mp4")
            snapshot = server.snapshot()
            self.assertEqual(snapshot["media_unique_bytes"], len(MEDIA))
            self.assertEqual(snapshot["media_sha256"], hashlib.sha256(body).hexdigest())

    def test_ranges_reconstruct_media_and_count_unique_not_duplicates(self):
        with self.origin() as server:
            chunks = []
            for value in ("bytes=0-99", "bytes=100-"):
                status, headers, body = request(server, fixture.PATHS[2], headers={"Range": value})
                self.assertEqual(status, 206)
                self.assertIn("Content-Range", headers)
                self.assertEqual(int(headers["Content-Length"]), len(body))
                chunks.append(body)
            self.assertEqual(b"".join(chunks), MEDIA)
            self.assertEqual(request(server, fixture.PATHS[2], headers={"Range": "bytes=-7"})[2], MEDIA[-7:])
            self.assertEqual(server.snapshot()["media_unique_bytes"], len(MEDIA))
            self.assertEqual(server.snapshot()["media_body_bytes"], len(MEDIA) + 7)

    def test_delayed_postwrite_commit_blocks_snapshot_and_publication(self):
        # Force the precise CI interleaving: duplicate body has reached client,
        # but the seven-byte handler counter commit has NOT happened yet.
        entered, release = threading.Event(), threading.Event()
        original = fixture.Handler.commit_media
        def delayed(handler, start, end, length):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release delayed counter commit')
            original(handler, start, end, length)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);evidence=root/'latest.json';nonce=root/'latest.json.request'
            with self.origin(snapshot_request_file=nonce) as server:
                request(server,fixture.PATHS[2])
                nonce.write_text('a'*32);server.publish(evidence)
                self.assertEqual(json.loads(evidence.read_text())['media_body_bytes'],len(MEDIA))
                with patch.object(fixture.Handler,'commit_media',delayed):
                    try:
                        self.assertEqual(request(server,fixture.PATHS[2],headers={'Range':'bytes=-7'})[2],MEDIA[-7:])
                        self.assertTrue(entered.wait(3))
                        # Deliberately inspect raw state to reproduce old failure.
                        self.assertEqual(server.media_bytes,len(MEDIA))
                        nonce.write_text('b'*32)
                        with self.assertRaises(TimeoutError):server.snapshot(timeout=.02)
                        with self.assertRaises(TimeoutError):server.publish(evidence,timeout=.02)
                        stale=json.loads(evidence.read_text())
                        self.assertEqual(stale['snapshot_token'],'a'*32)
                        self.assertEqual(stale['media_body_bytes'],len(MEDIA))
                    finally:
                        release.set()
                    server.publish(evidence)
                    after=json.loads(evidence.read_text())
                    self.assertTrue(after['settled'])
                    self.assertEqual(after['snapshot_token'],'b'*32)
                    self.assertEqual(after['media_body_bytes'],len(MEDIA)+7)
                    self.assertEqual(after['media_unique_bytes'],len(MEDIA))

    def test_provider_reader_requires_fresh_persisted_nonce_and_phase(self):
        # Exercise the ACTUAL sidecar reader locally, no proof runtime calls.
        sys.path.insert(0,str(SCRIPT.parent))
        provider=__import__('talos-proof-media-pinchflat-provider')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);evidence=root/'latest.json';nonce=root/'latest.json.request'
            phase=root/'phase'
            with self.origin(phase_file=phase,snapshot_request_file=nonce) as server:
                request(server,fixture.PATHS[2]);server.publish(evidence)
                old=json.loads(evidence.read_text())
                child=subprocess.Popen([sys.executable,'-c',provider.STATS_READER,str(root),'download'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    deadline=time.monotonic()+3
                    while not nonce.exists():
                        if time.monotonic()>=deadline:raise AssertionError('snapshot nonce was not requested')
                        threading.Event().wait(.01)  # bounded request-file synchronization
                    token=nonce.read_text()
                    self.assertNotEqual(token,old['snapshot_token'])
                    # Still only the old publication: not enough for this reader.
                    self.assertIsNone(child.poll())
                    self.assertEqual(json.loads(evidence.read_text()),old)
                    server.publish(evidence)
                    out,err=child.communicate(timeout=3)
                    self.assertEqual(child.returncode,0,err.decode())
                    current=json.loads(out)
                    self.assertEqual(current,json.loads(evidence.read_text()))
                    self.assertEqual(current['snapshot_token'],token)
                    self.assertEqual(current['phase'],'download')
                    self.assertEqual(current['phases']['metadata']['media_body_bytes'],len(MEDIA))
                    self.assertEqual(current['phases']['download']['media_body_bytes'],0)
                    self.assertEqual(evidence.stat().st_mode & 0o777,0o600)
                    self.assertEqual(nonce.stat().st_mode & 0o777,0o600)
                finally:
                    if child.poll() is None:child.kill()
                    child.communicate(timeout=3)

    def test_failed_body_write_reserves_budget_but_never_counts_delivery(self):
        with self.origin(max_bytes=len(MEDIA)) as server:
            with patch.object(fixture.Handler,'write_body',side_effect=BrokenPipeError):
                with self.assertRaises(http.client.IncompleteRead):
                    request(server,fixture.PATHS[2])
            snapshot=server.snapshot()
            self.assertEqual(snapshot['reserved_body_bytes'],len(MEDIA))
            self.assertEqual(snapshot['sent_body_bytes'],0)
            self.assertEqual(snapshot['media_body_bytes'],0)
            self.assertEqual(snapshot['media_unique_bytes'],0)
            self.assertEqual(request(server,fixture.PATHS[2])[0],429)

    def test_invalid_ranges_fail_closed(self):
        with self.origin() as server:
            for value in ("bytes=", "bytes=-0", "bytes=5-3", "bytes=99999-", "bytes=0-1,3-4", "items=1-2", "bytes=" + "9" * 90 + "-"):
                with self.subTest(value=value):
                    status, headers, body = request(server, fixture.PATHS[2], headers={"Range": value})
                    self.assertEqual(status, 416)
                    self.assertEqual(headers["Content-Range"], f"bytes */{len(MEDIA)}")
                    self.assertEqual(body, b"")
            self.assertEqual(server.snapshot()["media_unique_bytes"], 0)

    def test_unknown_paths_query_forwarding_and_traversal_fail(self):
        with self.origin() as server:
            for path in ("/", "/favicon.ico", "/../etc/passwd", "/%2e%2e/etc/passwd", "/feed.xml?url=http://example.com", "http://example.com/feed.xml", "/media/proof-001.mp4/extra"):
                self.assertEqual(request(server, path)[0], 404)
            self.assertEqual(server.snapshot()["rejected"], 7)
            self.assertEqual(len(server.routes), 3)

    def test_budgets(self):
        with self.origin(max_requests=2) as server:
            self.assertEqual(request(server, "/missing")[0], 404)
            self.assertEqual(request(server, "/feed.xml", "POST")[0], 501)
            self.assertEqual(request(server, "/feed.xml")[0], 429)
            self.assertEqual(server.snapshot()["requests"], 2)
        with self.origin(max_bytes=len(MEDIA)) as server:
            self.assertEqual(request(server, fixture.PATHS[2])[0], 200)
            self.assertEqual(request(server, fixture.PATHS[2])[0], 429)
            self.assertEqual(server.snapshot()["sent_body_bytes"], len(MEDIA))

    def test_request_bodies_rejected(self):
        with self.origin() as server:
            for headers in ({"Content-Length": "1"}, {"Transfer-Encoding": "chunked"}):
                self.assertEqual(request(server, "/feed.xml", headers=headers)[0], 400)

    def test_duplicate_ranges_rejected_over_real_socket(self):
        with self.origin() as server:
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                client.putrequest("GET", fixture.PATHS[2])
                client.putheader("Range", "bytes=0-1")
                client.putheader("Range", "bytes=3-4")
                client.endheaders()
                response = client.getresponse()
                self.assertEqual(response.status, 416)
                self.assertEqual(response.read(), b"")
            finally:
                client.close()

    def test_socket_guard_blocks_upstream(self):
        with socket.socket() as sock:
            with self.assertRaises(AssertionError):
                sock.connect(("192.0.2.1", 80))


class InputTests(unittest.TestCase):
    def test_snapshot_is_immutable_and_input_checks_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.mp4"
            path.write_bytes(MEDIA)
            snapshot = fixture.load_media(path)
            path.write_bytes(b"not media")
            self.assertEqual(snapshot, MEDIA)
            with self.assertRaises(ValueError):
                fixture.load_media(path)
            path.write_bytes(b"x" * (fixture.MAX_MEDIA + 1))
            with self.assertRaises(ValueError):
                fixture.load_media(path)
            link = Path(directory) / "link.mp4"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                fixture.load_media(link)
            link.unlink()
            os.link(path, link)
            with self.assertRaises(ValueError):
                fixture.load_media(link)
            with self.assertRaises((ValueError, OSError)):
                fixture.load_media(directory)

    def test_invalid_server_limits(self):
        for kwargs in ({"max_requests": 513}, {"max_bytes": fixture.MAX_BYTES + 1}):
            with self.assertRaises(ValueError):
                fixture.Fixture(MEDIA, **kwargs)


if __name__ == "__main__":
    unittest.main()
