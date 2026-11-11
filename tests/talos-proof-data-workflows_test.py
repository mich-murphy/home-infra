#!/usr/bin/env python3
"""Offline workflow regression tests; fakes are not live application evidence."""
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('data_live', Path(__file__).with_name('talos-proof-data-live.py'))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class Workflows(unittest.TestCase):
    def setUp(self):
        live.RESULT = {'checks':[], 'limitations':[]}
        live.CREDS = {'COUCHDB_PASSWORD':'offline-only', 'ADMIN_PASSWORD':'offline-only'}

    def test_private_archive_is_exclusive_and_mode0600(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(live, 'STATEPATH', Path(directory)), patch.object(live, 'LIFE') as life:
                life.no_symlinks.side_effect = lambda path:path
                path = live.save_private_new('archive.json', b'first')
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                with self.assertRaises(FileExistsError):
                    live.save_private_new('archive.json', b'overwritten')
                self.assertEqual(path.read_bytes(), b'first')

    def test_negative_requires_exact_http_status(self):
        for status in (401, 403, 409):
            error = urllib.error.HTTPError('https://proof.invalid', status, '', {}, None)
            with patch.object(live, 'http', side_effect=error):
                live.expect_http('expected', status, 'https://proof.invalid', '/')
                with self.assertRaises(RuntimeError):
                    live.expect_http('wrong', 404, 'https://proof.invalid', '/')
        with patch.object(live, 'http', return_value={}):
            with self.assertRaises(RuntimeError):
                live.expect_http('no denial', 403, 'https://proof.invalid', '/')

    def test_replication_is_loopback_bounded_and_nonpersistent(self):
        db = 'proof_' + 'a'*32
        payload = live.couch_replication(db, db+'_replica', 'user:private')
        self.assertFalse(payload['continuous'])
        self.assertFalse(payload['create_target'])
        self.assertEqual(payload['doc_ids'], ['document', 'deleted'])
        for endpoint in ('source','target'):
            self.assertTrue(payload[endpoint]['url'].startswith('http://127.0.0.1:5984/proof_'))
            self.assertIn('Authorization', payload[endpoint]['headers'])
        for invalid in ('production', 'http://example.com', db+'/../other'):
            with self.assertRaises(RuntimeError):
                live.couch_replication(invalid, db+'_replica', 'private')

    def test_couch_documents_normalizes_only_revision_and_sorts_design(self):
        docs = [{'_id':'z', '_rev':'1-a', 'nested':{'_rev':'preserve'}}, {'_id':'_design/proof', '_rev':'2-b', 'views':{}}]
        with patch.object(live, 'http', return_value={'rows':[{'doc':d} for d in docs]}):
            actual = live.couch_documents('https://proof.invalid', 'proof_db', 'private')
        self.assertEqual(actual, [{'_id':'_design/proof', 'views':{}}, {'_id':'z', 'nested':{'_rev':'preserve'}}])

    def test_miniflux_workflow_preserves_star_preferences_and_content(self):
        entry = {'id':7, 'title':'Proof article', 'content':'Synthetic proof content', 'status':'unread', 'starred':False}
        user = {'id':1, 'theme':'light_serif', 'entries_per_page':100}
        original = copy.deepcopy(user)
        calls = []
        def http(base, path, method='GET', body=None, auth=None, **kwargs):
            calls.append((path,method,copy.deepcopy(body)))
            if path=='/healthcheck': return b'OK'
            if path=='/v1/categories': return {'id':2}
            if path=='/v1/feeds': return {'feed_id':3}
            if path=='/v1/feeds/3/entries': return {'entries':[copy.deepcopy(entry)]}
            if path=='/v1/me': return copy.deepcopy(user)
            if path=='/v1/users/1':
                self.assertIn(body['theme'], ('dark_serif','light_serif'))
                user.update(body)
                return copy.deepcopy(user)
            if path=='/v1/entries/7/bookmark': entry['starred']=not entry['starred']; return b''
            if path=='/v1/entries': entry['status']=body['status']; return b''
            if path=='/v1/entries/7': return copy.deepcopy(entry)
            if path=='/v1/feeds/3': return {'id':3}
            if path=='/v1/categories/2' and method=='DELETE': return b''
            raise AssertionError((path,method))
        saved = {}
        def dump(_):
            saved.update(entry=copy.deepcopy(entry), user=copy.deepcopy(user))
            return b'offline-dump'
        @contextlib.contextmanager
        def fresh(*args):
            source_entry, source_user = copy.deepcopy(entry), copy.deepcopy(user)
            entry.clear(); user.clear()
            yield
            entry.clear(); entry.update(source_entry)
            user.clear(); user.update(source_user)
        def restore(*args):
            entry.update(saved['entry']); user.update(saved['user'])
        with patch.object(live, 'http', side_effect=http), patch.object(live, 'forwarded', side_effect=lambda *a:contextlib.nullcontext('https://miniflux.proof.invalid')), patch.object(live, 'restart'), patch.object(live, 'scale'), patch.object(live, 'fresh_pvc', side_effect=fresh), patch.object(live, 'postgres_dump', side_effect=dump), patch.object(live, 'clean_postgres_restore', side_effect=restore), patch.object(live, 'authenticated_recovery', side_effect=http):
            live.miniflux()
        self.assertEqual(user, original)
        self.assertTrue(saved['entry']['starred'])
        self.assertNotEqual(saved['user']['theme'], original['theme'])
        self.assertIn('Miniflux theme/page-size preferences match after clean-PVC restore', live.RESULT['checks'])
        self.assertEqual(sum(path.endswith('/bookmark') for path,_,_ in calls),1)


if __name__ == '__main__':
    unittest.main()
