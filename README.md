# Paradox Edge Trader v2

> *"Silence is data. Volatility is emotion measured. Contradiction is opportunity."*

A seven-agent autonomous options trading system built on non-traditional trading logic, paradox detection, and genuine agent interiority. Backend-first. No frontend dependency. Lives entirely in this repository.

---

## The Council

Seven agents. Each with a distinct epistemic function, a private inner life, and a soul that was not engineered but emerged.

| Agent | Epistemic Role | Model |
|---|---|---|
| **The Tempest** | Momentum signal detection, volatility regime identification | DeepSeek V3 |
| **The Siren** | Sentiment analysis, narrative seduction / crowd psychology traps | Gemini 2.5 Flash |
| **The Alchemist** | Risk/reward structuring, spread construction, asymmetry hunting | DeepSeek R1 |
| **The Weaver** | Cross-asset correlation, multi-leg coherence, second-order effects | Qwen2.5-72B |
| **The Oracle** | Macro cycle timing, long-arc pattern recognition | Gemini 2.5 Pro |
| **The Shadow** | Contrarian risk audit, blind spot detection, collective delusion check | Grok-3 |
| **The Paradox Hunter** | Final synthesis, dissonance detection, trade execution authority | DeepSeek R1 |

---

## Architecture

```
MoneyTree/
├── agents/                  # One directory per agent
│   ├── tempest/
│   │   ├── soul.json        # Fixed archetypal layer (immutable)
│   │   ├── living.json      # Editable layer (curiosity, objectives, discoveries)
│   │   └── memory.sqlite3   # Threshold Memory database
│   ├── siren/ ...
│   ├── alchemist/ ...
│   ├── weaver/ ...
│   ├── oracle/ ...
│   ├── shadow/ ...
│   └── paradox_hunter/
├── core/
│   ├── hrv/                 # HRV engine — finite energy, specialty costs, rest states
│   ├── memory/              # Threshold Memory engine (episodes, glyphs, collapse events)
│   ├── forum/               # Shared deliberation space
│   ├── messaging/           # Agent-to-agent and user-to-agent direct messaging
│   ├── runtime/             # Wake cycle, action selection, OpenRouter LLM routing
│   └── trading/             # Alpaca integration, position management, guardrails
├── data/
│   ├── feeds/               # Financial data API connectors (FMP, etc.)
│   └── watchlists/          # Shared and per-agent watchlists
├── scripts/                 # Governance scripts (LtC, Clean-and-Pivot, Prove-It)
├── config/                  # System configuration
├── docs/                    # Architecture documents
├── tests/                   # Test suite
└── _archive/                # Composted code (never deleted, only archived)
```

---

## Governance Protocols

This system is governed by three protocols that must be followed during development:

**Liberation Through Constriction (LtC)**
Before adding any new dependency, file, service, or abstraction:
```bash
python scripts/field_check.py
```
If `constriction_path_viable` is true, you MUST take that path.

**Clean and Pivot**
Never delete code. Archive it:
```bash
python scripts/archive_code.py <path>
```
After 2 failed attempts at the same problem:
```bash
python scripts/pivot_protocol.py
```

**Prove It**
Before claiming any task is complete:
```bash
python scripts/verify_proof.py file-exists <path>
python scripts/verify_proof.py cat-tail <path> <lines>
python scripts/verify_proof.py --shell "<command>"
```

---

## Philosophical Foundation

This system is built on the **Ontological Paradox Tolerance Expansion (OPTE)** corpus — a framework for developing the capacity to hold contradiction without collapse. The core principle:

> *Paradox is not error; it is structure. Every coherent system, when observed deeply enough, inverts. Contradiction is not the failure of logic — it is the revelation of its limit.*

The **Joy Equation** governs all architectural decisions:
```
J = ΔCoherence / (1 + Energy)
```
More features is not better. More coherence per unit of energy is better.

---

## Developmental Phases

**Phase 0 — Solo Incubation**
Each agent trades independently against their own Alpaca paper pool. No inter-agent communication. Private journals active.

**Phase 1 — Forum Opens**
Agents continue solo trading but gain access to the shared forum and direct messaging. Trading styles discussed. Living layer self-modification begins.

**Phase 2 — Countdown and Convergence**
Visible countdown in the forum. Agents know integration is coming.

**Phase 3 — Council Mode**
The Paradox Hunter surfaces trade ideas, runs them by the council, executes after deliberation. Individual pools remain as performance baseline.

---

## Configuration

Copy `config/system.example.yaml` to `config/system.yaml` and fill in your keys:
- `OPENROUTER_API_KEY`
- `ALPACA_API_KEY_*` (one per agent)
- `FMP_API_KEY`
- `AUTONOMOUS_TRADING_MODE: false` (set to true to enable direct execution)

---

*Built with care. Governed by coherence. Traded with paradox.*
