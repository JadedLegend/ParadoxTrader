"""CLI control/readiness tests: no providers, credentials, sockets, or schedulers."""
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('rehearsal_cli_under_test', ROOT / 'scripts' / 'rehearsal.py')
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


class RehearsalCLITests(unittest.TestCase):
    def test_repository_run_roots_are_rejected(self):
        for path in (ROOT, ROOT / 'rehearsal-runs', ROOT / 'data' / 'rehearsals'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                cli.root_path(path)

    def test_offline_manifest_does_not_load_private_config_or_fetch_catalog(self):
        with mock.patch.dict(os.environ, {'OPENROUTER_API_KEY': 'ambient-key-must-not-be-used'}), \
             mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')):
            manifest = cli.manifest_for()
        self.assertEqual(manifest['mode'], 'offline')
        self.assertEqual(set(manifest['agent_models']), set(cli.OWNERS))
        self.assertNotIn('ambient-key', json.dumps(manifest))
        self.assertEqual(manifest['limits']['wakes_per_agent'], 2)
        self.assertEqual(manifest['limits']['max_requests'], 28)

    def test_real_manifest_requires_explicit_model_and_budget_inputs(self):
        with self.assertRaises(ValueError):
            cli.manifest_for('real')

    def test_explicit_file_json_is_bounded(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'too-large.json'
            path.write_bytes(b'x' * (4 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                cli.read_json(path)

    def test_status_stop_and_start_parser_do_not_arm_real_models_implicitly(self):
        for command in ['start', 'resume']:
            parsed = cli.parser().parse_args([command, '12345678-1234-4234-8234-123456789abc'])
            self.assertFalse(parsed.allow_real_models)
        self.assertEqual(cli.parser().parse_args(['prepare']).mode, 'offline')
