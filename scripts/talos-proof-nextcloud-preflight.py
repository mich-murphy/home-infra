#!/usr/bin/env python3
"""Separate receipt-bound failed-preflight release / read-only diagnosis.
OFFLINE until NEW exact parent authority. Never reruns the native six-phase run.
"""
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

spec=importlib.util.spec_from_file_location('preflight_supervisor',Path(__file__).with_name('talos-proof-nextcloud-cron-supervisor.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
SOURCES=('scripts/talos-proof-nextcloud-cron.py','scripts/talos-proof-nextcloud-cron.php',
         'scripts/talos-proof-nextcloud-cron-supervisor.py','scripts/talos-proof-data.py',
         'scripts/talos-proof-nextcloud-preflight.py')
ARTIFACTS=('docs/evidence/talos-data/nextcloud-cron-source-review-97384394-9c9c-47d4-8d17-50e63b9b62fd.json',
           'docs/evidence/talos-data/nextcloud-cron-docker-config-source.json',
           'docs/evidence/talos-data/nextcloud-packaged-metadata-bridge-49e437a1-23fe-491f-92e9-541137daaa6a.json',
           'docs/evidence/talos-data/nextcloud-public-image-parity-412faf37-f124-44b2-b52a-418ad71f9cd0.json')


BACKEND_PROFILE='backend-cgroup-v2-absolute-tools-execution-envelope-kill-after-v3'
CGROUP_FILES=('memory.current','memory.peak','memory.events','memory.stat')


def digest(raw): return hashlib.sha256(raw).hexdigest()


def canonical(value):
    try: return str(uuid.UUID(value))==value and uuid.UUID(value).version==4
    except (ValueError,TypeError,AttributeError): return False


def private_json(path,expected):
    path=s.life.no_symlinks(path);info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600
        or path==s.ROOT or s.ROOT in path.parents): raise RuntimeError('private provenance required')
    raw=path.read_bytes()
    if digest(raw)!=expected: raise RuntimeError('immutable provenance hash mismatch')
    return json.loads(raw)


class Preflight(s.Supervisor):
    def authorize(self,start=False):
        path=s.life.no_symlinks(os.environ.get('TALOS_PROOF_DATA_LEASE','/nonexistent'))
        if not stat.S_ISREG(path.lstat().st_mode) or stat.S_IMODE(path.stat().st_mode)!=0o600:
            raise RuntimeError('private preflight receipt required')
        raw=path.read_bytes();r=json.loads(raw)
        if self.scope not in ('release-preflight','diagnose-preflight'): raise RuntimeError('separate preflight scope required')
        required=dict(action=self.scope,phases=[self.scope],group='nextcloud',stage='cron',run_id=self.run,
            state_dir=str(self.state),namespace=s.NS,budget_mib=832,synthetic_age=False,cleanup_authorized=True,
            selected_controllers=['cronjob/nextcloud-cron','deployment/postgres','deployment/redis'])
        if self.scope=='diagnose-preflight': required['backend_forensics_profile']=BACKEND_PROFILE
        if any(r.get(k)!=v for k,v in required.items()): raise RuntimeError('exact separate preflight receipt required')
        if (not canonical(r.get('authorization_id')) or r['authorization_id']==self.run
            or type(r.get('issued')) not in (int,float) or not math.isfinite(r['issued']) or not 0<r['issued']<=time.time()
            or type(r.get('expires')) not in (int,float) or not math.isfinite(r['expires']) or not r['issued']<r['expires'] or r['expires']<=time.time()
            or r.get('endpoint')!=s.life.EXPECTED_ENDPOINT or not all(r.get(k) for k in ('context','node_uid','namespace_uid'))):
            raise RuntimeError('new exact target/authorization window required')
        if start and r['expires']-time.time()<(300 if self.scope=='release-preflight' else 900):
            raise RuntimeError('preflight observation/stop window unavailable')
        if self.original is not None and raw!=self.original: raise RuntimeError('immutable preflight receipt changed')
        if r.get('reviewed_source_sha256')!={name:digest((s.ROOT/name).read_bytes()) for name in SOURCES}:
            raise RuntimeError('reviewed preflight source drift')
        if r.get('reviewed_artifact_sha256')!={name:digest((s.ROOT/name).read_bytes()) for name in ARTIFACTS}:
            raise RuntimeError('reviewed packaged metadata/source index drift')
        s.cron.packaged_metadata()  # Includes transitive parent record, before consumption/API.
        events=s.life.native_cron_events(self.state)
        if start and any(e.get('authorization_id')==r['authorization_id'] for e in events): raise RuntimeError('replayed preflight authorization')
        if self.scope=='release-preflight': self.release_provenance(r)
        elif r.get('document_sha256')!=self.document_hashes(r['html_claim']): raise RuntimeError('diagnostic document drift')
        if not start:
            used=[e for e in events if e.get('event')=='preflight-authorized' and e.get('run_id')==self.run
                  and e.get('authorization_id')==r['authorization_id'] and e.get('scope')==self.scope
                  and e.get('receipt_sha256')==digest(raw)]
            if len(used)!=1: raise RuntimeError('single consumed preflight authority required')
            s.life.lease('nextcloud')
        self.original=raw
        return r

    def save(self,value):
        if self.original is not None:
            value={**value,'authorization_id':json.loads(self.original)['authorization_id']}
        return super().save(value)

    def consume(self):
        r=self.authorize(start=True)
        self.save(dict(event='preflight-authorized',run_id=self.run,scope=self.scope,receipt_sha256=digest(self.original)))
        return r

    def release_provenance(self,r):
        origin=private_json(r.get('origin_receipt_path','/nonexistent'),r.get('origin_receipt_sha256'))
        for key in ('run_id','state_dir','group','stage','context','endpoint','namespace','namespace_uid','node_uid',
                    'html_claim','object_uids','backend_images','network_policy_uids','selected_controllers','budget_mib'):
            if origin.get(key)!=r.get(key): raise RuntimeError('original retained identity drift')
        if (origin.get('action','run')!='run' or origin.get('phases')!=list(s.cron.PHASES)
            or origin.get('synthetic_age') is not True or r['issued']<=origin.get('issued',math.inf)
            or r.get('origin_source_sha256')!=origin.get('reviewed_source_sha256')):
            raise RuntimeError('original native receipt/source bindings required')
        sources=r.get('origin_source_sha256')
        if (not isinstance(sources,dict) or not all(re.fullmatch('[0-9a-f]{64}',str(sources.get(k,''))) for k in SOURCES[:-1])
            ):
            raise RuntimeError('original fixed preflight compiler/source provenance required')
        refs=r.get('origin_journal_sha256')
        if not isinstance(refs,dict) or not refs: raise RuntimeError('original journal hash map required')
        history=[]
        for name,sha in refs.items():
            if not isinstance(name,str) or not re.fullmatch(r'[0-9a-f-]{36}\.json',name) or str(uuid.UUID(name[:-5]))+'.json'!=name:
                raise RuntimeError('original journal filename required')
            e=private_json(self.state/name,sha)
            if e.get('run_id')!=self.run: raise RuntimeError('foreign original history')
            history.append(e)
        events=s.life.native_cron_events(self.state);prior=[e for e in events if e.get('run_id')==self.run]
        own_types={'preflight-authorized','preflight-release-blocked','preflight-release-observation'}
        for e in prior:
            if e not in history and (e.get('event') not in own_types or not canonical(e.get('authorization_id'))):
                raise RuntimeError('unreferenced or later original history')
        allowed={'pending','backend-start-intent','memory','phase-intent','phase-created','pods','private-log',
                 'blocked-pending-cleanup','stop-intent','stop-pods'}
        for kind in allowed:
            if sum(e.get('event')==kind for e in prior)!=sum(e.get('event')==kind for e in history):
                raise RuntimeError('duplicate/unreferenced original history')
        counts={kind:(3 if kind=='memory' else 1) for kind in allowed}
        if any(sum(e.get('event')==kind for e in history)!=count for kind,count in counts.items()):
            raise RuntimeError('complete original twelve-event history required')
        if any(e.get('event') not in allowed for e in history): raise RuntimeError('unknown/unconfirmed/later original history')
        def one(kind):
            found=[e for e in history if e.get('event')==kind]
            if len(found)!=1: raise RuntimeError('exact original preflight history required')
            return found[0]
        if self.pending()!={self.run} or len([e for e in prior if e.get('event')=='pending'])!=1:
            raise RuntimeError('sole original pending transaction required')
        if one('pending').get('intent')!=s.cron.intent(self.run): raise RuntimeError('original transaction intent mismatch')
        one('backend-start-intent');one('stop-intent');one('stop-pods')
        if one('blocked-pending-cleanup').get('active') is not None: raise RuntimeError('original helper retirement not recorded')
        expected=s.cron.job('preflight',self.run)
        expected['spec']['template']['spec']['volumes'][0]['persistentVolumeClaim']['claimName']=r['html_claim']
        intent=one('phase-intent');created=one('phase-created');name='nc-preflight-'+self.run
        # Hash binds the original intent, while the unchanged job-shape oracle
        # checks fixed RO/env/command. Compiler metadata bridge edits must not
        # make the historical PHP source equal to current code.
        if r.get('origin_preflight_document_sha256')!=digest(json.dumps(expected,sort_keys=True,separators=(',',':')).encode()):
            raise RuntimeError('original preflight document hash mismatch')
        if (intent.get('phase')!='preflight' or intent.get('job')!=expected or created.get('name')!=name
            or not isinstance(r.get('preflight_job_uid'),str) or not r['preflight_job_uid'] or created.get('uid')!=r['preflight_job_uid']):
            raise RuntimeError('exact readonly original preflight Job/UID required')
        pods=one('pods')
        if pods.get('job')!=name or len(pods.get('pods',{}).get('items',[]))!=1: raise RuntimeError('one recorded failed preflight Pod required')
        pod=pods['pods']['items'][0];meta=pod['metadata'];statuses=pod.get('status',{}).get('containerStatuses',[])
        if (meta.get('namespace')!=s.NS or pod.get('status',{}).get('phase')!='Failed'
            or not any(o.get('kind')=='Job' and o.get('name')==name and o.get('uid')==r['preflight_job_uid'] for o in meta.get('ownerReferences',[]))
            or len(statuses)!=1 or statuses[0].get('name')!='cli' or statuses[0].get('restartCount')!=0
            or statuses[0].get('state',{}).get('terminated',{}).get('exitCode') in (None,0)):
            raise RuntimeError('recorded failed preflight status/owner required')
        self.envelope(pod['spec'],expected['spec']['template']['spec'],actual_pod=True)
        log=one('private-log')
        if log.get('job')!=name or log.get('pod')!=meta['name'] or log.get('container')!='cli': raise RuntimeError('original private log identity mismatch')
        observation=json.loads(log['log'].splitlines()[-1])
        if observation.get('status')!='BLOCKED_OR_FAILED': raise RuntimeError('recorded payload failure required')
        stopped=private_json(r.get('origin_stop_snapshot_path','/nonexistent'),r.get('origin_stop_snapshot_sha256'))
        if (stopped.get('namespace',{}).get('metadata',{}).get('uid')!=r['namespace_uid']
            or len(stopped.get('nodes',[]))!=1 or stopped['nodes'][0]['metadata']['uid']!=r['node_uid']):
            raise RuntimeError('original confirmed stop target mismatch')
        finished=s.datetime.datetime.fromisoformat(statuses[0]['state']['terminated']['finishedAt'].replace('Z','+00:00')).timestamp()
        if (type(stopped.get('at')) not in (int,float) or not math.isfinite(stopped['at'])
            or not origin['issued']<finished<=stopped['at']<r['issued']):
            raise RuntimeError('post-failure confirmed stop timestamp required')
        self.stopped_snapshot(stopped,r)
        # Independently accepted provenance exists for this historical run only.
        if self.run=='33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1':
            review=json.loads((s.ROOT/'docs/evidence/talos-acceptance/nextcloud-native-failure-review-320eb83b065948108cf7672f6157a58b.json').read_bytes())
            if (r['origin_stop_snapshot_sha256']!=review['postfailure_snapshot_sha256']
                or r['preflight_job_uid']!=review['failed_helper_job_uid']
                or meta.get('uid')!=review['failed_helper_pod_uid']):
                raise RuntimeError('independently accepted historical provenance mismatch')

    def stopped_snapshot(self,stopped,r):
        # Snapshot contains raw API objects, not a receipt-reported passing flag.
        for field in ('pods','controllers'):
            if not isinstance(stopped.get(field),dict) or not isinstance(stopped[field].get('items'),list):
                raise RuntimeError('raw stopped snapshot list required')
        controllers=stopped['controllers']['items'];seen={}
        for c in controllers:
            if (c.get('kind') not in ('Deployment','StatefulSet','DaemonSet','CronJob','Job')
                or not isinstance(c.get('spec'),dict) or not all(c.get('metadata',{}).get(k) for k in ('name','namespace','uid'))):
                raise RuntimeError('raw stopped controller identity/spec required')
            key=c['kind'].lower()+'/'+c['metadata']['name']
            identity=(c['metadata']['namespace'],key)
            if identity in seen: raise RuntimeError('duplicate stopped controller')
            seen[identity]=c
        required={k:v for k,v in r['object_uids'].items() if k.startswith(('deployment/','cronjob/'))}
        if not {'deployment/nextcloud','deployment/postgres','deployment/redis','cronjob/nextcloud-cron'}<=required.keys():
            raise RuntimeError('retained stopped controllers required')
        for key,uid in required.items():
            c=seen.get((s.NS,key),{})
            if c.get('metadata',{}).get('uid')!=uid:
                raise RuntimeError('missing/changed retained stopped controller')
            if c['kind']!='CronJob' and type(c['spec'].get('replicas')) is not int:
                raise RuntimeError('explicit stopped replica state required')
        self.stopped_items(stopped['pods']['items'],controllers)

    def admission(self):
        # Diagnostic-only extension: no Job/DS object is safe, even without Pods.
        def barriers():
            for c in self.obj('get','jobs,daemonsets','-A')['items']:
                if c['metadata']['namespace'].startswith('proof-'):
                    raise RuntimeError('proof Job/DaemonSet blocks diagnosis')
            counts={'postgres':0,'redis':0};observed_memory=0
            for pod in self.obj('get','pods','-A')['items']:
                if not pod['metadata']['namespace'].startswith('proof-'): continue
                if not getattr(self,'backends_started',False):
                    raise RuntimeError('proof Pod before diagnostic backend startup')
                meta=pod['metadata'];app=meta.get('labels',{}).get('app.kubernetes.io/name')
                owners=meta.get('ownerReferences',[])
                if (meta['namespace']!=s.NS or app not in ('postgres','redis') or len(owners)!=1
                    or owners[0].get('kind')!='ReplicaSet' or owners[0].get('controller') is not True):
                    raise RuntimeError('exact owned backend Pod required')
                rs=self.obj('-n',s.NS,'get','replicaset',owners[0]['name'])
                r=self.authorize();parent=rs.get('metadata',{}).get('ownerReferences',[])
                if (rs.get('metadata',{}).get('uid')!=owners[0].get('uid')
                    or rs['metadata'].get('namespace')!=s.NS or len(parent)!=1
                    or parent[0].get('kind')!='Deployment' or parent[0].get('name')!=app
                    or parent[0].get('controller') is not True
                    or parent[0].get('uid')!=r['object_uids']['deployment/'+app]):
                    raise RuntimeError('backend Pod deployment ownership mismatch')
                self.save(dict(event='backend-observed-pod',run_id=self.run,backend=app,pod=pod))
                counts[app]+=1
                self.envelope(pod['spec'],self.approved(app)['spec']['template']['spec'],actual_pod=True)
                # Charge every observed Pod, including duplicates; no Deployment-count shortcut.
                observed_memory+=sum(s.quantity(c['resources']['limits']['memory']) for c in pod['spec']['containers'])
                status=pod.get('status',{});containers=status.get('containerStatuses',[])
                if (meta.get('deletionTimestamp') is not None or status.get('phase')!='Running'
                    or not any(c.get('type')=='Ready' and c.get('status')=='True' for c in status.get('conditions',[]))
                    or len(containers)!=len(pod['spec']['containers'])
                    or {c.get('name') for c in containers}!={c['name'] for c in pod['spec']['containers']}
                    or any(c.get('ready') is not True or type(c.get('restartCount')) is not int
                        or c['restartCount']!=0 or set(c.get('state',{}))!={'running'}
                        or c.get('lastState',{})!={} for c in containers)):
                    raise RuntimeError('backend Pod not healthy running/ready without restart evidence')
            if getattr(self,'backends_started',False):
                if observed_memory+s.quantity('192Mi')+s.quantity('192Mi')>s.quantity('832Mi'):
                    raise RuntimeError('all observed backend Pods exceed diagnostic memory budget')
                if counts!={'postgres':1,'redis':1}:
                    raise RuntimeError('exactly one healthy Pod per backend required')
        barriers()
        super().admission()
        barriers()

    def backend_identity(self,pod):
        """Ownership only; never require a healthy resource envelope for capture."""
        r=self.target();meta=pod['metadata'];name=meta.get('labels',{}).get('app.kubernetes.io/name')
        if name not in ('postgres','redis'): raise RuntimeError('backend name required')
        nodes=self.obj('get','nodes')['items']
        if (len(nodes)!=1 or nodes[0]['metadata'].get('uid')!=r['node_uid']
            or pod.get('spec',{}).get('nodeName')!=nodes[0]['metadata'].get('name')):
            raise RuntimeError('backend node drift')
        def identity(p):
            m=p.get('metadata',{});owners=m.get('ownerReferences',[])
            if (m.get('namespace')!=s.NS or not m.get('uid') or not m.get('name')
                or len(owners)!=1 or owners[0].get('kind')!='ReplicaSet'
                or owners[0].get('controller') is not True):
                raise RuntimeError('backend Pod identity/owner gap')
            rs=self.obj('-n',s.NS,'get','replicaset',owners[0]['name']);rm=rs.get('metadata',{});parents=rm.get('ownerReferences',[])
            if (rm.get('namespace')!=s.NS or rm.get('uid')!=owners[0].get('uid') or len(parents)!=1
                or any(parents[0].get(k)!=v for k,v in dict(kind='Deployment',name=name,uid=r['object_uids']['deployment/'+name],controller=True).items())):
                raise RuntimeError('backend retained Deployment ownership gap')
            return (m['name'],m['namespace'],m['uid'],owners,p.get('spec',{}).get('nodeName'),
                    [(c.get('name'),c.get('containerID'),c.get('restartCount'),c.get('state')) for c in (p.get('status',{}).get('containerStatuses',[])+p.get('status',{}).get('initContainerStatuses',[]))])
        expected=identity(pod)
        live=self.obj('-n',s.NS,'get','pod',meta['name'])
        if identity(live)!=expected: raise RuntimeError('backend Pod/container identity drift')
        return live

    def backend_execution_envelope(self,pod):
        # Only resources may drift for capture; every other execution-relevant
        # field (image/env/PATH/mounts/security/command/extra containers) is frozen.
        name=pod['metadata'].get('labels',{}).get('app.kubernetes.io/name')
        if name not in ('postgres','redis'): raise RuntimeError('backend execution identity required')
        actual=copy.deepcopy(pod['spec']);approved=copy.deepcopy(self.approved(name)['spec']['template']['spec'])
        for spec in (actual,approved):
            spec.pop('resources',None)
            for c in spec.get('containers',[])+spec.get('initContainers',[]): c.pop('resources',None)
        self.envelope(actual,approved,actual_pod=True)

    @staticmethod
    def backend_metrics(metrics,name):
        if set(metrics)!=set(CGROUP_FILES): raise RuntimeError('backend cgroup gap')
        limit={'postgres':384,'redis':64}[name]*1048576
        for key in ('memory.current','memory.peak'):
            if not re.fullmatch(r'[1-9][0-9]*\n?',metrics[key]) or int(metrics[key])>limit:
                raise RuntimeError('backend byte measurement/limit failure')
        parsed={}
        for key,required in (('memory.events',{'oom','oom_kill','max','high','low'}),('memory.stat',{'anon','file'})):
            values={}
            for line in metrics[key].splitlines():
                match=re.fullmatch(r'([a-z][a-z0-9_]*)[ \t]+(0|[1-9][0-9]*)',line)
                if not match or match[1] in values: raise RuntimeError('malformed backend counter')
                values[match[1]]=int(match[2])
            if not required<=values.keys(): raise RuntimeError('missing backend counter')
            parsed[key]=values
        if any(parsed['memory.events'][key] for key in ('oom','oom_kill','max','high')):
            raise RuntimeError('backend OOM/limit event')

    def backend_forensics(self,name):
        gaps=[]
        def attempt(label,fn):
            try: return fn()
            except Exception as e:
                gaps.append(label)
                self.save(dict(event='backend-capture-gap',run_id=self.run,backend=name,operation=label,
                    error_type=type(e).__name__,stdout=getattr(e,'stdout',None),stderr=getattr(e,'stderr',None)))
        pods=self.obj('-n',s.NS,'get','pods')
        self.save(dict(event='backend-raw-pods',run_id=self.run,backend=name,pods=pods))
        relevant=[];seen=set()
        candidates=list(pods['items'])
        candidates.extend(e['pod'] for e in s.life.native_cron_events(self.state)
            if e.get('run_id')==self.run and e.get('event')=='backend-observed-pod' and e.get('backend')==name)
        for pod in candidates:
            meta=pod.get('metadata',{});owners=meta.get('ownerReferences',[])
            app=meta.get('labels',{}).get('app.kubernetes.io/name')
            owned=False
            for owner in owners:
                if owner.get('kind')!='ReplicaSet': continue
                rs=attempt('discover-owner',lambda:self.obj('-n',s.NS,'get','replicaset',owner['name']))
                if rs is not None:
                    owned=owned or any(p.get('kind')=='Deployment' and p.get('name')==name
                        for p in rs.get('metadata',{}).get('ownerReferences',[]))
            if (app==name or owned) and meta.get('uid') not in seen:
                seen.add(meta.get('uid'));relevant.append(pod)
        if len(relevant)!=1: gaps.append('backend-cardinality')
        for pod in relevant:
            self.save(dict(event='backend-capture-pod',run_id=self.run,backend=name,pod=pod))
            if attempt('identity',lambda:self.backend_identity(pod)) is None: continue
            meta=pod['metadata'];containers=pod.get('spec',{}).get('containers',[])
            statuses=pod.get('status',{}).get('containerStatuses',[])
            attempt('envelope',lambda:self.envelope(pod['spec'],self.approved(name)['spec']['template']['spec'],actual_pod=True))
            all_containers=containers+pod.get('spec',{}).get('initContainers',[])
            all_statuses=statuses+pod.get('status',{}).get('initContainerStatuses',[])
            if (len(containers)!=1 or len(statuses)!=1
                or {c.get('name') for c in all_containers}!={c.get('name') for c in all_statuses}):
                gaps.append('container-status')
            for declared in all_containers:
                container=declared.get('name')
                if not isinstance(container,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*',container):
                    gaps.append('container-name');continue
                found=[c for c in all_statuses if c.get('name')==container]
                status=found[0] if len(found)==1 else {}
                if (not status.get('containerID') or type(status.get('restartCount')) is not int):
                    gaps.append('container-status')
                if (meta.get('deletionTimestamp') is not None or pod.get('status',{}).get('phase')!='Running'
                    or status.get('ready') is not True or set(status.get('state',{}))!={'running'}
                    or status.get('restartCount')!=0 or status.get('lastState',{})!={}):
                    gaps.append('backend-lifetime-state')
                for previous in (False,True):
                    if previous and not (status.get('restartCount') or status.get('lastState')): continue
                    def logs(previous=previous,container=container):
                        self.backend_identity(pod)
                        raw=self.call('-n',s.NS,'logs',meta['name'],'-c',container,*(['--previous'] if previous else []),'--request-timeout=5s')
                        self.save(dict(event='backend-private-log',run_id=self.run,backend=name,pod_uid=meta['uid'],container=container,previous=previous,log=raw))
                        self.backend_identity(pod)
                    attempt('previous-log' if previous else 'current-log',logs)
            c=statuses[0] if len(statuses)==1 else {}
            container=c.get('name')
            metrics={}
            if pod.get('status',{}).get('phase')=='Running' and set(c.get('state',{}))=={'running'}:
                self.backend_exec_binding=pod
                try:
                    for key in CGROUP_FILES:
                        def read(key=key):
                            raw=self.call('-n',s.NS,'exec',meta['name'],'-c',container,'--request-timeout=5s','--','/usr/bin/timeout','--kill-after=1s','2','/bin/cat','/sys/fs/cgroup/'+key)
                            metrics[key]=raw
                        attempt(key,read)
                finally: self.backend_exec_binding=None
            attempt('metrics',lambda:self.backend_metrics(metrics,name))
        refreshed=attempt('final-pod-snapshot',lambda:self.obj('-n',s.NS,'get','pods'))
        if refreshed is not None:
            self.save(dict(event='backend-final-pods',run_id=self.run,backend=name,pods=refreshed))
            if {p.get('metadata',{}).get('uid') for p in refreshed['items']}!={p.get('metadata',{}).get('uid') for p in pods['items']}:
                gaps.append('changed-pod-lifetimes')
        if gaps: raise RuntimeError('backend capture/acceptance gaps: '+','.join(gaps))

    def stop(self):
        # Diagnostic only: each guarded cleanup gets one independent attempt.
        if self.scope!='diagnose-preflight': raise RuntimeError('diagnostic stop only')
        self.authorize()
        failures=list(getattr(self,'cleanup_uncertainty',[]))
        def attempt(label,fn):
            try: fn()
            except Exception as e:
                failures.append(label)
                self.cleanup_uncertainty=list(failures)
                try:
                    self.save(dict(event='diagnostic-cleanup-failed',run_id=self.run,operation=label,
                        error_type=type(e).__name__,private_message=str(e)[:1024]))
                except Exception:
                    failures.append(label+'-journal')
                    self.cleanup_uncertainty=list(failures)
        attempt('stop-intent',lambda:self.save(dict(event='stop-intent',run_id=self.run)))
        attempt('stop-pods',lambda:self.save(dict(event='stop-pods',run_id=self.run,pods=self.obj('-n',s.NS,'get','pods'))))
        for name in ('postgres','redis'):
            attempt(name+'-capture',lambda name=name:self.backend_forensics(name))
        for name in ('postgres','redis'):
            def backend(name=name):
                r=self.target();uid=r['object_uids'].get('deployment/'+name)
                if not uid: raise RuntimeError('backend UID binding required')
                self.call('-n',s.NS,'patch','deployment',name,'--type=json','-p',json.dumps([
                    dict(op='test',path='/metadata/uid',value=uid),dict(op='replace',path='/spec/replicas',value=0)]))
            attempt(name,backend)
        def helper():
            records=[e for e in s.life.native_cron_events(self.state) if e.get('run_id')==self.run and e.get('event')=='phase-created']
            if not records: return
            name='nc-preflight-'+self.run
            if len(records)!=1 or records[0].get('name')!=name or not records[0].get('uid'):
                raise RuntimeError('single recorded diagnostic helper UID required')
            if name in getattr(self,'helper_cleanup_attempted',set()): return
            self.helper_cleanup_attempted={name}
            self.jobs[name]=records[0]['uid']
            evidence=self.forensics(name)
            if evidence[2]: raise RuntimeError('helper capture incomplete')
            self.diagnostic_capture_identity(evidence,name,records[0]['uid'])
            self.delete_own_job(name)
        attempt('helper-capture-retirement',helper)
        attempt('pod-absence',lambda:self.call('-n',s.NS,'wait','--for=delete','pod','--all','--timeout=180s'))
        attempt('stopped-controllers',self.require_stopped)
        attempt('global-absence',self.stopped_world)
        if failures:
            self.cleanup_uncertainty=list(failures)
            try: self.save(dict(event='stop-unconfirmed',run_id=self.run,failures=failures))
            except Exception: pass  # Existing pending stays; never report confirmation.
            raise RuntimeError('diagnostic cleanup unconfirmed: '+','.join(failures))

    def identities(self):
        super().identities()
        r=self.authorize()
        # Include every receipt-retained UID, not only the native backend/PVC
        # subset checked by the shared activation envelope.
        for key,uid in r['object_uids'].items():
            if not re.fullmatch(r'(deployment|cronjob|secret|pvc|pv|service|configmap)/[a-z0-9][a-z0-9.-]*',key):
                raise RuntimeError('unsupported retained identity binding')
            kind,name=key.split('/')
            obj=self.obj(*(() if kind=='pv' else ('-n',s.NS)),'get',kind,name)
            meta=obj.get('metadata',{})
            if (not isinstance(uid,str) or not uid or meta.get('uid')!=uid or meta.get('name')!=name
                or meta.get('namespace')!=(None if kind=='pv' else s.NS)):
                raise RuntimeError('retained UID/name/namespace drift')

    @staticmethod
    def stopped_items(pods,controllers):
        if any(p['metadata']['namespace'].startswith('proof-') for p in pods): raise RuntimeError('proof/helper Pod absence unconfirmed')
        for c in controllers:
            if not c['metadata']['namespace'].startswith('proof-'): continue
            if c['kind']=='CronJob':
                if c['spec'].get('suspend') is not True: raise RuntimeError('proof schedule not suspended')
            elif c['kind'] in ('Job','DaemonSet') or c['spec'].get('replicas',1)!=0:
                raise RuntimeError('proof controller/helper not stopped')

    def stopped_world(self):
        self.target()
        self.stopped_items(self.obj('get','pods','-A')['items'],
            self.obj('get','deployments,statefulsets,daemonsets,cronjobs,jobs','-A')['items'])

    def release_preflight(self):
        self.scope='release-preflight';r=self.consume()
        try:
            self.identities();self.network_policies();self.require_stopped();self.stopped_world()
            name='nextcloud-cron-payload-'+self.run;cm=self.obj('-n',s.NS,'get','configmap',name)
            if (cm.get('kind')!='ConfigMap' or cm['metadata'].get('namespace')!=s.NS or cm['metadata'].get('name')!=name
                or not r.get('payload_configmap_uid') or cm['metadata'].get('uid')!=r['payload_configmap_uid']
                or digest(cm.get('data',{}).get('native.php','').encode())!=r['origin_source_sha256']['scripts/talos-proof-nextcloud-cron.php']):
                raise RuntimeError('original retained payload UID/source mismatch')
            self.stopped_world()
            self.save(dict(event='preflight-release-observation',run_id=self.run,preflight_job_uid=r['preflight_job_uid'],
                historical_failure_gate='unknown',stopped=True,native_acceptance=False))
            self.save(dict(event='clean',run_id=self.run,scope='release-preflight'))
        except BaseException as e:
            self.save(dict(event='preflight-release-blocked',run_id=self.run,error_type=type(e).__name__,private_message=str(e)[:1024]))
            raise

    def documents(self,html=None):
        cm=copy.deepcopy(s.cron.compile_bundle(self.run)['payload']);cm['data'].pop('intent.json')
        job=s.cron.job('preflight',self.run)
        job['spec']['template']['spec']['containers'][0]['env'][0]['value']='diagnose-preflight'
        job['spec']['template']['spec']['containers'][0]['securityContext']['readOnlyRootFilesystem']=True
        # No implicit HTML alias: both live mappings are rechecked by identities.
        if html is None:
            html=json.loads(s.life.no_symlinks(os.environ['TALOS_PROOF_DATA_LEASE']).read_bytes())['html_claim']
        job['spec']['template']['spec']['volumes'][0]['persistentVolumeClaim']['claimName']=html
        return cm,job

    def document_hashes(self,html=None):
        cm,job=self.documents(html)
        return {d['kind'].lower()+'/'+d['metadata']['name']:digest(json.dumps(d,sort_keys=True,separators=(',',':')).encode()) for d in (cm,job)}

    def call(self,*args,data=None):
        mutations=s.life.MUTATIONS.intersection(args)
        verb=args[2] if len(args)>2 and args[:2]==('-n',s.NS) else (args[0] if args else '')
        if self.scope=='release-preflight':
            if mutations or verb!='get': raise RuntimeError('release is read-only; no app/helper command')
        else:
            if mutations-{'patch','create','delete','exec'}: raise RuntimeError('diagnostic forbids this mutation')
            if not mutations and verb not in ('get','logs','wait'):
                raise RuntimeError('diagnostic command not allowed')
            if 'exec' in args:
                bound=getattr(self,'backend_exec_binding',None)
                if (not bound or data is not None or args not in tuple(
                    ('-n',s.NS,'exec',bound['metadata']['name'],'-c',bound['spec']['containers'][0]['name'],
                     '--request-timeout=5s','--','/usr/bin/timeout','--kill-after=1s','2','/bin/cat','/sys/fs/cgroup/'+f) for f in CGROUP_FILES)):
                    raise RuntimeError('exact recorded backend cgroup command required')
                statuses=bound.get('status',{}).get('containerStatuses',[])
                if (bound.get('status',{}).get('phase')!='Running' or len(statuses)!=1
                    or statuses[0].get('name')!=bound['spec']['containers'][0]['name']
                    or not statuses[0].get('containerID') or set(statuses[0].get('state',{}))!={'running'}):
                    raise RuntimeError('recorded Running backend container required')
                self.backend_execution_envelope(bound)
                live=self.backend_identity(bound)
                self.backend_execution_envelope(live)
                result=super().call(*args,data=data)
                self.save(dict(event='backend-cgroup',run_id=self.run,pod_uid=bound['metadata']['uid'],
                    container=statuses[0]['name'],file=args[-1],raw=result))
                live=self.backend_identity(bound)
                self.backend_execution_envelope(live)
                return result
            if 'patch' in args:
                r=self.authorize();name=args[4] if len(args)>4 else ''
                if name not in ('postgres','redis') or args[:4]!=('-n',s.NS,'patch','deployment') or args[5:7]!=('--type=json','-p') or len(args)!=8:
                    raise RuntimeError('diagnostic backend patch only')
                expected=[dict(op='test',path='/metadata/uid',value=r['object_uids']['deployment/'+name]),dict(op='replace',path='/spec/replicas',value=0)]
                actual=json.loads(args[7]);expected[1]['value']=actual[1].get('value') if len(actual)==2 else None
                if actual!=expected or type(expected[1]['value']) is not int or expected[1]['value'] not in (0,1): raise RuntimeError('exact diagnostic UID patch required')
            if 'create' in args:
                self.authorize();cm,job=self.documents();d=json.loads(data)
                if args!=('create','-f','-','-o','json') or d not in (cm,job): raise RuntimeError('only exact diagnostic payload/readonly Job allowed')
                intent_event='diagnostic-payload-intent' if d['kind']=='ConfigMap' else 'phase-intent'
                intents=[e for e in s.life.native_cron_events(self.state) if e.get('run_id')==self.run and e.get('event')==intent_event]
                if len(intents)!=1 or intents[0].get('document' if d['kind']=='ConfigMap' else 'job')!=d:
                    raise RuntimeError('durable diagnostic create intent required')
                event='diagnostic-payload-created' if d['kind']=='ConfigMap' else 'phase-created'
                if any(e.get('run_id')==self.run and e.get('event')==event for e in s.life.native_cron_events(self.state)):
                    raise RuntimeError('single diagnostic create only')
            if 'delete' in args:
                path='/apis/batch/v1/namespaces/'+s.NS+'/jobs/nc-preflight-'+self.run
                uids=[e['uid'] for e in s.life.native_cron_events(self.state) if e.get('run_id')==self.run and e.get('event')=='phase-created' and e.get('name')=='nc-preflight-'+self.run]
                if args!=('delete','--raw',path,'-f','-') or len(uids)!=1 or json.loads(data).get('preconditions')!={'uid':uids[0]}:
                    raise RuntimeError('only recorded diagnostic helper UID retirement allowed')
        return super().call(*args,data=data)

    def diagnostic_capture_identity(self,evidence,name,uid):
        # Cleanup ownership only: drifted/failed Pods must still be capturable and
        # retireable under the recorded Job UID, never accepted as healthy evidence.
        for pod in evidence[0]['items']:
            meta=pod['metadata'];owners=meta.get('ownerReferences',[])
            if (meta.get('namespace')!=s.NS or len(owners)!=1
                or owners[0].get('kind')!='Job' or owners[0].get('name')!=name
                or owners[0].get('uid')!=uid):
                raise RuntimeError('diagnostic Pod owner/namespace mismatch')

    def diagnostic_helper(self,job):
        self.admission();name=job['metadata']['name']
        self.save(dict(event='phase-intent',run_id=self.run,phase='diagnose-preflight',job=job))
        created=json.loads(self.call('create','-f','-','-o','json',data=json.dumps(job)))
        self.active=name;self.jobs[name]=created['metadata']['uid']
        self.save(dict(event='phase-created',run_id=self.run,name=name,uid=self.jobs[name]))
        failure=None
        try:self.call('-n',s.NS,'wait','--for=condition=complete','job/'+name,'--timeout=190s')
        except Exception as e:failure=e
        self.helper_cleanup_attempted={name}
        try:
            evidence=self.forensics(name)
            if evidence[2]: raise RuntimeError('helper capture incomplete')
        except Exception:
            self.cleanup_uncertainty=['helper-capture']
            raise
        try:
            for pod in evidence[0]['items']:
                if (pod['metadata'].get('namespace')!=s.NS or not any(o.get('kind')=='Job' and o.get('name')==name
                    and o.get('uid')==self.jobs[name] for o in pod['metadata'].get('ownerReferences',[]))):
                    raise RuntimeError('diagnostic Pod owner/namespace mismatch')
                self.envelope(pod['spec'],job['spec']['template']['spec'],actual_pod=True)
            self.validate_forensics(evidence)
            pod=evidence[0]['items'][0];observation=json.loads(evidence[1][(pod['metadata']['name'],'cli')].splitlines()[-1])
            result=observation.get('result',{})
            if (observation.get('phase')!='diagnose-preflight' or result.get('empty') is not True
                or type(result.get('db_tables')) is not int or result['db_tables']!=0 or result.get('redis_authenticated') is not True):
                raise RuntimeError('explicit diagnostic empty-HTML/read-only backend result required')
        except Exception as e:failure=e
        try: self.delete_own_job(name)
        except Exception:
            self.cleanup_uncertainty=['helper-retirement']
            raise
        if failure:raise failure

    def diagnose_preflight(self):
        self.scope='diagnose-preflight'
        # Even a previously clean UUID is not a new diagnostic transaction.
        self.unused_run()
        if self.pending(): raise RuntimeError('pending cleanup blocks diagnosis')
        self.consume()
        self.save(dict(event='pending',run_id=self.run,scope='diagnose-preflight'))
        failure=None
        try:
            self.admission();self.require_stopped()
            self.scale_backends(1)
            self.backends_started=True
            self.call('-n',s.NS,'wait','--for=condition=available','deployment/postgres','deployment/redis','--timeout=180s')
            self.admission();cm,job=self.documents()
            self.save(dict(event='diagnostic-payload-intent',run_id=self.run,document=cm))
            obj=json.loads(self.call('create','-f','-','-o','json',data=json.dumps(cm)))
            self.save(dict(event='diagnostic-payload-created',run_id=self.run,name=cm['metadata']['name'],uid=obj['metadata']['uid']))
            self.diagnostic_helper(job)
        except BaseException as e:
            failure=e
            self.save(dict(event='diagnostic-failed',run_id=self.run,error_type=type(e).__name__,private_message=str(e)[:1024]))
        try:
            self.stop();self.require_stopped();self.stopped_world()
            self.save(dict(event='diagnostic-result',run_id=self.run,success=failure is None,stopped=True,native_acceptance=False))
            self.save(dict(event='clean',run_id=self.run,scope='diagnose-preflight'))
        except BaseException as e:
            self.save(dict(event='stop-unconfirmed',run_id=self.run,error_type=type(e).__name__,private_message=str(e)[:1024]))
            raise
        if failure: raise failure


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['release-preflight','diagnose-preflight','stop'])
    p.add_argument('--state',required=True);p.add_argument('--run-id',required=True)
    a=p.parse_args();i=Preflight(a.state,a.run_id)
    if a.action=='release-preflight':i.release_preflight()
    elif a.action=='diagnose-preflight':i.diagnose_preflight()
    else:
        i.scope='diagnose-preflight';i.stop()
    print('Preflight-only scope ended; private observations are not native acceptance.')


if __name__=='__main__':
    try:main()
    except Exception as e:
        print('Preflight scope BLOCKED_OR_FAILED: '+type(e).__name__)
        raise SystemExit(1)
