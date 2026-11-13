#!/usr/bin/env python3
"""Mandatory workstation PHP filesystem regression; never execute the application.

TALOS_PROOF_TEST_PHP must be the absolute project-locked Nix PHP executable.
Only extracted function declarations run in a fresh private fixture. The literal
/proof mount is relocated in this test copy; production has no path override.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'docs/evidence/talos-data/nextcloud-packaged-metadata-bridge-49e437a1-23fe-491f-92e9-541137daaa6a.json'
EXPECTED = '86a6fd499c4bc438efc6cc0e4b87b11b69c8c21b111de29c6f2fce3d73bde32c'
KEY = 'packaged-metadata.json'
STAMP = '..2026_11_12_05_00_00.1234567890'


class ProjectedMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tool = os.environ.get('TALOS_PROOF_TEST_PHP', '')
        if not tool or not Path(tool).is_absolute():
            raise RuntimeError('absolute TALOS_PROOF_TEST_PHP from locked project Nix PHP is required; no skips')
        cls.php = Path(tool)
        if not str(cls.php.resolve()).startswith('/nix/store/') or not os.access(cls.php, os.X_OK):
            raise RuntimeError('TALOS_PROOF_TEST_PHP must be an executable from the locked Nix store')
        cls.source = (ROOT / 'scripts/talos-proof-nextcloud-cron.php').read_text()
        cls.functions = cls.source.split('final class GateFailure', 1)[1].split('function exclusive(', 1)[0]
        cls.functions = 'final class GateFailure' + cls.functions
        if cls.functions.count("$mount = '/proof';") != 1:
            raise RuntimeError('fixed production mount declaration changed; review fixture extraction')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='talos-proof-projection-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.home.chmod(0o700)
        self.assertNotIn(ROOT, self.home.parents)
        self.mount = self.home / 'mount'
        self.mount.mkdir(mode=0o700)
        directory = self.mount / STAMP
        directory.mkdir(mode=0o700)
        self.target = directory / KEY
        self.write(self.target, BRIDGE.read_bytes())
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), EXPECTED)
        (self.mount / '..data').symlink_to(STAMP)
        (self.mount / KEY).symlink_to('..data/' + KEY)

    @staticmethod
    def write(path, data):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)

    def execute(self, body='projectedMetadata();', seam=''):
        # Neither shell, tool discovery, network, nor application entrypoint runs.
        functions = self.functions.replace("$mount = '/proof';", '$mount = ' + json.dumps(str(self.mount)) + ';')
        script = '<?php declare(strict_types=1); namespace ProjectionFixture; use \\RuntimeException; use \\Throwable;\n' + seam + '\n' + functions
        script += '\ntry { ' + body + ' echo json_encode(["ok"=>true]); } catch (\\Throwable $e) { echo json_encode(["ok"=>false,"gate"=>$e->getMessage()]); }\n'
        path = self.home / ('fixture-' + str(len(list(self.home.glob('fixture-*.php')))) + '.php')
        self.write(path, script.encode())
        env = {'HOME': str(self.home), 'TMPDIR': str(self.home), 'PATH': '/nonexistent', 'LANG': 'C'}
        completed = subprocess.run([str(self.php), '-n', '-d', 'allow_url_fopen=0', '-d',
            'disable_functions=exec,passthru,shell_exec,system,proc_open,popen,fsockopen,pfsockopen,stream_socket_client',
            str(path)], env=env, capture_output=True, timeout=5, check=False)
        # Do not dump fixture contents, stderr or raw PHP messages in failures.
        self.assertEqual(completed.returncode, 0, 'bounded PHP fixture process failed')
        self.assertFalse(completed.stderr, 'PHP fixture emitted unexpected stderr')
        result = json.loads(completed.stdout)
        for entry in self.home.rglob('*'):
            if not entry.is_symlink():
                self.assertEqual(stat.S_IMODE(entry.stat().st_mode), 0o700 if entry.is_dir() else 0o600)
        return result

    def reject(self, gate=None, **kwargs):
        result = self.execute(**kwargs)
        self.assertFalse(result['ok'])
        if gate:
            self.assertEqual(result['gate'], gate)

    def test_normal_atomic_projection_and_ordinary_source_guard(self):
        self.assertTrue(self.execute()['ok'])
        # Real PHP reproduces the original guard's rejection of a valid projection.
        self.reject('ordinary source remains strict', body="hashCheck(" + json.dumps(str(self.mount)) + ", 'packaged-metadata.json', '" + EXPECTED + "', 'ordinary source remains strict');")

    def test_missing_entry_rejects_with_path_diagnostic(self):
        (self.mount / KEY).unlink()
        self.reject('projected metadata path unavailable')

    def test_missing_target_rejects(self):
        self.target.unlink()
        self.reject('projected metadata path unavailable')

    def test_absolute_or_escaping_data_link_rejects(self):
        for link in (str(self.target.parent), '../outside', STAMP + '/nested'):
            (self.mount / '..data').unlink()
            (self.mount / '..data').symlink_to(link)
            self.reject('projected metadata data link invalid')

    def test_alternate_key_and_direct_target_link_reject(self):
        for link in ('..data/other.json', STAMP + '/' + KEY, str(self.target)):
            (self.mount / KEY).unlink()
            (self.mount / KEY).symlink_to(link)
            self.reject('projected metadata entry link invalid')

    def test_regular_entry_is_not_a_projection_fallback(self):
        (self.mount / KEY).unlink()
        self.write(self.mount / KEY, BRIDGE.read_bytes())
        self.reject('projected metadata type invalid')

    def test_target_symlink_and_ancestor_symlink_reject(self):
        copy = self.home / 'copy'
        self.write(copy, self.target.read_bytes())
        self.target.unlink()
        self.target.symlink_to(copy)
        self.reject('projected metadata type invalid')
        self.target.unlink()
        self.write(self.target, copy.read_bytes())
        moved = self.home / 'moved'
        self.target.parent.rename(moved)
        (self.mount / STAMP).symlink_to(moved)
        self.reject('projected metadata type invalid')

    def test_mount_ancestor_symlink_rejects(self):
        moved = self.home / 'moved'
        self.mount.rename(moved)
        self.mount.symlink_to(moved)
        self.reject('projected metadata type invalid')

    def test_special_fifo_and_directory_reject_without_opening(self):
        self.target.unlink()
        os.mkfifo(self.target, 0o600)
        self.reject('projected metadata type invalid')
        self.target.unlink()
        self.target.mkdir(mode=0o700)
        self.reject('projected metadata type invalid')

    def test_corrupt_and_oversized_bytes_reject(self):
        self.target.unlink()
        self.write(self.target, b'corrupt metadata')
        self.reject('reviewed packaged metadata drift')
        self.target.unlink()
        self.write(self.target, b'x' * 8193)
        self.reject('projected metadata target bounds invalid')

    def test_data_link_swap_after_open_and_during_read_rejects(self):
        # Deterministic real filesystem swaps at the exact I/O boundary, not sleeps.
        # No callback/override exists in the production reader.
        for operation in ('fopen', 'stream_get_contents'):
            (self.mount / '..data').unlink()
            (self.mount / '..data').symlink_to(STAMP)
            link = json.dumps(str(self.mount / '..data'))
            target = json.dumps(STAMP + '1')
            if operation == 'fopen':
                seam = 'function fopen($p,$m) { $f=\\fopen($p,$m); \\unlink(' + link + '); \\symlink(' + target + ',' + link + '); return $f; }'
            else:
                seam = 'function stream_get_contents($f,$n) { $b=\\stream_get_contents($f,$n); \\unlink(' + link + '); \\symlink(' + target + ',' + link + '); return $b; }'
            # A complete alternative generation with identical bytes must reject too.
            alternate = self.mount / (STAMP + '1')
            if not alternate.exists():
                alternate.mkdir(mode=0o700)
                self.write(alternate / KEY, BRIDGE.read_bytes())
            self.reject('projected metadata identity changed', seam=seam)

    def test_regular_target_inode_swap_rejects_even_same_bytes(self):
        path = json.dumps(str(self.target))
        replacement = self.target.with_name('replacement')
        self.write(replacement, BRIDGE.read_bytes())
        seam = 'function fopen($p,$m) { $f=\\fopen($p,$m); \\rename(' + json.dumps(str(replacement)) + ',' + path + '); return $f; }'
        self.reject('projected metadata identity changed', seam=seam)

    def test_same_target_link_replacement_and_hardlink_reject(self):
        link = json.dumps(str(self.mount / '..data'))
        seam = 'function fopen($p,$m) { $f=\\fopen($p,$m); \\rename(' + link + ',' + json.dumps(str(self.mount / '..old')) + '); \\symlink(' + json.dumps(STAMP) + ',' + link + '); return $f; }'
        self.reject('projected metadata identity changed', seam=seam)
        (self.mount / '..old').unlink()
        os.link(self.target, self.home / 'hardlink')
        self.reject('projected metadata target bounds invalid')

    def test_read_failure_distinct_from_unavailable_path_or_type(self):
        self.reject('projected metadata read unavailable', seam='function stream_get_contents($f,$n) { return false; }')

    def test_image_and_pvc_source_guards_unchanged(self):
        source = self.home / 'source'
        source.mkdir(mode=0o700)
        self.write(source / 'real.php', b'<?php // fixture, never executed')
        (source / 'base.php').symlink_to('real.php')
        expected = hashlib.sha256((source / 'real.php').read_bytes()).hexdigest()
        for label in ('image source remains strict', 'PVC source remains strict'):
            self.reject(label, body='hashCheck(' + json.dumps(str(source)) + ", 'base.php', '" + expected + "', '" + label + "');")
        self.assertIn('is_file($path) && !is_link($path)', self.source)
        self.assertIn("hashCheck($root,$relative,$hash,'actual core source parity mismatch')", self.source)
        self.assertIn("hashCheck('/var/www/html',$path,$hash", self.source)
        self.assertIn('$bridge=json_decode(projectedMetadata(),true,512,JSON_THROW_ON_ERROR);', self.source)


if __name__ == '__main__':
    unittest.main()
