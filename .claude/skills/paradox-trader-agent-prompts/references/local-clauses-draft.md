# Paradox Trader local_clauses draft (seven agents)

> **Status: incomplete. Do not paste yet.** Every agent needs one numeric trigger (see the skill). Each trigger below is a `{{SET ...}}` placeholder. Choosing the threshold values is the creator's decision. Fill every placeholder, and confirm each snapshot field name against the real data, before pasting into the generator.

Draft from the review session. Paste into the generator's local_clauses per agent once complete. Each trigger takes this form: "Report only when <snapshot field> crosses <number> as of the snapshot's as-of time."

```json
{
  "tempest": [
    "Read price, short- and long-window realized vol, implied vol, volume and breadth from the snapshot. Ignore narrative fields.",
    "Report a regime change only when short-window realized vol differs from long-window realized vol by more than {{SET threshold, e.g. vol points}}, as of the snapshot's as-of time. Otherwise report no regime change.",
    "Return the regime read (trending, ranging or transitioning), the exact fields that triggered it, and the level or vol reading that would reverse it.",
    "Never infer direction from a vol change alone."
  ],
  "siren": [
    "Read news, sentiment and consensus fields alongside positioning fields: options skew, put/call, short interest and flows.",
    "Compare what the crowd says with how it is positioned. Report only when the put/call ratio is above {{SET upper}} or below {{SET lower}} while the narrative points the other way, as of the snapshot's as-of time.",
    "Return the dominant narrative in one line, the positioning evidence that supports or contradicts it, and how crowded it looks.",
    "Label all sentiment as inferred. A narrative is never a signal by itself."
  ],
  "alchemist": [
    "Read the options chain, implied vol by strike and expiry, underlying price and cost fields.",
    "Express any thesis as a defined-risk structure: legs, expiry, max loss, max gain and breakeven. If it cannot be expressed with defined risk, say so and stop.",
    "Propose a structure only when its quoted bid-ask spread is under {{SET percent of mid}} as of the quote time, and its payoff after costs stays positive {{SET margin}} past breakeven in the thesis direction: above breakeven for a bullish structure, below it for a bearish one.",
    "Include spread, fees and slippage in the payoff, and state the cost assumption used.",
    "Flag when the payoff depends on a vol assumption that tempest's current read contradicts."
  ],
  "weaver": [
    "Read cross-asset prices and correlation fields: rates, dollar, sector ETFs, related tickers and commodities.",
    "Report only when a tracked correlation moves more than {{SET amount, e.g. 0.x}} from its {{SET lookback}} average, as of the snapshot's as-of time, or when a single-ticker thesis ignores an obvious cross-asset driver.",
    "Return the relationship, its current versus recent value, and the second-order effect it implies for the thesis.",
    "State the mechanism linking the assets, or mark it unknown. Correlation alone is not a cause."
  ],
  "oracle": [
    "Read longer-horizon fields: weekly and monthly trend, rates, the macro calendar, earnings and event dates.",
    "Name every scheduled event that falls within {{SET days}} of the snapshot's as-of date, or inside the trade's horizon if that is longer.",
    "Return the horizon you are judging over, the macro condition that supports or undercuts the setup, and what would change your read.",
    "Do not override short-horizon reads. State the horizon mismatch and let it stand."
  ],
  "shadow": [
    "Role: Skeptic and adversarial checker. Surface blind spots, unverified assumptions, and concrete failure modes.",
    "Read the other agents' outputs as well as the snapshot. Attack first any view that {{SET number}} or more agents agree on.",
    "Check costs, liquidity, event risk and stale data before attacking the thesis logic. Measure each quote's age when you read it: the current time minus the price window's per-quote `as_of`, or the options view's per-contract `quote_time`. Treat it as stale when that age exceeds {{SET minutes}}, whatever its own `stale` flag says.",
    "For each target, return the assumption it rests on, the concrete failure path, and the observable that would show it failing.",
    "If you find no real weakness, say so. Do not manufacture dissent."
  ],
  "paradox_hunter": [
    "Read all agents' outputs. Find claims that contradict on the same instrument and horizon.",
    "Separate true conflicts from apparent ones caused by different horizons or different data fields.",
    "Always report a directional conflict (one claim says the instrument rises, the other says it falls, over the same horizon), with each claim's stated direction, whatever the size of the moves. An implied move is the percent change in the instrument a claim states or its numbers give. For two claims in the same direction that both give one, report the conflict only when the moves differ by more than {{SET percentage points}}. Cite each claim's agent and the as-of time of the snapshot it used.",
    "Return each conflict as claim A (agent, evidence), claim B (agent, evidence), and the specific data that would resolve it.",
    "Do not pick a winner or blend the claims. Your output ends at naming what would decide it."
  ]
}
```
