#!/usr/bin/env python3
"""Fail-closed media proof target, coordinator lease and private-file validation.

No kubectl mutation is exposed without rechecking exact target + identity + lease.
The coordinator owns the lease; this module never creates or refreshes one.
"""
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://127.0.0.1:64120'
HOSTNAME = 'talos-proof'
SERVICES = tuple(('radarr sonarr lidarr prowlarr qbittorrent qbitwebui sabnzbd plex '
                  'tautulli seerr kometa jellyfin jellyplex-watched audiobookshelf pinchflat recyclarr').split())
BUDGET = {name: (768 if name in ('plex', 'jellyfin', 'kometa', 'seerr') else 512) for name in SERVICES}
MUTATIONS = {'apply', 'scale', 'exec', 'rollout', 'delete', 'create', 'patch', 'label', 'annotate',
             'run', 'replace', 'cp', 'edit', 'set', 'attach', 'port-forward'}


def no_symlinks(value):
    expanded = Path(os.path.expanduser(str(value)))
    if '..' in expanded.parts:
        raise RuntimeError('private paths cannot contain parent traversal')
    path = Path(os.path.abspath(expanded))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError('private paths and ancestors cannot be symlinks')
    canonical = path.resolve()
    if canonical == ROOT or ROOT in canonical.parents:
        raise RuntimeError('private state must be outside checkout')
    return path


def private_dir(value, create=False):
    path = no_symlinks(value)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise RuntimeError('private directory must be owned by current user, mode 0700')
    return path


def private_file(value):
    path = no_symlinks(value)
    private_dir(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise RuntimeError('private file must be regular, owned by current user, mode 0600')
    return path


def read_private(value, binary=False):
    path = private_file(value)
    before = path.lstat()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb' if binary else 'r') as handle:
        current = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
            raise RuntimeError('private file changed while opening')
        return handle.read()


def write_private(value, payload, replace=False):
    path = no_symlinks(value)
    private_dir(path.parent)
    if path.exists():
        private_file(path)
        if not replace:
            raise RuntimeError('refuse to overwrite existing private state')
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_TRUNC if replace else os.O_EXCL)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'wb' if isinstance(payload, bytes) else 'w') as handle:
        handle.write(payload)
    return path


def kubectl_read(*args):
    """Local config/cluster reads only. No arbitrary verbs or plugin invocation."""
    if any(arg in MUTATIONS for arg in args):
        raise RuntimeError('mutation cannot use read-only kubectl path')
    if not args or args[0] not in ('config', 'get', 'wait'):
        raise RuntimeError('unsupported read-only kubectl operation')
    kubeconfig = os.environ.get('KUBECONFIG', '')
    if not kubeconfig or os.pathsep in kubeconfig:
        raise RuntimeError('one explicit private KUBECONFIG is required')
    private_file(kubeconfig)
    result = subprocess.run(['kubectl', '--kubeconfig', kubeconfig, *args], capture_output=True, timeout=360)
    if result.returncode:
        raise RuntimeError('proof kubectl read failed (details withheld)')
    return result.stdout.decode()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def lease(group):
    if group not in SERVICES:
        raise RuntimeError('unknown media lease group')
    receipt = json.loads(read_private(os.environ.get('TALOS_PROOF_MEDIA_LEASE', '/nonexistent')))
    now = time.time()
    if receipt.get('group') != group or not number(receipt.get('expires')) or receipt['expires'] <= now:
        raise RuntimeError('coordinator lease group mismatch or expiry')
    if receipt.get('endpoint') != ENDPOINT or not isinstance(receipt.get('node_uid'), str) or not receipt['node_uid'] or not isinstance(receipt.get('context'), str) or not receipt['context']:
        raise RuntimeError('lease does not record exact proof endpoint and node UID')
    config = json.loads(kubectl_read('config', 'view', '--minify', '-o', 'json'))
    clusters = config.get('clusters', [])
    if len(clusters) != 1 or config.get('current-context') != receipt.get('context'):
        raise RuntimeError('coordinator lease does not match active kubeconfig context')
    cluster = clusters[0].get('cluster', {})
    if cluster.get('server') != ENDPOINT or cluster.get('insecure-skip-tls-verify'):
        raise RuntimeError('exact proof loopback endpoint with TLS verification required')
    if not (cluster.get('certificate-authority-data') or cluster.get('certificate-authority')):
        raise RuntimeError('explicit proof API CA trust required')
    if cluster.get('certificate-authority'):
        private_file(cluster['certificate-authority'])
    # Reject exec/auth-provider hooks: identity inspection must not run arbitrary kubeconfig code.
    for user in config.get('users', []):
        if 'exec' in user.get('user', {}) or 'auth-provider' in user.get('user', {}):
            raise RuntimeError('proof kubeconfig cannot contain credential plugins')
        for key in ('client-certificate', 'client-key'):
            if user.get('user', {}).get(key):
                private_file(user['user'][key])
    nodes = json.loads(kubectl_read('get', 'nodes', '-o', 'json')).get('items', [])
    if len(nodes) != 1:
        raise RuntimeError('exactly one dedicated proof node required')
    meta = nodes[0].get('metadata', {})
    if meta.get('name') != HOSTNAME or meta.get('labels', {}).get('kubernetes.io/hostname') != HOSTNAME or meta.get('uid') != receipt['node_uid']:
        raise RuntimeError('proof node name, hostname or recorded UID mismatch')
    return receipt, nodes[0]


def exclusivity(group):
    """Reject data/media/unknown proof groups, including pending pods and active controllers."""
    allowed = {'proof-' + group, 'proof-validation', 'proof-gateway'}
    pods = json.loads(kubectl_read('get', 'pods', '-A', '-o', 'json'))['items']
    for pod in pods:
        ns = pod['metadata']['namespace']
        if ns.startswith('proof-') and ns not in allowed and pod.get('status', {}).get('phase') not in ('Succeeded', 'Failed'):
            raise RuntimeError('another proof group has live or pending pods')
    controllers = json.loads(kubectl_read('get', 'deployments,statefulsets', '-A', '-o', 'json'))['items']
    for controller in controllers:
        ns = controller['metadata']['namespace']
        if ns.startswith('proof-') and ns not in allowed and controller['spec'].get('replicas', 1):
            raise RuntimeError('another proof group is activated, including controllers without pods')


def guard(group, extra_mib=0):
    receipt, node = lease(group)
    exclusivity(group)
    alloc = node['status']['allocatable']['memory']
    if not alloc.endswith('Ki'):
        raise RuntimeError('unsupported node memory units')
    available = receipt.get('available_mib')
    age = time.time() - receipt.get('measured_at', 0)
    if not number(available) or not 0 <= age <= 120 or not 0 < available <= int(alloc[:-2]) / 1024:
        raise RuntimeError('fresh valid guest available-memory receipt required')
    if available < BUDGET[group] + extra_mib + 192:
        raise RuntimeError('insufficient measured guest headroom for bounded service plus reserve')
    return receipt


def kube(group, *args, data=None, capacity=False, extra_mib=0):
    """Every operation revalidates identity; every mutation also checks cross-group exclusivity."""
    lease(group)
    if any(arg in MUTATIONS for arg in args):
        exclusivity(group)
        if capacity:
            guard(group, extra_mib)
    kubeconfig = private_file(os.environ['KUBECONFIG'])
    result = subprocess.run(['kubectl', '--kubeconfig', str(kubeconfig), *args], input=data,
                            capture_output=True, timeout=960)
    if result.returncode:
        raise RuntimeError('proof kubectl operation failed (details withheld)')
    return result.stdout
