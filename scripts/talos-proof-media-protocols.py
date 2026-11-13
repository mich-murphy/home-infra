#!/usr/bin/env python3
"""Repository CLI for the closed synthetic media download fixture."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'kubernetes/apps/media/fixtures/download-protocols/server.py'), run_name='__main__')
