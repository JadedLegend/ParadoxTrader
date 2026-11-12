# Internal lineage contracts

All components use one existing trade-queue database, plus a separate mock-broker database representing the external simulator. No runtime/provider/memory actions are wired in this slice. No mutation HTTP endpoints are added. Pilot agent: `alchemist`. Fictional contract: `DEMO270115C00100000`, underlying DEMO, expiry 2027-01-15, call, strike 100, multiplier 100. Whole contracts only; long opening buy and closing sell. Price strings are Decimal USD per share.

## Queue compatibility

Extract original `TradeQueue`, `QUEUE_DB`, and `QUEUE_SCHEMA` into `core/trading/queue.py`, preserving the exact default path and re-export from `alpaca.py`. `ensure_queue_schema(conn)` adds nullable `lineage_proposal_id` to old rows safely. Existing `enqueue/get_pending/approve/reject` signatures/shapes stay compatible; `get_entry(trade_id)` is a bounded owner-side helper. Linked proposal creation writes the existing pending queue row and lineage proposal in one transaction. Linked review transitions append `proposal_reviewed` lineage events in the same DB transaction; repeated same-state review does not rewrite history. Legacy unlinked rows keep legacy behavior. Linked rejected/executed rows cannot silently be reapproved. False review results are conflicts, not successful approval.

## Store public methods

`LineageStore(db_path)` construction is lazy. Explicit operations initialize queue and lineage tables. New default uses the existing queue path, not a different approval store. Typed errors: `LineageError`, `LineageConflict`, `LineageAccessError`, `LineageNotFound` in `core/trading/lineage/errors.py`.

- `create_inquiry(agent_id, title, *, phase=0, visibility='owner', operation_key) -> inquiry_id`
- `add_entry(inquiry_id, agent_id, kind, content, *, source='agent', operation_key) -> entry_id`, kind observation/interpretation. Source agent/operator/external; no journal import.
- `set_inquiry_state(inquiry_id, agent_id, state, *, reason='', operation_key) -> event_id`, state open/paused/abandoned. Reopening appends a revisited event.
- `create_proposal(inquiry_id, agent_id, structure, *, thesis='', horizon='', uncertainty='', operation_key) -> proposal_id`
- `add_review(inquiry_id, agent_id, content, *, proposal_id=None, order_id=None, position_id=None, operation_key) -> review_id`
- `get_proposal(proposal_id, agent_id) -> dict` includes proposal_id,inquiry_id,agent_id,queue_id,structure,thesis,horizon,uncertainty,review_status.
- `prepare_order(proposal_id, agent_id) -> order dict`: require approved existing linked queue row; unique local order per proposal; deterministic client_order_id; reserve closing quantities; no HTTP. Repeated preparation returns same order, not a new ID.
- `get_order(order_id, agent_id) -> order dict`
- `mark_order_issue(order_id, agent_id, category) -> order dict`: category submission_unknown/unavailable/failed. Append issue event and preserve last confirmed broker/fill information.
- `apply_snapshot(order_id, agent_id, snapshot) -> order dict`: atomic new fill/position/event projection update. Reject wrong identities, inconsistent snapshots, changed fill IDs, overfills, bad long/close quantities; no model text changes. Stale lower revision ignored; equal revision must match previously confirmed snapshot.
- `list_inquiries(agent_id, *, viewer_agent_id=None, phase=0, operator=False, limit=50, offset=0) -> {'status':'ok','inquiries':[{inquiry_id,agent_id,title,state,phase,visibility,created_at,updated_at}], 'total', 'limit', 'offset'}`
- `get_inquiry(inquiry_id, *, viewer_agent_id=None, phase=0, operator=False) -> {'status':'ok','inquiry':metadata,'entries':[],'proposals':[],'orders':[],'fills':[],'positions':[],'reviews':[],'events':[],'truncated':bool}`. Bound per category at 100 with explicit truncation; no private memory reads. Operator true is trusted internal server capability, never client query. Nonoperator reads require viewer identity. Own data accessible; peer only phase>=1 AND original inquiry phase>=1 AND explicit visibility community. Phase-zero entries stay private.

Keys are scoped by agent and reject conflicting payloads under the same operation key. New UUIDs are stable within idempotent operations. Source events/entries/proposals/reviews/fills append only. Inquiry/order/position current-state columns are projections; no earlier interpretation overwritten.

`structure`: `{symbol, underlying, expiry, option_type:'call'|'put', strike:decimal-string, side:'buy'|'sell', intent:'open'|'close', qty:positive-integer, order_type:'limit', limit_price:positive-decimal-string, multiplier:100}`. No additional fields grant execution. Validate OCC contract metadata consistency. No shorts/spreads/assignment or real contract lookup. Proposal queue JSON contains compatible symbol/qty/side/order_type/limit_price plus inquiry/lineage IDs and explicit mode mock.

`order`: `{order_id,proposal_id,inquiry_id,agent_id,queue_id,client_order_id,broker_order_id:null|string,broker:'mock',status:'pending_submission'|'submission_unknown'|'accepted'|'rejected'|'partially_filled'|'filled'|'canceled',sync_state:'pending'|'ok'|'submission_unknown'|'unavailable'|'failed',broker_revision:integer,qty,filled_qty,structure,created_at,updated_at}`. Keep last broker-confirmed status when unavailable. No position from mere acceptance.

`fill`: `{fill_id,broker_fill_id,order_id,proposal_id,inquiry_id,position_id,agent_id,qty,price,side,created_at,authority:'mock_broker'}`. Gross execution result only; fees/mark unavailable.

`position`: `{position_id,agent_id,symbol,qty,average_entry_price:null|string,gross_realized_pnl:string,market_value:null,unrealized_pnl:null,fees:null,mark_status:'unavailable',status:'open'|'closed',multiplier:100}`. Identity stable per agent/symbol; fill-linked only. All write arithmetic Decimal. Closing holds must account for unfilled existing close orders before approving another dispatch.

## Broker and service

`MockBroker(db_path)` persistent simulator, no network/config/account imports. `BrokerUnavailable` and `BrokerConflict` exceptions. Public methods `submit_order(client_order_id, structure)`, `lookup_order(client_order_id) -> snapshot|None`, `cancel_order(client_order_id)`, `fill_order(client_order_id, qty, price)`. Test-driver controls `reject_next` and `fail_after_accept_once` plus `unavailable` (or equivalent documented constructor properties). Submission rejects unsupported input; same identifier/request returns same persisted order; different payload conflict. Lookup None is authoritative absence only; outage raises.

Snapshot: `{broker:'mock',client_order_id,broker_order_id,status:'accepted'|'rejected'|'partially_filled'|'filled'|'canceled',revision:positive-integer,structure,qty,filled_qty,fills:[{fill_id,qty,price,created_at}],created_at,updated_at}`. Fills append, revision increments, cancellation preserves fills; complete orders cannot be canceled into empty positions. Limit price respected.

`PaperLifecycle(store, broker)` rejects non-MockBroker adapters and any agent other than alchemist. `submit(proposal_id) -> order`, `reconcile(order_id) -> order`, `cancel(order_id) -> order`. Persist intent first, lookup before send, reuse client ID after ambiguous outcome. If lookup unavailable, record unavailability and DO NOT submit. Return explicit sync issues rather than pretending rejection/not-found. Broker snapshot errors mark failed, with no partial local updates. No calls from `agent_loop`, Alpaca, council, scheduler, or HTTP mutations.

## UI/API

Parent owns frontend API wrappers, App navigation, fixture resolver, shared CSS, route manifest, fixture generator, project notes, and legacy approve/reject response conflict handling. UI/API agent owns `frontend/src/lineage/contracts.ts`, `frontend/src/lineage/client.ts`, `views/InquiryHistory.tsx`, related UI tests, new read-only API helpers/routes/tests. Store and broker agents should communicate any necessary contract change immediately.

`GET /api/lineage/inquiries?agent_id=alchemist&limit=50&offset=0` and `/api/lineage/inquiries/{inquiry_id}?agent_id=alchemist`. Operator authorization: Header Authorization Bearer against nonempty server env LINEAGE_OPERATOR_TOKEN using constant-time comparison; default not configured =>503 lineage_operator_unavailable, wrong/missing=>403 lineage_operator_required. Fixed pilot agent only; caller cannot choose operator/viewer/phase query roles. No token in frontend bundle. Connected browser login/session transport is not implemented in this slice; fail explicitly, default preview remains local.

Frontend wrappers `getLineageInquiries(agent_id='alchemist',limit=50,offset=0)` and `getLineageInquiry(inquiry_id,agent_id='alchemist')`. DTOs `LineageListResponse` and `LineageDetailResponse`. Local reader export `readLineageFixture(path)` in client.ts lazy-loads JSON `fixture.json` generated by parent, shape `{mode:'mock_demo',agent_id:'alchemist',list:LineageListResponse,details:Record<inquiry_id,LineageDetailResponse>}`. No backend fallback for preview. Parent generates a full fill/restart/close cycle and open/paused/revisited inquiries without trades. Reader limits, IDs, detail access, and metadata clone behavior are bounded. UI headline Inquiry History, one-agent label Alchemist, distinct inquiry/proposal/queue/mock-order/fill/position/review sections; current sync issues explicit and broker data labeled mock confirmed. No inferred market marks or full net returns.
