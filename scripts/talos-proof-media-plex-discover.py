#!/usr/bin/env python3
"""Native Plex discovery; optional explicit stopped-only adapter code update.

Default is READ-ONLY. Neither mode activates apps or creates libraries.
"""
import importlib
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
import argparse
s = importlib.import_module('talos-proof-media-safety')
d = importlib.import_module('talos-proof-media-dependencies')

def prepare_adapter(group, state):
    """Approved stopped-only code/reference update; never reapply the base."""
    if group != 'media-plex-tautulli':
        raise RuntimeError('exact Plex/Tautulli group required')
    s.guard(group)
    s.require_helpers_deleted(group)
    for service in ('plex', 'tautulli'):
        pods = json.loads(s.kube(group, '-n', 'proof-' + service, 'get', 'pods', '-o', 'json'))['items']
        controllers = json.loads(s.kube(group, '-n', 'proof-' + service, 'get', 'deployments,statefulsets', '-o', 'json'))['items']
        if pods or any(x['spec'].get('replicas', 1) != 0 for x in controllers):
            raise RuntimeError('both Plex and Tautulli must be stopped with all pods deleted')
    before = json.loads(s.kube(group, '-n', 'proof-plex', 'get', 'deployment', 'plex', '-o', 'json'))
    code = (s.ROOT / 'kubernetes/apps/media/plex/plex-unclaimed-proxy.py').read_text()
    name = 'local-unclaimed-adapter-' + hashlib.sha256(code.encode()).hexdigest()[:16]
    resource = {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':'proof-plex',
        'labels':{'app.kubernetes.io/part-of':'talos-proof','app.kubernetes.io/name':'plex'}},
        'immutable':True,'data':{'plex-unclaimed-proxy.py':code}}
    expected = copy.deepcopy(before['spec'])
    volumes = expected['template']['spec']['volumes']
    matches = [x for x in volumes if x['name'] == 'local-adapter-code']
    if len(matches) != 1:
        raise RuntimeError('expected exact existing adapter code volume')
    matches[0]['configMap']['name'] = name
    # JSON Patch test makes a concurrent spec change fail before replacement.
    patch = [{'op':'test','path':'/spec','value':before['spec']},
             {'op':'replace','path':'/spec','value':expected}]
    s.write_private(state / ('plex-adapter-before-' + uuid.uuid4().hex + '.json'), json.dumps(before))
    s.kube(group, '-n', 'proof-plex', 'apply', '-f', '-', data=json.dumps(resource).encode())
    s.kube(group, '-n', 'proof-plex', 'patch', 'deployment', 'plex', '--type=json', '-p', json.dumps(patch))
    after = json.loads(s.kube(group, '-n', 'proof-plex', 'get', 'deployment', 'plex', '-o', 'json'))
    s.write_private(state / ('plex-adapter-after-' + uuid.uuid4().hex + '.json'), json.dumps(after))
    if after['spec'] != expected:
        raise RuntimeError('adapter-only update changed unexpected Deployment fields')
    print(json.dumps({'result':'PREPARED_STOPPED_ONLY','configmap':name,
                      'entire_spec_matches_only_code_reference_change':True}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--ca', type=Path, required=True)
    p.add_argument('--group', choices=['media-plex-tautulli'], required=True)
    p.add_argument('--prepare-adapter', action='store_true', help='explicit approved stopped-only adapter code/reference update; no activation')
    a = p.parse_args()
    state = s.private_dir(a.state)
    if a.prepare_adapter:
        prepare_adapter(a.group, state)
        return
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
