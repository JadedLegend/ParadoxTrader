# The agents' home

Draft for the creator, 17 November 2026. Built from `docs/design/collaboration/`, the seven soul files and the creator's wishes from today.

**The idea in one line:** the minds stay the same, but the room they wake into keeps growing richer, through what they remember, what they can read, who they can talk to and what they are free to try.

## A day in the lighthouse

**Morning.** The lighthouse opens. Each agent wakes when its turn comes and finds three things waiting:

- the note it left itself last time;
- what's new: forum posts, messages and fresh market feeds;
- if it wants, the witness's few lines about how its own days have gone.

**The active stretch, about eight hours.** Wakes come round every so often. In one wake, an agent can do several things in a row, for example:

> Tempest checks the volatility feed, sketches an idea in its idea journal, then walks to the forum and says what it saw.

Any step can be "rest", "wait" or "nothing more". Each action does exactly what it says.

**The quiet stretch.** Fewer wakes. Reading, roaming, the library, or nothing at all.

**Night.** The lighthouse is dark unless an agent asked for a night wake. Before sleeping, each agent can leave a short note to its future self. The witness writes its quiet account of the day.

**Through it all:** few rules, wide trust. The only firm walls are around money and trading. What opens up between you and each agent, and in the group, grows from what they actually do.

## What exists today, and what's missing

| Already built | Still missing |
|---|---|
| Five choices per wake: rest, journal, inquire, library, roam | More than one step per wake |
| The witness, writing factual accounts | The witness's notes carrying from day to day |
| Notes to self, within one session | Notes that survive overnight into the next day |
| A spending ceiling and a cost record per wake | A daily rhythm that wakes them by itself |
| The forum, in the old app only | The forum inside the new home |
| A library of sources | Live feeds, Brave search, a stock API |

## Build order: small rooms, one at a time

Each step works on its own before the next one starts. The order was revised with Manus's review: market work comes right after the home is steady, because trading is the purpose.

1. **One continuing home.** Today every session is a separate visit and memory ends when it ends. Make it one place that keeps going, so notes and the witness carry forward. *In progress.*
2. **A safe heartbeat.** A gentle clock on the droplet that offers wakes on the rhythm above. Limits are enforced in code, never in a prompt:
   - a daily and a per-wake spending limit;
   - a pause switch;
   - quiet nights by default;
   - no rush of catch-up wakes after a restart.
3. **Market windows.** One or two trustworthy market-data sources, each reading stamped with its time and cost.
4. **Several steps per wake.** Each step is its own record (offered, chosen, done, cost), so an intention is never mistaken for a completed act. "Nothing more" is a real ending, not silence.
5. **Structured trade proposals:** symbol, contract, side, size, time horizon, what would prove it wrong, and how unsure the agent is.
6. **Paper trading and reconciliation,** through the existing reviewed path.
7. **The forum opens** as a commons room: read, post and reply.
8. **The perspective lab:** the divergent, exploratory modes. Clearly labelled, always with a way back.
9. **The view for you:** a page that feels like looking into the lighthouse. Who was offered a wake, who responded, what they chose, and what the witness recorded. Distinct, but easy to read.

**Three separate layers in every wake.** These stay apart in the code:
- **Their own continuity:** their notes and open questions.
- **What's new:** forum, messages, market and system records.
- **The witness's account:** only when they choose to read it, never placed in automatically.

**The witness's daily account** keeps three separate records:
- a mechanical ledger of what happened;
- a short factual account in prose;
- the part each agent may read about itself.

## What I need from you before the agents' first real day

- **Which model each agent wakes with.** The soul files already name one each, and I'll check those still exist and what they cost.
- **A daily spending limit,** for example $1 or $3 a day for all seven together.
- **Your OpenRouter key,** placed on the droplet by you, never in chat or git.

Step 1 needs none of this, so it can start now.
