#!/usr/bin/env python3
"""Bounded live policy proof: correlate exact source/destination with BPF drop events."""
import json, os, subprocess, sys, time
from pathlib import Path
import proof_guard
proof_guard.check()
if os.environ.get('PROOF_TESTS_AUTHORIZED') != 'yes':
    raise SystemExit('Explicit authorization required')
k=['python3',str(Path(__file__).with_name('proof_guard.py')),'--context',os.environ['PROOF_CONTEXT']]
def run(*args):return subprocess.run(k+list(args),text=True,capture_output=True,timeout=30)
def pod(ns,app):
    r=run('-n',ns,'get','pods','-l','app='+app,'-o','json');r.check_returncode()
    return next(p for p in json.loads(r.stdout)['items'] if not p['metadata'].get('deletionTimestamp') and p['status'].get('phase')=='Running')
positive=pod('proof-validation','client');negative=pod('proof-network-test','denied-client');target=pod('proof-network-test','fixture')
ip=target['status']['podIP'];src=negative['status']['podIP']
print('Producer positive:',positive['metadata']['name'],positive['status']['podIP'],flush=True)
print('Producer negative:',negative['metadata']['name'],src,flush=True)
print('Known-live backend:',target['metadata']['name'],ip,flush=True)
r=run('-n','proof-validation','exec',positive['metadata']['name'],'--','wget','-q','-T','3','-O','-',f'http://{ip}:8080/')
r.check_returncode(); print('PASS positive exact backend:',r.stdout.strip(),flush=True)
for dest,port in [(ip,8080),('192.168.254.254',8080),('198.51.100.1',8080),('172.31.250.10',6443)]:
    # Monitor is scoped in time per request; no continuous daemon or polling loop.
    monitor=subprocess.Popen(k+['-n','kube-system','exec','ds/cilium','-c','cilium-agent','--','cilium-dbg','monitor','--type','drop'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        time.sleep(0.5)  # allow monitor socket subscription, not a readiness poll
        r=run('-n','proof-network-test','exec',negative['metadata']['name'],'--','wget','-q','-T','3','-O','-',f'http://{dest}:{port}/')
        if r.returncode==0:raise RuntimeError('Unexpected allowed destination '+dest)
        time.sleep(0.2)
    finally:
        monitor.terminate()
        try:out=monitor.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:monitor.kill();out=monitor.communicate()[0]
    matches=[l for l in out.splitlines() if src in l and dest in l and 'Policy denied' in l]
    print(f'REQUEST producer={src} destination={dest}:{port} exit={r.returncode}',flush=True)
    print(r.stderr.strip(),flush=True)
    if not matches:print(out,flush=True);raise RuntimeError('No matching observed policy drop')
    for l in matches: print('OBSERVED '+l,flush=True)
    print('PASS exact correlated BPF policy drop',flush=True)
