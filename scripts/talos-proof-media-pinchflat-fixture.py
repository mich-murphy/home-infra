#!/usr/bin/env python3
"""Offline, loopback-only Pinchflat candidate origin; stdlib, no upstream client.

Only protocol behavior is tested here, not Pinchflat/yt-dlp compatibility.
Input must be a newly generated two-second synthetic H264/AAC MP4, never an
application download. See docs/evidence/talos-media/pinchflat-fixture-preparation.md.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import stat
import time

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

    def __init__(self, media, port=0, max_requests=MAX_REQUESTS, max_bytes=MAX_BYTES):
        if not 12 <= len(media) <= MAX_MEDIA or media[4:8] != b"ftyp":
            raise ValueError("invalid MP4 snapshot")
        if not 1 <= max_requests <= MAX_REQUESTS or not 1 <= max_bytes <= MAX_BYTES:
            raise ValueError("invalid budget")
        super().__init__(("127.0.0.1", port), Handler)
        self.timeout = 0.25
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.media = bytes(media)
        self.max_requests, self.max_bytes = max_requests, max_bytes
        self.requests = self.sent_bytes = self.media_bytes = 0
        self.coverage = bytearray(len(media))
        self.routes = {path: 0 for path in PATHS}
        self.rejected = 0
        self.resources = self._resources()

    def _resources(self):
        page = self.origin + PATHS[1]
        media = self.origin + PATHS[2]
        metadata = {"@context": "https://schema.org", "@type": "VideoObject",
                    "identifier": "proof-001", "name": TITLE,
                    "description": "New synthetic two-second offline proof video",
                    "uploadDate": UPLOAD_DATE, "duration": "PT2S",
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

    def snapshot(self):
        return {"origin": self.origin, "requests": self.requests,
                "rejected": self.rejected, "routes": dict(self.routes),
                "sent_body_bytes": self.sent_bytes, "media_body_bytes": self.media_bytes,
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
        if body and fixture.sent_bytes + length > fixture.max_bytes:
            fixture.rejected += 1
            self.reply(429)
            return
        self.reply(code, length, headers)
        if body:
            # Reserve the budget before writing; aborted writes are conservative.
            fixture.sent_bytes += length
            try:
                self.wfile.write(data[start:end + 1])
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return
            if self.path == PATHS[2]:
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
    parser.add_argument("--mp4", required=True)
    parser.add_argument("--synthetic-input", action="store_true", required=True,
                        help="attest newly generated synthetic input, isolated from app downloads")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--seconds", type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900 or not 0 <= args.port <= 65535:
        parser.error("seconds must be 1..900 and port 0..65535")
    with Fixture(load_media(args.mp4), args.port) as fixture:
        print(json.dumps({"feed": fixture.origin + PATHS[0],
                          "scope": "offline candidate only"}), flush=True)
        deadline = time.monotonic() + args.seconds
        try:
            while time.monotonic() < deadline and fixture.requests < fixture.max_requests:
                fixture.handle_request()
        except KeyboardInterrupt:
            pass
        finally:
            print(json.dumps(fixture.snapshot(), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
