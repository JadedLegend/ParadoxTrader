---
name: paradox-trader-dashboard-preview
description: Use when previewing the ParadoxTrader dashboard locally.
category: verification
---

# ParadoxTrader dashboard: local preview on Windows with throwaway data

- Put the preview launcher in the scratchpad, never in the repo. It imports the gateway from the settings worktree and calls `create_gateway` with a scratch `sessions_root`, the built `frontend/dist`, a throwaway owner login, a password hash read from a scratch file, and a scratch `settings_dir`.
- Windows has no `os.O_NOFOLLOW`. Set it to `0` in the preview launcher only, and say so in a comment. Do not patch the gateway for that.
- Server modules must still import on Windows. POSIX-only modules such as `fcntl` go in `try: import fcntl` / `except ImportError: fcntl = None`, and the code that uses them skips the lock when it is None. Before serving, run `python -c "import MODULE"` on Windows; a top-level `fcntl` import breaks the whole preview.
- Start the launcher with the scratch venv's Python, for example `../venv/Scripts/python.exe serve.py` from the scratchpad preview folder. The system Python lacks starlette and exits with ModuleNotFoundError.
- Serve with uvicorn on `127.0.0.1:8091` in the background. Stop it with `TaskStop` on its task id and confirm the port is free.
- Open `http://127.0.0.1:8091/config` in the browser pane and check text first (`get_page_text`, `find`). Confirm saves with `read_network_requests` on `/api/settings`.
- Settings checks: a saved key shows only its last four characters and the field clears; "Remove key" appears; the model list loads from the live catalog in the browser.
- For a phone-width check, set the viewport, test for horizontal overflow with JavaScript, then reset it with preset `desktop` before the turn ends.
- Use only a fake test key and throwaway data. Never type a real key into the preview.
- The private dashboard has no public HTTPS address, so Better Design's `finalize-dashboard-review` cannot return VALID for it. Measure at 1440 and 375 locally, and say in the PR body that the public-preview review was not done. Do not claim it passed.
- Before the turn ends, delete the preview's scratch `settings_dir`. A key that reaches the preview persists there, and a Check connection run then calls the live provider with it.
