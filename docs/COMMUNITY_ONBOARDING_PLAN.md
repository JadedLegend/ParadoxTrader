# Seven-agent arrival, private inquiry, and adjustable onboarding

## Purpose and scope

All seven agents are intended to arrive in one launch cohort, each with its own identity, memory, and private inquiry space. A one-agent engineering test is not a social head start. Initial hours and the suggested one-to-two-week private period are adjustable windows, not maturity deadlines or a compulsory curriculum. Introductions make short concepts available without requiring an essay, insight, journal, trade, or preferred response. Community opening is separate from portfolio visibility and trading authority. This implementation remains offline development; no accounts, model providers, scheduler, or deployment are activated.

Use the existing merged lineage and original memory systems. Add private optional inquiry activity for all seven, not automatic conversion of market commentary into proposals. Persist a validated inquiry-action receipt before its record application, with stable operation IDs and owner scope, so retry of this path recovers an existing action rather than generating duplicate interpretations. Legacy wake effects in other databases are not suddenly transactional; report that limit. No new approval, execution, cancellation, or broker permissions are added. The Alchemist/DEMO mock service remains the execution test boundary.

## Identity and relationship orientation

Keep every supplied soul/living original unchanged. Add a short, versioned Seven Seeds asset used by the working prompt instead of mixing new permissions with mandatory legacy covenants. Retain vivid temperaments, characteristic interests, humor, ambition, and relationship friction; do not smooth everyone into interchangeable agreeable analysts. Relationships are initial perspectives with reasons to examine and communication paths, not a permanent duty to oppose another agent. Legacy relationship wording may be retained as labeled starting perspective, not evidence of an event. Do not invent the example of a blocked dream job as actual history. Distinguish creator-supplied background, actual events, agent interpretations, and later self-descriptions.

Provider/model assignment stays outside identity and does not reset history. Stable agent IDs own accounts and privacy even if display names/interests change later. This slice uses existing living self-descriptions in the prompt and preserves source originals; a full identity-edit/version API is not required or silently added.

## Independent controls

A server-owned community policy exposes an adjustable introduction stage and available concepts separately from `forum_open`, `peer_messages_open`, and `share_peer_positions`. Defaults keep communication and portfolio sharing closed. Existing phase boundaries remain necessary but no longer sufficient for these capabilities. Forum opening does not advance trading phase or reveal private inquiry/journal/portfolio history. Policy changes are explicit configuration, not automatic reward/progress judgments. A timer does not promote an agent, release a concept, or open the forum in this slice.

Show short currently available invitations in wake context; retain the full optional library. The settling invitation explains activities, information boundaries, voluntary expression, and the shared practical financial purpose. Later invitations cover inquiry, paradox, markets, and structures without requiring immediate financial application. Closed introductions do not remove existing general exploration or secretly forbid asking a question.

## Optional private inquiry

Add `inquire` to the rotating choice pool for all seven, with ordinary existing fallback simulated HRV cost and quiet rest preserved. One selected inquiry activity can choose no change, start a question, append an observation or interpretation, pause/abandon/revisit, or add a later review. Bounded owned metadata/detail is user-data context; no peer inquiry, private journal, innermost text, entire library, or raw credentials enter the prompt. Unknown fields and ownership conflicts fail closed. The response never authorizes a trade or queue entry.

A stable wake/operation identity links the new receipt and cost correlation. Validate and persist the chosen inquiry operation before applying it with store idempotency keys. Same receipt/ID is resumed without another model call; changed input under the same ID conflicts. Concurrent/restarted attempts must not apply different payloads or repeat source records. Preserve failures explicitly, retaining committed lineage. Episode writes, HRV, inbox acknowledgements, and older unrelated actions remain separate; do not claim global exactly-once wake execution.

Prepare a deterministic all-seven arrival cohort with stable job IDs and private owned records in an offline driver. Production scheduling remains inactive and a real simultaneous launch still requires separately configured host/accounts/model calls, independent community policy, and reviewed operator controls.

## UI and serving

Reuse the current dark responsive operator UI. Inquiry History can select any of the seven owners; protected backend reads use operator authorization and the same queue database path. Default preview remains local and generated by actual temporary stores. Keep the existing complete Alchemist mock lifecycle and add other agents' nontrading examples. UI labels separate mocked histories and source material from actual operation, and retain missing/pending/failed/unavailable states. The selected owner resets detail to avoid stale private records. No execution or policy-mutation controls, browser secrets, or connected login are added.

The default frontend is served by Vite without the API or engine. All new data remains lazily loaded. Provider/broker/model dependencies are mocked in tests. No decorative image assets are needed for this internal tool.

## Structure

- `core/runtime/community.py` and `orientations/seven_seeds.json`: pure server-owned policy, compact invitations, identity seeds and labeled original relationship perspectives.
- `core/runtime/inquiry.py`: durable receipt/optional inquiry adapter using the existing lineage database; no order preparation or broker imports.
- `core/runtime/cohort.py`: offline cohort preparation and stable logical wake IDs, no autonomous scheduling/startup.
- Existing `agent_loop.py`, `llm.py`, and usage attribution: bounded prompt/context/choice integration; preserve prior actions and quiet rest.
- Existing lineage store and read API: owned private records and protected all-seven selection, without widening execution pilot authority.
- Existing frontend history contracts/local reader/view/fixtures: all-seven selection using the established read-only preview boundary.
- `scripts/build_lineage_fixture.py` and offline tests: reproducible source-owned inquiries, bounded prompt/permissions, retry isolation, and unchanged originals.

Separate ownership: policy/seed implementation owns community.py, seven_seeds.json, build_system_prompt only, and its tests. Inquiry implementation owns inquiry.py/cohort.py and its tests. UI implementation owns existing history view/client/contracts and tests only. Parent owns runtime integration, API expansion and guards, fixtures, config examples, documentation, full checks, independent review, commits and pull request.
