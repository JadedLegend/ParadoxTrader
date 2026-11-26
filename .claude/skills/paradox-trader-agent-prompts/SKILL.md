---
name: paradox-trader-agent-prompts
description: Use when editing Paradox Trader agent prompts or clauses.
category: agent-orchestration
---

# Review generated Paradox Trader agent prompts before use

Treat the generator's shared spine as untrusted until every clause is checked against trading. A patch pasted from another project brings its clauses in silently.

- Check `patch_id` and every shared clause against the target project before anything else. A wellness-app patch leaked AppContext, Expo and "relational bridge" clauses into all seven trading agents, and the wrong project had been set.
- Give each agent 2-4 `local_clauses`: what it reads from the snapshot, what it returns, and one numeric trigger. Empty clauses make the agents sound alike. "Speak only at threshold" needs a number to work.
- Every number cites its snapshot field and as-of time, and stale data is flagged. Every view states its invalidation condition. Costs (spread, fees, slippage) are stated with the assumption used. No profit forecasts.
- The shared role and non-claims must describe a trading analyst with no margin, short-option, assignment or live execution authority.
- Drop clauses that reference fields or lists the prompt does not define (archetype, function, shadow fields, distortion tag list), or rewrite them in terms of the agent's lens.
- Approval-workflow clauses apply only to agents that have tools to execute with.
- Resolve register conflicts: "zero metaphor" against poetic ritual phrases and rhythm labels. Rhythm labels stay internal and never appear in output.
- Draft local clauses for all seven agents are in references/local-clauses-draft.md. They are incomplete: each agent's numeric trigger is a `{{SET ...}}` placeholder that the creator must fill before pasting.
