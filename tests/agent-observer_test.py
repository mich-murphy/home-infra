#!/usr/bin/env python3
"""Fake-backend tests for the reduced Docker observer."""

import http.client
import importlib.util
import io
import json
import pathlib
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch


SOURCE = pathlib.Path(__file__).parents[1] / "docker/init/agent-observer/observer.py"
SPEC = importlib.util.spec_from_file_location("agent_observer", SOURCE)
observer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
# The Ansible bootstrap copies this source directory; keep test bytecode out.
previous_bytecode_setting = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    SPEC.loader.exec_module(observer)
finally:
    sys.dont_write_bytecode = previous_bytecode_setting


class FakeBackend:
    def __init__(self):
        self.requests = []
        self.responses = {}

    def get(self, path):
        self.requests.append(path)
        return self.responses.get(path, (404, b"not exposed"))


class ObserverTest(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.server = observer.ObserverServer(("127.0.0.1", 0))
        self.server.backend = self.backend
        self.thread = __import__("threading").Thread(target=self.server.serve_forever)
        self.thread.start()
        self.connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, method, path):
        self.connection.request(method, path)
        response = self.connection.getresponse()
        body = response.read()
        return response.status, body

    def test_projection_drops_sensitive_fields(self):
        canary = "OBSERVER_CANARY_SECRET"
        self.backend.responses["/containers/json?all=1"] = (200, json.dumps([{
            "Id": "abc123",
            "Names": ["/media-server"],
            "Image": "registry.example/media:latest",
            "ImageID": "sha256:image",
            "State": "running",
            "Status": "Up 1 hour",
            "ExitCode": 0,
            "Labels": {"secret": canary},
            "Command": canary,
            "Env": ["TOKEN=" + canary],
            "Mounts": [{"Source": "/secret/host/path"}],
            "Health": {"Status": "healthy", "Log": [{"Output": canary}]},
        }]).encode())
        self.backend.responses["/containers/media-server/json"] = (200, json.dumps({
            "Id": "abc123",
            "Name": "/media-server",
            "Image": "sha256:image",
            "Config": {"Image": "registry.example/media:latest", "Env": [canary], "Cmd": [canary]},
            "State": {"Status": "running", "ExitCode": 0, "Health": {"Status": "healthy", "Log": [{"Output": canary}]}},
            "Mounts": [{"Source": canary}],
            "NetworkSettings": {"Networks": {"private": {"IPAddress": canary}}},
        }).encode())

        status, body = self.request("GET", "/containers/json?all=1")
        self.assertEqual(status, 200)
        status2, body2 = self.request("GET", "/containers/media-server/json")
        self.assertEqual(status2, 200)
        for output in (body, body2):
            self.assertNotIn(canary.encode(), output)
        listed = json.loads(body)[0]
        self.assertEqual(listed["Health"], {"Status": "healthy"})
        self.assertNotIn("Labels", listed)
        inspected = json.loads(body2)
        self.assertEqual(inspected["ImageRef"], "registry.example/media:latest")
        self.assertEqual(inspected["Health"], {"Status": "healthy"})
        self.assertNotIn("Config", inspected)

    def test_denied_routes_and_ambiguous_requests_never_hit_backend(self):
        for method, path, expected in (
            ("POST", "/containers/json", 405),
            ("POST", "/containers/name/logs", 405),
            ("GET", "/containers/name/logs?follow=1", 400),
            ("GET", "/containers/name/logs?tail=all", 400),
            ("GET", "/containers/name/logs?tail=99999", 400),
            ("GET", "/containers/name/logs?since=1700000000", 400),
            ("GET", "/containers/name/logs?stdout=1&stdout=0", 400),
            ("GET", "/containers/name/archive", 404),
            ("GET", "/events", 404),
            ("GET", "/containers/json?labels=secret", 400),
            ("GET", "/containers/json?all=1&all=0", 400),
            ("GET", "/containers/json?all=2", 400),
            ("GET", "/containers/%2Fsecret/json", 404),
            ("GET", "/containers/../json", 404),
        ):
            status, _ = self.request(method, path)
            self.assertEqual(status, expected, path)
        self.assertEqual(self.backend.requests, [])

    def test_logs_route_demuxes_and_defaults_tail(self):
        def frame(stream: int, payload: bytes) -> bytes:
            return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload

        body = (
            frame(1, b"stdout line\n")
            + frame(2, b"stderr OBSERVER_CANARY_SECRET\n")
            + frame(1, b"\xff\xfe invalid utf-8\n")
            # Final frame claims 40 payload bytes but delivers 9.
            + bytes([1, 0, 0, 0]) + (40).to_bytes(4, "big") + b"truncated"
        )
        self.backend.responses["/containers/media-server/logs?stdout=1&stderr=1&tail=100&timestamps=0"] = (200, body)
        self.backend.responses["/containers/media-server/logs?stdout=1&stderr=1&tail=50&timestamps=0"] = (200, body)

        status, result = self.request("GET", "/containers/media-server/logs")
        self.assertEqual(status, 200)
        self.assertIn(b"stdout line\n", result)
        self.assertIn(b"stderr OBSERVER_CANARY_SECRET\n", result)
        # Invalid UTF-8 is replaced, and a truncated final frame is dropped.
        self.assertIn("\ufffd\ufffd invalid utf-8\n".encode(), result)
        self.assertNotIn(b"truncated", result)

        status, _ = self.request("GET", "/containers/media-server/logs?stdout=1&stderr=1&tail=50&timestamps=0")
        self.assertEqual(status, 200)
        self.assertEqual(self.backend.requests[-1], "/containers/media-server/logs?stdout=1&stderr=1&tail=50&timestamps=0")

        # Unknown container surfaces the backend's 404.
        self.backend.responses["/containers/missing/logs?stdout=1&stderr=1&tail=100&timestamps=0"] = (404, b"nope")
        status, result = self.request("GET", "/containers/missing/logs")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(result), {"error": "container not found"})

    def test_version_prefix_and_head(self):
        self.backend.responses["/version"] = (200, json.dumps({
            "ApiVersion": "1.46", "MinAPIVersion": "1.24", "Version": "27.0",
            "Os": "linux", "Arch": "amd64", "Secret": "OBSERVER_CANARY_SECRET",
        }).encode())
        status, body = self.request("GET", "/v1.46/version")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["ApiVersion"], "1.46")
        self.assertNotIn(b"Secret", body)
        status, body = self.request("HEAD", "/v1.46/version")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(self.backend.requests, ["/version", "/version"])

    def test_backend_errors_are_sanitized(self):
        self.backend.responses["/version"] = (500, b"backend password OBSERVER_CANARY_SECRET")
        status, body = self.request("GET", "/version")
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(body), {"error": "observer backend unavailable"})
        self.assertNotIn(b"OBSERVER_CANARY_SECRET", body)

    def run_slow_upstream(self, response: bytes, delay: float, *, body_only=False):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2)
        address = listener.getsockname()
        received = threading.Event()

        def serve():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(1)
                    request = b""
                    while b"\r\n\r\n" not in request:
                        chunk = connection.recv(4096)
                        if not chunk:
                            return
                        request += chunk
                    received.set()
                    remaining = response
                    if body_only:
                        headers, remaining = response.split(b"\r\n\r\n", 1)
                        connection.sendall(headers + b"\r\n\r\n")
                    if delay == 0:
                        connection.sendall(remaining)
                    else:
                        for byte in remaining:
                            connection.sendall(bytes([byte]))
                            time.sleep(delay)
            except OSError:
                # Deadline tests deliberately close the client mid-response.
                pass
            finally:
                listener.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        return address[0], address[1], thread, received

    def test_successful_real_backend_round_trip(self):
        payload = json.dumps({"ApiVersion": "1.46", "Secret": "canary"}).encode()
        response = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
        host, port, thread, received = self.run_slow_upstream(response, 0)
        self.server.backend = observer.BackendClient((host, port))
        with patch.object(observer.socket, "getaddrinfo", side_effect=AssertionError("request must not resolve DNS")):
            # Connect the test client numerically before suppressing DNS globally.
            client = socket.socket()
            client.settimeout(2)
            client.connect(("127.0.0.1", self.server.server_port))
            with client:
                client.sendall(b"GET /version HTTP/1.1\r\nHost: observer\r\n\r\n")
                result = http.client.HTTPResponse(client)
                result.begin()
                self.assertEqual(result.status, 200)
                self.assertEqual(json.loads(result.read()), {"ApiVersion": "1.46"})
        self.assertTrue(received.is_set())
        thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_already_readable_data_obeys_absolute_deadline(self):
        raw = io.BytesIO(b"continuously available\n")
        reader = observer.DeadlineReader(raw, None, time.monotonic() - 1)
        with self.assertRaises(observer.UpstreamTimeout):
            reader.readline()
        self.assertEqual(raw.tell(), 0)
        reader = observer.DeadlineReader(raw, None, 10)
        # Expire between two reads even though neither needs to wait on a socket.
        with patch.object(observer.time, "monotonic", side_effect=[9, 11]):
            with self.assertRaises(observer.UpstreamTimeout):
                reader.read(2)
        self.assertEqual(raw.tell(), 1)

    def test_upstream_size_and_time_limits(self):
        oversized = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(observer.MAX_UPSTREAM_BODY_BYTES + 1).encode() + b"\r\n\r\n"
        host, port, thread, received = self.run_slow_upstream(oversized, 0)
        status, body = observer.BackendClient((host, port)).get("/version")
        self.assertIsNone(status)
        self.assertIsNone(body)
        self.assertTrue(received.is_set())
        thread.join(2)
        self.assertFalse(thread.is_alive())

        with patch.object(observer, "UPSTREAM_TIMEOUT_SECONDS", 0.2):
            for body_only in (False, True):
                with self.subTest(body_only=body_only):
                    response = b"HTTP/1.1 200 OK\r\nContent-Length: 40\r\n\r\n" + b"x" * 40
                    host, port, thread, received = self.run_slow_upstream(response, 0.015, body_only=body_only)
                    started = time.monotonic()
                    status, body = observer.BackendClient((host, port)).get("/version")
                    elapsed = time.monotonic() - started
                    self.assertIsNone(status)
                    self.assertIsNone(body)
                    self.assertTrue(received.is_set())
                    self.assertGreater(elapsed, 0.15)
                    self.assertLess(elapsed, 0.8)
                    thread.join(2)
                    self.assertFalse(thread.is_alive())

    def test_slow_inbound_deadline_and_saturation_recovery(self):
        old_timeout = observer.INBOUND_TIMEOUT_SECONDS
        observer.INBOUND_TIMEOUT_SECONDS = 0.2
        slow = []
        drip = None
        try:
            drip = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=1)
            drip_connection = drip

            def drip_send():
                for byte in b"GET /_ping HTTP/1.1\r\nHost: observer\r\n":
                    try:
                        drip_connection.send(bytes([byte]))
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    time.sleep(0.03)

            sender = threading.Thread(target=drip_send, daemon=True)
            sender.start()
            started = time.monotonic()
            drip.settimeout(1)
            try:
                while drip.recv(4096):
                    pass
            except ConnectionResetError:
                pass
            self.assertLess(time.monotonic() - started, 0.6)
            drip.close()
            drip = None
            sender.join(1)

            for _ in range(observer.MAX_CONCURRENT_REQUESTS):
                connection = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=1)
                connection.sendall(b"GET /_ping HTTP/1.1\r\nHost: observer\r\n")
                slow.append(connection)
            time.sleep(0.05)
            saturated = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=1)
            saturated.sendall(b"GET /_ping HTTP/1.1\r\nHost: observer\r\n\r\n")
            response = saturated.recv(128)
            self.assertTrue(response.startswith(b"HTTP/1.1 503 Service Unavailable\r\n"))
            self.assertNotIn(b"\\\\r\\\\n", response)
            saturated.close()
            for connection in slow:
                connection.close()
            time.sleep(0.25)
            status, _ = self.request("GET", "/events")
            self.assertEqual(status, 404)
            self.assertFalse(any(thread.name == "observer-request" for thread in threading.enumerate()))
        finally:
            if drip is not None:
                drip.close()
            for connection in slow:
                connection.close()
            observer.INBOUND_TIMEOUT_SECONDS = old_timeout

    def test_stale_backend_is_sanitized(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        address = listener.getsockname()
        listener.close()
        with patch.object(observer.socket, "getaddrinfo", side_effect=AssertionError("request must not resolve DNS")):
            status, body = observer.BackendClient((address[0], address[1])).get("/version")
        self.assertIsNone(status)
        self.assertIsNone(body)
        self.server.backend = observer.BackendClient((address[0], address[1]))
        status, body = self.request("GET", "/version")
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(body), {"error": "observer backend unavailable"})
        self.assertNotIn(str(address[1]).encode(), body)


if __name__ == "__main__":
    unittest.main()
