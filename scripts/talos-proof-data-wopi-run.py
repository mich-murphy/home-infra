#!/usr/bin/env python3
"""Receipt-bounded WOPI attempt; append-only diagnostics then unconditional cleanup.
Single-attempt grants or historical two-attempt receipts; limits remain768+64.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import threading
import yaml

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True,type=int,choices=[1,2]);parser.add_argument('--state',required=True);parser.add_argument('--format',choices=['txt','odt'],default='txt')
    args=parser.parse_args();os.umask(0o077)
    spec=importlib.util.spec_from_file_location('life',ROOT/'scripts/talos-proof-data.py')
    life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
    life.LEASE_GROUP='nextcloud';life.LEASE_STAGE='wopi'
    state=life.private(args.state);life.STATE_DIR=state;receipt=life.lease('nextcloud')
    if receipt.get('document_format','txt') != args.format:
        raise RuntimeError('native ODT requires explicit new format-bound parent grant')
    os.environ['TALOS_PROOF_WOPI_FORMAT']=args.format
    # New grants bind one activation separately from the browser-attempt ceiling.
    # This supervisor intentionally runs one suite, then unconditionally stops.
    single_activation = 'max_activations' in receipt
    if single_activation and (receipt['max_activations'] != 1 or receipt.get('max_browser_attempts') not in (1,2) or args.attempt != 1):
        raise RuntimeError('exactly one activation and bounded browser attempts required')
    maximum=1 if single_activation else receipt.get('max_attempts')
    if not receipt.get('lease_id') or maximum not in (1,2) or args.attempt>maximum:
        raise RuntimeError('explicit bounded attempt receipt required')
    limits=receipt.get('approved_controller_limits_mib')
    if (maximum==2 or limits is not None) and limits!={'collabora':768,'wopi-fixture':64}:
        raise RuntimeError('exact parent-approved controller limits required')
    lease_id=hashlib.sha256(str(receipt['lease_id']).encode()).hexdigest()[:16]
    target=life.no_symlinks(state/(f'wopi-activation-{lease_id}.json' if single_activation else f'wopi-retry-{lease_id}-{args.attempt}.json'))
    if target.exists():raise RuntimeError('attempt already consumed for this lease')
    if args.attempt==2 and not (state/f'wopi-retry-{lease_id}-1.json').exists():raise RuntimeError('first bounded attempt must precede second')
    subprocess.run([sys.executable,str(ROOT/'scripts/talos-proof-data-memory.py'),'--group','nextcloud','--stage','wopi'],check=True,timeout=60)
    life.guard('nextcloud')
    pods=json.loads(life.kube('-n','proof-nextcloud','get','pods','-o','json'))['items']
    if pods:raise RuntimeError('attempt requires all group pods deleted first')
    prefix='wopi-'+str(time.time_ns())+'-'+uuid.uuid4().hex
    os.environ['TALOS_PROOF_WOPI_OUTPUT_PREFIX']=prefix
    result={'output_prefix':prefix,'status':'started','attempt':args.attempt,'started':time.time(),'document_format':args.format,'scope':'CODE768 + WOPI fixture64 ONLY','observations':{},'cleanup':{}}
    lock=threading.RLock()
    def save():
        with lock:
            snapshot=life.no_symlinks(state/(prefix+'-snapshot-'+str(time.time_ns())+'.json'))
            fd=os.open(snapshot,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2)
    # Consume before any activation and refuse reuse of this lease/attempt.
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'output_prefix':prefix,'started':result['started']},f)
    save()
    stop=threading.Event()
    sampler=None
    def sample_kernel(phase):
        try:
            parent=Path.home()/'.local/state/home-infra/talos-proof'
            pods=json.loads(kube('-n','proof-nextcloud','get','pods','-o','json'))['items']
            samples=[]
            for pod in pods:
                statuses=pod['status'].get('containerStatuses',[])
                if not statuses:continue
                cid=statuses[0]['containerID'].split('://')[1]
                base='/sys/fs/cgroup/kubepods/burstable/pod'+pod['metadata']['uid']+'/'+cid
                sample={'phase':phase,'pod_uid':pod['metadata']['uid'],'pod_phase':pod['status'].get('phase'),
                        'containers':[{k:c.get(k) for k in ('name','imageID','containerID','restartCount','ready')} for c in statuses],
                        'time':time.time(),'cgroup':{},'read_times':{}}
                for name in ('memory.current','memory.peak','memory.events','memory.stat'):
                    life.lease('nextcloud')
                    proc=subprocess.run([str(parent/'bin/talosctl'),'--talosconfig',str(parent/'config/talosconfig'),'-e','127.0.0.1:50120','-n','172.31.250.10','read',base+'/'+name],capture_output=True,text=True,timeout=10)
                    sample['cgroup'][name]=proc.stdout if proc.returncode==0 else 'unavailable'
                    sample['read_times'][name]=time.time()
                events=dict(line.split() for line in sample['cgroup'].get('memory.events','').splitlines() if len(line.split())==2)
                if any(int(events.get(name,0)) for name in ('oom','oom_kill')):
                    with lock:result['status']='failed';result['observed_oom']=True
                samples.append(sample)
            with lock:result['observations'].setdefault('kernel_samples',[]).extend(samples)
        except Exception as error:
            with lock:result['observations'].setdefault('kernel_gaps',[]).append({'phase':phase,'error':type(error).__name__})
        save()
    def sampling():
        while not stop.wait(10):sample_kernel('during bounded suite')
    def kube(*command):return life.kube('--request-timeout=15s',*command)
    try:
        docs=list(yaml.safe_load_all(subprocess.check_output(['kubectl','kustomize',str(ROOT/'kubernetes/apps/data/nextcloud')],text=True)))
        approved=[]
        for d in docs:
            kind=d['kind'];name=d['metadata']['name'];app=d.get('spec',{}).get('podSelector',{}).get('matchLabels',{}).get('app.kubernetes.io/name')
            keep=(kind=='Namespace' or (kind in ('Deployment','Service') and name in ('collabora','wopi-fixture')) or
                  (kind=='ConfigMap' and name=='wopi-fixture-source') or
                  (kind=='NetworkPolicy' and (not d['spec']['podSelector'] or app in ('collabora','wopi-fixture'))) or
                  (kind=='CiliumNetworkPolicy' and d['spec']['endpointSelector']['matchLabels']['app.kubernetes.io/name']=='collabora') or
                  (kind=='HTTPRoute' and d['spec'].get('hostnames')==['collabora.proof.invalid']))
            if keep:
                if kind=='Deployment' and name=='wopi-fixture':
                    d['spec']['template']['spec']['containers'][0]['env']=[{'name':'PROOF_WOPI_FORMAT','value':args.format}]
                approved.append(d)
        actual={d['metadata']['name']:int(d['spec']['template']['spec']['containers'][0]['resources']['limits']['memory'][:-2]) for d in approved if d['kind']=='Deployment'}
        if actual!={'collabora':768,'wopi-fixture':64}:raise RuntimeError('unchanged exact controller limits required')
        life.kube('--request-timeout=15s','apply','-f','-',data=json.dumps({'apiVersion':'v1','kind':'List','items':approved}))
        # No credential generation/Secret update: retain existing fresh proof identity.
        subprocess.run([sys.executable,str(ROOT/'scripts/talos-proof-data-memory.py'),'--group','nextcloud','--stage','wopi'],check=True,timeout=60)
        subprocess.run([sys.executable,str(ROOT/'scripts/talos-proof-data.py'),'activate','--group','nextcloud','--stage','wopi','--state',str(state)],check=True,timeout=300)
        sample_kernel('before suite')
        sampler=threading.Thread(target=sampling,daemon=True);sampler.start()
        with (state/(prefix+'-cli.txt')).open('x') as log:
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/talos-proof-data.py'),'test','--group','nextcloud','--stage','wopi','--state',str(state)],stdout=log,stderr=log,timeout=660)
        result['suite_exit']=proc.returncode
        outputs=[p for p in state.glob('nextcloud-wopi-*-result.json') if p.stat().st_mtime>=result['started']]
        if outputs:
            result['suite']=json.loads(max(outputs,key=lambda p:p.stat().st_mtime).read_text())
        result['status']='passed-with-component-limitations' if proc.returncode==0 and not result.get('observed_oom') else 'failed'
    except Exception as error:
        result['status']='failed';result['failure_type']=type(error).__name__
    finally:
        stop.set()
        if sampler:sampler.join(timeout=95)
        # Diagnostics never obstruct cleanup. Persist independently after each item.
        try:
            result['observations']['fixture']=json.loads(kube('-n','proof-nextcloud','exec','deployment/wopi-fixture','--','cat','/data/evidence.json'))
        except Exception as error:result['observations']['fixture_gap']=type(error).__name__
        save()
        try:
            # Negative requests may NOT create a valid PutFile or earn editing PASS.
            live_spec=importlib.util.spec_from_file_location('live',ROOT/'tests/talos-proof-data-live.py')
            live=importlib.util.module_from_spec(live_spec);live_spec.loader.exec_module(live)
            live.LIFE=life;live.GROUP='nextcloud';live.NS='proof-nextcloud';live.RESULT={'checks':[]}
            creds=life.credentials(state)['nextcloud']
            import urllib.error
            negative={}
            with live.forwarded('wopi-fixture',8082) as base:
                for name,path,method,body,headers in [
                    ('bad-token','/wopi/files/proof?access_token=wrong','GET',None,{}),
                    ('wrong-lock','/wopi/files/proof/contents?access_token='+creds['NEXTCLOUD_ADMIN_PASSWORD'],'POST',b'NEVER-SAVE',{'X-WOPI-Lock':'wrong-lock'})]:
                    try: live.http(base,path,method,body,headers=headers,raw=True);negative[name]=200
                    except urllib.error.HTTPError as error:negative[name]=error.code
            result['observations']['negative']=negative
            after=json.loads(kube('-n','proof-nextcloud','exec','deployment/wopi-fixture','--','cat','/data/evidence.json'))
            result['observations']['fixture_after_negatives']=after
            before=result['observations'].get('fixture',{})
            result['observations']['negative_bytes_unchanged']=bool(before.get('sha256')) and before.get('sha256')==after.get('sha256') and type(before.get('bytes')) is int and before['bytes']==after.get('bytes')
            if negative!={'bad-token':401,'wrong-lock':409} or not result['observations']['negative_bytes_unchanged']:result['status']='failed'
        except Exception as error:
            result['observations']['negative_gap']=type(error).__name__
            result['status']='failed'
        save()
        try:
            sample_kernel('after suite and negatives')
        finally:
            # Even diagnostic timeout/exception cannot skip this exact lease-gated stop.
            try:
                kube('-n','proof-nextcloud','scale','deployment/collabora','deployment/wopi-fixture','--replicas=0')
                kube('-n','proof-nextcloud','wait','--for=delete','pod','--all','--timeout=90s')
                count=len(json.loads(kube('get','pods','-A','-l','app.kubernetes.io/part-of=talos-proof','-o','json'))['items'])
                result['cleanup']={'selected_replicas':0,'pod_deletion_confirmed':True,'global_labelled_pod_count':count}
            except Exception as error:
                result['cleanup']={'blocked':type(error).__name__,'no_VM_restart_or_guard_bypass':True}
            result['finished']=time.time();save()
    print(json.dumps(result,indent=2))
    if result['status']!='passed-with-component-limitations' or result['cleanup'].get('global_labelled_pod_count')!=0:raise SystemExit(1)


if __name__=='__main__':main()
