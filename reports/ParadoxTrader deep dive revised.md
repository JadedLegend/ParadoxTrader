# ParadoxTrader deep dive, revised

This revision replaces the recommendations in `reports/ParadoxTrader project deep dive.md` wherever the two disagree. The outside research summaries in that earlier report still stand. It treats the repository README and the merged design history as **decision records**, not open questions.

Everything below was checked against the exact current code: `main` at `3912fd3`, which matches this branch apart from the report files.

The decisions it takes as settled:

- **Arrival:** all seven agents arrive together.
- **The witness:** the environmental witness is a factual, bounded observer. It is not an eighth decision-maker and it does not write psychology.
- **No personality grading:** there is no personality scorecard.
- **Order of work:** Alpaca paper access comes after market data, durable order handling and reconciliation, basic risk limits, and observation are working. It is not a default next step.

The sections keep four kinds of statement apart:

- **[Confirmed]:** verified in the current code.
- **[Staged]:** work that exists on the VPS but has not been installed or run. These items come from the README; they cannot be checked from the repository.
- **[Design]:** a proposal in the docs that has not been built.
- **[Recommendation]:** my own suggestion.

## 1. Corrections to the first report

| Earlier claim | Status on `3912fd3` | Correction |
|---|---|---|
| Add personas one at a time, as ablations | Contradicts a decision record | **Withdrawn.** The restricted controller already runs one shared seven-member arrival cohort, with a barrier between rounds and no social head start (`docs/REHEARSAL.md`). Any measurement happens after arrival together. |
| The witness could become the eighth agent | Contradicts a decision record | **Withdrawn.** The README states it is "not an eighth decision-maker, therapist, psychologist, judge, or behavior manager." It is built that way: a mechanical writer filling in a template, with no model call and no writes to agents' memory. |
| "Wire one agent → order intent → Alpaca `mleg` order" in week 1 | Conflicts with the README's sequence and its lineage and recovery boundaries | **Withdrawn as a default.** It bypassed the lineage review, the cost admission budget and the mock-broker recovery contract. The replacement sequence is in section 5. |
| `POST /api/config` has no authentication; the scheduler starts on boot; CORS allows any origin | **Present** in `api/app.py` (lines 729–743, 94–99, 103–110) | Still true. However, this is the legacy broad app. The decided path does not run it: that path is the restricted controller plus `api/rehearsal.py`, which says "never imports the broad app" and has no scheduler. The real hazard is that `render.yaml` and `start.sh` still launch `api.app:app`. See section 5, step 0. |
| The Render disk mount breaks imports | Present in `render.yaml`; never observed | **Downgraded.** It only matters on Render, and the VPS was chosen instead. |
| Seven data-feed modules are "dead code" | **Present.** Nothing outside `data/feeds/` imports FMP, Polygon, Finnhub, EODHD, Alpha Vantage, Apify-Yahoo or Interzoid. | Reworded. They are **unwired client code**, not worthless. Your keys and the limits on those accounts are not in the repo, so I could not assess them. |
| Approving a queued trade places no order | **Present.** `TradeQueue.approve()` only changes a status. `submit_trade` is called only from `core/trading/council.py`, which nothing imports. | Still true, and by design for now. The README says "approval itself does not submit an order." |

## 2. Confirmed implementation facts

**Arrival and sessions [Confirmed]**

- The restricted controller is reached through `scripts/rehearsal.py`, with `prepare`, `start`, `stop`, `recover` and `resume` commands.
- It runs seven fixed owners through two rounds in one cohort.
- Each wake offers only rest, journal, private inquiry, library reading and roam. Broker, market, forum and order tools are "structurally absent."
- Real preparation requires three things:
  - an explicit seven-owner model map, checked against the model catalog;
  - a positive budget in USD that you choose;
  - the dedicated `REHEARSAL_OPENROUTER_API_KEY`. The controller has no fallback to any other key.
- Before any request is sent, the controller reserves its cost against the budget. If the cost is unknown, the reservation is kept rather than counted as zero.
- If the controller process dies, `recover` marks requests that were sent but never answered as uncertain, and never resends them.
- This has only been exercised offline, with a scripted transport. No real model session has run.

**The witness [Confirmed]**

- It writes an append-only factual account to a private `witness.sqlite3` for each run, built from control-store metadata.
- Each agent can read only its own account. The broad account is for the steward (you) and requires operator authentication.
- It makes no model calls, chooses no actions, gives no rewards, writes no agent memory, changes no permissions and places no trades.

**Trading [Confirmed]**

- The lineage store (`core/trading/lineage/`) keeps proposal, review authorization, order, broker-confirmed fill, position and later review as distinct records, each with a stable ID.
- `PaperLifecycle` (`core/trading/lifecycle.py`: `submit`, `reconcile`, `cancel`) drives `MockBroker`, which has `submit_order(client_order_id, structure)`, `lookup_order`, `cancel_order` and `fill_order`.
- Both are tested only with the fictional contract `DEMO270115C00100000` and one Alchemist pilot.
- There is a separate legacy Alpaca wrapper, `core/trading/alpaca.py`. It sends no `client_order_id`, nothing calls it on a live path, and it is **not** the paper adapter the README asks for.

**Inspection and tests [Confirmed]**

- `api/rehearsal.py` is GET-only and checks `LINEAGE_OPERATOR_TOKEN` with a constant-time comparison.
- 662 Python tests and 495 frontend tests pass, all offline.

## 3. Staged but not installed: the VPS

All of this comes from the README's VPS handoff and cannot be verified from the repository.

**The host [Staged]**

- A DigitalOcean Droplet named `EdgeTrader` (Ubuntu 24.04, $15.60/mo with backups).
- SSH login is key-only, and the firewall allows inbound traffic on port 22 only.
- A locked `paradoxtrader` application user exists.

**Uploaded to `/root/paradoxtrader-upload/` but never run [Staged]**

- `release.tar.gz`: the merged `c2f9cb4` source plus a frontend build.
- `install_host.sh`, `private_dashboard.py` (an authenticated gateway that listens only on the server itself) and `backup_data.py`.

**Not yet on the host [Staged]**

- The application's Python environment and service, the backup timer, any credentials, and any prepared session. `/opt/paradoxtrader/releases/` and `/var/lib/paradoxtrader/sessions/` are empty.

**Known open items in the staged drafts [Staged]**

- `StaticFiles` errors should return 404 instead of an unhandled 500.
- Interrupted `.backup-*` folders should be cleaned up, with SQLite handles closed explicitly.

**Access risk [Staged]**

- The deploy private key exists only in the Manus environment.
- If you cannot get it back, add a new public key that you control through the DigitalOcean console.

**One thing I cannot confirm.** The README says the draft gateway "wraps the existing read-only API." The tarball is not in the repo, so I cannot check which API that is. It must be `api/rehearsal.py`. If it is `api/app.py`, the anonymous config write and the scheduler that starts on boot come back.

## 4. Design proposals, not built [Design]

- **A continuing rhythm:** wakes every 15–30 minutes for about 8 hours, then hourly for about 4 hours, then quiet overnight. This is offered availability, not compulsory activity.
- **Durable homes for each owner** and wake dispatch that survives a restart.
- **Opening the forum** roughly one to two weeks after arrival. These are flexible windows, not readiness tests.
- **An evolving interface for names and relationships.**
- **The Evaluation Protocol** (`docs/research/ParadoxEdgeTrader_Evaluation_Protocol.md`) sets the standards for judging results:
  - point-in-time data, with nothing the agents could not have known at the time;
  - results reported after costs;
  - an untouched holdout period;
  - the seven agents are not counted as independent trials.
- **Choices left to you:**
  - when Alpaca accounts are assigned;
  - how much paper capital each one gets;
  - the exact seven model IDs.

## 5. Recommendations, in the README's own order [Recommendation]

**0. Close the latent hazard without new architecture.**

- Mark `render.yaml` and `start.sh` as legacy, or remove them, so that nothing deploys `api.app:app` by accident.
- If the broad app has to stay runnable, make three small changes in place:
  - put the scheduler behind an environment variable that defaults to off;
  - reuse the existing `_require_lineage_operator` check on `POST /api/config` and the other routes that change state;
  - remove `guardrails.*` from the keys the API is allowed to write.
- Confirm the staged gateway targets `api/rehearsal.py`.

**1. Finish the host.**

- Install a key you control, fix the two draft issues listed in section 3, then install and verify the service and backups.
- Keep the broad backend and any scheduling off.

**2. Commission the first real common arrival.**

- Decide the seven model IDs and a budget. Deliver `REHEARSAL_OPENROUTER_API_KEY` to the server privately.
- Then run `prepare` and `start` once, through the restricted controller, with the witness on.
- No Alpaca credentials are needed for this step.

**3. Continuing operation.**

- Wire durable homes and restart-safe dispatch into the existing continuity and usage-ledger paths.
- Use the rhythm above, as offered availability.

**4. Market data, as a bounded read.**

- Choose one of your existing feeds, or Alpaca's free indicative options data, to produce a **frozen snapshot for each wake**.
- Record the snapshot in the run, with its fetch cost counted in the usage ledger.
- Whether agents can see it is your decision. The controller currently makes market tools absent on purpose, so this step changes that.

**5. A reviewed Alpaca paper adapter.**

- Implement the same interface as `MockBroker`: `submit_order(client_order_id, structure)`, `lookup_order` and `cancel_order`, with fills arriving through reconciliation.
- Plug it into `PaperLifecycle`, so orders flow only from a lineage review authorization and reuse the durable client order IDs and restart recovery.
- Test it against the mock contract's test cases first. Turn it on for one account only when you choose to.
- Do not reuse `core/trading/alpaca.py` as the execution path.

**6. Evaluation.**

- Add the missing numbers to the Evaluation Protocol:
  - a minimum trade count;
  - a holdout window;
  - stop and go thresholds;
  - a cost model;
  - a simple rules-only baseline to compare against.
- State whether defined-risk credit spreads are allowed.
- Judge the cohort as a whole, together. No agent is graded on personality.

From the outside research, this still holds: in the studies the first report found, LLM trading agents mostly fail to beat simple benchmarks. The best-supported version of your contradiction idea is that options are usually priced for more movement than actually happens, which is a premium exposed to crashes. Step 6 is where that gets tested honestly.
