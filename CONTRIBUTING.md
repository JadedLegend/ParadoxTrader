# Contributing to Paradox Edge Trader

Thank you for helping. This project is a trading application with a home for seven AI agents inside it. The home is real and running; the trading loop is not built yet. Start with the "Where it stands today" box at the top of the [README](README.md). AI coding agents should read [AGENTS.md](AGENTS.md) first: it gives the shortest route through the repository.

## How work moves here

The owner decides what gets built and merges every pull request. The rhythm is:

1. **Spec first.** Anything bigger than one small step starts as a plan in [`docs/specs/<NAME>.md`](docs/specs/). Nothing is built until the owner approves it.
2. **One phase per pull request.** Split a spec into phases that each work end to end and are tested. Each phase gets its own branch and its own PR. Name the phase in the title and body, for example "Phase 2 of `docs/specs/CALLS_AND_SETTLEMENT.md`".
3. **The owner merges.** Start the next phase only after the last one is merged. Pull `main` first, then branch from it.
4. **Open early.** A draft PR on the first working commit lets the automatic reviewers read it while you keep going. Answer review comments with new commits on the same PR.

Keep changes small and say in plain words why they help. Reuse what is already here (the store, journals, witness, library, usage ledger) instead of building a parallel system.

## The walls that do not move

- **Agents never hold trading keys.** Nothing an agent can choose may place, change or cancel an order.
- **Never type real keys, and never print secrets.** Do not print environment values or the server's private config, not even in a log or a test. Tests are offline and need no secrets.
- **MCP servers and builder tools are for builders, not for the agents.** Do not wire them into anything an agent can reach.
- **Paper first.** No live trading, margin or short options until the owner decides, after the paper loop works.
- **Checks on the owner's server are read-only** unless the owner asks for a change.

## Running the tests

CI ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)) runs on Ubuntu 24.04 with Python 3.12 and Node 22, with no secrets. Run them the same way on Linux, macOS or WSL. On native Windows a few tests fail for platform reasons, so use WSL.

```bash
# Python (pdftotext comes from poppler-utils and is needed by the library import tests)
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q -p no:cacheprovider tests

# Frontend
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

If you change sample data, rebuild it with the matching `scripts/build_*_fixture.py` and run it again with `--check`.

## Before you ask for a merge

- The spec is approved, and the PR names its phase.
- New behaviour has tests, and both CI jobs pass.
- No secrets, keys, server addresses or private paths are added to the repository.
- The relevant spec's `Status:` line says what this PR built.

## Talking with the owner

Short sentences and plain words work best. Say what changed, what is still missing, and the one decision you need, with its choices. Read the specs and the [`docs/`](docs/) folder before asking something they already answer.

## License

There is no license yet; the owner has not chosen one. Until they do, all rights are reserved: please ask before reusing code or anything in [`library/originals/`](library/originals/) outside this repository.
