#!/usr/bin/env python3
"""Read-only prospective VM120 backup-membership gate; never edits backup jobs."""
import argparse
import json
import re
import subprocess
import sys

VMID = 120


def flag(value, default=False):
    if value is None:
        return default
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if type(value) is str and value in ('0', '1'):
        return value == '1'
    raise ValueError('invalid boolean')


def ids(value):
    if value is None or value == '':
        return set()
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:[,; ]+\d+)*', value):
        raise ValueError('invalid VM selector')
    return {int(v) for v in re.split(r'[,; ]+', value)}


def check(jobs):
    if not isinstance(jobs, list) or len(jobs) > 1024:
        raise ValueError('invalid job list')
    enabled = 0
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError('invalid job')
        if not flag(job.get('enabled'), default=True):
            continue
        enabled += 1
        explicit = ids(job.get('vmid'))
        # --exclude is documented for --all, not an escape from an explicit ID.
        if VMID in explicit:
            raise ValueError('enabled job explicitly includes proof VM')
        if job.get('pool') or job.get('tags') or job.get('exclude-tags'):
            raise ValueError('membership selector requires explicit review')
        if flag(job.get('all')):
            if VMID not in ids(job.get('exclude')):
                raise ValueError('enabled all-guests job includes proof VM')
        elif not explicit:
            raise ValueError('unknown enabled job membership')
    return enabled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', action='store_true', help='read local Proxmox API via pvesh')
    args = parser.parse_args()
    try:
        if args.host:
            raw = subprocess.run(['pvesh', 'get', '/cluster/backup', '--output-format', 'json'],
                                 check=True, capture_output=True, timeout=15).stdout
        else:
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('oversized job response')
        count = check(json.loads(raw))
    except (ValueError, TypeError, OSError, subprocess.SubprocessError):
        # Never publish raw job objects, recipient details or subprocess output.
        print('REFUSED: VM120 backup membership is unsafe or could not be established. '
              'Review https://proxmox:8006/#v1:0:=datacenter:backup ; explicitly exclude '
              'ONLY new proof VM120 where required, preserving existing guest membership '
              'and all other settings. This checker changed nothing.', file=sys.stderr)
        return 1
    print(f'Backup membership gate passed for VM120 ({count} enabled jobs checked); no job changed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
