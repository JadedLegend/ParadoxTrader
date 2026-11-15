# ParadoxTrader code review, 2026-11-14 (at `99d1736`)

This review replaces both earlier deep-dive reports; you don't need to read them alongside it. Every point is tied to a file and line in the current `main`. Some were run, and those say so. The README's settled decisions are taken as given, so nothing here argues for one-at-a-time arrival, scoring, an eighth decision-maker or early Alpaca activation.

## The short version

- **The new parts are solid.** That means the lineage store, `MockBroker`, `PaperLifecycle`, the rehearsal store and controller, the usage ledger, the GET-only `api/rehearsal.py` and the `deploy/` gateway. They use immutable records, idempotent keys, "unknown" kept distinct from "zero", and conservative accounting when state is uncertain.
- **The old parts are the risk.** These are `api/app.py`, `core/trading/council.py`, the autonomous branch in `alpaca.py`, `scheduler.py` and the plain LLM client. They still ship alongside the new parts, and they bypass the boundaries the new parts enforce.
- **Nothing can currently place an order.** The Alpaca base URL is hard-coded to paper, and `submit_trade`'s only caller, `council.run_council_deliberation`, has no caller of its own.

## Fix before installing on the VPS

| # | Issue | Where | Verified |
|---|---|---|---|
| 1 | Backup pruning deletes **any** directory in the backup folder: manual copies, `lost+found`, or a snapshot with a skewed clock. | `deploy/backup_data.py:72-79` | Reproduced by the reviewer |
| 2 | A backup that finds **no databases** (empty or unmounted data dir) still counts as success, then prunes real snapshots. About 14 days later, no good backup remains. | `deploy/backup_data.py:97-105` | Reproduced by the reviewer |
| 3 | Data locations don't line up. Rehearsals default to `~/.local/share/paradoxtrader/rehearsals`, while the dashboard and backups read `/var/lib/paradoxtrader/sessions`. `QUEUE_DB` is hard-coded to `<repo>/data/` and ignores `DATA_DIR`. Real runs could end up invisible and never backed up. | `scripts/rehearsal.py:21`, `core/trading/queue.py:12`, `deploy/README.md` | Read |
| 4 | The legacy app is only locked inside `start.sh`. Running `uvicorn api.app:app` bypasses that lock. The app also allows requests from any origin and has unauthenticated POSTs: wake (spends credit), forum, dm, phase, init, countdown, self-definition (rewrites `soul.json`), and legacy queue approve or reject. Any web page you visit could POST to `localhost:8000`. | `api/app.py:112-117, 457-835`, `start.sh:8-13` | Read |

Suggested fixes:

1. Prune only names matching `^\d{8}T\d{6}Z$`, and never the snapshot just written.
2. Exit non-zero, without pruning, when zero databases are found.
3. Document `sudo -u paradoxtrader … --root /var/lib/paradoxtrader/sessions`, and derive `QUEUE_DB` from `DATA_DIR`.
4. Add an import-time guard in `api/app.py`, and leave `api/app.py` and `start.sh` out of the release tarball.

## Latent hazards in the legacy code, worth deleting rather than fixing

- **`alpaca.submit_trade` skips every safety step.** When `guardrails.autonomous_trading_mode` is true, it calls `place_option_order` directly, bypassing the queue, review, lineage and `PaperLifecycle`. The size guard reads the proposer-supplied `estimated_value`, which defaults to `0` (`alpaca.py:237-262`, confirmed at line 244). The daily-loss check uses total `unrealized_pl`.
- **The legacy LLM path has no spend ceiling and re-bills on retry.** `_call_llm_raw` makes 3 attempts on any exception, including after a billed 2xx with a bad body (`core/runtime/llm.py:187-240`). The budget and one-attempt rules exist only in the rehearsal provider.
- **`/api/agents/positions` ignores the sharing policy.** It returns every agent's raw Alpaca positions regardless of `share_peer_positions`, and each wake polls Alpaca whenever credentials exist (`agent_loop.py:711-745`, `app.py:652-661`).
- **Parallel systems.**
  - `council.py` duplicates the lineage and rehearsal flow.
  - `scheduler.py` wakes agents in a fixed order with tempest first, which is in tension with arriving together. It has no per-agent lock, so overlapping wakes can overwrite each other's HRV state.
  - There are two snapshot validators with different rules (`lifecycle.py:50` and `projections.py:13`).

Recommendation: move `council.py`, the autonomous branch and the legacy scheduler to `archive/`. Then move the budget and no-retry rules into the shared call path, so the first real arrival inherits them.

## Correctness bugs (small, cheap)

- **`decimal_text` writes round numbers in scientific notation.** A `--budget-usd 10` is stored and shown as `1E+1` (`core/usage/pricing.py`). *Confirmed by running it.*
- **Forum and message threads return the oldest N rows.** They use `ORDER BY created_at ASC LIMIT ?`, so the dashboard freezes after 50 posts (`core/forum/store.py:91`, `core/messaging/store.py:69`). *Confirmed.*
- **`ThresholdMemory.condense` swaps its fields**, printing content where the phase should be and the phase where the title should be (`core/memory/engine.py:278`).
- **The rehearsal store trusts the caller's `reserved_usd`.** `"0"` is accepted, and `finish_request` never checks cost against the reservation (`rehearsal/store.py:1101-1145`). The OpenRouter transport computes the reservation correctly, but the store's claim that it enforces bounds independently is not true.
- **Legacy queue rows can be flipped between approved and rejected**, and a missing ID returns success (`queue.py:99-127`).
- **`main.py approve` prints "approved" even when nothing was approved.**
- **Peers can read operator reviewer notes.** Community-visible lineage reads include them (`lineage/reads.py:62-95`). This may be intended, but those notes aren't written by agents.
- **`PaperLifecycle` has no size or notional limits.** It allows up to 1e6 quantity at a 1e6 price, and `_apply` turns any exception into an unexplained `failed` (`lifecycle.py:138-146`). Today the DEMO-symbol restriction keeps this safe. Set the limits before the paper adapter goes in behind it.

## Tests

- **Python, on this Windows PC: 388 failed, 292 passed, 16 errors.**
  - About 880 of the error lines are platform-related. They are missing `os.fchmod` and `os.O_NOFOLLOW` on win32, plus Windows file locks during temp cleanup.
  - About 60 are assertion failures. Some look like line-ending differences, for example `438 != 384` on byte lengths.
  - The handoff reports 678 passing on Linux. I could not confirm that here, because WSL Ubuntu has no pip and Docker Desktop wasn't running.
  - **Implication:** you can't run the core suites on your own machine. Either make the permission calls portable (skip `fchmod` and `O_NOFOLLOW` on win32) or always test in WSL or a container.
- **Frontend.**
  - Type-checking, lint and build are clean.
  - vitest shows 487 to 493 of 495 passing, with failures that come and go. `tests/rehearsalApi.test.ts` times out at 5 s under the full suite but passes alone (37/37).
  - The build bundles the private library corpus as an 815 kB chunk, so never deploy `dist` publicly.
- **Missing tests** for the bugs above:
  - `submit_trade` with a missing `estimated_value`;
  - `get_thread` past its limit;
  - `reserve_request` with `"0"`;
  - the legacy queue flip;
  - `condense`;
  - backup pruning with a foreign directory and with an empty source.

## Frontend notes

- Every endpoint the UI calls exists on the backend.
- Behind the new gateway, only `/api/rehearsals*` is proxied, so the Dashboard, Forum, Queue, Config, Library, Usage and Lineage views will 404. That's consistent with connected mode not being deployed yet.
- **Config's "trades execute automatically" toggle** can never succeed, since `guardrails.*` returns 403. It silently does nothing in preview. Remove it or label it.
- **Approve and Wake buttons** carry no text saying what they do or what they cost.
- Loading, error and empty states are strong throughout, and no secrets are in `src`.

## Security hardening for when the agents and keys arrive

- **`dashboard.env`:** make it 0600 `root:root` and add `InaccessiblePaths=/etc/paradoxtrader`. Run the future key-holding controller as a separate Unix user.
- **Gateway password check:** the PBKDF2 check (390k rounds) runs on every request inside the event loop, which stalls it for seconds. Move it to a thread and issue a session cookie after one successful login.
- **Install:** use pinned, dashboard-only requirements, extract to a temp directory and verify before moving into place, and pass `--no-same-owner`.
- **systemd:** add `CapabilityBoundingSet`, `RestrictAddressFamilies`, `SystemCallFilter` and related settings, then run `systemd-analyze security` on the host.
- **Smaller items:**
  - a NUL byte in the path returns 500 instead of 404 (`private_dashboard.py:131`);
  - non-HTTP connection types pass the auth gate without a check;
  - `.github/workflows/postman-publish.yaml` pipes `curl | sh` while holding a key, and looks malformed.
- **Clean:** no secrets anywhere in the tracked tree or the git history; tokens are compared in constant time and never logged; static file serving blocks path traversal.

## What the earlier deep dive got wrong

- **It was out of date on its own headline.** The render and `start.sh` hazard was fixed in `ee182a8`, after the revised report, but the report still tells you to fix it.
- **It missed the real remaining exposure:** the unauthenticated legacy routes and the open cross-origin policy.
- **"662 + 495 tests pass" was copied from the README, not rerun.**
- **Its "no path takes market data to an agent" is too strong.** `free_feeds.get_market_snapshot` is imported by `main.py` and `api/app.py`.
- **The first version argued against settled decisions:** one-at-a-time personas, Alpaca in week 1, and "the environment is the problem". The revision withdrew them, but it is a diff on the first report, so the two have to be read together.
- **It skipped things that matter now:** `deploy/`, the frontend, the materials intake, and the open question of who approves trades.

## The path to the first real arrival (README order, with the actual blockers)

1. **Host.** Restore owner SSH access through the DigitalOcean console, fix backup items 1–3 above, then follow `deploy/README.md`.
2. **Models and budget.** Choose the seven exact model IDs, checked against the live OpenRouter catalog, and set a USD budget. Fix `decimal_text` first so the budget displays correctly. Deliver the OpenRouter key privately to `/etc/paradoxtrader/`.
3. **Arrival.** Run `scripts/rehearsal.py prepare/start` as `paradoxtrader` with `--root /var/lib/paradoxtrader/sessions`.
4. **Continuity, market data, paper adapter, evaluation:** unchanged from the README. Archive the legacy trading and scheduler code before step 6, so only one order path exists.

Decisions that are yours to make:

- the seven model IDs;
- the budget;
- whether the `doxtrade` collection joins the library (see `materials/incoming/README.md`);
- how trade approval works when no person signs off.
