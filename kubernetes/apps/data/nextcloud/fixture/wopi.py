#!/usr/bin/env python3
"""Bounded concurrent single-document WOPI fixture, NOT Nextcloud/conformance.
No raw request logging: WOPI carries secrets in query strings.
"""
import io
import zipfile
import xml.etree.ElementTree as ET
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit

MAX_BYTES = 1024 * 1024
INITIAL = b'Synthetic WOPI proof document\n'


def odt():
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        archive.writestr('mimetype','application/vnd.oasis.opendocument.text',compress_type=zipfile.ZIP_STORED)
        archive.writestr('content.xml','<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:text><text:p>Synthetic Nextcloud Office proof</text:p></office:text></office:body></office:document-content>')
        archive.writestr('META-INF/manifest.xml','<?xml version="1.0"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>')
    return buffer.getvalue()


def document_marker(data, format, marker):
    if format == "txt": return marker.encode() in data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.read("mimetype") != b"application/vnd.oasis.opendocument.text":
            raise ValueError("not an ODT document")
        content = ET.fromstring(archive.read("content.xml"))
    return marker in "".join(content.itertext())


class Host:
    def __init__(self, root, token, format="txt"):
        if not token:
            raise ValueError('fresh private proof token required')
        self.token = token
        if format not in ('txt','odt'): raise ValueError('unsupported fixture format')
        self.format = format
        self.path = Path(root) / ('proof.' + format)
        if not self.path.exists(): self.path.write_bytes(odt() if format=='odt' else INITIAL)
        self.lock = ''
        self.lock_expires = 0
        self.events = []
        self.requests = []
        self.mutex = threading.RLock()

    def event(self, name):
        with self.mutex:
            self.events.append(name)
            self.events = self.events[-128:]

    def current_lock(self):
        with self.mutex:
            if time.monotonic() > self.lock_expires: self.lock = ''
            return self.lock

    def version(self):
        with self.mutex: return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def evidence(self):
        with self.mutex:
            data = self.path.read_bytes()
            return {'events':list(self.events),'requests':list(self.requests),
                    'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
                    'format':self.format,
                    'marker_present':document_marker(data,self.format,'WOPI-SAVED-')}

    def record(self, event, status, size):
        with self.mutex:
            self.requests.append({'event':event,'status':status,'bytes':size})
            self.requests = self.requests[-128:]
            # Independent failure-path capture: no token/lock values/file bytes.
            path = self.path.parent / 'evidence.json'
            temp = path.with_suffix('.partial')
            temp.write_text(json.dumps(self.evidence()))
            temp.replace(path)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, address, handler_class):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address,handler_class)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            try: request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally: self.shutdown_request(request)
            return
        try: super().process_request(request,address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try: super().process_request_thread(request,address)
        finally: self.slots.release()

    def handle_error(self, request, address):
        pass  # no raw token-bearing request/traceback output


def handler(host):
    class WOPI(BaseHTTPRequestHandler):
        server_version = 'ProofWOPI'
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(5)
            self.completed = 0
            self.operation = 'request'

        def log_message(self, *args): pass

        def reply(self, status, body=b'', headers=None, close=False):
            if isinstance(body,dict):
                body=json.dumps(body).encode()
                headers=dict(headers or {}, **{'Content-Type':'application/json'})
            self.completed += 1
            if close or self.completed>=32: self.close_connection=True
            host.record(self.operation,status,len(body))
            self.send_response(status)
            for key,value in (headers or {}).items(): self.send_header(key,value)
            self.send_header('Content-Length',str(len(body)))
            if self.close_connection: self.send_header('Connection','close')
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            supplied=parse_qs(urlsplit(self.path).query).get('access_token',[''])[0]
            return hmac.compare_digest(supplied,host.token)

        def framing(self):
            if self.headers.get('Transfer-Encoding') is not None:
                self.reply(501,close=True); return None
            try: length=int(self.headers.get('Content-Length','0'))
            except ValueError:
                self.reply(400,close=True); return None
            if not 0<=length<=MAX_BYTES:
                self.reply(413,close=True); return None
            return length

        def handle_expect_100(self):
            self.operation='ExpectContinue'
            if not self.authorized(): self.reply(401,close=True); return False
            if self.framing() is None: return False
            self.send_response_only(100); self.end_headers()
            return True

        def conflict(self):
            host.event('lock-conflict')
            self.reply(409,headers={'X-WOPI-Lock':host.current_lock()})

        def do_GET(self):
            path=urlsplit(self.path).path
            self.operation='health' if path=='/healthz' else 'Get'
            if path=='/healthz': return self.reply(200,b'ok')
            if not self.authorized(): return self.reply(401,close=True)
            with host.mutex:
                if path=='/wopi/files/proof':
                    self.operation='CheckFileInfo';host.event(self.operation)
                    return self.reply(200,{'BaseFileName':host.path.name,'OwnerId':'synthetic-owner',
                        'UserId':'synthetic-editor','UserFriendlyName':'Synthetic Editor',
                        'Size':host.path.stat().st_size,'Version':host.version(),
                        'UserCanWrite':True,'ReadOnly':False,'SupportsUpdate':True,
                        'SupportsLocks':True,'SupportsGetLock':True,
                        'PostMessageOrigin':'https://collabora.proof.invalid'})
                if path=='/wopi/files/proof/contents':
                    self.operation='GetFile';host.event(self.operation)
                    return self.reply(200,host.path.read_bytes(),{'X-WOPI-ItemVersion':host.version()})
                if path=='/proof/evidence': return self.reply(200,host.evidence())
            return self.reply(404)

        def do_POST(self):
            path=urlsplit(self.path).path
            op=self.headers.get('X-WOPI-Override','')
            self.operation='PutFile' if path=='/wopi/files/proof/contents' else (op if op in ('GET_LOCK','LOCK','REFRESH_LOCK','UNLOCK') else 'unsupported')
            if not self.authorized(): return self.reply(401,close=True)
            length=self.framing()
            if length is None: return
            # Read bounded body OUTSIDE state lock: a stalled upload must not
            # block health/evidence/other clients. Every accepted POST is drained.
            try: data=self.rfile.read(length)
            except (TimeoutError,OSError): return self.reply(408,close=True)
            if len(data)!=length: return self.reply(400,close=True)
            lock=self.headers.get('X-WOPI-Lock','')
            with host.mutex:
                active=host.current_lock()
                if path=='/wopi/files/proof/contents':
                    if not active or lock!=active: return self.conflict()
                    temp=host.path.with_suffix('.partial');temp.write_bytes(data);temp.replace(host.path)
                    host.event('PutFile')
                    return self.reply(200,headers={'X-WOPI-ItemVersion':host.version()})
                if path!='/wopi/files/proof': return self.reply(404)
                if op=='GET_LOCK':
                    host.event('GetLock');return self.reply(200,headers={'X-WOPI-Lock':active})
                if op not in ('LOCK','REFRESH_LOCK','UNLOCK'): return self.reply(501)
                if not lock or len(lock)>1024: return self.reply(400)
                old=self.headers.get('X-WOPI-OldLock')
                if op=='LOCK':
                    if (old is not None and active!=old) or (old is None and active and active!=lock): return self.conflict()
                    host.lock=lock;host.lock_expires=time.monotonic()+1800
                elif not active or active!=lock: return self.conflict()
                elif op=='UNLOCK': host.lock='';host.lock_expires=0
                else: host.lock_expires=time.monotonic()+1800
                host.event(op);return self.reply(200)
    return WOPI


if __name__=='__main__':
    os.umask(0o077)
    Server(('0.0.0.0',8082),handler(Host('/data',os.environ['NEXTCLOUD_ADMIN_PASSWORD'],os.environ.get('PROOF_WOPI_FORMAT','txt')))).serve_forever(poll_interval=.2)
