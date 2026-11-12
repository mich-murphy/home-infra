#!/usr/bin/env python3
"""MANUAL workstation decoder checks, separate from the repository/root gate.

Requires explicit exact Nix ffmpeg. Generates ONLY a new synthetic in-memory MP4
for offline tests. This is NOT the existing proof fixture or Plex/Tautulli evidence.
No skip path: unavailable tools or unsuccessful decode exit nonzero.
"""
import argparse
import hashlib
import importlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
h = importlib.import_module('talos-proof-media-headless')
FFMPEG = None


class Workstation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        h.command(FFMPEG)
        # Explicit offline-only generator, never used by production decode().
        result = subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostdin',
                                 '-f', 'lavfi', '-i', 'testsrc=size=96x64:rate=10',
                                 '-t', '5', '-threads', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                                 '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4', 'pipe:1'],
                                env={'LANG': 'C', 'LC_ALL': 'C'}, capture_output=True, timeout=15,
                                preexec_fn=h._limits)
        if result.returncode or not 0 < len(result.stdout) <= h.FIXTURE_BYTES:
            raise RuntimeError('bounded NEW synthetic generation failed')
        cls.data = result.stdout
        cls.digest = hashlib.sha256(cls.data).hexdigest()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='offline-headless-')
        self.root = Path(self.temp.name).resolve()
        os.chmod(self.root, 0o700)
        self.addCleanup(self.temp.cleanup)

    def run_decode(self, data=None, **kwargs):
        source = io.BytesIO(self.data if data is None else data)
        self.addCleanup(source.close)
        return h.decode(source, FFMPEG, self.root, size=len(self.data), digest=self.digest, **kwargs)

    def test_real_bounded_decode(self):
        live = []
        result = self.run_decode(observe=lambda p, alive, verified: live.append((p, alive, verified)))
        self.assertTrue(result['decoder_only'])
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['frames'], 50)
        self.assertGreater(result['media_us'], 4000000)
        verified_live = [p for p, alive, verified in live if alive and verified]
        self.assertGreaterEqual(len(verified_live), 3)
        self.assertGreater(verified_live[-1].frame, verified_live[0].frame)
        self.assertGreater(verified_live[-1].media_us, verified_live[0].media_us)
        with self.assertRaises(ProcessLookupError):
            os.kill(result['pid'], 0)
        files = list(self.root.rglob('*.raw'))
        self.assertEqual(len(files), 2)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in files))
        self.assertLessEqual(sum(p.stat().st_size for p in files), h.MAX_OUTPUT)
        self.assertFalse(list(self.root.rglob('home-*')))

    def test_cancellation_while_decoding(self):
        cancel = threading.Event()
        def observed(progress, alive, verified):
            cancel.set()
        with self.assertRaisesRegex(h.Rejected, 'cancelled'):
            self.run_decode(cancel=cancel, observe=observed)
        self.assertFalse(list(self.root.rglob('home-*')))

    def test_corruption(self):
        with self.assertRaises(h.Rejected):
            self.run_decode(data=self.data[:-1] + bytes([self.data[-1] ^ 1]))

    def test_oversize(self):
        with self.assertRaises(h.Rejected):
            self.run_decode(data=self.data + b'x')

    def test_decoder_failure_despite_matching_input_hash(self):
        data = b'not a media container'
        with self.assertRaises(h.Rejected):
            h.decode(io.BytesIO(data), FFMPEG, self.root, size=len(data),
                     digest=hashlib.sha256(data).hexdigest())

    def test_walltime_kills_owned_child(self):
        with self.assertRaisesRegex(h.Rejected, 'wall-time'):
            self.run_decode(seconds=0.2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True, help='exact /nix/store/.../bin/ffmpeg')
    args = parser.parse_args()
    FFMPEG = args.ffmpeg
    unittest.main(argv=[sys.argv[0]], verbosity=2)
