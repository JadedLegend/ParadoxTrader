---
name: paradox-trader-runtime-loaded-files
description: Use when a ParadoxTrader PR adds a file the code loads.
category: deployment
---

# ParadoxTrader: ship a runtime-loaded file in the same commit as the code that loads it

- Some runtime code reads a markdown file at import time. `core/runtime/orientation.py` loads `core/runtime/skills/learning-from-inquiry/SKILL.md` into every agent's system prompt. Commit that file in the same commit and PR as the code that reads it. Code merged without the file fails every wake at startup.
- Before wrap-up, run `git status --short` and check every untracked or modified file the changed code loads. An untracked skill folder shows as `?? core/runtime/skills/`.
- Leave out stray files that are not part of the feature (for example a root `SKILL.md` holding one stray line). Name them to the user rather than committing or deleting them.
- Once installed on the server, confirm the next wake starts before reporting that the agents have the new text. See `paradox-trader-agent-heartbeat` for wake checks.
