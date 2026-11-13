#!/usr/bin/env python3
"""Owned decoder exec trampoline: no fork-time Python callbacks or networking."""
import os
from pathlib import Path
import re
import resource
import sys


def main():
    path, *args = sys.argv[1:]
    if not re.fullmatch(r'/nix/store/[a-z0-9]{32}-ffmpeg[^/]*/bin/ffmpeg', path):
        raise SystemExit('invalid decoder')
    if not str(Path(path).resolve()).startswith('/nix/store/'):
        raise SystemExit('invalid decoder target')
    expected = ['-hide_banner', '-loglevel', 'error', '-nostdin', '-nostats',
                '-stats_period', '0.25', '-progress', 'pipe:1', '-max_alloc', '67108864',
                '-threads', '1', '-filter_threads', '1', '-protocol_whitelist', 'pipe',
                '-readrate', '1', '-i', 'pipe:0', '-map', '0:v:0', '-an', '-threads', '1',
                '-c:v', 'wrapped_avframe', '-f', 'null', '-']
    if args != expected:
        raise SystemExit('fixed stdin-only decoder arguments required')
    limits = [(resource.RLIMIT_CPU, 30), (resource.RLIMIT_FSIZE, 262144),
              (resource.RLIMIT_NOFILE, 64), (resource.RLIMIT_CORE, 0)]
    if sys.platform != 'darwin':
        limits.append((resource.RLIMIT_AS, 1024**3))
    for kind, bound in limits:
        resource.setrlimit(kind, (bound, bound))
    os.execve(path, [path, *args], dict(os.environ))


if __name__ == '__main__':
    main()
