#!/usr/bin/env python3
"""Explicit bounded rehearsal control; default mode is credential-free offline.

No server, schedule, account feed, broker, or ordinary agent wake is started.
Actual model calls require a prepared real manifest, --allow-real-models, and
REHEARSAL_OPENROUTER_API_KEY. Never use a browser key or an ambient Manus key.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
# PARADOX_SESSIONS_ROOT is the same variable the private dashboard reads, so runs
# started on the VPS land where the dashboard and the backups look.
DEFAULT_ROOT = Path(os.environ.get('PARADOX_SESSIONS_ROOT')
                    or Path.home() / '.local' / 'share' / 'paradoxtrader' / 'rehearsals')
OWNERS = ('tempest', 'siren', 'alchemist', 'weaver', 'oracle', 'shadow', 'paradox_hunter')
LIMITS = {'wakes_per_agent': 2, 'max_requests': 28, 'max_output_tokens': 1024,
          'max_input_bytes': 24000, 'max_runtime_seconds': 900,
          'request_timeout_seconds': 60, 'max_parallelism': 3}


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('input_file_too_large')
    return json.loads(path.read_text(encoding='utf-8'))


def selected_models(path=None):
    if path:
        data = read_json(path)
        return data.get('agent_models', data) if isinstance(data, dict) else data
    # Shipped public examples only: no YAML/private config loader or env mutation.
    data = read_json(REPO / 'frontend' / 'src' / 'preview' / 'fixtures.json')
    return {row['agent_id']: row['model'] for row in data['agents']}


def manifest_for(mode='offline', *, models_file=None, catalog_file=None, fetch_catalog=False, budget_usd=None):
    from core.runtime.rehearsal.provider import catalog_snapshot, validate_manifest
    if mode == 'real' and (not models_file or budget_usd is None):
        raise ValueError('real_prepare_requires_explicit_models_and_budget')
    models = selected_models(models_file)
    if mode == 'real':
        if bool(catalog_file) == bool(fetch_catalog):
            raise ValueError('real_prepare_requires_one_catalog_source')
        if fetch_catalog:
            # Public catalog GET only; no authorization header or paid inference.
            import requests
            response = requests.get('https://openrouter.ai/api/v1/models', timeout=20, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError('catalog_unavailable')
            if len(response.content) > 4 * 1024 * 1024:
                raise ValueError('catalog_too_large')
            catalog = response.json()
        else:
            catalog = read_json(catalog_file)
        if isinstance(catalog, dict) and catalog.get('synthetic') is True:
            raise ValueError('synthetic_catalog_not_for_real_prepare')
    else:
        from core.runtime.rehearsal.examples import synthetic_catalog
        catalog = synthetic_catalog(models)
        if catalog_file or fetch_catalog:
            raise ValueError('offline_prepare_uses_synthetic_catalog_only')
    manifest = {'schema_version': 1, 'mode': mode, 'agent_models': models,
                'limits': {**LIMITS, 'budget_usd': budget_usd if budget_usd is not None else '10.00'},
                'catalog_snapshot': catalog_snapshot(models, catalog),
                'capabilities': ['rest', 'journal', 'inquire', 'library', 'roam']}
    return validate_manifest(manifest)


def root_path(raw):
    root = Path(raw).expanduser().absolute()
    resolved = root.resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise ValueError('rehearsal_root_must_be_outside_repository')
    return root


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default=str(DEFAULT_ROOT), help='Private run root outside the repository')
    commands = p.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Create isolated records; no model calls')
    prepare.add_argument('--mode', choices=['offline', 'real'], default='offline')
    prepare.add_argument('--models-file')
    prepare.add_argument('--catalog-file')
    prepare.add_argument('--fetch-catalog', action='store_true', help='Explicit public catalog GET, not inference')
    prepare.add_argument('--budget-usd')
    prepare.add_argument('--run-id')
    prepare.add_argument('--continues-from', help='Earlier finished run in this root whose memory and witness carry forward')
    for command in ['start', 'resume', 'stop', 'status', 'recover']:
        child = commands.add_parser(command)
        child.add_argument('run_id')
        if command in ['start', 'resume']:
            child.add_argument('--allow-real-models', action='store_true', help='Explicit paid-session arming; does not grant trading permission')
        if command == 'recover':
            child.add_argument('--confirm-controller-exited', action='store_true', help='Explicitly acknowledge the old process is gone; uncertain requests will not be resent')
    commands.add_parser('list')
    serve = commands.add_parser('serve', help='Explicit localhost read-only API; no scheduler or model startup')
    serve.add_argument('--port', type=int, default=8765)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    from core.runtime.rehearsal.store import RehearsalStore
    store = RehearsalStore(root_path(args.root))
    if args.command == 'serve':
        if not 1024 <= args.port <= 65535:
            raise ValueError('invalid_read_server_port')
        token = os.environ.get('LINEAGE_OPERATOR_TOKEN', '')
        if not token or not token.strip():
            raise ValueError('read_operator_token_missing')
        from api.rehearsal import create_app
        import uvicorn
        uvicorn.run(create_app(root_path(args.root), operator_token=token), host='127.0.0.1',
                    port=args.port, log_level='warning', access_log=False)
        return 0
    if args.command == 'prepare':
        manifest = manifest_for(args.mode, models_file=args.models_file, catalog_file=args.catalog_file,
                                fetch_catalog=args.fetch_catalog, budget_usd=args.budget_usd)
        if args.continues_from:
            # Check the earlier run before creating anything for the new one.
            from core.runtime.rehearsal.home import CARRIED_STATUSES
            previous = store.get_run(args.continues_from)
            if previous['status'] not in CARRIED_STATUSES:
                raise ValueError('home_previous_run_not_finished')
            if previous['mode'] != manifest['mode']:
                raise ValueError('home_mode_mismatch')
        summary = store.prepare(manifest, run_id=args.run_id)
        home = None
        if args.continues_from:
            # Carry first: preparing profiles creates this run's own inquiry store.
            from core.runtime.rehearsal.home import continue_home
            home = continue_home(store, summary['run_id'], args.continues_from)
        from core.runtime.rehearsal.controller import snapshot_profiles
        snapshot_profiles(store, summary['run_id'], REPO)
        result = store.get_run(summary['run_id'])
        if home is not None:
            result['home'] = home
    elif args.command == 'list':
        result = store.list_runs()
    elif args.command == 'status':
        result = store.get_run(args.run_id)
    elif args.command == 'stop':
        result = store.request_stop(args.run_id)
    elif args.command == 'recover':
        if not args.confirm_controller_exited:
            raise ValueError('recovery_not_acknowledged')
        result = store.recover(args.run_id)
    else:
        from core.runtime.rehearsal.provider import OpenRouterTransport
        from core.runtime.rehearsal.controller import RehearsalController
        manifest = store.get_manifest(args.run_id)
        if manifest['mode'] == 'real':
            if not args.allow_real_models:
                raise ValueError('real_model_session_not_armed')
            key = os.environ.get('REHEARSAL_OPENROUTER_API_KEY', '')
            if not key or not key.strip():
                raise ValueError('dedicated_rehearsal_key_missing')
            transport = OpenRouterTransport(key)
            result = RehearsalController(store, args.run_id, transport=transport, repo_root=REPO).run(resume=args.command == 'resume')
        else:
            from core.runtime.rehearsal.examples import ScriptedHTTP
            transport = OpenRouterTransport('offline-scripted-not-a-credential', http_post=ScriptedHTTP())
            with ExitStack() as blocked:
                for target, method in [(socket, 'create_connection'), (socket.socket, 'connect'), (socket.socket, 'connect_ex')]:
                    blocked.enter_context(mock.patch.object(target, method, side_effect=AssertionError('Offline rehearsal forbids networking')))
                result = RehearsalController(store, args.run_id, transport=transport, repo_root=REPO).run(resume=args.command == 'resume')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Never expose headers, keys, provider bodies or raw transport exceptions.
        safe_codes = {'real_model_session_not_armed', 'dedicated_rehearsal_key_missing',
                      'real_prepare_requires_explicit_models_and_budget', 'real_prepare_requires_one_catalog_source',
                      'synthetic_catalog_not_for_real_prepare', 'rehearsal_root_must_be_outside_repository',
                      'recovery_not_acknowledged', 'read_operator_token_missing', 'invalid_read_server_port',
                      'home_previous_run_not_finished', 'home_mode_mismatch'}
        code = str(exc) if isinstance(exc, ValueError) and str(exc) in safe_codes else 'rehearsal_operation_failed'
        print(json.dumps({'error': code, 'type': type(exc).__name__, 'automatic_retry': False}), file=sys.stderr)
        raise SystemExit(1)
