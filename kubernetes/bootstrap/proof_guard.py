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
    if c.get('proxy-url') or c.get('tls-server-name'):
        raise ValueError('Kubeconfig proxy/TLS-name overrides are forbidden')
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
# These affect Helm/client-go transport or credentials independently of the checked
# context. Refuse even empty variables rather than relying on tool-specific parsing.
ENV_OVERRIDES = {
    'KUBERNETES_MASTER', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
    'http_proxy', 'https_proxy', 'all_proxy',
}
FORBIDDEN_FLAGS = {
    '--server', '--kubeconfig', '--cluster', '--user',
    '--insecure-skip-tls-verify', '--tls-server-name', '--certificate-authority',
    '--client-certificate', '--client-key', '--token', '--username', '--password',
    '--as', '--as-group', '--as-uid', '--proxy-url', '--kuberc',
}
def validate_environment():
    if any(name in ENV_OVERRIDES or name.startswith('HELM_KUBE') for name in os.environ):
        raise ValueError('Inherited target/TLS/auth/proxy overrides are forbidden')
    if os.environ.get('KUBECTL_KUBERC', 'false') != 'false':
        raise ValueError('Kubectl preference overrides are forbidden')
    # New kubectl versions can load flag defaults/aliases from a preferences file.
    os.environ['KUBECTL_KUBERC'] = 'false'

def validate_args(args):
    """Inspect only kubectl arguments, not the command after the first --.

    Cobra/pflag accepts -sURL, -s=URL and boolean clusters such as -itsURL.
    Value-taking shorthands consume their remaining token (-nnamespace is not
    a server flag). Unknown short options fail closed rather than guessing.
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--':
            break
        if arg.startswith('--'):
            flag = arg.split('=', 1)[0].replace('_', '-')
            if flag in FORBIDDEN_FLAGS:
                raise ValueError('Target/TLS/auth override flags are forbidden')
            if flag == '--context':
                if '=' in arg:
                    context = arg.split('=', 1)[1]
                else:
                    i += 1
                    context = args[i] if i < len(args) else None
                if context != os.environ.get('PROOF_CONTEXT'):
                    raise ValueError('Context override forbidden')
        elif arg.startswith('-') and arg != '-':
            for pos, short in enumerate(arg[1:], 1):
                if short == 's':
                    raise ValueError('Server shorthand override forbidden')
                if short in 'cfklnopv':  # value consumes suffix or next argument
                    if pos == len(arg) - 1:
                        i += 1
                    break
                if short not in 'AaFhiqRtw':
                    raise ValueError('Unrecognized short option forbidden')
        i += 1

def kubectl_args():
    return ['kubectl', '--kubeconfig', os.environ['KUBECONFIG'],
            '--context', os.environ['PROOF_CONTEXT'], '--server', TARGET['server']]

def check():
    validate_environment()
    if not os.environ.get('KUBECONFIG') or not os.environ.get('PROOF_CONTEXT'):
        raise ValueError('Explicit private kubeconfig and context required')
    if os.pathsep in os.environ['KUBECONFIG']:
        raise ValueError('One dedicated kubeconfig file required')
    if os.environ.get('PROOF_API_SERVER') != TARGET['server']:
        raise ValueError('Expected server must equal pinned proof endpoint')
    k = kubectl_args() + ['--request-timeout=15s']
    # Inspect the configured endpoint without a server override hiding a mismatch.
    validate_config(json.loads(subprocess.check_output(
        kubectl_args()[:-2] + ['config', 'view', '--minify', '-o', 'json'])))
    validate_nodes(json.loads(subprocess.check_output(k + ['get', 'nodes', '-o', 'json'])))

def main():
    try:
        validate_args(sys.argv[1:])
        check()
        if len(sys.argv) > 1:
            os.execvp('kubectl', kubectl_args() + sys.argv[1:])
    except (ValueError, KeyError, subprocess.CalledProcessError):
        # Do not echo caller arguments, config contents, or credential values.
        raise SystemExit('Proof safety guard refused operation') from None
if __name__ == '__main__':
    main()
