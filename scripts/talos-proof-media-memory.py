#!/usr/bin/env python3
"""Refresh ONLY memory fields of an existing parent-issued media lease.

Live-only command. Both independent readings must succeed; no stale fallback.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import time

safety = importlib.import_module('talos-proof-media-safety')
ENDPOINT = '127.0.0.1:50120'
NODE = '172.31.250.10'


def refresh(group, talosctl):
    receipt, _ = safety.lease(group)
    config = safety.private_file(os.environ['TALOSCONFIG'])
    result = subprocess.run([str(talosctl), '--talosconfig', str(config), '-e', ENDPOINT,
                             '-n', NODE, 'read', '/proc/meminfo'], capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('fresh Talos MemAvailable unavailable; receipt unchanged')
    rows = [line.split() for line in result.stdout.decode().splitlines() if line.startswith('MemAvailable:')]
    if len(rows) != 1 or len(rows[0]) != 3 or rows[0][2] != 'kB':
        raise RuntimeError('unexpected Talos meminfo; receipt unchanged')
    talos = int(rows[0][1]) // 1024
    summary = json.loads(safety.kubectl_read('get', '--raw', '/api/v1/nodes/talos-proof/proxy/stats/summary'))
    kubelet = summary['node']['memory']['availableBytes']
    if not isinstance(kubelet, int) or isinstance(kubelet, bool) or kubelet <= 0 or talos <= 0:
        raise RuntimeError('invalid memory reading; receipt unchanged')
    kubelet //= 1048576
    # Revalidate identity/group/expiry after reads; copy no fields from an old receipt.
    current, _ = safety.lease(group)
    if current != receipt:
        raise RuntimeError('parent receipt changed during measurement; refuse overwrite')
    current.update(available_mib=min(kubelet, talos), measured_at=time.time())
    safety.write_private(os.environ['TALOS_PROOF_MEDIA_LEASE'], json.dumps(current), replace=True)
    return {'kubelet_available_mib': kubelet, 'talos_available_mib': talos, 'admission_mib': min(kubelet, talos)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('group', choices=[*safety.SERVICES, *safety.DEPENDENCY_BATCHES])
    p.add_argument('--talosctl', required=True, type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(refresh(args.group, args.talosctl)))
    except Exception as exc:
        print(json.dumps({'result': 'MEMORY_REFRESH_FAILED', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
