# Options view

The market window shows prices, headlines and posts. This adds a small,
read-only look at options for one ticker, so the agents can ask the question
the project exists for: what disagrees between price, volatility, time and
liquidity. Nothing here can place, change or cancel an order.

## Phase 1: one ticker, a few contracts

**What the agents get**

- One line on every choice, under the price line. For example:
  "SPY options (Alpaca indicative feed, delayed, Nov 21 expiry, 2 days):
  at-the-money IV 14.2%, call 733 bid 2.10 ask 2.18, put 733 bid 2.35 ask
  2.44, spread 3.7%."
- When an agent chooses inquire, the inquiry also gets up to five
  contracts, each with its strike, type, expiry, bid, ask, implied
  volatility and delta.
- When the market is closed, or the data is missing or old, the line says so.
  It never shows a number it did not receive.

**What is fetched**

- One ticker, SPY by default, chosen in Settings.
- The two nearest expiries at least one day out, and the strikes nearest the
  current price: two calls and two puts each, plus the at-the-money pair.
- Alpaca's options snapshots endpoint on the market data host, read-only, with
  the free **indicative** feed and a designated data account's paper key.
  Alpaca says this feed adjusts quotes and delays trades, so every line and
  record carries "indicative, delayed". Good enough to rehearse the thinking;
  not good enough to price a short-lived edge.
- Each contract keeps its own quote time. The record also keeps the fetch time,
  the feed, the data source and the account label (never the key).

**Limits**

- At most one fetch every 30 minutes, and only during market hours. It is
  shared and cached like the price window, and a failed fetch waits for its next
  window. A wake never waits more than 10 seconds for it.
- At most 10 contracts kept and about 600 characters of text, so prompts stay
  small.

**Done when**

- Tests use scripted data with the network blocked. They cover parsing,
  per-contract times, closed market, missing fields, the cache, only the
  read-only address, and the choice line and inquiry records.
- On the droplet, one wake shows the options line during market hours.

## Also in this phase (from the 11/19 reviews)

- **One data account:** the price window and the options view use one paper
  account named in Settings, instead of whichever agent woke. The record names
  the account by label.
- **Per-price times:** each price in the window keeps its own quote time, so
  one fresh ticker can no longer make a stale one look current.

## Later

- Open interest and volume per contract. These come from a separate contracts
  endpoint.
- A second ticker, or the agents' approved tickers (ticker proposals, phase 2
  of MARKET_WINDOW.md).
- A paid real-time feed, once a paper round trip shows the thinking is worth
  pricing precisely.
