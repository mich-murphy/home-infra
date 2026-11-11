#!/usr/bin/env python3
"""Offline native v12.4 contract regressions; mocks are NOT live acceptance."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
j = importlib.import_module('talos-proof-media-jellyfin')


class Jellyfin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name).resolve()
        self.guard = patch.object(j, 'check'); self.guard.start()
        self.marker = {'owner_id':'owner','outsider_id':'other','item_id':'movie','library_id':'library',
                       'runtime_ticks':120210000,'resume_ticks':82000000,'resume_settings':{'MinResumeDurationSeconds':1},
                       'outsider_credentials':'outsider.json','media_path':'/Videos/movie/stream.mp4?static=true'}
        self.session = {'marker':self.marker,'headers':{'X-Emby-Token':'OFFLINE-TOKEN'},'media_source':'native-source','play_session':'native-session'}
        j.s.write_private(self.state/'session.json', json.dumps(self.session))
        self.bridge = {'service':'jellyfin','state':str(self.state),'ca':'/unused','group':'jellyfin','session_file':'session.json'}
    def tearDown(self):
        self.guard.stop(); self.tmp.cleanup()
    def test_native_start_progress_stop_and_exact_session(self):
        api = Mock();api.last_status = 204
        def reply(path,*args):
            if path.startswith('/Sessions?'):
                if stopped[0]: return [{'DeviceId':j.DEVICE,'UserId':'owner','NowPlayingItem':None}]
                return [{'DeviceId':j.DEVICE,'UserId':'owner','NowPlayingItem':{'Id':'movie'},'PlayState':{'IsPaused':False}}]
            return None
        api.call.side_effect = reply
        stopped = [False]
        with patch.object(j, 'api_for', return_value=api):
            for phase, position in [('start',100),('progress',1500),('progress',8000),('stop',8200)]:
                stopped[0] = phase == 'stop'
                answer = j.callback(self.bridge, {'phase':phase,'state':'stopped' if stopped[0] else 'playing','time':position,'duration':12021})
                self.assertEqual(answer, {'stopped':True} if stopped[0] else {'active':True})
        posts = [c for c in api.call.call_args_list if len(c.args)>1]
        self.assertEqual([c.args[0] for c in posts], ['/Sessions/Playing','/Sessions/Playing/Progress','/Sessions/Playing/Progress','/Sessions/Playing/Stopped'])
        for call in posts:
            self.assertEqual(call.args[2]['PlaySessionId'], 'native-session')
            self.assertEqual(call.args[2]['MediaSourceId'], 'native-source')
            if call.args[0].endswith('/Stopped'):
                self.assertNotIn('PlayMethod',call.args[2])
            else:
                self.assertEqual(call.args[2]['PlayMethod'], 'DirectPlay')
        self.assertEqual(len(list(self.state.glob('session.json.progress*.json'))), 2)
    def test_wrong_client_or_paused_cannot_be_active(self):
        for device, paused in [('other-device',False),(j.DEVICE,True)]:
            api = Mock();api.last_status = 204
            api.call.side_effect = [None,[{'DeviceId':device,'UserId':'owner','NowPlayingItem':{'Id':'movie'},'PlayState':{'IsPaused':paused}}]]
            with patch.object(j, 'api_for', return_value=api), self.assertRaisesRegex(RuntimeError, 'differs'):
                j.callback(self.bridge, {'phase':'start','state':'playing','time':100,'duration':12021})
    def test_stop_without_real_progress_or_bad_group_refused_before_api(self):
        with patch.object(j, 'api_for') as api:
            with self.assertRaises((FileNotFoundError,RuntimeError)):
                j.callback(self.bridge, {'phase':'stop','state':'stopped','time':8200,'duration':12021})
            with self.assertRaises(RuntimeError):
                j.callback(dict(self.bridge,group='media-plex-jellyplex'), {})
            api.assert_not_called()
    def test_verify_existing_resume_before_playback_or_configuration_writes(self):
        j.s.write_private(self.state/'done.json', json.dumps(self.marker))
        for lost in (False,True):
            api = Mock();api.call.side_effect = [{'MinResumeDurationSeconds':1},[{'ItemId':'library'}],
                {'UserData':{'Played':False,'PlaybackPositionTicks':0 if lost else 82000000}},
                {'Items':[{'Id':'movie','UserData':{'PlaybackPositionTicks':82000000}}]}]
            with patch.object(j,'owner',return_value=(api,'owner')), patch.object(j,'stream') as stream, patch.object(j,'acl') as acl:
                if lost:
                    with self.assertRaisesRegex(RuntimeError,'persisted resume'):
                        j.verify(self.state,Path('/unused'),Path('/unused'), 'done.json')
                    stream.assert_not_called();acl.assert_not_called()
                else:
                    j.verify(self.state,Path('/unused'),Path('/unused'), 'done.json')
                    stream.assert_called_once();acl.assert_called_once()
            self.assertTrue(all(len(c.args)==1 for c in api.call.call_args_list))
    def test_acl_requires_authenticated_denial_not_missing_token(self):
        for code in (401,403,404,500):
            with self.subTest(code=code):
                def denied(): raise urllib.error.HTTPError('https://offline.invalid',code,'',{},None)
                if code in (403,404):j.deny(denied)
                else:
                    with self.assertRaises(RuntimeError):j.deny(denied)
        with self.assertRaisesRegex(RuntimeError,'unexpectedly readable'):j.deny(lambda: b'content')
    def test_resume_consumes_prior_marker_before_native_playback_info(self):
        api = Mock();api.headers = {'X-Emby-Token':'OFFLINE'}
        api.call.return_value = {'PlaySessionId':'native-issued','MediaSources':[{'Id':'source'}]}
        with patch.object(j,'verify',return_value=self.marker) as verify, patch.object(j,'owner',return_value=(api,'owner')):
            bridge = j.prepare_bridge(self.state, Path('/unused'), Path('/unused'), 'prior.json')
        verify.assert_called_once_with(self.state,Path('/unused'),Path('/unused'),'prior.json')
        self.assertEqual(bridge['resume_seconds'],8.2)
        self.assertEqual(api.call.call_args.args[2]['StartTimeTicks'],82000000)
        record = j.read_record(self.state,bridge['session_file'])
        self.assertEqual(record['play_session'],'native-issued')
    def test_near_end_or_no_actual_decoder_is_not_resume_pass(self):
        with self.assertRaises(RuntimeError):
            j.finish(self.state, Path('/unused'),Path('/unused'),self.bridge,{'timeline_activity_observed':False})
        j.s.write_private(self.state/'session.json.stop.json', json.dumps({'position_ticks':115000000}))
        with self.assertRaisesRegex(RuntimeError,'too near end'):
            j.finish(self.state,Path('/unused'),Path('/unused'),self.bridge,{'timeline_activity_observed':True,'timeline_stopped':True})
        self.assertEqual(len(list(self.state.glob('jellyfin-browser-functional-*'))),0)


if __name__ == '__main__': unittest.main()
