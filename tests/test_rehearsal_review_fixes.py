"""Focused review fixes: no real HTTP, account keys, server, or scheduler."""
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from core.runtime.rehearsal.store import RehearsalStore, RehearsalError, RehearsalStopped
from core.runtime.rehearsal.provider import OpenRouterTransport, ProviderError
from core.runtime.rehearsal.controller import RehearsalController, snapshot_profiles, _run_file
from tests.test_rehearsal_provider import manifest, Response
from scripts import rehearsal as cli


class ReviewFixTests(unittest.TestCase):
    def test_known_wrong_returned_model_fails_without_replaying_or_applying(self):
        with TemporaryDirectory() as tmp, mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
            store = RehearsalStore(tmp)
            run_id = store.prepare(manifest('real'))['run_id']
            token = store.begin(run_id)
            job = store.claim_job(run_id, 'tempest-r1', token)
            calls = []
            def post(*args, **kwargs):
                calls.append(1)
                return Response(model='different/wrong-model', usage={'cost': '0.003', 'prompt_tokens': 3, 'completion_tokens': 2})
            transport = OpenRouterTransport('explicit-test-key', http_post=post, is_live=True)
            with self.assertRaises(ProviderError) as raised:
                transport.generate(store=store, run_id=run_id, token=token, wake_id=job['wake_id'], agent_id='tempest',
                                   activity='choice', messages=[{'role': 'user', 'content': 'bounded'}])
            self.assertEqual(str(raised.exception), 'returned_model_mismatch')
            self.assertEqual(len(calls), 1)
            event = store.list_requests(run_id)['events'][0]
            self.assertEqual(event['response_model'], 'different/wrong-model')
            self.assertEqual(event['cost_usd'], '0.003')
            self.assertNotEqual(event['outcome'], 'success')
            self.assertIsNone(store.get_choice(run_id, job['wake_id']))

    def test_stop_between_reservation_and_dispatch_does_not_enter_http(self):
        with TemporaryDirectory() as tmp:
            store = RehearsalStore(tmp)
            run_id = store.prepare(manifest('real'))['run_id']
            token = store.begin(run_id)
            job = store.claim_job(run_id, 'tempest-r1', token)
            reserve = store.reserve_request
            def stop_after_reserve(*args, **kwargs):
                request_id = reserve(*args, **kwargs)
                store.request_stop(run_id)
                return request_id
            post = mock.Mock(side_effect=AssertionError('HTTP must not be entered after pre-dispatch stop'))
            transport = OpenRouterTransport('explicit-test-key', http_post=post, is_live=True)
            with mock.patch.object(store, 'reserve_request', side_effect=stop_after_reserve), self.assertRaises(RehearsalStopped):
                transport.generate(store=store, run_id=run_id, token=token, wake_id=job['wake_id'], agent_id='tempest',
                                   activity='choice', messages=[{'role': 'user', 'content': 'bounded'}])
            post.assert_not_called()
            self.assertEqual(store.list_requests(run_id)['events'][0]['outcome'], 'not_sent')

    def test_usage_symlinks_and_sidecars_are_rejected_before_any_http_or_external_write(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = RehearsalStore(root / 'runs')
            run_id = store.prepare(manifest('real'))['run_id']
            token = store.begin(run_id)
            job = store.claim_job(run_id, 'tempest-r1', token)
            external = root / 'external'
            external.write_bytes(b'original bytes must stay intact')
            for suffix in ['', '-wal', '-shm', '-journal']:
                path = store.run_path(run_id) / ('usage.sqlite3' + suffix)
                path.symlink_to(external)
                post = mock.Mock(side_effect=AssertionError('No HTTP for an unsafe file'))
                transport = OpenRouterTransport('explicit-test-key', http_post=post, is_live=True)
                with self.assertRaises(RehearsalError):
                    transport.generate(store=store, run_id=run_id, token=token, wake_id=job['wake_id'], agent_id='tempest',
                                       activity='choice', messages=[{'role': 'user', 'content': 'bounded'}])
                post.assert_not_called()
                self.assertEqual(external.read_bytes(), b'original bytes must stay intact')
                path.unlink()

    def test_disappearing_normal_sqlite_sidecar_is_not_a_safety_violation(self):
        with TemporaryDirectory() as tmp:
            store = RehearsalStore(tmp)
            run_id = store.prepare(manifest())['run_id']
            main = store.run_path(run_id) / 'control.sqlite3'
            sidecar = Path(str(main) + '-journal')
            exists, is_file = Path.exists, Path.is_file
            def stale_exists(path):
                return True if path == sidecar else exists(path)
            def disappeared_file(path):
                return False if path == sidecar else is_file(path)
            with mock.patch.object(Path, 'exists', stale_exists), mock.patch.object(Path, 'is_file', disappeared_file):
                self.assertEqual(store.safe_run_file(run_id, 'control.sqlite3'), main)

    def test_prompt_assets_are_frozen_before_run_and_not_rebuilt_on_restart(self):
        with TemporaryDirectory() as tmp:
            store = RehearsalStore(tmp)
            run_id = store.prepare(manifest())['run_id']
            snapshot_profiles(store, run_id)
            from core.runtime.rehearsal.examples import ScriptedHTTP
            controller = RehearsalController(store, run_id, transport=OpenRouterTransport('offline-test-key', http_post=ScriptedHTTP()))
            initial = controller._system_prompt('tempest')
            with mock.patch('core.runtime.rehearsal.controller._prompt_builder', side_effect=AssertionError('Do not rebuild a frozen prompt')):
                snapshot_profiles(store, run_id)
                self.assertEqual(controller._system_prompt('tempest'), initial)
            self.assertTrue((store.run_path(run_id) / 'profiles' / 'tempest_prompt.txt').exists())

    def test_sqlite_sidecar_symlink_is_rejected_before_controller_store_open(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / 'run'
            run.mkdir()
            external = root / 'external'
            external.write_text('original')
            for suffix in ['-wal', '-shm', '-journal']:
                sidecar = run / ('memory.sqlite3' + suffix)
                sidecar.symlink_to(external)
                with self.assertRaises(RehearsalError):
                    _run_file(run, 'memory.sqlite3')
                self.assertEqual(external.read_text(), 'original')
                sidecar.unlink()

    def test_recovery_parser_requires_explicit_operator_acknowledgement(self):
        no = cli.parser().parse_args(['recover', '77777777-7777-4777-8777-777777777777'])
        yes = cli.parser().parse_args(['recover', '77777777-7777-4777-8777-777777777777', '--confirm-controller-exited'])
        self.assertFalse(no.confirm_controller_exited)
        self.assertTrue(yes.confirm_controller_exited)
