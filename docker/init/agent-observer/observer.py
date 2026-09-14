#!/usr/bin/env python3
"""Small, deliberately reduced Docker status projection for the Hermes agent."""

from __future__ import annotations

import errno
import http.client
import ipaddress
import json
import re
import select
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

BACKEND_HOST = "docker-socket-proxy-agent-backend"
BACKEND_PORT = 2375
MAX_UPSTREAM_BODY_BYTES = 1_048_576
MAX_UPSTREAM_HEADER_BYTES = 65_536
MAX_DOWNSTREAM_BODY_BYTES = 1_048_576
UPSTREAM_TIMEOUT_SECONDS = 3.0
INBOUND_TIMEOUT_SECONDS = 3.0
DOWNSTREAM_TIMEOUT_SECONDS = 3.0
MAX_REQUEST_LINE_BYTES = 4096
MAX_CONCURRENT_REQUESTS = 16
MAX_LIST_ITEMS = 1024
MAX_STRING_BYTES = 4096
CONTAINER_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
API_VERSION = re.compile(r"^v[0-9]+\.[0-9]+$")
# The logs backend path is always reconstructed from validated parts; the
# pattern below only admits exactly that construction.
BACKEND_PATH = re.compile(
    r"^/(?:_ping|version|containers/json(?:\?all=[01])?|containers/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/json|containers/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/logs\?stdout=[01]&stderr=[01]"
    r"&tail=[0-9]{1,4}&timestamps=[01])$"
)
LOG_TAIL_DEFAULT = 100
LOG_TAIL_MAX = 1000
# The container-logs query contract: parameter -> (allowed value pattern,
# default when omitted). Iteration order is the rebuilt query's parameter
# order, which BACKEND_PATH matches exactly. Anything outside this table is
# rejected rather than forwarded, so the backend request is fully described
# by validated parts.
LOGS_PARAMETERS = {
    "stdout": (r"[01]", "1"),
    "stderr": (r"[01]", "1"),
    "tail": (r"[0-9]{1,4}", str(LOG_TAIL_DEFAULT)),
    "timestamps": (r"[01]", "0"),
}


class BodyLimitExceeded(Exception):
    pass


class UpstreamTimeout(Exception):
    pass


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise UpstreamTimeout
    return remaining


def _wait_for(sock: socket.socket, readable: bool, deadline: float) -> None:
    timeout = _remaining_timeout(deadline)
    readers = [sock] if readable else []
    writers = [] if readable else [sock]
    read_ready, write_ready, _ = select.select(readers, writers, [], timeout)
    if (readable and not read_ready) or (not readable and not write_ready):
        raise UpstreamTimeout


def _send_absolute(sock: socket.socket, data: bytes, deadline: float) -> None:
    view = memoryview(data)
    while view:
        _wait_for(sock, False, deadline)
        try:
            sent = sock.send(view)
        except BlockingIOError:
            continue
        if sent == 0:
            raise ConnectionError("socket closed")
        view = view[sent:]


class DeadlineReader:
    """File wrapper that gives each buffered HTTP read one absolute deadline."""

    def __init__(self, raw_file, sock: socket.socket, deadline: float):
        self.raw_file = raw_file
        self.sock = sock
        self.deadline = deadline

    def _read_one(self) -> bytes:
        while True:
            _remaining_timeout(self.deadline)
            try:
                chunk = self.raw_file.read(1)
            except BlockingIOError:
                chunk = None
            if chunk:
                return chunk
            if chunk == b"":
                return b""
            _wait_for(self.sock, True, self.deadline)

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        if size < 0:
            chunks = []
            while True:
                chunk = self._read_one()
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        chunks = []
        for _ in range(size):
            chunk = self._read_one()
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def readline(self, size: int = -1) -> bytes:
        chunks = []
        length = 0
        while size < 0 or length < size:
            chunk = self._read_one()
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            if chunk == b"\n":
                break
        return b"".join(chunks)

    def close(self) -> None:
        self.raw_file.close()

    def __getattr__(self, name):
        return getattr(self.raw_file, name)


class DeadlineSocket:
    def __init__(self, raw: socket.socket, deadline: float):
        self.raw = raw
        self.deadline = deadline

    def makefile(self, *args, **kwargs):
        return DeadlineReader(self.raw.makefile(*args, **kwargs), self.raw, self.deadline)

    def send(self, data, *args, **kwargs):
        return self.raw.send(data, *args, **kwargs)

    def settimeout(self, value):
        return self.raw.settimeout(value)

    def close(self):
        return self.raw.close()

    def __getattr__(self, name):
        return getattr(self.raw, name)


def _read_limited(response, deadline: float) -> bytes:
    headers_size = sum(len(str(key)) + len(str(value)) + 4 for key, value in response.getheaders())
    if headers_size > MAX_UPSTREAM_HEADER_BYTES:
        raise BodyLimitExceeded
    length = response.headers.get("Content-Length")
    if length is not None and (not length.isdigit() or int(length) > MAX_UPSTREAM_BODY_BYTES):
        raise BodyLimitExceeded

    chunks: list[bytes] = []
    size = 0
    while True:
        _remaining_timeout(deadline)
        chunk = response.read(min(65536, MAX_UPSTREAM_BODY_BYTES - size + 1))
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > MAX_UPSTREAM_BODY_BYTES:
            raise BodyLimitExceeded
        chunks.append(chunk)


class DeadlineHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection using the startup-resolved backend address only."""

    def __init__(self, address: tuple[str, int], deadline: float):
        super().__init__(BACKEND_HOST, timeout=1)
        self.backend_address = address
        self.deadline = deadline

    def connect(self) -> None:
        # The address was resolved before the server accepted clients. Use a
        # numeric AF_INET socket directly so this request performs no DNS.
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.setblocking(False)
        try:
            result = raw.connect_ex(self.backend_address)
            if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                raise OSError(result, "backend connection failed")
            if result:
                _wait_for(raw, False, self.deadline)
                error = raw.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if error:
                    raise OSError(error, "backend connection failed")
            self.sock = DeadlineSocket(raw, self.deadline)
        except Exception:
            raw.close()
            raise

    def send(self, data) -> None:
        if self.sock is None:
            self.connect()
        _send_absolute(self.sock.raw, data, self.deadline)


class BackendClient:
    def __init__(self, backend_address: tuple[str, int] | None = None):
        self.backend_address = backend_address

    def get(self, path: str) -> tuple[int | None, bytes | None]:
        if self.backend_address is None or not BACKEND_PATH.fullmatch(path):
            return None, None
        deadline = time.monotonic() + UPSTREAM_TIMEOUT_SECONDS
        connection = DeadlineHTTPConnection(self.backend_address, deadline)
        try:
            connection.request(
                "GET",
                path,
                headers={"Accept": "application/json", "Connection": "close", "Host": BACKEND_HOST},
            )
            response = connection.getresponse()
            return response.status, _read_limited(response, deadline)
        except (BodyLimitExceeded, TimeoutError, UpstreamTimeout, OSError, ValueError, http.client.HTTPException):
            return None, None
        finally:
            connection.close()


def resolve_backend() -> tuple[str, int]:
    """Resolve the fixed IPv4 backend once, before accepting clients."""
    addresses = socket.getaddrinfo(
        BACKEND_HOST,
        BACKEND_PORT,
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    )
    for family, _, _, _, sockaddr in addresses:
        if family == socket.AF_INET:
            host = sockaddr[0]
            ipaddress.IPv4Address(host)
            return host, BACKEND_PORT
    raise OSError("backend has no numeric IPv4 address")


def _safe_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    encoded = value.encode("utf-8", "ignore")
    if len(encoded) > MAX_STRING_BYTES:
        return None
    return value


def _copy_string(output: dict, key: str, value: object) -> None:
    safe = _safe_string(value)
    if safe is not None:
        output[key] = safe


def _copy_exit_code(output: dict, value: object) -> None:
    if isinstance(value, int) and not isinstance(value, bool) and -(2**31) <= value < 2**31:
        output["ExitCode"] = value


def _copy_health(output: dict, state: object) -> None:
    if isinstance(state, dict):
        health = state.get("Health")
        if isinstance(health, dict):
            status = _safe_string(health.get("Status"))
            if status is not None:
                output["Health"] = {"Status": status}


def project_container_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError
    result = []
    for item in value[:MAX_LIST_ITEMS]:
        if not isinstance(item, dict):
            continue
        projected: dict = {}
        _copy_string(projected, "Id", item.get("Id"))
        names = item.get("Names")
        if isinstance(names, list):
            safe_names = [name for name in names[:128] if _safe_string(name) is not None]
            if safe_names:
                projected["Names"] = safe_names
        _copy_string(projected, "Image", item.get("Image"))
        _copy_string(projected, "ImageID", item.get("ImageID"))
        _copy_string(projected, "State", item.get("State"))
        _copy_string(projected, "Status", item.get("Status"))
        _copy_exit_code(projected, item.get("ExitCode"))
        _copy_health(projected, item)
        result.append(projected)
    return result


def project_container_inspect(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError
    projected: dict = {}
    _copy_string(projected, "Id", value.get("Id"))
    _copy_string(projected, "Name", value.get("Name"))
    _copy_string(projected, "Image", value.get("Image"))
    config = value.get("Config")
    if isinstance(config, dict):
        _copy_string(projected, "ImageRef", config.get("Image"))
    state = value.get("State")
    if isinstance(state, dict):
        status = state.get("Status")
        _copy_string(projected, "State", status)
        _copy_string(projected, "Status", status)
        _copy_exit_code(projected, state.get("ExitCode"))
    else:
        _copy_string(projected, "State", state)
        _copy_string(projected, "Status", value.get("Status"))
    _copy_health(projected, state)
    return projected


def project_version(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError
    output: dict = {}
    for key in ("ApiVersion", "MinAPIVersion", "Version", "Os", "Arch"):
        _copy_string(output, key, value.get(key))
    return output


def project_container_logs(body: bytes) -> bytes:
    """Decode the backend's finite (never followed) multiplexed log stream.

    Frames are an 8-byte header (stream byte, 3 padding, big-endian length)
    plus payload; payloads are coerced to UTF-8 rather than relayed verbatim,
    and an incomplete final frame is dropped instead of relayed as a partial
    line.
    """
    chunks: list[str] = []
    offset = 0
    while offset + 8 <= len(body):
        end = offset + 8 + int.from_bytes(body[offset + 4 : offset + 8], "big")
        if end > len(body):
            break
        chunks.append(body[offset + 8 : end].decode("utf-8", "replace"))
        offset = end
    return "".join(chunks).encode("utf-8")


def build_logs_backend_path(ref: str, query: str) -> str | None:
    """Rebuild the logs query from the LOGS_PARAMETERS contract.

    Returns None unless the contract fully describes the query. Encoded
    bytes ('%'/'+') are rejected because the contract matches literal
    values: anything encoded is a parameter the validation never saw, and
    the backend must receive exactly the string that was validated. A
    repeated key is likewise rejected: it is ambiguous on re-parse, so it
    is not a value this function can vouch for.
    """
    if "%" in query or "+" in query:
        return None
    parts = [part.partition("=") for part in query.split("&")] if query else []
    keys = [key for key, _, _ in parts]
    if len(keys) != len(set(keys)):
        return None
    resolved = {key: default for key, (_, default) in LOGS_PARAMETERS.items()}
    for key, separator, value in parts:
        allowed = LOGS_PARAMETERS.get(key) if separator else None
        if allowed is None or not re.fullmatch(allowed[0], value):
            return None
        resolved[key] = value
    if int(resolved["tail"]) > LOG_TAIL_MAX:
        return None
    return f"/containers/{ref}/logs?" + "&".join(
        f"{key}={resolved[key]}" for key in LOGS_PARAMETERS
    )


class ObserverHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def handle_one_request(self) -> None:  # noqa: D102
        deadline = time.monotonic() + INBOUND_TIMEOUT_SECONDS
        self.request.setblocking(False)
        self.rfile = DeadlineReader(self.rfile, self.request, deadline)
        super().handle_one_request()

    def version_string(self) -> str:  # noqa: D102
        return "docker-observer"

    def log_message(self, format, *args) -> None:  # noqa: A002,D102
        # Request targets can contain sensitive values. Do not log them.
        return

    def parse_request(self) -> bool:
        if len(self.raw_requestline) > MAX_REQUEST_LINE_BYTES:
            self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
            return False
        return super().parse_request()

    def _reject(self, status: HTTPStatus) -> None:
        self._send_json(status, {"error": "request rejected"})

    def _send_downstream(self, status: HTTPStatus | int, content_type: bytes, body: bytes) -> None:
        try:
            reason = HTTPStatus(status).phrase
        except ValueError:
            reason = "Error"
        visible_body = b"" if self.command == "HEAD" else body
        response = (
            b"HTTP/1.1 "
            + str(int(status)).encode("ascii")
            + b" "
            + reason.encode("ascii")
            + b"\r\nContent-Type: "
            + content_type
            + b"\r\nContent-Length: "
            + str(len(body)).encode("ascii")
            + b"\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
            + visible_body
        )
        try:
            self.request.setblocking(False)
            _send_absolute(self.request, response, time.monotonic() + DOWNSTREAM_TIMEOUT_SECONDS)
        except (OSError, UpstreamTimeout):
            return
        finally:
            self.close_connection = True

    def _send_json(self, status: HTTPStatus | int, value: object) -> None:
        try:
            body = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        except (TypeError, ValueError):
            status, body = HTTPStatus.BAD_GATEWAY, b'{"error":"observer backend unavailable"}'
        if len(body) > MAX_DOWNSTREAM_BODY_BYTES:
            status, body = HTTPStatus.BAD_GATEWAY, b'{"error":"observer backend unavailable"}'
        self._send_downstream(status, b"application/json", body)

    def _send_text(self, status: HTTPStatus, body: bytes) -> None:
        self._send_downstream(status, b"text/plain; charset=utf-8", body)

    def _route(self) -> tuple[str, str | None] | None:
        target = self.path
        if any(ord(char) < 0x20 or ord(char) > 0x7e for char in target):
            return None
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or parsed.fragment or "%" in target:
            return None
        path = parsed.path
        if "\\" in path or "//" in path or "/./" in path or "/../" in path:
            return None
        parts = path.split("/")
        if len(parts) > 1 and API_VERSION.fullmatch(parts[1]):
            parts.pop(1)
            path = "/" + "/".join(parts[1:])
        kind = {"_ping": "ping", "version": "version", "containers/json": "list"}.get(path[1:])
        if kind:
            return (kind, parsed.query)
        # /containers/{ref}/{subresource}: the ref must be a strict name or
        # ID and the subresource must be one this observer serves.
        if len(parts) == 4 and parts[1] == "containers":
            ref, subresource = parts[2], parts[3]
            if CONTAINER_REF.fullmatch(ref) and subresource in ("json", "logs"):
                return (subresource, ref + ("?" + parsed.query if parsed.query else ""))
        return None

    def _query_for_list(self, query: str) -> str | None:
        if not query:
            return ""
        if "%" in query or "+" in query or "&" in query or "=" not in query:
            return None
        key, value = query.split("=", 1)
        if key != "all" or value not in ("0", "1"):
            return None
        return "?all=" + value

    def _serve(self) -> None:
        route = self._route()
        if route is None:
            self._reject(HTTPStatus.NOT_FOUND)
            return
        kind, query_or_ref = route
        if kind in ("ping", "version") and query_or_ref:
            self._reject(HTTPStatus.BAD_REQUEST)
            return
        if kind == "ping":
            status, _ = self.server.backend.get("/_ping")  # type: ignore[attr-defined]
            if status is None or status < 200 or status >= 300:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "observer backend unavailable"})
            else:
                # Do not relay even the backend's otherwise harmless body.
                self._send_text(HTTPStatus.OK, b"OK\n")
            return
        if kind == "list":
            query = self._query_for_list(query_or_ref or "")
            if query is None:
                self._reject(HTTPStatus.BAD_REQUEST)
                return
            backend_path = "/containers/json" + query
            projection = project_container_list
        elif kind == "json":
            if query_or_ref and "?" in query_or_ref:
                self._reject(HTTPStatus.BAD_REQUEST)
                return
            backend_path = "/containers/" + (query_or_ref or "") + "/json"
            projection = project_container_inspect
        elif kind == "logs":
            ref, _, query = (query_or_ref or "").partition("?")
            backend_path = build_logs_backend_path(ref, query)
            if backend_path is None:
                self._reject(HTTPStatus.BAD_REQUEST)
                return
        else:
            backend_path = "/version"
            projection = project_version

        status, body = self.server.backend.get(backend_path)  # type: ignore[attr-defined]
        if status is None or body is None or status < 200 or status >= 300:
            if status == HTTPStatus.NOT_FOUND and kind in ("json", "logs"):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "container not found"})
            else:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "observer backend unavailable"})
            return
        if kind == "logs":
            self._send_text(HTTPStatus.OK, project_container_logs(body))
            return
        try:
            value = projection(json.loads(body))
        except (ValueError, TypeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "observer backend unavailable"})
            return
        self._send_json(HTTPStatus.OK, value)

    def do_GET(self) -> None:  # noqa: D102
        self._serve()

    def do_HEAD(self) -> None:  # noqa: D102
        self._serve()

    def do_POST(self) -> None:  # noqa: D102
        self._reject(HTTPStatus.METHOD_NOT_ALLOWED)

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST
    do_TRACE = do_POST
    do_CONNECT = do_POST


class ObserverServer(ThreadingHTTPServer):
    request_queue_size = MAX_CONCURRENT_REQUESTS
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, ObserverHandler)
        self.request_limiter = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        self.backend = BackendClient()
        self.timeout = INBOUND_TIMEOUT_SECONDS + 2

    def process_request(self, request, client_address) -> None:
        if not self.request_limiter.acquire(blocking=False):
            try:
                request.setblocking(False)
                _send_absolute(
                    request,
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Length: 0\r\nConnection: close\r\n\r\n",
                    time.monotonic() + DOWNSTREAM_TIMEOUT_SECONDS,
                )
            except (OSError, UpstreamTimeout):
                pass
            finally:
                self.shutdown_request(request)
            return
        thread = threading.Thread(
            target=self._process_request,
            args=(request, client_address),
            daemon=self.daemon_threads,
        )
        thread.start()

    def _process_request(self, request, client_address) -> None:
        try:
            request.settimeout(INBOUND_TIMEOUT_SECONDS)
            self.finish_request(request, client_address)
            self.shutdown_request(request)
        except Exception:
            self.handle_error(request, client_address)
            self.shutdown_request(request)
        finally:
            self.request_limiter.release()

    def handle_error(self, request, client_address) -> None:  # noqa: D102
        # Do not emit request targets, response bodies, or backend details.
        return


def main() -> None:
    if len(sys.argv) > 1:
        raise SystemExit("unsupported command")
    try:
        backend_address = resolve_backend()
    except (OSError, socket.gaierror):
        raise SystemExit("backend resolution failed") from None
    server = ObserverServer(("0.0.0.0", 2375))
    server.backend = BackendClient(backend_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
