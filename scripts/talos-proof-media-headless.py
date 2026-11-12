#!/usr/bin/env python3
"""Offline-prepared, non-browser Plex decoder component; CLI deliberately disabled.

No lease, credentials, or private proof state are read here. Parent integration
must supply the existing verified API, enforce its lease on every callback, and
own timeline/activity/history calls. Low-level decode() is also usable with NEW
synthetic byte streams for workstation tests; that is never runtime evidence.
"""
import ctypes
import dataclasses
import hashlib
import importlib
import os
from pathlib import Path
import queue
import re
import resource
import selectors
import shutil
import stat
import subprocess
import tempfile
import sys
import threading
import time
import urllib.request
import uuid

FIXTURE_SHA256 = '9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb'
FIXTURE_BYTES = 120214
MAX_SECONDS = 25
MAX_OUTPUT = 262144
CHUNK = 8192


class Rejected(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise Rejected(message)


@dataclasses.dataclass(frozen=True)
class Identity:
    client: str
    session: str
    item: str

    def __post_init__(self):
        require(all(isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', x)
                    for x in (self.client, self.session)), 'invalid client/session')
        require(bool(re.fullmatch(r'[0-9]+', self.item)), 'invalid item')

    def headers(self):
        return {'X-Plex-Client-Identifier': self.client,
                'X-Plex-Session-Identifier': self.session}


def open_plex_stream(api, path, identity):
    """No URL argument, redirects, HTTP diagnostic mode, or predownload.

    Reuses the independently verified API opener, including CA/hostname/SNI and
    loopback transport. Caller owns the returned response and must close it.
    Socket reads have a one-second timeout so cancellation can join the producer.
    """
    API = importlib.import_module('talos-proof-media-http').API
    require(type(api) is API and api.service == 'plex' and not api.allow_http and api.ca
            and api.base == 'https://plex.proof.invalid:18443', 'verified Plex API required')
    require(bool(re.fullmatch(r'/library/parts/[0-9]+/[0-9]+/file\.mp4', path)),
            'only scanned original MP4 path allowed')
    normalized = {key.lower(): value for key, value in api.headers.items()}
    for key, value in identity.headers().items():
        require(normalized.get(key.lower(), value) == value, 'GET identity mismatch')
    headers = {**api.headers, **identity.headers(), 'Accept-Encoding': 'identity'}
    request = urllib.request.Request(api.base + path, headers=headers, method='GET')
    response = api.opener.open(request, timeout=1)
    try:
        require(response.status == 200 and response.geturl() == api.base + path,
                'exact HTTP200 original response required (no redirects)')
        require(response.headers.get('Content-Encoding', 'identity') == 'identity',
                'encoded response forbidden')
        length = response.headers.get('Content-Length')
        require(length == str(FIXTURE_BYTES) and not response.headers.get('Transfer-Encoding'),
                'exact Content-Length and unchunked response required')
        return response
    except BaseException:
        response.close()
        raise


class StreamCheck:
    def __init__(self, size=FIXTURE_BYTES, digest=FIXTURE_SHA256):
        require(type(size) is int and 0 < size <= FIXTURE_BYTES, 'invalid stream bound')
        require(bool(re.fullmatch('[0-9a-f]{64}', digest)), 'invalid digest')
        self.size, self.digest = size, digest
        self.count, self.hash = 0, hashlib.sha256()

    def feed(self, data):
        require(isinstance(data, bytes) and len(data) <= CHUNK, 'invalid stream chunk')
        require(self.count + len(data) <= self.size, 'stream exceeds exact fixture bound')
        self.hash.update(data)
        self.count += len(data)

    def finish(self):
        require(self.count == self.size and self.hash.hexdigest() == self.digest,
                'fixture length/hash mismatch')


@dataclasses.dataclass(frozen=True)
class Progress:
    frame: int
    media_us: int


class ProgressParser:
    def __init__(self):
        self.buffer, self.block = b'', {}
        self.last = Progress(0, 0)

    def feed(self, data):
        self.buffer += data
        require(len(self.buffer) <= MAX_OUTPUT, 'progress buffer exceeded')
        result = []
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            key, sep, value = line.partition(b'=')
            require(bool(sep) and len(line) <= 4096, 'malformed progress')
            self.block[key] = value.strip()
            if key == b'progress':
                require(value.strip() in (b'continue', b'end'), 'invalid progress state')
                try:
                    current = Progress(int(self.block[b'frame']), int(self.block[b'out_time_us']))
                except (KeyError, ValueError):
                    raise Rejected('missing decoded frame/media time') from None
                require(current.frame >= self.last.frame and current.media_us >= self.last.media_us
                        and 0 <= current.media_us <= 15000000, 'invalid/regressing progress')
                if current.frame > self.last.frame and current.media_us > self.last.media_us:
                    result.append(current)
                self.last, self.block = current, {}
        return result


class Lifecycle:
    """Evidence acceptance only; never manufactures application replies or times.

    A reviewed adapter must call playing -> activity -> advanced -> stopped ->
    history in that order, using decoder snapshots and actual application data.
    The activity callback watermark must be sampled AFTER its HTTP response.
    """
    def __init__(self, identity, baseline_history_ids):
        self.identity = identity
        self.baseline = set(map(str, baseline_history_ids))
        self.previous = Progress(0, 0)
        self.advances = 0
        self.stage = 'new'
        self.after_activity = None

    def advanced(self, progress, alive, verified):
        require(alive, 'post-exit progress cannot prove playback')
        require(progress.frame > self.previous.frame and progress.media_us > self.previous.media_us,
                'decoded frames and media time must both advance')
        if self.stage == 'activity':
            require(verified and progress.frame > self.after_activity.frame and
                    progress.media_us > self.after_activity.media_us, 'no post-activity decode')
            self.stage = 'concurrent'
        self.previous = progress
        self.advances += 1

    def playing(self, identity, alive, verified):
        require(identity == self.identity, 'timeline identity mismatch')
        require(self.stage == 'new' and alive and verified and self.advances >= 2,
                'playing requires verified stream and advancing live decode')
        self.stage = 'playing'
        return self.previous  # actual decoder media time, not wall-clock fabrication

    def activity(self, rows, alive, watermark):
        require(self.stage == 'playing' and alive, 'activity must return during decode')
        matches = [r for r in rows if str(r.get('rating_key')) == self.identity.item
                   and r.get('machine_id') == self.identity.client and r.get('state') == 'playing']
        require(len(matches) == 1, 'no unique same-client playing activity')
        require(watermark.frame >= self.previous.frame and watermark.media_us >= self.previous.media_us,
                'stale activity watermark')
        self.after_activity, self.stage = watermark, 'activity'

    def stopped(self, identity, alive, returncode, native_stopped):
        require(identity == self.identity, 'stopped identity mismatch')
        require(self.stage == 'concurrent' and not alive and returncode == 0 and native_stopped is True,
                'requires genuine successful decoder end and native stopped response')
        self.stage = 'stopped'

    def history(self, rows):
        require(self.stage == 'stopped' and len(rows) == 1, 'unique stopped history required')
        row = rows[0]
        require(str(row.get('rating_key')) == self.identity.item and
                row.get('machine_id') == self.identity.client and
                row.get('row_id') is not None and str(row['row_id']) not in self.baseline,
                'stale/wrong-client history')
        try:
            duration = int(row['duration'])
        except (KeyError, ValueError, TypeError):
            raise Rejected('missing actual history duration') from None
        require(duration > 0, 'history duration must be positive')
        self.stage = 'complete'


def command(ffmpeg):
    path = Path(ffmpeg)
    require(bool(re.fullmatch(r'/nix/store/[a-z0-9]{32}-ffmpeg[^/]*/bin/ffmpeg', str(path)))
            and str(path.resolve()).startswith('/nix/store/') and
            path.is_file() and os.access(path, os.X_OK), 'exact Nix ffmpeg required')
    return [str(path), '-hide_banner', '-loglevel', 'error', '-nostdin', '-nostats',
            '-stats_period', '0.25', '-progress', 'pipe:1', '-max_alloc', '67108864', '-threads', '1',
            '-filter_threads', '1', '-protocol_whitelist', 'pipe', '-readrate', '1',
            '-i', 'pipe:0', '-map', '0:v:0', '-an', '-threads', '1',
            '-c:v', 'wrapped_avframe', '-f', 'null', '-']


def _limits():
    limits = [(resource.RLIMIT_CPU, 30), (resource.RLIMIT_FSIZE, MAX_OUTPUT),
              (resource.RLIMIT_NOFILE, 64), (resource.RLIMIT_CORE, 0)]
    if sys.platform != 'darwin':
        limits.append((resource.RLIMIT_AS, 1024**3))
    for kind, bound in limits:
        resource.setrlimit(kind, (bound, bound))


class MemoryWatch:
    """Darwin lacks usable RLIMIT_AS: exact-PID RSS watchdog, NOT a hard cap.

    Linux uses kernel RLIMIT_AS. Parent must review Darwin watchdog overshoot
    and supply a hard sandbox if its scoped receipt requires a hard ceiling.
    """
    def __init__(self):
        self.lib = None
        if sys.platform == 'darwin':
            self.lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
            self.lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                             ctypes.c_void_p, ctypes.c_int]
            self.lib.proc_pidinfo.restype = ctypes.c_int

    def check(self, process):
        if self.lib is not None and process.poll() is None:
            task = ctypes.create_string_buffer(96)  # Darwin proc_taskinfo
            count = self.lib.proc_pidinfo(process.pid, 4, 0, task, len(task))
            if count != len(task):
                require(process.poll() is not None, 'cannot inspect owned decoder RSS')
                return
            resident = ctypes.c_uint64.from_buffer(task, 8).value
            require(resident <= 1024**3, 'decoder RSS watchdog exceeded')


def decode(source, ffmpeg, private_root, *, size=FIXTURE_BYTES, digest=FIXTURE_SHA256,
           observe=None, cancel=None, seconds=MAX_SECONDS):
    """Stream bytes straight to ONE owned child; no input file or other process.

    observe(progress, alive, hash_verified) is a trusted bounded integration
    hook, not an authority grant. It must not block or launch subprocesses.
    Return means decoder-only success, NOT application/lifecycle success.
    Source.read must be bounded (verified opener uses a 1s socket timeout).
    """
    require(0 < seconds <= MAX_SECONDS, 'invalid wall-time bound')
    root = Path(private_root)
    info = root.lstat()
    require(root.is_absolute() and not root.is_symlink() and
            all(not p.is_symlink() for p in root.parents) and stat.S_ISDIR(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid(),
            'owned private 0700 root required')
    argv = command(ffmpeg)
    check, parser = StreamCheck(size, digest), ProgressParser()
    memory = MemoryWatch()
    run = Path(tempfile.mkdtemp(prefix='headless-' + uuid.uuid4().hex + '-', dir=root))
    home = run / ('home-' + uuid.uuid4().hex)
    home.mkdir(mode=0o700)
    logs = []
    process, worker = None, None
    stop = threading.Event()
    chunks = queue.Queue(maxsize=2)
    selector = selectors.DefaultSelector()
    def produce():
        try:
            while not stop.is_set():
                # read1 limits the live HTTPResponse to one socket read, avoiding
                # read(n)'s indefinite refill under a slow trickle. Live responses
                # are unchunked with exact Content-Length (checked above).
                data = getattr(source, 'read1', source.read)(CHUNK)
                while not stop.is_set():
                    try:
                        chunks.put(data, timeout=0.1)
                        break
                    except queue.Full:
                        continue
                if not data:
                    return
        except Exception:
            while not stop.is_set():
                try:
                    chunks.put(Rejected('stream read failed'), timeout=0.1)
                    return
                except queue.Full:
                    continue
    try:
        for label in ('stdout', 'stderr'):
            path = run / (label + '-' + uuid.uuid4().hex + '.raw')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            logs.append(os.fdopen(fd, 'wb'))
        # Start before producer thread: preexec resource limits run single-threaded.
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=home,
                                   env={'HOME': str(home), 'TMPDIR': str(home), 'LANG': 'C', 'LC_ALL': 'C'},
                                   close_fds=True, start_new_session=True, preexec_fn=_limits)
        for stream, label in ((process.stdout, 0), (process.stderr, 1)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE, 2)
        worker = threading.Thread(target=produce, daemon=True)
        worker.start()
        deadline, output, verified, pending = time.monotonic() + seconds, 0, False, b''
        advances = 0
        while selector.get_map():
            require(time.monotonic() < deadline, 'decoder wall-time exceeded')
            require(cancel is None or not cancel.is_set(), 'decode cancelled')
            memory.check(process)
            for key, _ in selector.select(timeout=0.05):
                if key.data == 2:
                    if not pending:
                        try:
                            data = chunks.get_nowait()
                        except queue.Empty:
                            continue
                        if isinstance(data, Exception):
                            raise data
                        if not data:
                            check.finish()
                            verified = True
                            selector.unregister(process.stdin)
                            process.stdin.close()
                            continue
                        check.feed(data)
                        pending = data
                    try:
                        written = os.write(process.stdin.fileno(), pending)
                        pending = pending[written:]
                    except BlockingIOError:
                        pass
                    except BrokenPipeError:
                        raise Rejected('decoder closed input early') from None
                    continue
                data = os.read(key.fileobj.fileno(), CHUNK)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                output += len(data)
                require(output <= MAX_OUTPUT, 'decoder output bound exceeded')
                logs[key.data].write(data)
                if key.data == 0:
                    for progress in parser.feed(data):
                        advances += 1
                        if observe:
                            observe(progress, process.poll() is None, verified)
            if process.poll() is not None and process.stdin and not process.stdin.closed:
                raise Rejected('decoder exited before validated input EOF')
        require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0,
                'decoder failed')
        require(verified and advances >= 2 and parser.last.frame > 0 and not parser.buffer,
                'missing verified advancing decoded frames')
        return {'decoder_only': True, 'frames': parser.last.frame, 'media_us': parser.last.media_us,
                'bytes': check.count, 'sha256': check.hash.hexdigest(), 'pid': process.pid,
                'returncode': process.returncode, 'private_logs': str(run)}
    finally:
        stop.set()
        if process is not None:
            if process.poll() is None:
                process.terminate()  # exact owned PID, never pkill/process-group discovery
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()
        source.close()
        if worker is not None:
            worker.join(timeout=2)
        selector.close()
        for log in logs:
            log.close()
        shutil.rmtree(home)
        require(worker is None or not worker.is_alive(), 'source failed bounded cancellation')


def main():
    # Deliberately no --receipt/--url/--credential switch: no reviewed integration
    # or current media activation grant exists. Do not invent a receipt schema.
    raise SystemExit('BLOCKED: reviewed scoped receipt and parent live integration required; decoder component only')


if __name__ == '__main__':
    main()
