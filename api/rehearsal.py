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
              'response_model', 'provider', 'request_count', 'duration_ms', 'updated_at',
              'decision_context', 'selection_origin')
REQUEST_FIELDS = ('request_id', 'wake_id', 'agent_id', 'activity', 'model', 'requested_model',
                  'response_model', 'provider', 'outcome', 'duration_ms', 'input_bytes',
                  'max_output_tokens', 'reserved_usd', 'failure_code', 'created_at', 'submitted_at', 'finished_at', 'finish_reason')
USAGE_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens',
                'cost_usd', 'reported_cost_usd', 'estimated_cost_usd', 'cost_status', 'cost_source')


def _error(status, code):
    raise HTTPException(status_code=status, detail=code) from None


def _project(value, fields):
    return {key: value[key] for key in fields if key in value}


def _decision_metadata(value):
    """Strict nested public projection: no arbitrary private source fields."""
    actions = ('rest', 'journal', 'inquire', 'library', 'roam')
    def number(item):
        return type(item) is int and 0 <= item <= 1_000_000_000
    def string(item):
        return isinstance(item, str) and len(item) <= 256
    def decimal(item):
        return string(item) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', item) is not None
    def obj(item, fields):
        if not isinstance(item, dict) or any(key not in item or not check(item[key]) for key, check in fields.items()):
            raise ValueError('invalid decision metadata')
        return _project(item, fields)
    if value is None:
        return None
    try:
        if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
            return None
        offered, costs = value['offered_actions'], value['action_costs']
        if not isinstance(offered, list) or not offered or len(offered) > 5 or any(action not in actions for action in offered) or len(set(offered)) != len(offered):
            return None
        if not isinstance(costs, list) or len(costs) > 5:
            return None
        costs = [obj(cost, {'action': lambda item: item in actions, 'max_requests': number,
                            'reservation_ceiling_usd': decimal, 'basis': lambda item: item == 'catalog_upper_bound'}) for cost in costs]
        if sorted(cost['action'] for cost in costs) != sorted(offered):
            return None
        constraints = obj(value['constraints'], {field: decimal if field == 'budget_usd' else number for field in LIMIT_FIELDS})
        snapshot = obj(value['admission_snapshot'], {'reserved_usd': decimal, 'remaining_budget_usd': decimal,
                       'request_count': number, 'remaining_requests': number, 'is_reservation': lambda item: item is False})
        model = obj(value['model'], {'requested_model': string, 'context_length': number,
                                     'max_completion_tokens': number, 'catalog_source': lambda item: item is None or string(item)})
        continuity = obj(value['continuity'], {'status': lambda item: item in ('empty', 'available', 'included', 'unavailable', 'truncated', 'partial', 'failed'),
                                              'refs': lambda item: isinstance(item, list) and len(item) <= 100,
                                              'truncated': lambda item: type(item) is bool, 'chars': number})
        refs = []
        for ref in continuity['refs']:
            if not isinstance(ref, dict) or ref.get('kind') not in ('journal', 'episode', 'inquiry', 'library'):
                return None
            if not (string(ref.get('id')) or number(ref.get('id'))):
                return None
            projected = _project(ref, ('kind', 'id', 'wake_id', 'agent_id'))
            if any(not string(projected[key]) for key in ('wake_id', 'agent_id') if key in projected):
                return None
            refs.append(projected)
        continuity['refs'] = refs
        return {'schema_version': 1, 'offered_actions': list(offered), 'action_costs': costs,
                'constraints': constraints, 'admission_snapshot': snapshot, 'model': model, 'continuity': continuity}
    except (KeyError, TypeError, ValueError):
        return None


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
    if 'decision_context' in result:
        result['decision_context'] = _decision_metadata(result['decision_context'])
    if 'selection_origin' in result and result['selection_origin'] not in (None, 'none', 'model'):
        result['selection_origin'] = None
    if value.get('action') == 'journal':
        if value.get('journal_mode') in ('note', 'compost', 'distill', 'witness'):
            result['journal_mode'] = value['journal_mode']
        channels = value.get('channels')
        if (value.get('journal_mode') != 'witness' and isinstance(channels, list) and 1 <= len(channels) <= 3
                and all(isinstance(channel, str) and channel in ('trading', 'idea', 'orientation', 'unclassified') for channel in channels)
                and len(set(channels)) == len(channels)
                and ('unclassified' not in channels or channels == ['unclassified'])):
            result['channels'] = list(channels)
    result['record_refs'] = []
    for ref in value.get('record_refs', []):
        if not isinstance(ref, dict):
            continue
        if ref.get('kind') == 'witness':
            if (value.get('agent_id') not in AGENTS or not _owner_wake(value['agent_id'], value.get('wake_id'))
                    or not isinstance(ref.get('id'), str) or not UUID.fullmatch(ref['id'])
                    or ref.get('agent_id', value['agent_id']) != value['agent_id']):
                continue
        elif ref.get('kind') not in ('journal', 'episode', 'inquiry', 'library'):
            continue
        result['record_refs'].append(_project(ref, ('kind', 'id')))
    return result


def _request(value):
    result = _project(value, REQUEST_FIELDS)
    usage = value.get('usage')
    if not isinstance(usage, dict) and any(field in value for field in USAGE_FIELDS):
        usage = value  # Existing actual-store events project coverage fields flat.
    result['usage'] = _project(usage, USAGE_FIELDS) if isinstance(usage, dict) else None
    return result
PRIVATE_FIELDS = frozenset(('continuity', 'include_metadata', 'include_continuity', 'status', 'refs',
    'truncated', 'chars', 'excerpts', 'unavailable', 'records', 'kind', 'id', 'wake_id', 'agent_id',
    'body', 'content', 'source', 'account_kind', 'body_truncated', 'inquiry_id', 'title', 'state',
    'title_source', 'title_truncated', 'latest_entry', 'entry_status', 'entry_id', 'created_at', 'record',
    'earlier_run_id', 'earlier_wake_id'))
def _private_context(value, owner, depth=0):
    if depth > 12:
        _error(404, 'rehearsal_decision_not_found')
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, list):
        return [_private_context(item, owner, depth + 1) for item in value]
    if not isinstance(value, dict):
        _error(404, 'rehearsal_decision_not_found')
    if ('agent_id' in value and value['agent_id'] != owner or
            'wake_id' in value and not _owner_wake(owner, value['wake_id']) or
            value.get('kind') == 'innermost'):
        _error(404, 'rehearsal_decision_not_found')
    return {key: _private_context(item, owner, depth + 1) for key, item in value.items() if key in PRIVATE_FIELDS}
def _decision_request(value, owner, wake_id):
    if not isinstance(value, dict) or value.get('agent_id') != owner or value.get('wake_id') != wake_id:
        _error(404, 'rehearsal_decision_not_found')
    result = _request(value)
    result.update(_project(value, ('input_sha256', 'input_coverage', 'input_status', 'context_status')))
    if 'messages' in value:
        messages = value['messages']
        if messages is not None:
            if not isinstance(messages, list) or any(not isinstance(message, dict) or
                    message.get('role') not in ('system', 'user', 'assistant', 'tool') or
                    not isinstance(message.get('content'), str) for message in messages):
                _error(404, 'rehearsal_decision_not_found')
            messages = [_project(message, ('role', 'content')) for message in messages]
        result['messages'] = messages
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


MAX_WAKES_PER_AGENT = 48


def _owner_wake(owner, wake):
    """True when ``wake`` is one of ``owner``'s wake IDs: ``<owner>-r<n>``, 1 <= n <= 48."""
    if not isinstance(owner, str) or not isinstance(wake, str) or not wake.startswith(owner + '-r'):
        return False
    number = wake[len(owner) + 2:]
    return bool(re.fullmatch(r'[1-9][0-9]?', number)) and int(number) <= MAX_WAKES_PER_AGENT


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
    class ReadOnlyRehearsalStore(RehearsalStore):
        def _connection(self, run_id, *, write=False):
            if write:
                raise RuntimeError('read-only inspection')
            return _read_connection(self._db_path(run_id))
    return ReadOnlyRehearsalStore(root)


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
    if kind not in ('journal', 'episode', 'inquiry', 'library', 'witness') or record_id is None:
        _error(400, 'invalid_rehearsal_request')
    if kind in ('inquiry', 'witness'):
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
    elif kind == 'witness':
        from core.runtime.rehearsal.witness import WitnessStore
        matching = [job for job in jobs if job.get('agent_id') == owner and
                    any(ref.get('kind') == 'witness' and ref.get('id') == record_id for ref in job.get('record_refs', []))]
        if any(not _owner_wake(owner, job.get('wake_id')) for job in matching):
            _error(404, 'rehearsal_record_not_found')
        account = WitnessStore(store.safe_run_file(run_id, 'witness.sqlite3')).get_account(record_id, owner)
        if account is None or account.get('id') != record_id:
            _error(404, 'rehearsal_record_not_found')
        value = _witness_account(account, owner)
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


CHANNELS = ('trading', 'idea', 'orientation', 'unclassified')


def _journal_note(value, owner):
    """Known literal source fields only, never an arbitrary private wrapper."""
    if not isinstance(value, dict):
        _error(503, 'rehearsal_unavailable')
    channels, sources = value.get('channels'), value.get('source_ids')
    wake = value.get('source_wake_id')
    if (value.get('author') != owner or value.get('agent_id', owner) != owner
            or type(value.get('id')) is not int or not 1 <= value['id'] <= 2**31 - 1
            or not isinstance(value.get('content'), str)
            or not isinstance(value.get('created_at'), str)
            or not isinstance(channels, list) or not 1 <= len(channels) <= 3
            or any(channel not in CHANNELS for channel in channels)
            or len(set(channels)) != len(channels)
            or ('unclassified' in channels and channels != ['unclassified'])
            or value.get('note_kind') not in ('note', 'compost', 'distillation')
            or value.get('state') not in ('active', 'released')
            or 'source_mode' not in value or value['source_mode'] not in ('real', 'offline', None)
            or 'source_wake_id' not in value
            or (wake is not None and not _owner_wake(owner, wake))
            or not isinstance(sources, list) or len(sources) > 20
            or any(type(source) is not int or not 1 <= source <= 2**31 - 1 for source in sources)
            or len(set(sources)) != len(sources)):
        _error(503, 'rehearsal_unavailable')
    result = _project(value, ('id', 'channels', 'note_kind', 'state', 'author', 'source_mode',
                              'created_at', 'source_wake_id', 'source_ids'))
    result['content'] = value['content'][:12000]
    result['truncated'] = value.get('truncated') is True or len(value['content']) > 12000
    return result


def _journal_sources(store, run_id, owner, channel, state, limit, offset):
    if channel not in ('idea', 'trading') or state == 'released':
        return [], 'not_applicable'
    path = store.safe_run_file(run_id, 'trade_queue.sqlite3')
    if not path.is_file():
        return [], 'missing'
    # Only source inquiries actually referenced by this owner's exact run wakes.
    ids = set()
    for job in store.list_jobs(run_id):
        if job.get('agent_id') != owner:
            continue
        if not _owner_wake(owner, job.get('wake_id')):
            _error(503, 'rehearsal_unavailable')
        for ref in job.get('record_refs', []):
            if ref.get('kind') == 'inquiry' and isinstance(ref.get('id'), str) and UUID.fullmatch(ref['id']):
                ids.add(ref['id'])
    with _read_connection(path) as conn:
        tables = {row['name'] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('lineage_inquiries','lineage_proposals') LIMIT 2")}
        if 'lineage_inquiries' not in tables or channel == 'trading' and 'lineage_proposals' not in tables:
            return [], 'missing'
        if not ids:
            return [], 'ok'
        ids = sorted(ids)[:256]
        where = 'i.agent_id=? AND i.inquiry_id IN (' + ','.join('?' for _ in ids) + ')'
        if channel == 'trading':
            where += ' AND EXISTS (SELECT 1 FROM lineage_proposals p WHERE p.inquiry_id=i.inquiry_id AND p.agent_id=i.agent_id LIMIT 1)'
        rows = conn.execute('SELECT i.inquiry_id,i.agent_id,i.title,i.state,i.created_at FROM lineage_inquiries i WHERE ' + where + ' ORDER BY i.created_at DESC,i.inquiry_id DESC LIMIT ? OFFSET ?', [owner, *ids, limit, offset]).fetchall()
        result = []
        for row in rows:
            proposals = []
            if channel == 'trading':
                proposals = [item['proposal_id'] for item in conn.execute('SELECT proposal_id FROM lineage_proposals WHERE inquiry_id=? AND agent_id=? ORDER BY created_at,proposal_id LIMIT 20', (row['inquiry_id'], owner))]
            result.append({'kind': 'inquiry', 'id': row['inquiry_id'], 'agent_id': owner,
                           'title': row['title'][:500], 'title_truncated': len(row['title']) > 500,
                           'state': row['state'], 'created_at': row['created_at'],
                           'provenance': 'lineage_proposals' if channel == 'trading' else 'lineage_inquiries',
                           'proposal_ids': proposals})
        return result, 'ok'


def _journal_read(root, run_id, owner, channel, state, limit, offset, note_id):
    from core.memory.compost import CompostStore
    store = _store(root)
    store.get_run(run_id)
    path = store.safe_run_file(run_id, f'memory/{owner}.sqlite3')
    compost = CompostStore(path, owner)
    note = None
    if note_id is not None:
        value = compost.get_note(note_id)
        if value is None:
            _error(404, 'rehearsal_record_not_found')
        note = _journal_note(value, owner)
        if note['id'] != note_id:
            _error(503, 'rehearsal_unavailable')
        values = {'status': 'ok', 'notes': [], 'total': 1}
        sources, source_status = [], 'not_applicable'
    else:
        values = compost.list_notes(channel=channel, state=state, limit=limit, offset=offset)
        sources, source_status = _journal_sources(store, run_id, owner, channel, state, limit, offset)
    if (values.get('status') not in ('ok', 'missing') or not isinstance(values.get('notes'), list)
            or len(values['notes']) > limit or type(values.get('total')) is not int or values['total'] < 0):
        _error(503, 'rehearsal_unavailable')
    notes = [_journal_note(value, owner) for value in values['notes']]
    if any(channel not in value['channels'] or state != 'all' and value['state'] != state for value in notes):
        _error(503, 'rehearsal_unavailable')
    return {'run_id': run_id, 'agent_id': owner, 'channel': channel, 'state': state,
            'status': values['status'], 'notes': notes, 'note': note, 'total': values['total'],
            'limit': limit, 'offset': offset, 'sources': sources, 'source_status': source_status}


def _witness_account(value, scope):
    if (not isinstance(value, dict) or value.get('scope') != scope or value.get('author') != 'witness'
            or value.get('method') != 'mechanical' or not isinstance(value.get('id'), str)
            or not UUID.fullmatch(value['id']) or not isinstance(value.get('content'), str)
            or len(value['content']) > 24000 or not isinstance(value.get('created_at'), str)
            or not isinstance(value.get('source_digest'), str) or len(value['source_digest']) > 256
            or not isinstance(value.get('source_refs'), list) or len(value['source_refs']) > 256):
        _error(503, 'rehearsal_unavailable')
    refs = []
    for ref in value['source_refs']:
        if (not isinstance(ref, dict) or ref.get('kind') not in ('run', 'wake', 'job', 'request', 'journal', 'episode', 'inquiry', 'library', 'witness')
                or not (isinstance(ref.get('id'), str) and len(ref['id']) <= 128 or type(ref.get('id')) is int and 1 <= ref['id'] <= 2**63 - 1)
                or 'agent_id' in ref and (ref['agent_id'] not in AGENTS or scope != 'steward' and ref['agent_id'] != scope)
                or 'wake_id' in ref and (not isinstance(ref['wake_id'], str) or ref['wake_id'] not in tuple(f'{owner}-r{round}' for owner in (AGENTS if scope == 'steward' else (scope,)) for round in (1, 2)))):
            _error(503, 'rehearsal_unavailable')
        if scope != 'steward' and ref['kind'] in ('wake', 'job') and not _owner_wake(scope, ref['id']):
            _error(503, 'rehearsal_unavailable')
        refs.append(_project(ref, ('kind', 'id', 'agent_id', 'wake_id')))
    return {**_project(value, ('id', 'scope', 'content', 'source_digest', 'author', 'method', 'created_at')), 'source_refs': refs}


def _witness_read(root, run_id, scope, limit, offset):
    from core.runtime.rehearsal.witness import WitnessStore
    store = _store(root)
    store.get_run(run_id)
    values = WitnessStore(store.safe_run_file(run_id, 'witness.sqlite3')).list_accounts(scope, limit=limit, offset=offset)
    if (values.get('status') not in ('ok', 'missing') or not isinstance(values.get('accounts'), list)
            or len(values['accounts']) > limit or type(values.get('total')) is not int or values['total'] < 0):
        _error(503, 'rehearsal_unavailable')
    accounts = [_witness_account(value, scope) for value in values['accounts']]
    return {'run_id': run_id, 'scope': scope, 'status': values['status'], 'accounts': accounts,
            'total': values['total'], 'limit': limit, 'offset': offset}


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

    @app.get('/api/rehearsals/{run_id}/decisions')
    def decisions(run_id: str, request: Request):
        _uuid(run_id)
        params = _params(request, ('agent_id', 'wake_id'))
        owner = _owner(params, required=True)
        wake_id = params.get('wake_id')
        if not _owner_wake(owner, wake_id):
            _error(404, 'rehearsal_decision_not_found')
        def fetch():
            store = _store(root)
            matching = [job for job in store.list_jobs(run_id) if job.get('wake_id') == wake_id]
            if len(matching) != 1 or matching[0].get('agent_id') != owner:
                _error(404, 'rehearsal_decision_not_found')
            value = store.get_decision_details(run_id, wake_id)
            if not isinstance(value, dict) or not all(key in value for key in ('metadata', 'private_context', 'requests')):
                _error(404, 'rehearsal_decision_not_found')
            metadata = _decision_metadata(value['metadata'])
            if metadata is None or not isinstance(value['requests'], list):
                _error(404, 'rehearsal_decision_not_found')
            if any(ref.get('agent_id', owner) != owner or not _owner_wake(owner, ref.get('wake_id', f'{owner}-r1'))
                   for ref in metadata['continuity']['refs']):
                _error(404, 'rehearsal_decision_not_found')
            return {'run_id': run_id, 'agent_id': owner, 'wake_id': wake_id,
                    'decision': {'metadata': metadata, 'private_context': _private_context(value['private_context'], owner),
                                 'requests': [_decision_request(event, owner, wake_id) for event in value['requests']]}}
        return read(fetch)

    @app.get('/api/rehearsals/{run_id}/journals')
    def journals(run_id: str, request: Request):
        _uuid(run_id)
        params = _params(request, ('agent_id', 'channel', 'state', 'limit', 'offset', 'note_id'))
        owner = _owner(params, required=True)
        channel, state = params.get('channel', 'unclassified'), params.get('state', 'all')
        if channel not in CHANNELS or state not in ('all', 'active', 'released'):
            _error(400, 'invalid_rehearsal_request')
        limit = _integer(params, 'limit', 20, 1, 20)
        offset = _integer(params, 'offset', 0, 0, 10000)
        note_id = _integer(params, 'note_id', None, 1, 2**31 - 1)
        return read(lambda: _journal_read(root, run_id, owner, channel, state, limit, offset, note_id))

    @app.get('/api/rehearsals/{run_id}/witness')
    def witness(run_id: str, request: Request):
        _uuid(run_id)
        params = _params(request, ('agent_id', 'limit', 'offset'))
        scope = _owner(params) or 'steward'
        limit = _integer(params, 'limit', 3, 1, 20)
        offset = _integer(params, 'offset', 0, 0, 10000)
        return read(lambda: _witness_read(root, run_id, scope, limit, offset))

    return app
