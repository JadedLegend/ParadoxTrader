"""AST-isolated communication gates: no app startup or actual stores."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest import mock

from tests.test_agent_loop import OfflineCase, config, loop
from tests.test_lineage_api import HTTPException
from core.runtime.community import get_community_policy

SOURCE = Path(__file__).resolve().parents[1] / 'api' / 'app.py'
NAMES = {'_require_community_access', 'get_forum_posts', 'post_to_forum', 'get_threads', 'send_dm'}


def handlers(forum, messaging):
    nodes = [copy.deepcopy(n) for n in ast.parse(SOURCE.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    for node in nodes:
        node.decorator_list = []
    values = {'HTTPException': HTTPException, 'Optional': Optional,
              'ForumPostRequest': SimpleNamespace, 'DMRequest': SimpleNamespace,
              'get_community_policy': get_community_policy, 'AGENTS': loop.AGENTS,
              'get_forum': lambda: forum, 'get_messaging': lambda: messaging}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SOURCE), 'exec'), values)
    return values


class CommunityAPITests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.runtime = {'current_phase': 0, 'community': {'forum_open': False, 'peer_messages_open': False}}
        self.patch(config, 'get_runtime_config', side_effect=lambda: self.runtime)
        self.forum_api = mock.Mock()
        self.dm_api = mock.Mock()
        self.routes = handlers(self.forum_api, self.dm_api)
        self.post = SimpleNamespace(author='tempest', content='A voluntary contribution', thread_id='general', reply_to=None, tags=[])

    def assert_denied(self, name, *args):
        with self.assertRaises(HTTPException) as raised:
            self.routes[name](*args)
        self.assertEqual((raised.exception.status_code, raised.exception.detail), (403, 'community_access_closed'))

    def test_phase_advance_never_opens_forum_or_peer_writes(self):
        for phase in (0, 1, 2, 3):
            self.runtime['current_phase'] = phase
            self.assert_denied('get_forum_posts')
            self.assert_denied('get_threads')
            self.assert_denied('post_to_forum', self.post)
            self.assert_denied('send_dm', SimpleNamespace(sender='shadow', recipient='siren', content='Why?'))
        self.forum_api.assert_not_called()
        self.forum_api.post.assert_not_called()
        self.dm_api.send.assert_not_called()

    def test_open_forum_does_not_open_peer_messages_or_portfolio_sharing(self):
        self.runtime = {'current_phase': 1, 'community': {'forum_open': True}}
        self.routes['post_to_forum'](self.post)
        self.forum_api.post.assert_called_once()
        self.assert_denied('send_dm', SimpleNamespace(sender='shadow', recipient='siren', content='Question'))
        self.assertFalse(get_community_policy(self.runtime)['share_peer_positions'])
        self.dm_api.send.assert_not_called()

    def test_open_gates_still_require_non_solo_phase(self):
        self.runtime['community'] = {'forum_open': True, 'peer_messages_open': True, 'share_peer_positions': True}
        self.assert_denied('post_to_forum', self.post)
        self.assert_denied('send_dm', SimpleNamespace(sender='shadow', recipient='siren', content='Question'))
        self.runtime['current_phase'] = 1
        self.routes['send_dm'](SimpleNamespace(sender='shadow', recipient='siren', content='Question'))
        self.dm_api.send.assert_called_once_with(sender='shadow', recipient='siren', content='Question')

    def test_user_correspondence_is_available_before_peer_access(self):
        for sender, recipient in [('user', 'tempest'), ('siren', 'user')]:
            self.routes['send_dm'](SimpleNamespace(sender=sender, recipient=recipient, content='A private invitation'))
        self.assertEqual(self.dm_api.send.call_count, 2)

    def test_unknown_participants_cannot_bypass_peer_gate(self):
        for sender, recipient in [('outsider', 'tempest'), ('tempest', 'outsider')]:
            with self.assertRaises(HTTPException) as raised:
                self.routes['send_dm'](SimpleNamespace(sender=sender, recipient=recipient, content='No'))
            self.assertEqual(raised.exception.status_code, 404)
        self.dm_api.send.assert_not_called()
