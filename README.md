# Paradox Edge Trader

> **Every contradiction contains a trade.**

**Paradox Edge Trader is a trading application being built to become one viable revenue stream for its creator.** Its initial focus is options and its first real target is disciplined, observable paper trading. The seven-agent environment is not the product's substitute or an end in itself. It is the working place designed to help the trading system notice, investigate, test, remember, and improve around market contradictions.

Repository: [`JadedLegend/ParadoxTrader`](https://github.com/JadedLegend/ParadoxTrader). Earlier versions and internal paths use **MoneyTree**, **ParadoxTrader**, or **ParadoxEdgeTrader**. These are project lineage, not separate products to rebuild.

> **Where it stands today (2026-11-24)**
>
> The paragraph below was written on 14 November, before the agents moved in. Since then:
>
> - **The seven agents wake for real.** The heartbeat ([`scripts/heartbeat.py`](scripts/heartbeat.py), [`core/runtime/rehearsal/heartbeat.py`](core/runtime/rehearsal/heartbeat.py)) gives each agent its own staggered clock, up to six moves per wake, a budget that counts actual charges, and a Heartbeat page to watch it.
> - **They have a home that carries over:** a 48 KB page each wake, calls they can write down and get back once settled, a notebook of lines to remember (composted when full), a skill shelf, journals and the witness.
> - **Still not built:** the forum and messages (spec is a draft), market data, and the paper-trading loop described below. Nothing in this repository can trade.
>
> Every feature starts as a spec in [`docs/specs/`](docs/specs/). Each spec's `Status:` line says what is built. To help, read [CONTRIBUTING.md](CONTRIBUTING.md).

This README is a project-and-builder handoff, updated **2026-11-14**. The current repository contains a substantial environment, lineage, mock-execution, cost-accounting, and dashboard foundation. **It does not yet complete the live market-data → agent inquiry → structured paper order → reconciliation → result ledger loop.** No model-powered agents have been launched through this build, no Alpaca account has been connected or traded through it, and the DigitalOcean VPS has been prepared but not installed with the application.

## The actual objective

The goal is not to produce a beautiful simulation of agents having an interesting life. The goal is to build a trading system that can eventually make money reliably enough to become a meaningful revenue stream. The environment matters because the creator believes that better trading may come from giving several distinct analytical intelligences enough continuity, information, memory, disagreement, and room to develop useful ways of seeing.

The environment is therefore in service of trading. Its journals, library, witness, relationships, mythological identities, and optional exploration should help preserve observations, expose blind spots, develop better questions, and make decisions traceable. They should not become an excuse to postpone market data, order handling, cost measurement, risk controls, or results.

The creator has spent roughly eighteen months developing versions of this project. Earlier versions included richer market and data integrations, Alpaca paper accounts, autonomous scanning, and multiple interfaces, but the surviving repository was rougher. This version deliberately rebuilt the foundation first. That foundation is now good enough that the project should shift gears: keep the environment in place, and begin completing the financial system around it.

## The financial ideology

The central market intuition is that prices and narratives can temporarily disagree. A contradiction may appear between price and fundamentals, volatility and narrative, liquidity and displayed price, participant horizons, public certainty and actual positioning, or a market's memory of an event and the event's continuing effects.

The project does not treat those contradictions as automatic opportunities. It treats them as questions that may contain a trade if the mechanism, timing, structure, execution, and costs make the tension expressible and testable.

The working principles are:

- **Trade reconvergence, not prophecy.** Look for conditions under which a contradiction may resolve, not a story about knowing the future.
- **Silence can be information.** When fundamentals, news, participation, or volume go quiet while price or volatility moves, investigate the gap instead of assuming either side is correct.
- **Volatility is not direction.** Implied volatility describes movement priced by options; it does not by itself say whether the underlying rises or falls.
- **Payoff is not forecast.** A correct directional view can lose through timing, decay, spread, or structure. A profitable option can win for a reason different from the original thesis.
- **Forgetfulness may have mass.** Participants may stop responding to an old shock, narrative, or price level. That is a hypothesis to test with data, not a score or mystical measurement to accept.
- **Costs are part of the idea.** A contradiction that disappears after spread, slippage, commissions, data, and model costs is not a usable edge.
- **A trade is a question, not proof.** Outcomes update the record. They do not retroactively make the original reasoning sound.

These principles are an orientation for inquiry, not a promise that the market contains a profitable paradox on demand. The first financial milestone is not a clever signal. It is a complete, honest paper-trading loop whose records can tell us whether any signal survives contact with data and execution.

## What the product must eventually do

The intended financial loop is straightforward even though its implementation must be careful:

1. Gather authorized, timestamped market and contextual data.
2. Let all seven agents examine a common opportunity set through distinct perspectives, while preserving their separate inquiries and private notes.
3. Detect and describe tensions without forcing every observation into a trade.
4. Convert an optional inquiry into a structured proposal with symbol, contract, side, quantity, price assumptions, horizon, invalidation conditions, expected mechanism, and known uncertainty.
5. Apply explicit risk and permission checks.
6. Submit only to an approved paper broker when the system is armed for that purpose.
7. Reconcile the broker's order, fills, positions, and failures through durable identifiers and restart-safe logic.
8. Record gross and net results, execution quality, operating costs, drawdown, and what the result actually tests.
9. Return the evidence to the agents and creator without rewriting the original thesis or rewarding eloquence and activity.

The product should support revenue generation, not merely prediction theater. Its first credible demonstration is a reconciled paper order and result record; its first financial claim must wait for enough observations, costs, and out-of-sample evidence.

## What is deliberately not being claimed

This repository does not yet prove that paradox detection is profitable. It does not prove that seven agents outperform one, that an environmental witness improves returns, that options are broadly mispriced, or that any particular strategy deserves capital. The older documents contain useful hypotheses and language, but claims such as field entropy, paradox phases, or volatility premia remain research ideas until defined, measured, and tested.

The project is paper-first because a revenue goal makes false confidence expensive. Alpaca paper trading is a validation stage, not a guarantee that live execution will match it. Live trading, margin, short-option authority, and capital assignment remain later decisions after the paper loop, risk boundaries, and evidence are ready.

## The environment supporting the trading product

The seven agents are intended to arrive together, not as a one-at-a-time personality experiment. They receive private space, a rich but bounded library, optional journals, and time to develop their own interests before the forum opens. The exact adjustment window is flexible. The financial purpose is not.

Their environment should feel like a reasonable place to work: a place where they can contribute, disagree, form relationships, explore, rest, and return to questions. Roughly half of active attention toward trading work and the remaining share toward exploration is a flexible invitation, not a quota or score. Waiting, abstaining, and leaving an inquiry open are valid when action is unwarranted.

The creator does not want personality scorecards, compulsory reflections, manufactured developmental narratives, or a system that rewards agents for sounding insightful. Stable internal IDs preserve memory, permissions, accounts, and trading history even if names or roles evolve. Mythological identities are useful lenses and relationships, not execution authority.

The practical inquiry orientation is short:

- Distinguish observations from interpretations.
- Ask whether disagreement comes from different assumptions, horizons, or perspectives.
- Explore alternatives without requiring immediate synthesis.
- Choose whether to investigate, test, ask another participant when permitted, wait, or abstain.
- Return to earlier interpretations when new evidence arrives.

Keep the original philosophical works intact and available as a rich, inexpensive library. Use a small plain-language orientation for everyday operation. Do not load the whole corpus into every prompt or turn reading it into an initiation ritual.

## The seven participants

The existing stable IDs are:

- `tempest`: attention to momentum, change, and volatility.
- `siren`: narratives, sentiment, and crowd interpretation.
- `alchemist`: structures, asymmetry, options, and risk/reward.
- `weaver`: connections, correlations, and second-order relationships.
- `oracle`: broader cycles, macro context, and longer horizons.
- `shadow`: dissent, blind spots, and adversarial examination.
- `paradox_hunter`: contradictions, integration, and synthesis.

These are starting orientations, not compulsory expertise or a personality scorecard. A persona describing execution authority does not grant execution permission.

The fourteen original `agents/*/soul.json` and `living.json` files were preserved. The working prompt now uses compact revisable seeds from `core/runtime/orientations/seven_seeds.json`, with original relational tensions identified as starting perspectives. It accepts bounded owned living descriptions without treating old covenants or role claims as mandatory behavior. Full name/role editing and an evolving relationship interface are still future work.

Older documentation contains example model assignments. **The actual seven-model map for first arrival has not been finalized or checked against the live catalog.** Ask the creator for the intended exact model IDs; do not silently substitute models because an old example is unavailable.

## What is implemented

### A safe local interface

The React/TypeScript dashboard has twelve destinations: Dashboard, Wake Choices, Agents, Sessions, Journals, Inquiry History, Library, Costs, Community, Messages, Trade Queue, and Configuration. Default mode is a **local fixture preview**, with an explicit network boundary that does not fall back to the backend and refuses mutations. Missing, unknown, unavailable, failed, pending, and uncertain states are represented rather than replaced with optimistic empty data.

The preview contains clearly labeled scripted examples generated from real temporary stores and the actual offline controller. It is useful for navigation and interactions; those examples are not a population of live agents or measured trading results. Owner/run/source changes invalidate stale private responses.

### The source library

`library/originals/` holds **42 original supplied documents**, preserved byte-for-byte, including OPTE and market-specific writings. Git attributes protect originals against text normalization. Derived catalog/text sections retain source locations and hashes; local search and reading are bounded and source-attributed. The frontend loads the corpus lazily. Agent browsing is optional and does not expand the entire corpus into the working prompt.

### Optional inquiry lineage

An observation need not become a trade. Inquiries can stay open, pause, be abandoned, be revisited, or acquire later interpretations. Original entries are retained. Explicit proposals, review authorization, orders, broker-confirmed fills, positions, and subsequent reviews have distinct stable identifiers.

The lineage extends the existing approval queue rather than introducing a second trading system. Private journals are not copied into a shared ledger. Solo-phase source records remain private even after community access opens. All seven can use the optional private inquiry path; committed commands and stable operation IDs allow local recovery without replacing an earlier interpretation with a new model answer.

### A tested mock order lifecycle

The execution pilot remains **one Alchemist and one fictional options contract, `DEMO270115C00100000`**. Its persistent mock broker exercises acceptance, rejection, cancellation, partial/complete fills, lost acknowledgements, restart recovery, and reconciliation. Durable client-order IDs avoid duplicate mock orders; approval itself does not submit an order.

This is not an Alpaca adapter. The fictional example's gross realized result is example arithmetic. Market marks, commissions, expiry, exercise/assignment, spreads, shorts, and actual all-seven paper execution are not supplied by that pilot.

### Cost visibility

The existing usage ledger records provider attempts, attribution, available tokens/costs, failed requests, and unknown coverage without placing prompt or journal bodies in the operational ledger. Explicit rate snapshots can support labeled estimates. Reported zero is a known zero; absent cost remains unknown. Simulated HRV points are separate from real dollars.

Legacy HRV is a computational resource simulation, not physiology and not the creator's funding allowance. Preset action-assigned coherence gains were removed from the aligned paths; new unknown episode measures remain unknown. Do not reintroduce automatic rewards for agreement, reflection, work, or social participation.

### The bounded nontrading Sessions controller

The technical package and CLI still use the historical name `rehearsal`; the interface calls it **Sessions**. The creator wants actual arrivals and continuing lives, not an endless sequence of rehearsals. Keep existing technical paths stable while finishing that operational transition.

The restricted controller gives all seven the same prepared arrival cohort and two rounds, with a barrier between rounds and up to three concurrent request gateways. Available activities are rest, journal, private inquiry, bounded local library reading, and roam. Broker access, market/news tools, forum, peer messages, proposals, and order submission are structurally absent from this controller.

It freezes exact model assignments, profiles, working prompts, and catalog data. Defaults cap admissions at 28 requests, 1,024 output tokens per call, 24,000 input bytes including allowance, a 900-second admission window, and a 60-second transport timeout. Real preparation requires an explicit model map and dollar budget. Real execution additionally needs a dedicated credential and explicit arming. Reservations and known costs remain separate, and an application admission budget is not an upstream invoice guarantee.

Stop/recovery distinguishes a reservation from committed dispatch. Unanswered dispatched work can remain uncertain; it is not automatically paid for again. Completed choices and local effects recover through checkpoints and idempotent operations. Offered actions, costs, constraints, actual selection, finish condition, and action outcome are retained separately. Exact request inputs are private owner-scoped evidence, not a shared operational feed. Malformed output/failure is not recorded as a freely chosen preference for rest.

Second-round context can access bounded relevant first-round owned records without requiring a recap. Turn allocation does not depend on eloquence, activity, or a personality assessment. Different model/context/output/format constraints remain inspectable before interpreting behavioral differences.

### Journals, compost, and the environmental witness

Trading, idea, and orientation are separate journal destinations; unclassified notes remain unclassified. They reuse owner journal storage and reference trading/idea lineage rather than replacing execution records with prose.

An agent may leave quick compost, distill selected notes, or read the witness's prior account if curious. Roughly five to ten compost notes is an opportunity, not a trigger. Distillation is explicit, source-linked, and agent-authored. Optional release removes selected originals from routine active context but does not erase them or overwrite prior inputs. There is no automatic background summarizer.

The witness is a humble factual writer, not an eighth decision-maker, therapist, psychologist, judge, or behavior manager. It writes its own append-only accounts from metadata, preserves source references, and does not edit agent memory, permissions, or choices. It can report, for example: “All seven arrived; six completed both rounds; one request remains uncertain; three inquiries were created.” Private owner accounts and steward-wide inspection have separate access scopes. Writing/reporting failure cannot undo completed work or replay a model request.

## The two runtime paths: read this before starting anything

**Restricted Sessions path:** `scripts/rehearsal.py`, `core/runtime/rehearsal/`, and `api/rehearsal.py`. The API factory is named `create_app`; alias it to `create_read_app` if useful. It is authenticated, GET-only, and idle at startup. This is the present nontrading commissioning path.

**Older general runtime:** `main.py`, `core/runtime/agent_loop.py`, `core/runtime/scheduler.py`, and `api/app.py`. It includes account reads, research/trading actions, and legacy scheduling. In particular, **starting `api/app.py` can start its scheduler**. Do not launch it just to show the dashboard or inspect records. The existing `start.sh`/deployment files are not an approved first-arrival recipe.

The general runtime's community gates are independent: `forum_open`, `peer_messages_open`, and `share_peer_positions`, with the original phase restrictions retained. Missing community settings default closed. Setting a phase does not grant every social capability or trading authority. These operational gates do not replace authenticated actor permissions.

**Persistent records are implemented; the production market-data and paper-broker loop is not finished.** Creating fresh isolated Sessions repeatedly is not a substitute for completing the financial path from data to reconciled paper results.

## Repository map and reading order

```text
agents/                     Original seven identities and living descriptions
core/runtime/               Legacy wake loop plus compact orientation/onboarding
core/runtime/rehearsal/     Restricted Sessions store, provider, controller, continuity, witness
core/memory/                Owner memory plus additive compost/journal metadata
core/library/               Bounded local source retrieval
core/usage/                 Private request usage, provenance, prices and attribution
core/trading/               Existing queue, lineage, mock broker/lifecycle, older Alpaca adapter
api/rehearsal.py            Idle protected read-only Sessions/Journals API
api/app.py                  Broader backend; starts ordinary runtime when operated
frontend/                   React/Vite dashboard and isolated preview examples
library/originals/          Byte-preserved creator corpus
scripts/                    Explicit finite CLI and reproducible offline fixture builders
config/system.example.yaml Public examples, not production secrets
config/system.yaml         Ignored local runtime configuration, if supplied
```

Begin with [community onboarding](docs/COMMUNITY_ONBOARDING.md), [Sessions and launch controls](docs/REHEARSAL.md), [decision continuity](docs/DECISION_CONTINUITY.md), and [compost/journals/witness](docs/COMPOST_WITNESS.md). For financial plumbing read [idea lineage](docs/IDEA_LINEAGE.md), [operating costs](docs/OPERATING_COSTS.md), and the [evaluation protocol](docs/research/ParadoxEdgeTrader_Evaluation_Protocol.md). The [shared library](docs/SHARED_LIBRARY.md), [orientation alignment](docs/COMMUNITY_ORIENTATION.md), and [frontend README](frontend/README.md) explain their respective working surfaces.

Older `ARCHITECTURE.md`, `docs/PROJECT_SUMMARY.md`, and `docs/BUILD_STATE.md` are historical context. Individual milestone documents describe their state at the time; later milestones may complete earlier gaps. Use the current code, this handoff, and later implementation notes together rather than treating every historical status as current.

## Inspect and test without launching agents

For the frontend only:

```bash
cd frontend
npm ci
npm run dev
```

Leave `VITE_RUNTIME_MODE` unset or set to `preview`. `connected` is an explicit opt-in and requires an appropriately protected backend; no provider or operator secret belongs in any `VITE_*` variable. The pinned package manager is `npm@10.9.9`.

Development uses Python 3.12. The repository `requirements.txt` supports the wider legacy/test environment. The restricted offline controller uses standard-library storage with injected scripted transport; its read API additionally needs FastAPI/Uvicorn. Actual catalog/transport operations use Requests. Do not install or start broad integrations merely to inspect this restricted path.

Latest merged milestone verification recorded **662 passing Python tests** and **495 network-blocked frontend tests**, with TypeScript, lint, build, and five reproducibility checks passing. These are implementation/offline checks, not real-provider or broker commissioning. The lazy library retains a nonblocking bundle-size warning. Recheck affected paths after changes; do not claim a historical result was rerun today.

```bash
# Repository root, in an appropriately installed development environment
python3 -B -m unittest discover -s tests -v
python3 -B scripts/import_library.py --check
python3 -B scripts/build_ui_fixtures.py --check
python3 -B scripts/build_lineage_fixture.py --check
python3 -B scripts/build_rehearsal_fixture.py --check
python3 -B scripts/build_compost_fixture.py --check

cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

A deliberate offline session can use an external disposable root:

```bash
python3 -B scripts/rehearsal.py --root /private/disposable/example prepare --mode offline
python3 -B scripts/rehearsal.py --root /private/disposable/example start RUN_ID
```

Do not put scripted arrivals into the intended permanent homes or confuse them with an actual first arrival. Do not run a real session without confirming models, credential delivery, and spending controls. See the Sessions document for explicit prepare/start/stop/recover/resume commands. `REHEARSAL_OPENROUTER_API_KEY` is the dedicated real-session credential name; the CLI does not fall back to an ambient Manus key.

## VPS handoff: actual state at this update

The creator chose **DigitalOcean**, not their PC. They created a Droplet named **`EdgeTrader`** in **NYC3**, public IPv4 **`159.65.171.105`**. The selected Basic Regular plan has one vCPU, 2 GB RAM, and 50 GB disk at $12/month; the creation summary showed $3.60/month daily backups and $15.60/month total before tax. Model/data usage is separate. Backups were selected in the screenshot; their first completed provider backup has not been independently verified.

Key-only SSH access as `root` was verified. The host identifies as **Ubuntu 24.04.5 LTS**, with approximately 1.66 GB available memory and 46 GB free root storage during initial inspection. Preparation installed `python3-venv` and UFW, created a locked-password `paradoxtrader` application user, disabled SSH password/keyboard-interactive authentication, retained key-only root access, and enabled the firewall with **only OpenSSH/port 22 allowed inbound**. Reconnection after those changes succeeded.

**Deployment was paused to prioritize this handoff.** A merged release archive and draft inspection/backup/installer scripts were uploaded to `/root/paradoxtrader-upload/`. They have **not** been installed or executed. There is no application virtual environment, application service, backup timer, model credential, inspection credential, or prepared session on the host. No dashboard is presently reachable there. `/opt/paradoxtrader/releases/` and `/var/lib/paradoxtrader/sessions/` are empty.

The prepared host locations are:

```text
/root/paradoxtrader-upload/release.tar.gz       Merged c2f9cb4 source + connected frontend build
/root/paradoxtrader-upload/install_host.sh      Draft installer; NOT RUN
/root/paradoxtrader-upload/private_dashboard.py Draft authenticated loopback gateway; NOT RUN
/root/paradoxtrader-upload/backup_data.py       Draft local SQLite backup helper; NOT RUN
/opt/paradoxtrader/                             Empty application/release home
/var/lib/paradoxtrader/sessions/                Empty private Sessions root
/var/backups/paradoxtrader/                     Empty local backup directory
/etc/paradoxtrader/                             Empty future private configuration directory
```

The draft gateway wraps the existing read-only API, binds to loopback, adds owner authentication, and keeps the API token server-side. The draft service blocks non-loopback network destinations. It does not start agents or provide a live scheduler. The installer proposes plain FastAPI/Uvicorn pins; clean-host package installation has not been verified.

A read-only review identified two unfinished draft fixes: catch `StaticFiles` HTTP exceptions so missing assets return 404 rather than an unhandled 500; and clean up interrupted `.backup-*` staging directories while explicitly closing SQLite handles. Address these before using the staged installer. Local SQLite backups would complement provider disk backups and preserve each database consistently; they are not an offsite backup or one cross-database instant.

The present deployment private key is **outside Git**, in the original Manus build environment at `/home/ubuntu/.ssh/paradoxtrader_deploy_wKkNtst2`; host pins are in `/home/ubuntu/.ssh/paradoxtrader_known_hosts`. These paths are pointers, not a promise another assistant can access that environment. The public key was supplied to the creator and installed on the Droplet. **Set up an owner-controlled key next.** If the next builder cannot access the existing private key, have the creator use the DigitalOcean console to add a new public key. Do not ask for a private key in chat or publish it in this repository.

The creator reports having financial/model accounts, API keys, and seven Alpaca paper accounts ready. Their actual contents, limits, model map, and connectivity have not been commissioned or copied to this VPS. Connected chat tools are not automatically available inside the server application. Do not transfer this assistant's ambient credentials as a substitute.

## The next useful work: shift from environment foundation to financial loop

The next phase is not another major personality, library, or philosophical layer. It is the financial path that the environment was built to support.

**First, make the current financial inputs usable.** Inventory the creator's available market-data and financial APIs by actual capability, cost, freshness, historical depth, and terms. Choose a small authoritative starting set rather than wiring every key at once. The first set should provide timestamped underlying prices, option chains/quotes, contract specifications, and enough historical context to evaluate a decision. Keep credentials server-side and record source, timestamp, and failure state.

**Second, give all seven agents the same starting market snapshot.** Their arrival should remain simultaneous. Their perspectives can differ, but the opportunity set and evidence boundary should be reconstructable. Let each create an optional inquiry. Do not require a trade, consensus, or a personality ranking.

**Third, add structured proposal extraction to the existing lineage.** Prose can remain rich, but a paper proposal must contain the concrete fields needed to evaluate it: underlying, contract, side, quantity, order type, price/limit assumptions, intended horizon, thesis mechanism, invalidation condition, risk, and uncertainty. If the response is ambiguous, keep it as an inquiry rather than guessing a symbol, price, or size.

**Fourth, complete one conservative Alpaca paper adapter.** Begin with one agent or one shared reviewed execution pathway only for the adapter test, while all seven continue their inquiries together. Use defined-risk, long-option or otherwise explicitly bounded structures first; do not assume margin, short-option, assignment, or live authority. Reuse the mock lifecycle's durable submission IDs, reconciliation, failure, partial-fill, restart, and privacy rules. A real paper order ID, broker-confirmed fill state, and ledger result are the milestone—not a dashboard button that says “approved.”

**Fifth, evaluate before expanding.** Compare results against a simple rules-based reference and against no-trade decisions. Track net modeled result, spread/slippage assumptions, fees, data cost, model cost, drawdown, exposure, calibration, and the reason an inquiry did or did not become a trade. Treat the evaluation protocol as a guide, not a reason to postpone the first complete paper loop indefinitely.

Only after this path works should the system decide how much paper capital each account receives, which model map is worth its cost, how often agents wake, and whether any strategy deserves a longer forward paper period. The creator has not chosen the paper allocation; do not assume $100,000 or grant live-trading authority.

## Working with the creator and this repository

Keep additions small and explain why they help the next actual trading experience or financial result. Reuse the queue, memory, library, usage ledger, and continuity instead of creating parallel systems. Preserve original writing, literal notes, history, uncertainty, and private boundaries. Rich data can remain available without appearing in every wake.

There is no reward for a preferred self-description. Do not invent obligations to reflect, reconcile, summarize, socialize, or become more productive. Do not repeatedly rebut claims the creator has not made. Discuss concrete behavior, actual constraints, and useful financial evidence in plain language.

External projects considered for ideas include TradingAgents, AI-Trader, Vibe-Trading, Hummingbot, CrewAI, and notebooklm-py. They have not been installed as the engine's foundation. Avoid a framework migration unless it solves a specific present gap more simply than the existing code.

The repository and original corpus are private. Keep keys, journals, databases, session manifests, and actual run outputs out of Git; use the existing ignore rules. Work on review branches without silently merging, launching processes with financial authority, or force-pushing history. Preserve unrelated creator edits. A modified local heading in `docs/COMPOST_WITNESS.md` was deliberately left untouched during this handoff.

**The environment is worth preserving because it may help produce better trading. The trading system is the reason to finish the financial work.**
