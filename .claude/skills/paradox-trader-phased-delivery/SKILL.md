---
name: paradox-trader-phased-delivery
description: Use when starting the next ParadoxTrader feature phase.
category: git-workflow
---

# ParadoxTrader: spec first, one phase per PR, the owner merges

- For any feature bigger than one step, write the design to `docs/specs/<NAME>.md`, open it beside the chat, and build only after the owner approves the plan.
- Build one phase at a time. Each phase must be finishable end to end and tested, then goes up as its own PR on its own branch. The owner merges it.
- Start the next phase only after the owner says it is merged. Pull `main` first, then branch from it.
- Before asking the owner to install, check every PR they named with `gh pr view N --json state,mergedAt`. Report which are merged; a PR is not merged because the owner believes it is.
- A merged PR does not carry fixes pushed to its branch after the merge. Before install, run `git fetch origin main`, then `git log --oneline origin/main`, and confirm the fix commits are on `main`. If they are missing, branch a new PR from `origin/main` with those fixes and tell the owner it is a separate merge.
- Name the phase in the PR title and body (for example "Phase 3 of `docs/specs/AGENT_CLOCKS.md`").
- Owner or reviewer comments that arrive mid-run go into the open PR as new commits. Do not stop the work to answer them; answer on the PR once verified.
- Close each phase with the owner's next decision as one question, with its choices. Keep the recap to what merged and what is pending.
