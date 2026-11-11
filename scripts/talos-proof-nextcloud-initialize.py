#!/usr/bin/env python3
"""Separate create-only stopped objects / read-only binding scope. OFFLINE until new grant.
Never installs, starts applications, issues a full-run receipt, or deletes storage.
"""
import argparse
import copy
import json
import math
import os
import re
import stat
import time
import yaml

import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('init_supervisor',Path(__file__).with_name('talos-proof-nextcloud-cron-supervisor.py'))
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
NS=s.NS
KINDS={'Deployment':'deployment','CronJob':'cronjob','Service':'service',
       'PersistentVolumeClaim':'pvc','ConfigMap':'configmap'}
STORAGE=s.ROOT/'kubernetes/platform/storage/storage.yaml'
STORAGE_DOCS=list(yaml.safe_load_all(STORAGE.read_text()))
STORAGE_CONFIG=next(d for d in STORAGE_DOCS if d['kind']=='ConfigMap')['data']
HELPER=yaml.safe_load(STORAGE_CONFIG['helperPod.yaml'])['spec']['containers'][0]
IMAGE=HELPER['image']


def declarations(html):
    if html not in ('nextcloud-data',):
        # Alias is parent-bound; never interpolate arbitrary paths into shell.
        import re
        if not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?',html):
            raise RuntimeError('invalid explicit HTML claim alias')
    result={}
    for name in ('nextcloud','postgres','redis','cronjob'):
        for d in yaml.safe_load_all((s.ROOT/'kubernetes/apps/data/nextcloud'/ (name+'.yaml')).read_text()):
            d=copy.deepcopy(d)
            if d['kind']=='PersistentVolumeClaim' and d['metadata']['name']=='nextcloud-data': d['metadata']['name']=html
            pod=(d.get('spec',{}).get('template',{}) or d.get('spec',{}).get('jobTemplate',{}).get('spec',{}).get('template',{})).get('spec',{})
            for v in pod.get('volumes',[]):
                if v.get('persistentVolumeClaim',{}).get('claimName')=='nextcloud-data': v['persistentVolumeClaim']['claimName']=html
            d['metadata']['namespace']=NS
            result[KINDS[d['kind']]+'/'+d['metadata']['name']]=d
    return result


class Initializer(s.Supervisor):
    def __init__(self,state,run):
        super().__init__(state,run)
        self.scope='initialize'

    def authorize(self,start=False):
        path=s.life.no_symlinks(os.environ.get('TALOS_PROOF_DATA_LEASE','/nonexistent'))
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600: raise RuntimeError('private initialization receipt required')
        raw=path.read_bytes(); r=json.loads(raw)
        expected=dict(group='nextcloud',stage='cron',action=self.scope,run_id=self.run,
            state_dir=str(self.state),budget_mib=832,cleanup_authorized=True,
            selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'],
            phases=['stopped-objects','readonly-binding'] if self.scope=='initialize' else ['initialization-cleanup'],
            namespace=NS,storage_device='/dev/sdb1')
        if any(r.get(k)!=v for k,v in expected.items()): raise RuntimeError('separate exact initialization receipt required')
        if (type(r.get('expires')) not in (int,float) or not math.isfinite(r['expires']) or r['expires']<=time.time()
            or not all(isinstance(r.get(k),str) and r[k] for k in ('context','node_uid','namespace_uid','html_claim'))
            or r.get('endpoint')!=s.life.EXPECTED_ENDPOINT): raise RuntimeError('initialization target/expiry missing')
        if start and r['expires']-time.time()<900: raise RuntimeError('initialization cleanup window unavailable')
        if not re.fullmatch(r'[1-9][0-9]*:(?:0|[1-9][0-9]*)',str(r.get('storage_device_id',''))):raise RuntimeError('parent-bound storage major:minor identity required')
        docs=declarations(r['html_claim'])
        missing=r.get('allowed_missing_resources')
        if not isinstance(missing,list) or not all(isinstance(k,str) for k in missing) or missing!=sorted(set(missing)) or not set(missing)<=set(docs): raise RuntimeError('exact allowed missing resources required')
        if not isinstance(r.get('existing_uids'),dict) or set(r['existing_uids'])!=set(docs)-set(missing)|{'secret/proof-credentials'}:
            raise RuntimeError('all existing identities must be parent-bound')
        if set(r['existing_uids']) & set(missing) or not all(r['existing_uids'].values()): raise RuntimeError('invalid existing UID bindings')
        if self.original is not None and self.original!=raw: raise RuntimeError('immutable initialization receipt changed')
        s.life.lease('nextcloud')
        self.original=raw
        return r

    def call(self,*args,data=None):
        if s.life.MUTATIONS.intersection(args):self.target()
        return super().call(*args,data=data)

    def target(self):
        r=self.authorize()
        ns=self.obj('get','namespace',NS)
        if ns['metadata']['uid']!=r['namespace_uid']: raise RuntimeError('namespace UID mismatch')
        return r

    def barriers(self):
        self.target()
        for pod in self.obj('get','pods','-A')['items']:
            ns=pod['metadata']['namespace']
            if ns.startswith('proof-') or (ns=='local-path-storage' and not self.provisioner_pod(pod)):
                raise RuntimeError('foreign/helper pod blocks initialization')
        for c in self.obj('get','deployments,statefulsets,daemonsets,cronjobs,jobs','-A')['items']:
            if not c['metadata']['namespace'].startswith('proof-'): continue
            if c['kind']=='CronJob':
                if c['spec'].get('suspend') is not True: raise RuntimeError('unsuspended schedule')
            elif c['kind'] in ('Job','DaemonSet') or c['spec'].get('replicas',1)!=0:
                raise RuntimeError('unstopped proof controller')

    def provisioner_pod(self,pod):
        # Only the actual platform controller envelope may be exempt, never a label alone.
        approved=next(d for d in STORAGE_DOCS if d['kind']=='Deployment')
        owners=pod['metadata'].get('ownerReferences',[])
        if not any(o.get('kind')=='ReplicaSet' and o.get('name','').startswith('local-path-provisioner-') for o in owners): return False
        try:
            owner=next(o for o in owners if o.get('kind')=='ReplicaSet')
            rs=self.obj('-n','local-path-storage','get','replicaset',owner['name'])
            dep=self.obj('-n','local-path-storage','get','deployment','local-path-provisioner')
            if rs['metadata']['uid']!=owner['uid'] or not any(o.get('kind')=='Deployment' and o.get('uid')==dep['metadata']['uid'] for o in rs['metadata'].get('ownerReferences',[])):return False
            actual=copy.deepcopy(pod['spec'])
            if actual.get('serviceAccount')=='local-path-provisioner-service-account':actual.pop('serviceAccount')
            volumes=actual.get('volumes',[])
            tokens=[v for v in volumes if v['name'].startswith('kube-api-access-')]
            if len(tokens)!=1:return False
            token=tokens[0]
            expected=dict(defaultMode=420,sources=[dict(serviceAccountToken=dict(expirationSeconds=3607,path='token')),
                dict(configMap=dict(name='kube-root-ca.crt',items=[dict(key='ca.crt',path='ca.crt')])),
                dict(downwardAPI=dict(items=[dict(path='namespace',fieldRef=dict(apiVersion='v1',fieldPath='metadata.namespace'))]))])
            if token.get('projected')!=expected or set(token)!={'name','projected'}:return False
            actual['volumes'].remove(token)
            for c in actual['containers']:
                mount=dict(name=token['name'],readOnly=True,mountPath='/var/run/secrets/kubernetes.io/serviceaccount')
                if mount not in c.get('volumeMounts',[]):return False
                c['volumeMounts'].remove(mount)
            # Only this explicit default SA projection is allowed, not arbitrary injected mounts.
            self.envelope(actual,approved['spec']['template']['spec'],actual_pod=True)
        except RuntimeError: return False
        return True

    def storage(self):
        sc=self.obj('get','storageclass','proof-local')
        if any(sc.get(k)!=v for k,v in dict(provisioner='rancher.io/local-path',volumeBindingMode='WaitForFirstConsumer',reclaimPolicy='Retain').items()):
            raise RuntimeError('proof-local must be Retain WaitForFirstConsumer')
        config=self.obj('-n','local-path-storage','get','configmap','local-path-config')
        if config.get('data')!=STORAGE_CONFIG or HELPER['resources']['limits']['memory']!='32Mi': raise RuntimeError('unreviewed provisioner/device/32Mi helper policy')
        dep=self.obj('-n','local-path-storage','get','deployment','local-path-provisioner')
        approved=next(d for d in STORAGE_DOCS if d['kind']=='Deployment')
        self.envelope(dep['spec']['template']['spec'],approved['spec']['template']['spec'])

    def validate_present(self,key,actual,approved):
        if actual['kind']!=approved['kind']: raise RuntimeError('object kind mismatch')
        a=copy.deepcopy(actual.get('spec',{})); b=copy.deepcopy(approved.get('spec',{}))
        if actual['kind']=='Deployment':
            self.envelope(a['template']['spec'],b['template']['spec'])
            self.template_metadata(a['template'].get('metadata',{}),b['template'].get('metadata',{}))
            a.pop('template');b.pop('template')
            for k,v in {'revisionHistoryLimit':10,'progressDeadlineSeconds':600}.items():
                if a.get(k)==v:a.pop(k)
        elif actual['kind']=='CronJob':
            for jt in (a['jobTemplate'],b['jobTemplate']):
                if jt.get('metadata')=={'creationTimestamp':None}: jt.pop('metadata')
            ap=a['jobTemplate']['spec'];bp=b['jobTemplate']['spec']
            self.envelope(ap['template']['spec'],bp['template']['spec'])
            self.template_metadata(ap['template'].get('metadata',{}),bp['template'].get('metadata',{}))
            ap.pop('template');bp.pop('template')
            for k,v in dict(parallelism=1,completions=1,completionMode='NonIndexed',suspend=False).items():
                if ap.get(k)==v:ap.pop(k)
        elif actual['kind']=='Service':
            # Only named API defaults; no ignoring arbitrary unknown API fields.
            for k,v in dict(type='ClusterIP',sessionAffinity='None',internalTrafficPolicy='Cluster',ipFamilyPolicy='SingleStack',ipFamilies=['IPv4']).items():
                if a.get(k)==v:a.pop(k)
            ip=a.pop('clusterIP',None); ips=a.pop('clusterIPs',None)
            import ipaddress
            if ip is not None:
                if not ipaddress.ip_address(ip).is_private or ips!=[ip]: raise RuntimeError('unexpected Service allocation')
            elif ips is not None: raise RuntimeError('unexpected Service allocation')
            for p in a['ports']:
                if p.get('protocol')=='TCP':p.pop('protocol')
        if a!=b or actual.get('data')!=approved.get('data'): raise RuntimeError('present declaration mismatch: '+key)
        # Preserve but reject injection metadata rather than silently adopting it.
        if actual['metadata'].get('labels',{})!=approved['metadata'].get('labels',{}): raise RuntimeError('present labels mismatch')
        annotations=copy.deepcopy(actual['metadata'].get('annotations',{}))
        if actual['kind']=='Deployment':
            revision=annotations.get('deployment.kubernetes.io/revision')
            if isinstance(revision,str) and revision.isdecimal(): annotations.pop('deployment.kubernetes.io/revision')
        if annotations: raise RuntimeError('unreviewed present annotations')

    def inventory(self):
        r=self.target(); docs=declarations(r['html_claim']); found={}
        for obj in self.obj('-n',NS,'get','deployments,cronjobs,services,pvc,configmaps,secrets')['items']:
            key=KINDS.get(obj['kind'],'secret')+'/'+obj['metadata']['name']
            if key in docs or key=='secret/proof-credentials': found[key]=obj
        if 'secret/proof-credentials' not in found: raise RuntimeError('missing existing secret; never generate')
        secret=found['secret/proof-credentials']
        if secret.get('type')!='Opaque' or not all(secret.get('data',{}).get(k) for k in ('POSTGRES_PASSWORD','NEXTCLOUD_ADMIN_PASSWORD','REDIS_HOST_PASSWORD')):
            raise RuntimeError('existing credential keys missing; never repair')
        if set(docs)-set(found)!=set(r['allowed_missing_resources']): raise RuntimeError('missing allowlist drift / partial initialization')
        for key,obj in found.items():
            if obj['metadata']['uid']!=r['existing_uids'].get(key): raise RuntimeError('existing UID mismatch')
            if key in docs:self.validate_present(key,obj,docs[key])
        # This narrow binding path only mounts THREE NEW claims, never retained/partial PVCs.
        claims={r['html_claim'],'postgres-data','redis-data'}
        if len(claims)!=3 or not {'pvc/'+n for n in claims}<=set(r['allowed_missing_resources']):
            raise RuntimeError('binding requires exactly three explicitly missing new PVCs; retained/partial blocks')
        return docs

    def verify_created(self,docs,created,before_binding=False):
        r=self.target()
        for key,doc in docs.items():
            kind,name=key.split('/')
            obj=self.obj('-n',NS,'get',kind,name)
            if obj['metadata']['uid']!=created.get(key,r['existing_uids'].get(key)):
                raise RuntimeError('created/existing UID drift')
            if kind=='pvc':
                if before_binding and (obj.get('status',{}).get('phase') not in (None,'Pending') or obj['spec'].get('volumeName')):
                    raise RuntimeError('partial/unexpected binding before helper')
                actual=copy.deepcopy(obj['spec']);expected=doc['spec']
                actual.pop('volumeName',None)
                if actual.get('volumeMode')=='Filesystem':actual.pop('volumeMode')
                if actual!=expected:raise RuntimeError('new PVC spec mismatch')
            else:self.validate_present(key,obj,doc)
        secret=self.obj('-n',NS,'get','secret','proof-credentials')
        if secret['metadata']['uid']!=r['existing_uids']['secret/proof-credentials']:raise RuntimeError('Secret UID drift')

    def binding_job(self,claims,pvc_uids,device_id):
        # Pure native busybox, no interpreter/installation/chown/fsGroup or write mount.
        if not re.fullmatch(r'[1-9][0-9]*:(?:0|[1-9][0-9]*)',device_id):raise RuntimeError('invalid block device identity')
        roots=[]
        import uuid
        for n in claims:
            uid=pvc_uids[n]
            if str(uuid.UUID(uid))!=uid:raise RuntimeError('canonical new PVC UID required')
            roots.append('/pvc-'+uid+'_'+NS+'_'+n)
        cases='\n'.join(str(i)+") root='"+root+"' ;;" for i,root in enumerate(roots))
        command='''set -eu
finish() {
  for f in memory.current memory.peak memory.events memory.stat; do
    echo "CGROUP $f"; cat "/sys/fs/cgroup/$f" || exit 91
  done
}
trap finish EXIT
for i in 0 1 2; do
  p="/claims/$i"
  case "$i" in
__ROOT_CASES__
  *) exit 92 ;;
  esac
  awk -v p="$p" -v root="$root" -v device="__DEVICE_ID__" '$3 == device && $4 == root && $5 == p { for(i=7;i<=NF;i++) if($i=="-" && $(i+1)=="xfs" && $(i+2)=="/dev/sdb1") { split($6,o,","); for(j in o) if(o[j]=="ro") ok=1 } } END { exit !ok }' /proc/self/mountinfo
  test -d "$p"; test ! -L "$p"
  entries=$(find "$p" -mindepth 1 -maxdepth 1 -print -quit) || exit 93
  test -z "$entries"
done
echo PROOF_BINDING_EMPTY_READONLY
'''.replace('__ROOT_CASES__',cases).replace('__DEVICE_ID__',device_id)
        return dict(apiVersion='batch/v1',kind='Job',metadata=dict(name='nc-binding-'+self.run,namespace=NS),spec=dict(backoffLimit=0,activeDeadlineSeconds=180,template=dict(spec=dict(
            automountServiceAccountToken=False,restartPolicy='Never',nodeSelector={'kubernetes.io/hostname':'talos-proof'},
            securityContext=dict(runAsUser=0,runAsGroup=0,seccompProfile=dict(type='RuntimeDefault')),
            containers=[dict(name='binding',image=IMAGE,command=['sh','-ec',command],
                securityContext=dict(allowPrivilegeEscalation=False,readOnlyRootFilesystem=True,capabilities=dict(drop=['ALL'])),
                resources=dict(requests=dict(cpu='5m',memory='64Mi'),limits=dict(cpu='100m',memory='64Mi')),
                volumeMounts=[dict(name='claim'+str(i),mountPath='/claims/'+str(i),readOnly=True) for i in range(3)])],
            volumes=[dict(name='claim'+str(i),persistentVolumeClaim=dict(claimName=n,readOnly=True)) for i,n in enumerate(claims)]))))

    def delete_binding(self,name,uid):
        if name!='nc-binding-'+self.run or self.obj('-n',NS,'get','job',name)['metadata']['uid']!=uid:
            raise RuntimeError('binding helper UID mismatch')
        self.call('delete','--raw','/apis/batch/v1/namespaces/'+NS+'/jobs/'+name,'-f','-',data=json.dumps(dict(apiVersion='v1',kind='DeleteOptions',propagationPolicy='Foreground',preconditions=dict(uid=uid))))
        self.call('-n',NS,'wait','--for=delete','job/'+name,'--timeout=180s')
        if self.obj('-n',NS,'get','jobs','--field-selector','metadata.name='+name)['items'] or self.obj('-n',NS,'get','pods','-l','job-name='+name)['items']:
            raise RuntimeError('binding helper absence unconfirmed')

    def provisioner_forensics(self):
        pods=self.obj('-n','local-path-storage','get','pods')['items']
        self.save(dict(event='initialization-provisioner-states',run_id=self.run,pods=pods))
        for p in pods:
            if self.provisioner_pod(p):continue
            for c in p['spec']['containers']:
                for previous in (False,True):
                    try:
                        log=self.call('-n','local-path-storage','logs',p['metadata']['name'],'-c',c['name'],*(['--previous'] if previous else []))
                        self.save(dict(event='initialization-provisioner-log',run_id=self.run,pod=p['metadata'],previous=previous,log=log))
                    except Exception as e:self.save(dict(event='initialization-provisioner-capture-gap',run_id=self.run,error=type(e).__name__,pod=p['metadata'],previous=previous))
        self.save(dict(event='initialization-provisioner-capture-gap',run_id=self.run,
            reason='automatic provisioner deletion can precede observation; no complete lifetime logs/cgroup coverage claimed'))

    def initialize(self):
        self.authorize(start=True)
        if self.pending():raise RuntimeError('pending cleanup blocks initialization')
        self.unused_run()
        docs=self.inventory();self.storage();self.barriers();self.memory_admission();self.barriers()
        r=self.authorize(); claims=sorted([r['html_claim'],'postgres-data','redis-data'])
        self.save(dict(event='pending',run_id=self.run,scope='initialize',allowed_missing_resources=r['allowed_missing_resources']))
        created={}
        try:
            for key in r['allowed_missing_resources']:
                self.barriers();self.memory_admission()
                # Fresh create-only API: races return AlreadyExists, never overwrite/recreate.
                self.save(dict(event='initialization-create-intent',run_id=self.run,key=key,document=docs[key]))
                obj=json.loads(self.call('create','-f','-','-o','json',data=json.dumps(docs[key])))
                created[key]=obj['metadata']['uid']
                self.save(dict(event='initialization-created',run_id=self.run,key=key,uid=created[key]))
            self.verify_created(docs,created,before_binding=True)
            self.storage();self.barriers();self.memory_admission();self.barriers()
            job=self.binding_job(claims,{n:created['pvc/'+n] for n in claims},r['storage_device_id']);name=job['metadata']['name']
            self.save(dict(event='initialization-binding-intent',run_id=self.run,job=job))
            obj=json.loads(self.call('create','-f','-','-o','json',data=json.dumps(job)))
            uid=obj['metadata']['uid']
            self.save(dict(event='initialization-binding-created',run_id=self.run,name=name,uid=uid))
            failure=None
            try:self.call('-n',NS,'wait','--for=condition=complete','job/'+name,'--timeout=190s')
            except Exception as e:failure=e
            try:self.provisioner_forensics()
            except Exception as e:
                failure=failure or e
                self.save(dict(event='initialization-provisioner-capture-gap',run_id=self.run,error=type(e).__name__))
            evidence=self.forensics(name) # raw current/previous logs + states BEFORE delete
            self.delete_binding(name,uid)
            if failure:raise failure
            rawpods,_,_=evidence
            for pod in rawpods['items']:
                self.envelope(pod['spec'],job['spec']['template']['spec'],actual_pod=True)
            self.validate_binding_evidence(evidence)
            expected={'pvc/'+n:created['pvc/'+n] for n in claims}
            for n in claims:
                pvc=self.obj('-n',NS,'get','pvc',n)
                pv=self.obj('get','pv',pvc['spec']['volumeName'])
                expected['pv/'+pv['metadata']['name']]=pv['metadata']['uid']
                self.bound_claim(n,expected)
                ps=pv['spec']; path=ps.get('local',ps.get('hostPath',{})).get('path','')
                if (ps.get('persistentVolumeReclaimPolicy')!='Retain' or
                    path!='/var/mnt/proof/'+ 'pvc-'+pvc['metadata']['uid']+'_'+NS+'_'+n or
                    ps.get('accessModes')!=['ReadWriteOnce'] or
                    s.quantity(ps.get('capacity',{}).get('storage','-1'))!=s.quantity(pvc['spec']['resources']['requests']['storage']) or
                    ps.get('nodeAffinity')!={'required':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'kubernetes.io/hostname','operator':'In','values':['talos-proof']}]}]}}):
                    raise RuntimeError('unexpected retained PV path/policy')
                self.save(dict(event='initialization-bound-observation',run_id=self.run,pvc=pvc,pv=pv))
            self.verify_created(docs,created)
            self.barriers()
            self.save(dict(event='initialization-stopped-bound',run_id=self.run,created_uids=created,
                full_run_authorized=False,provisioner_forensics_complete=False))
            self.save(dict(event='clean',run_id=self.run))
        except BaseException:
            self.save(dict(event='initialization-blocked-pending',run_id=self.run,created_uids=created))
            raise

    @staticmethod
    def validate_binding_evidence(evidence):
        # Shared capture returns raw log strings. No JSON/native payload interpretation here.
        rawpods,logs,gaps=evidence
        if gaps: raise RuntimeError('binding forensics gap')
        pods=rawpods['items']
        if len(pods)!=1:raise RuntimeError('one binding pod required')
        status=pods[0].get('status',{}).get('containerStatuses',[])
        if len(status)!=1 or status[0].get('restartCount',0)!=0 or status[0].get('state',{}).get('terminated',{}).get('exitCode')!=0:
            raise RuntimeError('binding container failed')
        log=logs.get((pods[0]['metadata']['name'],'binding'),'')
        if 'PROOF_BINDING_EMPTY_READONLY' not in log or not all('CGROUP '+f in log for f in ('memory.current','memory.peak','memory.events','memory.stat')):
            raise RuntimeError('missing emptiness/cgroup measurements')
        import re
        for name in ('memory.current','memory.peak'):
            match=re.search(r'^CGROUP '+re.escape(name)+r'\n([0-9]+)$',log,re.M)
            if not match or int(match[1])>64*1048576:raise RuntimeError('binding memory measurement/ceiling')
        if not re.search(r'^oom 0$',log,re.M) or not re.search(r'^oom_kill 0$',log,re.M):raise RuntimeError('binding OOM or missing events')

    def stop(self):
        # Original unexpired initialization grant permits retirement, never activation.
        self.scope='initialize';self.retire_binding()

    def cleanup_only(self):
        self.scope='initialization-cleanup';self.retire_binding()

    def retire_binding(self):
        # No create, scale, fixture or main rerun; pending journal does not inhibit stop.
        self.target()
        events=[e for e in s.life.native_cron_events(self.state) if e.get('run_id')==self.run]
        if not any(e.get('event')=='pending' and e.get('scope')=='initialize' for e in events):raise RuntimeError('original initialization intent required')
        bindings={e['name']:e['uid'] for e in events if e.get('event')=='initialization-binding-created'}
        for j in self.obj('-n',NS,'get','jobs')['items']:
            if j['metadata']['name']=='nc-binding-'+self.run:
                name=j['metadata']['name'];uid=bindings.get(name)
                if not uid:raise RuntimeError('unknown helper UID; new parent recovery needed')
                self.provisioner_forensics();self.forensics(name);self.delete_binding(name,uid)
        self.barriers()
        # Retain all created objects, including partially Bound PVCs. New init UUID cannot adopt them.
        self.save(dict(event='initialization-cleanup-stopped',run_id=self.run,retained_objects=True))
        self.save(dict(event='clean',run_id=self.run))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['initialize','stop','cleanup']);p.add_argument('--state',required=True);p.add_argument('--run-id',required=True)
    a=p.parse_args();i=Initializer(a.state,a.run_id)
    if a.action=='initialize':i.initialize()
    elif a.action=='stop':i.stop()
    else:i.cleanup_only()
    print('Stopped initialization scope ended. NEW post-binding parent UID receipt still required; no native acceptance.')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('Initialization BLOCKED_OR_FAILED: '+type(e).__name__)
        raise SystemExit(1)
