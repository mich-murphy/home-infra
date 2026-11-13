#!/usr/bin/env python3
"""Stopped-group recovery planning and local archive primitives, no cluster CLI.

Selected-pair recovery != all-seven configured-service recovery. Shared data is
captured ONCE; independent config volumes separately. Secret objects, external
keys and image availability are NOT backed up by these volume archives.
Existing safety prohibits pipeline helper admission: owner wiring required.
"""
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import uuid

safety = importlib.import_module('talos-proof-media-safety')
SERVICES = frozenset('radarr sonarr lidarr prowlarr qbittorrent qbitwebui sabnzbd'.split())
NS = 'proof-media-pipeline'


def expect(ok, message):
    if not ok:
        raise RuntimeError(message)


def require_owner_wiring():
    raise RuntimeError('BLOCKED: existing safety forbids pipeline recovery helper; owner must authorize stopped helper128 + reserve192, not an app grant')


def stopped(deployments, pods):
    expect(not pods, 'ALL group pods must be deleted, including terminal/terminating/helpers')
    expect(all(d['spec'].get('replicas', 1) == 0 for d in deployments), 'ALL applications must be stopped')


def bindings(deployments):
    result = {}
    for d in deployments:
        name = d['metadata']['name']
        expect(d['metadata']['namespace'] == NS and name in SERVICES and name not in result, 'unknown/duplicate group deployment')
        result[name] = {v['name']: v['persistentVolumeClaim']['claimName']
                        for v in d['spec']['template']['spec'].get('volumes', []) if 'persistentVolumeClaim' in v}
    return result


def plan(deployments, pods, pvc_inventory, *, selected, scope, required_secrets):
    """Pure plan from owner-supplied complete namespace snapshots, no API calls.

    required_secrets is an explicit list of {name, keys}; only requirements are
    recorded, never a claim that credentials were captured. qbitwebui .salt is
    in its config archive; ENCRYPTION_KEY remains an external Secret requirement.
    """
    stopped(deployments, pods)
    original = bindings(deployments)
    expect(original.keys() == SERVICES, 'complete configured seven-service namespace inventory required, even for selected-pair recovery')
    selected = frozenset(selected)
    expect(scope in ('selected-pair', 'all-seven-configured'), 'explicit recovery scope required')
    expect(selected <= original.keys(), 'selected deployment absent')
    if scope == 'selected-pair':
        expect('+'.join(sorted(selected)) in ['+'.join(sorted(x.split('+'))) for x in safety.PIPELINE_PAIRS]
               and len(selected) == 2, 'unsupported selected pair')
    else:
        expect(selected == SERVICES and original.keys() == SERVICES, 'all-seven requires complete seven-service inventory')
    expect(bool(required_secrets) and all(x.get('name') and x.get('keys') and all(isinstance(k, str) and k for k in x['keys']) for x in required_secrets), 'explicit external Secret/key requirements missing')
    requirements = {x['name']: set(x['keys']) for x in required_secrets}
    expect(len(requirements) == len(required_secrets), 'duplicate Secret requirements')
    for app in selected:
        keys = {'password', 'encryption-key'} if app == 'qbitwebui' else {'seed'}
        expect(keys <= requirements.get(app + '-bootstrap', set()), 'selected bootstrap Secret/key requirements missing')
    # Also enumerate actual projected Secret keys from supplied selected PodSpecs.
    # A whole-Secret volume without items requires an explicit '*' requirement.
    for d in deployments:
        if d['metadata']['name'] not in selected:
            continue
        pod = d['spec']['template']['spec']
        for c in pod.get('containers', []) + pod.get('initContainers', []):
            for env in c.get('env', []):
                ref = env.get('valueFrom', {}).get('secretKeyRef')
                if ref:
                    expect(ref['key'] in requirements.get(ref['name'], set()), 'actual Secret env key requirement missing')
            expect(not c.get('envFrom'), 'envFrom Secret/config capture needs explicit owner review')
        for v in pod.get('volumes', []):
            if 'secret' in v:
                ref = v['secret']
                keys = {i['key'] for i in ref['items']} if ref.get('items') else {'*'}
                expect(keys <= requirements.get(ref['secretName'], set()), 'actual Secret volume requirements missing')
            expect('projected' not in v, 'projected volume requirements need explicit owner review')
    # Every configured deployment is retained in original mappings, even if only
    # two configs are captured: every shared alias must move together on restore.
    configs, shared_refs = {}, []
    for app, volumes in original.items():
        for volume, claim in volumes.items():
            if claim == 'data':
                shared_refs.append([app, volume])
            else:
                expect(claim == app + '-config', 'unexpected PVC mapping; review rather than guess')
                if app in selected:
                    configs.setdefault(claim, []).append([app, volume])
    expect(bool(shared_refs), 'shared data mapping absent')
    claims = {'data': shared_refs, **configs}
    expect(all(app + '-config' in configs for app in selected), 'independent config missing')
    inventory = {x['metadata']['name']: x for x in pvc_inventory}
    volumes = []
    for claim, aliases in claims.items():
        pvc = inventory[claim]
        expect(pvc['metadata']['namespace'] == NS and bool(pvc['metadata']['uid']), 'PVC identity missing')
        volumes.append(dict(source_claim=claim, source_uid=pvc['metadata']['uid'], aliases=aliases,
                            storage=pvc['spec']['resources']['requests']['storage']))
    if 'qbitwebui' in selected:
        expect(any(x['name'] == 'qbitwebui-bootstrap' and 'encryption-key' in x['keys'] for x in required_secrets), 'qbitwebui encryption-key requirement missing')
    return dict(schema=1, scope=scope, selected=sorted(selected), original=original, volumes=volumes,
                external_secrets_required=copy.deepcopy(required_secrets),
                config_paths_required={'qbitwebui': ['qbitwebui.db', '.salt']} if 'qbitwebui' in selected else {},
                whole_stack_recovery_proven=False)


def immutable_manifest(state, payload, label):
    expect(label in ('snapshot', 'restore-attempt', 'restored', 'rollback-attempt'), 'unknown manifest label')
    path = Path(state) / ('pipeline-' + label + '-' + uuid.uuid4().hex + '.json')
    safety.write_private(path, json.dumps(payload, sort_keys=True))  # O_EXCL; never replace old evidence.
    return path


def archive_tree(root):
    """One tar per claim, dereference=False preserves internal hardlinks."""
    root = Path(root)
    expect(root.is_dir() and not root.is_symlink(), 'real volume root required')
    total = 0
    for p in [root, *root.parents, *root.rglob('*')]:
        expect(not p.is_symlink(), 'symlink forbidden in fixture snapshot')
        mode = p.stat().st_mode
        expect(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'special file forbidden')
        if stat.S_ISREG(mode):
            total += p.stat().st_size
            expect(total <= 128 * 1024 * 1024, 'snapshot input exceeds fresh fixture bound')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', dereference=False) as archive:
        archive.add(root, arcname='.', recursive=True)
    payload = buffer.getvalue()
    safety_archive(payload)
    return payload


def safety_archive(payload):
    expect(len(payload) <= 128 * 1024 * 1024, 'archive exceeds fresh fixture bound')
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:') as archive:
        members = archive.getmembers()
        names = set()
        regular = set()
        for m in members:
            p = PurePosixPath(m.name)
            expect(not p.is_absolute() and '..' not in p.parts, 'unsafe archive path')
            expect(str(p) not in names, 'duplicate archive member')
            names.add(str(p))
            expect(m.isdir() or m.isfile() or m.islnk(), 'unsupported archive member')
            if m.isfile():
                regular.add(str(p))
        for m in members:
            if m.islnk():
                target = PurePosixPath(m.linkname)
                expect(not target.is_absolute() and '..' not in target.parts and str(target) in regular, 'unsafe hardlink target')
        # A file cannot be an ancestor of another member.
        non_dirs = {str(PurePosixPath(m.name)) for m in members if not m.isdir()}
        expect(all(not any(str(p) in non_dirs for p in PurePosixPath(m.name).parents) for m in members), 'non-directory archive ancestor')


def restore_tree(payload, destination, expected_sha256):
    expect(hashlib.sha256(payload).hexdigest() == expected_sha256, 'archive checksum mismatch')
    safety_archive(payload)
    destination = Path(destination)
    expect(destination.is_absolute() and '..' not in destination.parts, 'canonical destination required')
    expect(all(not p.is_symlink() for p in (destination, *destination.parents)), 'destination symlink forbidden')
    # Exclusive root means failed/partial extraction cannot be silently retried.
    destination.mkdir(mode=0o700, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:') as archive:
        archive.extractall(destination, filter='data')


def capture_local(state, recovery_plan, roots):
    """Temporary/local fixture tool, NOT a cluster snapshot or grant."""
    expect(set(roots) == {v['source_claim'] for v in recovery_plan['volumes']}, 'capture every selected claim exactly once')
    result = copy.deepcopy(recovery_plan)
    for volume in result['volumes']:
        root = Path(roots[volume['source_claim']])
        if volume['source_claim'] == 'qbitwebui-config':
            expect(all((root / p).is_file() for p in result['config_paths_required']['qbitwebui']), 'qbitwebui DB/salt missing from actual capture')
        payload = archive_tree(root)
        archive = Path(state) / ('pipeline-volume-' + uuid.uuid4().hex + '.tar')
        safety.write_private(archive, payload)
        volume.update(archive=archive.name, sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
    result['capture_kind'] = 'local-fixture-only'
    return immutable_manifest(state, result, 'snapshot')


def verify_pvc_uids(expected, inventory):
    indexed = {}
    for pvc in inventory:
        meta = pvc['metadata']
        expect(meta['namespace'] == NS and meta['name'] not in indexed, 'PVC namespace/duplicate identity differs')
        indexed[meta['name']] = meta['uid']
    expect(all(indexed.get(name) == uid for name, uid in expected.items()), 'PVC identity changed; no restart permitted')


def rebind_plan(recovery_plan, deployments, pods, fresh_pvcs, *, current_pvcs):
    """Pure all-alias patch plan. Does not create PVCs or patch/restart apps."""
    stopped(deployments, pods)
    expect(bindings(deployments) == recovery_plan['original'], 'original mappings drifted')
    verify_pvc_uids({v['source_claim']: v['source_uid'] for v in recovery_plan['volumes']}, current_pvcs)
    expect(set(fresh_pvcs) == {v['source_claim'] for v in recovery_plan['volumes']}, 'fresh PVC mapping incomplete')
    restored = copy.deepcopy(recovery_plan['original'])
    original_uids = {v['source_uid'] for v in recovery_plan['volumes']}
    source_names = {v['source_claim'] for v in recovery_plan['volumes']}
    used_names, used_uids = set(), set()
    for v in recovery_plan['volumes']:
        pvc = fresh_pvcs[v['source_claim']]
        meta = pvc['metadata']
        expect(meta['namespace'] == NS and meta['name'] not in source_names
               and meta['uid'] and meta['uid'] not in original_uids, 'restore requires distinct fresh PVC identity')
        expect(meta['name'] not in used_names and meta['uid'] not in used_uids, 'fresh PVCs must be independent')
        expect(pvc['spec']['resources']['requests']['storage'] == v['storage'], 'fresh PVC storage differs')
        used_names.add(meta['name']); used_uids.add(meta['uid'])
        for app, alias in v['aliases']:
            restored[app][alias] = meta['name']
    return dict(original=copy.deepcopy(recovery_plan['original']), restored=restored,
                source_pvc_uids={v['source_claim']: v['source_uid'] for v in recovery_plan['volumes']},
                fresh_pvc_uids={v['metadata']['name']: v['metadata']['uid'] for v in fresh_pvcs.values()},
                restart_authorized=False, read_before_test_writes_required=True)


def mapping_patches(current, target):
    expect(current.keys() == target.keys(), 'deployment set differs')
    return {app: [{'volume': alias, 'from_claim': claim, 'to_claim': target[app][alias]}
                  for alias, claim in volumes.items() if claim != target[app][alias]]
            for app, volumes in current.items()}


def rollback_plan(transaction, deployments, pods, *, current_pvcs):
    stopped(deployments, pods)
    expect(bindings(deployments) == transaction['restored'], 'restored mappings drifted; refuse blind rollback')
    verify_pvc_uids({**transaction['source_pvc_uids'], **transaction['fresh_pvc_uids']}, current_pvcs)
    return mapping_patches(transaction['restored'], transaction['original'])


def verify_mappings(transaction, deployments, pods, *, current_pvcs, rollback=False):
    stopped(deployments, pods)
    expected = transaction['original' if rollback else 'restored']
    expect(bindings(deployments) == expected, 'mapping verification failed; no restart permitted')
    verify_pvc_uids(transaction['source_pvc_uids' if rollback else 'fresh_pvc_uids'], current_pvcs)
    return {'mappings_verified': True, 'restart_authorized': False,
            'next_gate': 'owner safety admission then existing API/file IDs read BEFORE test writes; external Secrets/keys independently required'}


if __name__ == '__main__':
    raise SystemExit('OFFLINE PRIMITIVES ONLY; no cluster/helper/restart authority')
