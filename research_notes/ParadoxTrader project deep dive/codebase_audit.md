# ParadoxTrader Codebase Technical Audit (as of HEAD 3912fd3, 2026-11-14)

Method: everything below comes from reading the repository at `/home/user/ParadoxTrader`, from its git history, and from running commands in a scratch clone (`/tmp/claude-0/-home-user-ParadoxTrader/9696711f-663e-5b1b-903a-8fe53cb77f8b/scratchpad/repo`) and a scratch venv. Nothing in the repository was modified. Each "Source" is a repo file and line, or a command I ran (marked `cmd:`). No web sources were needed or used.

## 1. What the code actually does end to end: module map, line counts, docs-to-code ratio

### Takeaway
There are two separate runtimes. The first is a legacy July-2026 "v2" general runtime: a FastAPI app, a scheduler, an LLM wake loop, an Alpaca wrapper and data feeds. The second is a newer Manus-built (Nov 2026) layer of tightly guarded offline subsystems: inquiry lineage, a mock broker, a usage ledger, a restricted "Sessions/rehearsal" controller, compost and witness. Most new code is defensive plumbing and tests. None of it closes the loop from market data to agent to order.

### Cited Findings
**Line counts (Python, `wc -l`):**

| Area | Lines |
|---|---|
| `main.py` | 267 |
| `core/` | 10,039 |
| `api/` | 1,437 |
| `scripts/` | 1,215 |
| `data/feeds/` | 1,589 |
| `tests/` | 12,304 |
| `agents/` | 0 (14 JSON persona files only) |

Inside `core/`:

| Subsystem | Lines |
|---|---|
| `runtime/` | 5,273, of which `runtime/rehearsal/` is 2,974 |
| `trading/` | 1,944 |
| `memory/` | 835 |
| `usage/` | 663 |
| `library/` | 355 |
| `research/` | 338 |
| `hrv/` | 266 |
| `forum/` | 189 |
| `messaging/` | 124 |

Source: cmd `find <dir> -name '*.py' | xargs cat | wc -l`.
- **Largest Python files:**

  | File | Lines |
  |---|---|
  | `core/runtime/rehearsal/store.py` | 1,253 |
  | `api/app.py` | 847 |
  | `core/runtime/agent_loop.py` | 840 |
  | `core/runtime/rehearsal/controller.py` | 667 |
  | `api/rehearsal.py` | 590 |
  | `core/runtime/inquiry.py` | 471 |
  | `core/runtime/rehearsal/provider.py` | 468 |
  | `core/runtime/llm.py` | 460 |

  Source: cmd `wc -l core/*/*.py ...`.
- **TypeScript:**

  | Item | Size |
  |---|---|
  | `frontend/src` (excluding JSON fixtures) | 3,751 lines |
  | `frontend/tests` | 3,213 lines |
  | `styles.css` | 408 lines |
  | JSON fixtures under `frontend/src` | 954,117 bytes |
  | `library/corpus.json` | 902,595 bytes, bundled into the frontend |

  Source: cmd `find frontend/src ... | wc -l`; `ls -la library/corpus.json`.
- **Markdown:** project docs outside `library/originals` (README, ARCHITECTURE, TODO, the 30+ `docs/*.md` files, frontend README, orientation md files) come to 2,332 lines, about 32,700 words or 263 KB. Separately, `library/originals/` is 2.2 MB: 42 creator documents in md, docx and pdf, of which the md files alone are 9,208 lines. Source: cmd `wc -l`, `wc -w`, `du -sh library/originals`; `ls library/originals | wc -l` = 42.
- **Docs-to-code ratio:**

  | Comparison | Ratio |
  |---|---|
  | Project markdown (263 KB) vs non-test Python (680 KB) + TS source (254 KB) = 934 KB of executable code | about 0.28 by characters |
  | Same, by lines (2,332 vs about 18,300) | about 0.13 |
  | Test code (Python 700 KB + TS tests) vs product code | test chars at or above non-test Python chars |
  | Including the creator's philosophical corpus (2.2 MB) | prose exceeds code about 2.6 to 1 by bytes |

  Source: cmd `wc -c` over each group.
- **What `main.py` is:** a CLI over the legacy runtime. Commands are `run`, `wake`, `forum`, `inbox`, `dm`, `status`, `queue`, `approve`, `reject`, `snapshot`, `countdown` and `init`. `run` spawns seven daemon threads that call `agent_wake` every `wake_interval_seconds` (default 600). Source: `main.py:1-20`, `main.py:184-213`.
- **What one legacy wake does** (`agent_wake`):
  1. Loads the soul/living JSON, HRV state and unread DMs.
  2. Builds a context dict in which market data is hard-coded as `{"status": "not_supplied"}`.
  3. Asks the LLM to pick a number from 1 to 5 out of HRV-costed actions.
  4. Falls back to `rest` if the reply doesn't parse.
  5. Executes the action, which is another LLM call that writes prose into SQLite memory, forum or DMs.

  Source: `core/runtime/agent_loop.py:749-840`, especially `:785-791` and `:818-823`.
- **The `propose_trade` action** only produces prose. It stores the text as a memory episode and returns `{"action": "propose_trade", "content": response}`. There is no structured order, no queue insert and no broker call. Source: `core/runtime/agent_loop.py:474-486`.
- **`core/trading/council.py` (264 lines) is dead code.** It is the only caller of `submit_trade` (`council.py:28`, `:239`), and no module in `core/`, `api/`, `main.py` or `scripts/` imports it. Source: cmd `grep -rn "council" --include=*.py core api main.py scripts | grep import` returned nothing.
- **The newer subsystems are all offline or injected-transport:**
  - **Rehearsal (Sessions):** two rounds, seven agents, a 28-request cap, 1,024 output tokens. Source: `core/runtime/rehearsal/provider.py:28`; `README.md` "bounded nontrading Sessions controller".
  - **Inquiry lineage with idempotent command receipts.** Source: `core/runtime/inquiry.py:269-445`.
  - **Mock broker lifecycle** for the fictional `DEMO270115C00100000`. Source: `core/trading/lifecycle.py:1`, `:24`.
  - **Usage ledger.** Source: `core/usage/store.py`.
  - **Compost and witness.** Source: `core/memory/compost.py`, `core/runtime/rehearsal/witness.py`.
- **Git history:** 43 commits. The first five, by the owner, are the initial upload on 2026-11-10/11. After that come 22 Manus commits (`dev-agent@manus.ai`) across PRs #1–#10, then 3 docs-only PRs (#11–#13) and the Claude GitHub Actions workflows (#14). Source: cmd `git log --format='%an' | sort | uniq -c` (Manus 22, owner 20, GenuineJaded 1).
- **Size of the PRs since the upload:** 203 files changed, +46,885 / −1,428, excluding `library/` and `package-lock.json`. The largest feature PRs:

  | PR | Change |
  |---|---|
  | Compost/witness (#10, `bb162c6`) | +13,018 |
  | Library (#4, `8b6ea28`) | +21,691, mostly corpus |
  | Rehearsal (#8, `801f0e9`) | +6,654 |
  | Continuity (#9, `a3d9bd4`) | +5,440 |
  | Lineage plus mock lifecycle (#6, `b0739f8`) | +5,185 |

  Source: cmd `git diff --stat 3e5c6f3 HEAD`, `git show --shortstat <sha>`.

### Inferences
- Roughly 60% of the Python added in the Manus week went to safety rails, provenance and idempotency around activities that never touch money: rest, journal, compost, witness, library reading, rehearsal. The only trading-relevant new code is the mock broker and lineage, and it is mock-only.
- Two LLM transports, two runtimes and two APIs (`api/app.py` and `api/rehearsal.py`) duplicate concepts. That doubles what any next builder has to understand.

### Gaps
- I did not measure comment and docstring density precisely. A rough grep found about 1,000 comment or docstring-start lines in non-test Python. Many functions carry long prose docstrings about intent, for example `api/app.py:642-654`.

## 2. Do the tests run and pass?

### Takeaway
Yes, everything I ran passed:
- 662 Python tests (plus 1,625 subtests)
- the frontend TypeScript build
- 495 Vitest tests
- the oxlint pass

The tests are almost entirely offline. They use mocks, injected transports and temporary SQLite. They prove internal consistency, not that the system works against any real service.

### Cited Findings
- **Python:**
  - Command: `python3 -m venv venv && venv/bin/pip install -r requirements.txt pytest httpx`, then in the scratch clone `venv/bin/python -m pytest -q -p no:cacheprovider`.
  - Result: **`662 passed, 1625 subtests passed in 45.06s`** on Python 3.13.18 with fastapi 0.162.7, pydantic 2.14.3, yfinance 1.8.0.
  - Source: cmd output.
- **The test suite is not self-describing:** `requirements.txt` has no pytest or httpx, so you must install them separately. Source: `requirements.txt`.
- **Python version mismatch:** `render.yaml` pins `PYTHON_VERSION 3.11`. I tested on 3.13 and did not test 3.11. Source: `render.yaml:8-9`.
- **Test footprint:** 51 test files with 645 `def test` functions. 50 of the 51 files use mocks, monkeypatch, `http_post` injection or "offline" fixtures. Source: cmd `grep -ln "monkeypatch\|mock\|http_post\|offline" tests/*.py | wc -l`.
- **Frontend, from the scratch clone `frontend/`:**

  | Step | Result |
  |---|---|
  | `npm ci` (node v22.23.4, npm 10.9.9) | succeeded |
  | `npm run build` (`tsc -b && vite build`) | succeeded in 322 ms, with a chunk-size warning: `corpus-*.js` 815.83 kB, `fixture-*.js` 584.16 kB, `index-*.js` 367.95 kB |
  | `npm test` (`vitest run`) | **18 files, 495 tests passed** |
  | `npm run lint` (oxlint) | no errors reported |

  Source: cmd output.
- **`npm audit`:** reports vulnerable versions of axios (1.0.0–1.19.0), follow-redirects (credential-header leakage advisories GHSA-q3jh-wrc6-jgq8, GHSA-8r9p-f939-6h3c, GHSA-mrwp-f3q8-3g9p), nanoid <3.3.18, postcss <=8.5.22, react-router 7.12.0–7.18.1 and source-map-js. All have fixes available. Source: cmd `npm audit`.
- **Live smoke test of the legacy API**, in the scratch clone with `DATA_DIR` set to scratch: `uvicorn api.app:app` started, and `/api/status` returned seven HRV states at 100. Within seconds the scheduler tried to wake `tempest` and failed with `ValueError: No OpenRouter API key configured.` Source: cmd uvicorn log; `core/runtime/scheduler.py:28-33`; `core/runtime/llm.py` (`_call_llm_raw` raising at the key check).

### Inferences
- The test suite is a real asset for refactoring safety. But 662 green tests coexist with zero end-to-end paths to a trade, so test count is not a proxy for progress here.

### Gaps
- I did not test under Python 3.11, the version `render.yaml` pins.
- I did not run the frontend in `connected` mode against a live backend.

## 3. Real LLM, broker and market-data integration vs mocks

### Takeaway
The LLM client is real (OpenRouter over HTTP) but has never been run with a key. The Alpaca client is a real but thin REST wrapper, and no reachable code path places an order through it. Real market data exists only as a `yfinance` snapshot shown on an API endpoint, and agents never receive it. Seven of the eight data-feed modules are imported by nothing.

### Cited Findings
**LLM**
- **Legacy client:** `core/runtime/llm.py` POSTs to `https://openrouter.ai/api/v1/chat/completions` with a 90 s timeout, retries and backoff. The key comes from `config.openrouter.api_key` or the `OPENROUTER_API_KEY` env var. It records usage metadata such as tokens and cost to the usage ledger, with optional LangSmith tracing. Source: `core/runtime/llm.py:31`, `:128-133`, `:150-231` (requests.post at about `:198`).
- **Separate rehearsal transport:** `OpenRouterTransport` does one POST with no retries, after a budget reservation, and the HTTP function can be injected for offline tests. Source: `core/runtime/rehearsal/provider.py:299-403`.
- **Perplexity:** a research client is wired into the `research` and `roam` actions when available. Source: `core/runtime/agent_loop.py:258-296`, `core/research/perplexity.py`.
- **Default model:** unset agents default to `deepseek/deepseek-chat`. Source: `core/runtime/config.py:77-78`.
- **Model map not final:** the README says "The actual seven-model map for first arrival has not been finalized or checked against the live catalog." Source: `README.md` (seven participants section).
- **README confirms nothing has run live:** "No actual model-powered agents have been launched, and no Alpaca account has been connected or traded through this build." Source: `README.md:7`.

**Broker**
- **The wrapper:** `AlpacaClient` has account, positions, orders, an options-contracts lookup and `place_option_order` against `https://paper-api.alpaca.markets`, with per-agent credentials. Source: `core/trading/alpaca.py:24-187`.
- **The submit path exists but is unreachable.** `submit_trade` executes directly when `guardrails.autonomous_trading_mode` is true, otherwise it queues the trade. Its only caller is the dead `council.py`. Source: `core/trading/alpaca.py:237-266`; `core/trading/council.py:239`.
- **Approving a queued trade does not place an order.** `approve_trade` only flips the queue status, and the README says "approval itself does not submit an order". Source: `api/app.py:498-508`; `README.md` (mock order lifecycle section).
- **Only live broker use:** read-only position snapshots via `get_cross_agent_positions`, which return `not_configured` without credentials. Source: `core/runtime/agent_loop.py:711-747`.
- **`place_option_order` sends no `client_order_id`.** Unlike the mock lifecycle, the real path has no idempotency on retry. Source: `core/trading/alpaca.py:167-187` vs `core/trading/lifecycle.py`.
- **Weak guardrails:**
  - They use `estimated_value` taken from the proposal dict.
  - The "daily loss" check actually uses current `unrealized_pl`, not a daily realized-plus-unrealized figure.

  Source: `core/trading/alpaca.py:198-229`, `:241-242`.
- **The mock broker is the only "execution" tested:** acceptance, rejection, cancellation, partial fills, lost acks and restart reconciliation for the fictional `DEMO270115C00100000`. Source: `core/trading/mock_broker.py`, `core/trading/lifecycle.py:24`; `README.md` ("This is not an Alpaca adapter").

**Market data**
- **yfinance works live.** In my smoke test, `/api/snapshot` returned `{"vix":19.3,"spy_price":754.37,...,"fear_greed_score":null}`. The CNN Fear & Greed lookup came back null. Source: cmd `curl localhost:8765/api/snapshot`; `data/feeds/free_feeds.py:142`.
- **`get_market_snapshot` is used only by `/api/snapshot` and the `main.py snapshot` command.** Source: cmd grep (`api/app.py:51`, `:527`; `main.py:39`, `:134`).
- **Seven feed modules are imported nowhere,** not in core, api, scripts or tests: `fmp.py`, `polygon.py`, `finnhub.py`, `eodhd.py`, `alpha_vantage.py`, `apify_yahoo.py` and `interzoid.py`, about 1,416 lines in total. Source: cmd `grep -rln "feeds.<module>"` returned nothing for each.
- **Agents are explicitly given no market data.** Wake context sets `"market_data": {"status": "not_supplied"}`, and `action_llm` defaults to the same. Source: `core/runtime/agent_loop.py:790`, `:195`.

### Inferences
- The "numerous financial/data API connections" the README attributes to earlier versions survive as code files. But they were not wired into the agent loop in the bundle either (see section 6), so they were never connected to decision-making.

### Gaps
- I did not test whether any of the seven dormant feed modules still works against its vendor API, because I had no keys.
- I did not verify that the Alpaca options-contract endpoint and parameters in `get_options_chain` match the current Alpaca API (for example, the `feed=indicative` parameter on `/v2/options/contracts`).

## 4. Distance from ONE real agent making ONE paper trade decision on real market data

### Takeaway
Close in raw parts, far in wiring. Every needed primitive exists in some form: an LLM client, a yfinance quote and options chain, an Alpaca paper client and an approval queue. None of them are connected. A focused builder could plausibly close the loop for one agent in a small amount of new code. That is an inference, not something I measured.

### Cited Findings
These are the concrete missing links, each tied to code:
1. **No market data reaches the agent prompt.** Context hard-codes `not_supplied`, even though `get_yf_quote` and `get_yf_options` exist. Source: `core/runtime/agent_loop.py:790`; `data/feeds/free_feeds.py:31-60`.
2. **No structured trade output.** `propose_trade` asks for prose and never parses symbol, quantity, side or limit into an order schema. Source: `core/runtime/agent_loop.py:474-486`.
3. **Nothing enqueues a proposal.** `TradeQueue.enqueue` is called only from `submit_trade`, which is reachable only from the dead `council.py`. Source: `core/trading/alpaca.py:265`; `core/trading/queue.py:60`.
4. **Approval doesn't execute.** No code path goes from an approved queue entry to `AlpacaClient.place_option_order`. Source: `api/app.py:498-508`.
5. **No real-broker idempotency or reconciliation.** The mock lifecycle has both; the Alpaca path has neither (no `client_order_id`, no fill polling). Source: `core/trading/alpaca.py:167-187`; `core/trading/lifecycle.py`.
6. **No configured credentials.** No OpenRouter key and no Alpaca paper keys are set. The legacy config wants seven Alpaca key pairs. Source: `render.yaml:12-39`; `README.md:7`.
7. **The model map is unfinalized.** Source: `README.md` (seven participants section).
8. **The action picker is restrictive.** The LLM must reply with a bare digit matching `[1-5]`, otherwise the wake becomes `rest`. `propose_trade` is one of five HRV-costed options, so a trade decision is never directly requested. Source: `core/runtime/agent_loop.py:806-823`, `:72-130`.

### Inferences
- The shortest path to a working trade:
  1. Write one script that pulls a yfinance chain for one underlying.
  2. Call `call_llm` once for one agent with a JSON-schema prompt.
  3. Validate the reply and write it to `TradeQueue`.
  4. On a CLI approve, call `AlpacaClient.place_option_order` with a `client_order_id`.

  This bypasses HRV, phases, rehearsal, compost and witness entirely. All of the primitives already exist.
- The restricted Sessions controller structurally excludes broker, market and news tools (`README.md`, Sessions section). Its current form therefore cannot be the vehicle for a first trade without redesign.

### Gaps
- I can't confirm that Alpaca paper options trading is enabled on the owner's account(s).

## 5. Code quality: architecture, over- vs under-engineering, dead code, security, deployability

### Takeaway
The newer modules are carefully written and heavily tested, but over-engineered for their purpose. The legacy `api/app.py`, which is what `render.yaml` and `start.sh` actually deploy, is under-engineered and unsafe: it has unauthenticated mutating endpoints, wildcard CORS with credentials, and a scheduler that starts spending as soon as the app boots. The Render disk mount likely breaks the app as well.

### Cited Findings
**Security**
- **Wildcard CORS with credentials:** `allow_origins=["*"], allow_credentials=True, allow_methods=["*"]`. Source: `api/app.py:103-110`.
- **`POST /api/config` has no authentication** and writes any dotted key path into `system.yaml`. In the smoke test I set `guardrails.autonomous_trading_mode=true` with an anonymous curl and got `{"status":"updated",...}`. That is the flag that makes `submit_trade` execute directly at Alpaca. Source: `api/app.py:729-743`; `core/runtime/config.py:73-74`; cmd output.
- **Other mutating endpoints with no authentication:**
  - `POST /api/phase`
  - `/api/countdown`
  - `/api/init`
  - `/api/wake/{agent_id}`, which triggers LLM spend
  - `/api/forum`
  - `/api/dm`
  - `/api/agents/{id}/self-definition`
  - `/innermost`
  - `/journal`

  Source: `api/app.py:449-490`, `:599`, `:656`, `:684`, `:746-831`.
- **Queue approve/reject only checks the operator token for lineage-linked entries.** Plain queue entries can be approved anonymously. Source: `api/app.py:498-521`.
- **`GET /api/config` redaction is name-based only.** It masks keys containing key, secret, token or password. Source: `api/app.py:715-726`.
- **No committed secrets found.** A regex scan for `sk-...`, Alpaca `PK...`, AWS and Postman `PMAK-` patterns came back empty, and `config/system.yaml` is gitignored. Source: cmd grep; `.gitignore:1-6`.
- **The newer read API is better designed:** `api/rehearsal.py` is GET-only and requires `LINEAGE_OPERATOR_TOKEN` with a constant-time comparison. Source: `api/rehearsal.py:1-10`, `:463`; `api/app.py:214-230`.

**Deployability**
- **The scheduler autostarts.** `lifespan` calls `_auto_init()` and then `start_scheduler()` on every boot. The scheduler wakes all seven agents every `wake_interval_seconds` (default 600). With `OPENROUTER_API_KEY` set in Render, deploying starts unattended LLM spend. Source: `api/app.py:94-99`; `core/runtime/scheduler.py:36-62`; `render.yaml:10-13`.
- **The deploy recipe is not approved, by the README's own account:** "starting `api/app.py` can start its scheduler. Do not launch it just to show the dashboard." `render.yaml` and `start.sh` both launch exactly that. Source: `README.md` (two runtime paths section); `render.yaml:7`; `start.sh:15`.
- **The Render disk mount likely breaks imports:**
  - `render.yaml` mounts a persistent disk at `/opt/render/project/src/data`, which is the repo's `data/` directory.
  - That directory holds the Python package `data/feeds/` (including `free_feeds.py`, imported at `api/app.py:51`).
  - `core/data_dir.py` also uses that path as the database directory.
  - Locally, with no override, SQLite databases go into the same `data/` package directory.

  Source: `render.yaml:40-43`; `core/data_dir.py:20-37`; `api/app.py:51`.
- **Inconsistent installs and versions:** `render.yaml` uses `npm install` rather than `npm ci` and pins Python 3.11, while the code was only exercised (by me) on 3.13. `requirements.txt` uses unpinned `>=` ranges and an unversioned `langsmith`. Source: `render.yaml:5-9`; `requirements.txt`.
- **A deployed dashboard shows fixtures, not live data, by default.** The frontend defaults to `preview` (fixture) mode, and `connected` must be opted into at build time with `VITE_RUNTIME_MODE`. Source: `frontend/src/api.ts:11-13`; `README.md` (inspect and test section).

**Architecture**
- **Dead code:**
  - `core/trading/council.py` (264 lines)
  - seven `data/feeds/*.py` modules (about 1,416 lines)
  - the governance scripts `scripts/field_check.py`, `archive_code.py`, `pivot_protocol.py` and `verify_proof.py`, listed in BUILD_STATE as "governance". I did not check whether CI or tests invoke them.

  Source: cmd grep; `docs/BUILD_STATE.md:9-13`.
- **Stale docs:** `docs/BUILD_STATE.md` still says "Phase 4 (in progress)" and lists Alpaca, council and feeds as next steps. The README labels it historical. Source: `docs/BUILD_STATE.md:3-28`; `README.md` (repository map section).
- **Simulated resource economy:** HRV is a "computational resource simulation", and every action has an `hrv_cost` that gates choices. The README itself says it is "not physiology and not the creator's funding allowance". Source: `core/runtime/agent_loop.py:72-130`; `README.md` (cost visibility section).
- **Over-engineering examples:**
  - `core/runtime/rehearsal/store.py` is 1,253 lines for a two-round non-trading rehearsal.
  - Compost/witness (PR #10) adds +13k lines for optional note distillation and an append-only "humble witness".
  - The TODO's acceptance criteria are philosophical ("no personality judgment", "cannot perform therapy/psychology"), not trading outcomes.

  Source: `wc -l`; `git show --shortstat bb162c6`; `TODO.md:3-8`.
- **Code-level quality of the new modules is high:** strict input validation, Decimal cost handling with unknown kept distinct from zero, idempotent operation receipts, lease-based claims. Source: `core/runtime/llm.py:44-95`; `core/runtime/inquiry.py:269-445`.

### Inferences
- The project's main technical debt is not sloppy code. It is misdirected effort: the safety and provenance machinery is in place for activities that produce no revenue, while the trade path has stayed unwired since July.
- The legacy `api/app.py` should not be exposed to the internet in its current state. Anyone who finds the URL can flip autonomous trading and trigger LLM spend.

### Gaps
- I did not deploy to Render. The disk-mount conflict is an inference from the config and from how persistent disks mount over a path; I did not observe it.

## 6. What `ParadoxEdgeTrader_preserved.bundle` contains

### Takeaway
It is a valid git bundle of the July 2026 "Paradox Edge Trader v2" repo (MistreeMoneyTree org): 19 commits and 94 files, with no tests. Every file in it still exists by path in the current repo. It is the code base the owner uploaded on 2026-11-11, so it preserves history but contains no lost features.

### Cited Findings
- **Heads:** `git bundle list-heads` shows `refs/heads/main` at 95b0f9e, `origin/main` at the same commit, and `origin/feature/postman-integration` at bf681fc. The bundle cloned without error. `git bundle verify` needs to run inside a repo and errored when I ran it from a non-repo directory, but the clone succeeded. Source: cmd `git bundle list-heads`, `git clone <bundle>`.
- **Commits:** 19, from 2026-07-14 (`a20508e` "initial foundation") to 2026-08-07 (`95b0f9e` merging the Postman integration). Authors were "Paradox Edge Trader" (the July agent) and MistreeMoneyTree. The commit sequence was:
  1. a web interface plus Render deployment
  2. an Alpaca `/v2` URL fix with seven-account env loading
  3. the Alpha Vantage, Apify-Yahoo, Finnhub, Polygon, EODHD and Interzoid feeds
  4. Perplexity research wiring
  5. LangSmith tracing
  6. model assignments editable in the Config panel
  7. config persistence via `DATA_DIR` "so changes survive on Render"
  8. an innermost journal, self-definition register and cross-agent positions
  9. phase persistence and an auto-init

  Source: cmd `git log --all` in the cloned bundle.
- **Size:** 94 files, 5,676 Python lines, 1,484 TS/TSX lines in `frontend/src`, and zero test files. Frontend views were Agents, Config, Dashboard, Forum, Inbox and TradeQueue. Source: cmd `git ls-tree -r --name-only HEAD | wc -l`; `git ls-files '*.py' | xargs cat | wc -l`.
- **No file is unique to the bundle.** Source: cmd `comm -23 bundle_files repo_files` produced empty output.
- **The trade path was not wired in the bundle either.** Its only `data.feeds` import is `free_feeds.get_market_snapshot` (in `main.py` and `api/app.py`), and its only `submit_trade` caller is `council.py`, which nothing imports. Source: cmd grep inside the bundle clone.

### Inferences
- The richer "API connections" were feed client files plus a Config UI, not an integrated pipeline. So the bundle doesn't hold a working trading loop that was lost.
- The bundle is safe to archive outside the repo. Keeping a 173 KB binary in the working tree adds little.

### Gaps
- I did not diff each file's July content against HEAD to see what Manus rewrote. Same paths does not mean same content. For example, `agent_loop.py` and `llm.py` were heavily modified per PR #1, `ca37d84`.
- Earlier rebuilds, before July 2026, are not in this bundle, so I could not assess them.

## 7. What's worth keeping vs what's a liability

### Takeaway
Keep:
- the OpenRouter client
- the usage and cost ledger
- the queue and lineage schema
- the mock broker's idempotency and reconciliation design, as a template for a real Alpaca adapter
- the yfinance snapshot and options functions
- the library corpus
- the test harness

The liabilities are the unauthenticated legacy API with its autostarting scheduler, the dead feed and council modules, the parallel runtimes, and the very large investment in non-trading ritual subsystems.

### Cited Findings
**Valuable**
- **LLM client:** OpenRouter with retries and precise usage and cost capture. Source: `core/runtime/llm.py:44-130`.
- **Usage ledger:** keeps "unknown cost" distinct from zero. Source: `core/usage/store.py`, `core/usage/pricing.py`; `README.md` (cost visibility section).
- **Mock broker lifecycle:** durable client-order IDs, partial fills, lost-ack recovery and reconciliation, which is exactly what a real Alpaca adapter needs. Source: `core/trading/mock_broker.py`, `core/trading/lifecycle.py`.
- **Trade queue plus lineage store:** proposal, approval, order, fill and position records with stable IDs. Source: `core/trading/queue.py`, `core/trading/lineage/`.
- **Spend caps in the rehearsal provider:** budget reservation before any HTTP call and hard request and token caps. These are reusable for any live run. Source: `core/runtime/rehearsal/provider.py:28`, `:299-403`.
- **Working real data:** yfinance quote and options chain. Source: `data/feeds/free_feeds.py:31-60`; smoke output.
- **Test suites:** 662 Python and 495 frontend tests, all passing. Source: cmd output.
- **The library:** 42 byte-preserved originals with git attributes protecting them. Source: `library/originals/`, `.gitattributes`.

**Liability**
- **The legacy API:** unauthenticated config, phase and wake endpoints plus wildcard CORS with credentials. Source: `api/app.py:103-110`, `:729-831`.
- **Deploy-time behaviour:** the scheduler autostarts at boot. Source: `api/app.py:94-99`.
- **Render config:** the disk mount over the code directory, and an unapproved start recipe. Source: `render.yaml:40-43`; `README.md`.
- **Dead code:** about 1,700 lines (seven feeds plus council) that look like features but are unreachable. Source: cmd grep.
- **Duplicate machinery:** two LLM transports and two runtimes. Source: `core/runtime/llm.py`; `core/runtime/rehearsal/provider.py`; `README.md` (two runtime paths section).
- **Bundle size:** about 1.4 MB of fixture JSON and about 0.9 MB of corpus JSON in the frontend bundle. Source: build output (`corpus-*.js` 815.83 kB).
- **Vulnerable frontend dependencies:** axios, follow-redirects and react-router. Source: cmd `npm audit`.
- **Seven-agent, seven-model, phase and HRV scaffolding** must be understood before a single trade can happen. Source: `core/runtime/agent_loop.py:72-130`; `docs/` (30+ milestone docs).

### Inferences
- The highest-leverage next step is a single-agent, single-underlying, human-approved paper-trade script built from the existing primitives (section 4). That would produce the first real ledger entry, and the existing tests would protect the reused modules.

### Gaps
- No real-money or paper-trading performance data exists anywhere in the repo to evaluate the trading thesis itself.
