# Options and volatility calls: test options edge at zero broker risk

Status: approved. Phase 1 built in `build/options-calls-phase1`; Phase 2 built in `build/options-calls-phase2`; Phase 3 built in `build/options-calls-phase3`. Wake storage and stock-only database compatibility covered by regression tests.

Builds on [`CALLS_AND_SETTLEMENT.md`](CALLS_AND_SETTLEMENT.md),
[`OPTIONS_VIEW.md`](OPTIONS_VIEW.md), and the
[evaluation protocol](../research/ParadoxEdgeTrader_Evaluation_Protocol.md).

## In plain words

Stock calls (`up` or `down`) only test whether an agent guessed a ticker's
direction. They cannot tell whether an agent understands **how much movement
options are already pricing in**, **bid/ask spread drag**, or **time decay**.

Day runs already show every waking agent a live read-only
[`OptionsView`](../../core/market/options.py) (up to 10 near-money contracts across
the two nearest expiries, with bid, ask, IV, and per-contract quote times), and
[`closes.py`](../../core/market/closes.py) already fetches official daily closes
for call settlement.

This spec adds two plain, intuitive kinds of `call` on top of what the agents
already see—without adding broker risk, complex math, or extra prompt clutter:

1. **Volatility calls (`kind: "vol"`):** "Are options pricing too much or too little
   movement between now and expiry?"
2. **Option calls (`kind: "option"`):** "Will buying one quoted call or put from
   the options line pay off at expiry after paying the ask price?"

Both settle mechanically after expiry close using only `closes.py`—requiring **no**
historical options bar API, **no** mid-life option mark guessing, and **no** broker
or order access.

## Design principles (keep it simple for the agents)

- **Speak the language of the page, not raw OCC codes.** On the choice page, agents
  read `SPY options ... Dec 04 (8 days): call 595 2.10/2.18 IV 14.2%`. They should
  never have to construct an 18-character OCC symbol like `SPY261204C00595000` by
  hand; naming `symbol`, `expiry`, `option_type`, and `strike` directly matches what
  they actually see.
- **No new action, no pressure, same cap.** `vol` and `option` use the existing
  `call` action (`kind` defaults to `"stock"` when omitted, keeping existing stock
  calls unchanged). The same shared cap of **5 open calls per agent** applies across
  all calls. Passing remains a valid choice.
- **Zero broker risk, long-only.** A call is still a sealed forecast, not a trade.
  No sizing, margin, short options, or multi-leg spread complexity.
- **No look-ahead and no stale quotes.** Entry quotes and IV come strictly from the
  `options` snapshot committed in that wake's decision context, never re-fetched on
  retry. Refusal codes end the wake cleanly without crashing the tick:
  - `call_options_unavailable` (no `options` view or status not `open`)
  - `call_options_stale` (the selected contract's `stale` flag is true, or `quote_time` is missing)
  - `call_no_iv` (no valid `iv` on the chosen expiry's ATM contracts for a `vol` call)
  - `call_bad_option_quote` (missing/zero `ask`, or `ask < bid`)
  - `call_contract_not_shown` (contract or expiry not in that wake's committed `options` snapshot)
- **Indicative feed honesty.** `OptionsView` uses Alpaca's free `"indicative, delayed"`
  feed. Every stored call and hand-back labels entry quotes as indicative/delayed;
  fees and commissions remain explicitly unmodeled.
- **Separate direction from payoff.** Settlement always records the underlying's %
  move and SPY's % move alongside the volatility or option outcome, so *"direction
  right, option lost to time decay/spread"* stays visible.
- **Unknown stays unknown.** Missing expiry closes stay pending up to
  `SETTLE_GRACE_SESSIONS` (5 trading sessions), then become `unsettled`—never `0`.
- **Append-only, private, zero extra spend.** Stored in `calls.sqlite3` (carried in
  `CARRIED_FILES`). Every call travels inside the choice JSON with no second request.

---

## Phase 1: Volatility calls (`vol`)

### Choice shape

```json
{
  "action": "call",
  "kind": "vol",
  "symbol": "<options ticker shown>",
  "expiry": "<YYYY-MM-DD from options line>",
  "iv_view": "high" | "low",
  "confidence": "low" | "medium" | "high",
  "reason": "<optional, <= 400 chars>"
}
```

- `symbol` and `expiry` must match a pair in that wake's committed `options`
  snapshot, with `status == "open"` and non-stale ATM contracts.
- Requires at least **2 trading sessions** between `entry_session` and `expiry` so
  a single day's noise does not settle a volatility call.
- Seals at entry:
  - `entry_underlying_price` (with timestamp)
  - `entry_iv`: mean of the ATM call `iv` and ATM put `iv` for `expiry` (or the
    single valid ATM `iv` if only one side has `iv`)
  - `implied_move_pct`: 1-sigma implied move over the remaining trading sessions
    $n$ ($\text{IV} \cdot \sqrt{n / 252} \times 100$)
  - `atm_strike`, `entry_quote_time`, `feed` (`indicative, delayed`)

### Mechanical settlement (plain code via `closes.py`)

Once `expiry` has closed (after 16:30 Eastern):

1. Fetch official closes $S_0$ (`entry_session`) and $S_T$ (`expiry`) for `symbol`
   and `YARDSTICK` (`SPY`).
2. Compare the **actual absolute % move** $|S_T - S_0| / S_0 \times 100$ directly
   against the sealed **implied % move** (`implied_move_pct`), with a deadband of
   **±0.25 percentage points** (within ±0.25% of implied = `flat`):
   - `iv_view == "high"` (agent expected less movement than options priced):
     `right` if $\text{actual\_move\_pct} < \text{implied\_move\_pct} - 0.25$,
     `wrong` if $\text{actual\_move\_pct} > \text{implied\_move\_pct} + 0.25$.
   - `iv_view == "low"` (agent expected more movement than options priced):
     `right` if $\text{actual\_move\_pct} > \text{implied\_move\_pct} + 0.25$,
     `wrong` if $\text{actual\_move\_pct} < \text{implied\_move\_pct} - 0.25$.
3. Record `actual_move_pct`, `signed_move_pct`, `implied_move_pct`, `entry_iv`,
   `spy_move_pct`, and `outcome`.

### Tests (network blocked)

- Valid `vol` call seals `entry_iv`, `implied_move_pct`, `atm_strike`, `entry_session`, `expiry`, and `quote_time`.
- Refusals: closed market, stale ATM quote, missing `iv`, unknown `expiry`, `< 2` trading sessions remaining, shared open-call cap of 5.
- Settlement: `right`, `wrong`, `flat` (within ±0.25% deadband), missing expiry close -> `pending` -> `unsettled`, idempotent re-settle.

---

## Phase 2: Expiry-settled single-leg option calls (`option`)

### Choice shape

```json
{
  "action": "call",
  "kind": "option",
  "symbol": "<options ticker shown>",
  "expiry": "<YYYY-MM-DD>",
  "option_type": "call" | "put",
  "strike": <number from options line>,
  "confidence": "low" | "medium" | "high",
  "reason": "<optional, <= 400 chars>"
}
```

- Matches the unique contract in that wake's committed `options` snapshot (with
  `status == "open"`, `stale == false`, valid `quote_time`, and `ask > 0`).
- Entry price is always the **quoted `ask`** (never mid-price), preserving real
  bid/ask spread friction from the start.
- Seals `contract` (OCC symbol), `entry_bid`, `entry_ask`, `spread_pct`, `entry_iv`,
  `entry_delta`, `entry_underlying_price`, `expiry`, and `quote_time`.
- Raise `core/market/options.py:options_evidence` slice from `[:5]` to `[:10]`
  (`MAX_CONTRACTS`) so every contract printed on the options line is selectable.

### Mechanical settlement (plain code via `closes.py`)

Once `expiry` has closed (after 16:30 Eastern), using official close $S_T$:

- $\text{intrinsic} = \max(0, S_T - K)$ for a call, or $\max(0, K - S_T)$ for a put.
- $\text{net\_pnl} = \text{intrinsic} - \text{entry\_ask}$ (per share), and
  $\text{return\_pct} = (\text{net\_pnl} / \text{entry\_ask}) \times 100$.
- Outcome: `flat` if $|\text{net\_pnl}| \le 0.01$, `right` if $\text{net\_pnl} > 0.01$,
  `wrong` if $\text{net\_pnl} < -0.01$.
- Store `underlying_move_pct` and `spy_move_pct` alongside `intrinsic`, `entry_ask`,
  `net_pnl`, `return_pct`, and `spread_pct`.

### Tests (network blocked)

- Single-leg call and put seal `entry_ask` (not mid) and match by `(symbol, expiry, option_type, strike)`.
- Refusals: stale quote, closed market, `ask <= 0`, contract not in wake snapshot.
- Settlement: ITM profit, OTM total premium loss (`-100%`), ITM-but-net-loss (`direction` right, `net_pnl < 0` -> `wrong`), missing expiry close -> `unsettled`.

---

## Phase 3: Hand-back, Heartbeat counts, and Evaluation summary

- Extend `call_results_line` in [`calls.py`](../../core/runtime/rehearsal/calls.py)
  to quote settled `vol` and `option` calls in plain language (up to 2 wakes, newest
  first, facts only):
  - `vol`: *"Your vol call 4: SPY Dec 04 options priced ±2.1% (IV 14.2%, too high), made Nov 26. SPY moved +0.8% (SPY +0.8%). Right."*
  - `option`: *"Your option call 5: long SPY Dec 04 595 call at 2.18 ask (indicative, spread 3.7%), made Nov 26 (SPY 593.50). Expiry close 596.10 -> intrinsic 1.10 (-49.5%, SPY +0.4%). Wrong."*
- Extend `CallStore.counts()` and `Heartbeat.tsx` so the counts-only `Calls` column
  includes `vol` and `option` calls without revealing `reason` text.
- Add a small offline steward evaluation helper (`scripts/evaluate_calls.py`)
  summarizing calibration by confidence, stock vs. vol vs. option outcomes, and
  spread drag from settled records.

---

## Settled design choices

1. **Shared cap:** One cap of **5 open calls** per agent across stock, `vol`, and `option` calls.
2. **Intuitive `vol` yardstick:** Settle `vol` calls by comparing **actual % move vs. 1-sigma implied % move** ($\text{IV} \cdot \sqrt{n / 252}$) with a ±0.25% deadband—matching what the options line actually implies without noisy short-window std-dev math.
3. **Single-leg only in Phase 2:** Keep Phase 2 to single-leg long calls/puts selected by `(symbol, expiry, option_type, strike)`; leave multi-leg spreads for later if needed.

---

## Not in this plan

- Multi-leg spreads, short options, margin, or Alpaca order submission (covered by the separate paper-trading spec).
- Mid-life option mark-to-market before expiry.
- Leaderboards or agent-vs-agent scoring.
