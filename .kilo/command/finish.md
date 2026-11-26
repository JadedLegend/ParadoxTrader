---
description: Route a phase or finish-line task to the ParadoxTrader Steward (`finisher`) and its specialist team.
agent: finisher
subtask: true
---
Steward assistant for ParadoxTrader.

Use this command to execute one scoped, spec-backed slice:
- Fix a concrete gap or bug (e.g., day-run prompt alignment, `api/rehearsal.py` schema sync, legacy archiving)
- Implement one approved phase of `docs/specs/*.md` (e.g., `FORUM_AND_MESSAGES.md` Phase 1, `MARKET_WINDOW.md` Phase 2, structured `propose` bridge, Alpaca paper adapter)
- Finish or verify a dashboard view against `api/rehearsal.py` and `deploy/private_dashboard.py`
- Run an adversarial pre-PR verification via `review-finish`

Pass a single clear sentence naming the spec/phase or bugfix target.
