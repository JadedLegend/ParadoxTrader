# From Paradox to Evidence

## A research and evaluation protocol for the Paradox Edge Trader

**Working paper · 12 November 2026**

## Abstract

Paradox Edge Trader is being built around a particular kind of market inquiry: noticing when price, narrative, positioning, volatility, timing, and payoff appear to describe the same situation differently. The project should preserve that humanly meaningful starting point without allowing an attractive explanation to become a trade, a trade to become evidence of insight, or a profitable outcome to become proof of a correct forecast.

This paper proposes a practical evaluation protocol for the engine's first paper-trading period. It treats an agent's observation as an inquiry with traceable lineage. An inquiry may remain open, be revisited, or stop without producing an order. If an optional paper proposal is made, the protocol keeps forecast, position construction, simulated execution, costs, and realized outcome separate. It evaluates both decision quality and operating quality while recording uncertainty and unavailable data explicitly.

The protocol has five commitments. It uses point-in-time evidence; separates directional, volatility, timing, and payoff claims; evaluates outcomes net of realistic costs where the data permit; protects an untouched evaluation period from repeated tuning; and treats the seven-agent environment as a source of varied hypotheses rather than seven independent confirmations. It is deliberately modest. It does not claim that the current system has demonstrated alpha, and it does not prescribe a strategy or require agents to trade.

## 1. The question the project should answer

The useful first question is not “Can the agents find paradoxes?” They almost certainly can produce descriptions that sound paradoxical. The useful question is narrower:

> When an agent identifies a market tension and chooses to investigate it, does the resulting record contain information that improves a bounded paper decision after costs, uncertainty, and execution constraints are considered?

That question contains several different tests. A forecast can be directionally correct while the selected option loses money because of timing, volatility repricing, spread, decay, or an unfavorable payoff shape. An option can make money while the underlying forecast was poorly supported. A paper order can appear successful because the fill assumption was generous. A group can agree because all members saw the same source rather than because several independent observations converged.

The engine therefore needs more than a return number. It needs a record of what was known at the time, what was inferred, what was chosen, what the simulated venue confirmed, and what later happened. The existing [traceable idea lineage](../IDEA_LINEAGE.md) already provides the appropriate separation between inquiries, optional proposals, orders, fills, positions, and reviews. This paper defines how to use that separation for evaluation.

## 2. What counts as an evaluated inquiry

An evaluated inquiry begins with an observation anchored to an instrument, source, observation time, horizon, and uncertainty. The observation may concern an unusual price move, a disagreement between price and narrative, a change in implied volatility, a suspected liquidity constraint, or a conflict between horizons. It does not need to contain the word “paradox.” The protocol cares about the mechanism being examined, not the label.

The agent then records an interpretation and, when useful, one or more alternatives. Each alternative should say what evidence would strengthen or weaken it. The agent chooses whether to investigate, ask, read, test a bounded paper scenario, wait, abstain, or leave the question open. The offered menu and the environmental constraints are retained beside the selected action. This matters because choosing rest when investigation was unavailable is not the same observation as choosing rest when several relevant investigations were available.

Only an explicit proposal creates a candidate paper decision. A proposal should identify the expected direction or volatility condition, the intended horizon, the proposed structure, the main exposures, the invalidating conditions, and the costs or liquidity assumptions that matter. It should also state what remains unknown. A missing input is not a zero and should not be silently replaced by a remembered value.

A proposal may be rejected, cancelled, or never submitted. Those outcomes remain useful records. The protocol does not count an absence of an order as a failed prediction, and it does not reward an order merely for existing.

## 3. Four claims that must not be collapsed

### 3.1 Direction

A directional claim concerns the underlying instrument's movement over a stated horizon. “The underlying will rise” is different from “the call will profit.” The evaluation record should retain the reference price, observation time, forecast horizon, and the later reference price used for evaluation.

### 3.2 Volatility or distribution

Implied volatility is derived from option prices and represents the movement the market price implies; historical or statistical volatility measures past price variation. The two are not interchangeable. The Options Industry Council describes implied volatility as the amount of movement the marketplace expects based on the option price, while also warning that model statistics do not guarantee future behavior. [1]

The protocol should therefore ask what the agent actually claimed. A view that implied volatility is too high is not the same as a directional bearish view. A view about the probability of a large move is not the same as a view about the sign of the move. When a proposal depends on implied-versus-realized volatility, the record should preserve the exact volatility measure, window, and source rather than summarize it as “volatility was mispriced.”

### 3.3 Timing

A thesis can be right at the wrong time. Every proposal needs an intended decision horizon and, where relevant, a planned holding or review window. Later evaluation should distinguish the result at the planned horizon from what happened after the agent would reasonably have closed or abandoned the position. Otherwise, a position can be judged against a future event the agent never had access to or never intended to hold through.

### 3.4 Payoff and construction

An option's result depends on strike, expiry, premium, contract multiplier, volatility, time decay, the underlying move, and execution. Greeks can describe sensitivities to selected inputs, but they are not guarantees. The practical implication is simple: retain the proposed structure and its exposures as first-class records. Do not use a correct underlying direction to retroactively label every option structure as correct.

## 4. The minimum record for a paper decision

The following information is sufficient for a first useful evaluation and can be gathered without turning every wake into a form:

- the original observation, source, instrument, timestamp, horizon, and known data gaps;
- the primary interpretation and any meaningful alternatives;
- the chosen action and the action menu and constraints that were actually available;
- the proposed structure, if any, with entry assumptions, exposure, intended holding window, and invalidation conditions;
- the information snapshot available before submission, distinguished from later information;
- the broker or mock-venue submission ID, acceptance/rejection state, fill assumptions, partial fills, cancellations, and reconciliation events;
- the realized or simulated outcome, including gross result, fees, spread or slippage assumptions, and the source of each mark;
- a later review that may revise the interpretation without rewriting the original record.

This is not a request for a long journal entry. The engine can capture much of the record mechanically. The agent's contribution can remain short. A one-sentence observation and a clear return cue are more useful than compulsory eloquence.

## 5. What to measure

The first paper period should produce a dashboard of evidence rather than one composite score. At minimum, report the following in separate sections.

**Inquiry behavior.** Count inquiries opened, revisited, paused, abandoned, and left open. Report how often an inquiry became a proposal and how often a proposal became a submitted paper order. These are descriptions of the environment, not quality grades. A low conversion rate may mean the agents are appropriately selective, or it may mean the tools are inadequate.

**Forecast quality.** For directional forecasts, measure the forecast against the stated horizon using a predeclared reference. For volatility forecasts, compare the chosen implied or statistical measure with the later realized measure using the same window definition. Preserve calibration information when the forecast is probabilistic. Do not convert a qualitative statement into a numerical probability after the outcome is known.

**Position quality.** Evaluate the structure against its intended purpose. Record payoff, maximum or scenario loss where determinable, exposure to the relevant Greeks, time to expiry, spread assumptions, and whether the structure expressed the stated thesis. A profitable position can still reveal that the original mechanism was wrong; a losing position can still have been a well-specified test under adverse but anticipated conditions.

**Execution quality.** Separate proposed price from broker-confirmed price, and broker-confirmed price from later mark. Track acknowledgement uncertainty, partial fills, cancellations, stale quotes, and unavailable marks. A paper fill should not be treated as an observation of live liquidity. If the venue model is optimistic or incomplete, label the result accordingly.

**Economic result.** Report gross and net simulated result separately. Net result should include the costs actually modeled and identify costs that remain unavailable. The project's operating-cost ledger should also report model and research-provider spend separately from trading results. Provider-reported cost, explicitly estimated token cost, and unknown cost must remain different categories, as specified in [Operating-cost visibility](../OPERATING_COSTS.md).

**Risk and restraint.** Report drawdown, concentration, open exposure, loss tails, and the number of decisions that were intentionally not made. Do not treat more activity as better. A strategy that earns a return only by increasing order count or accepting unmodeled execution risk has not demonstrated a durable advantage.

## 6. How to avoid learning the wrong lesson

The project's unusual richness creates a specific evaluation risk: after seeing results, a builder can change the prompt, persona, source selection, wake rhythm, structure rules, or review window until the past looks coherent. This is a form of research flexibility, even if no single person intends to overfit.

The protocol should therefore divide the paper period into a development segment and an untouched evaluation segment before results are examined in detail. Changes to prompts, data sources, action menus, or execution assumptions should receive a version identifier. A later version may be better, but its results should not be pooled with the earlier version as if the environment had always been stable.

A single holdout period is not a magic shield. Bailey, Borwein, López de Prado, and Zhu argue that ordinary holdout techniques can be unreliable for investment backtests and propose combinatorially symmetric cross-validation to estimate the probability of backtest overfitting. [2] The project does not need to implement their full method in its first paper-trading phase. It should adopt the underlying discipline: record the number of variants examined, preserve the selection process, avoid tuning on the final period, and treat a striking result found after many choices as weaker evidence than a preregistered result.

The seven agents also should not be counted as seven independent trials. They may share data, prompts, tools, market conditions, or a common creator. Agreement after common exposure is evidence of a shared response, not seven independent confirmations. Preserve each initial view before peer discussion where comparison matters, and record the common sources that could explain convergence.

## 7. Options-specific paradox tests

The engine can turn its central interest into a small set of repeatable questions without forcing every agent through the same checklist.

One test examines **implied versus realized movement**. The inquiry states the option-implied measure, the later realized measure, the horizon, and the costs of expressing the view. Cboe describes VIX as a measure of near-term volatility expectations conveyed by SPX option prices and notes that index options have, over long periods, tended to price slightly more uncertainty than subsequent realized S&P 500 volatility. [3] That observation is a useful hypothesis source, not a promise that every underlying, expiry, or regime will show the same spread. Robert J. Engle's volatility-forecasting discussion likewise emphasizes that implied volatility need not be a good proxy for the market's best forecast of future volatility. [4]

Another test examines **direction versus payoff**. The record asks whether the thesis concerned direction, magnitude, timing, or volatility, then evaluates the structure against those separate claims. It should be possible to conclude: “the direction forecast was correct, but the selected structure lost because the move was too small and time decay dominated.” That is more useful than marking the whole inquiry simply right or wrong.

A third test examines **liquidity under stress**. A displayed option price is not automatically an achievable fill, especially when the inquiry itself expects a sharp move. The paper environment should vary spread and fill assumptions in clearly labeled scenarios instead of presenting one frictionless result as fact. Any scenario result remains a simulation until supported by a venue-confirmed paper record.

The first protocol should exclude margin and short-option authority rather than treating them as small extensions. The SEC warns that margin can magnify losses and that option-writing strategies may expose an investor to losses exceeding the initial investment. [5] Keeping those permissions closed makes the first results easier to interpret and prevents a simulated edge from depending on an unexamined financing or assignment risk.

A fourth test examines **consensus and source dependence**. The engine records whether several agents independently observed the same tension before discussion, whether they relied on the same news item or market field, and whether later agreement came from new evidence or social exchange. The result is not a score for agreement. It is a way to learn whether the community is finding independent information or amplifying one frame.

## 8. A modest first experiment

The first real study should be deliberately small. Use the existing seven-agent environment in paper mode, but begin evaluation with one instrument family and a limited set of liquid options whose contract specifications and historical data can be reconstructed. Keep inquiry creation available to all seven, while restricting order execution to the reviewed paper pathway until the adapter and risk controls are proven.

Before the study begins, freeze the model map, prompt version, library snapshot, data-source list, cost-rate snapshot, execution assumptions, and evaluation windows. Define the minimum required fields for a proposal and the rules for missing data. State which results will be considered gross, net-modeled, or unavailable. Decide in advance how a stale quote, uncertain acknowledgement, partial fill, or missing mark is represented.

During the study, do not require a trade from every agent or a fixed number of proposals. Record the menu they received and the actions they selected. Maintain an append-only event trail. If a model, data source, or service fails, record the environmental failure instead of interpreting it as a personality choice.

At the end of the development segment, review the records for completeness and operational failures before inspecting apparent profitability. Then lock the evaluation segment. The final report should include a small set of representative lineages: an inquiry that stayed open, one that was abandoned, one that produced a rejected or uncertain order, one with partial fills, one profitable structure, and one losing structure. Examples make the protocol inspectable without replacing aggregate statistics.

## 9. What would count as encouraging evidence

Encouraging evidence would not be a single large simulated win. It would be a repeated pattern in which the engine's inquiries remain traceable, forecasts are evaluated against their stated horizons, proposals respect their own invalidation conditions, execution records are recoverable, and results remain favorable after the costs that are actually modeled. The pattern should persist in an untouched segment and should not disappear when reasonable spread or fill assumptions are applied.

It would also be encouraging if the agents became more calibrated or more selective without being instructed to produce more prose or more trades. Better uncertainty labels, clearer separation between observation and interpretation, appropriate abstention, and useful return cues are operational improvements. They become financially relevant only when connected to later decision and outcome records.

The project should be equally willing to find no advantage. A null result can reveal that a paradox is interesting but not tradable, that the available data cannot identify the mechanism, that the costs consume the edge, or that the environment needs better tooling. Those conclusions protect the project from turning a compelling mythology into an expensive confirmation exercise.

## Conclusion

Paradox Edge Trader does not need to choose between a rich interior environment and disciplined financial evaluation. It needs a clear boundary between them. The agents may explore, develop interests, disagree, wait, and form relationships. When one of their inquiries becomes a paper decision, the system should preserve what was known, what was proposed, what the venue confirmed, what it cost, and what later evidence changed.

That boundary gives the project a fair test. It allows a paradox to remain an inquiry when no action is warranted. It allows a trade to be judged by construction and execution rather than by story. It allows a profitable outcome to be useful without becoming proof. Most importantly, it gives future builders a way to improve the environment while leaving earlier evidence intact.

## Current implementation limits

This is a proposed research protocol, not an empirical result. The repository currently has a tested one-agent, one-fictional-contract mock lifecycle and read-only lineage view. It does not yet demonstrate live model performance, real options-paper performance, Alpaca lifecycle recovery, expiry or assignment, commissions, complete market marks, or a production evaluation period. The first study should not claim those capabilities until they are implemented and verified.

The protocol also does not recommend a particular option, ticker, direction, or trade. It defines what the project should record and compare before making such claims.

## References

[1]: https://www.optionseducation.org/advancedconcepts/volatility-the-greeks "Volatility & the Greeks — Options Industry Council"

[2]: https://scholarworks.wmich.edu/math_pubs/42/ "The Probability of Backtest Overfitting — Bailey, Borwein, López de Prado, and Zhu"

[3]: https://www.cboe.com/en/tradable-products/vix/ "Cboe Volatility Index — Cboe"

[4]: https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0416.00009 "Forecasting Volatility — Robert F. Engle"

[5]: https://www.sec.gov/oiea/investor-alerts-and-bulletins/ib_marginaccount "Investor Bulletin: Understanding Margin Accounts — U.S. Securities and Exchange Commission"
