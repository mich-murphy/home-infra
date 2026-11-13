#!/usr/bin/env python3
"""Offline archive preservation regressions, no cluster execution."""
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
r = importlib.import_module('talos-proof-media-recovery')

class Preservation(unittest.TestCase):
    def test_uuid_exclusive_and_old_archive_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve()
            old = state / 'qbittorrent-config-snapshot.tar'
            old.write_bytes(b'earlier archive retained')
            first, second = (r.archive_name('qbittorrent', 'config') for _ in range(2))
            self.assertNotEqual(first, second)
            r.safety.write_private(state / first, b'new archive')
            with self.assertRaises((FileExistsError, RuntimeError)):
                r.safety.write_private(state / first, b'forbidden replacement')
            self.assertEqual(old.read_bytes(), b'earlier archive retained')
    def test_manifests_and_restore_attempts_append_only(self):
        source = (ROOT / 'scripts/talos-proof-media-recovery.py').read_text()
        self.assertNotIn('replace=True', source)
        for marker in ['.restore-started.json', '-recovery-attempt-', '-restored-', "'manifest': result_path.name"]:
            self.assertIn(marker, source)

if __name__ == '__main__': unittest.main()
