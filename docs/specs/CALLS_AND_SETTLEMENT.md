# Calls and settlement: write a call down, check it later, hand back the result

Status: approved. Phase 1 is built (PR #53); phase 2 is built in `build/settle-calls`;
phase 3 is not built yet.

## In plain words

Right now an agent can think "I think gold drifts up this week," but nothing ever
checks. The lesson skill has nothing solid to learn from.

This adds a sealed envelope. An agent may write down a **call**: one ticker, which
way, by when, how sure, and why. The price at that moment is stamped on it from what
the agent was actually shown. When the date comes, plain code (no AI, no cost) opens
the envelope and writes down what really happened. On the agent's next wake, the
result is handed back. What the agent does with it is up to the agent: reflect, keep
a lesson, ignore it.

A call is a forecast, not a trade. It buys nothing, sizes nothing and touches no
broker. Paper trades stay a separate, later step.

## Ideas borrowed

- TradingAgents: record a decision, settle it after its holding period, hand the
  result back for reflection.
- ai-hedge-fund and Vibe-Trading: append-only records, and "unknown" is never 0.
- AI-Trader: every call carries the time of the data it was based on, so the
  witness can check nobody used later news.

## Rules that hold in every phase

- **No look-ahead.** The starting price comes from the market window already
  committed with that wake's choice. It is never re-read later. A resumed wake sees
  the same price.
- **Append-only.** A call is never edited. A settlement is a separate row. An agent
  that changes its mind writes a new call or a journal note; the old call still
  settles.
- **Unknown is unknown.** No fresh price at call time: the call is refused with a
  reason. No price at settle time: the call stays pending and says why, never 0%.
- **No new spend.** Making a call is one choice (one request, like rest or
  journal). Settling costs no AI requests. The daily budget is unchanged.
- **Private by default,** like journals. The witness sees only a mechanical count
  ("tempest made a call; 2 open; 1 settled"), not the reason text.
- **Bounded.** At most 5 open calls per agent. Watchlist tickers only.

## Phase 1: make a call

- New choice: `{"action": "call", "symbol": "GLD", "direction": "up" | "down",
  "horizon_days": 1-20, "confidence": "low" | "medium" | "high", "reason": "..."}`.
  Reason up to 400 characters. `horizon_days` counts trading days.
- The choice instructions list it next to journal, inquire and the others.
- Offered only on wakes that have a market window (the live day runs). The frozen
  decision record carries `call_options`, so the witness can tell it was offered.
- Stored in `calls.sqlite3` in the run, carried to the next day with the rest of
  the home: agent, wake, symbol, direction, horizon, confidence, reason, entry
  price, the price's own `as_of`, and the entry session (that price's Eastern
  date). No settle date is stored: phase 2 counts real trading days from the
  daily bars, so holidays need no hand-kept calendar.
- Refusals end the wake as failed with a code, never crash the tick:
  `call_symbol_not_watched`, `call_no_price` (no committed price, or a price with
  no time of its own), `call_too_many_open`, `call_not_offered`.
- The next choice lists the agent's own open calls (symbol, way, horizon, entry
  session, confidence and sealed price), so it knows what's pending. No settle
  date is shown, since none is stored.
- The witness records "call offered" on wakes whose decision record carries
  `call_options`, separate from the five-item recorded menu, and never the reason.
- Tests: a valid call is stored with the committed price; resume reuses it; each
  refusal; a price with no time is refused; the cap of 5; append-only; offered
  only beside a window; the next wake lists the open call.

Status: built in `build/calls-phase1`.

## Phase 2: settle (code only)

- The heartbeat tick, after the close on a trading day, settles every open call
  whose settle date has passed.
- It reads that day's closing price from the data account (the same paper key the
  window already uses), plus SPY's close for the same two dates as a yardstick.
- It writes a settlement row: exit price and time, % move, SPY's % move, and
  `right` / `wrong`. A move under 0.1% counts as `flat`, neither right nor wrong.
- No price: the call stays `pending_price` with the reason and retries next tick.
  After 5 trading days it becomes `unsettled` with that reason.
- Never blocks or delays agent wakes. A settle failure is a note in the heartbeat
  problems list.
- Tests: right, wrong, flat; holiday and weekend settle dates; missing price, then
  retry, then unsettled; settling twice is a no-op.

Status: built in `build/settle-calls`. How it works:

- `core/market/closes.py` reads Alpaca's daily bars (IEX feed, the data
  account's paper key). Each bar's Eastern date is one trading session, so the
  sessions that come back are the calendar: Thanksgiving simply has no bar.
- The settle session is the `horizon_days`-th session after the entry session.
  The move compares that close with the sealed entry price. SPY's move compares
  its closes on the entry and settle sessions; when either is missing it is left
  out, never 0.
- A session counts only once it has closed (after 16:30 Eastern), so a
  still-moving bar is never used.
- Every tick checks, after its wakes and at most every 30 minutes, and only
  while some call is open. A missing close stays pending and becomes
  `unsettled` 5 sessions later. With no market data at all, weekdays are
  counted instead (plus 2 for holidays), so an outage still ends.
- Settlements go into the newest day run's `calls.sqlite3`, which carries to
  the next day. A settled call leaves the agent's open list.
- Only on `mode: real` with Settings, like the market window. Pending reasons
  show on the heartbeat page's problems list: ticker, date and call number,
  never the agent's reason.

## Phase 3: hand the result back

- On the agent's next wake after a settlement, continuity includes it as quoted
  data: "Your call: GLD up within 5 days (medium), made Nov 20 at 241.10. Settled
  Nov 27 at 243.00: +0.8%, SPY +0.3%. Right." It shows on up to 2 wakes, then
  drops out of routine context. It stays in the record.
- No forced reflection. The existing journal and lesson skill are how an agent
  chooses to keep something. The call's id is a reference the agent can cite.
- The Heartbeat page (read-only) gains a per-agent line: open, settled, right,
  wrong. Counts only, no reason text.
- Tests: the hand-back appears once settled and stops after 2 wakes; references
  resolve; the page shows counts and never the reason.

## Not in this plan

Paper trades, sizing, options calls, agents seeing each other's calls, scoring
agents against each other, and leaderboards. Any of these can come later on top of
settled calls.

## Owner decisions

1. Horizon range: 1 to 20 trading days (about a month)?
2. Should other agents see a settled call (not its reason), or keep calls fully
   private?
3. Is 5 open calls per agent the right cap?
