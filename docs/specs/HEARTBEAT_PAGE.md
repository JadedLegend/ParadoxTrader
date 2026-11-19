# Heartbeat page

A read-only dashboard page that answers four questions without asking anyone:
is the home awake, who woke today and what did they choose, what has it cost,
and is anything wrong.

## What it shows

- **Now:** the heartbeat's own status line, in plain words. For example:
  "Running: next wake 10:08 (Siren)", "Paused", "Clock-only: nothing is
  dispatched", "Today's budget is spent" or "Quiet: no more wakes today".
- **Today:** wakes so far, how many failed or were missed, and the next wake.
- **Cost:** what was actually spent today, what is set aside for requests in
  flight, and the daily budget. Reservations are worst-case figures, so they
  are labelled as such.
- **Needs a look:** each failed or unsure wake, naming the agent, model and
  reason. If there is nothing, it says so.
- **Each agent:** the last wake (time and choices) and the next wake.
- **Today's wakes:** every slot in time order, with its agent, outcome and
  choices.
- **What the agents see:** the current market window line, headlines, X posts
  and Reddit lines exactly as they are quoted to the agents, with each feed's
  last check time and whether it worked.

## Rules

- It is read-only. It never wakes, pauses or changes anything, and it never
  shows a key or an agent's private notes.
- The data comes from the heartbeat's own status and its ledger, the day runs'
  totals and the market caches, served at `GET /api/heartbeat` by the private
  dashboard.
- Every part shows its own empty and error state. A failed feed or a missing
  ledger never blanks the page.
- The page refreshes every minute while it is open.
