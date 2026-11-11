#!/usr/bin/env python3
"""Fetch only SHA256-locked public bootstrap artifacts. Never accesses cluster."""
import hashlib,json,os,sys,urllib.request
from pathlib import Path
lock=Path(__file__).with_name('artifacts.lock.json')
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
for item in json.loads(lock.read_text())['artifacts']:
    target=out/item['file']
    data=target.read_bytes() if target.exists() else urllib.request.urlopen(item['url'],timeout=60).read()
    if hashlib.sha256(data).hexdigest()!=item['sha256']:
        raise SystemExit('Checksum mismatch: '+item['file'])
    target.write_bytes(data)
    print(item['file']+' verified')
