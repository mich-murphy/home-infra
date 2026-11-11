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
import re
from fractions import Fraction
import os
from pathlib import Path
import stat
import subprocess
import time
import uuid
import yaml

ROOT = Path(__file__).resolve().parents[1]
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
life = load('cron_life', 'talos-proof-data.py')
cron = load('cron_payload', 'talos-proof-nextcloud-cron.py')
NS = 'proof-nextcloud'

def quantity(value):
    """Exact rational Kubernetes quantity; no floats, rounding or ignored keys."""
    match=re.fullmatch(r'([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))([eE][+-]?[0-9]+|[numkKMGTPE]|[KMGTPE]i)?',str(value))
    if not match: raise RuntimeError('unsupported exact resource quantity')
    number,suffix=match.groups(); suffix=suffix or ''
    scale={'':1,'n':Fraction(1,10**9),'u':Fraction(1,10**6),'m':Fraction(1,1000),'k':1000,'K':1000}
    scale.update({u:1000**i for i,u in enumerate('MGTPE',2)})
    scale.update({u+'i':1024**i for i,u in enumerate('KMGTPE',1)})
    multiplier=Fraction(10)**int(suffix[1:]) if suffix.startswith(('e','E')) and len(suffix)>1 and suffix[1] in '+-0123456789' else scale[suffix]
    return Fraction(number)*multiplier


def resources(value):
    result=copy.deepcopy(value)
    for section in ('requests','limits'):
        for key,v in result.get(section,{}).items():
            if key in ('cpu','memory'): result[section][key]=quantity(v)
    return result


class Supervisor:
    def __init__(self, state, run):
        if str(uuid.UUID(run)) != run or uuid.UUID(run).version != 4:
            raise RuntimeError('canonical parent-known v4 run UUID required')
        self.state = life.shared_data_state(state); self.run = run
        self.lock_fd=os.open(self.state,os.O_RDONLY)
        try: fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            os.close(self.lock_fd); del self.lock_fd; raise RuntimeError('another data supervisor owns journal directory')
        self.active = None; self.original = None; self.scope = "run"; self.jobs = {}
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
        scope=r.get('action','run') if self.scope=='stop' else self.scope
        if scope not in ('run','cleanup'): raise RuntimeError('invalid receipt action')
        required = dict(group='nextcloud', stage='cron', run_id=self.run,
                        phases=['cleanup'] if scope=='cleanup' else list(cron.PHASES), budget_mib=832, synthetic_age=True, cleanup_authorized=True, state_dir=str(self.state),
                        selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'])
        if r.get('action', 'run') != scope or any(r.get(k)!=v for k,v in required.items()):
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
        return life.pending_native_cron(self.state)

    def unused_run(self):
        if any(e.get('run_id') == self.run for e in life.native_cron_events(self.state)):
            raise RuntimeError('reused run UUID forbidden')

    @staticmethod
    def approved(name):
        path=ROOT/'kubernetes/apps/data/nextcloud'/('cronjob.yaml' if name=='nextcloud-cron' else name+'.yaml')
        return next(d for d in yaml.safe_load_all(path.read_text()) if d['kind'] in ('Deployment','CronJob'))

    def envelope(self, actual, approved, actual_pod=False):
        # Compare the complete reviewed template, allowing only documented API defaults.
        def normalized(pod):
            pod=copy.deepcopy(pod)
            if pod.get('securityContext')=={}:pod.pop('securityContext')
            defaults=dict(dnsPolicy='ClusterFirst',schedulerName='default-scheduler',
                restartPolicy='Always',terminationGracePeriodSeconds=30,enableServiceLinks=True,
                serviceAccount='default',serviceAccountName='default',priority=0,
                preemptionPolicy='PreemptLowerPriority')
            if actual_pod:
                defaults['nodeName']='talos-proof'
                defaults['tolerations']=[dict(key='node.kubernetes.io/not-ready',operator='Exists',effect='NoExecute',tolerationSeconds=300),
                    dict(key='node.kubernetes.io/unreachable',operator='Exists',effect='NoExecute',tolerationSeconds=300)]
            for key,value in defaults.items():
                if pod.get(key)==value: pod.pop(key)
            if 'resources' in pod: pod['resources']=resources(pod['resources'])
            if 'overhead' in pod:
                pod['overhead']={k:quantity(v) if k in ('cpu','memory') else v for k,v in pod['overhead'].items()}
            for c in pod.get('containers',[]):
                if 'resources' in c: c['resources']=resources(c['resources'])
                for key,value in dict(terminationMessagePath='/dev/termination-log',terminationMessagePolicy='File',imagePullPolicy='IfNotPresent').items():
                    if c.get(key)==value: c.pop(key)
                for port in c.get('ports',[]):
                    if port.get('protocol')=='TCP': port.pop('protocol')
                for mount in c.get('volumeMounts',[]):
                    if mount.get('readOnly') is False: mount.pop('readOnly')
            for volume in pod.get('volumes',[]):
                if volume.get('persistentVolumeClaim',{}).get('readOnly') is False:
                    volume['persistentVolumeClaim'].pop('readOnly')
            return pod
        if normalized(actual)!=normalized(approved):
            raise RuntimeError('full pod security/resource/image/template envelope mismatch')

    @staticmethod
    def template_metadata(actual, approved):
        actual=copy.deepcopy(actual)
        if actual.get('creationTimestamp') is None: actual.pop('creationTimestamp',None)
        if actual.get('annotations')=={}: actual.pop('annotations')
        if actual!=approved: raise RuntimeError('unreviewed template metadata/injection envelope')

    @staticmethod
    def html_claim(pod):
        mounts=[m['name'] for c in pod['containers'] for m in c.get('volumeMounts',[]) if m['mountPath']=='/var/www/html']
        claims=[v['persistentVolumeClaim']['claimName'] for v in pod.get('volumes',[]) if v['name'] in mounts and 'persistentVolumeClaim' in v]
        if len(mounts)!=1 or len(claims)!=1: raise RuntimeError('ambiguous HTML mapping')
        return claims[0]

    def bound_claim(self, claim, expected):
        pvc=self.obj('-n',NS,'get','pvc',claim)
        if pvc['metadata']['uid']!=expected.get('pvc/'+claim): raise RuntimeError('PVC UID mismatch')
        if pvc.get('status',{}).get('phase')!='Bound' or pvc['spec'].get('storageClassName')!='proof-local':
            raise RuntimeError('PVC must be Bound proof-local')
        pv=self.obj('get','pv',pvc['spec']['volumeName'])
        ref=pv['spec'].get('claimRef',{})
        if (pv['metadata']['uid']!=expected.get('pv/'+pv['metadata']['name'])
            or pv['spec'].get('storageClassName')!='proof-local'
            or ref.get('uid')!=pvc['metadata']['uid'] or ref.get('name')!=claim or ref.get('namespace')!=NS):
            raise RuntimeError('PV source/claim UID mismatch')

    def identities(self):
        r=self.authorize(); expected=r.get('object_uids',{}); objects={}
        for kind,name in [('secret','proof-credentials'),('deployment','nextcloud'),('deployment','postgres'),
                          ('deployment','redis'),('cronjob','nextcloud-cron')]:
            obj=self.obj('-n',NS,'get',kind,name)
            if not expected.get(kind+'/'+name) or expected[kind+'/'+name]!=obj['metadata']['uid']:
                raise RuntimeError('retained object UID mismatch')
            objects[name]=obj
        native=objects['nextcloud-cron']['spec']['jobTemplate']['spec']
        approved=self.approved('nextcloud-cron')['spec']['jobTemplate']['spec']
        if objects['nextcloud-cron']['spec'].get('suspend') is not True:
            raise RuntimeError('schedule must stay suspended')
        if any(native.get(k,1)!=1 for k in ('parallelism','completions')) or native.get('completionMode','NonIndexed')!='NonIndexed' or native.get('suspend',False):
            raise RuntimeError('CronJob serial execution envelope mismatch')
        if set(native)-set(approved)-{'parallelism','completions','completionMode','suspend'}:
            raise RuntimeError('unreviewed CronJob job envelope')
        self.template_metadata(native['template'].get('metadata',{}),approved['template'].get('metadata',{}))
        for key in ('backoffLimit','activeDeadlineSeconds'):
            if native.get(key)!=approved[key]: raise RuntimeError('CronJob deadline/retry mismatch')
        html=self.html_claim(native['template']['spec'])
        if html!=self.html_claim(objects['nextcloud']['spec']['template']['spec']) or html!=r.get('html_claim'):
            raise RuntimeError('live Deployment/CronJob HTML mapping mismatch')
        approved=copy.deepcopy(approved['template']['spec'])
        approved['volumes'][0]['persistentVolumeClaim']['claimName']=html
        self.envelope(native['template']['spec'],approved)
        claims={html}
        for name in ('postgres','redis'):
            pod=objects[name]['spec']['template']['spec']
            backend=self.approved(name)['spec']['template']
            self.template_metadata(objects[name]['spec']['template'].get('metadata',{}),backend.get('metadata',{}))
            self.envelope(pod,backend['spec'])
            if pod['containers'][0]['image']!=r.get('backend_images',{}).get(name):
                raise RuntimeError('backend image binding mismatch')
            claims.update(v['persistentVolumeClaim']['claimName'] for v in pod.get('volumes',[]) if 'persistentVolumeClaim' in v)
        for claim in sorted(claims): self.bound_claim(claim,expected)
        self.html=html

    def admission(self):
        self.identities()
        pods=self.obj('get','pods','-A')['items']
        cron.barrier(pods)
        for pod in pods:
            if pod['metadata']['namespace']!=NS: continue
            app=pod['metadata'].get('labels',{}).get('app.kubernetes.io/name')
            if app not in ('postgres','redis'): raise RuntimeError('unselected backend pod')
            # Admission must include actual Pod resources, not only controller intent/image.
            actual=copy.deepcopy(pod['spec'])
            # Token automount stays disabled; injected sidecars/volumes are rejected.
            self.envelope(actual,self.approved(app)['spec']['template']['spec'],actual_pod=True)
        for kind in ('deployments,statefulsets','cronjobs'):
            for c in self.obj('get',kind,'-A')['items']:
                m=c['metadata']; ns=m.get('namespace','')
                if not ns.startswith('proof-'): continue
                if kind=='cronjobs':
                    if not c['spec'].get('suspend',False): raise RuntimeError('unsuspended proof schedule')
                elif not (ns==NS and m['name'] in ('postgres','redis')) and c['spec'].get('replicas',1):
                    raise RuntimeError('active unselected controller/helper')
        # Independent observations, never receipt-reported passing booleans.
        self.memory_admission()

    def memory_admission(self):
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
        """Capture ALL raw states/logs before interpreting payload success or OOM."""
        gaps=[]; logs={}
        try:
            pods=self.obj('-n',NS,'get','pods','-l','job-name='+name)
            self.save(dict(event='pods',run_id=self.run,job=name,pods=pods))
        except Exception as e:
            self.save(dict(event='capture-gap',run_id=self.run,job=name,error=type(e).__name__,
                stdout=getattr(e,'stdout',None),stderr=getattr(e,'stderr',None)))
            raise
        for pod in pods['items']:
            for c in pod['spec'].get('initContainers',[])+pod['spec']['containers']:
                for previous in (False,True):
                    # Previous is meaningful only for restarted containers, but current is always attempted.
                    statuses=pod.get('status',{}).get('containerStatuses',[])+pod.get('status',{}).get('initContainerStatuses',[])
                    if previous and not any(x['name']==c['name'] and x.get('restartCount',0) for x in statuses): continue
                    try:
                        raw=self.call('-n',NS,'logs',pod['metadata']['name'],'-c',c['name'],*(['--previous'] if previous else []))
                        self.save(dict(event='private-previous-log' if previous else 'private-log',
                            run_id=self.run,job=name,pod=pod['metadata']['name'],container=c['name'],log=raw))
                        if not previous: logs[(pod['metadata']['name'],c['name'])]=raw
                    except Exception as e:
                        gaps.append(type(e).__name__)
                        self.save(dict(event='capture-gap',run_id=self.run,job=name,previous=previous,error=type(e).__name__,
                            stdout=getattr(e,'stdout',None),stderr=getattr(e,'stderr',None)))
        if gaps:
            # A reachable API can truthfully report no logs for a waiting/failed
            # container. Retain raw errors/state, fail acceptance, but still retire
            # the own helper. An unreachable API cannot confirm safe cleanup.
            try:
                refreshed=self.obj('-n',NS,'get','pods','-l','job-name='+name)
                self.save(dict(event='capture-gap-pods',run_id=self.run,job=name,pods=refreshed))
            except Exception:
                self.save(dict(event='capture-unreachable',run_id=self.run,job=name))
                raise RuntimeError('raw forensic capture gap; API unreachable')
        return pods,logs,gaps

    def validate_forensics(self, evidence):
        pods,logs,gaps=evidence
        if gaps: raise RuntimeError('raw forensic capture gap')
        if len(pods['items'])!=1: raise RuntimeError('exact one phase pod required')
        pod=pods['items'][0]; statuses=pod.get('status',{}).get('containerStatuses',[])
        if len(statuses)!=1: raise RuntimeError('missing/ambiguous native container forensics')
        c=statuses[0]
        observation=json.loads(logs[(pod['metadata']['name'],c['name'])].splitlines()[-1])
        cg=observation.get('cgroups',{})
        if observation.get('status')=='BLOCKED_OR_FAILED': raise RuntimeError('native payload failed')
        if any(not isinstance(cg.get(k),str) for k in ('memory.peak','memory.current','memory.events','memory.stat')):
            raise RuntimeError('native cgroup measurement gap')
        events=dict(line.split() for line in cg['memory.events'].splitlines())
        if int(cg['memory.peak'])>192*1048576 or int(events.get('oom_kill','0')) or int(events.get('oom','0')):
            raise RuntimeError('native cgroup OOM/limit failure')
        if c.get('state',{}).get('terminated',{}).get('exitCode')!=0:
            raise RuntimeError('native phase failed')

    def delete_own_job(self, name):
        uid=self.jobs.get(name) or self.authorize().get('object_uids',{}).get('job/'+name)
        if not uid or not any(name=='nc-'+p+'-'+self.run for p in (*cron.PHASES,'cleanup')):
            raise RuntimeError('own Job UID binding required')
        job=self.obj('-n',NS,'get','job',name)
        if job['metadata']['uid']!=uid: raise RuntimeError('Job UID mismatch')
        self.call('delete','--raw','/apis/batch/v1/namespaces/'+NS+'/jobs/'+name,'-f','-',
            data=json.dumps(dict(apiVersion='v1',kind='DeleteOptions',propagationPolicy='Foreground',preconditions=dict(uid=uid))))
        self.call('-n',NS,'wait','--for=delete','job/'+name,'--timeout=180s')
        if self.obj('-n',NS,'get','jobs','--field-selector','metadata.name='+name)['items']:
            raise RuntimeError('Job remains after deletion')
        if self.obj('-n',NS,'get','pods','-l','job-name='+name)['items']:
            raise RuntimeError('phase pod persists after deletion')
        self.active=None

    def retire_prior_jobs(self):
        # Only exact UUID phase names AND parent/journal UID bindings are eligible.
        for e in life.native_cron_events(self.state):
            if e.get('event')=='phase-created' and e.get('run_id')==self.run:
                self.jobs[e['name']]=e['uid']
        for job in self.obj('-n',NS,'get','jobs')['items']:
            name=job['metadata']['name']
            if any(name=='nc-'+p+'-'+self.run for p in (*cron.PHASES,'cleanup')):
                self.active=name
                self.forensics(name)
                self.delete_own_job(name)

    def phase(self, phase):
        self.admission()
        document=cron.job(phase,self.run); name=document['metadata']['name']
        document['spec']['template']['spec']['volumes'][0]['persistentVolumeClaim']['claimName']=self.html
        if phase=='cron':
            source=self.obj('-n',NS,'get','cronjob','nextcloud-cron')
            template=copy.deepcopy(source['spec']['jobTemplate']['spec'])
            original=template['template']['spec']
            expected=document['spec']['template']['spec']
            if (original.get('initContainers') or len(original['containers'])!=1
                or original.get('automountServiceAccountToken') is not False
                or original.get('securityContext')!=expected['securityContext']
                or original['containers'][0].get('securityContext')!=expected['containers'][0]['securityContext']
                or resources(original['containers'][0].get('resources',{}))!=resources(expected['containers'][0]['resources'])):
                raise RuntimeError('CronJob-derived security/resource envelope mismatch')
            # Derive from suspended native template, adding only reviewed CLI instrumentation.
            original['containers'][0].update(command=expected['containers'][0]['command'],
                env=expected['containers'][0]['env'],envFrom=expected['containers'][0]['envFrom'],
                volumeMounts=expected['containers'][0]['volumeMounts'])
            original['volumes']=expected['volumes']
            template.update(backoffLimit=0,activeDeadlineSeconds=180)
            document['spec']=template
        self.save(dict(event='phase-intent',run_id=self.run,phase=phase,job=document))
        created=json.loads(self.call('create','-f','-','-o','json',data=json.dumps(document)))
        self.active=name; self.jobs[name]=created['metadata']['uid']
        self.save(dict(event='phase-created',run_id=self.run,name=name,uid=self.jobs[name]))
        failure=None
        try:
            self.call('-n',NS,'wait','--for=condition=complete','job/'+name,'--timeout=190s')
        except Exception as e: failure=e
        # An unreachable API blocks confirmed deletion; reachable capture/validation failures still retire the helper.
        evidence=self.forensics(name)
        try: self.validate_forensics(evidence)
        except Exception as e: failure=e
        self.delete_own_job(name)
        if failure: raise failure

    def stop(self):
        # Pending journal must NOT block stop. Receipt/target still mandatory;
        # expired/unreachable target is reported pending, never bypassed/restarted.
        self.authorize()
        self.save(dict(event='stop-intent',run_id=self.run))
        # Strict capture here rather than the legacy best-effort deletion hook.
        self.save(dict(event='stop-pods',run_id=self.run,pods=self.obj('-n',NS,'get','pods')))
        self.call('-n',NS,'scale','deployment/postgres','deployment/redis','--replicas=0')
        self.retire_prior_jobs()
        self.call('-n',NS,'wait','--for=delete','pod','--all','--timeout=180s')
        if self.obj('-n',NS,'get','pods')['items']: raise RuntimeError('stop pods remain')

    def run_sequence(self):
        self.authorize(start=True)
        if self.pending(): raise RuntimeError('pending private cleanup blocks activation')
        self.unused_run()
        bundle=cron.compile_bundle(self.run)
        self.admission()
        self.require_stopped()
        self.save(dict(event='pending',run_id=self.run,intent=cron.intent(self.run)))
        try:
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

    def require_stopped(self):
        for name in ('postgres','redis','nextcloud'):
            if self.obj('-n',NS,'get','deployment',name)['spec'].get('replicas',1)!=0:
                raise RuntimeError('initial backend/frontend controllers must be stopped')

    def cleanup_only(self):
        # A NEW action=cleanup receipt may target the old run UUID, never refresh old bytes.
        self.scope='cleanup'
        r=self.authorize()
        if r['expires']-time.time()<780: raise RuntimeError('cleanup and stop window unavailable')
        if self.run not in self.pending(): raise RuntimeError('cleanup requires own pending journal')
        self.identities()
        self.require_stopped()
        self.save(dict(event='cleanup-intent',run_id=self.run))
        try:
            self.retire_prior_jobs()
            self.admission(); self.require_stopped()
            self.call('-n',NS,'scale','deployment/postgres','deployment/redis','--replicas=1')
            self.call('-n',NS,'wait','--for=condition=available','deployment/postgres','deployment/redis','--timeout=180s')
            self.phase('cleanup')
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
    elif a.action=='stop':
        s.scope='stop'; s.stop()
    else:
        s.cleanup_only()
    print('Guarded sequence ended; inspect private UUID journal. No general application acceptance implied.')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('Native cron BLOCKED_OR_FAILED: '+type(e).__name__)
        raise SystemExit(1)
