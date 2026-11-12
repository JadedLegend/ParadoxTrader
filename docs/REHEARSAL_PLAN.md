# Seven-agent nontrading rehearsal controller

This milestone prepares a complete, observable finite rehearsal with the actual assigned OpenRouter model IDs, without starting it during development. The first planned run has one common cohort and two bounded wake rounds for all seven, with max three simultaneous outbound calls. No personality grading, enthusiasm/coherence rewards, forced journal/inquiry, or predetermined conclusions are added.

## Existing code and reuse

The existing ordinary wake reads Alpaca positions when keys are present, and its global action dispatcher includes trading/research tools. It is not a safe nontrading launch entry point. The bounded controller will reuse `prepare_cohort`, strict `run_inquiry` receipts, `ThresholdMemory`, source `LibraryStore`, `build_system_prompt` identity/orientation, and `UsageStore`. It will expose only rest, optional journal, private inquiry, bounded local library reading, and roam. No broker/feed/trading/scheduler imports or global configuration mutation are needed to dispatch this restricted session. It is a commissioning controller, not a second unrestricted agent framework.

Real provider calls use an explicit, frozen seven-owner model map and a verified public catalog snapshot. Exact models must be supported; missing models/parameters/pricing/context are readiness failures, not invitations to silently substitute. Existing persona/model assignments are not rewritten. OpenRouter is the existing route; direct provider account adapters are outside this slice.

## Run controls and persistence

Use a private run root outside tracked source, one immutable manifest and source-profile snapshots per run, one run-control SQLite database, per-owner memory, and the existing run-local lineage/usage databases. Preserve previous agent histories; no real-run content enters checked-in fixtures. Readiness and explicit prepare/start/stop/resume commands are finite application-owned operations, not schedule setup. Starting requires mode-specific explicit acknowledgement; the CLI dry-run path never reads credentials or contacts a model.

Freeze one arrival cohort and both logical wake rounds. Persist choices and validated response/application checkpoints before effects. Completed jobs are not reissued. A submitted request lost before its result is known becomes uncertain; do not silently replay paid work. Inquiry committed steps can recover through existing receipts. Journal/roam/library side effects need owner-local idempotency linkage. Stop prevents future reservations/dispatch; an already-sent request may return and be recorded, and its cost is not undone. A process-wide/run controller lease prevents competing dispatchers.

The run has exact seven owners, two rounds, 28 maximum HTTP attempts, 1,024 maximum output tokens per request, 24,000 maximum UTF-8 input bytes, 900 seconds maximum runtime, 60 seconds request timeout, and concurrency <= 3. These are defaults and upper bounds in this slice, not an unlimited future job. Real mode requires an explicit positive operator-selected USD admission budget and frozen prices. Keep conservative reservations for unknown costs/failures; reported/estimated/unknown spend remains separately visible. An application admission budget is not an absolute guarantee about an upstream invoice; provider account/key limits remain a separately controlled protection.

Forum, peer DMs and sharing, broker/account reads, market/news research, tools, proposals, orders and execution are structurally absent. Session prompts describe unavailable market evidence and capabilities accurately, independent of ordinary application gates. Local source excerpts are quoted user data, not permission-granting instructions. Different model styles and legitimate no-change/rest are ordinary outcomes.

## Inspection and serving

Extend the existing dark operator-dashboard style with a lazy Rehearsal view: run status/limit coverage, seven-member progress, pending/completed/failed/stopped/uncertain states, chosen action, requested/returned model and upstream provider where supplied, request latency, coverage-aware costs, and selected-owner private record links. Operational metadata is separate from journal/source content. Avoid constant-watch expectations: inspection is useful after the finite run.

Use a separate protected read-only rehearsal API with no scheduler/provider startup, rather than starting the existing broad backend. No browser provider keys or implicit launch controls; CLI owns prepare/start/resume/stop until connected operator authentication is deliberately integrated. Default frontend mode remains local, clearly labeled mocked examples and blocks all mutations/network fallback.

## Project structure

- `core/runtime/rehearsal/store.py`: private run state, stable jobs, request reservations, stop/lease and recovery checkpoints.
- `core/runtime/rehearsal/provider.py`: pure exact-model readiness/catalog validation and explicitly armed single-attempt OpenRouter transport, no fallback or implicit credentials.
- `core/runtime/rehearsal/controller.py`: finite bounded seven-member rounds, allowed activity dispatcher, existing private stores and optional source reading.
- `scripts/rehearsal.py`: explicit offline/real preparation and finite run/stop/status/resume control; no actual calls during implementation.
- `api/rehearsal.py`: protected read-only run/private-record API; no broad API/scheduler import.
- `frontend/src/rehearsal/` and `views/Rehearsal.tsx`: typed, local preview and actual metadata contracts.
- `scripts/build_rehearsal_fixture.py`: deterministic actual-store mocked example builder, excluding real records.
- `tests/test_rehearsal_*` and frontend tests: offline guarded execution, concurrency, budgets, stop/restart, owner privacy and view-state regressions.

## External provider contract

Primary docs checked 2026-11-12: OpenRouter model catalog pricing is USD per token/request/unit; catalog `max_completion_tokens` is a ceiling, and supported parameters include `max_tokens`. Require supported caps and inspect pricing overrides/extra billed units instead of assuming token-only cost. Provider `require_parameters` prevents unsupported request parameters being ignored; restrict model routing (no models/fallback array) and disable provider fallbacks, with price ceilings using documented USD-per-million prompt/completion units. No undocumented assumption that all seven example IDs are currently available has been made.

Sources: [models catalog](https://openrouter.ai/docs/guides/overview/models), [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [usage accounting](https://openrouter.ai/docs/guides/guides/usage-accounting).
