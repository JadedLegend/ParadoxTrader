# Fixture-backed choice-window milestone

The accepted next slice is a navigable frontend preview of each agent's wake choices, plus consistent UI/API position status. Reuse the existing React/Vite dark purple-and-teal dashboard language and seven identities. This is not a visual redesign or an account-connection milestone.

The frontend defaults to fixture mode. Its central client returns clearly labeled local examples for reads and blocks backend mutations. Connected behavior requires an explicit build-time mode; there is no in-app switch that silently starts the engine. No keys are collected or shipped to the browser in this work. The choice-window demonstration is local interaction, not an agent decision, forecast, journal, or paper order.

A dedicated Wake Choices page lets the operator inspect seven agents and phase/resource scenarios, open an accessible choice dialog, select an offered action, and see a session-only demonstration receipt. Show simulated HRV separately from money, preserve quiet rest, and distinguish available choices from future tools. Phase 0 does not display agent communication options. The proposed schedule remains a design proposal, not a timer started by this preview.

Keep general navigation useful on smaller screens. Existing pages distinguish fixtures, loading failures, unknown position data, confirmed empty portfolios, and connected values. Preview controls for wakes, initialization, trading approval, configuration, messages, and identity/journal changes are disabled or replaced with clear read-only explanations. No fake write successes.

## Structure

- `frontend/src/data/`: shared UI contracts and explicit preview/connected client boundary.
- `frontend/src/preview/`: deterministic example data, action-window state, and testable local interactions.
- `frontend/src/views/`: existing operator screens plus Wake Choices.
- `frontend/src/components/`: accessible shared choice dialog.
- `scripts/build_ui_fixtures.py`: offline regeneration from public persona files and actual menu logic, with temporary state and blocked provider/network boundaries.
- `api/app.py`: backend read-only position/status contract corrections; application startup remains unlaunched.
- `frontend/tests/` and `tests/`: preview isolation, local action-state, runtime fixture parity, and API contract checks.

The existing frontend lockfile and TypeScript checker remain the toolchain. Managed diagnostics are unavailable because this repository is not attached to a Manus web project; use the existing check-only/build commands rather than reinitializing or changing hosting. Delivery remains a development branch and pull request against the existing foundation, not a public deployment.
