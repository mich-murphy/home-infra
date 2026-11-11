#!/usr/bin/env python3
"""Receipt-bound serial native cron. No grant issuance, VM start, or credentials creation.

Only a NEW parent receipt with exact run UUID, UIDs and full sequence authorizes
execution. All Kubernetes operations reuse the data lifecycle lease primitives.
"""
import argparse
import copy
import datetime
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
life = load('cron_life', 'talos-proof-data.py')
cron = load('cron_payload', 'talos-proof-nextcloud-cron.py')
NS = 'proof-nextcloud'

class Supervisor:
    def __init__(self, state, run):
        if str(uuid.UUID(run)) != run or uuid.UUID(run).version != 4:
            raise RuntimeError('canonical parent-known v4 run UUID required')
        self.state = life.private(state); self.run = run
        self.lock_fd=os.open(self.state,os.O_RDONLY)
        try: fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            os.close(self.lock_fd); del self.lock_fd; raise RuntimeError('another data supervisor owns journal directory')
        self.active = None; self.original = None
        life.LEASE_GROUP='nextcloud'; life.LEASE_STAGE='cron'; life.STATE_DIR=self.state

    def __del__(self):
        if hasattr(self,'lock_fd'): os.close(self.lock_fd)

    def save(self, value):
        path = self.state/(str(uuid.uuid4())+'.json')
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(value,f); f.flush(); os.fsync(f.fileno())
        directory = os.open(self.state,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        return path

    def authorize(self, start=False):
        # Local validation BEFORE even current-context or any API request.
        path = life.no_symlinks(os.environ.get('TALOS_PROOF_DATA_LEASE','/nonexistent'))
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600:
            raise RuntimeError('private receipt required')
        raw = path.read_bytes(); r=json.loads(raw)
        required = dict(group='nextcloud', stage='cron', run_id=self.run,
                        phases=list(cron.PHASES), budget_mib=832, synthetic_age=True, cleanup_authorized=True, state_dir=str(self.state),
                        selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'])
        if any(r.get(k)!=v for k,v in required.items()):
            raise RuntimeError('exact cron sequence receipt required')
        if type(r.get('expires')) not in (int,float) or not math.isfinite(r['expires']) or r['expires']<=time.time():
            raise RuntimeError('expired receipt')
        if start and r['expires']-time.time()<len(cron.PHASES)*240+300:
            raise RuntimeError('full sequence and cleanup window unavailable')
        if not r.get('context') or not r.get('node_uid') or r.get('endpoint')!=life.EXPECTED_ENDPOINT:
            raise RuntimeError('target identity missing')
        if self.original is not None and raw!=self.original:
            raise RuntimeError('immutable receipt changed')
        life.lease('nextcloud')
        self.original=raw
        return r

    def call(self,*args,data=None):
        self.authorize()
        result=life.kube(*args,data=data)
        self.authorize()
        return result

    def obj(self,*args):
        return json.loads(self.call(*args) if '--raw' in args else self.call(*args,'-o','json'))

    def pending(self):
        completed=set(); pending=set()
        for p in self.state.glob('*.json'):
            value=json.loads(p.read_text())
            if value.get('event')=='pending': pending.add(value['run_id'])
            if value.get('event')=='clean': completed.add(value['run_id'])
        return pending-completed

    def identities(self):
        r=self.authorize()
        expected=r.get('object_uids',{})
        targets=[('pvc','nextcloud-data'),('secret','proof-credentials'),('deployment','postgres'),
                 ('deployment','redis'),('cronjob','nextcloud-cron')]
        for kind,name in targets:
            obj=self.obj('-n',NS,'get',kind,name)
            if not expected.get(kind+'/'+name) or expected[kind+'/'+name]!=obj['metadata']['uid']:
                raise RuntimeError('retained object UID mismatch')
            if kind=='pvc':
                if obj['status']['phase']!='Bound': raise RuntimeError('PVC not bound')
                pv=self.obj('get','pv',obj['spec']['volumeName'])
                if pv['metadata']['uid']!=expected.get('pv/'+pv['metadata']['name']) or pv['spec']['claimRef']['uid']!=obj['metadata']['uid']:
                    raise RuntimeError('PV source/claim UID mismatch')
            if kind=='deployment':
                pod=obj['spec']['template']['spec']; containers=pod['containers']
                limit='384Mi' if name=='postgres' else '64Mi'
                if len(containers)!=1 or pod.get('initContainers') or containers[0]['resources']['limits']['memory']!=limit:
                    raise RuntimeError('backend envelope mismatch')
                if containers[0]['image']!=r.get('backend_images',{}).get(name):
                    raise RuntimeError('exact backend image binding required')
            if kind=='cronjob':
                if obj['spec'].get('suspend') is not True: raise RuntimeError('schedule must stay suspended')
                native=obj['spec']['jobTemplate']['spec']['template']['spec']
                c=native['containers']
                if len(c)!=1 or c[0]['image']!=cron.IMAGE or c[0]['resources']['limits']['memory']!='192Mi':
                    raise RuntimeError('native CronJob identity/envelope mismatch')

    def admission(self):
        self.identities()
        pods=self.obj('get','pods','-A')['items']
        cron.barrier(pods)
        for pod in pods:
            if pod['metadata']['namespace']!=NS: continue
            containers=pod['spec']['containers']
            app=pod['metadata']['labels']['app.kubernetes.io/name']
            expected=self.authorize().get('backend_images',{}).get(app)
            if len(containers)!=1 or containers[0]['image']!=expected or pod['spec'].get('initContainers'):
                raise RuntimeError('actual backend pod envelope/image mismatch')
            for volume in pod['spec'].get('volumes',[]):
                if 'persistentVolumeClaim' in volume:
                    claim=volume['persistentVolumeClaim']['claimName']
                    pvc=self.obj('-n',NS,'get','pvc',claim)
                    r=self.authorize()
                    if pvc['metadata']['uid']!=r.get('object_uids',{}).get('pvc/'+claim):
                        raise RuntimeError('backend PVC UID not bound')
                    pv=self.obj('get','pv',pvc['spec']['volumeName'])
                    if pv['metadata']['uid']!=r.get('object_uids',{}).get('pv/'+pv['metadata']['name']) or pv['spec']['claimRef']['uid']!=pvc['metadata']['uid']:
                        raise RuntimeError('backend PV attachment mismatch')
        for kind in ('deployments,statefulsets','cronjobs'):
            for c in self.obj('get',kind,'-A')['items']:
                m=c['metadata']; ns=m.get('namespace','')
                if not ns.startswith('proof-'): continue
                if kind=='cronjobs':
                    if not c['spec'].get('suspend',False): raise RuntimeError('unsuspended proof schedule')
                elif not (ns==NS and m['name'] in ('postgres','redis')) and c['spec'].get('replicas',1):
                    raise RuntimeError('active unselected controller/helper')
        # Independent observations, never receipt-reported passing booleans.
        summary=self.obj('get','--raw','/api/v1/nodes/talos-proof/proxy/stats/summary')
        observed=datetime.datetime.fromisoformat(summary['node']['memory']['time'].replace('Z','+00:00')).timestamp()
        if not 0<=time.time()-observed<=30: raise RuntimeError('stale kubelet memory')
        kubelet=summary['node']['memory']['availableBytes']/1048576
        self.authorize()
        state=Path.home()/'.local/state/home-infra/talos-proof'
        p=subprocess.run([str(state/'bin/talosctl'),'--talosconfig',str(state/'config/talosconfig'),
            '-e','127.0.0.1:50120','-n','172.31.250.10','read','/proc/meminfo'],capture_output=True,text=True,check=True,timeout=15)
        self.authorize()
        mem=[int(l.split()[1])/1024 for l in p.stdout.splitlines() if l.startswith('MemAvailable:')]
        if len(mem)!=1 or not all(math.isfinite(v) and v>=832 for v in [kubelet,*mem]):
            raise RuntimeError('fresh dual minimum below unchanged 832MiB requirement')
        cron.barrier(self.obj('get','pods','-A')['items'])
        self.save(dict(event='memory',run_id=self.run,kubelet=kubelet,talos=mem[0],at=time.time()))

    def forensics(self, name):
        pods=self.obj('-n',NS,'get','pods','-l','job-name='+name)
        self.save(dict(event='pods',run_id=self.run,pods=pods))
        selected=pods['items']
        if len(selected)!=1: raise RuntimeError('exact one phase pod required for forensics')
        pod=selected[0]
        statuses=pod['status'].get('containerStatuses',[])
        if len(statuses)!=1: raise RuntimeError('missing/ambiguous native container forensics')
        for c in statuses:
            current=self.call('-n',NS,'logs',pod['metadata']['name'],'-c',c['name'])
            self.save(dict(event='private-log',run_id=self.run,log=current))
            observation=json.loads(current.splitlines()[-1])
            cg=observation.get('cgroups',{})
            if observation.get('status')=='BLOCKED_OR_FAILED':
                raise RuntimeError('native payload failed; retain private forensics')
            if any(not isinstance(cg.get(k),str) for k in ('memory.peak','memory.current','memory.events','memory.stat')):
                raise RuntimeError('native cgroup measurement gap')
            events=dict(line.split() for line in cg['memory.events'].splitlines())
            if int(cg['memory.peak'])>192*1048576 or int(events.get('oom_kill','0')) or int(events.get('oom','0')):
                raise RuntimeError('native cgroup OOM/limit failure')
            if c.get('restartCount',0):
                self.save(dict(event='private-previous-log',run_id=self.run,
                    log=self.call('-n',NS,'logs',pod['metadata']['name'],'-c',c['name'],'--previous')))
        return pod

    def phase(self, phase):
        self.admission()
        document=cron.job(phase,self.run); name=document['metadata']['name']
        if phase=='cron':
            source=self.obj('-n',NS,'get','cronjob','nextcloud-cron')
            template=copy.deepcopy(source['spec']['jobTemplate']['spec'])
            original=template['template']['spec']
            expected=document['spec']['template']['spec']
            if (original.get('initContainers') or len(original['containers'])!=1
                or original.get('automountServiceAccountToken') is not False
                or original.get('securityContext')!=expected['securityContext']
                or original['containers'][0].get('securityContext')!=expected['containers'][0]['securityContext']
                or original['containers'][0].get('resources')!=expected['containers'][0]['resources']):
                raise RuntimeError('CronJob-derived security/resource envelope mismatch')
            # Derive from suspended native template, adding only reviewed CLI instrumentation.
            original['containers'][0].update(command=expected['containers'][0]['command'],
                env=expected['containers'][0]['env'],envFrom=expected['containers'][0]['envFrom'],
                volumeMounts=expected['containers'][0]['volumeMounts'])
            original['volumes']=expected['volumes']
            template.update(backoffLimit=0,activeDeadlineSeconds=180)
            document['spec']=template
        self.save(dict(event='phase-intent',run_id=self.run,phase=phase,job=document))
        self.call('create','-f','-',data=json.dumps(document)); self.active=name
        failure=None
        try:
            self.call('-n',NS,'wait','--for=condition=complete','job/'+name,'--timeout=190s')
        except Exception as e: failure=e
        # Required capture; any gap preserves Job and blocks another phase.
        pod=self.forensics(name)
        terminated=pod['status'].get('containerStatuses',[{}])[0].get('state',{}).get('terminated',{})
        if terminated.get('exitCode')!=0: failure=RuntimeError('native phase failed')
        self.call('-n',NS,'delete','job',name,'--wait=true','--timeout=180s')
        if self.obj('-n',NS,'get','pods','-l','job-name='+name)['items']:
            raise RuntimeError('phase pod persists after deletion')
        self.active=None
        if failure: raise failure

    def stop(self):
        # Pending journal must NOT block stop. Receipt/target still mandatory;
        # expired/unreachable target is reported pending, never bypassed/restarted.
        self.authorize()
        self.save(dict(event='stop-intent',run_id=self.run))
        # Strict capture here rather than the legacy best-effort deletion hook.
        self.save(dict(event='stop-pods',run_id=self.run,pods=self.obj('-n',NS,'get','pods')))
        self.call('-n',NS,'scale','deployment/postgres','deployment/redis','--replicas=0')
        self.call('-n',NS,'wait','--for=delete','pod','--all','--timeout=180s')
        if self.obj('-n',NS,'get','pods')['items']: raise RuntimeError('stop pods remain')

    def run_sequence(self):
        self.authorize(start=True)
        if self.pending(): raise RuntimeError('pending private cleanup blocks activation')
        self.save(dict(event='pending',run_id=self.run,intent=cron.intent(self.run)))
        try:
            bundle=cron.compile_bundle(self.run)
            self.admission()
            self.save(dict(event='backend-start-intent',run_id=self.run))
            self.call('-n',NS,'scale','deployment/postgres','deployment/redis','--replicas=1')
            self.call('-n',NS,'wait','--for=condition=available','deployment/postgres','deployment/redis','--timeout=180s')
            self.admission()
            self.call('create','-f','-',data=json.dumps(bundle['payload']))
            for phase in cron.PHASES: self.phase(phase)
            self.stop()
            self.save(dict(event='clean',run_id=self.run))
        except BaseException:
            self.save(dict(event='blocked-pending-cleanup',run_id=self.run,active=self.active))
            try: self.stop()
            except Exception: self.save(dict(event='stop-unconfirmed',run_id=self.run))
            raise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['run','stop','cleanup']); p.add_argument('--state',required=True); p.add_argument('--run-id',required=True)
    a=p.parse_args(); s=Supervisor(a.state,a.run_id)
    if a.action=='run': s.run_sequence()
    elif a.action=='stop': s.stop()
    else:
        s.authorize(); s.phase('cleanup'); s.stop(); s.save(dict(event='clean',run_id=s.run))
    print('Guarded sequence ended; inspect private UUID journal. No general application acceptance implied.')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('Native cron BLOCKED_OR_FAILED: '+type(e).__name__)
        raise SystemExit(1)
