#!/usr/bin/env python3
"""Offline optional-profile/native-completion mutants. No Pinchflat execution."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
p=importlib.import_module('talos-proof-media-pinchflat-provider')


class Provider(unittest.TestCase):
    def test_optional_render_defaults_and_fixture_cannot_mount_client_pvcs(self):
        root=subprocess.check_output(['kubectl','kustomize',str(ROOT/'kubernetes/apps/media')]).decode()
        self.assertNotIn('rss-fixture',root)
        docs=list(yaml.safe_load_all(subprocess.check_output(['kubectl','kustomize',str(ROOT/'kubernetes/apps/media/pinchflat-rss')])))
        deployment=next(x for x in docs if x['kind']=='Deployment')
        self.assertEqual(deployment['spec']['replicas'],0)
        spec=deployment['spec']['template']['spec']
        app,fixture=spec['containers']
        self.assertEqual(app['resources']['limits']['memory'],'256Mi')
        self.assertEqual(fixture['resources']['limits']['memory'],'128Mi')
        self.assertEqual(fixture['name'],'rss-fixture')
        self.assertTrue(all(m.get('readOnly') for m in fixture['volumeMounts'] if m['name']!='rss-stats'))
        input_mount=next(m for m in fixture['volumeMounts'] if m['name']=='rss-input')
        self.assertEqual(input_mount['subPath'],'fixture.mp4')
        self.assertEqual(input_mount['mountPath'],'/proof-input/fixture.mp4')
        self.assertFalse(set(m['name'] for m in fixture['volumeMounts']) & {'config','fixture'})
        self.assertFalse(any(m['name'].startswith('rss-') for m in app['volumeMounts']))
        self.assertNotIn('serviceAccountToken',json.dumps(spec['volumes']))
        self.assertNotIn('ipBlock',root)
    def test_wrong_marker_blocks_kube_and_prepare_cannot_overlap_app(self):
        with patch.object(p.s,'lease',return_value=({'provider_fixture':'wrong'},{})), patch.object(p.s,'kube') as kube:
            with self.assertRaises(RuntimeError):p.kube('apply','-f','-')
            kube.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp).resolve();fixture=state/p.INPUT;fixture.write_bytes(b'not playable test input');fixture.chmod(0o600)
            with patch.object(p.s,'pinchflat_provider_guard'),patch.object(p.s,'require_helpers_deleted'), \
                 patch.object(p,'INPUT_SHA',hashlib.sha256(fixture.read_bytes()).hexdigest()), \
                 patch.object(p,'kube',return_value=json.dumps({'spec':{'replicas':1}}).encode()) as kube:
                with self.assertRaisesRegex(RuntimeError,'stopped'):p.prepare(state,fixture)
                self.assertEqual(kube.call_args.args,('get','deployment','pinchflat','-o','json'))
    def test_only_download_phase_full_coverage_and_same_instance_can_pass(self):
        before={'instance_id':'one','media_sha256':p.INPUT_SHA,'phases':{'download':{'media_body_bytes':0,'media_unique_bytes':0}}}
        after={'instance_id':'one','media_sha256':p.INPUT_SHA,'media_size':120214,
               'phases':{'download':{'media_body_bytes':120214,'media_unique_bytes':120214,'routes':{'/media/proof-001.mp4':1}}}}
        p.coverage(before,after)
        mutants=[]
        value=copy.deepcopy(after);value['instance_id']='restarted';mutants.append(value)
        value=copy.deepcopy(after);value['phases']['download']['media_unique_bytes']=0;mutants.append(value)
        value=copy.deepcopy(after);value['phases']['download']['media_body_bytes']=120213;mutants.append(value)
        for value in mutants:
            with self.assertRaises(RuntimeError):p.coverage(before,value)
        value=copy.deepcopy(before);value['phases']['download']['media_body_bytes']=1
        with self.assertRaises(RuntimeError):p.coverage(value,after)
    def test_real_index_and_download_jobs_are_required_not_just_rows_or_file(self):
        item={'id':3,'source_id':2,'original_url':p.HTML,'media_id':'proof-001','title':'Synthetic proof 001',
              'uploaded_at':'2026-01-01T00:00:00Z','duration_seconds':12,'media_downloaded_at':'native-time',
              'media_filepath':'/downloads/rss-proof-unique/item.mp4','media_size_bytes':120214,'last_error':None}
        index={'source_id':2,'media_item_id':None,'id':4,'worker':'Pinchflat.SlowIndexing.MediaCollectionIndexingWorker','state':'completed','completed_at':'native-time'}
        download={'source_id':2,'media_item_id':3,'id':5,'worker':'Pinchflat.Downloading.MediaDownloadWorker','state':'completed','completed_at':'native-time'}
        observed={'items':[item],'jobs':[index,download]}
        self.assertEqual(p.completion(observed,2)[0],item)
        for change in ['no-index','no-download','error','no-date','wrong-size']:
            value=copy.deepcopy(observed)
            if change=='no-index':value['jobs'].pop(0)
            elif change=='no-download':value['jobs'][-1]['state']='available'
            elif change=='error':value['items'][0]['last_error']='retained failure'
            elif change=='no-date':value['items'][0]['uploaded_at']=None
            else:value['items'][0]['media_size_bytes']=0
            with self.assertRaises(RuntimeError):p.completion(value,2)
    def test_global_stage_checks_do_not_confuse_per_queue_one_with_global_one(self):
        p.stage_executing({'executing':[{'queue':'media_fetching'}]},'media_fetching')
        for jobs in [[{'queue':'media_fetching'},{'queue':'media_collection_indexing'}],[{'queue':'remote_metadata'}]]:
            with self.assertRaises(RuntimeError):p.stage_executing({'executing':jobs},'media_fetching')
    def test_readonly_sql_and_no_replacement_downloader(self):
        self.assertTrue(all(query.startswith('SELECT ') for query in p.SQL.values()))
        self.assertIn('coalesce(t.source_id,m.source_id)',p.SQL['jobs'])
        self.assertIn('LEFT JOIN media_items',p.SQL['jobs'])
        source=(ROOT/'scripts/talos-proof-media-pinchflat-provider.py').read_text()
        self.assertNotIn('Repo.insert',source)
        self.assertNotIn('Repo.update',source)
        self.assertNotIn('yt-dlp -U',source)
        self.assertIn('command -v yt-dlp',source)
        self.assertIn('binary_after==binary',source)
        self.assertIn("'/sources','POST'",source)

if __name__=='__main__':unittest.main()
