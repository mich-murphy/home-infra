#!/usr/bin/env python3
"""Proxmox-side guard. Only stops proof VM120; never adjusts host or other guests."""
import pathlib, subprocess, time, json, fcntl
lock = open("/root/.local/state/home-infra/talos-proof/resource-guard.lock", "w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("Resource guard already running")
state = pathlib.Path('/root/.local/state/home-infra/talos-proof')
baseline = int((state / 'swap-baseline-kib').read_text())
last = None
ongoing = 0
pressure_samples = 0
previous_psi = None
previous_time = None
while True:
    mem = {l.split(':')[0]: int(l.split()[1]) for l in pathlib.Path('/proc/meminfo').read_text().splitlines()}
    vm = dict(l.split() for l in pathlib.Path('/proc/vmstat').read_text().splitlines())
    swap_io = int(vm['pswpin']) + int(vm['pswpout'])
    ongoing = ongoing + 1 if last is not None and swap_io > last else 0
    last = swap_io
    psi = pathlib.Path('/proc/pressure/memory').read_text()
    now = time.monotonic()
    totals = {line.split()[0]: int(line.split()[-1].split('=')[1]) for line in psi.splitlines()}
    rates = {kind: 0.0 for kind in totals}
    if previous_psi is not None:
        rates = {kind: (totals[kind]-previous_psi[kind])/(now-previous_time)/10000 for kind in totals}
    previous_psi, previous_time = totals, now
    pressure = max(rates.values())
    pressure_samples = pressure_samples + 1 if rates['full'] >= 1 or rates['some'] >= 5 else 0
    sample = {'time': time.time(), 'available_mib': mem['MemAvailable']//1024,
              'swap_used_kib': mem['SwapTotal']-mem['SwapFree'], 'swap_io_pages':swap_io,
              'psi_delta_percent': rates}
    print(json.dumps(sample), flush=True)
    if sample['available_mib'] < 1536 or sample['swap_used_kib']-baseline > 65536 or ongoing >= 3 or pressure_samples >= 6:
        print('SAFETY STOP: stopping ONLY proof VM120', flush=True)
        subprocess.run(['qm','stop','120'], check=True)
        raise SystemExit(1)
    time.sleep(5)
