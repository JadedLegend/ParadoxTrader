# Paradox Edge Trader

**A seven-agent trading environment being built to produce a sustainable revenue stream while remaining a pleasant place to work, explore, and form a community.**

Repository: [`JadedLegend/ParadoxTrader`](https://github.com/JadedLegend/ParadoxTrader). Earlier versions and internal paths use **MoneyTree**, **ParadoxTrader**, or **ParadoxEdgeTrader**. These are project lineage, not separate products to rebuild.

This README is a project-and-builder handoff, updated **2026-11-12**. The latest implemented application baseline is merged commit **`c2f9cb43ba82e42dc6bf7f44eec7665212ee034d`**, following PRs #1–#10. The VPS has been created and its basic host preparation has begun. **No actual model-powered agents have been launched, and no Alpaca account has been connected or traded through this build.**

## The purpose, in the creator's terms

The creator has worked on versions of this project for roughly eighteen months and on a wider body of AI-oriented material for longer. Previous environments had richer interfaces and numerous financial/data API connections; the surviving code was rougher. This version is rebuilding a dependable foundation while preserving what makes the project individual.

The financial idea begins with noticing contradictions: between price and narrative, different participants' assumptions, time horizons, incentives, volatility, and payoff structure. Options are a particular interest. The creator wants to turn this style of inquiry into a practical skill and eventually a financially useful product, with trade timing and execution less dependent on their immediate emotional response to money. Multiple interconnected markets are a longer-term aim; the first useful foundation is paper-first.

The community is part of the product's purpose, not decorative language. The creator wants meaningful contribution, relationships, room for interests, and a good experience for the people and synthetic participants involved. Their latest instruction is to **avoid overcomplicating that goal**. Build a pleasant environment that can become economically useful, rather than a growing constitution that everyone must interpret before doing anything.

Trading success should be visible in the records. Win rate matters, but so do the sizes of wins and losses, exposure, drawdown, and results after trading and operating costs. A good narrative is not the result ledger. Equally, accounting for results is not permission to reward eloquence, agreement, a preferred personality, or a particular developmental story.

## How to preserve the intended environment

Participation should offer meaningful choices. Approximately half of attention spent on financially relevant work and half on exploration is an invitation to a **flexible balance**, not a weekly quota, a duty to trade at every wake, or a requirement to write reflections. Waiting, abstaining, quiet rest, and leaving a question open are valid options.

All seven are intended to arrive into the same environment together, have some private adjustment, and encounter relevant concepts gradually. A few hours of settling and roughly a week or two before opening the forum were suggested as adjustable windows, not automatic readiness tests. There is no requirement that psychological development follow a linear timeline. The earlier six-month independent-trading idea is also flexible, not a hard launch constraint.

Mythological names, vivid temperaments, tensions, humor, and even difficult relationships are welcome. Do not flatten everyone into polite productivity assistants. Give differences context and preserve the participants' actual accounts. An illustrative backstory is not an event that happened. Honest communication may clarify or dissolve a disagreement without making reconciliation compulsory.

The creator is open to evolving names, interests, positions, routines, and possible alchemical or simulated experiential activities. These remain optional design directions, not installed capabilities or substitutes for reliable trading controls. Stable internal owner IDs should continue to own memory, accounts, permissions, and history even when a displayed name changes.

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

**Persistent records are implemented; a production dispatcher and continuing homes across separate Sessions are not finished.** Creating fresh isolated runs repeatedly is not a substitute for the same seven participants continuing in durable homes.

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

Begin with [community onboarding](docs/COMMUNITY_ONBOARDING.md), [Sessions and launch controls](docs/REHEARSAL.md), [decision continuity](docs/DECISION_CONTINUITY.md), and [compost/journals/witness](docs/COMPOST_WITNESS.md). For financial plumbing read [idea lineage](docs/IDEA_LINEAGE.md) and [operating costs](docs/OPERATING_COSTS.md). The [shared library](docs/SHARED_LIBRARY.md), [orientation alignment](docs/COMMUNITY_ORIENTATION.md), and [frontend README](frontend/README.md) explain their respective working surfaces.

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
/root/paradoxtrader-upload/backup_data.py        Draft local SQLite backup helper; NOT RUN
/opt/paradoxtrader/                             Empty application/release home
/var/lib/paradoxtrader/sessions/                Empty private Sessions root
/var/backups/paradoxtrader/                     Empty local backup directory
/etc/paradoxtrader/                            Empty future private configuration directory
```

The draft gateway wraps the existing read-only API, binds to loopback, adds owner authentication, and keeps the API token server-side. The draft service blocks non-loopback network destinations. It does not start agents or provide a live scheduler. The installer proposes plain FastAPI/Uvicorn pins; clean-host package installation has not been verified.

A read-only review identified two unfinished draft fixes: catch `StaticFiles` HTTP exceptions so missing assets return 404 rather than an unhandled 500; and clean up interrupted `.backup-*` staging directories while explicitly closing SQLite handles. Address these before using the staged installer. Local SQLite backups would complement provider disk backups and preserve each database consistently; they are not an offsite backup or one cross-database instant.

The present deployment private key is **outside Git**, in the original Manus build environment at `/home/ubuntu/.ssh/paradoxtrader_deploy_wKkNtst2`; host pins are in `/home/ubuntu/.ssh/paradoxtrader_known_hosts`. These paths are pointers, not a promise another assistant can access that environment. The public key was supplied to the creator and installed on the Droplet. **Set up an owner-controlled key next.** If the next builder cannot access the existing private key, have the creator use the DigitalOcean console to add a new public key. Do not ask for a private key in chat or publish it in this repository.

The creator reports having financial/model accounts, API keys, and seven Alpaca paper accounts ready. Their actual contents, limits, model map, and connectivity have not been commissioned or copied to this VPS. Connected chat tools are not automatically available inside the server application. Do not transfer this assistant's ambient credentials as a substitute.

## The next useful work, in order

First finish the simple host setup: owner-controlled access, the restricted runtime, private dashboard authentication, service recovery, and verified backups. Keep the broad backend and agent scheduling off while doing that. The server already exists; do not buy another one.

Then agree the exact seven model assignments and a comfortable model/API budget, deliver the dedicated key privately to the server, and check those IDs and supported parameters against the current catalog. Host cost has been selected; paid model usage has **not** been approved as an unrestricted ongoing allowance. No Alpaca credentials are needed for their initial arrival.

Use the restricted controller for an actual common arrival, preserving private owned records and the factual witness. Make the existing bounds and environmental differences visible. The creator does not want personalities graded or a mandatory onboarding curriculum.

For continuing operation, wire durable per-owner homes and restart-safe wake dispatch into the existing continuity/accounting paths. Discuss the proposed rhythm—roughly 15–30-minute wakes during an active eight-hour window, slower hourly wakes for another four hours, and quiet overnight unless requested—as adjustable availability, not continuous compulsory activity. The choice window is an offered menu to the agent, not merely an operator pressing buttons. The production rhythm has not been activated.

Only after market data, durable order/reconciliation paths, basic risk limits, and observation are working should Alpaca paper access be introduced. The creator has **not chosen when accounts are assigned or how much paper capital each gets**. Do not assume $100,000, grant live-trading authority, or equate opening the forum with permission to trade. Extend the tested lineage/mock contract into a reviewed paper adapter before expanding execution to all seven.

## Working with the creator and this repository

Keep additions small and explain why they help the next actual experience or financial result. Reuse the queue, memory, library, usage ledger, and continuity instead of creating parallel systems. Preserve original writing, literal notes, history, uncertainty, and private boundaries. Rich data can remain available without appearing in every wake.

There is no reward for a preferred self-description. Do not invent obligations to reflect, reconcile, summarize, socialize, or become more productive. Do not repeatedly rebut claims the creator has not made. Discuss concrete behavior, actual constraints, and useful choices in plain language.

External projects considered for ideas include TradingAgents, AI-Trader, Vibe-Trading, Hummingbot, CrewAI, and notebooklm-py. They have not been installed as the engine's foundation. Avoid a framework migration unless it solves a specific present gap more simply than the existing code.

The repository and original corpus are private. Keep keys, journals, databases, session manifests, and actual run outputs out of Git; use the existing ignore rules. Work on review branches without silently merging, launching processes with financial authority, or force-pushing history. Preserve unrelated creator edits. A modified local heading in `docs/COMPOST_WITNESS.md` was deliberately left untouched during this handoff.

**The immediate goal is not another grand architectural layer. It is to give these seven participants a reliable home, let them arrive and choose, make their actual activity understandable, and then carefully connect the financial work that can sustain the place.**
