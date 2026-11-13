#!/usr/bin/env python3
"""Offline, loopback-only Pinchflat candidate origin; stdlib, no upstream client.

Only protocol behavior is tested here, not Pinchflat/yt-dlp compatibility.
Input must be a retained immutable twelve-second synthetic H264/AAC MP4, never an
application download. See docs/evidence/talos-media/pinchflat-fixture-preparation.md.
"""
import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import stat
import time
import threading
import uuid

MAX_MEDIA = 2 * 1024 * 1024
MAX_REQUESTS = 512
MAX_BYTES = 32 * 1024 * 1024
PATHS = ("/feed.xml", "/video/proof-001", "/media/proof-001.mp4")
TITLE = "Synthetic proof 001"
UPLOAD_DATE = "2026-01-01T00:00:00Z"


def load_media(path):
    """Take a bounded immutable snapshot, without following a final symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("input must be a regular, non-hardlinked file")
        if not 12 <= info.st_size <= MAX_MEDIA:
            raise ValueError("input must be 12 bytes through 2 MiB")
        # A bounded read loop also handles short regular-file reads.
        data = bytearray()
        while len(data) <= MAX_MEDIA:
            chunk = os.read(fd, min(65536, MAX_MEDIA + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        data = bytes(data)
    finally:
        os.close(fd)
    if len(data) != info.st_size or data[4:8] != b"ftyp":
        raise ValueError("input changed or lacks MP4 ftyp header")
    # Not a codec/provenance validator: generation and ffprobe evidence are required.
    return data


def byte_range(value, size):
    """Exactly one byte range; malformed/multiple/unsatisfiable ranges fail closed."""
    if len(value) > 80:
        raise ValueError("range too long")
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()):
        raise ValueError("invalid range")
    left, right = match.groups()
    if not left:
        suffix = int(right)
        if suffix == 0:
            raise ValueError("empty suffix")
        return max(0, size - suffix), size - 1
    start = int(left)
    end = min(int(right), size - 1) if right else size - 1
    if start >= size or end < start:
        raise ValueError("unsatisfiable range")
    return start, end


class Fixture(HTTPServer):
    request_queue_size = 4
    allow_reuse_address = False

    def __init__(self, media, port=0, max_requests=MAX_REQUESTS, max_bytes=MAX_BYTES, phase_file=None, snapshot_request_file=None):
        if not 12 <= len(media) <= MAX_MEDIA or media[4:8] != b"ftyp":
            raise ValueError("invalid MP4 snapshot")
        if not 1 <= max_requests <= MAX_REQUESTS or not 1 <= max_bytes <= MAX_BYTES:
            raise ValueError("invalid budget")
        super().__init__(("127.0.0.1", port), Handler)
        self.timeout = 0.25
        self.instance_id = uuid.uuid4().hex
        self.request_lock = threading.RLock()
        self.snapshot_request_file = snapshot_request_file
        self.snapshot_token = None
        self.phase_file = phase_file
        self.phase = 'metadata'
        self.phases = {name: {'media_body_bytes':0, 'coverage':bytearray(len(media)), 'routes':dict.fromkeys(PATHS,0)} for name in ('metadata','download')}
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.media = bytes(media)
        self.max_requests, self.max_bytes = max_requests, max_bytes
        self.requests = self.reserved_bytes = self.sent_bytes = self.media_bytes = 0
        self.coverage = bytearray(len(media))
        self.routes = {path: 0 for path in PATHS}
        self.rejected = 0
        self.resources = self._resources()

    def _resources(self):
        page = self.origin + PATHS[1]
        media = self.origin + PATHS[2]
        metadata = {"@context": "https://schema.org", "@type": "VideoObject",
                    "identifier": "proof-001", "name": TITLE,
                    "description": "Retained synthetic twelve-second offline proof video",
                    "uploadDate": UPLOAD_DATE, "duration": "PT12S",
                    "url": page, "contentUrl": media}
        html = (f'<!doctype html><html><head><title>{TITLE}</title>'
                f'<link rel="canonical" href="{page}">'
                '<script type="application/ld+json">' + json.dumps(metadata) +
                '</script></head><body><video controls>'
                f'<source src="{media}" type="video/mp4"></video></body></html>')
        # No enclosure: RSS entries must lead to the metadata-bearing HTML page,
        # not a bare MP4 which loses upload_date on independent re-extraction.
        feed = (f'<?xml version="1.0"?><rss version="2.0"><channel>'
                f'<title>Offline synthetic proof collection</title>'
                f'<link>{self.origin}/feed.xml</link>'
                '<description>Single synthetic fixture</description><item>'
                f'<title>{TITLE}</title><link>{page}</link>'
                f'<guid isPermaLink="true">{page}</guid>'
                '<pubDate>Thu, 01 Jan 2026 00:00:00 GMT</pubDate>'
                '</item></channel></rss>')
        return {PATHS[0]: ("application/rss+xml", feed.encode()),
                PATHS[1]: ("text/html; charset=utf-8", html.encode()),
                PATHS[2]: ("video/mp4", self.media)}

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address

    def update_phase(self):
        if self.phase_file:
            try:
                with open(self.phase_file, encoding='ascii') as handle:
                    value = handle.read(16).strip()
            except FileNotFoundError:
                value = 'metadata'
            if value not in self.phases:
                raise ValueError('invalid bounded fixture phase')
            if self.phase == 'download' and value != 'download':
                raise ValueError('fixture phase cannot move backwards')
            self.phase = value

    def process_request(self, request, client_address):
        # Client Content-Length completion precedes the handler's post-write
        # commit. Hold this barrier through the ENTIRE synchronous handler.
        with self.request_lock:
            super().process_request(request, client_address)

    @contextmanager
    def settled(self, timeout=3):
        if not self.request_lock.acquire(timeout=timeout):
            raise TimeoutError('fixture request/counter completion timed out')
        try:
            yield
        finally:
            self.request_lock.release()

    def publish(self, path, timeout=3):
        with self.settled(timeout):
            self.update_phase()
            # A fresh private request nonce acknowledges a publication AFTER
            # handler completion; an old, atomically valid JSON is insufficient.
            if self.snapshot_request_file:
                try:
                    with open(self.snapshot_request_file, encoding='ascii') as handle:
                        token = handle.read(33)
                except FileNotFoundError:
                    token = None
                if token is not None and not re.fullmatch('[a-f0-9]{32}', token):
                    raise ValueError('invalid fixture snapshot request token')
                self.snapshot_token = token
            temporary = str(path) + '.' + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump(self.snapshot(), handle)
            os.replace(temporary, path)  # ephemeral counter view only, NEVER an archive

    def snapshot(self, timeout=3):
        with self.settled(timeout):
            return self._snapshot()

    def _snapshot(self):
        # Only under the request-completion lock; no delivery counted in advance.
        return {"settled":True, "snapshot_token":self.snapshot_token, "instance_id":self.instance_id, "phase":self.phase,
                "phases":{name:{'media_body_bytes':v['media_body_bytes'], 'media_unique_bytes':sum(v['coverage']), 'routes':dict(v['routes'])} for name,v in self.phases.items()}, "origin": self.origin, "requests": self.requests,
                "rejected": self.rejected, "routes": dict(self.routes),
                "reserved_body_bytes": self.reserved_bytes, "sent_body_bytes": self.sent_bytes, "media_body_bytes": self.media_bytes,
                "media_unique_bytes": sum(self.coverage), "media_size": len(self.media),
                "media_sha256": hashlib.sha256(self.media).hexdigest(),
                "limits": {"requests": self.max_requests, "body_bytes": self.max_bytes},
                "scope": "fixture-protocol-only; not native Pinchflat acceptance"}


class Handler(BaseHTTPRequestHandler):
    # One request per connection; synchronous server bounds workers/state.
    protocol_version = "HTTP/1.0"
    server_version = "OfflineFixture/1"
    sys_version = ""

    def log_message(self, *_args):
        pass  # Never retain attacker-controlled URLs/headers or unbounded logs.

    def parse_request(self):
        if not super().parse_request():
            return False
        if self.server.requests >= self.server.max_requests:
            self.reply(429)
            return False
        self.server.update_phase()
        self.server.requests += 1
        return True

    def send_error(self, code, message=None, explain=None):
        # Keep stdlib parser/unsupported-method errors bodyless and unlogged.
        self.server.rejected += 1
        self.reply(code)

    def do_HEAD(self):
        self.serve(False)

    def do_GET(self):
        self.serve(True)

    def serve(self, body):
        fixture = self.server
        if self.path not in fixture.resources:
            fixture.rejected += 1
            self.reply(404)
            return
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length") not in (None, "0"):
            fixture.rejected += 1
            self.reply(400)
            return
        fixture.routes[self.path] += 1
        fixture.phases[fixture.phase]["routes"][self.path] += 1
        content_type, data = fixture.resources[self.path]
        start, end, code = 0, len(data) - 1, 200
        headers = {"Content-Type": content_type, "Accept-Ranges": "bytes"}
        ranges = self.headers.get_all("Range", [])
        if ranges:
            try:
                if len(ranges) != 1:
                    raise ValueError("duplicate range")
                start, end = byte_range(ranges[0], len(data))
            except ValueError:
                fixture.rejected += 1
                self.reply(416, headers={"Content-Range": f"bytes */{len(data)}"})
                return
            code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        length = end - start + 1
        if body and fixture.reserved_bytes + length > fixture.max_bytes:
            fixture.rejected += 1
            self.reply(429)
            return
        self.reply(code, length, headers)
        if body:
            # Reserve the budget before writing; aborted writes are conservative.
            fixture.reserved_bytes += length
            try:
                self.write_body(data[start:end + 1])
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return
            fixture.sent_bytes += length
            if self.path == PATHS[2]:
                self.commit_media(start, end, length)

    def write_body(self, data):
        self.wfile.write(data)
        self.wfile.flush()

    def commit_media(self, start, end, length):
        # Called only AFTER successful write + flush. This means server-side
        # write completion, NOT proof of client consumption or durable app output.
        fixture = self.server
        fixture.phases[fixture.phase]["media_body_bytes"] += length
        fixture.phases[fixture.phase]["coverage"][start:end+1] = b"\x01" * length
        fixture.media_bytes += length
        fixture.coverage[start:end + 1] = b"\x01" * length

    def reply(self, code, length=0, headers=None):
        self.send_response(code)
        self.send_header("Content-Length", str(length))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", help="ephemeral private latest counter view, not archive")
    parser.add_argument("--phase-file", help="local sidecar-only metadata→download phase control")
    parser.add_argument("--mp4", required=True)
    parser.add_argument("--synthetic-input", action="store_true", required=True,
                        help="attest newly generated synthetic input, isolated from app downloads")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--seconds", type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900 or not 0 <= args.port <= 65535:
        parser.error("seconds must be 1..900 and port 0..65535")
    with Fixture(load_media(args.mp4), args.port, phase_file=args.phase_file,
                 snapshot_request_file=(args.evidence_file + '.request') if args.evidence_file else None) as fixture:
        print(json.dumps({"feed": fixture.origin + PATHS[0],
                          "scope": "offline candidate only"}), flush=True)
        deadline = time.monotonic() + args.seconds
        try:
            while time.monotonic() < deadline and fixture.requests < fixture.max_requests:
                if args.evidence_file:
                    fixture.publish(args.evidence_file)
                fixture.handle_request()
        except KeyboardInterrupt:
            pass
        finally:
            if args.evidence_file:
                fixture.publish(args.evidence_file)
            print(json.dumps(fixture.snapshot(), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
