#!/usr/bin/env python3
"""Real temp-filesystem hardlink archives; offline mapping doubles, no cluster."""
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
r = importlib.import_module('talos-proof-media-pipeline-recovery')
a = importlib.import_module('talos-proof-media-arr-import')


def deployments(names=r.SERVICES):
    return [dict(metadata=dict(name=n, namespace=r.NS), spec=dict(replicas=0, template=dict(spec=dict(volumes=[
        dict(name='config',persistentVolumeClaim={'claimName':n+'-config'}),
        *([] if n == 'prowlarr' else [dict(name='fixture',persistentVolumeClaim={'claimName':'data'}),
                                    dict(name='shared-data',persistentVolumeClaim={'claimName':'data'})])])))) for n in sorted(names)]


def pvc(name, uid=None):
    return dict(metadata=dict(name=name, namespace=r.NS, uid=uid or name+'-uid'),
                spec={'resources': {'requests': {'storage':'1Gi'}}})


def make_plan(ds=None, **kwargs):
    ds = ds or deployments()
    return r.plan(ds, [], [pvc('data'), *[pvc(n+'-config') for n in r.SERVICES]],
                  selected=kwargs.get('selected', ['qbittorrent','radarr']),
                  scope=kwargs.get('scope','selected-pair'),
                  required_secrets=kwargs.get('required_secrets',[dict(name='radarr-bootstrap',keys=['seed']),dict(name='qbittorrent-bootstrap',keys=['seed'])]))


def apply_mapping(ds, mapping):
    ds = copy.deepcopy(ds)
    for d in ds:
        for v in d['spec']['template']['spec']['volumes']:
            v['persistentVolumeClaim']['claimName'] = mapping[d['metadata']['name']][v['name']]
    return ds


class Recovery(unittest.TestCase):
    def test_shared_archive_once_independent_configs_scope_and_secrets(self):
        plan = make_plan()
        self.assertEqual([v['source_claim'] for v in plan['volumes']], ['data','qbittorrent-config','radarr-config'])
        self.assertEqual(len(plan['volumes'][0]['aliases']), 12)
        self.assertFalse(plan['whole_stack_recovery_proven'])
        with self.assertRaisesRegex(RuntimeError, 'all-seven'):
            make_plan(scope='all-seven-configured')
        with self.assertRaisesRegex(RuntimeError, 'bootstrap Secret'):
            make_plan(selected=['qbittorrent','qbitwebui'])
        full = make_plan(scope='all-seven-configured', selected=r.SERVICES,
                         required_secrets=[dict(name=n+'-bootstrap',keys=['encryption-key','password'] if n=='qbitwebui' else ['seed']) for n in r.SERVICES])
        self.assertEqual(len(full['volumes']), 8)
        self.assertEqual(full['config_paths_required']['qbitwebui'], ['qbitwebui.db','.salt'])

    def test_all_apps_and_all_pods_off_even_unselected_and_terminal(self):
        ds = deployments(); ds[-1]['spec']['replicas']=1
        with self.assertRaisesRegex(RuntimeError, 'ALL applications'): make_plan(ds)
        with self.assertRaisesRegex(RuntimeError, 'ALL group pods'):
            r.stopped(deployments(), [{'status':{'phase':'Succeeded'}}])
        with self.assertRaisesRegex(RuntimeError, 'owner must authorize'): r.require_owner_wiring()

    def test_all_shared_aliases_rebound_and_rollback_verified_before_restart(self):
        ds = deployments(); plan = make_plan(ds)
        fresh = {v['source_claim']:pvc('new-'+v['source_claim']) for v in plan['volumes']}
        inventory = [pvc(v['source_claim']) for v in plan['volumes']] + list(fresh.values())
        transaction = r.rebind_plan(plan, ds, [], fresh, current_pvcs=inventory)
        self.assertFalse(transaction['restart_authorized'])
        rebound = apply_mapping(ds,transaction['restored'])
        for app, volumes in transaction['restored'].items():
            for alias, claim in volumes.items():
                if alias != 'config': self.assertEqual(claim, 'new-data')
        patches = r.rollback_plan(transaction, rebound, [], current_pvcs=inventory)
        self.assertIn('sonarr', patches)  # Unselected config retained, shared alias moves.
        self.assertTrue(r.verify_mappings(transaction, rebound, [], current_pvcs=inventory)['mappings_verified'])
        with self.assertRaisesRegex(RuntimeError, 'no restart'):
            r.verify_mappings(transaction, rebound, [], rollback=True, current_pvcs=inventory)
        self.assertTrue(r.verify_mappings(transaction, ds, [], rollback=True, current_pvcs=inventory)['mappings_verified'])
        drift = copy.deepcopy(rebound); drift[0]['spec']['template']['spec']['volumes'][0]['persistentVolumeClaim']['claimName']='wrong'
        with self.assertRaisesRegex(RuntimeError, 'refuse blind rollback'): r.rollback_plan(transaction,drift,[],current_pvcs=inventory)
        with self.assertRaisesRegex(RuntimeError, 'original mappings drifted'): r.rebind_plan(plan,rebound,[],fresh,current_pvcs=inventory)
        with self.assertRaisesRegex(RuntimeError, 'PVC identity changed'):
            r.verify_mappings(transaction, ds, [], rollback=True, current_pvcs=[])
        fresh['data']['metadata']['uid']='data-uid'
        with self.assertRaisesRegex(RuntimeError, 'distinct fresh'): r.rebind_plan(plan,ds,[],fresh,current_pvcs=inventory)

    def test_real_hardlink_roundtrip_and_checksum_corruption_no_partial_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); data=root/'data'; (data/'torrents').mkdir(parents=True); (data/'media').mkdir()
            source=data/'torrents'/'fixture.mp4'; source.write_bytes(b'procedural test fixture')
            imported=data/'media'/'import.mp4'; imported.hardlink_to(source)
            payload=r.archive_tree(data)
            digest=hashlib.sha256(payload).hexdigest()
            dest=root/'restored'; r.restore_tree(payload,dest,digest)
            expected=dict(size=source.stat().st_size,sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertTrue(a.hardlink_oracle(a.observe_file(dest/'torrents'/'fixture.mp4'),a.observe_file(dest/'media'/'import.mp4'),expected)['same_device_inode'])
            with self.assertRaises(FileExistsError): r.restore_tree(payload,dest,digest)
            with self.assertRaisesRegex(RuntimeError,'checksum'): r.restore_tree(payload+b'corrupt',root/'bad',digest)
            self.assertFalse((root/'bad').exists())

    def test_immutable_uuid_manifests_shared_once_and_old_artifacts_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp).resolve(); old=state/'old.tar'; old.write_bytes(b'old retained evidence')
            plan=make_plan(); roots={}
            for v in plan['volumes']:
                p=state/v['source_claim']; p.mkdir(); (p/'fixture').write_text(v['source_claim']); roots[v['source_claim']]=p
            manifest=r.capture_local(state,plan,roots)
            result=json.loads(manifest.read_text())
            self.assertEqual(result['capture_kind'],'local-fixture-only')
            self.assertEqual(len({v['archive'] for v in result['volumes']}),3)
            self.assertEqual(old.read_bytes(),b'old retained evidence')
            second=r.immutable_manifest(state,{},'snapshot'); self.assertNotEqual(second,manifest)
            with patch.object(r.uuid,'uuid4',return_value=type('U',(),{'hex':'fixed'})()):
                r.immutable_manifest(state,{},'restore-attempt')
                with self.assertRaises((FileExistsError, RuntimeError)): r.immutable_manifest(state,{},'restore-attempt')

    def test_qbitwebui_salt_must_actually_be_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp).resolve()
            plan=make_plan(selected=['qbittorrent','qbitwebui'],required_secrets=[dict(name='qbitwebui-bootstrap',keys=['encryption-key','password']),dict(name='qbittorrent-bootstrap',keys=['seed'])])
            roots={}
            for v in plan['volumes']:
                p=state/v['source_claim'];p.mkdir();roots[v['source_claim']]=p
            with self.assertRaisesRegex(RuntimeError,'DB/salt'): r.capture_local(state,plan,roots)

    def test_unsafe_archive_links_traversal_and_special_files_rejected(self):
        for name, kind, target in [('../escape',tarfile.REGTYPE,''),('bad',tarfile.SYMTYPE,'safe'),
                                   ('bad',tarfile.LNKTYPE,'../escape'),('device',tarfile.CHRTYPE,''),
                                   ('bad',tarfile.LNKTYPE,'missing')]:
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w') as t:
                m=tarfile.TarInfo(name);m.type=kind;m.linkname=target;t.addfile(m)
            with self.subTest(name=name,kind=kind),self.assertRaises(RuntimeError): r.safety_archive(stream.getvalue())


if __name__=='__main__':unittest.main()
