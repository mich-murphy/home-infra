#!/usr/bin/env python3
"""SHA-pinned public Nextcloud35 Office package; offline prepare or leased preload.
No app Internet, production configuration, global SSRF/TLS or DNS exceptions.
"""
import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = '12.0.2'
NAME = 'richdocuments-v12.0.2.tar.gz'
URL = 'https://github.com/nextcloud-releases/richdocuments/releases/download/v12.0.2/' + NAME
SHA256 = '5deacee4fa1bb8eb7068e86c6dadbdaf0e44f8c79df0298a2254f562e3ed949b'
SIZE = 14642847


def verify(path):
    with path.open('rb') as source:
        if hashlib.file_digest(source,'sha256').hexdigest() != SHA256 or path.stat().st_size != SIZE:
            raise RuntimeError('pinned Office package integrity mismatch')
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != 'richdocuments' or '..' in parts or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise RuntimeError('unsafe Office package member')
        info = archive.extractfile('richdocuments/appinfo/info.xml').read().decode()
        if '<version>12.0.2</version>' not in info or '<nextcloud min-version="35" max-version="35"/>' not in info:
            raise RuntimeError('unexpected Office compatibility metadata')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','preload'])
    parser.add_argument('--state',required=True)
    args=parser.parse_args()
    os.umask(0o077)
    spec=importlib.util.spec_from_file_location('life',ROOT/'scripts/talos-proof-data.py')
    life=importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
    state=life.private(args.state)
    path=life.no_symlinks(state/NAME)
    if args.action=='prepare':
        if not path.exists():
            partial=life.no_symlinks(state/(NAME+'.partial'))
            fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                with os.fdopen(fd,'wb') as target,urllib.request.urlopen(URL,timeout=120) as response:
                    while block:=response.read(1024*1024):target.write(block)
                verify(partial);partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
        verify(path)
        print('Verified public Office12.0.2 package SHA256 '+SHA256+'; no cluster access.')
        return
    verify(path)
    life.LEASE_GROUP='nextcloud';life.LEASE_STAGE='full'
    life.lease('nextcloud');life.participants('nextcloud')
    # Require one actual current CODE pod, never a broad cluster CIDR allowlist.
    pods=json.loads(life.kube('-n','proof-nextcloud','get','pods','-l','app.kubernetes.io/name=collabora','-o','json'))['items']
    ips=[p['status']['podIP'] for p in pods if p.get('status',{}).get('phase')=='Running' and not p['metadata'].get('deletionTimestamp')]
    if len(ips)!=1:raise RuntimeError('one current Collabora pod IP required')
    address=str(ipaddress.ip_address(ips[0]))
    life.kube('-n','proof-nextcloud','exec','deployment/nextcloud','--','sh','-ec',
        'test ! -e /var/www/html/custom_apps/richdocuments || test "$(cat /var/www/html/custom_apps/richdocuments/.proof-artifact-sha256)" = '+SHA256)
    life.lease('nextcloud')
    with path.open('rb') as source:
        result=subprocess.run(['kubectl','-n','proof-nextcloud','exec','-i','deployment/nextcloud','--','sh','-ec',
            'mkdir -p /var/www/html/custom_apps; tar -xzpf - --no-same-owner -C /var/www/html/custom_apps; '
            'printf %s '+SHA256+' > /var/www/html/custom_apps/richdocuments/.proof-artifact-sha256; '
            'chown -R 33:33 /var/www/html/custom_apps/richdocuments'],stdin=source,capture_output=True,timeout=180)
    if result.returncode:raise RuntimeError('proof-only Office preload failed; output withheld')
    def occ(command):
        life.kube('-n','proof-nextcloud','exec','deployment/nextcloud','--','su','-s','/bin/sh','www-data','-c','php /var/www/html/occ '+command)
    occ('app:enable richdocuments')
    for key,value in {'wopi_url':'http://collabora:9980','public_wopi_url':'https://collabora.proof.invalid',
        'wopi_callback_url':'http://nextcloud','wopi_allowlist':address,'disable_certificate_verification':'no'}.items():
        occ('config:app:set richdocuments '+key+' --value='+value)
    occ('richdocuments:activate-config')
    print('Pinned proof Office enabled with supported internal URLs and exact current CODE IP; editing not yet implied.')


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Office preparation stopped: '+type(error).__name__)
        raise SystemExit(1)
