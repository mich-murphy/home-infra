#!/usr/bin/env python3
"""Render (never apply) two scoped Flux controllers from a verified upstream release.
Requires PyYAML. Generated output is kept outside Git by the operator.
"""
import argparse
import hashlib
import json
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision', required=True)
    p.add_argument('--install-yaml', help='optional local cached upstream manifest, checksum verified')
    args = p.parse_args()
    print(yaml.safe_dump_all(manifest(args), sort_keys=False), end='')


if __name__ == '__main__':
    main()
