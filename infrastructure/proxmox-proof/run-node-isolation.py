#!/usr/bin/env python3
"""Mac orchestrator. IMPLEMENTATION ONLY until separate parent execution grant.

No deployment action. Starts only the new bounded collector unit after validating
an idle proof cluster. Never scales/stops workloads or changes network policy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time

UUID = '555e8603-58e6-4fb6-a190-378a3f11c257'
NODE_UID = '4845bfd5-3bdb-453d-8503-83b43edb7a1e'
HOST = 'root@proxmox'
STATE = '/root/.local/state/home-infra/talos-proof'
COLLECTOR = STATE + '/collect-isolation.py'
# One constructor invocation, no DNS, proxy, HTTP redirect, registry or retry.
# Return 2 only on connect failure; the host counter must independently correlate.
PERL_DEADLINE = '$SIG{ALRM}=sub{print STDERR "proof-node-alarm-expired\\n";exit 124}; alarm 3; '
PERL = (PERL_DEADLINE + '$s=IO::Socket::INET->new(PeerAddr=>$ARGV[0],PeerPort=>$ARGV[1],'
        'Proto=>"tcp",Timeout=>1) or exit 2; '
        'print $s $ARGV[2]; $s->recv($r,128); alarm 0; exit 0;')


PHASE = 'preflight'


def private_failure(error, directory=None):
    directory = directory or Path.home() / '.local/state/home-infra/talos-proof'
    path = directory / 'node-isolation-last-error.json'
    temp = directory / ('node-isolation-error.tmp-' + str(os.getpid()))
    value = {'phase': PHASE, 'reason': 'node_isolation_' + PHASE + '_failed',
             'error_type': type(error).__name__, 'monotonic': time.monotonic(),
             'detail': str(error) if isinstance(error, RuntimeError) else type(error).__name__}
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(argv, timeout=5, codes=(0,)):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    require(result.returncode in codes and len(result.stdout) <= 2_000_000, 'bounded command failed')
    return result


def run_node(argv, directory=None):
    """Retain private exit/stderr even for loader failure before phaseDone.

    Never persist argv/stdout (which could include synthetic tokens/configs).
    Unique files preserve each failed attempt rather than overwriting history.
    """
    directory = directory or Path.home() / '.local/state/home-infra/talos-proof'
    failure = None
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        value = {'returncode': result.returncode, 'transport_timeout': False, 'stderr': result.stderr[:8192]}
    except subprocess.TimeoutExpired as exc:
        failure = exc
        stderr = exc.stderr or ''
        if isinstance(stderr, bytes):
            stderr = stderr.decode('utf-8', errors='replace')
        value = {'returncode': None, 'transport_timeout': True, 'stderr': stderr[:8192]}
    value['phase'] = 'node_attempt'
    path = directory / ('node-isolation-command-' + str(time.monotonic_ns()) + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    require(failure is None, 'node exec transport deadline exceeded; private stderr retained')
    return result


def ssh(argv):
    return run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3', HOST,
                shlex.join(argv)])


def kube(kubeconfig, *args):
    return ['kubectl', '--kubeconfig', str(kubeconfig), '--server=https://127.0.0.1:64120',
            '--request-timeout=3s', *args]


def validate_cluster(kubeconfig):
    nodes = json.loads(run(kube(kubeconfig, 'get', 'nodes', '-o', 'json')).stdout)['items']
    require(len(nodes) == 1 and nodes[0]['metadata']['uid'] == NODE_UID, 'wrong node UID')
    node = nodes[0]['metadata']['name']
    require(any(c['type'] == 'Ready' and c['status'] == 'True'
                for c in nodes[0]['status']['conditions']), 'node not ready')
    pods = json.loads(run(kube(kubeconfig, 'get', 'pods', '-A', '-o', 'json')).stdout)['items']
    # Conservative superset of app namespaces, including validation fixtures.
    # Infrastructure operations namespace is not excluded: any proof-* pod blocks.
    require(not any(p['metadata']['namespace'].startswith('proof-') and
                    p.get('status', {}).get('phase') not in ('Succeeded', 'Failed') for p in pods),
            'proof app/fixture pods must all be absent or terminal')
    controllers = json.loads(run(kube(kubeconfig, 'get', 'deployments,statefulsets,daemonsets,jobs,cronjobs',
                                      '-A', '-o', 'json')).stdout)['items']
    for controller in controllers:
        if not controller['metadata']['namespace'].startswith('proof-'):
            continue
        spec, kind = controller.get('spec', {}), controller['kind']
        if kind in ('Deployment', 'StatefulSet'):
            require(spec.get('replicas', 1) == 0, 'app controller can create pods')
        elif kind == 'CronJob':
            require(spec.get('suspend') is True, 'app cronjob not suspended')
        elif kind == 'Job':
            require(controller.get('status', {}).get('active', 0) == 0 and
                    (spec.get('suspend') is True or any(c.get('status') == 'True' and
                     c.get('type') in ('Complete', 'Failed') for c in controller.get('status', {}).get('conditions', []))),
                    'app job can create pods')
        else:
            require(False, 'app daemonset present')
    cilium = [p for p in pods if p['metadata']['namespace'] == 'kube-system' and
              p['metadata'].get('labels', {}).get('k8s-app') == 'cilium' and
              p['spec'].get('hostNetwork') is True and p['spec'].get('nodeName') == node and
              p.get('status', {}).get('phase') == 'Running' and
              any(x.get('name') == 'cilium-agent' and x.get('ready') is True
                  for x in p.get('status', {}).get('containerStatuses', []))]
    require(len(cilium) == 1, 'no unique ready host-network Cilium tool')
    return cilium[0]['metadata']['name'], cilium[0]['metadata']['uid']


def node_command(kubeconfig, pod, port, token):
    # Limit the interpreter before exec. Perl alarm bounds both connect/receive;
    # its exit124 is NEVER the connect-failure exit2. Exactly one constructor.
    script = 'ulimit -v 12288 && ulimit -t 1 && ulimit -n 16 && exec perl -MIO::Socket::INET -e "$1" -- "$2" "$3" "$4"'
    return kube(kubeconfig, '-n', 'kube-system', 'exec', pod, '-c', 'cilium-agent', '--',
                'bash', '-c', script, 'proof-isolation', PERL, '10.77.1.100', str(port), token)


def launch_command(run_id, port):
    control = 10000 + (int(run_id[:8], 16) % 3000) * 3
    args = ['--approve', UUID, '--mode', 'node', '--address', '10.77.1.100', '--protocol', 'TCP',
            '--port', str(port), '--control-before', str(control),
            '--control-after', str(control + 1), '--run-id', run_id]
    output = STATE + '/isolation-' + run_id + '.json'
    stop = shlex.join(['/usr/bin/python3', '-B', COLLECTOR, '--cleanup', *args])
    return ['systemd-run', '--unit=talos-proof-isolation-' + run_id + '.service', '--service-type=exec',
            '--property=RuntimeMaxSec=40', '--property=TimeoutStopSec=10',
            '--property=MemoryMax=32M', '--property=CPUQuota=10%', '--property=TasksMax=8',
            '--property=LimitNOFILE=32', '--property=UMask=0077', '--property=ExecStopPost=' + stop,
            '/usr/bin/python3', '-B', COLLECTOR, *args, '--output', output]


def marker(work, name, value):
    require((name in ('claim', 'done') and value in ('one', 'denied', 'failed')) or
            (name == 'producer' and len(value) <= 4096), 'invalid marker')
    # noclobber is the at-most-one-attempt claim. No retry after an uncertain SSH
    # outcome. Marker files are under root0700 fresh run directory.
    unit = 'talos-proof-isolation-' + work.rsplit('isolation-', 1)[1] + '.service'
    check = 'systemctl is-active --quiet ' + shlex.quote(unit) + ' && '
    return ssh(['sh', '-c', check + '(umask 077; set -C; printf %s ' + shlex.quote(value) + ' > ' +
                shlex.quote(work + '/' + name) + ')'])


def phase(work):
    unit = 'talos-proof-isolation-' + work.rsplit('isolation-', 1)[1] + '.service'
    script = ('value=; if test -f ' + shlex.quote(work + '/phase') +
              '; then value=$(head -c 64 ' + shlex.quote(work + '/phase') + '); fi; '
              'if test "$value" != complete; then systemctl is-active --quiet ' + shlex.quote(unit) +
              ' || exit 1; fi; printf %s "$value"')
    value = ssh(['sh', '-c', script]).stdout.strip()
    require(value in ('', 'armed', 'complete'), 'unknown collector phase')
    return value


def execute(kubeconfig):
    global PHASE
    PHASE = 'cluster_validation'
    identity = validate_cluster(kubeconfig)
    run_id = secrets.token_hex(16)
    port = 25000 + secrets.randbelow(4000)
    work = STATE + '/isolation-' + run_id
    PHASE = 'collector_launch'
    ssh(launch_command(run_id, port))  # independent systemd unit, not SSH child
    print(json.dumps({'phase': 'collector-started'}), flush=True)
    deadline = time.monotonic() + 40
    attempted = False
    while time.monotonic() < deadline:
        PHASE = 'collector_wait'
        current = phase(work)
        if current == 'armed' and not attempted:
            PHASE = 'node_precheck'
            require(validate_cluster(kubeconfig) == identity, 'Cilium incarnation changed')
            command = node_command(kubeconfig, identity[0], port, run_id)
            marker(work, 'producer', json.dumps({'node_uid': NODE_UID, 'cilium_pod': identity[0],
                   'cilium_pod_uid': identity[1], 'all_proof_app_pods_zero': True, 'host_network': True,
                   'command_sha256': hashlib.sha256(shlex.join(command).encode()).hexdigest(),
                   'planning_envelope_mib': 96, 'root_unit_cap_mib': 32,
                   'guest_process_allowance_mib': 24, 'transport_allowance_mib': 40,
                   'initial_host_floor_mib': 1888, 'during_host_floor_mib': 1792}))
            marker(work, 'claim', 'one')  # never retry this command or the connect
            attempted = True
            PHASE = 'node_attempt'
            result = run_node(command)
            marker(work, 'done', 'denied' if result.returncode == 2 else 'failed')
            require(result.returncode == 2, 'node command did not report bounded connect denial')
            print(json.dumps({'phase': 'node-attempt-finished'}), flush=True)
        if current == 'complete':
            PHASE = 'completion_validation'
            require(attempted and validate_cluster(kubeconfig) == identity, 'post-attempt identity/app state changed')
            status = ssh(['systemctl', 'show', 'talos-proof-isolation-' + run_id + '.service',
                          '--property=ActiveState,Result,ExecMainStatus']).stdout
            fields = dict(line.split('=', 1) for line in status.splitlines() if '=' in line)
            require(fields.get('ActiveState') == 'inactive' and fields.get('Result') == 'success' and
                    fields.get('ExecMainStatus') == '0', 'collector/StopPost not successfully finished')
            # Receipt stays root-private. Emit only its hash, not configs/packets.
            digest = ssh(['sha256sum', STATE + '/isolation-' + run_id + '.json']).stdout.split()[0]
            require(len(digest) == 64 and all(x in '0123456789abcdef' for x in digest), 'invalid receipt hash')
            print(json.dumps({'phase': 'complete', 'status': 'capture-pending-human-review', 'sha256': digest}))
            return
        time.sleep(.5)
    raise RuntimeError('orchestrator deadline; independent unit cleanup remains responsible')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-live-window', required=True, choices=[UUID])
    parser.add_argument('--kubeconfig', type=Path, default=Path.home() / '.local/state/home-infra/talos-proof/config/kubeconfig')
    args = parser.parse_args()
    try:
        execute(args.kubeconfig)
        return 0
    except Exception as exc:
        recorded = False
        try:
            private_failure(exc)
            recorded = True
        except OSError:
            pass
        print(json.dumps({'status': 'failed-no-acceptance', 'reason': 'node_isolation_' + PHASE + '_failed',
                          'private_diagnostic_written': recorded}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
