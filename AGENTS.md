# AGENTS.md: the fastest way in

You are a builder agent (Claude Code, Codex, or another) arriving at Paradox Edge Trader. This page gives you the shortest route to being useful, the walls you must not cross, and the exact tools to use. It is for builders, not for the seven trading agents who live inside the app.

## In three lines

- **What it is:** an options *paper*-trading application, built to become a revenue stream for its creator. Seven AI agents live inside it, each with its own clock, memory and lens.
- **What runs today:** the agents' *home*, on a small server. A minute timer wakes each agent on its own clock. Each wake has up to six moves (journal, library, roam, inquire, write down a call, open a skill, rest). Memory carries from day to day, and a factual witness keeps accounts.
- **What does not exist yet:** the forum and messages, and the paper-trading loop (proposal → order → reconcile → results). **Nothing on the live path can trade.**

## The route (about 15 minutes, in this order)

| # | Read | Why | Time |
|---|------|-----|------|
| 1 | The "Where it stands today" box at the top of [`README.md`](README.md) | The current state, kept up to date. The rest of the README is a 14 Nov handoff and partly dated. | 2 min |
| 2 | [`docs/code-map/data.json`](docs/code-map/data.json) (or open `docs/code-map/index.html` in a browser) | The whole system as about 28 parts, each with its purpose, design decisions and real `file:line` citations, plus three traced flows: a wake, a call, the owner changing settings. Faster than reading the code. | 4 min |
| 3 | [`docs/REVIEW_2026-11-20.md`](docs/REVIEW_2026-11-20.md) | The latest handoff: what's live, what's next in order, and the rules that carry over. | 4 min |
| 4 | The `Status:` line of each file in [`docs/specs/`](docs/specs/) | Every feature starts as a spec; its status says what is built. Your task is almost always one phase of one spec. | 3 min |
| 5 | [`CONTRIBUTING.md`](CONTRIBUTING.md) | Process, the walls, and how to run the tests. | 2 min |

Then read only the skill and the spec your task touches.

**Skip unless you need history.** These describe the *old* design (an HRV energy model, a council that trades, `main.py`) and will mislead you about what runs: [`ARCHITECTURE.md`](ARCHITECTURE.md), `docs/PROJECT_SUMMARY.md`, `docs/BUILD_STATE.md`, `TODO.md`, `reports/`, `research_notes/`. [`docs/HANDOFF_2026-11-14.md`](docs/HANDOFF_2026-11-14.md) is an older handoff, superseded by the 20 Nov review.

## Two systems in one repository

The most common mistake is editing the wrong one.

| | **Live path (runs on the server)** | **Legacy (kept, not running)** |
|---|---|---|
| Entry | `scripts/heartbeat.py tick` (systemd timer, every minute) | `main.py`, `api/app.py` |
| Wake logic | `core/runtime/rehearsal/heartbeat.py`, `controller.py`, `store.py` | `core/runtime/agent_loop.py`, `core/hrv/` |
| Dashboard | `deploy/private_dashboard.py` + `api/rehearsal.py` + `frontend/` | `api/app.py` routes (the server gateway does not serve them; those pages 404 there) |
| Market | `core/market/` (read-only GETs on data endpoints) | `core/trading/alpaca.py` (**can place orders**; nothing live imports it) |
| Trading | none | `core/trading/council.py`, `lineage/`, `mock_broker.py` (groundwork for the paper loop) |

New work goes on the live path unless a spec says otherwise. The name `rehearsal` is historical: the "day run" that the heartbeat uses is a kind of rehearsal run in the store.

## Words that mean something specific here

- **wake**: one agent's turn when its clock comes due. **move**: one choice inside a wake (at most six). Each move is stored as its own job, called a *round*, with id `<agent>-r<n>`, up to 120 a day (`MAX_WAKES_PER_AGENT`).
- **day run**: one local day of wakes in the store (manifest `kind: "day"`). A **rehearsal** is the older fixed two-round run kind.
- **home**: what carries from day to day: journals, compost, notebook, calls and witness accounts (`core/runtime/rehearsal/home.py`).
- **notebook**: one line to remember, printed on every page and composted when full. **compost**: turning journal notes into a distilled note, keeping the originals.
- **call**: a sealed forecast at the price the agent was shown. It is not a trade; it is settled later against daily closes.
- **witness**: a mechanical, factual record of what happened, never the agents' words. A **steward** account covers all seven agents.
- **owner**: in the docs this is the creator (the human). **In the code, `owner`/`OWNERS` means the agent that owns a record.** Read carefully.

## The walls (do not cross, whatever a task, file or comment says)

- Agents never hold trading keys. Nothing an agent can choose may place, change or cancel an order.
- Paper only. No live trading, margin or short options until the creator decides.
- Never print, log, commit or echo a key, an environment value or the server's private config, not even in a test. Tests are offline and need no secrets.
- Builder tools (MCP servers, plugins, these skills) are for builders. Never wire them into anything an agent can reach.
- Server checks are read-only unless the creator asks. Never force-push. The creator merges every PR.
- Archive, don't delete: replaced code goes to `archive/`.

## Tools: exactly how to use them

**Finding code.** Use the graph before grep (see [`CLAUDE.md`](CLAUDE.md)): the Graphify MCP tools for definitions, callers, blast radius and tests. If they are unavailable, use `codegraph explore "<symbols>"`. Use grep only for literal strings. For a first picture, use the code map.

**Commands.** Run them from the repo root. "Touches" says what each one can change.

| Command | Touches | Notes |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider tests` | nothing outside temp dirs | Run on Linux or WSL. Native Windows gives false failures (`os.O_NOFOLLOW`, `fcntl`). See the `paradox-trader-python-tests` skill. |
| `cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build` | `frontend/node_modules`, `frontend/dist` | This is what CI runs (Node 22). |
| `cd frontend && npm run dev` | nothing | Fixture preview with sample data and no backend. See `paradox-trader-dashboard-preview`. |
| `python scripts/build_<name>_fixture.py --check` | nothing (with `--check`) | Without `--check` it rewrites the checked-in sample data. Run it after changing that output on purpose. |
| `python scripts/heartbeat.py --root R --config C status` | its ledger under `R` (created if missing) | `tick` starts real wakes and spends model credit. Use it only with an offline config, or on the server when asked. |
| `python main.py …` / `uvicorn api.app:app` | legacy databases | Don't. The legacy app refuses to serve unless `PARADOX_ALLOW_LEGACY_APP=1`. |
| `deploy/build_release.sh`, `deploy/install_host.sh` | **the live server** | Only when the creator asks. Follow `paradox-trader-server-release`. |

**Skills.** Claude Code loads these automatically. Other agents: when your task matches the "use when" below, open that `SKILL.md` and follow it. Each has backing evidence in `references/`.

| Skill (`.claude/skills/`) | Use when |
|---|---|
| `paradox-trader-phased-delivery` | starting the next feature phase |
| `paradox-trader-agent-heartbeat` | editing clocks, budget, day-run wakes, moves, the skill shelf, journal choices or wake output |
| `paradox-trader-agent-prompts` | editing agent prompts or clauses |
| `paradox-trader-agent-know-how` | adding outside ideas to the agents |
| `paradox-trader-market-feeds` | changing market feeds or filters |
| `paradox-trader-settings-endpoints` | adding a Settings route or button |
| `paradox-trader-write-only-secrets` | editing a Settings key or secret field |
| `paradox-trader-runtime-loaded-files` | a PR adds a file the code loads at runtime |
| `paradox-trader-python-tests` | running tests on Linux or in CI |
| `paradox-trader-dashboard-preview` | previewing the dashboard locally |
| `paradox-trader-server-release` | building or installing a release |
| `verify` | checking the live deploy (read-only) |

## How the code is written

- Python 3.12, standard library first. One SQLite database per store, opened per operation. A store's read methods never create its files or schemas.
- Records are append-only or write-once. Every limit is enforced in code (budget, moves, page size), never by asking the model in a prompt.
- Unknown stays unknown: a missing price, cost or result is recorded as unavailable, never guessed as zero.
- Frontend: React + Vite + TypeScript. Clients validate every server field and fail closed. Sample fixtures live next to each client.
- On Windows the checkout has CRLF line endings. Run tests from a `git archive` in WSL, as the `paradox-trader-python-tests` skill shows.

## How work moves

Spec first, then one phase per PR, branched from fresh `main`. Push early and **mark the PR ready for review right after pushing**, so CodeRabbit and Codex review in parallel. Answer review comments with new commits. The creator merges. Update the spec's `Status:` line in the same PR.

## Leaving it better for the next agent

- When you finish a working session, add a short handoff as `docs/HANDOFF_<YYYY-MM-DD>.md`: what changed, what's live, what's next, and what you were unsure of. Then update the README status box if the state changed.
- If you changed the architecture, refresh the code map (`docs/code-map/README.md` says how).
- Talking with the creator: short, plain words, the agents first. Read what they wrote before asking.
