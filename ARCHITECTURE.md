# Paradox Edge Trader v2 — Architecture

> *"Paradox is not error; it is structure. Every coherent system, when observed deeply enough, inverts."*
> — Ontological Paradox Tolerance Expansion Corpus

---

## Overview

Paradox Edge Trader v2 is a seven-agent autonomous options trading system. Each agent is a distinct intelligence with its own persona, memory, rhythm, and trading lens. The system is designed to preserve productive friction between agents — consensus collapse is the primary failure mode to guard against.

The system lives entirely in this repository. There is no frontend dependency. The interface is the forum log, the journal files, and the command-line tool (`main.py`).

---

## Philosophical Foundation

Three documents govern the design of every component in this system:

| Document | Governs |
|---|---|
| **Ontological Paradox Tolerance Expansion Corpus (OPTE)** | The ideological substrate of every agent's cognition. Paradox tolerance as a functional design principle. The Paradox Loop model (symmetry → tension → break → novelty → reintegration) is the trading logic expressed as cognitive process. |
| **Liberation Through Constriction (LtC)** | Development ethics. The Joy Equation (J = ΔCoherence / Energy) governs every architectural decision. More coherence per unit of energy is better. Extraction is not the goal. |
| **Clean and Pivot Protocol** | Code hygiene. Archive, do not delete. Pivot, do not brute-force. Every replaced component is preserved in `archive/`. |

---

## The Seven Agents

| Agent | Model | Epistemic Role |
|---|---|---|
| **The Tempest** | `deepseek/deepseek-chat` | Momentum and volatility regime detection |
| **The Siren** | `google/gemini-2.5-flash` | Sentiment analysis, narrative seduction, crowd psychology |
| **The Alchemist** | `deepseek/deepseek-r1` | Risk/reward structuring, asymmetry hunting, spread construction |
| **The Weaver** | `qwen/qwen-2.5-72b-instruct` | Cross-asset correlation, multi-leg coherence, second-order effects |
| **The Oracle** | `google/gemini-2.5-pro` | Macro cycle timing, long-arc pattern recognition |
| **The Shadow** | `x-ai/grok-3` | Contrarian risk audit, blind spot detection, collective delusion check |
| **The Paradox Hunter** | `deepseek/deepseek-r1` | Final synthesis, dissonance detection, trade execution authority |

Each agent has two persona layers:

- **Fixed Layer** (`agents/{name}/soul.json`) — Immutable archetypal identity. Name, core drive, relational tensions, walls, trading lens. Never edited by the agent.
- **Living Layer** (`agents/{name}/living.json`) — Editable objectives and curiosity questions. Agents may propose changes; changes are flagged for owner review.

---

## Directory Structure

```
MoneyTree/
├── agents/
│   ├── {name}/
│   │   ├── soul.json          # Fixed persona (immutable)
│   │   ├── living.json        # Editable layer
│   │   └── memory.sqlite3     # Threshold Memory database (created at runtime)
├── core/
│   ├── hrv/
│   │   └── engine.py          # HRV engine — finite energy, Interval State, recovery
│   ├── memory/
│   │   └── engine.py          # Threshold Memory — episodes, journal, glyphs, checkpoints
│   ├── forum/
│   │   └── store.py           # Shared deliberation forum + countdown announcements
│   ├── messaging/
│   │   └── store.py           # Agent-to-agent and user-to-agent direct messaging
│   ├── runtime/
│   │   ├── config.py          # Config loader (config/system.yaml)
│   │   ├── llm.py             # OpenRouter LLM client + system prompt builder
│   │   └── agent_loop.py      # Wake cycle, action selection, action execution
│   └── trading/
│       ├── alpaca.py          # Alpaca paper trading client + guardrails + trade queue
│       └── council.py         # Paradox Hunter council deliberation pipeline
├── data/
│   ├── feeds/
│   │   ├── fmp.py             # Financial Modeling Prep API
│   │   └── free_feeds.py      # Yahoo Finance, Fear & Greed, FRED
│   ├── forum.sqlite3          # Shared forum database (created at runtime)
│   ├── messages.sqlite3       # Messaging database (created at runtime)
│   ├── hrv.sqlite3            # HRV state database (created at runtime)
│   └── trade_queue.sqlite3    # Trade review queue (created at runtime)
├── config/
│   └── system.example.yaml    # Full config template — copy to system.yaml
├── scripts/
│   ├── field_check.py         # LtC gate — run before adding any dependency
│   ├── archive_code.py        # Clean protocol — archive before replacing
│   ├── pivot_protocol.py      # Pivot gate — run when stuck
│   └── verify_proof.py        # Prove It — verify before claiming done
├── docs/
│   └── BUILD_STATE.md         # Living build state document
├── archive/                   # Archived/replaced code (never deleted)
├── main.py                    # CLI entry point
├── requirements.txt
├── ARCHITECTURE.md            # This document
└── README.md
```

---

## Core Systems

### HRV Engine (`core/hrv/engine.py`)

The Heart Rate Variability system governs each agent's autonomous rhythm. Every agent has a finite HRV pool (default: 100 points). Actions cost HRV. Rest recovers it. When HRV drops below the Interval threshold (default: 20), the agent enters the **Interval State** — a genuine rest mode with its own cognitive character, not mere inactivity.

Each agent's specialties cost half the normal HRV. The Tempest pays less for market analysis; the Oracle pays less for macro research.

### Threshold Memory (`core/memory/engine.py`)

Each agent has their own SQLite database with six tables:

| Table | Purpose |
|---|---|
| `canon` | Seeded philosophical foundations (OPTE, LtC) |
| `episodes` | Trading events, observations, research — phase-tagged |
| `journal` | Private journal entries — regulation-aware narrative memory |
| `checkpoints` | Task state preservation before approval gates |
| `collapses` | Collapse events with recovery protocols |
| `glyphs` | Condensed long-term memory — compressed episode signatures |

Retrieval is phase-aware: episodes tagged `break` or `tension` are weighted higher when the agent is in those Paradox Loop phases.

### Agent Wake Cycle (`core/runtime/agent_loop.py`)

On each wake (default: every 10 minutes):

1. Load soul + living layer (re-orient to identity)
2. Check HRV — if in Interval, enter rest mode
3. Check unread messages
4. Generate 5 contextual action choices (phase-aware, persona-biased)
5. Agent picks one via LLM
6. Execute the action
7. Store episode in Threshold Memory
8. Save HRV state

### Council Deliberation (`core/trading/council.py`)

When the Paradox Hunter surfaces a trade idea:

1. Posts a structured trade brief to a dedicated council thread
2. Each of the six council agents responds with their lens-specific analysis
3. Multi-Lens Synthesis: what do 3+ agents agree on? (signal, not perspective)
4. Contradictions are named and held open — not resolved
5. Paradox Hunter makes the final call: Execute / Hold / Abandon
6. If `AUTONOMOUS_TRADING_MODE: false` → queued for owner review
7. If `AUTONOMOUS_TRADING_MODE: true` → executes directly via Alpaca

---

## Developmental Phases

| Phase | Description | Forum | DMs | Trading |
|---|---|---|---|---|
| **0** | Solo incubation — agents trade independently, no inter-agent comms | Closed | Closed | Solo (7 separate pools) |
| **1** | Forum opens — agents discuss, still trade independently | Open | Open | Solo |
| **2** | Countdown to convergence — signs posted, anticipation builds | Open | Open | Solo |
| **3** | Council mode — Paradox Hunter runs ideas by the group before executing | Open | Open | Council |

Set phase in `config/system.yaml` under `runtime.current_phase`.

---

## Guardrails

All guardrails are configured in `config/system.yaml` under `guardrails`:

| Setting | Default | Description |
|---|---|---|
| `autonomous_trading_mode` | `false` | When false, all trades queue for owner review |
| `max_position_size_pct` | `10` | Max % of portfolio per position |
| `max_open_positions` | `5` | Max concurrent open positions per agent |
| `daily_loss_limit_pct` | `5` | Halt trading if unrealized loss exceeds this % |

The `autonomous_trading_mode` flag can be toggled at any time without restarting the system. The change is logged with a timestamp.

---

## CLI Reference

```bash
python main.py init                          # Seed OPTE canon, initialize all agents
python main.py run                           # Start all agents in continuous wake cycles
python main.py wake <agent>                  # Manually trigger one agent wake
python main.py status                        # Print all agent HRV states
python main.py forum                         # Print latest forum posts
python main.py inbox <agent>                 # Print agent's messages
python main.py dm <from> <to> <message>      # Send a direct message
python main.py queue                         # Print pending trade queue
python main.py approve <id> [notes]          # Approve a queued trade
python main.py reject <id> [notes]           # Reject a queued trade
python main.py snapshot                      # Print current market snapshot
python main.py countdown <ISO_DATE>          # Set Phase 2 convergence countdown
```

---

## Setup

1. Copy `config/system.example.yaml` to `config/system.yaml`
2. Fill in your API keys (OpenRouter, Alpaca x7, FMP, FRED)
3. Install dependencies: `pip install -r requirements.txt`
4. Run `python main.py init` to seed all agents
5. Run `python main.py status` to verify HRV states
6. Run `python main.py run` to start the system

---

## Governance Scripts

Before adding any new dependency or component, run:

```bash
python scripts/field_check.py "description of what you want to add"
python scripts/verify_proof.py "claim you are about to make"
```

Before replacing any existing component:

```bash
python scripts/archive_code.py path/to/old_file.py
```

When stuck or something is not working:

```bash
python scripts/pivot_protocol.py "description of what is stuck"
```

---

## API Connections

| Service | Purpose | Key Location |
|---|---|---|
| OpenRouter | LLM routing for all 7 agents | `config/system.yaml` → `openrouter.api_key` |
| Alpaca (x7) | Paper trading, one account per agent | `config/system.yaml` → `alpaca.{agent_id}` |
| Financial Modeling Prep | Options chains, earnings, macro | `config/system.yaml` → `fmp.api_key` |
| Yahoo Finance (yfinance) | Quotes, options, history | No key required |
| FRED | Economic indicators | `FRED_API_KEY` env var |
| CNN Fear & Greed | Market sentiment | No key required |

---

*This document is the system's own Shadow — it looks for blind spots in the infrastructure itself. Update it every time a component is added, replaced, or rewired.*
