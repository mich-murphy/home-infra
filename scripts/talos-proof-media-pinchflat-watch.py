"""Pinchflat first-known-OOM stop; native cgroup reads, no fixture Python.

Workstation-only monitor; no lease creation, no retries or app log reads.
"""
from contextlib import contextmanager
import importlib
import json
import threading
import uuid

s = importlib.import_module('talos-proof-media-safety')
o = importlib.import_module('talos-proof-media-observe')
ACTIVE = None


def events(payload):
    """Strict current-lifetime cgroup-v2 events, including child-only OOMs."""
    sections = {}
    key = None
    for line in payload.splitlines():
        if line.startswith('FILE '):
            key = line[5:]
            if key in sections:
                raise RuntimeError('duplicate cgroup counter section')
            sections[key] = []
        elif key and o.valid_line(line) and line != 'UNAVAILABLE':
            sections[key].append(line)
        else:
            raise RuntimeError('missing/unreadable/invalid cgroup counters; STOP')
    if set(sections) != {'memory.current','memory.peak','memory.stat','memory.events'}:
        raise RuntimeError('incomplete cgroup counter sample; STOP')
    for name in ('memory.current','memory.peak'):
        if len(sections[name]) != 1 or not sections[name][0].isdigit():
            raise RuntimeError('invalid native cgroup memory scalar; STOP')
    if not sections['memory.stat']:
        raise RuntimeError('missing native memory.stat; STOP')
    result = {}
    for line in sections['memory.events']:
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit() or parts[0] in result:
            raise RuntimeError('invalid memory.events sample; STOP')
        result[parts[0]] = int(parts[1])
    if not {'oom','oom_kill'} <= result.keys():
        raise RuntimeError('missing OOM counters; STOP')
    return result


def latch(state, error_type):
    s.write_private(state / ('pinchflat-oom-stop-'+uuid.uuid4().hex+'.json'),json.dumps({'result':'STOP','reason':'OOM/restart/control/counter failure; parent review required','error_type':error_type}))


def require_not_stopped(state):
    if list(state.glob('pinchflat-oom-stop-*.json')):
        raise RuntimeError('retained Pinchflat STOP receipt requires parent review; no rerun')


def sample(state, pods=None, require_running=False):
    require_not_stopped(state)
    if pods is None:
        pods = json.loads(s.kube('pinchflat','-n','proof-pinchflat','get','pods','-o','json'))['items']
    record = {'pods': [], 'result':'SAMPLED'}
    failure = None
    try:
        s.resources.pinchflat_no_restart(pods)
        running = 0
        for pod in pods:
            entry = {'uid':pod['metadata']['uid'],'name':pod['metadata']['name'],'pod_status':o.summarize(pod),'containers':[]}
            record['pods'].append(entry)
            statuses = pod.get('status',{}).get('containerStatuses',[]) + pod.get('status',{}).get('initContainerStatuses',[])
            for status in statuses:
                if 'running' not in status.get('state',{}):
                    continue
                raw = s.kube('pinchflat','-n','proof-pinchflat','exec',pod['metadata']['name'],'-c',status['name'],'--','/bin/sh','-c',o.CGROUP).decode()
                parsed = events(raw)
                entry['containers'].append({'name':status['name'],'container_id':status.get('containerID'),'cgroup':raw,'events':parsed})
                running += 1
                if any(parsed.get(key,0)>0 for key in ('oom','oom_kill','oom_group_kill')):
                    raise RuntimeError('Pinchflat cgroup OOM event, including child-only OOM: STOP, no retry')
            if require_running:
                expected = {c['name'] for c in pod['spec']['containers']}
                if {c['name'] for c in entry['containers']} != expected:
                    raise RuntimeError('all app/fixture containers must be running for OOM preflight')
        if require_running and (len(pods)!=1 or not running):
            raise RuntimeError('exactly one running Pinchflat Pod required for OOM preflight')
    except Exception as exc:
        failure = exc
        record['result'] = 'STOP'
        record['error_type'] = type(exc).__name__
    finally:
        s.write_private(state / ('pinchflat-oom-check-'+uuid.uuid4().hex+'.json'),json.dumps(record))
    if failure:
        latch(state,type(failure).__name__)
        raise failure
    return record


def stop(state):
    """Stop first; positive counters were already retained by sample()."""
    s.kube('pinchflat','-n','proof-pinchflat','scale','deployment','pinchflat','--replicas=0')
    try:
        o.capture('pinchflat',state)  # Best effort while terminating, never delays scale0.
    finally:
        s.kube('pinchflat','-n','proof-pinchflat','wait','--for=delete','pod','--all','--timeout=180s')


class Monitor:
    def __init__(self,state,require_running=True):
        self.state=state
        self.require_running=require_running
        self.done=threading.Event()
        self.lock=threading.Lock()
        self.failure=None
        self.thread=threading.Thread(target=self.run,daemon=True)
    def checkpoint(self):
        with self.lock:
            if self.failure:
                raise RuntimeError('Pinchflat OOM monitor latched STOP; no further control command authorized') from self.failure
            try:
                return sample(self.state,require_running=self.require_running)
            except Exception as exc:
                self.failure=exc
                raise
    def run(self):
        while not self.done.wait(1):
            try:
                self.checkpoint()
            except Exception as exc:
                self.failure=exc
                self.done.set()
                try:
                    stop(self.state)  # Interrupt long native exec by stopping its Pod.
                except Exception:
                    pass  # Main thread still sees latched failure; parent owns failed cleanup.
                return


@contextmanager
def monitoring(state,require_running=True):
    global ACTIVE
    if ACTIVE is not None:
        raise RuntimeError('nested Pinchflat monitor forbidden')
    monitor=Monitor(state,require_running=require_running)
    ACTIVE=monitor
    try:
        monitor.checkpoint()
        monitor.thread.start()
        yield monitor
        monitor.checkpoint()
    finally:
        monitor.done.set()
        if monitor.thread.ident is not None:
            monitor.thread.join(timeout=15)
        ACTIVE=None
        if monitor.thread.is_alive():
            raise RuntimeError('Pinchflat monitor did not stop; parent cleanup required')


def fail_control(exc):
    if ACTIVE is None:
        raise RuntimeError('native control failed without OOM monitoring')
    with ACTIVE.lock:
        ACTIVE.failure=exc
        latch(ACTIVE.state,type(exc).__name__)


def checkpoint():
    if ACTIVE is None:
        raise RuntimeError('native Pinchflat control requires active OOM monitoring')
    return ACTIVE.checkpoint()


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',required=True,type=Path)
    parser.add_argument('--seconds',type=int,default=900)
    args=parser.parse_args()
    if not 1 <= args.seconds <= 900:
        parser.error('seconds must be 1..900')
    state=s.private_dir(args.state)
    try:
        # Can be started under the new grant BEFORE its single activation. This
        # covers startup→exercise gaps; absence is allowed only in this outer
        # window watcher, never for native control-command preflights.
        with monitoring(state,require_running=False) as monitor:
            if monitor.done.wait(args.seconds):
                raise RuntimeError('Pinchflat monitor stopped early')
    except Exception:
        raise SystemExit('Pinchflat monitoring STOP; private evidence retained; parent cleanup/review required')
    finally:
        # A bounded watcher may not silently leave an unmonitored application.
        try: stop(state)
        except Exception:
            raise SystemExit('Pinchflat monitoring cleanup failed; parent action required')
