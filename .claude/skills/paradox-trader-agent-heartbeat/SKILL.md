---
name: paradox-trader-agent-heartbeat
description: Use when editing ParadoxTrader heartbeat clocks or budget.
category: agent-runtime
---

# ParadoxTrader heartbeat: individual clocks, owner settings in the dashboard

- Agents wake on their own staggered clocks, one wake per agent per slot. Never schedule one gathering of all agents.
- The owner's choices (each agent's OpenRouter model, the key, the daily budget) live in the dashboard Settings page and its `settings_dir`. Do not add server config files for them. The key is write-only: the UI shows only "Set, ends in …" and never echoes it.
- Budget: lowering it applies at once; raising it applies from the next wake. A model change or a budget raise closes today's run and opens a new segment of the same day that continues the home. Spend is summed across that day's segments.
- Carried-over "already done" markers must be keyed by day, or yesterday's markers make today's wakes look like repeats.
- The store accepts memory references only from earlier rounds of the same day. A carried day has to be taught to that check, or its references are rejected.
- Until the owner has chosen models and a budget, the heartbeat runs clock-only (keeps time, wakes no one, spends nothing). Switching to live dispatch is an explicit owner step.
- Before that switch, build the day manifest against today's live OpenRouter catalog using the seven agent models (`agent_models()`, never the eight-slot `models()` that includes the witness). If the build raises, stay clock-only and fix it first.
- On a failed live wake, restore the clock-only config before diagnosing. A wake refused by the spend guard spends nothing; the cause is usually a catalog shape the guard does not yet read (see provider-key-model-check).
- The witness account stays idle until the witness writes it in prose; the Settings page says so.
- When the owner says "latest <model family>" for a slot, query the OpenRouter model list sorted by `created` and take the newest plain text line of that family. Skip variant lines whose name marks another modality (for example "omni") unless the owner asks for them. Report the chosen id and the rejected alternative.
- A failed wake writes a slot note naming the agent and model, for example "siren on xiaomi/mimo-v2.6-flash: http_rejected". Read that note and the status problems list before blaming the model or the key.
- After the owner says Settings is filled in, verify on the droplet by reading the saved settings through the app's own `OwnerSettings` read, not the UI. Report the count of models and key boxes set per slot. Do not infer "saved" from a page that looked filled.
