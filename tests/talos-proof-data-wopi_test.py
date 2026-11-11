#!/usr/bin/env python3
"""Offline WOPI fixture protocol regressions; never connects to proof API."""
import io
import zipfile
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import socket
import time
import unittest
from http.server import HTTPServer

spec = importlib.util.spec_from_file_location('fixture',Path(__file__).resolve().parents[1]/'kubernetes/apps/data/nextcloud/fixture/wopi.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class WOPIProtocol(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.host = fixture.Host(self.directory.name,'synthetic-offline-token')
        self.server = fixture.Server(('127.0.0.1',0),fixture.handler(self.host))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.directory.cleanup()

    def request(self,method='GET',suffix='',op=None,lock=None,body=None,token='synthetic-offline-token',headers=None):
        h = dict(headers or {})
        if op: h['X-WOPI-Override']=op
        if lock: h['X-WOPI-Lock']=lock
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        c.request(method,'/wopi/files/proof'+suffix+'?access_token='+token,body,h)
        r=c.getresponse();value=(r.status,dict(r.getheaders()),r.read());c.close();return value

    def test_native_odt_info_lock_save_and_reopen_offline(self):
        self.host = fixture.Host(self.directory.name,'synthetic-offline-token','odt')
        self.server.RequestHandlerClass = fixture.handler(self.host)
        info=json.loads(self.request()[2])
        self.assertEqual(info['BaseFileName'],'proof.odt')
        original=self.request(suffix='/contents')[2]
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            first=archive.infolist()[0]
            self.assertEqual((first.filename,first.compress_type),('mimetype',zipfile.ZIP_STORED))
            self.assertEqual(archive.read('mimetype'),b'application/vnd.oasis.opendocument.text')
            members={n:archive.read(n) for n in archive.namelist()}
        marker='WOPI-SAVED-offline-protocol-only'
        # This is an offline fixture protocol test, NOT evidence of CODE editing.
        members['content.xml']=members['content.xml'].replace(b'Synthetic Nextcloud Office proof',marker.encode())
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            for name,data in members.items():archive.writestr(name,data)
        saved=output.getvalue()
        self.assertEqual(self.request('POST',op='LOCK',lock='editor')[0],200)
        self.assertEqual(self.request('POST','/contents',lock='wrong',body=saved)[0],409)
        self.assertEqual(self.host.path.read_bytes(),original)
        self.assertEqual(self.request('POST','/contents',lock='editor',body=saved)[0],200)
        self.assertTrue(fixture.document_marker(self.request(suffix='/contents')[2],'odt',marker))
        reopened=fixture.Host(self.directory.name,'synthetic-offline-token','odt')
        self.assertEqual(reopened.path.read_bytes(),saved)
        self.assertTrue(reopened.evidence()['marker_present'])
        self.assertEqual(self.request(token='wrong')[0],401)

    def test_odt_marker_must_be_in_content_xml_not_zip_metadata(self):
        marker='WOPI-SAVED-decoy'
        output=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(fixture.odt())) as original, zipfile.ZipFile(output,'w') as target:
            for name in original.namelist():target.writestr(name,original.read(name))
            target.writestr('styles.xml',marker)
            target.comment=marker.encode()
        self.assertFalse(fixture.document_marker(output.getvalue(),'odt',marker))
        with self.assertRaises(zipfile.BadZipFile):fixture.document_marker(b'not odt','odt',marker)
        with self.assertRaises(ValueError):fixture.Host(self.directory.name,'token','docx')

    def test_token_required_for_info_read_and_write(self):
        for method,suffix,op in [('GET','',None),('GET','/contents',None),('POST','','LOCK'),('POST','/contents',None)]:
            self.assertEqual(self.request(method,suffix,op,lock='a',token='wrong')[0],401)
        self.assertEqual(self.host.path.read_bytes(),fixture.INITIAL)

    def test_info_read_actual_bytes_version(self):
        status,headers,body=self.request()
        info=json.loads(body)
        self.assertEqual(status,200);self.assertTrue(info['SupportsLocks']);self.assertTrue(info['UserCanWrite'])
        self.assertEqual(info['Version'],hashlib.sha256(fixture.INITIAL).hexdigest())
        self.assertEqual(self.request(suffix='/contents')[2],fixture.INITIAL)

    def test_unlocked_nonempty_put_is_refused(self):
        self.assertEqual(self.request('POST','/contents',body=b'illegal')[0],409)
        self.assertEqual(self.host.path.read_bytes(),fixture.INITIAL)

    def test_real_lock_save_refresh_unlock(self):
        self.assertEqual(self.request('POST',op='LOCK',lock='editor')[0],200)
        self.assertEqual(self.request('POST',op='REFRESH_LOCK',lock='editor')[0],200)
        status,headers,_=self.request('POST','/contents',lock='editor',body=b'Saved marker\n')
        self.assertEqual(status,200)
        self.assertEqual(headers['X-WOPI-ItemVersion'],hashlib.sha256(b'Saved marker\n').hexdigest())
        self.assertEqual(self.request(suffix='/contents')[2],b'Saved marker\n')
        self.assertEqual(self.request('POST',op='UNLOCK',lock='editor')[0],200)
        self.assertEqual(self.host.events,['LOCK','REFRESH_LOCK','PutFile','GetFile','UNLOCK'])

    def test_lock_conflicts_report_held_lock(self):
        self.request('POST',op='LOCK',lock='one')
        for op in ['LOCK','REFRESH_LOCK','UNLOCK']:
            status,h,_=self.request('POST',op=op,lock='two')
            self.assertEqual(status,409);self.assertEqual(h['X-WOPI-Lock'],'one')
        self.assertEqual(self.request('POST','/contents',lock='two',body=b'wrong')[0],409)

    def test_get_lock_and_unlock_relock(self):
        self.request('POST',op='LOCK',lock='one')
        self.assertEqual(self.request('POST',op='GET_LOCK')[1]['X-WOPI-Lock'],'one')
        self.assertEqual(self.request('POST',op='LOCK',lock='two',headers={'X-WOPI-OldLock':'wrong'})[0],409)
        self.assertEqual(self.request('POST',op='LOCK',lock='two',headers={'X-WOPI-OldLock':'one'})[0],200)
        self.assertEqual(self.host.lock,'two')

    def test_expired_lock_and_unknown_operation_fail_closed(self):
        self.request('POST',op='LOCK',lock='old');self.host.lock_expires=0
        self.assertEqual(self.request('POST',op='REFRESH_LOCK',lock='old')[0],409)
        self.assertEqual(self.request('POST',op='RENAME_FILE',lock='old')[0],501)
        self.assertEqual(self.request(suffix='/wrong')[0],404)

    def test_payload_bound_and_missing_lock(self):
        self.assertEqual(self.request('POST',op='LOCK')[0],400)
        self.request('POST',op='LOCK',lock='editor')
        self.assertEqual(self.request('POST','/contents',lock='editor',body=b'',headers={'Content-Length':str(fixture.MAX_BYTES+1)})[0],413)
        self.assertEqual(self.host.path.read_bytes(),fixture.INITIAL)

    def test_expect_continue_upload_handshake(self):
        self.request('POST',op='LOCK',lock='editor')
        with socket.create_connection(('127.0.0.1',self.server.server_port),timeout=2) as sock:
            stream=sock.makefile('rb')
            sock.sendall(b'POST /wopi/files/proof/contents?access_token=synthetic-offline-token HTTP/1.1\r\nHost: localhost\r\nX-WOPI-Lock: editor\r\nExpect: 100-continue\r\nContent-Length: 4\r\nConnection: close\r\n\r\n')
            self.assertIn(b'100 Continue',stream.readline())
            self.assertEqual(stream.readline(),b'\r\n')
            sock.sendall(b'save')
            self.assertIn(b'200 OK',stream.readline())
        self.assertEqual(self.host.path.read_bytes(),b'save')

    def test_stalled_post_does_not_block_evidence_or_other_clients(self):
        with socket.create_connection(('127.0.0.1',self.server.server_port),timeout=2) as stalled:
            stalled.sendall(b'POST /wopi/files/proof/contents?access_token=synthetic-offline-token HTTP/1.1\r\nHost: localhost\r\nContent-Length: 100\r\n\r\nx')
            started=time.monotonic()
            self.assertEqual(self.request()[0],200)
            self.assertLess(time.monotonic()-started,1.5)

    def test_http11_persistent_connection_drains_post_body(self):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
        target='/wopi/files/proof?access_token=synthetic-offline-token'
        c.request('POST',target,b'drained',{'X-WOPI-Override':'LOCK','X-WOPI-Lock':'one'})
        first=c.getresponse();self.assertEqual(first.status,200);first.read();sock=c.sock
        c.request('GET',target);second=c.getresponse()
        self.assertEqual(second.status,200);second.read();self.assertIs(c.sock,sock);c.close()

    def test_failure_evidence_is_persisted_without_token_or_lock(self):
        self.request('POST',op='LOCK',lock='private-lock')
        self.request('POST','/contents',lock='wrong-lock',body=b'not-saved')
        raw=(Path(self.directory.name)/'evidence.json').read_text()
        self.assertNotIn('synthetic-offline-token',raw);self.assertNotIn('private-lock',raw)
        record=json.loads(raw)
        self.assertIn('lock-conflict',record['events'])
        self.assertEqual(record['requests'][-1]['status'],409)
        self.assertFalse(record['marker_present'])


if __name__=='__main__':
    unittest.main()
