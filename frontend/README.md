# Paradox Edge Trader frontend

React, TypeScript, and Vite operator interface for the seven-agent community.

## Frontend-only preview

Use Node 22.12+ and npm 10.9.9. From this directory:

```sh
npm ci
npm run dev
```

Open the local address Vite prints. **Do not start the Python API or engine for this preview.** The API's existing startup lifecycle starts its scheduler if independently launched.

The default mode uses labeled local fixtures for all reads and blocks all backend writes. No environment file, accounts, or keys are needed. Inspect the Wake Choices page to select an agent and demonstrate a choice window. Your demonstration is local UI state, not an agent decision or executed activity.

Only the exact build-time setting `VITE_RUNTIME_MODE=connected` restores existing backend requests. A `VITE_API_URL` by itself does not enable them. There is no in-app mode switch. Connected operation requires separate configuration and execution-safety work; it is not deployed or enabled by this milestone. Never put private provider/broker keys in `VITE_*` variables.

## Checks

```sh
npm test
npm run typecheck
npm run lint
npm run build
```

Frontend interaction tests run in an isolated DOM with network calls blocked. The Python regression suite and offline fixture-generation check run from the repository root:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/build_ui_fixtures.py --check
```

To regenerate public persona/menu examples, run the fixture script without `--check`. It does not read configured credentials or private agent records.

See [fixture choice UI notes](../docs/FIXTURE_CHOICE_UI.md) for the actual milestone boundary and [the implementation plan](../docs/CHOICE_UI_PLAN.md) for structure.
