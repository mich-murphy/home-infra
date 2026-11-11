#!/usr/bin/env python3
"""Offline real-player bridge regressions; mocks do not prove Plex/Tautulli."""
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
p = importlib.import_module('talos-proof-media-playback')
b = importlib.import_module('talos-proof-media-browser')


class Playback(unittest.TestCase):
    def test_same_client_session_timeline_and_activity_identity(self):
        bridge = {'state': '/unused', 'ca': '/unused/ca', 'group': 'media-plex-tautulli',
                  'item': '7', 'client': 'client-proof', 'session': 'session-proof'}
        event = {'state': 'playing', 'time': 1200, 'duration': 12021}
        for machine, state, expected in [('client-proof', 'playing', True), ('other-client', 'playing', False),
                                         ('client-proof', 'stopped', False)]:
            plex = Mock(); plex.headers = {}
            with patch.object(b, 'check_lease') as guard, patch.object(p.s, 'private_dir', return_value=Path('/unused')), \
                 patch.object(p.s, 'private_file', return_value=Path('/unused/ca')), \
                 patch.object(p.s, 'read_private', side_effect=[json.dumps({'tautulli':{}}), json.dumps({'item_id':'7'})]), \
                 patch.object(p.d, 'api_for', return_value=plex), \
                 patch.object(p, 'tautulli_call', return_value={'sessions':[{'rating_key':'7','machine_id':machine,'state':state}]}):
                self.assertEqual(p.callback({'bridge':bridge,'event':event}), {'active':expected})
            guard.assert_called_once_with('plex', 'media-plex-tautulli')
            self.assertEqual(plex.headers['X-Plex-Client-Identifier'], bridge['client'])
            self.assertEqual(plex.headers['X-Plex-Session-Identifier'], bridge['session'])
            url = plex.call.call_args.args[0]
            self.assertIn('session=session-proof', url)
            self.assertIn('time=1200', url)

    def test_bad_group_no_connection(self):
        with patch.object(p.d, 'api_for') as api:
            with self.assertRaises(RuntimeError):
                p.callback({'bridge': {'group': 'plex'}, 'event': {}})
            api.assert_not_called()

    def test_ended_decoder_and_legacy_sequential_workflow_cannot_pass(self):
        source = (ROOT / 'tests/talos-proof-media-player.mjs').read_text()
        self.assertIn('video.paused || video.ended || video.currentTime<=at', source)
        self.assertIn("await report('stopped')", source)
        self.assertIn("if(!activity) throw", source)
        with self.assertRaisesRegex(RuntimeError, 'legacy sequential timeline gate retired'):
            p.d.tautulli()
        with patch.object(p.s, 'read_private') as read:
            with self.assertRaises(RuntimeError):
                p.finish(Path('/unused'), '/unused', {}, {'timeline_activity_observed': False})
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
