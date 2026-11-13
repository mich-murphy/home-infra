#!/usr/bin/env python3
"""Offline-prepared native headless adapter. CLI activation remains BLOCKED.

Unit contracts are not app evidence. This module never authorizes activation,
changes app settings, or substitutes browser receipts. No imports read state.
"""
import hashlib
import importlib
import json
import subprocess
import sys
import os
import socket
import signal
from pathlib import Path
import time
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))

h = importlib.import_module('talos-proof-media-headless')
s = importlib.import_module('talos-proof-media-safety')
p = importlib.import_module('talos-proof-media-playback')
d = importlib.import_module('talos-proof-media-dependencies')
MODE = 'plex-tautulli-native-headless-v1'
GROUP = 'media-plex-tautulli'
LIMITS = {'plex': 512, 'tautulli': 192}
ACTION_SECONDS = 3
WORKER_CLEANUP_SECONDS = 2
WORKER_TERM_GRACE_SECONDS = 1


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def validate_receipt(receipt, binding, templates, now=None):
    """Pure proposed receipt contract, NOT a grant or activation interface.

    Bind full templates, not only main-container limits. Existing lease() owns
    exact endpoint/context/node identity checks; existing guard owns both fresh
    independent memory measurements and exclusivity. Never refresh either.
    """
    now = time.time() if now is None else now
    expected = {'mode': MODE, 'client': binding['client'], 'session': binding['session'],
                'item': binding['item'], 'media_path': binding['media_path'],
                'fixture_sha256': h.FIXTURE_SHA256, 'fixture_bytes': h.FIXTURE_BYTES,
                'decoder_path': binding['ffmpeg'], 'decoder_sha256': binding['decoder_sha256'],
                'expires': receipt.get('expires'), 'limits_mib': LIMITS,
                'reserve_mib': 192, 'total_mib': 896,
                'pod_templates_sha256': {k: canonical_sha(v) for k, v in templates.items()},
                'darwin_rss_watchdog_not_hard_ceiling': True}
    h.Identity(binding['client'], binding['session'], binding['item'])
    h.require(receipt.get('group') == GROUP and s.number(receipt.get('expires')) and
              receipt['expires'] > now and canonical_sha(receipt.get('headless')) == canonical_sha(expected),
              'exact new headless receipt required; browser/other receipts forbidden')
    h.require(set(templates) == set(LIMITS), 'exact two templates required')
    for name, template in templates.items():
        actual = s.resources.effective_limits(template['spec'])['memory']
        h.require(actual == LIMITS[name] * s.resources.MIB,
                  'full PodTemplate budget differs from headless plan')
    h.require(h.command(binding['ffmpeg'])[0] == binding['ffmpeg'], 'decoder path changed')
    with open(binding['ffmpeg'], 'rb') as decoder:
        digest = hashlib.file_digest(decoder, 'sha256').hexdigest()
    h.require(digest == binding['decoder_sha256'], 'decoder hash changed')


def aggregate_admission(controllers, pods):
    """Conservative snapshot admission, not rollout/exclusivity authority.

    Include terminal/terminating duplicates; no per-Pod or desired-replica-only
    sum. Live wiring must additionally prevent changes between snapshots.
    """
    templates = {}
    total = 0
    for name, limit in LIMITS.items():
        selected = [c for c in controllers if c['metadata']['namespace'] == 'proof-' + name]
        h.require(len(selected) == 1, 'unsupported controller cardinality')
        c = selected[0]
        spec = c['spec']
        h.require(c['metadata']['name'] == name and spec.get('replicas') == 1 and
                  not c['metadata'].get('deletionTimestamp'), 'unsupported replica/deleting controller')
        h.require((c['kind'] == 'Deployment' and spec.get('strategy') == {'type': 'Recreate'}) or
                  (c['kind'] == 'StatefulSet' and spec.get('updateStrategy') == {'type': 'OnDelete'}),
                  'surge/rolling or unknown update strategy unsupported')
        templates[name] = spec['template']
        actual = [p for p in pods if p['metadata']['namespace'] == 'proof-' + name]
        h.require(len(actual) == 1, 'all simultaneous Pods including terminating duplicates required')
        pod = actual[0]
        h.require(not pod['metadata'].get('deletionTimestamp'), 'terminating Pod unsupported')
        owners = pod['metadata'].get('ownerReferences', [])
        h.require(len(owners) == 1 and owners[0].get('controller') is True,
                  'unowned or ambiguous Pod unsupported')
        memory = s.resources.effective_limits(pod['spec'])['memory']
        h.require(memory == limit * s.resources.MIB, 'actual pod budget drift')
        total += memory
    h.require(total + 192 * s.resources.MIB <= 896 * s.resources.MIB,
              'aggregate simultaneous Pod budget exceeded')
    return templates


def guard(binding):
    # Do not modify general group budgets/profiles to get admission. The old
    # aggregate happens to equal 896 but its component limits are NOT authority.
    receipt = s.guard(GROUP)
    s.require_helpers_deleted(GROUP)
    controllers = json.loads(s.kubectl_read('get', 'deployments,statefulsets', '-A', '-o', 'json'))['items']
    pods = json.loads(s.kubectl_read('get', 'pods', '-A', '-o', 'json'))['items']
    templates = aggregate_admission(controllers, pods)
    validate_receipt(receipt, binding, templates)
    return receipt


class BoundedAPI:
    """Existing verified API transport with bounded body and socket reads.

    Total deadline (including trickling headers/body) is enforced by Worker.
    """
    def __init__(self, api):
        self.api = api

    def call(self, *args, **kwargs):
        return self.api.call(*args, **kwargs, max_bytes=32768, timeout=1)


class Native:
    """Runs only in one owned serial API process, never decoder callbacks."""
    def __init__(self, binding):
        self.binding = binding
        self.identity = h.Identity(binding['client'], binding['session'], binding['item'])
        self.state = s.private_dir(Path(binding['state']))
        self.ca = s.private_file(Path(binding['ca']))
        self.credentials = json.loads(s.read_private(self.state / 'credentials.json'))
        self.plex = d.api_for('plex', self.ca, self.credentials)
        self.plex.headers.update(self.identity.headers())
        self.plex = BoundedAPI(self.plex)
        self.tautulli = BoundedAPI(d.api_for('tautulli', self.ca, self.credentials))

    def call(self, action, payload):
        guard(self.binding)
        if action == 'baseline':
            marker = json.loads(s.read_private(self.state / 'plex-functional.json'))
            h.require(str(marker['item_id']) == self.identity.item, 'scanned item changed')
            # Do not guess/change Tautulli's native polling/history configuration.
            # Its settings/source preflight is a separate future review gate.
            rows = self.history()
            h.require(not rows, 'nonempty baseline needs reviewed pagination; never reset history')
            return rows
        if action in ('playing', 'stopped'):
            if action == 'playing':
                os.kill(payload['pid'], 0)  # exact owned decoder PID, immediately before native request
            media_us = payload['media_us']
            h.require(type(media_us) is int and 0 <= media_us <= 12021354,
                      'timeline must use actual bounded decoder media time')
            query = {'ratingKey': self.identity.item, 'key': '/library/metadata/' + self.identity.item,
                     'state': action, 'time': media_us // 1000, 'duration': 12021,
                     'session': self.identity.session, 'X-Plex-Client-Identifier': self.identity.client}
            self.plex.call('/:/timeline?' + urllib.parse.urlencode(query), raw=True)
            if action == 'stopped':
                guard(self.binding)
                sessions = d.xml(self.plex, '/status/sessions')
                h.require(not any(x.get('machineIdentifier') == self.identity.client and
                                  x.get('state') == 'playing' for x in sessions.iter('Player')),
                          'same client still playing after actual stop')
            return True
        if action == 'activity':
            return p.tautulli_call(self.tautulli, self.credentials['tautulli'],
                                   'get_activity')['sessions']
        if action == 'history':
            return self.history()
        raise h.Rejected('unsupported native action')

    def history(self):
        guard(self.binding)
        rows = p.tautulli_call(self.tautulli, self.credentials['tautulli'], 'get_history',
                              rating_key=self.identity.item, include_activity=0)['data']
        h.require(len(rows) <= 100 and all(r.get('row_id') is not None for r in rows),
                  'unsupported baseline history shape/pagination')
        return rows


def serve(connection, binding):
    """No detached threads. Parent enforces total deadline, including TLS/reads."""
    try:
        reader = connection.makefile('rb')
        guard(binding)  # validate authority before any credential/private state read
        native = Native(binding)
        connection.settimeout(None)  # parent bounds every action and total run lifetime
        while True:
            line = reader.readline(4097)
            if not line:
                return
            h.require(len(line) <= 4096 and line.endswith(b'\n'), 'invalid owned request')
            action, payload = json.loads(line)
            try:
                result = native.call(action, payload)
                encoded = json.dumps(result).encode()
                h.require(len(encoded) <= 32768, 'native result exceeds IPC bound')
                connection.sendall(json.dumps(['ok', result]).encode() + b'\n')
            except Exception:
                connection.sendall(b'["failed", null]\n')  # no credentials/raw exceptions in IPC
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        # Never print secret-bearing exception diagnostics from the owned worker.
        try:
            connection.sendall(b'["failed", null]\n')
        except OSError:
            pass
    finally:
        connection.close()


def worker_command(fd):
    return [sys.executable, '-I', '-S', str(Path(__file__).resolve()), '--owned-worker', str(fd)]


def worker_binding(connection):
    # Bootstrap never reads ahead into a subsequent action.
    data = b''
    while not data.endswith(b'\n'):
        chunk = connection.recv(1)
        h.require(chunk and len(data) < 4096, 'invalid owned bootstrap')
        data += chunk
    return json.loads(data)


class Worker:
    """One action in flight. Nonblocking poll; timeout is an UNKNOWN outcome.

    Local kill/reap cannot cancel a server-accepted request or prove ordering.
    A timed-out request remains UNRESOLVED remote completion, even after local
    reap or a later stop acknowledgement: no acceptance, never retry playing.
    """
    # Exclusive waiter ownership is a caller precondition: no foreign waitpid,
    # SIGCHLD handler/auto-reaping, or access to _process before close completes.
    # Python can check the visible SIGCHLD policy, not arbitrary foreign waiters
    # or a native SA_NOCLDWAIT policy. This is NOT protection against those.
    @staticmethod
    def require_wait_policy():
        h.require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
                  'owned API cleanup UNKNOWN: default SIGCHLD policy required')

    def __init__(self, binding):
        self.require_wait_policy()  # before spawning or allocating IPC
        # Serialization can fail; do it before owning any process or sockets.
        data = json.dumps(binding).encode() + b'\n'
        h.require(len(data) <= 4096, 'bounded owned worker bootstrap failed')
        self.connection, child = socket.socketpair()
        self._process = None
        self.buffer = b''
        self.pending = None
        self.closed = False
        self.cleanup_unknown = False
        try:
            self.connection.setblocking(False)
            self._process = subprocess.Popen(worker_command(child.fileno()),
                                            pass_fds=(child.fileno(),), close_fds=True,
                                            start_new_session=True,
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
            child.close()
            h.require(self.connection.send(data) == len(data),
                      'bounded owned worker bootstrap failed')
        except Exception as error:
            # Independent closes: failure of one must not skip the other or
            # process cleanup. Preserve the original bootstrap exception.
            for endpoint in (child, self.connection):
                try:
                    endpoint.close()
                except Exception:
                    error.add_note('owned API IPC cleanup UNKNOWN after bootstrap failure')
            if self._process is not None:
                try:
                    self.close()
                except Exception:
                    error.add_note('owned API cleanup UNKNOWN after bootstrap failure')
            raise

    def submit(self, action, payload=None):
        h.require(self.pending is None, 'overlapping API actions forbidden')
        data = json.dumps([action, payload or {}]).encode() + b'\n'
        h.require(len(data) <= 4096, 'owned request exceeds bound')
        h.require(self.connection.send(data) == len(data), 'partial API submission/unknown outcome')
        self.pending = (action, time.monotonic() + ACTION_SECONDS)

    def poll(self):
        if self.pending is None:
            return None
        h.require(time.monotonic() < self.pending[1], 'API deadline/unknown outcome; no acceptance')
        try:
            data = self.connection.recv(32769)
        except BlockingIOError:
            data = None
        h.require(data != b'', 'API worker closed/unknown outcome')
        if data:
            self.buffer += data
        h.require(len(self.buffer) <= 32768, 'API IPC result exceeds bound')
        if b'\n' not in self.buffer:
            # Never reap the session leader here: retain its identity until
            # the last group signal. EOF or action expiry detects failure.
            return None
        line, self.buffer = self.buffer.split(b'\n', 1)
        h.require(not self.buffer, 'unexpected extra API reply')
        status, result = json.loads(line)
        action, self.pending = self.pending[0], None
        h.require(status == 'ok', 'native API failed/unknown outcome')
        return action, result

    def wait(self):
        while True:
            result = self.poll()
            if result is not None:
                return result[1]
            time.sleep(0.01)  # bounded local IPC only; never used for CI

    def _require_signal_ownership(self):
        self.require_wait_policy()
        h.require(self._process.returncode is None,
                  'owned API cleanup UNKNOWN: leader already reaped')
        # Successful Popen(start_new_session=True) establishes PID=SID=PGID.
        # Do not query zombie SID/PGID: Darwin may return ESRCH before reap.
        # Retained unreaped lifetime, not a liveness query, pins this identity.

    def close(self):
        if self.closed:
            h.require(not self.cleanup_unknown, 'owned API cleanup UNKNOWN')
            return
        self.closed = True
        deadline = time.monotonic() + WORKER_CLEANUP_SECONDS
        failed = False
        try:
            self.connection.close()
        except Exception:
            failed = True  # IPC failure must not skip independent process cleanup
        # Do not poll/wait between TERM and KILL, even when the leader exits.
        # Its unreaped lifetime pins this numeric PID/PGID under the exclusive
        # ownership precondition. No discovery, escaped-group claim, or remote
        # cancellation claim. A changed/known-reaped identity fails closed.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                self._require_signal_ownership()
            except Exception:
                # Do not initiate waitpid either: waiter ownership is unknown.
                # Retain the handle for explicit owner disposition, not cleanup.
                self.cleanup_unknown = True
                raise h.Rejected('owned API cleanup UNKNOWN: ownership lost') from None
            try:
                os.killpg(self._process.pid, sig)
            except ProcessLookupError:
                pass  # the unreaped group may have no live members
            except OSError:
                failed = True
            if sig == signal.SIGTERM:
                grace = min(deadline, time.monotonic() + WORKER_TERM_GRACE_SECONDS)
                while time.monotonic() < grace:
                    time.sleep(min(0.01, max(0, grace - time.monotonic())))
        # This is the only reaping site. No group signals may follow it.
        try:
            remaining = deadline - time.monotonic()
            h.require(remaining > 0, 'owned API cleanup budget exhausted')
            self._process.wait(timeout=remaining)
        except Exception:
            failed = True
        self.cleanup_unknown = failed or self._process.returncode is None
        h.require(not self.cleanup_unknown, 'owned API cleanup UNKNOWN')


class Pump:
    """Only nonblocking worker IPC on decoder pump; no HTTP or target reads."""
    def __init__(self, worker, identity, baseline, expires):
        self.worker, self.identity = worker, identity
        self.expires = expires
        self.life = h.Lifecycle(identity, baseline)
        self.process = None
        self.ready_activity = None
        self.wait_watermark = False
        self.required_epoch = 0
        self.watermark_batch = None
        self.latest = h.Progress(0, 0)

    def tick(self, process, progress, verified):
        h.require(time.time() < self.expires, 'headless lease expired during decode')
        self.process = process
        result = self.worker.poll()
        if result:
            action, value = result
            if action == 'playing':
                h.require(value is True and process.poll() is None, 'playing returned after decoder exit')
                self.worker.submit('activity')
            elif action == 'activity':
                h.require(process.poll() is None, 'activity returned after decoder exit')
                # DO NOT use progress here: it can be queued before the response.
                self.ready_activity = value
                self.wait_watermark = True
                self.required_epoch = progress.epoch + 1
                return True  # request bounded pipe drain/parser quarantine

    def observe(self, progress, alive, verified):
        self.latest = progress
        if not alive:
            h.require(self.life.stage == 'concurrent' and not self.wait_watermark,
                      'decoder ended before concurrent activity proof')
            return  # terminal reports may supply stop time, never concurrency
        if progress.epoch < self.required_epoch:
            return  # includes complete parser batches queued before the reply
        if self.watermark_batch == (progress.epoch, progress.batch):
            return  # ALL records in the watermark batch are conservative backlog
        if self.wait_watermark:
            # First complete report consumed AFTER response is only a watermark;
            # even if FFmpeg had queued it before response, it earns no concurrency.
            self.life.activity(self.ready_activity, self.process.poll() is None, progress)
            self.wait_watermark = False
            self.watermark_batch = (progress.epoch, progress.batch)
            self.life.previous = progress
            return
        self.life.advanced(progress, alive, verified)
        if self.life.stage == 'new' and verified and self.life.advances >= 2:
            actual = self.life.playing(self.identity, self.process.poll() is None, verified)
            self.worker.submit('playing', {'media_us': actual.media_us, 'pid': self.process.pid})


def run(binding, api, private_root):
    """Prepared adapter, NOT an activation entrypoint. Fixed input; no overrides.

    Caller must first supply reviewed native settings/source preflight and
    supported profile activation wiring. CLI intentionally cannot invoke this.
    """
    raise h.Rejected('HOLD: upstream progress flush semantics, same-session native source '
                     'contract and end-to-end deadline are not reviewed; no runtime adapter')
    receipt = guard(binding)
    identity = h.Identity(binding['client'], binding['session'], binding['item'])
    worker = Worker(binding)
    pump = None
    try:
        worker.submit('baseline')
        baseline = worker.wait()
        pump = Pump(worker, identity, [row['row_id'] for row in baseline], receipt['expires'])
        guard(binding)
        source = h.open_plex_stream(api, binding['media_path'], identity)
        try:
            result = h.decode(source, binding['ffmpeg'], private_root,
                              observe=pump.observe, pump=pump.tick)
        finally:
            source.close()  # also covers decoder setup/validation failures
        h.require(worker.pending is None and pump.life.stage == 'concurrent',
                  'missing after-response concurrent live decode')
        worker.submit('stopped', {'media_us': result['media_us']})
        pump.life.stopped(identity, False, result['returncode'], worker.wait())
        # Bounded actual history polling; no stale rows or wall-time duration.
        for _ in range(5):
            worker.submit('history')
            rows = worker.wait()
            fresh = [r for r in rows if str(r['row_id']) not in pump.life.baseline and
                     str(r.get('rating_key')) == identity.item and r.get('machine_id') == identity.client]
            if fresh:
                pump.life.history(fresh)
                break
            time.sleep(0.2)
        h.require(pump.life.stage == 'complete', 'no unique positive native durable history')
        return {'mode': MODE, 'native_lifecycle': True, 'decoder': result}
    finally:
        # Drain by cancellation/reap BEFORE cleanup, never racing two local actions.
        worker.close()
        # No automatic remote cleanup after failure/unknown HTTP completion.
        # A later stop ACK would not resolve an earlier server-accepted playing
        # request. Local reap is ONLY local cleanup, not remote completion.


def main():
    raise SystemExit('BLOCKED: unsupported 512/192 full-template activation wiring; '
                     'new exact headless receipt and captured native Tautulli settings/API/fixture '
                     'preflight required. No state read and no activation grant.')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--owned-worker':
        connection = socket.socket(fileno=int(sys.argv[2]))
        connection.settimeout(ACTION_SECONDS)
        serve(connection, worker_binding(connection))
    else:
        main()
