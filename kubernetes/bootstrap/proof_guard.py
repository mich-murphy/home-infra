#!/usr/bin/env python3
"""Fail-closed identity guard for this isolated live proof, never prints credentials."""
import json, os, subprocess, sys
from pathlib import Path
TARGET = json.loads(Path(__file__).with_name('proof-target.json').read_text())
def validate_config(config):
    clusters = config.get('clusters', [])
    if len(clusters) != 1:
        raise ValueError('Expected one minified cluster')
    c = clusters[0]['cluster']
    if c.get('server') != TARGET['server'] or c.get('insecure-skip-tls-verify', False):
        raise ValueError('Not the pinned TLS-enabled proof endpoint')
    if not (c.get('certificate-authority') or c.get('certificate-authority-data')):
        raise ValueError('Explicit trusted proof CA required')
def validate_nodes(value):
    nodes = value.get('items', [])
    if len(nodes) != 1:
        raise ValueError('Expected exactly one proof node')
    n = nodes[0]
    ips = [a['address'] for a in n['status']['addresses'] if a['type'] == 'InternalIP']
    if (n['metadata']['name'] != TARGET['nodeName'] or
        n['metadata']['uid'] != TARGET['nodeUID'] or ips != [TARGET['nodeIP']]):
        raise ValueError('Proof node identity mismatch')
def check():
    if not os.environ.get('KUBECONFIG') or not os.environ.get('PROOF_CONTEXT'):
        raise ValueError('Explicit private kubeconfig and context required')
    if os.environ.get('PROOF_API_SERVER') != TARGET['server']:
        raise ValueError('Expected server must equal pinned proof endpoint')
    k = ['kubectl', '--context', os.environ['PROOF_CONTEXT'], '--request-timeout=15s']
    validate_config(json.loads(subprocess.check_output(k + ['config', 'view', '--minify', '-o', 'json'])))
    validate_nodes(json.loads(subprocess.check_output(k + ['get', 'nodes', '-o', 'json'])))
def main():
    try:
        check()
        if len(sys.argv) > 1:
            forbidden = ['--server', '--kubeconfig', '--cluster', '--user', '--insecure-skip-tls-verify', '--tls-server-name', '--certificate-authority']
            if any(a == flag or a.startswith(flag + '=') for a in sys.argv[1:] for flag in forbidden):
                raise ValueError('Target/TLS override flags are forbidden')
            args = sys.argv[1:]
            for i, arg in enumerate(args):
                if arg == '--context' and (i + 1 >= len(args) or args[i + 1] != os.environ['PROOF_CONTEXT']):
                    raise ValueError('Context override forbidden')
                if arg.startswith('--context=') and arg.split('=', 1)[1] != os.environ['PROOF_CONTEXT']:
                    raise ValueError('Context override forbidden')
            os.execvp('kubectl', ['kubectl', '--context', os.environ['PROOF_CONTEXT']] + sys.argv[1:])
    except (ValueError, KeyError, subprocess.CalledProcessError) as e:
        raise SystemExit('Proof safety guard refused operation: ' + str(e)) from None
if __name__ == '__main__':
    main()
