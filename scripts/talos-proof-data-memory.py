#!/usr/bin/env python3
"""Refresh only observed memory fields in an already granted private data lease."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--group',required=True);p.add_argument('--stage',required=True)
    args=p.parse_args()
    spec=importlib.util.spec_from_file_location('life',ROOT/'scripts/talos-proof-data.py')
    life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
    life.LEASE_GROUP=args.group;life.LEASE_STAGE=args.stage
    receipt=life.lease(args.group)
    path=life.no_symlinks(os.environ['TALOS_PROOF_DATA_LEASE'])
    original=path.read_bytes()
    state=Path.home()/'.local/state/home-infra/talos-proof'
    summary=json.loads(life.kube('get','--raw','/api/v1/nodes/talos-proof/proxy/stats/summary'))
    kubelet=math.floor(summary['node']['memory']['availableBytes']/1024/1024)
    proc=subprocess.run([str(state/'bin/talosctl'),'--talosconfig',str(state/'config/talosconfig'),'-n','172.31.250.10','read','/proc/meminfo'],capture_output=True,check=True,timeout=30,text=True)
    mem=dict((line.split(':',1)[0],int(line.split()[1])) for line in proc.stdout.splitlines() if ':' in line)
    talos=math.floor(mem['MemAvailable']/1024)
    life.lease(args.group)
    if path.read_bytes()!=original:raise RuntimeError('receipt changed during observation')
    receipt.update(kubelet_available_mib=kubelet,talos_available_mib=talos,available_mib=min(kubelet,talos),measured_at=time.time())
    fd=os.open(path,os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(receipt,f)
    print(json.dumps({k:receipt[k] for k in ['kubelet_available_mib','talos_available_mib','available_mib','measured_at']}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Memory observation stopped: '+type(error).__name__)
        raise SystemExit(1)
