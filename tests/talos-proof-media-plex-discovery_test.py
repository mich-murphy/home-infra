#!/usr/bin/env python3
"""Offline creation-contract tests. Native runtime discovery remains unexecuted."""
import importlib
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
