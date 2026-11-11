#!/usr/bin/env python3
"""Narrow native Plex READ-ONLY discovery. No activation or creation fallback."""
import importlib
import json
from pathlib import Path
import re
import sys
import uuid
import argparse
s = importlib.import_module('talos-proof-media-safety')
d = importlib.import_module('talos-proof-media-dependencies')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--ca', type=Path, required=True)
    p.add_argument('--group', choices=['media-plex-tautulli'], required=True)
    a = p.parse_args()
    state = s.private_dir(a.state)
    credentials = json.loads(s.read_private(state / 'credentials.json'))
    api = d.api_for('plex', s.private_file(a.ca), credentials)
    result = {}
    for path in ['/identity','/library/sections','/system/agents?mediaType=1','/media/providers']:
        s.lease(a.group);s.exclusivity(a.group)
        try:
            root = d.xml(api, path)
            # Native XML may carry identity/auth-bearing fields. Keep only private.
            import xml.etree.ElementTree as ET
            filename = 'plex-discovery-' + uuid.uuid4().hex + '.xml'
            s.write_private(state / filename, ET.tostring(root))
            summary = {'http_status':api.last_status,'private_response':filename}
            if path.startswith('/system/agents'):
                codes = [x.get('code') for agent in root.findall('Agent')
                         if agent.get('identifier') == 'com.plexapp.agents.none' for x in agent.iter('Language')]
                summary['personal_agent_languages'] = [x for x in codes if x and re.fullmatch(r'[a-zA-Z-]{1,16}',x)]
                summary['native_offered_no_language'] = 'xn' in codes
            result[path] = summary
        except Exception as exc:
            result[path] = {'error_type':type(exc).__name__,'http_status':getattr(exc,'code',None)}
    s.write_private(state / ('plex-discovery-' + uuid.uuid4().hex + '.json'), json.dumps(result))
    print(json.dumps({'result':'DISCOVERY_ONLY_NOT_FUNCTIONAL_PASS','responses':result}))

if __name__ == '__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'result':'FAIL','error_type':type(exc).__name__}))
        raise SystemExit(1)
