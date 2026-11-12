# Compost/witness component contract

Use branch `build/compost-and-witness`, baseline merged PR9. No real calls, keys, engine, schedule, Git changes or unrelated source edits from implementation agents.

## Journal memory component

`core/memory/compost.py`, `CompostStore(db_path, owner)` with fixed owner `tempest,siren,alchemist,weaver,oracle,shadow,paradox_hunter`. Run callers always select `memory/{owner}.sqlite3` through existing safe run paths. Reads do not initialize missing DBs or migrate legacy ones. Explicit writes reuse existing journal rows and add metadata/operation/source-link tables. Old rows remain unclassified.

Methods:

- `append_note(operation_key, content, *, channels=None, note_kind='note', source_wake_id=None, source_mode='real')`: literal text up to 6000 chars/12000 UTF-8 bytes; channels are a unique subset of trading/idea/orientation or default unclassified; note_kind note/compost. Return `{status:'applied'|'no_change', refs:[{kind:'journal',id:INT}], id:INT|None}`. Persist the effect identity atomically; conflict rather than change an existing result. Source mode real/offline is attribution, not a model verification claim.
- `prepare_distillation(operation_key, source_ids=None, *, max_chars=4000)`: freeze a nonempty selected source set and its bounded literal excerpts before the activity request. Explicit IDs unique integers, max20, exact owned compost; default up to10 active notes. Advisory5–10, no minimum. Return `{status:'ready'|'empty', source_ids, notes:[{id,content,channels,source_mode,truncated}], truncated}`; immutable on retry. No source row changes.
- `apply_distillation(operation_key, content, *, channels=None, release=False, source_wake_id=None, source_mode='real')`: apply only the previously frozen sources. Literal agent text, separate distillation journal row and source links; release selected compost atomically only if nonempty output. Empty text is no_change and releases nothing. Return same result shape as append.
- `list_notes(*, channel='unclassified', state='all', limit=20, offset=0)`: `{status:'ok'|'missing', notes,total}`; bounded rows include id, literal/excerpt content, channels, note_kind, state active/released, author/source_mode, created_at, source_wake_id, source_ids and truncation. Missing labels => legacy unclassified, not reclassified. `get_note(note_id)` returns original note plus links or None, read-only. Channels trading/idea/orientation/unclassified; state active/released/all.
- `active_catalog(limit=10)`: only compact owned IDs/channel metadata, not automatic full note bodies. `is_released(note_id)` for read-only routine context filtering.

No extra scores, glyph truncation/condense calls or source deletion. Distillation is agent-authored, not witness-authored. Existing `ThresholdMemory` public methods remain unchanged.

## Controller and witness component

Own controller.py, store.py, continuity.py, new witness.py, and focused tests. Keep five CAPABILITIES; journal choice allows optional `journal_mode:'note'|'compost'|'distill'|'witness'`, `channels:[...]`, `source_ids:[INT...]` only for distill, `release:BOOL` only for distill. Defaults keep old plain journal behavior. Validate no foreign owners/paths. New modes are in exact choice instructions/private input evidence; preserve old choice recovery. Distill is a chosen existing second request using frozen sources; witness mode reads at most three prior owner accounts without a second request or agent-memory write. Nothing auto-distills at a count.

For witness mode, extend refs with `{kind:'witness',id:UUID}` and safe job projection with journal_mode/channels if present (not raw arbitrary choice/source IDs). Use current permission gates; no ordinary scheduler or broker imports.

`RehearsalStore.get_witness_snapshot(run_id, owner=None)` returns consistent public run/jobs/request facts in one read transaction, no source bodies or DDL. `WitnessStore(db_path)` writer renders facts itself, with `record(snapshot, *, scope='steward', operation_key)` returning an immutable account `{id,scope,content,source_refs,source_digest,author:'witness',method:'mechanical',created_at}`. Strict scope steward or fixed owner; exact repeat idempotent, changes conflict. Private read methods `list_accounts(scope,limit=3,offset=0)` => `{status,accounts,total}`, `get_account(id,scope)` => row orNone. Reads don't create/migrate files; writer only its own witness.sqlite3.

Write owner account after completed/failed/stopped/uncertain wake, and broad account after controller end. Reporting error must not change finished wake status or resend a request. Missing accounts explicit. Add fixed witness.sqlite3 to safe run files. Preserve source identifiers; no source interpretations, hidden reasoning, private quotations or personality labels in mechanical text. Install a short humble voice asset, not another model. Agent word-for-word notes stay separate.

Released compost is excluded from routine continuity reads, original/source reads remain allowed. Do not automatically insert witness bodies or full active compost into every choice: optional compact catalog only; explicit mode reads.

## Protected API and frontend component

Own api/rehearsal.py, frontend/src/journals/{contracts.ts,client.ts}, views/Journals.tsx and focused tests. Parent owns App/api wrapper/preview resolver/styles/route manifest and fixture builder.

GET `/api/rehearsals/{run_id}/journals?agent_id=OWNER&channel=CHANNEL&state=STATE&limit=N&offset=N` returns list_notes plus bounded owner-only inquiry source headers (idea) and proposal-bearing inquiry source headers (trading), no duplicate execution rows. `note_id=INT` requests one original note including its distillation source IDs; never innermost. Owner/auth validation before any store IO; exact query allowlist. GET `/api/rehearsals/{run_id}/witness?agent_id=OWNER&limit=N` returns private owner accounts; omit agent_id for steward-facing account only after operator auth. Max20, no mutation routes. GET-only app remains scheduler/provider free. Direct mechanical reads and lineage header queries must be read-only.

Frontend Journals uses run/owner selectors and three destination tabs plus Unclassified, active/released/all filter, escaped original/digest content and source links, witness owner/steward optional read, stale run/owner/source guards, explicit empty/missing/failure. It should stay quiet, not a mandatory reflection portal. Client module uses lazy generated `fixture.json`, parent api exports `getJournalNotes(run,params)` and `getWitnessAccounts(run,params)` with concrete types from contracts. No frontend keys, actual model/network calls or writes. Parent-generated data envelope `{runs:[...], journals:{RUN:{OWNER:[notes...]}}, witnesses:{RUN:{SCOPE:[accounts...]}}}`. Source notes preserve IDs; preview data explicitly scripted.
