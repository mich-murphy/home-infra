#!/usr/bin/env python3
"""Test actual QEMU-forwarded NodePorts with trusted TLS, not service port-forward."""
import os, subprocess
from pathlib import Path
import proof_guard
proof_guard.check()
if os.environ.get('PROOF_TESTS_AUTHORIZED') != 'yes':raise SystemExit('Explicit authorization required')
k=['python3',str(Path(__file__).with_name('proof_guard.py')),'--context',os.environ['PROOF_CONTEXT']]
ca=Path(os.environ['PROOF_GATEWAY_CA'])
expected=subprocess.check_output(k+['-n','proof-network-test','exec','deploy/fixture','--','cat','/data/www/index.html'],text=True).strip()
def request(host,port,tls=False,trust=True,warmup=False):
    args=['curl','--silent','--show-error','--max-time','15','--noproxy','*','--resolve',f'{host}:{port}:127.0.0.1','-w','\n%{http_code}\n']
    if tls and trust:args+=['--cacert',str(ca)]
    if warmup:args+=['--fail','--retry','6','--retry-delay','1','--retry-max-time','30']
    return subprocess.run(args+[f'{"https" if tls else "http"}://{host}:{port}/'],text=True,capture_output=True)
for port,tls in [(18080,False),(18443,True)]:
    r=request('fixture.proof.invalid',port,tls,warmup=True)
    if r.stderr:print('Bounded Gateway programming warmup:',r.stderr.strip())
    assert r.returncode==0,(r.returncode,r.stderr)
    body,status=r.stdout.rsplit('\n',2)[:2];assert status=='200' and body.strip()==expected,r.stdout
    print(f'PASS {"trusted HTTPS" if tls else "HTTP"} actual NodePort forward localhost:{port} status={status} body={body.strip()}')
for port,tls in [(18080,False),(18443,True)]:
    r=request('unmatched.proof.invalid',port,tls);assert r.returncode==0,r.stderr
    status=r.stdout.strip().splitlines()[-1];assert status=='404',r.stdout
    print(f'PASS unmatched hostname no route localhost:{port} status={status}')
r=request('fixture.proof.invalid',18443,True,False);assert r.returncode==60,(r.returncode,r.stdout,r.stderr)
print('PASS untrusted CA rejected curl exit60')
r=request('outside.invalid',18443,True);assert r.returncode in (35,60),(r.returncode,r.stdout,r.stderr)
print(f'PASS outside listener SNI rejected (TLS handshake/hostname failure) curl exit{r.returncode}')
