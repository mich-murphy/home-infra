#!/usr/bin/env python3
"""Fake-backend tests for the reduced Docker observer."""

import http.client
import importlib.util
import io
import json
import pathlib
import re
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

    def backend_log_path(self, container, parameters):
        resolved = {"stdout": "1", "stderr": "1", "tail": "100", "timestamps": "0"}
        resolved.update(parameters)
        return "/containers/{container}/logs?{query}".format(
            container=container,
            query="&".join(f"{key}={resolved[key]}" for key in ("stdout", "stderr", "tail", "timestamps")),
        )

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

    def make_log_stream(self, lines):
        """Backend-style multiplexed frames from (stream, payload) pairs."""
        import struct

        return b"".join(
            struct.pack(">Bxxx", stream) + len(payload).to_bytes(4, "big") + payload
            for stream, payload in lines
        )

    def get_logs(self, container, query=""):
        path = "/containers/" + container + "/logs" + ("?" + query if query else "")
        return self.request("GET", path)

    def test_logs_are_readable_as_plain_text(self):
        self.backend.responses[self.backend_log_path("media-server", {})] = (200, self.make_log_stream([
            (1, b"stdout line\n"),
            (2, b"stderr line\n"),
        ]))

        status, body = self.get_logs("media-server")

        self.assertEqual(status, 200)
        self.assertEqual(body, b"stdout line\nstderr line\n")

    def test_logs_of_unknown_container_report_not_found(self):
        status, body = self.get_logs("missing")

        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "container not found"})

    def test_logs_stream_filtering_and_timestamps_are_forwarded(self):
        for query in ("stdout=0", "stderr=0", "timestamps=1", "tail=50"):
            with self.subTest(query=query):
                parameters = dict(part.split("=") for part in query.split("&"))
                self.backend.responses[self.backend_log_path("media-server", parameters)] = (
                    200, self.make_log_stream([(2, b"only stderr\n")])
                )

                status, body = self.get_logs("media-server", query)

                self.assertEqual(status, 200)
                self.assertEqual(body, b"only stderr\n")
                self.assertEqual(
                    self.backend.requests[-1],
                    self.backend_log_path("media-server", parameters),
                )

    def test_logs_default_to_a_bounded_tail(self):
        self.backend.responses[self.backend_log_path("media-server", {})] = (200, b"")

        status, _ = self.get_logs("media-server")

        self.assertEqual(status, 200)
        requested_tail = re.search(r"tail=([0-9]+)", self.backend.requests[-1]).group(1)
        self.assertTrue(requested_tail.isdigit() and 0 < int(requested_tail) <= 1000)

    def test_logs_never_follow_or_window_by_time(self):
        # Reading logs must always terminate: whatever the caller sends,
        # follow/since/until must not reach the backend.
        for query in ("follow=1", "since=1700000000", "until=1700000000"):
            with self.subTest(query=query):
                status, _ = self.get_logs("media-server", query)

                self.assertEqual(status, 400)
                self.assertNotIn(query.split("=")[0], self.backend.requests[-1] if self.backend.requests else "")

    def test_logs_replace_undecodable_bytes_and_drop_incomplete_frames(self):
        self.backend.responses[self.backend_log_path("media-server", {})] = (
            200,
            self.make_log_stream([(1, b"\xff\xfe not utf-8\n")])
            + self.make_log_stream([(1, b"complete\n")])[:8]  # header claims more bytes than follow
        )

        status, body = self.get_logs("media-server")

        self.assertEqual(status, 200)
        self.assertIn("\ufffd\ufffd not utf-8\n".encode(), body)
        self.assertNotIn(b"complete", body)

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
