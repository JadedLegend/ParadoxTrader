# Practical Build Path: Infrastructure, Costs and Fastest Path to a Paper-Trading MVP (as of 2026-11-14)

All prices were retrieved on 2026-11-14 unless noted. Vendor pricing changes often. Re-check every number before committing money. Model names below are taken exactly from the vendor pricing pages fetched today.

## Q1. Alpaca: options support in paper accounts, data feeds, SDK, rate limits, fill realism; alternatives

### Takeaway
Alpaca paper accounts have options enabled by default, up to Level 3 (spreads), with multi-leg ("mleg") orders. That is enough to go from mock broker to real paper options orders in days. The weak points are the free "indicative" options feed (real OPRA data costs $99/mo), paper fills that ignore liquidity, and exercise/assignment events that only appear the next day and must be polled.

### Cited Findings
- **Options levels:** Level 0 is disabled. Level 1 is covered calls and cash-secured puts. Level 2 adds buying calls and puts. Level 3 adds buying call and put spreads. There is no naked short option level on the page. — [Alpaca Options Trading docs, last updated 2026-09-16](https://docs.alpaca.markets/docs/options-trading)
- **Paper accounts:** options trading is enabled by default and can be disabled under Account > Configure. Live options require a separate approval process. — [Alpaca Options Trading docs](https://docs.alpaca.markets/docs/options-trading)
- **Order types:** market, limit, stop and stop_limit. Stop and stop_limit are single-leg only. Time-in-force is `day` or `gtc` only. `qty` must be a whole number, `notional` is not allowed, and `extended_hours` must be false. — [Alpaca Options Trading docs](https://docs.alpaca.markets/docs/options-trading)
- **Multi-leg orders:** POST `/v2/orders` with `"order_class": "mleg"` and a `legs` array. Each leg has `symbol`, `ratio_qty`, `side` and `position_intent`, for example `buy_to_open`.
  - Leg ratios must be in simplest form (GCD = 1).
  - Every leg must be covered within the same mleg order, so two short calls in one mleg order are rejected.
  - An equity leg cannot be combined with option legs.
  - Margin is computed as the worst-case payoff per expiration.
  - The examples include vertical spreads, an iron condor and rolls. The page states no maximum number of legs; the examples go up to 4.
  - Source: [Alpaca Options Level 3 docs, last updated 2025-09-24](https://docs.alpaca.markets/docs/options-level-3-trading)
- **Exercise, assignment and expiry in paper:** balances update instantly, but these events appear in the Activities endpoint only the next day. Assignment is not pushed over websocket and must be polled via REST.
  - Exercise endpoint: `POST /v2/positions/{symbol_or_contract_id}/exercise`. Requests sent between market close and midnight are rejected.
  - In-the-money contracts by $0.01 or more are auto-exercised. If buying power is insufficient, Alpaca sells the position within the hour before expiry.
  - Source: [Alpaca Options Trading docs](https://docs.alpaca.markets/docs/options-trading)
- **Contracts endpoint:** returns 100 results per page by default, and by default only contracts expiring by the next weekend. Pass expiry filters to see the full chain. — [Alpaca Options Trading docs](https://docs.alpaca.markets/docs/options-trading)
- **Market data plans:**
  - Free ($0/mo): options feed is "Indicative", 200 API calls/min, stocks from IEX only, 30 websocket symbols, real-time via websocket but 15-minute delay via the API.
  - Algo Trader Plus ($99/mo): real-time OPRA options, all US exchanges, unlimited calls and symbols.
  - Both plans include 7+ years of history. The page headline also says "up to 10,000 API calls/min", which conflicts with the per-plan table.
  - Source: [alpaca.markets/data, 2026-11-14](https://alpaca.markets/data)
- **Paper fill model:**
  - Fills happen at the NBBO, so buys fill at the ask and sells at the bid. Volatility and liquidity are ignored, and partial fills are decided by a random number. These points come from Alpaca staff forum replies, relayed by a third-party summary. — [TradersPost blog](https://blog.traderspost.io/article/alpaca-paper-trading); [Alpaca forum](https://forum.alpaca.markets/t/does-a-paid-account-give-more-accurate-paper-market-fills/14303)
  - Alpaca says paper trading does not model market impact, information leakage, latency slippage, queue position for non-marketable limit orders, or price improvement. Orders larger than the displayed NBBO size can still fill. Quoted via a secondary source. — [Alpaca Paper Trading docs](https://docs.alpaca.markets/docs/paper-trading); [TradersPost](https://blog.traderspost.io/article/alpaca-paper-trading)
  - Anecdotal user reports describe limit orders filling 50–260 seconds after the price crossed. Alpaca has not confirmed this. — [Alpaca forum thread](https://forum.alpaca.markets/t/paper-trading-fill-delays-of-50-260-seconds-limit-orders-filled-minutes-after-price-crossed/18223)
- **Official Alpaca MCP server (V2):**
  - It is a rewrite on FastMCP and OpenAPI. Tool names differ from V1.
  - Options tools: contract search, `get_option_chain`, snapshots with Greeks and IV, `place_option_order` for single-leg and multi-leg orders, and exercise/decline tools.
  - Paper is the default (`ALPACA_PAPER_TRADE=true`). Install with `uvx alpaca-mcp-server`. Requires Python 3.10+.
  - No release tag or version was published on the page.
  - Source: [github.com/alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server)
- **Alternatives (mostly secondary sources, low confidence):**
  - Tradier issues every user both live and sandbox API tokens. The sandbox uses 15-minute delayed data. — [Tradier docs](https://docs.tradier.com/docs/endpoints); [QuantConnect Tradier docs](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/tradier.md)
  - The tastytrade sandbox reportedly resets daily and uses 15-minute delayed quotes. — [third-party broker research doc](https://raxx-internal-docs.pages.dev/business-legal/byob-broker-research-2026-05-20)
  - IBKR has the broadest set of order types. Sources disagree on whether paper trading requires a funded live account. — [dev.to comparison](https://dev.to/pickuma/brokerage-apis-for-algorithmic-trading-alpaca-interactive-brokers-and-tradier-compared-11bi); [aifinhub](https://aifinhub.pages.dev/articles/broker-apis-compared-2026/)
  - Schwab's sandbox is described as incomplete, and its OAuth 2.0 setup as heavy. — [aifinhub](https://aifinhub-monorepo.pages.dev/articles/choosing-a-broker-api-2026/)

### Inferences
- Alpaca paper fills at the touch, so it is effectively optimistic on size and pessimistic on price (no price improvement). For multi-leg options, the bigger risk is unrealistic fills on illiquid strikes.
  - The MVP should add its own guards: reject orders whose size exceeds the displayed NBBO size, reject wide bid/ask spreads (for example spread / mid above X%), and use limit orders at mid or better.
  - Record "paper fill vs. mid" slippage in the ledger so paper P&L can be haircut later.
- Agents that want to hold naked short options or ratio spreads cannot do so on Alpaca Level 3. Strategy prompts should be restricted to defined-risk structures: verticals, iron condors, CSPs and covered calls.
- The $99/mo Algo Trader Plus plan is probably required once agents base decisions on option quotes and Greeks. Indicative quotes are not OPRA NBBO and can differ from real markets. It is fine to start on free indicative data for plumbing tests.
- Because assignment and expiry show up a day late, the reconciliation job must run each morning before agents wake. It should diff broker positions against the internal ledger.
- Tradier is the most credible backup broker for options. IBKR is the most capable but has the most integration friction.

### Gaps
- I did not read Alpaca's Trading API rate limit for order endpoints. Historically it was about 200 requests/min per account, but that is unverified here. Check the response headers.
- I did not check the current alpaca-py version or release date on PyPI or GitHub.
- I did not fetch Tradier, tastytrade, IBKR or Schwab pricing or primary API docs. The comparison above is mostly secondary.
- The docs do not state a maximum leg count for mleg orders (examples show 4).

## Q2. Options market data sources and costs (live + historical for backtesting)

### Takeaway
For live data, Alpaca Algo Trader Plus ($99/mo, real-time OPRA) is the simplest choice if Alpaca is the broker. For historical options backtesting, ThetaData is the clearest-priced option seen: $40–$160/mo, 6–14 years of history, full OPRA NBBO tick data from $80. Massive (formerly Polygon) options pricing could not be confirmed from the official page.

### Cited Findings
- **Alpaca:** Free plan = indicative options feed. $99/mo = real-time OPRA. 7+ years of history. — [alpaca.markets/data](https://alpaca.markets/data)
- **ThetaData options tiers (2026-11-14):**
  - Value: $40/mo, 6 years of history, 1-minute intervals, 2 concurrent requests.
  - Standard: $80/mo, 10 years, tick-level data, every OPRA NBBO quote, chain snapshots, 4 concurrent requests.
  - Pro: $160/mo, 14 years, streams every option trade, 8 concurrent requests.
  - All tiers are listed as real-time. Billed annually saves 20%. Greeks are not mentioned on the page.
  - Source: [thetadata.net/pricing](https://www.thetadata.net/pricing)
- **Massive (formerly Polygon):**
  - polygon.io/pricing now redirects to massive.com/pricing. Plans are billed per asset class. — [apicostcalc](https://apicostcalc.com/blog/polygon-massive-rebrand-api-pricing.html)
  - Stock tiers are widely reported as $0 / $29 / $79 / $199. — [qveris guide](https://qveris.ai/guides/polygon-pricing-optimized/)
  - Options tiers conflict across sources. One June 2026 comparison lists Starter $29 (15-minute delayed, 2 years), Developer $79 (4 years) and Advanced $199 (real-time, tick history, Greeks/IV). Another lists an older "Options Developer" plan at about $99. — [FlashAlpha comparison](https://flashalpha.com/articles/options-data-pricing-comparison-flashalpha-thetadata-polygon-spotgamma-squeezemetrics); [apis.io](https://apis.io/plans/polygon/polygon-plans-pricing/)
  - The official massive.com pricing page I fetched showed only Stocks Advanced at $199/mo and no options tiers. — [massive.com/pricing](https://massive.com/pricing?product=options)
- **Tradier sandbox:** 15-minute delayed data for free with the account. — [Tradier docs](https://docs.tradier.com/docs/endpoints)

### Inferences
- The cheapest credible stack is $99/mo (Alpaca real-time OPRA for live agents) plus $40–$80/mo (ThetaData for historical chains and backtests), about $140–$180/mo. The minimum for an MVP that only tests plumbing is $0, using Alpaca indicative data.
- If agents need Greeks and IV, the Alpaca snapshots expose them (per the MCP server tools), so a separate Greeks vendor is not needed for the MVP.

### Gaps
- I could not retrieve ORATS or CBOE DataShop pricing in this pass.
- Massive options tier prices are unconfirmed from the primary source.
- I did not confirm whether ThetaData includes Greeks or IV in each tier.

## Q3. LLM operating cost: current pricing and worked monthly estimate for 7 agents

### Takeaway
At current prices, 7 agents waking every 30 minutes through the trading day cost roughly $3/mo on Claude Haiku 5.5, $50–$130/mo on Claude Sonnet 5.5 and $100–$250/mo on Claude Opus 5.5, depending mostly on caching and tool-loop turns. Cheap tiers from Google and DeepSeek are in the same few-dollar range as Haiku. The biggest cost lever is a prompt-cache design matched to the wake interval.

### Cited Findings (all per million tokens, retrieved 2026-11-14)

**Anthropic** ([pricing page](https://platform.claude.com/docs/en/about-claude/pricing)):

| Model | Input | 5-min cache write | 1-h cache write | Cache hit | Output |
|---|---|---|---|---|---|
| Claude Opus 5.5 | $4 | $5 | $8 | $0.20 | $20 |
| Claude Sonnet 5.5 | $2 | $2.50 | $4 | $0.10 | $10 |
| Claude Haiku 5.5 (prompt ≤100K tokens) | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 |
| Claude Haiku 5.5 (prompt >100K tokens) | $0.50 | — | — | — | $2.50 |
| Claude Fable 5.2 | $8 | — | — | $0.20 | $40 |
| Claude Haiku 4.5 | $1 | — | — | — | $5 |
| Claude Sonnet 4.6 | $3 | — | — | — | $15 |

- The Batch API gives 50% off input and output, and it stacks with caching.
- 1M-token context is billed at standard pricing on Claude 4.6+ (except Haiku 5.5).
- US-only inference (`inference_geo`) costs 1.1x.

**Google Gemini** ([pricing page](https://aistudio.google.com/docs/pricing)):
- Gemini 3.1 Pro Preview: $2 input / $12 output (prompts ≤200K tokens).
- Gemini 3.8 Flash and 3.6 Flash: $0.75 / $3.75 through 2026-12-31, doubling to $1.50 / $7.50 on 2027-01-01.
- Gemini 3.5 Flash-Lite: $0.30 / $2.50. Gemini 3.1 Flash-Lite: $0.25 / $1.50.
- Batch is 50% off. The Flash and Flash-Lite free tiers may use your data to improve Google products.
- Gemini 2.5 Pro and Flash are rerouted from 2026-12-01.

**DeepSeek** ([pricing page](https://api-docs.deepseek.com/quick_start/pricing)):

| Model | Cache hit | Cache miss | Output |
|---|---|---|---|
| deepseek-flash (V4.1-Flash) | $0.006 | $0.30 | $1.20 |
| deepseek-v4-pro | $0.044 | $1.32 | $3.96 |

- These are peak prices. Off-peak is half price. Peak is 01:00–04:00 and 06:00–10:00 UTC on weekdays.

**OpenAI** (the official page returned 403, so these are third-party figures to verify):
- GPT-5 mini: about $0.25 / $2.00. GPT-5 nano: about $0.05 / $0.40.
- An October 2026 aggregator lists GPT-6 Astra $10/$50, GPT-6.1 Sol $2/$10 and GPT-6 Luna $0.10/$0.50.
- Sources: [benchlm.ai](https://benchlm.ai/openai/api-pricing); [anotherwrapper](https://anotherwrapper.com/llm-pricing/gpt-5-mini-2025-08-07)

### Worked estimate (my arithmetic on the Anthropic prices above)

**Assumptions:**
- 21 trading days per month.
- Each wake: 15K-token stable prefix (system prompt, tool schemas, strategy rules), 5K fresh market snapshot and state, 1.5K output.
- One model turn per wake. Tool-use loops re-send context each turn, so 3 turns per wake roughly triples input cost.

**Per-wake cost with a cache hit on the prefix:**
- Opus 5.5: about $0.053. Uncached: about $0.11.
- Sonnet 5.5: about $0.0265. Uncached: about $0.055.
- Haiku 5.5: about $0.0014.

**Monthly calls and cost (cached prefix):**

| Schedule | Calls/month (7 agents × 21 days) | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|---|
| 6 wakes/day | 882 | ~$1.2 | ~$23 | ~$47 |
| Every 30 min (13/day) | 1,911 | ~$2.7 | ~$51 | ~$101 |
| Every 5 min (78/day) | 11,466 | ~$16 | ~$304 | ~$608 |

**Caching pitfall:**
- The default cache TTL is 5 minutes. With 30-minute wakes, every call pays a cache write. On Sonnet that is 15K × $2.50/M = $0.0375, so the call costs about $0.0625, which is more than not caching.
- Use the 1-hour cache write ($4/M on Sonnet) for wakes 5–60 minutes apart. Also share one common prefix across the 7 agents, with agent-specific instructions after the cache breakpoint.

**Tiered mix (example):**
- 6 routine agents on Haiku 5.5 every 30 minutes, plus 1 decision/risk agent on Opus 5.5 every 30 minutes.
- Cost: about $2.3 + $14.5, roughly $17/mo.
- Escalate to Sonnet or Opus only when a routine agent flags something.

### Inferences
- LLM cost is not the binding constraint for an MVP. Data ($99/mo) and possibly the VPS will exceed it unless you run frontier models every few minutes.
- The Batch API (50% off, asynchronous) fits end-of-day review, post-mortems and journal summarization, not intraday decisions.
- Use structured outputs or a strict tool schema for the order intent (underlying, legs, limit, max loss, rationale). That lowers parse failures and keeps outputs short. Output tokens cost 5x input on every Claude model listed.

### Gaps
- OpenAI pricing is not verified from the primary page (HTTP 403).
- No measured token counts for this project's actual prompts. Measure with the token-counting endpoint before relying on the estimate.

## Q4. Minimal MVP architecture and open-source tooling

### Takeaway
Use one Python process (APScheduler or cron) on the existing VPS that runs this loop: snapshot, agents, deterministic risk gate, Alpaca mleg limit order, then a reconcile job writing to a Postgres/SQLite ledger. Use alpaca-py directly in the order path. The Alpaca MCP server is useful for exploration, but deterministic code should own order submission.

### Cited Findings
- The Alpaca MCP server V2 exposes chains, snapshots with Greeks and IV, and single- and multi-leg order placement. Paper is the default. — [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server)
- Assignment and expiry must be polled via REST and appear the next day. This drives the design of the reconciliation job. — [Alpaca docs](https://docs.alpaca.markets/docs/options-trading)
- Mleg constraints: covered legs only, simplest ratios, no equity legs. These belong in the pre-trade validator. — [Alpaca L3 docs](https://docs.alpaca.markets/docs/options-level-3-trading)

### Inferences (recommended design, not sourced as a standard)
1. **Scheduler:** APScheduler, run on the exchange calendar (Alpaca `/v2/calendar`). Example wakes: 09:45, then every 30 minutes, plus 15:30 and 16:15 ET.
2. **Snapshot service:** one call per wake that fetches account, positions, open orders, and chain snapshots with Greeks for a watchlist. Freeze it as an immutable JSON blob with an id, so every agent sees the same data and decisions can be replayed.
3. **Agent call:** the Anthropic SDK with a cached shared prefix and an agent-specific suffix. The final output is a tool call with a schema of type `OrderIntent | NoAction`.
4. **Risk gate (pure Python, no LLM):** check max loss per trade and per day, the allowed strategies list, bid/ask width, NBBO size, buying power, no expiry-day opens, and a kill-switch flag.
5. **Order submission:** alpaca-py, `order_class=mleg`, limit at mid with a timeout and cancel-replace. Set `client_order_id` from the decision id for idempotency.
6. **Reconciliation:** stream trade updates over websocket. Run a morning REST diff of positions and activities, covering next-day exercise, assignment and expiry.
7. **Ledger:** append-only tables for decisions (with snapshot id, prompt hash, model, tokens and cost), orders, fills and positions, plus LLM spend per agent.
- **Backtesting:** vectorbt, backtrader and Lean/QuantConnect are candidates. QuantConnect Lean has native options support and a Tradier/Alpaca brokerage integration (see the QuantConnect Tradier docs linked in Q1). For LLM agents, backtesting means replaying stored snapshots or ThetaData history through the same pipeline. That is expensive per step, so sample.

### Gaps
- I did not verify the current release status or options support of vectorbt, backtrader or Lean in this pass.

## Q5. Regulatory and practical: PDT, options approval, tax, investment adviser concerns

### Takeaway
The $25K pattern day trader rule is gone. The SEC approved FINRA's Rule 4210 amendments on 2026-04-14, effective 2026-06-04, and replaced it with intraday margin standards. Brokers have up to an 18-month phase-in, so Alpaca's current behavior must be checked. Selling a signals product or community could trigger investment adviser analysis: the publisher exclusion protects impersonal, regular-circulation publications, but auto-execution features weaken it.

### Cited Findings
- **PDT approval:** the SEC approved removing the PDT designation and the $25,000 minimum (FINRA Rule 4210, SR-FINRA-2025-017) on 2026-04-14 and approved new intraday margin standards at the same time. — [ThinkAdvisor, 2026-04-14](https://www.thinkadvisor.com/amp/2026/04/14/sec-approves-plan-removing-day-trading-limit-for-small-investors/); [Bloomberg Government](https://news.bgov.com/securities-law/sec-approves-plan-removing-day-trading-limit-for-investors-1)
- **PDT effective date:** 2026-06-04, with an 18-month phase-in for broker-dealers that need system changes. Restrictions are now triggered by repeated intraday margin deficits. — [Firstrade guide, 2026-06-03](https://blog.firstrade.com/blog/2026/6/3/the-complete-guide-to-the-pdt-rule-elimination-everything-investors-need-to-know-on-day-one); [E*TRADE](https://us.etrade.com/knowledge/library/margin/pattern-day-trading-rule-change)
  - These are secondary sources. I did not read the SEC release itself. One source gives it as Release No. 34-105226. — [NexusFi](https://nexusfi.com/a/concepts/pattern-day-trader-rule)
- **Options approval:** Alpaca paper is Level 3 by default. Live accounts go through a separate approval, and upgrades will use a separate API. — [Alpaca docs](https://docs.alpaca.markets/docs/options-trading)
- **Investment adviser rule:** *Lowe v. SEC* (1985) held that bona fide, impersonal publications of general and regular circulation fall within the Advisers Act publisher exclusion. — [472 U.S. 181](https://law.resource.org/pub/us/case/reporter/US/472/472.US.181.83-1911.html); [MTSU First Amendment Encyclopedia](https://firstamendment.mtsu.edu/article/lowe-v-securities-and-exchange-commission/)
  - Auto-trading links where the publisher sends trade instructions to brokers (the Weiss Research matter) are discussed as falling outside a plain newsletter analysis. — [IBKR publisher exclusion spotlight](https://brokerage.ibkr.com/webinars/spotlight-publisher-exclusion.pdf)

### Inferences
- **Paper only:** PDT is irrelevant to paper trading. For live trading, the intraday margin regime may still constrain frequent same-day round trips in small accounts during the phase-in, so check Alpaca's current implementation.
- **Product risk:** a personal tool is fine. Publishing timely, personalized or auto-executed signals to paying users looks like advice, not a bona fide publication, and may require SEC or state investment adviser registration, or broker-dealer issues if you route orders.
  - Lower-risk shapes are open-source software that users run on their own keys, or delayed, impersonal educational content.
  - Get securities counsel before charging money.
- **Tax (background knowledge, not verified in this pass):**
  - Equity and ETF options are usually short-term capital gains when held under a year.
  - Broad-based index options such as SPX are generally Section 1256 contracts (60/40 long/short-term, marked to market).
  - Wash-sale rules can apply across options and their underlyings.
  - Paper trading has no tax consequence.

### Gaps
- The SEC order and FINRA Regulatory Notice were not read directly.
- Alpaca's post-PDT intraday margin implementation is unknown.
- The tax points above are unsourced in this pass. Verify against IRS Publication 550 and IRC §1256.
- I found no current (post-2020) SEC guidance on algorithmic or LLM signal services.
