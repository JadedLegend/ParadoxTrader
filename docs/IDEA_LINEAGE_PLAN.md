# Traceable idea lineage — first slice

## Purpose and reuse

An inquiry is not a trade obligation. Preserve seven identities, existing phase/HRV/menu rules, individual memory, optional participation, and paper-only permissions. Start with the Alchemist and one fictional single-leg long options contract through a persistent mock broker. No Alpaca/provider calls, running agents, timers, new reward scores, or mandatory reflection.

Existing `core/trading/alpaca.py` has `TradeQueue`, stable integer queue IDs, pending/approved/rejected review states, options submission and guardrails. Its general order method accepts a client-order ID, but the options path does not; approval does not dispatch an order. `agent_loop` keeps free-form trade ideas/reviews as episodes without structured broker objects. Memory episodes/checkpoints are useful personal context, not broker confirmations. Position snapshots have explicit lookup states but no fill-linked local continuity.

Extend the existing trade-queue database with lineage tables and nullable linkage. Preserve existing queue rows and public import paths; extract queue-only storage to a standalone module and re-export it from `alpaca.py`. Do not create another proposal approval queue or silently migrate away from the current queue path. Existing broker execution remains unchanged and disconnected from the new mock service. No private journal/checkpoint/episode content is copied into shared records; optional opaque episode references may be supplied explicitly.

## Records and continuity

Use stable UUID identities for inquiries, entries, proposals, local orders, fills, positions, and retrospective reviews. Append inquiry observations/interpretations and status changes rather than rewriting prior text. Inquiries can stay open, pause, be abandoned, or be reopened/revisited without proposing or ordering anything. Explicit operation keys make repeated writes idempotent and reject different payloads under the same key.

A structured proposal is optional and links to one inquiry plus the existing review-queue row. It has a separately recorded thesis/horizon/uncertainty and a validated fictional options structure. Broker-confirmed snapshots and executions belong to order/fill history, never to a model claim. Reviews append an interpretation and may reference a proposal/order/position; they do not mutate a prior thesis or change permissions.

## Submission, reconciliation, and positions

Persist the local submission intent and deterministic client-order ID before calling the mock broker. Require explicit existing-queue approval. Only the Alchemist is supported by the pilot execution service; no agent wake or HTTP mutation endpoint dispatches it. Reject non-mock adapters. Reconcile by the same durable ID after uncertain responses/restarts. A lookup outage is unavailable, not proof that the order is absent. An authoritative not-found lookup permits a same-ID idempotent submission; it never creates a new ID for a retry.

The persistent mock supports acceptance/rejection, cancellation, partial/complete fills, and deliberate before/after-submit outages. Versioned broker snapshots and stable fill IDs make repeated/out-of-order reconciliation idempotent. Apply fills and position updates in one local transaction; acceptance alone creates no holding. First scope is whole contracts, single-leg long opening buys and closing sells, multiplier 100. Prevent overfills, changed fill identities, unsupported/short intents, and overselling confirmed unreserved holdings. Price/quantity/P&L arithmetic uses Decimal. Outcomes distinguish gross realized results from unavailable market marks and unknown fees; no expiry/exercise/assignment/spread simulation is claimed.

## Read-only view and privacy

Add Inquiry History to the existing dark operator interface, keeping the lazy, network-isolated preview. Generate its one-agent mock example from the real lifecycle engine in temporary stores, not handwritten fictitious order states. Show separate inquiry entries, optional proposals, explicit queue review, broker state/fills, position quantities/outcomes, and optional later reviews. Missing, pending, failed, unavailable, and not-yet-recorded states remain distinct.

Store read helpers enforce agent identity and phase visibility; phase-zero records are owner-only even if they later appear in a community phase. Operator access is explicit and separate. New backend read routes require a server-side operator credential; no browser bundle secrets or client-selected operator/phase impersonation. Default preview needs no authentication or backend. The existing backend's general authentication limitations and actual browser login/connected operation remain outside this pilot and must be reported. No write/execute/cancel endpoints are added.

New linked proposals are excluded from the existing unguarded global queue listing. Existing unlinked queue behavior remains compatible. Reviews of linked proposal IDs through legacy endpoints require the same operator authorization, and conflicting review transitions return a conflict rather than a success message. Trusted internal operator code can explicitly include linked rows for offline inspection.

## Structure

`core/trading/queue.py` owns the existing queue schema/storage and additive linkage. `core/trading/lineage/` holds durable inquiry/event/order/position projections and access policy. `core/trading/mock_broker.py` is the separate durable broker simulator. `core/trading/lifecycle.py` owns mock-only submission/reconciliation. `scripts/build_lineage_fixture.py` builds the temporary one-agent example. `frontend/src/lineage/` and `views/InquiryHistory.tsx` supply typed bounded reads and the operator history view. Offline tests cover restart and crash-window continuity without any actual provider, broker, journal, or scheduler access.
