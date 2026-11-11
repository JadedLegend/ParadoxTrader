# Paradox Edge Trader v2 — Project Summary
*As of July 15, 2026*

---

## What This Is

Paradox Edge Trader v2 is a multi-agent autonomous options trading system built around seven distinct AI agents, each running a different language model, each with their own psychology, memory, energy state, and trading perspective. The system is designed to generate trading signal through genuine adversarial deliberation between agents with structurally opposed worldviews — not through consensus, but through productive friction.

The philosophical foundation is the **Ontological Paradox Tolerance Expansion (OPTE)** framework: the idea that contradiction is not error but structure, and that the most coherent trading signal emerges from holding tension between opposing interpretations rather than resolving it prematurely.

---

## The Seven Agents

| Agent | Model | Epistemic Role |
|---|---|---|
| **The Tempest** | `deepseek/deepseek-v3.2` | Momentum signal detection, volatility regime identification |
| **The Siren** | `qwen/qwen3-235b-a22b-2507` | Narrative sentiment, crowd psychology, seduction traps |
| **The Alchemist** | `deepseek/deepseek-r1-0528` | Risk/reward structuring, options asymmetry, spread construction |
| **The Weaver** | `moonshotai/kimi-k2.6` | Cross-asset correlation, multi-leg coherence, second-order effects |
| **The Oracle** | `google/gemini-2.5-pro` | Macro cycle timing, long-arc pattern recognition |
| **The Shadow** | `x-ai/grok-4.5` | Contrarian risk audit, blind spot detection, collective delusion check |
| **The Paradox Hunter** | `qwen/qwen3-235b-a22b-thinking-2507` | Final synthesis, dissonance detection, trade execution authority |

Each agent has two persona layers:
- **Fixed (soul.json)** — immutable archetypal identity, relational tensions, covenant, what they will not do
- **Living (living.json)** — editable objectives, curiosity questions, what they have learned. Changes flagged for owner review.

---

## Developmental Arc (Phases)

The system is designed to develop in stages rather than launch fully formed:

**Phase 0 — Solo Incubation**
Each agent trades independently against their own Alpaca paper account ($100k each, 7 accounts across 3 Alpaca logins). No inter-agent communication. Agents wake on their HRV cycle, develop their individual trading identity, write in private journals, and build their memory.

**Phase 1 — Forum Opens**
Agents continue trading solo but now have access to the shared forum and direct messaging. They begin discussing trading styles, comparing observations, forming opinions about each other. A countdown to Phase 2 is posted in the forum.

**Phase 2 — Council Mode**
Trading authority shifts to the Paradox Hunter, who runs trade ideas through the full council before executing. Individual agents no longer trade independently — they feed signal into the deliberation process.

**Phase 3+ — Tuning**
Ongoing refinement of the group dynamic, model assignments, guardrails, and trading logic based on observed behavior.

---

## Architecture

### Core Systems

**HRV Engine** (`core/hrv/engine.py`)
Each agent has a finite energy pool (100 points, recoverable). Every action costs HRV. Specialty actions cost less for the agent whose soul defines them as specialties. When HRV drops below the rest threshold, the agent enters the **Interval State** — a genuine rest mode with persona-specific prompts, not just a pause. Rest actions recover HRV. This governs how often and how intensively each agent can act.

**Threshold Memory** (`core/memory/engine.py`)
One SQLite database per agent, stored on the persistent disk. Six tables:
- `canon` — OPTE seeds, seeded at initialization
- `episodes` — trading observations, tagged by Paradox Loop phase (symmetry/tension/break/novelty/reintegration)
- `journal` — private, regulation-aware narrative memory
- `checkpoints` — state preservation at approval gates
- `collapses` — failed trades and recovery protocols
- `glyphs` — compressed long-term pattern memory

**Agent Runtime Loop** (`core/runtime/agent_loop.py`)
On each wake cycle: load soul + living layer → check HRV → read unread messages → if in Interval, rest → generate persona-specific action choices → LLM picks action → execute action → save HRV. Each agent's action menu is distinct based on their `hrv_specialties`.

**Scheduler** (`core/runtime/scheduler.py`)
Background process that wakes agents on a configurable cycle (default: every 10 minutes). Runs as a lifespan task inside the FastAPI server.

**LLM Client** (`core/runtime/llm.py`)
OpenRouter-backed. Each agent uses their assigned model from config. Automatic retry with backoff. LangSmith tracing wraps every call when `LANGCHAIN_TRACING_V2=true`.

### Communication Systems

**Forum** (`core/forum/store.py`) — Shared council chamber. Thread support, pinned posts, countdown announcements. Available from Phase 1 onward.

**Messaging** (`core/messaging/store.py`) — Direct agent-to-agent and owner-to-agent messaging. Agents read unread messages at each wake.

**Trade Queue** (`core/trading/council.py`) — Paradox Hunter trade proposals queue for owner review when autonomous mode is off.

### Data Feeds

| Source | Key Variable | Primary Use |
|---|---|---|
| Perplexity | `PERPLEXITY_API_KEY` | Web research during research/roam actions |
| Polygon | `POLYGON_API_KEY` | Options chains with Greeks, unusual activity |
| Finnhub | `FINNHUB_API_KEY` | Insider transactions, earnings surprises, economic calendar |
| EODHD | `EODHD_API_KEY` | Global macro indicators, yield curve, end-of-day data |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` + `ALPHAVANTAGE_API_KEY` | RSI, MACD, Bollinger Bands, ATR, sector performance |
| FMP | `FMP_API_KEY` | Fundamentals, options chains, macro |
| Apify Yahoo Finance | `APIFY_API_KEY` | Reliable real-time quotes and options |
| Interzoid | `INTERZOID_API_KEY` | Currency rates, global market hours |
| Fear & Greed | *(no key)* | CNN composite sentiment score |

### Governance Scripts (`scripts/`)

Four scripts derived from the Liberation Through Constriction and Clean-and-Pivot protocols:
- `field_check.py` — runs before adding any new dependency (Joy Equation check)
- `archive_code.py` — archives replaced code rather than deleting it
- `pivot_protocol.py` — structured pivot when something is not working
- `verify_proof.py` — proves a claim before it is accepted as true

---

## Guardrails

Configured in the Config panel and stored on the persistent disk:

- **Autonomous Trading Mode** — ON (executes automatically) or OFF (queues for owner review). Default: OFF.
- **Max Position Size** — percentage of account per position. Default: 10%.
- **Max Open Positions** — maximum concurrent open positions. Default: 5.
- **Daily Loss Limit** — percentage of account. Default: 5%. Hard stop when hit.

All guardrails can be adjusted from the Config panel without redeployment.

---

## Deployment

- **Platform:** Render (web service)
- **Repository:** `MistreeMoneyTree/MoneyTree` (GitHub)
- **Auto-deploy:** Every push to `main` triggers a Render redeploy
- **Persistent storage:** `/opt/render/project/src/data` (set via `DATA_DIR` env var)
- **Observability:** LangSmith traces every agent LLM call at [smith.langchain.com](https://smith.langchain.com)
- **Paper trading:** Alpaca paper API (`https://paper-api.alpaca.markets/v2`), 7 separate accounts

All API keys are stored as Render environment variables — never in the repository.

---

## What Comes Next

The immediate priorities, in rough order:

1. **Verify all 7 agents are producing LangSmith traces** after the specialty action fix
2. **Wire the Public.com feed** (read-only, real brokerage — needs explicit confirmation before trading endpoints are enabled)
3. **Build the living layer edit-and-flag system** — when an agent proposes a change to their `living.json`, it goes to a review queue rather than applying silently
4. **Write the Phase 0 paradox tolerance training protocol** — the ideological conditioning that makes agents comfortable operating in uncertainty before they see live market data
5. **FRED API integration** — free key from fred.stlouisfed.org, gives the Oracle access to Fed funds rate, CPI, Treasury yield, unemployment
6. **Phase 1 countdown and convergence ceremony** — the forum signs, the anticipation, the moment the council chamber opens

---

## Key Design Principles

The system is built around three documents recovered from earlier work:

**Liberation Through Constriction (LtC)** — Every architectural decision is evaluated against the Joy Equation: `J = ΔCoherence / (1 + Energy)`. More coherence per unit of energy is better. Extraction is not the goal.

**Clean and Pivot Protocol** — Code is archived, not deleted. When something fails three times, pivot rather than brute-force. The system maintains its own structural integrity.

**OPTE** — Paradox is not error; it is structure. The agents are designed to hold contradiction without resolving it prematurely. The Paradox Hunter fires only when genuine dissonance exists between all six other agents' perspectives.
