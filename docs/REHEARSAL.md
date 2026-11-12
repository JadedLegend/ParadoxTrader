# Seven-agent nontrading rehearsal

The commissioning controller is implemented. It has exercised all seven owners through two complete wake rounds using the actual controller, private stores and an explicitly scripted offline transport. The deterministic example contains 14 completed wakes and 26 scripted requests. No real provider session, account access, trading, scheduler, server or deployment was started during implementation.

The point of the next real session is to see how this architecture handles actual selected model responses. There is no personality scorecard. Rest and empty optional writing are complete outcomes. The offline notes in the UI are labeled scripted examples and were not authored by live models.

## What is reused

The controller reuses the existing seven owner identities, compact `build_system_prompt` orientation, cohort preparation, `run_inquiry` receipts, `ThresholdMemory`, source `LibraryStore` and `UsageStore`. The ordinary `agent_loop` is deliberately not a commissioning entry point: it can read configured Alpaca accounts and dispatch research/trading actions. This restricted session does neither.

Run-local lineage uses the same existing queue-backed schema rather than a second approval/order system. Inquiry choices can start, extend, pause, abandon, revisit, review or leave a question alone through the existing strict parser. No proposal or order is generated as a side effect of participating.

One run contains a private control database, isolated owner memories, queue-backed inquiry records, usage ledger and a copied source corpus. Original soul/living files and whole working prompts are frozen and hash-checked at preparation. Updating source traits or orientation later does not rewrite the prepared run's prompts. The pure identity function is compiled without executing the legacy model module's tracing/environment setup.

## Participation and visibility

Each wake offers only rest, optional journal, private inquiry, bounded local library reading and roam. Forum, peer messages, holdings sharing, broker reads, market/news research, tools, proposals and execution are structurally absent. Existing application credentials or open community gates cannot enable them in this controller.

There is one shared arrival cohort and a barrier between the two rounds. At most three request gateways work concurrently; a shared arrival does not mean seven network requests must leave in the same instant. All seven have the same commissioning window and no social head start is recorded.

The Rehearsal screen shows status, seven-member progress, selected actions, requested/returned models, upstream provider when supplied, latency, admission reservations, known costs and unknown coverage. Journal, episode, inquiry and source records are separate deliberate owner-scoped reads. Prompts, queries, journal bodies, staged output, secrets and hidden reasoning are absent from operational summaries. Owner/run changes invalidate stale private-record responses. Missing records, failed requests, stopped work and uncertain work are explicit states.

Default frontend mode reads the checked-in example generated from temporary offline stores and never falls back to a backend. A real run's private content is never copied into that fixture. The dedicated read-only API has server-side operator authentication and no startup scheduler or model call. Browser authentication delivery remains separate work; no provider/operator keys belong in `VITE_*` variables.

## Bounds and cost accountability

The first slice fixes seven owners and two rounds. Upper bounds are 28 request admissions, 1,024 output tokens requested per call, 24,000 UTF-8 input bytes including a conservative protocol allowance, a 900-second admission window, 60-second transport timeout and three concurrent gateways. Lower request/input/output/timeout/concurrency caps can be prepared, while both rounds remain fixed. New admission stops at the deadline; already-dispatched requests may settle afterward. The socket timeout is not a promise of an absolute provider invoice or network-wide wall-clock cancellation.

Real preparation requires an explicit seven-owner model map, a supplied or explicitly fetched public catalog, and a positive operator-selected USD budget. Catalog normalization freezes only those exact IDs. Missing models, unsupported `max_tokens`, inadequate context/caps, unavailable prices, unsupported overrides and additional billed units fail readiness. Nothing silently chooses a replacement model. A supplied different returned model fails before its output is applied; missing returned metadata stays unknown.

Input-byte/output/request-fee reservations are made atomically before transport. Routing requires supported parameters, disables fallback and sets documented pricing ceilings. Missing costs and failed requests retain their conservative reservations. Provider-reported zero remains a known zero; missing cost is not zero. Known request costs and reservation totals are distinct. The existing usage ledger records each dispatched attempt without prompt/content capture. Concurrent gateways share one run-local usage-ledger initialization lock.

This is an application admission budget, not an absolute upstream invoice cap. Metadata is only as current as the chosen catalog capture, tokenization/provider behavior still needs actual commissioning, and upstream account/key limits are a separate protection. A dedicated environment-variable name does not itself prove the key belongs to a separately limited account.

## Stop and continuity

Each run has immutable stable logical wakes, private choices/output checkpoints and a single persistent controller token. A stop-aware database transition immediately before transport is the dispatch linearization point: a stop recorded before that transition denies the send. Once dispatch is committed, the work is considered in flight and cannot be cancelled by pretending its cost vanished. A reservation stopped before dispatch is recorded `not_sent`, not as a paid HTTP call.

Returned work can settle metadata and private checkpoints after stop. Undispatched jobs remain visibly stopped, not misleadingly pending. Resume is explicit, preserves the original deadline and only unstops safe jobs. Journal/episode inserts share a transaction with their owner-local dedupe key; committed inquiry receipts and staged source citations can be applied again locally without another model interpretation or duplicate private record.

Process death requires a separate `recover` acknowledgement that the old controller has exited. Recovery revokes its token, marks dispatch-committed unanswered work uncertain and never silently resends it. An unused reservation can settle `not_sent`. A successful response lost before its durable checkpoint remains uncertain rather than prompting a duplicate paid call. Completed runs are not reissued.

Private run files, parents and SQLite sidecars reject preexisting symlinks. Ordinary journal-file creation/removal by another SQLite worker is handled through one stat result, avoiding a false safety failure between stale `exists` and `is_file` probes. These protections are not a sandbox against an administrator who controls the run directory or trusted Python callers who deliberately construct their own transport.

## CLI operation

The private default root is `~/.local/share/paradoxtrader/rehearsals`, outside the repository. Commands below are instructions; no real start was performed during development.

Prepare a credential-free scripted example:

```sh
python3 scripts/rehearsal.py prepare --mode offline
python3 scripts/rehearsal.py start RUN_ID
python3 scripts/rehearsal.py status RUN_ID
```

Use a separate terminal for a requested stop:

```sh
python3 scripts/rehearsal.py stop RUN_ID
```

After a genuine process exit, explicitly recover and then resume only safe work:

```sh
python3 scripts/rehearsal.py recover RUN_ID --confirm-controller-exited
python3 scripts/rehearsal.py resume RUN_ID
```

For a future real session, `models.json` contains either the exact seven-owner mapping or an `agent_models` object. Catalog JSON is the public OpenRouter `{data:[...]}` response. The budget value is a deliberate choice for that session; `YOUR_BUDGET` below is not a preset allowance.

```sh
python3 scripts/rehearsal.py prepare --mode real \
  --models-file /private/path/models.json --fetch-catalog \
  --budget-usd YOUR_BUDGET
```

A prepared real start additionally requires `REHEARSAL_OPENROUTER_API_KEY` supplied privately in the process environment and an explicit flag:

```sh
python3 scripts/rehearsal.py start RUN_ID --allow-real-models
```

The CLI never uses an ambient Manus/OpenRouter key as a fallback. Real resume requires the same explicit arming and key. Neither flag grants trading authority. Keep secrets outside Git and never paste them into a browser build.

To serve only the protected read endpoints locally, first privately supply `LINEAGE_OPERATOR_TOKEN`, then explicitly run:

```sh
python3 scripts/rehearsal.py serve --port 8765
```

This binds to `127.0.0.1`, disables access logging and does not import the ordinary backend. Authenticated GET routes are `/api/rehearsals`, `/{run_id}`, `/{run_id}/jobs`, `/{run_id}/requests` and `/{run_id}/records` beneath that prefix. There is no launch/stop mutation endpoint. Connected browser credential delivery and host deployment have not been commissioned.

## Verification and remaining work

Final validation passed 555 Python tests, including 109 rehearsal-focused regressions and protected FastAPI ASGI reads. All 428 frontend tests passed across 15 files. TypeScript, lint (zero warnings/errors), production build, and all four source/menu/lineage/rehearsal fixture checks passed. The build retains the existing nonblocking warning for the roughly 816 KB on-demand library corpus; it is separate from the initial application chunk.

The guarded complete offline run exercised every allowed action and all seven owners through both rounds. Offline tests cover exact routing, strict output parsing, unknown costs, admission bounds, concurrent controllers, stop-before-dispatch, post-stop checkpoint settlement, interrupted dispatch, local receipt/effect replay, frozen prompts, owner-only reads and symlink/sidecar rejection. Real FastAPI ASGI tests exercise the protected read application without a running server. Frontend DOM tests block networking and cover all eleven routes, stale owner selections and record envelopes.

Validation commands:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/build_rehearsal_fixture.py --check
python3 -B scripts/build_ui_fixtures.py --check
python3 -B scripts/build_lineage_fixture.py --check
python3 -B scripts/import_library.py --check
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

The first paid run, current model availability, credential/account limits, real token/billing behavior and real model differences remain untested. Normal ongoing scheduling, browser login, ordinary market research, all-seven paper execution and Alpaca integration remain separate milestones. This slice adds no trading authority and changes no original identity, scheduler, broker code or global configuration.

## Provider sources

OpenRouter primary documentation checked 2026-11-12: [model catalog and pricing units](https://openrouter.ai/docs/guides/overview/models), [provider routing and price ceilings](https://openrouter.ai/docs/guides/routing/provider-selection), and [returned usage accounting](https://openrouter.ai/docs/guides/guides/usage-accounting). Catalog pricing is USD per token/request/unit; routing prompt/completion ceilings are USD per million tokens. The controller keeps those units separate.
