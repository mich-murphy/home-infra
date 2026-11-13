#!/usr/bin/env python3
"""Offline prospective backup membership and diagnostic-privacy regressions."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backup_safety', ROOT / 'infrastructure/proxmox-proof/backup-safety.py')
safety = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safety)


class BackupMembership(unittest.TestCase):
    def test_all_guests_must_explicitly_exclude_new_vm(self):
        for value in (1, True, '1'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    safety.check([{'all': value, 'exclude': '9001,9003'}])
                self.assertEqual(safety.check([{'all': value, 'exclude': '9001,9003,120'}]), 1)

    def test_explicit_membership_not_overridden_by_exclude(self):
        with self.assertRaises(ValueError):
            safety.check([{'vmid': '101,120', 'exclude': '120'}])
        self.assertEqual(safety.check([{'vmid': '101;102 111'}]), 1)

    def test_disabled_and_empty_lists(self):
        self.assertEqual(safety.check([]), 0)
        for value in (False, 0, '0'):
            self.assertEqual(safety.check([{'enabled': value, 'all': 1}]), 0)

    def test_unknown_or_malformed_fails_closed(self):
        cases = [{}, {'pool': 'production'}, {'all': 1, 'exclude': '120', 'pool': 'other'},
                 {'tags': 'proof'}, {'enabled': 'false', 'all': 1}, {'all': 2},
                 {'vmid': '101,not-an-id'}, {'all': 1, 'exclude': [120]}]
        for job in cases:
            with self.subTest(job=job), self.assertRaises(ValueError):
                safety.check([job])
        with self.assertRaises(ValueError):
            safety.check({'all': 1})

    def test_every_enabled_job_is_checked(self):
        with self.assertRaises(ValueError):
            safety.check([{'all': 1, 'exclude': '120'}, {'all': 1}])

    def test_host_command_is_read_only_and_errors_private(self):
        error = subprocess.CalledProcessError(1, ['pvesh'], stderr=b'PRIVATE-SENTINEL')
        out = io.StringIO()
        with patch.object(sys, 'argv', ['check', '--host']), \
             patch.object(safety.subprocess, 'run', side_effect=error) as run, \
             contextlib.redirect_stderr(out):
            self.assertEqual(safety.main(), 1)
        self.assertEqual(run.call_args.args[0], ['pvesh', 'get', '/cluster/backup', '--output-format', 'json'])
        self.assertTrue(run.call_args.kwargs['capture_output'])
        self.assertNotIn('PRIVATE-SENTINEL', out.getvalue())
        self.assertIn('https://proxmox:8006/', out.getvalue())

    def test_creation_gate_precedes_vm_mutation(self):
        source = (ROOT / 'infrastructure/proxmox-proof/create.sh').read_text()
        self.assertLess(source.index('backup-safety.py'), source.index('qm create 120'))
        self.assertIn('backup-safety.py" --host', source)


if __name__ == '__main__':
    unittest.main()
