# Incoming materials

Material that has arrived for the project but has **not** been wired into anything. Nothing here is loaded by agents, prompts, the library store, or the rehearsal. Curated originals live in `library/`; this folder is the waiting room before that decision is made.

Files are stored byte-exact (see `.gitattributes`) so each bundle's own checksum manifest stays valid.

## `doxtrade/` — Financial Research Collection, version 1 (2026-11-14)

An assistant-authored, options-centered reading collection: 20 core papers plus 1 counterpoint (P01–P21), with reading notes, a source catalog and provenance. It holds **notes and references only**. No PDFs or republished paper text are included; the PDFs consulted stay in a separate source cache outside the repo.

Intake checks (2026-11-14):
- All 28 entries in `doxtrade/MANIFEST.sha256` verify.
- Scanned for API keys, tokens, passwords, account numbers and personal email addresses. No secrets found. The only matches were prose about agents' token budgets.
- Total size is about 370 KB, with no file anywhere near GitHub's 100 MB limit.

| File | What it is |
|---|---|
| `START-HERE.md` | Entry point: purpose, evidence labels, a reading map by interest, and a synthesis in numbered sections |
| `READING-COMPANION.md` | All 21 reading notes in one document |
| `reading-notes/P01.md` … `P21.md` | The same notes, one per paper, for browsing or retrieval |
| `source-catalog.json` | Per-paper record: bibliographic identity, URL, evidence type, horizon, limits, possible questions and data requirements |
| `references.bib` | BibTeX for all 21 papers |
| `provenance.json` | 46 retrieval records with URLs and hashes, including failed attempts |
| `Reading-Companion.docx`, `Research-Guide.docx` | Word versions for reading outside the repo, generated with python-docx |
| `MANIFEST.sha256` | Checksums for the files above |

Papers: Black–Scholes (P01); option returns and volatility or variance premia (P02–P04); demand-based option pricing and gamma fragility (P05–P06); liquidity, funding and limits of arbitrage (P07–P08); carry, time-series momentum and macro announcements (P09–P11); the global financial cycle debate (P12, P21); Grossman–Stiglitz (P13); social influence, cascades and forecasting tournaments (P14–P16); backtest overfitting and multiple testing (P17–P18); and the LLM trading-agent preprints FinMem and TradingAgents (P19–P20).

The collection is explicit that it contains no ParadoxTrader result and no established trading edge, and that its notes are reference content, not agent instructions.

## Open questions (the creator's to decide; nothing is built)

1. **Route to the agents.** Should these join the shared library through `scripts/import_library.py` and `core/library/store.py`, so they get bounded retrieval and optional browsing like the existing originals? Or should they stay operator-only reading?
2. **Which form.** The per-paper notes (`reading-notes/P*.md`) suit retrieval best. Should `START-HERE.md`'s interpretive sections be exposed too, or held back so they don't read as house doctrine?
3. **Store and ownership.** Should the material be shared by all seven, or offered on request? Either way it is read-only, with no owner-private copies.
4. **Cost limits.** Loading notes on demand through bounded retrieval keeps prompt cost near zero. Preloading them into every prompt is the pattern the README rules out.
5. **Data requirements.** `source-catalog.json` lists the data each paper would need, such as option chains, positioning and macro releases. None of it is connected. Market data remains a later, bounded-read step in the README's sequence.
