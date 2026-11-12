# Offered choices and owner-local continuity

This update makes the environment's conditions visible alongside an agent's choice. It also makes bounded records from an owner's first wake available to its second, while leaving writing, revisiting and interpretation optional. The user-facing screen is **Sessions**; existing technical routes and commissioning module names remain stable.

## What the record preserves

| Layer | Evidence |
|---|---|
| Offered choices | The actual five-action menu at the choice request: rest, journal, inquire, library and roam. |
| Costs and constraints | Per-action conservative request reservation ceilings; frozen input, output, context, timeout and concurrency limits; the shared request/budget snapshot when the context was prepared. |
| Choice | A valid committed choice is distinct from no recorded choice. Malformed output fails processing rather than being repaired into rest. |
| Execution | Request admission, provider response, truncation, formatting failure, transport uncertainty and the completed or failed activity remain separately recorded. |
| Private input | The final role/content messages admitted to each request, a canonical input hash and linked owner-local context, stored privately before dispatch. |

The action ceilings include the choice request: at most one request for rest and two for the other activities. They describe upper-bound catalog reservations, not a bill or simulated HRV cost. An offered activity is not a reserved allocation. Concurrent work may consume resources before its second request; the actual admission and execution record shows what happened.

An observed action is therefore one part of a record, not a conclusion about preference. The witness can later say what was offered, what was chosen and what completed without turning these facts into a personality assessment.

## Continuity without a recap obligation

Before a new choice, the controller assembles a small owner-local source context from linked journal, free-exploration episode and inquiry records in strictly earlier rounds of the same run. It reads source stores without creating a missing memory database. It does not scan peers, the innermost layer or the philosophical library.

The context uses at most four source references and 4,000 extracted characters, with individual quoted text capped at 800 characters. Inquiry references retain their stable identifiers, title, state and a bounded latest entry with its original kind and source. Missing or unreadable source material and truncation have explicit coverage. Source notes themselves are unchanged.

This context is optional quoted user data, not an instruction to agree, explain oneself or produce a recap. It is available before the second choice and relevant activity. The inquiry activity still uses the existing owner-local inquiry handler, so a later command can append to or revisit the earlier inquiry through its stable ID. No extra recap model call is added.

The two-round barrier remains independent of eloquence, action type, output length or inferred character. Both turns are planned for every owner; stop, admission or provider failures remain operational constraints rather than personality judgments.

## Durable evidence and private inspection

Decision metadata and private source context are committed once before a new choice request. Repeated identical writes are idempotent; conflicting changes are rejected. Request input snapshots are committed before dispatch. If input persistence fails, the request is recorded as not sent and transport is not entered.

Prepared context is reused on recovery rather than recomputed from a later shared budget snapshot or newer source wording. An older job with no captured decision context remains unavailable; the update does not invent a historical menu or input. Existing choice/output checkpoints and conservative handling of uncertain dispatched requests remain in use.

Operational job projections contain menu/limit/coverage metadata and selection provenance, but no quoted private body. The protected decision endpoint requires operator authentication and exact owner/wake matching:

```text
GET /api/rehearsals/{run_id}/decisions?agent_id=OWNER&wake_id=OWNER-rN
```

In Sessions, offered actions, selected action and outcome are separate. Full decision context and request messages require an explicit owner-local read. Changing the run or owner clears prior details and guards against late responses. The default preview has no backend fallback, keys or launch controls.

The preview is generated from actual temporary scripted controller stores. Its example dispatch is serialized for deterministic shared-resource snapshots; real controller concurrency is unchanged. Identifiers and timestamps are normalized, and example input hashes are rebuilt for those normalized messages. The fixture is explicitly labeled synthetic rather than presented as real model evidence.

## Fit with compost and the witness

This is the source-evidence layer for the proposed quiet witness and optional compost. A later agent-written compost note or witness account can link to the choice conditions and actual outcome. Neither needs to replace the original note or explain what a choice means about the agent.

The proposed five-to-ten-note compost collection, optional distillation, release from active context and separate trading/idea/orientation journal views remain the next layer. This update does not install a witness model, automatic summaries, new journal obligations or archive deletion.

## Verification status

Final verification passed: **594 offline Python tests**, **448 network-blocked frontend tests**, TypeScript diagnostics, lint with zero warnings/errors, production build and all four source/example reproducibility checks. A focused post-review run also passed 27 checks for protected reads, exact inputs, failure provenance and source coverage.

Independent read-only review found one source-error path: a readable inquiry title could conceal an unreadable latest entry in the public coverage flag. The fix preserves the title while marking partial coverage; a deterministic regression covers it. The existing API idle check still requires GET-only routes, now including the sixth protected decision endpoint.

The build retains the existing nonblocking large-chunk warning for lazily loaded source assets. No real model calls, broker/account connections, scheduler activation or deployment were performed. Real-provider behavior and connected operator credential delivery remain untested commissioning work; the later compost and witness layer remains a design rather than installed behavior.
