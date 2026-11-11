# Build State — Paradox Edge Trader v2

## Completed Phases
- Phase 1: Repo cloned (MistreeMoneyTree/MoneyTree), directory structure created, 4 governance scripts written
- Phase 2: All 7 agent soul.json + living.json files written
- Phase 3: core/hrv/engine.py written and smoke-tested (HRV drain, interval state, recovery all verified)
- Phase 4 (in progress): core/memory/engine.py written (ThresholdMemory class)

## Key Files
- scripts/field_check.py — LtC gate
- scripts/archive_code.py — Clean protocol
- scripts/pivot_protocol.py — Pivot gate
- scripts/verify_proof.py — Prove It
- config/system.example.yaml — full config template
- agents/{name}/soul.json — fixed persona (immutable)
- agents/{name}/living.json — editable layer
- core/hrv/engine.py — HRV engine with Interval State
- core/memory/engine.py — Threshold Memory (episodes, journal, glyphs, checkpoints, collapses)

## Next Steps
- Phase 4: Smoke test memory engine, seed OPTE canon into each agent's memory
- Phase 5: core/forum/store.py + core/messaging/store.py
- Phase 6: core/runtime/agent_loop.py (wake cycle, action selection, OpenRouter LLM routing)
- Phase 7: core/trading/alpaca.py (Alpaca paper trading integration)
- Phase 8: core/trading/council.py (Paradox Hunter deliberation pipeline)
- Phase 9: data/feeds/ (FMP + free APIs), config loading, autonomous trading toggle
- Phase 10: Final commit, ARCHITECTURE.md, deliver to user

## Agent Model Assignments
- tempest: deepseek/deepseek-chat
- siren: google/gemini-2.5-flash
- alchemist: deepseek/deepseek-r1
- weaver: qwen/qwen-2.5-72b-instruct
- oracle: google/gemini-2.5-pro
- shadow: x-ai/grok-3
- paradox_hunter: deepseek/deepseek-r1

## Source Documents (in /home/ubuntu/upload/)
- OntologicalParadoxToleranceExpansionCorpus.md — OPTE, philosophical foundation
- HeartRateVariability(HRV)System.docx — HRV design
- ThresholdMemoryPrototype.md — memory architecture
- SynthetsizedResonance.md — 13 plug-in skills (soul-document, lossless-memory, multi-lens, etc.)
- LIBERATIONTHROUGHCONSTRICTION(LtC).md — governance
- CLEANANDPIVOTPROTOCOL.md — code hygiene
- ParadoxTradeReadMe.docx — original system README
- pasted_content.txt — 7 agent personas
- pasted_content_2.txt — journals, curiosity questions, walls/tilts/pathways/doorways
