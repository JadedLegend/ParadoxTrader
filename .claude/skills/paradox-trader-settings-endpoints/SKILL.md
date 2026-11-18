---
name: paradox-trader-settings-endpoints
description: Use when adding a Settings page route or button.
category: frontend
---

# ParadoxTrader Settings endpoints: register the route on the page

- Every new Settings path must be added to the private host's list in `frontend/src/data/client.ts` (`servedByPrivateHost`). If it writes, add it to `isSettingsWrite` too.
- A missing entry fails silently: the browser never sends the request, and the button shows a generic failure. When a Settings button does nothing, check `read_network_requests` for the path first. If it never appears, fix the allowlist before touching the server.
- Add a client test that the path is served and that only POST is a write, in `frontend/tests/client.test.ts`.
- After any change under `frontend/src`, rebuild the private page (`VITE_RUNTIME_MODE=connected VITE_HOST_PROFILE=private npm run build`) before previewing. The preview serves the built output.
- Show check results as one row per item with a tick or cross and a short reason. Check the saved values, and say so on the button.
- Key handling follows paradox-trader-write-only-secrets.
