# Fixture-backed UI and wake-choice windows

This milestone adds a navigable, frontend-only view of the seven-agent community. **Default frontend mode uses local examples, not your accounts, financial APIs, models, memory databases, or scheduler.** Account and key connection is a later slice; no credentials need to be supplied for this preview.

## Try it from this development branch

Use Node 22.12 or later and the pinned npm toolchain. From `frontend/`, run `npm ci`, then `npm run dev`. Open the local URL printed by Vite. No `.env` file is required; omitted or unrecognized `VITE_RUNTIME_MODE` means preview. Do not start `python main.py run` or the FastAPI application for fixture work: the existing API lifespan still starts the legacy scheduler if independently launched.

The banner labels the mode on every page. Dashboard, Wake Choices, Agents, Community, Messages, Trade Queue, and Configuration are navigable with no backend. Wake Choices is also linked from agent/status screens. The retained dark purple-and-teal design now has clearer secondary text, keyboard focus indicators, and narrow-screen navigation/layouts.

## What the choice window represents

Choose an agent and inspect an individual, community, council, or quiet-interval example. The menus are generated offline from the actual runtime menu logic, existing persona specialties, and explicitly constructed sample HRV values. They remain examples rather than menus pending in a running agent. Phase 0 excludes peer communication; every menu retains rest. The actual interval path bypasses a picker entirely, whereas the interval demonstration lets the operator inspect its one rest option.

The native dialog supports keyboard navigation, radio selection, Escape/Close, and leaving a question undecided. Selecting an option creates an **operator demonstration receipt** for this mounted page only. It is not an agent choice or executed activity. Receipts show a hypothetical simulated-HRV change; the original fixture state stays unchanged. Navigating away, reloading, or clearing removes them. Nothing is saved to local storage or an agent record.

Journals and episodes start empty in this preview rather than inventing developmental history. Example market quotes are not supplied. A DEMO position and review card are visibly synthetic UI examples, not recommendations or paper-account holdings. Position displays distinguish confirmed sample holdings, confirmed empty data, unconfigured credentials, unavailable lookup, and missing state; unknown data is not treated as an empty portfolio.

## Isolation and API contracts

All frontend calls go through one explicit client boundary. Preview reads resolve local fixture responses. Preview writes reject without a backend request, even if someone programmatically invokes a disabled control. Unknown fixture routes fail explicitly rather than falling back to the network. Wake/init/phase controls, journal and identity changes, message/forum sending, trading review, and configuration changes are disabled or explained in the preview. Configuration preview does not collect keys.

Only the exact build-time setting `VITE_RUNTIME_MODE=connected` restores existing backend request behavior. There is no in-app toggle. A configured `VITE_API_URL` alone does not enable it. This is not authorization or deployment of connected mode, and it does not harden the remaining legacy execution/configuration endpoints. Private provider and broker keys must never appear in any `VITE_*` environment variable or browser bundle.

The backend's positions wrapper now reuses the corrected snapshot helper (`status`, `positions`, `observed_at`) instead of an incompatible broker constructor and separate credential schema. Agent summaries include stored `max_hrv`, distinguish absent HRV state from zero, and use the existing model preference field. No new account calls were made; these contracts are tested with mocked boundaries and undecorated handler extraction, without importing the FastAPI application.

The queue renderer now reads the backend's nested `proposal` fields, so the DEMO symbol, side, quantity, and synthetic thesis display correctly. The read-only `/api/queue` handler also has a distinct name from its store helper, removing the legacy recursion/name collision without changing order execution or trade-review semantics.

## Checks and reproducibility

From the repository root, run `python3 -B -m unittest discover -s tests -v` and `python3 -B scripts/build_ui_fixtures.py --check`. From `frontend/`, run `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`. Fixtures can be regenerated with `python3 -B scripts/build_ui_fixtures.py`; the script disables tracing, blocks sockets/HTTP/model/config access, uses temporary data paths, and exports selected public persona fields rather than private records or credentials.

Frontend interactions are exercised in a network-blocked test DOM. This is not a real-browser visual audit of responsive layouts or native dialog focus behavior. No frontend/backend server is launched by this milestone's checks.

Validation on this branch: **92 Python tests and 196 frontend tests passed**; TypeScript checking and the production frontend build passed; lint reported **zero warnings and zero errors**. Independent review identified the nested queue-rendering mismatch, and a client test exposed a non-affirmative mode fallback. Both are corrected and covered. The fixture configuration guard was also moved before importing runtime/LLM code.

The development branch includes the preceding wake and orientation work. Delivery is a pull request, not a main-branch merge or public deployment. Next work remains the real wake-window/concurrency controls, bounded library retrieval, source timestamps, cost accounting, and the paper-order lifecycle. The user's existing accounts and keys can be connected through protected configuration when that stage is ready.
