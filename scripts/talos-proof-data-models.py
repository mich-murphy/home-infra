#!/usr/bin/env python3
"""Public, commit-pinned Immich CLIP artifacts; Mac download, leased proof-only preload.
No cluster Internet policy exception is needed. No production model/cache is copied.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'ViT-B-32__openai'
REVISION = 'a857c8de2c07bbcfa6646adfcf31b798845afa1e'
REPO = 'immich-app/' + MODEL
FILES = ('config.json', 'textual/model.onnx', 'textual/merges.txt', 'textual/special_tokens_map.json',
         'textual/tokenizer.json', 'textual/tokenizer_config.json', 'textual/vocab.json',
         'visual/model.onnx', 'visual/preprocess_cfg.json')
PREFIX = 'clip/' + MODEL + '/' + REVISION


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['download','preload'])
    p.add_argument('--state',required=True)
    a = p.parse_args()
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location('life',ROOT/'scripts/talos-proof-data.py')
    life = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(life)
    state = life.private(a.state)
    target = state / 'models' / PREFIX
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    manifest_path = state / 'model-manifest.json'
    if a.action == 'download':
        tree_url = f'https://huggingface.co/api/models/{REPO}/tree/{REVISION}?recursive=true'
        tree = json.load(urllib.request.urlopen(tree_url,timeout=60))
        metadata = {x['path']:x for x in tree if x.get('type')=='file'}
        manifest = {'repo':REPO,'model':MODEL,'revision':REVISION,'cache_prefix':PREFIX,
                    'image_release':'Immich v3.3.6','selection':'Default-compatible 512-dimensional OpenCLIP; CPU ONNX only, no face/OCR/GPU claim.',
                    'source_metadata_url':tree_url,'files':[]}
        for name in FILES:
            path = life.no_symlinks(target/name)
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            url = f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}'
            info = metadata[name]
            if not path.exists():
                temp = path.with_suffix(path.suffix+'.partial')
                fd = os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                try:
                    with os.fdopen(fd,'wb') as f, urllib.request.urlopen(url,timeout=300) as response:
                        while block := response.read(1024*1024):
                            f.write(block)
                    temp.replace(path)
                finally:
                    if temp.exists(): temp.unlink()
            h = hashlib.sha256()
            with path.open('rb') as f:
                while block := f.read(1024*1024): h.update(block)
            digest = h.hexdigest()
            if path.stat().st_size != info['size']:
                raise RuntimeError('download size mismatch')
            expected = info.get('lfs',{}).get('oid')
            if expected and digest != expected:
                raise RuntimeError('upstream LFS SHA256 mismatch')
            manifest['files'].append({'path':name,'url':url,'bytes':path.stat().st_size,'sha256':digest,'upstream_lfs_sha256':expected})
            print('Verified public artifact: '+name)
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
        manifest_path.chmod(0o600)
        (ROOT/'docs/evidence/talos-data/ml-model-artifacts.json').write_text(json.dumps(manifest,indent=2)+'\n')
    else:
        life.LEASE_GROUP = 'immich'
        life.lease('immich')
        manifest = json.loads(life.no_symlinks(manifest_path).read_text())
        if manifest['revision'] != REVISION or manifest['model'] != MODEL:
            raise RuntimeError('unexpected artifact manifest')
        archive = life.no_symlinks(state/'model-preload.tar')
        with tarfile.open(archive,'w') as tar:
            for entry in manifest['files']:
                name = entry['path']
                if name not in FILES:
                    raise RuntimeError('unexpected model file')
                path = life.no_symlinks(target/name)
                h=hashlib.sha256()
                with path.open('rb') as f:
                    while block := f.read(1024*1024): h.update(block)
                if h.hexdigest()!=entry['sha256']:
                    raise RuntimeError('artifact changed since download')
                tar.add(path,arcname=PREFIX+'/'+name,recursive=False)
        archive.chmod(0o600)
        life.lease('immich')
        with archive.open('rb') as source:
            result=subprocess.run(['kubectl','-n','proof-immich','exec','-i','deployment/ml','--','python','-c',"import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall('/cache',filter='data')"],stdin=source,capture_output=True,timeout=600)
        if result.returncode:
            raise RuntimeError('proof-only model preload failed; no output emitted')
        print('Pinned model artifacts preloaded into fresh proof ML cache; inference not yet implied.')


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print('Model preparation stopped: '+type(e).__name__)
        raise SystemExit(1)
