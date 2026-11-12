"""Isolated operator-only rehearsal inspection; never imports the broad app.

Construct with create_app(private_root, operator_token=...) or supply the
server-only LINEAGE_OPERATOR_TOKEN. This module cannot prepare/start a run.
"""
from contextlib import contextmanager
import hmac
import os
from pathlib import Path
import re
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

AGENTS = frozenset(('tempest', 'siren', 'alchemist', 'weaver', 'oracle', 'shadow', 'paradox_hunter'))
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
LIMIT_FIELDS = ('wakes_per_agent', 'max_requests', 'max_output_tokens', 'max_input_bytes',
                'max_runtime_seconds', 'request_timeout_seconds', 'max_parallelism', 'budget_usd')
SUMMARY_FIELDS = ('run_id', 'mode', 'status', 'created_at', 'started_at', 'ended_at', 'stop_requested',
                  'request_count', 'reserved_usd', 'known_cost_usd', 'unknown_cost_requests',
                  'reported_cost_usd', 'estimated_cost_usd')
JOB_FIELDS = ('wake_id', 'agent_id', 'round', 'status', 'action', 'failure_code', 'requested_model',
              'response_model', 'provider', 'request_count', 'duration_ms', 'updated_at')
REQUEST_FIELDS = ('request_id', 'wake_id', 'agent_id', 'activity', 'model', 'requested_model',
                  'response_model', 'provider', 'outcome', 'duration_ms', 'input_bytes',
                  'max_output_tokens', 'reserved_usd', 'failure_code', 'created_at', 'submitted_at', 'finished_at')
USAGE_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens',
                'cost_usd', 'reported_cost_usd', 'estimated_cost_usd', 'cost_status', 'cost_source')


def _error(status, code):
    raise HTTPException(status_code=status, detail=code) from None


def _project(value, fields):
    return {key: value[key] for key in fields if key in value}


def _summary(value):
    result = _project(value, SUMMARY_FIELDS)
    result['limits'] = _project(value['limits'], LIMIT_FIELDS)
    result['agent_models'] = {agent: model for agent, model in value['agent_models'].items() if agent in AGENTS}
    result['agents'] = [_project(agent, ('agent_id', 'pending', 'completed', 'failed', 'stopped', 'uncertain'))
                        for agent in value['agents'] if agent['agent_id'] in AGENTS]
    result['capabilities'] = [cap for cap in value['capabilities'] if cap in ('rest', 'journal', 'inquire', 'library', 'roam')]
    return result


def _job(value):
    result = _project(value, JOB_FIELDS)
    result['record_refs'] = [_project(ref, ('kind', 'id')) for ref in value.get('record_refs', [])
                             if ref.get('kind') in ('journal', 'episode', 'inquiry', 'library')]
    return result


def _request(value):
    result = _project(value, REQUEST_FIELDS)
    usage = value.get('usage')
    if not isinstance(usage, dict) and any(field in value for field in USAGE_FIELDS):
        usage = value  # Existing actual-store events project coverage fields flat.
    result['usage'] = _project(usage, USAGE_FIELDS) if isinstance(usage, dict) else None
    return result


def _params(request, allowed):
    params = request.query_params
    if any(key not in allowed or len(params.getlist(key)) != 1 for key in params):
        _error(400, 'invalid_rehearsal_request')
    return params


def _integer(params, key, default, minimum, maximum):
    value = params.get(key)
    if value is None:
        return default
    if not re.fullmatch(r'[0-9]{1,10}', value) or not minimum <= int(value) <= maximum:
        _error(400, 'invalid_rehearsal_request')
    return int(value)


def _owner(params, required=False):
    owner = params.get('agent_id')
    if (required or owner is not None) and owner not in AGENTS:
        _error(404, 'rehearsal_agent_not_found')
    return owner


def _uuid(value):
    if not isinstance(value, str) or not UUID.fullmatch(value):
        _error(400, 'invalid_rehearsal_request')
    return value


def _store(root):
    # Lazy import only after auth/validation. No provider/controller is imported.
    from core.runtime.rehearsal.store import RehearsalStore
    return RehearsalStore(root)


def _safe_file(run_path, relative):
    base = Path(run_path).resolve(strict=True)
    candidate = base / relative
    # Reject links in every component, not merely links pointing outside the run.
    part = base
    for component in Path(relative).parts:
        part = part / component
        if part.is_symlink():
            _error(404, 'rehearsal_record_not_found')
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(base) or not resolved.is_file():
        _error(404, 'rehearsal_record_not_found')
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(candidate) + suffix).is_symlink():
            _error(404, 'rehearsal_record_not_found')
    return resolved


@contextmanager
def _read_connection(path):
    conn = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA query_only=ON')
        yield conn
    finally:
        conn.close()


def _inquiry(path, inquiry_id, owner):
    # Reuse existing LineageStore ownership and bounded detail reads, but replace
    # its schema-creating transaction with an explicitly read-only connection.
    from core.trading.lineage import LineageStore, LineageAccessError, LineageNotFound

    class ReadOnlyLineageStore(LineageStore):
        def _connection(self):
            return _read_connection(self.db_path)

    try:
        value = ReadOnlyLineageStore(path).get_inquiry(inquiry_id, viewer_agent_id=owner, phase=0, operator=False)
        if value['inquiry']['agent_id'] != owner:
            _error(404, 'rehearsal_record_not_found')
        return value
    except (LineageAccessError, LineageNotFound):
        _error(404, 'rehearsal_record_not_found')


def _record_selection(params):
    owner = _owner(params, required=True)
    kind, record_id = params.get('kind'), params.get('id')
    if kind not in ('journal', 'episode', 'inquiry', 'library') or record_id is None:
        _error(400, 'invalid_rehearsal_request')
    if kind == 'inquiry':
        _uuid(record_id)
    elif kind == 'library':
        if not re.fullmatch(r'doc-[0-9a-f]{12}-s[0-9]{5}', record_id):
            _error(400, 'invalid_rehearsal_request')
    elif not re.fullmatch(r'[1-9][0-9]{0,9}', record_id) or int(record_id) > 2**31 - 1:
        _error(400, 'invalid_rehearsal_request')
    return owner, kind, record_id


def _record(store, run_id, params):
    owner, kind, record_id = _record_selection(params)
    # Run-local reference plus selected owner prevents cross-owner integer ID
    # collisions, arbitrary memory enumeration and unrelated inquiry UUID reads.
    jobs = store.list_jobs(run_id)
    if not any(job['agent_id'] == owner and any(ref.get('kind') == kind and str(ref.get('id')) == record_id
               for ref in job.get('record_refs', [])) for job in jobs):
        _error(404, 'rehearsal_record_not_found')
    run_path = store.run_path(run_id)
    if kind == 'inquiry':
        value = _inquiry(_safe_file(run_path, 'trade_queue.sqlite3'), record_id, owner)
    elif kind == 'library':
        path = _safe_file(run_path, 'library.sqlite3')
        with _read_connection(path) as conn:
            row = conn.execute('SELECT section_id,document_id,locator,text FROM library_sections WHERE section_id=? LIMIT 1', (record_id,)).fetchone()
        if row is None:
            _error(404, 'rehearsal_record_not_found')
        value = dict(row)
        value['truncated'] = len(value['text']) > 1200
        value['text'] = value['text'][:1200]
    else:
        path = _safe_file(run_path, f'memory/{owner}.sqlite3')
        table, columns = ('journal', 'id,content,phase,created_at') if kind == 'journal' else ('episodes', 'id,title,content,phase,created_at')
        with _read_connection(path) as conn:
            row = conn.execute(f'SELECT {columns} FROM {table} WHERE id=? LIMIT 1', (int(record_id),)).fetchone()
        if row is None:
            _error(404, 'rehearsal_record_not_found')
        value = dict(row)
        value['truncated'] = len(value['content']) > 12000
        value['content'] = value['content'][:12000]
    return {'run_id': run_id, 'agent_id': owner, 'kind': kind,
            'id': int(record_id) if kind in ('journal', 'episode') else record_id, 'record': value}


def create_app(root, operator_token=None):
    """Create an idle, GET-only ASGI app. Does not inspect root or open a store."""
    app = FastAPI(title='Read-only rehearsal inspection', docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def protect(request, call_next):
        token = operator_token if operator_token is not None else os.environ.get('LINEAGE_OPERATOR_TOKEN', '')
        try:
            expected = ('Bearer ' + token).encode('utf-8') if isinstance(token, str) and token.strip() else None
            supplied = request.headers.get('authorization', '').encode('utf-8')
        except UnicodeError:
            expected, supplied = None, b''
        if expected is None:
            return JSONResponse({'detail': 'rehearsal_operator_unavailable'}, status_code=503, headers={'Cache-Control': 'private, no-store'})
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse({'detail': 'rehearsal_operator_required'}, status_code=403, headers={'Cache-Control': 'private, no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def read(callback):
        try:
            return callback()
        except HTTPException:
            raise
        except (FileNotFoundError, KeyError):
            _error(404, 'rehearsal_not_found')
        except ValueError as exc:
            if str(exc) in ('run not found', 'job not found'):
                _error(404, 'rehearsal_not_found')
            _error(400, 'invalid_rehearsal_request')
        except Exception:
            # Never echo provider/store exception text, filesystem paths or keys.
            _error(503, 'rehearsal_unavailable')

    @app.get('/api/rehearsals')
    def runs(request: Request):
        params = _params(request, ('limit', 'offset'))
        limit = _integer(params, 'limit', 20, 1, 20)
        offset = _integer(params, 'offset', 0, 0, 1_000_000)
        def fetch():
            value = _store(root).list_runs(limit=limit, offset=offset)
            return {'runs': [_summary(run) for run in value['runs']], 'total': value['total'], 'limit': limit, 'offset': offset}
        return read(fetch)

    @app.get('/api/rehearsals/{run_id}')
    def run(run_id: str, request: Request):
        _uuid(run_id)
        _params(request, ())
        return read(lambda: _summary(_store(root).get_run(run_id)))

    @app.get('/api/rehearsals/{run_id}/jobs')
    def jobs(run_id: str, request: Request):
        _uuid(run_id)
        owner = _owner(_params(request, ('agent_id',)))
        def fetch():
            values = _store(root).list_jobs(run_id)
            return {'run_id': run_id, 'jobs': [_job(job) for job in values if job['agent_id'] in AGENTS and (owner is None or job['agent_id'] == owner)]}
        return read(fetch)

    @app.get('/api/rehearsals/{run_id}/requests')
    def requests(run_id: str, request: Request):
        _uuid(run_id)
        params = _params(request, ('limit', 'offset', 'agent_id'))
        owner = _owner(params)
        limit = _integer(params, 'limit', 50, 1, 50)
        offset = _integer(params, 'offset', 0, 0, 1_000_000)
        def fetch():
            value = _store(root).list_requests(run_id, limit=limit, offset=offset, agent_id=owner)
            # Do not trust an adapter accidentally returning another owner's rows.
            if any(event['agent_id'] not in AGENTS or (owner and event['agent_id'] != owner) for event in value['events']):
                _error(503, 'rehearsal_unavailable')
            return {'run_id': run_id, 'events': [_request(event) for event in value['events']], 'total': value['total'], 'limit': limit, 'offset': offset}
        return read(fetch)

    @app.get('/api/rehearsals/{run_id}/records')
    def records(run_id: str, request: Request):
        _uuid(run_id)
        params = _params(request, ('agent_id', 'kind', 'id'))
        # Owner validation precedes constructing even the read-only store.
        _record_selection(params)
        return read(lambda: _record(_store(root), run_id, params))

    return app
