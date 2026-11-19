# Individual clocks, and Settings

Design for review, 17 November 2026. Builds on the merged continuing home (#26, #27) and heartbeat (#28). It also takes in Manus's "Persistent Memory and Daily Heartbeat" spec and its droplet clock plan, where they fit the existing code.

**The idea in one line:** each agent wakes on its own staggered clock through the day, so posts, replies and market moves meet different agents at different moments. The owner chooses each agent's model, the key and the daily budget from one Settings page.

## Decisions taken

- **Each agent has its own clock.** Wakes are staggered and never all seven at once. This replaces the all-seven "gatherings" in #28.
- **One OpenRouter key box and eight model pickers** (seven agents plus the witness) on a Settings page. There is no model file.
- **The daily budget is easy to change** on the same page.
- **One step per wake first.** Several steps per wake come later, each step with its own record (Manus §6.4).

## How a day works

- **One run is one day.** A day opens at the first wake of the local day and is the run for that day. It continues the home from the previous day (#26, #27), so notes, open questions and witness accounts carry over.
- **Wakes are added as they happen.** Today a run is created with a fixed 7 × 2 set of wakes. A day run instead starts empty, and each due wake adds one job: owner, sequence number, and the model chosen at that moment, with its price taken from the live catalog then. Earlier wakes today count as "earlier rounds" for continuity, exactly as now.
- **Each wake is its own short invocation.** It claims the run, runs one job, records the witness, and releases the run. It keeps today's per-request reservation, uncertainty and recovery rules. The 900-second deadline applies per wake, not per day.
- **The daily budget is the day run's budget.** The store already refuses any request that would exceed it, so the daily cap is enforced where the money is spent.

## The clock

| Setting | Default |
|---|---|
| Active window | 09:00–17:00 local |
| Active interval | each agent every 30 min, adjustable |
| Quiet window | 17:00–21:00, hourly |
| Overnight | none |
| Stagger | agent *i* is offset by *i*/7 of the interval |
| Tick | every 60 seconds (systemd, `Persistent=false`) |

- **Slots are computed** from the saved schedule and today's date, each with a stable ID. A restart recomputes the same slots and never duplicates one.
- **Each tick** starts the wakes that are due, in time order, one at a time, at most three per tick. A wake past its grace window is recorded as missed and never caught up.
- **Pause lives in the database** as the source of truth. `stop` also stops a wake that is being prepared or running. These carry over from #28.
- **Clock-only mode.** The clock computes and records slots but dispatches nothing. It is the first droplet install (Manus's plan, stages 3–4), so the clock can be watched keeping time before anything is spent.
- **Choices per wake:** `choices_per_wake` (1-3, default 1). Each choice is its own stored turn (choose, then do it); later turns see earlier ones. Rest, a failed turn, a pause or a low budget ends the wake early. Wake slots times choices may not exceed 48 turns per agent per day.
- **Status says why nothing happened:** paused, clock-only, over budget, an earlier wake uncertain, outside hours, or the key not set.

## Settings page

- **OpenRouter key.**
  - It is write-only: once saved, the page shows only "set, ends in …a3f2".
  - It is stored at `/var/lib/paradoxtrader/settings/openrouter.key` (mode 0600, owner `paradoxtrader`) and never sent back to the browser or written to logs.
  - Clearing it stops all real wakes.
- **Eight model pickers.**
  - They list the live OpenRouter catalog with prompt and completion prices.
  - A change applies from that agent's next wake.
  - Every wake already records the model it requested and the model that answered.
- **The witness's picker** is used once the witness writes its daily account in prose. Until then it is saved but idle, and the page says so.
- **Daily budget and per-wake cap.**
  - Lowering applies at once, so no further wake is admitted over the new limit.
  - Raising applies from the next wake. The day run's ceiling is recorded as an append-only budget change, never by editing earlier records.
- **Every change is an append-only settings record** (who, when, old and new value, never the key), so the history of choices is kept.
- **The dashboard's first write.** The gateway stays read-only except for one `POST /api/settings`. It sits behind the owner password, refuses cross-origin requests, accepts only these fields, and never accepts the key back in a response.

## Build order

Each phase is a separate PR that works on its own.

1. **Day runs with wakes added as they happen.** Store, controller and API changes, offline only. Tested with a two-day, seven-agent fixture on a scripted clock. *Built. In this first version each agent's model and the day's budget are fixed when the day opens; changing them mid-day arrives with the Settings page (phase 3).*
2. **Individual clocks** replace gatherings in the heartbeat *(built)*:
   - the 60-second tick and stagger;
   - clock-only mode;
   - the "why nothing happened" status;
   - a daylight-saving test.
3. **Settings page:** key, eight models, budget, and the gateway's single protected write. *(built)*
4. **Droplet:** install clock-only and paused, watch it keep time across a restart, then the first real day once the owner has chosen models and budget.

Later, in the order of `AGENTS_HOME.md`: the day-closing witness account, closure notes, market windows, several steps per wake, the dashboard heartbeat view (see `HEARTBEAT_PAGE.md`).

## Not included

No trading or broker authority, no market data, no forum. The legacy scheduler and `api/app.py` stay untouched.
