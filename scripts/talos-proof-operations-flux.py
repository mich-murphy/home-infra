#!/usr/bin/env python3
"""Render scoped Flux controllers, or run a private-receipt-gated fixture proof.
Requires PyYAML. Render is offline when supplied a checksum-verified cached release.
"""
import argparse
import hashlib
import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
import re
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[1]
NS = 'proof-operations-system'
FIXTURE = 'proof-operations-gitops'


def manifest(args):
    lock = json.loads((ROOT / 'kubernetes/operations/gitops/artifacts.lock.json').read_text())
    raw = Path(args.install_yaml).read_bytes() if args.install_yaml else urllib.request.urlopen(lock['url'], timeout=30).read()
    if hashlib.sha256(raw).hexdigest() != lock['sha256']:
        raise ValueError('upstream install.yaml checksum mismatch')
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        raise ValueError('revision must be an immutable 40-character Git commit SHA')
    docs = []
    for name, part in [(NS, 'talos-proof-operations'), (FIXTURE, 'talos-proof')]:
        docs.append({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': name, 'labels': {
            'app.kubernetes.io/part-of': part, 'pod-security.kubernetes.io/enforce': 'restricted'}}})
    for o in yaml.safe_load_all(raw):
        kind, name = o['kind'], o['metadata']['name']
        if kind == 'CustomResourceDefinition' and (name.endswith('.source.toolkit.fluxcd.io') or name.endswith('.kustomize.toolkit.fluxcd.io')):
            docs.append(o)
        elif (kind in ('Deployment', 'ServiceAccount') and name in lock['images']) or (kind == 'Service' and name == 'source-controller'):
            o['metadata']['namespace'] = NS
            if kind == 'Deployment':
                spec = o['spec']['template']['spec']
                spec.pop('priorityClassName', None)
                c = spec['containers'][0]
                c['image'] = lock['images'][name]
                c['resources'] = {'requests': {'cpu': '25m', 'memory': '64Mi'},
                                  'limits': {'cpu': '300m', 'memory': '192Mi'}}
                c['args'] = [a for a in c['args'] if not a.startswith(('--events-addr=', '--watch-all-namespaces'))]
                c['args'] += ['--watch-all-namespaces=false', '--concurrent=1']
                if name == 'kustomize-controller':
                    c['args'] += ['--no-cross-namespace-refs=true', '--no-remote-bases=true', '--default-service-account=fixture-reconciler']
            docs.append(o)
    def rb(kind, name, **extra):
        return {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': kind,
                'metadata': {'name': name, 'namespace': NS}, **extra}
    docs.append({'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': 'fixture-reconciler', 'namespace': NS}})
    rules = [
        {'apiGroups': ['source.toolkit.fluxcd.io', 'kustomize.toolkit.fluxcd.io'], 'resources': ['*'], 'verbs': ['*']},
        {'apiGroups': [''], 'resources': ['secrets', 'configmaps', 'serviceaccounts'], 'verbs': ['get', 'list', 'watch']},
        {'apiGroups': [''], 'resources': ['events'], 'verbs': ['create', 'patch']},
        {'apiGroups': ['coordination.k8s.io'], 'resources': ['leases'], 'verbs': ['get', 'list', 'watch', 'create', 'update', 'patch', 'delete']},
        {'apiGroups': [''], 'resources': ['serviceaccounts'], 'resourceNames': ['fixture-reconciler'], 'verbs': ['impersonate']},
    ]
    docs += [rb('Role', 'flux-control', rules=rules), rb('RoleBinding', 'flux-control',
             roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': 'flux-control'},
             subjects=[{'kind': 'ServiceAccount', 'name': n, 'namespace': NS} for n in lock['images']])]
    role = rb('Role', 'fixture-only', rules=[{'apiGroups': [''], 'resources': ['configmaps'], 'verbs': ['get', 'list', 'watch', 'create', 'patch', 'update', 'delete']}])
    role['metadata']['namespace'] = FIXTURE
    binding = rb('RoleBinding', 'fixture-only', roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': 'fixture-only'}, subjects=[{'kind': 'ServiceAccount', 'name': 'fixture-reconciler', 'namespace': NS}])
    binding['metadata']['namespace'] = FIXTURE
    docs += [role, binding]
    docs += [
        {'apiVersion': 'source.toolkit.fluxcd.io/v1', 'kind': 'GitRepository', 'metadata': {'name': 'proof-fixture', 'namespace': NS}, 'spec': {
            'interval': '1m', 'timeout': '30s', 'url': 'https://github.com/mich-murphy/home-infra', 'ref': {'commit': args.revision}}},
        {'apiVersion': 'kustomize.toolkit.fluxcd.io/v1', 'kind': 'Kustomization', 'metadata': {'name': 'proof-fixture', 'namespace': NS}, 'spec': {
            'interval': '30s', 'retryInterval': '15s', 'timeout': '30s', 'prune': True, 'serviceAccountName': 'fixture-reconciler',
            'sourceRef': {'kind': 'GitRepository', 'name': 'proof-fixture'},
            'path': './kubernetes/operations/gitops/fixture-v1', 'targetNamespace': FIXTURE}},
        {'apiVersion': 'cilium.io/v2', 'kind': 'CiliumNetworkPolicy', 'metadata': {'name': 'scoped-controllers', 'namespace': NS}, 'spec': {
            'endpointSelector': {}, 'ingress': [{'fromEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS}}]}], 'egress': [
                {'toEntities': ['kube-apiserver'], 'toPorts': [{'ports': [{'port': '6443', 'protocol': 'TCP'}, {'port': '443', 'protocol': 'TCP'}]}]},
                {'toEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': 'kube-system', 'k8s:k8s-app': 'kube-dns'}}], 'toPorts': [{'ports': [{'port': '53', 'protocol': 'UDP'}, {'port': '53', 'protocol': 'TCP'}], 'rules': {'dns': [{'matchPattern': '*'}]}}]},
                {'toEndpoints': [{'matchLabels': {'k8s:io.kubernetes.pod.namespace': NS}}]},
            ]}},
        {'apiVersion': 'cilium.io/v2', 'kind': 'CiliumNetworkPolicy', 'metadata': {'name': 'source-github-only', 'namespace': NS}, 'spec': {
            'endpointSelector': {'matchLabels': {'app': 'source-controller'}}, 'egress': [
                {'toFQDNs': [{'matchName': 'github.com'}], 'toPorts': [{'ports': [{'port': '443', 'protocol': 'TCP'}]}]}]}},
    ]
    return docs


def operations():
    spec = importlib.util.spec_from_file_location('operations_guard', ROOT / 'scripts/talos-proof-operations.py')
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    ops.GROUP = 'operations-flux'
    return ops


def cleanup(ops):
    # No CRD, namespace, PVC, or unrelated workload removal.
    try:
        ops.kube('-n', NS, 'patch', 'kustomization', 'proof-fixture', '--type=merge',
                 '-p', '{"spec":{"suspend":true}}', stdout=subprocess.DEVNULL)
    finally:
        ops.kube('-n', NS, 'delete', 'deployment', 'source-controller', 'kustomize-controller',
                 '--ignore-not-found=true', '--wait=true', stdout=subprocess.DEVNULL)


def live(args):
    ops = operations()
    ops.gate()
    if args.action == 'cleanup':
        cleanup(ops)
        return
    out = ops.private_dir()
    # Baseline from real kubelet stats, not declared limits or host free memory.
    node = ops.gate()
    summary = ops.obj('get', '--raw', '/api/v1/nodes/talos-proof/proxy/stats/summary')
    available = summary['node'].get('memory', {}).get('availableBytes', 0)
    if available < (384 + 512) * 1024**2:
        raise RuntimeError('Flux needs 384Mi controller ceilings plus 512Mi measured reserve')
    active = ops.obj('get', 'pods', '-A', '-l', 'app.kubernetes.io/part-of=talos-proof', '-o', 'json')['items']
    if any(p['metadata']['namespace'] not in ('proof-validation', 'proof-gateway')
           and p.get('status', {}).get('phase') not in ('Succeeded', 'Failed') for p in active):
        raise RuntimeError('another app batch is active')
    docs = manifest(args)
    transitions = []
    def value(expected):
        ops.kube('-n', FIXTURE, 'wait', '--for=jsonpath={.data.revision}=' + str(expected),
                 'configmap/reconciliation-fixture', '--timeout=120s', stdout=subprocess.DEVNULL)
        cm = ops.obj('-n', FIXTURE, 'get', 'configmap', 'reconciliation-fixture', '-o', 'json')
        transitions.append({'expected': str(expected), 'observed': cm['data']['revision']})
    def path(version):
        ops.kube('-n', NS, 'patch', 'kustomization', 'proof-fixture', '--type=merge', '-p',
                 json.dumps({'spec': {'path': './kubernetes/operations/gitops/fixture-v' + str(version)}}),
                 stdout=subprocess.DEVNULL)
        value(version)
    try:
        ops.kube('apply', '--server-side', '-f', '-', input=yaml.safe_dump_all(docs).encode(), stdout=subprocess.DEVNULL)
        for controller in ('source-controller', 'kustomize-controller'):
            ops.kube('-n', NS, 'rollout', 'status', 'deployment/' + controller, '--timeout=180s', stdout=subprocess.DEVNULL)
        for resource in ('gitrepository', 'kustomization'):
            ops.kube('-n', NS, 'wait', '--for=condition=Ready', resource + '/proof-fixture', '--timeout=180s', stdout=subprocess.DEVNULL)
        value(1)
        ops.kube('-n', FIXTURE, 'patch', 'configmap', 'reconciliation-fixture', '--type=merge',
                 '-p', '{"data":{"revision":"drift"}}', stdout=subprocess.DEVNULL)
        value(1)
        path(2)
        path(1)
        negatives = {}
        for verb, resource in [('create', 'deployments'), ('get', 'secrets')]:
            # can-i returns 1 on expected denial; avoid treating that as a command error.
            ops.gate()
            config = ops.private_file(os.environ['KUBECONFIG'])
            receipt = json.loads(ops.private_file(os.environ['TALOS_PROOF_OPERATIONS_LEASE']).read_text())
            result = subprocess.run(['kubectl', '--kubeconfig', str(config),
                '--context', receipt['context'], '--server', ops.ENDPOINT, '--request-timeout=30s',
                'auth', 'can-i', verb, resource, '-n', FIXTURE,
                '--as=system:serviceaccount:' + NS + ':fixture-reconciler'],
                capture_output=True, timeout=40)
            if result.returncode != 1 or result.stdout.strip() != b'no':
                raise RuntimeError('fixture privilege denial not proven')
            negatives[verb + ' ' + resource] = 'no'
        git = ops.obj('-n', NS, 'get', 'gitrepository', 'proof-fixture', '-o', 'json')
        ks = ops.obj('-n', NS, 'get', 'kustomization', 'proof-fixture', '-o', 'json')
        (out / 'flux.json').write_text(json.dumps({'commit': args.revision, 'transitions': transitions,
            'source_revision': git.get('status', {}).get('artifact', {}).get('revision'),
            'applied_revision': ks.get('status', {}).get('lastAppliedRevision'),
            'negative_rbac': negatives, 'rollback': 'fixture path v2 to v1, same immutable commit'}, indent=2) + '\n')
        print('Private Flux evidence: ' + str(out))
    finally:
        # May fail closed on lease expiry. Parent must refresh lease for explicit cleanup.
        cleanup(ops)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=['render', 'run', 'cleanup'], default='render')
    p.add_argument('--revision')
    p.add_argument('--install-yaml', help='optional local cached upstream manifest, checksum verified')
    args = p.parse_args()
    if args.action != 'cleanup' and not args.revision:
        p.error('--revision required for render/run')
    os.umask(0o077)
    if args.action == 'render':
        print(yaml.safe_dump_all(manifest(args), sort_keys=False), end='')
    else:
        live(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Flux proof stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
