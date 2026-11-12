#!/usr/bin/env python3
"""Optional workstation OTP loopback fixture, NOT Pinchflat/native acceptance.

TALOS_PROOF_TEST_OTP must name an explicitly selected workstation OTP prefix.
Only exact subprocess PIDs are terminated; no global epmd, cookie file or pkill.
"""
import os
from pathlib import Path
import secrets
import selectors
import socket
import subprocess
import tempfile
import time
import unittest
import uuid


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@unittest.skipUnless(os.environ.get('TALOS_PROOF_TEST_OTP'), 'explicit workstation OTP required')
class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['TALOS_PROOF_TEST_OTP'])
        cls.temp = tempfile.TemporaryDirectory(prefix='proof-otp-loopback-')
        cls.processes = []
        cls.addClassCleanup(cls.cleanup)
        epmd_port, dist_port = port(), port()
        while dist_port == epmd_port:
            dist_port = port()
        cls.cookie = secrets.token_hex(24)
        # Do not load a user's .erlang/.erlang.cookie, ERL_* startup flags or
        # libraries. This is a disposable fixture, never their existing node.
        cls.env = dict(PATH=os.defpath, HOME=cls.temp.name, TMPDIR=cls.temp.name,
            LANG='C.UTF-8', ERL_EPMD_PORT=str(epmd_port), ERL_EPMD_ADDRESS='127.0.0.1',
            ERL_CRASH_DUMP=str(Path(cls.temp.name)/'erl-crash.dump'))
        private = lambda path, flags: os.open(path, flags, 0o600)
        cls.epmd_log = open(Path(cls.temp.name)/'epmd.log', 'xb', opener=private)
        epmd = subprocess.Popen([str(cls.root/'bin/epmd'), '-port', str(epmd_port), '-address', '127.0.0.1'],
                                env=cls.env, stdout=cls.epmd_log, stderr=cls.epmd_log, umask=0o077)
        cls.processes.append(epmd)
        deadline = time.monotonic()+10
        while True:
            if epmd.poll() is not None:
                raise RuntimeError('owned epmd exited')
            try:
                with socket.create_connection(('127.0.0.1', epmd_port), timeout=.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError('owned epmd readiness timeout')
                time.sleep(.05)
        cls.node_log = open(Path(cls.temp.name)/'node-stderr.log', 'xb', opener=private)
        elixir = os.environ.get('TALOS_PROOF_TEST_ELIXIR')
        extra = ['-pa', *[str(p) for p in Path(elixir).glob('lib/*/ebin')]] if elixir else []
        startup = 'io:format("READY~n"), timer:sleep(infinity).'
        if elixir:
            startup = '{ok,_}=application:ensure_all_started(elixir), '+startup
        node = subprocess.Popen([str(cls.root/'bin/erl'), *extra, '+S', '1', '+A', '1', '-noshell',
            '-start_epmd', 'false', '-sname', 'proof_'+uuid.uuid4().hex+'@localhost',
            '-setcookie', cls.cookie, '-kernel', 'inet_dist_use_interface', '{127,0,0,1}',
            'inet_dist_listen_min', str(dist_port), 'inet_dist_listen_max', str(dist_port),
            '-eval', startup], env=cls.env,
            cwd=cls.temp.name, stdout=subprocess.PIPE, stderr=cls.node_log, umask=0o077)
        cls.processes.append(node)
        with selectors.DefaultSelector() as selector:
            selector.register(node.stdout, selectors.EVENT_READ)
            if not selector.select(15) or node.stdout.readline() != b'READY\n':
                raise RuntimeError('owned loopback node readiness failed')
        cls.address = '127.0.0.1:'+str(dist_port)
        cls.version = subprocess.run([str(cls.root/'bin/erl'), '-version'], capture_output=True,
                                     env=cls.env, cwd=cls.temp.name, umask=0o077,
                                     timeout=10, check=True).stderr.decode().strip()
        print('WORKSTATION ONLY:', cls.version, 'owned PIDs', [p.pid for p in cls.processes])

    @classmethod
    def cleanup(cls):
        for process in reversed(cls.processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.stdout:
                process.stdout.close()
        for name in ('epmd_log', 'node_log'):
            if hasattr(cls, name):
                getattr(cls, name).close()
        cls.temp.cleanup()

    def call(self, *args, data=None):
        return subprocess.run([str(self.root/'bin/erl_call'), '-address', self.address,
            '-c', self.cookie, '-R', '-timeout', '5', *args], input=data,
            env=self.env, capture_output=True, timeout=10)

    def test_e_without_trailing_whitespace_hides_error_when_result_suppressed(self):
        source = b'io:format("PROOF_JSON:{}~n").'
        hidden = self.call('-e', '-fetch_stdout', '-no_result_term', data=source)
        visible = self.call('-e', '-fetch_stdout', data=source)
        self.assertEqual(hidden.returncode, 0)
        self.assertEqual(hidden.stdout, b'')
        self.assertEqual(visible.returncode, 0)
        self.assertIn(b'Incomplete form', visible.stdout)
        self.assertNotIn(b'PROOF_JSON:', visible.stdout)

    def test_e_with_newline_forwards_stdout_and_keeps_result(self):
        result = self.call('-e', '-fetch_stdout', data=b'io:format("PROOF_JSON:{}~n").\n')
        self.assertEqual(result.returncode, 0, result.stderr.decode().replace(self.cookie, '[TEST_COOKIE]'))
        self.assertIn(b'PROOF_JSON:{}\n', result.stdout)
        self.assertIn(b'{ok, ok}', result.stdout)

    @unittest.skipUnless(os.environ.get('TALOS_PROOF_TEST_ELIXIR'), 'explicit workstation Elixir required')
    def test_elixir_mfa_numeric_charlist_and_runtime_exception_are_visible(self):
        code='(fn -> IO.puts("PROOF_JSON:{}"); :proof_rpc_ok end).()'
        mfa='Elixir.Code eval_string [['+','.join(str(ord(x)) for x in code)+']]'
        result=self.call('-a',mfa,'-fetch_stdout')
        self.assertEqual(result.returncode,0,result.stderr.decode().replace(self.cookie,'[TEST_COOKIE]'))
        self.assertIn(b'PROOF_JSON:{}',result.stdout)
        self.assertIn(b'{proof_rpc_ok, []}',result.stdout)
        code='raise "proof_elixir_failure"'
        mfa='Elixir.Code eval_string [['+','.join(str(ord(x)) for x in code)+']]'
        failure=self.call('-a',mfa,'-fetch_stdout')
        self.assertEqual(failure.returncode,0)
        self.assertIn(b'badrpc',failure.stdout)
        self.assertIn(b'Elixir.RuntimeError',failure.stdout)
        self.assertIn(','.join(str(x) for x in b'proof_elixir_failure').encode(),failure.stdout)
        self.assertNotIn(b'PROOF_JSON:',failure.stdout)

    def test_documented_mfa_forwards_stdout_without_eval_str_and_preserves_error_term(self):
        argument = 'io format [['+','.join(str(x) for x in b'PROOF_JSON:{}~n')+']]'
        result = self.call('-a', argument, '-fetch_stdout')
        self.assertEqual(result.returncode, 0, result.stderr.decode().replace(self.cookie, '[TEST_COOKIE]'))
        self.assertIn(b'PROOF_JSON:{}\n', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith(b'ok'))
        error = self.call('-a', 'erlang error [proof_transport_failure]', '-fetch_stdout')
        self.assertEqual(error.returncode, 0)  # Transport success != application success.
        self.assertIn(b'badrpc', error.stdout)
        self.assertIn(b'proof_transport_failure', error.stdout)


if __name__ == '__main__':
    unittest.main()
