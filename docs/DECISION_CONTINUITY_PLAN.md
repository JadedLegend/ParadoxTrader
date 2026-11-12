# Offered choices and owner-local continuity

This slice implements the three requested refinements without starting real models, altering the seven identities, introducing personality assessments, or changing trading/community authority. Existing technical commissioning modules keep their names; the user-facing account concerns sessions and what actually happened, rather than treating participation as a performance examination.

The controller already fails malformed choices instead of guessing rest. It offers the same five optional activities; request admission can still deny an otherwise offered activity. We will preserve that distinction rather than introduce a new resource-based recommendation policy. An offer is not a reservation or a guarantee of successful execution.

## Architecture and ownership

`core/runtime/rehearsal/store.py` owns write-once per-wake decision metadata/private context and request input snapshots alongside existing jobs and requests. Reads of older records explicitly return unavailable context; they never backfill imagined offers or alter earlier choices. The provider records the exact capped message input before dispatch, separately from public telemetry. Requested and returned models, caps, formatting/transport failures, finish reasons and actual outcomes remain operational facts, not explanations of character.

The controller and a small `continuity.py` helper supply bounded, quoted owner-local notes and inquiries from linked prior wakes before the next choice and relevant activity. No compulsory recap, recap model call, innermost material, peer records, or memory rewriting is introduced. Empty prior activity legitimately yields empty continuity. Original entries remain the source, with references and marked excerpts.

The existing protected read-only API and local preview add explicit decision-context reads. The session view presents offers, costs/constraints, selected action, selection provenance and execution state separately. Full prompt/evidence content is operator-protected and owner-scoped, absent from public summaries and ordinary logs. The witness can later consume this evidence without inferring preference from an action alone. This slice does not install or run a witness model.

## Shared implementation contract

Public job projections add optional `decision_context` and `selection_origin`. Origin is `model` only when a valid model choice was committed; otherwise it is `none`. There is no controller fallback to rest. Older jobs without context remain explicitly unknown.

`commit_decision_context(run_id, wake_id, token, *, metadata, private_context)` writes once for the claimed owner wake. `get_decision_context(run_id, wake_id)` returns public metadata or None. `get_decision_details(run_id, wake_id)` returns `{metadata, private_context, requests}` or None; requests include only linked exact input snapshots for that owner/wake. `commit_request_context(run_id, request_id, token, messages)` writes the capped literal role/content messages once before dispatch. Successful context commits must be immutable and idempotent, conflicting writes rejected.

Decision metadata (strict bounded JSON) is:

```json
{
  "schema_version": 1,
  "offered_actions": ["rest", "journal", "inquire", "library", "roam"],
  "action_costs": [{"action":"rest", "max_requests":1, "reservation_ceiling_usd":"0", "basis":"catalog_upper_bound"}],
  "constraints": {"wakes_per_agent":2,"max_requests":28,"max_output_tokens":1024,"max_input_bytes":24000,"max_runtime_seconds":900,"request_timeout_seconds":60,"max_parallelism":3,"budget_usd":"0"},
  "admission_snapshot": {"reserved_usd":"0","remaining_budget_usd":"0","request_count":0,"remaining_requests":28,"is_reservation":false},
  "model": {"requested_model":"synthetic/tempest","context_length":131072,"max_completion_tokens":4096,"catalog_source":"synthetic"},
  "continuity": {"status":"empty","refs":[],"truncated":false,"chars":0}
}
```

Action cost ceilings include the picker: rest uses at most one request, other choices at most two. They are conservative catalog-based maximum reservations, not billed costs or HRV points. The admission snapshot is a point-in-time observation, not a reserved allocation; concurrent work may consume resources before the chosen activity. Actual admission/result records remain authoritative.

Private context contains bounded literal owner excerpts and source refs; it never claims to know which excerpt the model used. Request snapshots include literal final messages, their SHA256 and input coverage, not keys, responses or hidden reasoning. They stay in the private run database; the read endpoint is `GET /api/rehearsals/{run_id}/decisions?agent_id=OWNER&wake_id=OWNER-rN`, requires operator authentication and exact owner matching. The frontend local fixture has `decisions[run_id][wake_id]` envelopes `{run_id,agent_id,wake_id,decision}` generated from temporary actual stores only.

## Preserved behavior and delivery

Every owner keeps two turns with a round barrier independent of eloquence, output length, action, or inferred personality. No new model calls, reward scores, forced journals, repaired choices, extra trading capability, live launch, schedule activation or main-branch merge. Continue the established dark operator interface; show missing/failed/truncated context honestly. Publish a reviewed branch with working-versus-untested notes.
