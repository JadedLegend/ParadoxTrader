# Market window

The agents' home has a library but no window. On the first live day 11 of 20
choices were library reads, and nobody chose to ask a question
("inquire"). The inquire activity already has a slot for market data, but today it
always says `"market_data": {"status": "unavailable"}`.

This plan gives the home a read-only window onto the market, one phase at a
time. Nothing here can place, change or cancel an order.

## Phase 1: prices through the window

**What the agents get**

- A small, shared snapshot of prices: the last price, the day's change, and the day's
  high, low and volume for a short watchlist. The default watchlist is SPY, QQQ, IWM, TLT and
  GLD: the broad market, small companies, bonds and gold. It is five symbols,
  which is the most the inquire slot holds.
- **When an agent chooses inquire:** the snapshot fills `market_data.quotes`
  instead of "unavailable".
- **On every choice:** one line in the choice context says what the window
  shows, for example "Market window (as of 14:30 ET, delayed): SPY +0.4%, QQQ +0.7%,
  ...", so the agent knows there is something to look at. It is quoted as untrusted
  data, below the instructions, like the library excerpts.
- **When it fails:** the market is closed, the data is stale, or the fetch fails.
  The line then says so plainly ("market closed; last close ...", or
  "window unavailable"). It never shows a made-up number.

**Where the data comes from**

- Alpaca's market data API: `GET data.alpaca.markets/v2/stocks/snapshots`
  with the free IEX feed. It uses the agent's own saved Alpaca paper key.
- A new module, `core/market/window.py`, that can only make that one GET. It does
  not reuse `core/trading/alpaca.py`, which can place orders.
- Live (`AK`) keys are already refused when they are saved in Settings.

**Limits**

- **One fetch per 15 minutes at most,** shared by all agents and cached in
  the sessions folder. A wake never waits more than 10 seconds for it, and a
  failed fetch is not retried until the next window.
- **Small and fixed:** at most 5 symbols and about 1 KB of text, so it costs
  almost nothing in prompt space.
- **Not saved as a fact.** If an agent writes about a price, the note is the
  agent's own note; the snapshot is not stored as a memory.

**Owner controls**

- The watchlist goes on the Settings page as one box ("up to 5 tickers").
  The default list applies until it is changed.
- The dashboard shows the last snapshot's time and whether it worked.

**Done when**

- The tests use a scripted HTTP fake and a blocked network. They cover
  inquire getting quotes, the choice line, market closed, a stale snapshot, a
  failed fetch, the 15-minute cache, a refused live key, and that no order
  endpoint is ever called.
- On the droplet, one wake shows the window line and one inquire gets real
  quotes.

- Status on the dashboard (the last snapshot's time and result) moves to the
  heartbeat page; phase 1 keeps the result in `settings/market/window.json`.

## Phase 2: agents recommend tickers (owner's request)

Any agent may propose one ticker for the window, with a reason and the research
behind it. The ticker joins the window only when more agents approve it than
reject it.

- **Proposing:** a proposal names one ticker, a short reason in the agent's own
  words, and at least one piece of grounding from its own record: a library
  section it read, an inquiry it made, or a window line it saw. A proposal with
  no grounding is not accepted. Each agent can have at most one open proposal.
- **Voting:** proposals appear as one line in the other agents' choice context.
  An agent may approve or reject a proposal during a wake (a small new choice,
  `vote`), with an optional one-line reason. The proposer cannot vote on its own
  proposal. A vote is final.
- **Deciding:** a proposal passes when approvals are more than rejections once
  at least four of the other six agents have voted, or once it is three days old
  with at least one vote. It lapses after three days otherwise. Ties fail.
- **The window:** approved tickers join the owner's list. The owner's tickers
  always stay, approved ones fill the spare places, the oldest approval drops
  out first, and the total stays at 10 or fewer. The owner can remove any
  ticker in Settings.
- **Owner view:** Settings lists open proposals with their reasons, grounding
  and votes.

## Later phases (each its own PR, after the one before is merged)

3. **Headlines.** Three to five headlines for the watchlist, from Alpha Vantage
   or FMP, in the same window and with the same caching.
4. **The agent's own paper account.** Each agent sees its own paper positions
   and cash in `own_positions`, read-only, never another agent's.
5. **Paper trading.** This is a separate spec with its own guardrails, and only
   when the owner asks for it.
