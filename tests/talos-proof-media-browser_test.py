#!/usr/bin/env python3
"""Offline browser safety/immutable-fixture checks; never a live browser PASS."""
import importlib
from pathlib import Path
import subprocess
import socket
import ssl
import threading
import hashlib
import base64
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
browser = importlib.import_module('talos-proof-media-browser')
fixture = importlib.import_module('talos-proof-media-fixture')
safety = importlib.import_module('talos-proof-media-safety')


class BrowserPreparation(unittest.TestCase):
    def test_exact_dependency_membership_and_original_exclusivity(self):
        cases = [('qbittorrent', None, 'qbittorrent'), ('plex', None, 'plex'),
                 ('plex', 'media-plex-tautulli', 'media-plex-tautulli'),
                 ('jellyfin', 'media-plex-jellyplex', 'media-plex-jellyplex')]
        for service, group, expected in cases:
            with patch.object(safety, 'lease') as lease, patch.object(safety, 'exclusivity') as exclusive:
                self.assertEqual(browser.check_lease(service, group), expected)
                lease.assert_called_once_with(expected)
                exclusive.assert_called_once_with(expected)
        for service, group in [('qbittorrent', 'media-plex-tautulli'), ('plex', 'media-seerr-request'),
                               ('jellyfin', 'media-plex-tautulli'), ('plex', 'qbittorrent'),
                               ('plex', 'invented-group'), ('unknown', 'media-plex-tautulli')]:
            with patch.object(safety, 'lease') as lease:
                with self.assertRaises(ValueError):
                    browser.check_lease(service, group)
                lease.assert_not_called()
        # Full shared-group cost remains unchanged; browser cannot grant admission.
        self.assertEqual(sum(safety.BUDGET[x] for x in safety.DEPENDENCY_BATCHES['media-plex-tautulli']) + 192, 896)

    def test_sid_value_equality_without_emission(self):
        module = (ROOT / 'tests/talos-proof-media-cookie.mjs').as_uri()
        source = """import {sameSID,authenticatedSID} from 'MODULE';
        const c={name:'SID',value:'test-only-valid',domain:'qbittorrent.proof.invalid',path:'/',secure:true};
        const sid=authenticatedSID([c],'https://qbittorrent.proof.invalid');
        if(!sameSID('other=x; SID='+sid,sid)) process.exit(1);
        const actual=authenticatedSID([{...c,name:'QBT_SID_8080',secure:false}],'https://qbittorrent.proof.invalid','QBT_SID_8080');
        if(!sameSID('QBT_SID_8080='+actual,actual,'QBT_SID_8080') || sameSID('SID='+actual,actual,'QBT_SID_8080')) process.exit(4);
        for(const header of ['', 'SID=', 'SID=wrong', 'SID='+sid+'; SID='+sid]) {
          if(sameSID(header,sid)) process.exit(2);
        }
        for(const cookies of [[],[c,c],[{...c,value:''}],[{...c,domain:'hostile.proof.invalid'}]]) {
          let refused=false;try {authenticatedSID(cookies,'https://qbittorrent.proof.invalid');} catch {refused=true;}
          if(!refused) process.exit(3);
        }
        """.replace('MODULE', module)
        result = subprocess.run(['node', '--input-type=module', '-e', source], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, b'')

    def test_host_allowlist_before_connect(self):
        with patch('socket.create_connection', side_effect=AssertionError('must not dial')):
            for host in ['production.invalid', 'plex.proof.invalid:18443', '127.0.0.1']:
                with self.assertRaises(ValueError):
                    browser.verified_spki('/unused', host)

    def test_fixture_immutable_and_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            legacy = state / 'Proof Fixture (2000).mp4'
            legacy.write_bytes(b'old fixture retained')
            command_result = subprocess.CompletedProcess([], 0, b'new offline test MP4', b'')
            with patch('subprocess.run', return_value=command_result) as run:
                path = fixture.browser_video(state, '/bin/sh', safety)
                command = run.call_args.args[0]
                self.assertIn('libx264', command)
                self.assertIn('baseline', command)
                self.assertIn('12', command)
                self.assertEqual(path.name, fixture.BROWSER_VIDEO)
                self.assertEqual(legacy.read_bytes(), b'old fixture retained')
                with self.assertRaises(RuntimeError):
                    fixture.browser_video(state, '/bin/sh', safety)
                self.assertEqual(run.call_count, 1)

    def test_no_unverified_global_tls_or_late_routing(self):
        source = (ROOT / 'tests/talos-proof-media-browser.mjs').read_text()
        self.assertNotIn("'--ignore-certificate-errors'", source)
        self.assertNotIn('ignoreHTTPSErrors:true', source)
        self.assertIn('--ignore-certificate-errors-spki-list=${input.spki}', source)
        self.assertLess(source.index("context.route('**/*'"), source.index('context.newPage()'))
        self.assertLess(source.index("context.routeWebSocket('**/*'"), source.index('context.newPage()'))
        self.assertIn("ws=>ws.close()", source)
        self.assertIn("hostile request carried real authenticated SID", source)
        self.assertNotIn('setExtraHTTPHeaders', source)
        self.assertIn("serviceWorkers:'block'", source)

    def test_decoder_not_http_only_and_no_native_claim(self):
        source = (ROOT / 'tests/talos-proof-media-player.mjs').read_text()
        for required in ['requestVideoFrameCallback', 'presentedFrames', 'seekFrame<6.5',
                         'video.currentTime>=8', 'native_player_ui_proved:false',
                         'application_progress_proved:false', 'audio_output_proved:false']:
            self.assertIn(required, source)


class IndependentSPKI(unittest.TestCase):
    def test_verified_leaf_key_and_wrong_ca_hostname_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            for name in ['trusted', 'wrong']:
                subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                                '-days', '1', '-subj', '/CN=plex.proof.invalid', '-addext',
                                'subjectAltName=DNS:plex.proof.invalid', '-keyout', str(state / (name + '.key')),
                                '-out', str(state / (name + '.crt'))], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                (state / (name + '.crt')).chmod(0o600)
            server = socket.socket()
            server.bind(('127.0.0.1', 0));server.listen(3);server.settimeout(10)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(state / 'trusted.crt', state / 'trusted.key')
            errors = []
            def serve():
                for _ in range(3):
                    try:
                        connection, _ = server.accept()
                        with connection:
                            try:
                                with context.wrap_socket(connection, server_side=True):
                                    pass
                            except ssl.SSLError:
                                pass  # expected client CA/hostname rejection
                    except Exception as exc:
                        errors.append(type(exc).__name__)
            thread = threading.Thread(target=serve, daemon=True);thread.start()
            original = socket.create_connection
            def local(address, timeout=15):
                self.assertEqual(address, ('127.0.0.1', 18443))
                return original(server.getsockname(), timeout=timeout)
            try:
                with patch('socket.create_connection', side_effect=local):
                    actual = browser.verified_spki(state / 'trusted.crt', 'plex.proof.invalid')
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        browser.verified_spki(state / 'wrong.crt', 'plex.proof.invalid')
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        browser.verified_spki(state / 'trusted.crt', 'jellyfin.proof.invalid')
                public = subprocess.run(['openssl', 'pkey', '-in', str(state / 'trusted.key'), '-pubout',
                                         '-outform', 'DER'], capture_output=True, check=True).stdout
                self.assertEqual(actual, base64.b64encode(hashlib.sha256(public).digest()).decode())
            finally:
                thread.join(timeout=12);server.close()
            self.assertFalse(thread.is_alive())
            self.assertFalse(errors)


if __name__ == '__main__':
    unittest.main()
