#!/usr/bin/env python3
"""Offline creation-contract tests. Native runtime discovery remains unexecuted."""
import importlib
import copy
import json
import tempfile
import importlib.util
from pathlib import Path
import sys
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'tests')]
v = importlib.import_module('talos-proof-media-services')

class Discovery(unittest.TestCase):
    def test_adapter_prepare_stopped_only_and_preserves_entire_other_spec(self):
        module = importlib.import_module('talos-proof-media-plex-discover')
        before = {'spec':{'replicas':0,'template':{'spec':{'volumes':[
            {'name':'local-adapter-code','configMap':{'name':'old'}},
            {'name':'config','persistentVolumeClaim':{'claimName':'recovered-uuid'}},
            {'name':'auth','secret':{'secretName':'bootstrap'}}],
            'containers':[{'name':'plex','image':'unchanged','resources':{'limits':{'memory':'384Mi'}}}]}}}}
        for active in (False,True):
            def kube(group,*args,**kwargs):
                if 'pods' in args:return json.dumps({'items':[{'active':True}] if active else []}).encode()
                if 'deployments,statefulsets' in args:return b'{"items":[]}'
                if 'get' in args:
                    value=copy.deepcopy(before)
                    if updated[0]:value['spec']=updated[0]
                    return json.dumps(value).encode()
                if 'patch' in args:
                    patch=json.loads(args[-1]);self.assertEqual(patch[0]['value'],before['spec']);updated[0]=patch[1]['value']
                return b'{}'
            updated=[None]
            with tempfile.TemporaryDirectory() as tmp, patch.object(module.s,'guard'),patch.object(module.s,'require_helpers_deleted'),patch.object(module.s,'kube',side_effect=kube) as calls:
                if active:
                    with self.assertRaisesRegex(RuntimeError,'must be stopped'):module.prepare_adapter('media-plex-tautulli',Path(tmp).resolve())
                    self.assertFalse(any('patch' in c.args or 'apply' in c.args for c in calls.call_args_list))
                else:
                    module.prepare_adapter('media-plex-tautulli',Path(tmp).resolve())
                    restored=copy.deepcopy(updated[0]);restored['template']['spec']['volumes'][0]['configMap']['name']='old'
                    self.assertEqual(restored,before['spec'])

    def test_adapter_discovery_exception_exact_get_query_only(self):
        spec = importlib.util.spec_from_file_location('plex_discovery_adapter',ROOT/'kubernetes/apps/media/plex/plex-unclaimed-proxy.py')
        adapter = importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        allowed = '/system/agents?mediaType=1'
        self.assertTrue(adapter.native_agent_discovery('GET',urllib.parse.urlsplit(allowed)))
        for method,path in [('POST',allowed),('DELETE',allowed),('GET','/system/agents'),
                            ('GET',allowed+'&mediaType=1'),('GET',allowed+'&extra='),
                            ('GET','/system/agents/com.plexapp.agents.none?mediaType=1')]:
            self.assertFalse(adapter.native_agent_discovery(method,urllib.parse.urlsplit(path)))

    def test_legacy_query_shape_uses_only_native_offered_no_language(self):
        for code in ['en-US','en','xn']:
            xml = ET.fromstring('<MediaContainer><Agent identifier="com.plexapp.agents.none"><Language code="'+code+'"/></Agent></MediaContainer>')
            with patch.object(v,'plex_xml',return_value=xml) as discovery:
                if code != 'xn':
                    with self.assertRaisesRegex(RuntimeError,'did not advertise'):v.plex_creation_query(Mock())
                else:
                    query = urllib.parse.parse_qs(v.plex_creation_query(Mock()))
                    self.assertEqual(query['language'],['xn'])
                    self.assertEqual(query['type'],['movie'])
                    self.assertEqual(query['location'],['/data/media'])
                self.assertEqual(discovery.call_args.args[1],'/system/agents?mediaType=1')
    def test_missing_or_duplicate_agent_fails(self):
        for body in ['<MediaContainer/>','<MediaContainer>'+2*'<Agent identifier="com.plexapp.agents.none"/>'+'</MediaContainer>']:
            with patch.object(v,'plex_xml',return_value=ET.fromstring(body)), self.assertRaises(RuntimeError):
                v.plex_creation_query(Mock())

if __name__ == '__main__': unittest.main()
