# Traceable idea lineage — first implementation

This slice gives an inquiry continuity without making it a trade obligation. It implements a durable, offline Alchemist pilot with one fictional options contract. Inquiries, optional proposed structures, review authorization, broker-confirmed mock execution, fill-linked positions, and later interpretation remain distinct records.

## Existing implementation reused

| Existing component | What was present | How this slice uses it |
|---|---|---|
| `core/trading/alpaca.py: TradeQueue` | Persisted integer queue IDs; pending/approved/rejected states; user notes | Extracted to broker-independent `core/trading/queue.py` and re-exported from the original import path. Added nullable linkage in the same queue database; old rows/IDs/payloads are preserved. There is no second approval queue. |
| API `get_trade_queue()` | Configured `db_path("trade_queue.sqlite3")` | New API lineage reads use the same resolved path. `DATA_DIR` and configured persistent storage therefore refer to the same proposal/review history. The old exported queue default remains unchanged for compatibility. |
| `AlpacaClient`, `check_guardrails`, `submit_trade` | Options adapter, existing guardrail and autonomous/review split; general orders accept a client-order ID | Their implementation bodies are unchanged. New durable submission/reconciliation is mock-only and does not dispatch through these functions. The existing options submission path still needs its own reviewed integration. |
| Agent trade-idea/review actions | Free-form episode text, not structured executable proposals or confirmed fills | Remain unchanged. No analysis is automatically promoted into a proposal; no new runtime action is compulsory. |
| Individual episodes/checkpoints/journals | Personal memory and resumption context | Not copied into shared lineage. Explicit inquiry entries are separate supplied text with source labels. No private journal or checkpoint import was added. |
| Position snapshots and preview client | Explicit lookup states and a fail-closed local preview | Kept intact. Inquiry History adds separately labeled mock records; it does not replace Alpaca account snapshots or inject simulated holdings into them. |

## Implemented continuity

An inquiry has a stable identifier, owner, original phase/visibility, and current state. Observation and interpretation entries append with their own identities and sources. Pausing, abandoning, and reopening/revisiting append events while retaining earlier text. A question may stay in inquiry indefinitely, with no proposal, order, or review.

A proposal is an explicit optional structured record with its own identifier, thesis, horizon, uncertainty, and existing queue ID. It is created with its queue row atomically. Review authorization is a separate event. Later reviews append another interpretation and may reference the relevant proposal, order, or position without changing an earlier hypothesis.

Operation keys are durable and agent-scoped. Reusing a key with the same content returns the same record; different content under that key is a conflict. Inquiry/event/entry/proposal/review/fill source tables reject updates/deletes. Current inquiry/order/position columns are projections, not replacements for their prior history.

## Working mock execution

The execution service accepts only the Alchemist and the fixed fictional `DEMO270115C00100000` call contract. The shared record store can retain alternative inquiries/structures, but they confer no pilot execution authority. Whole contracts, long opening buys, closing sells, limit prices, and multiplier 100 are the supported mechanics. Execution prices are positive, capped at 1,000,000 USD/share, with at most eight normalized fractional places.

The service commits the local intent and deterministic client-order ID before a broker call. It requires explicit queue approval; approval itself dispatches nothing. The persistent mock broker deduplicates identical submissions by that ID and rejects changed requests under the same ID. A lost acknowledgement is recorded as unknown, not as rejection or acceptance. Lookup outages never cause a fresh submission. An authoritative absent result permits an explicit same-ID retry through `submit`; `reconcile` itself only looks up existing intents.

Acceptance, rejection, cancellation, partial fills, and complete fills are separate mock-confirmed states. Cancellation retains any prior fills. Versions and stable fill identities prevent replaying or changing earlier executions; stale observations cannot downgrade confirmed state. New fills, order state, position quantity/cost basis, gross realized result, and their events commit in one local transaction. A failure partway through that transaction leaves none of its partial updates committed.

The tested full example opens two contracts in separate fills, restarts around an uncertain acknowledgement and partial-fill state, then closes in two separate fills. It produces one closed position, with an engine-derived **gross simulated realized result of USD 50**. That is example arithmetic, not an observed strategy return. Fees, market marks, market value, and unrealized P&L remain unavailable. The example has an optional later review and three other inquiries with no proposals/orders, including pause and abandon/revisit histories.

## Privacy and read-only access

Nonoperator store reads require a viewer identity. Owners can access their own records; peer access requires a community phase and explicitly community-visible records originally created in a community phase. Solo-phase history stays owner-only even when the viewer later enters a community phase. A position aggregate containing private contributing inquiries is suppressed from peer views. Foreign-owner and cross-inquiry review references are rejected.

New backend history routes require a server-side `LINEAGE_OPERATOR_TOKEN`, checked before accessing a store. Missing configuration is unavailable; a missing/wrong credential is forbidden. Clients cannot select an operator identity, viewer, or phase through query parameters. Linked private proposals are excluded from the existing unguarded global queue list. Linked legacy review requests require the same operator credential, and conflicting state transitions return HTTP 409. Existing unlinked queue behavior is retained.

No credentials are embedded in frontend code. Newly created queue/lineage and mock database files are private (0600); existing database permissions are not silently rewritten. These are local durable SQLite files, not a hosted database or backup service.

## UI and verification

Inquiry History is a read-only tenth operator screen. Its default local example is generated from the real lifecycle in temporary databases. It shows independent inquiry notes, optional structures, queue review, mock order/synchronization state, confirmed fills, position/gross outcome, later reviews, and event history. Missing, pending, failed, unavailable, and truncated records have separate presentation. Source text renders as plain escaped text; no trade/approve/cancel controls were added to this view.

```sh
# Repository root: offline regression and reproducible data checks
python3 -B -m unittest discover -s tests -v
python3 -B scripts/build_lineage_fixture.py --check
python3 -B scripts/build_ui_fixtures.py --check
python3 -B scripts/import_library.py --check

# Frontend only: no Python API or engine launch
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
npm run dev
```

Inspect Inquiry History from the frontend navigation. The default preview neither reads actual runtime databases nor contacts providers/brokers. Do not launch the Python API just to inspect it: the existing API startup lifecycle starts its scheduler if independently operated.

Offline evidence includes actual subprocess exits before dispatch and after mock venue acceptance, recovery to a single venue order, SQLite-triggered failure after local fill insertion, transaction rollback and idempotent recovery, closing reservations and simultaneous oversell prevention, private-history access, queue migration, protected API reads/reviews, and generated example parity. Frontend tests use a network-blocked DOM. No real-browser visual audit or deployment is claimed.

Final validation passed **370 Python tests** and **347 frontend tests across 13 files**. TypeScript checks passed; lint reported zero warnings/errors; the production build and three source/fixture reproducibility checks passed. The existing lazy private corpus retains its non-blocking size warning. New queue/lineage/mock file permissions were verified as 0600.

Independent review corrections enforce the fixed fictional pilot contract before intent creation or dispatch, align authenticated history with the existing API queue's configured database path, and reject impossible partial-filled rejection snapshots at the transactional store boundary. Regression tests exercise each correction, as well as the linked legacy authorization guards.

## Working versus remaining

| Area | Current status |
|---|---|
| Optional inquiry/entry/state/review persistence | Implemented and tested, including idempotency and retained prior interpretations |
| Existing queue integration and configured API storage path | Implemented and tested; legacy rows/imports preserved; linked private rows protected |
| One-agent/one-contract mocked order/fill/position cycle | Implemented and tested, including hard process exits and failed local transactions |
| Read-only local history and protected backend handlers | Implemented and tested in offline/isolated environments |
| Autonomous agent use of inquiry tools or wake-to-lineage capture | **Not implemented** in this slice; no model calls or agent wake behavior changed |
| Connected browser login/session/header delivery | **Not implemented**; backend reads require operator authorization and the UI reports failure explicitly without pretending history is empty |
| Alpaca lifecycle adapter or actual paper account orders | **Not connected or tested**; existing options submission is not the new durable lifecycle |
| Additional agents/contracts, spreads, shorts, adjusted multipliers | **Not enabled by the pilot execution service** |
| Expiry, exercise, assignment, commissions, market marks | **Not simulated or available** |
| Hosted durability, migration of legacy default paths, production authentication/security | **Not deployed/validated**; explicit database paths must be consistent when operated outside the existing API getters |

The next integration can give the Alchemist an optional inquiry-recording interface before any real paper-broker adapter is introduced. Broader execution should follow the same lineage and recovery contract rather than turn ordinary observations into trade requests.

See [implementation/reuse plan](IDEA_LINEAGE_PLAN.md) and [internal component contracts](LINEAGE_CONTRACTS.md) for structure and interfaces.
