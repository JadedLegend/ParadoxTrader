# ParadoxTrader — Reading Companion v1

Prepared November 14, 2026. Twenty core readings and one additional macroeconomic counterpoint.

These are assistant-authored notes accompanying the original sources. Evidence summaries, interpretation, optional inquiry and limitations remain separate. This is a first-pass collection, with review depth recorded for every entry; it is not a claim that all twenty-one full papers have been critically reviewed. The collection supplies intellectual resources, not a new operating protocol.

# P01 — The Pricing of Options and Corporate Liabilities

**Fischer Black; Myron Scholes · 1973**  
**Area:** Options  
**Evidence:** Theoretical pricing model  
**Review depth:** selected original pages inspected  
**Horizon:** Contract valuation; application depends on expiry and holding period.

## Source and review basis

[The Pricing of Options and Corporate Liabilities](https://doi.org/10.1086/260062)

Original 1973 article hosted by Princeton. The scanned introduction, printed pp. 637–638, was inspected through OCR; the full derivation was not reviewed. Citation verified through Crossref.

## What the source contributes

The article derives option valuation from the restriction that appropriately constructed stock-and-option portfolios should not offer sure profits. Its opening discussion distinguishes European and American exercise and explains how the option value changes with the underlying price and remaining time.

## What it does not establish

A model price is conditional on a model and its assumptions. This first-pass note does not validate a pricing implementation, an American-option approximation, or a forecast of future returns. The OCR text is an aid to reading, not an authoritative transcription of equations.

## Connection to ParadoxTrader — interpretation

Provides a reference against which an apparent options paradox can be decomposed. A familiar pricing relationship may explain a surprising outcome before a new market mechanism is needed.

## An optional question to explore

Which part of a proposed discrepancy is ordinary payoff geometry, which part depends on a pricing assumption, and which part remains unexplained?

## Data that would be needed for a financial investigation

Exact contract terms, underlying price, strike, expiry, exercise/settlement convention, rates and dividends; practical valuation also needs a justified volatility input. Inputs are requirements, not verified provider capabilities.

**Read alongside:** P02 · P05.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P02 — Expected Option Returns

**Joshua D. Coval; Tyler Shumway · 2001**  
**Area:** Options  
**Evidence:** Asset-pricing theory with historical empirical tests  
**Review depth:** published abstract inspected  
**Horizon:** The paper considers option-return behavior; no intraday or current-market generalization is established here.

## Source and review basis

[Expected Option Returns](https://doi.org/10.1111/0022-1082.00352)

Published Journal of Finance abstract and bibliographic metadata supplied through Crossref. Full article not reviewed; an earlier working-paper abstract is separately present in the metadata cache.

## What the source contributes

The authors derive restrictions on expected option returns and report index-option evidence consistent with several of them. Their abstract also reports negative average returns for certain zero-beta straddles, suggesting that market beta alone does not explain those option returns.

## What it does not establish

Historical sample averages and model restrictions do not establish the return of a particular contract or a current strategy. Removing local directional exposure does not remove every economically relevant risk. This note does not reproduce numerical return claims from the abstract as current expectations.

## Connection to ParadoxTrader — interpretation

Directly develops the accuracy paradox: being right about the stock and choosing an attractive option exposure are different claims. It also complicates the idea that a directionally balanced position is neutral in every sense.

## An optional question to explore

After separating directional exposure from option P&L, what residual risks or priced services might explain the result?

## Data that would be needed for a financial investigation

Contract-level prices and terms, matched underlying returns, a consistent holding rule and hedge specification, and transaction-cost assumptions.

**Read alongside:** P03 · P04.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P03 — Delta-Hedged Gains and the Negative Market Volatility Risk Premium

**Gurdip Bakshi; Nikunj Kapadia · 2003**  
**Area:** Options  
**Evidence:** Stochastic-volatility theory with index-option evidence  
**Review depth:** earlier working-paper abstract inspected; published citation verified  
**Horizon:** Option holding and hedging windows; specify these before transferring the mechanism.

## Source and review basis

[Delta-Hedged Gains and the Negative Market Volatility Risk Premium](https://doi.org/10.1093/rfs/hhg002)

Crossref verifies the 2003 Review of Financial Studies article. The substantive abstract available in this search is the 2001 working-paper record, DOI 10.2139/ssrn.267106; the final full text was not reviewed.

## What the source contributes

The abstract describes a relationship, within a stochastic-volatility framework, between average delta-hedged gains and the volatility risk premium. It reports negative average gains in its S&P 500 option sample and patterns across moneyness and volatility conditions.

## What it does not establish

The inference is model- and sample-dependent. Discrete hedging, jumps, costs and implementation details affect a practical result. A negative historical premium for a buyer is not an instruction to sell options, and the premium sign convention must be stated.

## Connection to ParadoxTrader — interpretation

Gives the insurance and accuracy paradoxes a measurable bridge: an option can be attractive as insurance while having an unfavorable average hedged financial payoff in a historical sample.

## An optional question to explore

Does a proposed volatility discrepancy survive a stated hedge rule and cost model, or does it mostly express compensation for bearing an exposure?

## Data that would be needed for a financial investigation

Synchronized option and underlying quotes, hedge timestamps, rates, contract terms, volatility assumptions and all modeled trading costs.

**Read alongside:** P02 · P04.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P04 — Variance Risk Premiums

**Peter Carr; Liuren Wu · 2009**  
**Area:** Options  
**Evidence:** Variance measurement theory with historical empirical application  
**Review depth:** working-paper abstract inspected; published citation verified  
**Horizon:** Matched option-maturity and realized-variance windows.

## Source and review basis

[Variance Risk Premiums](https://doi.org/10.1093/rfs/hhn038)

Published print year is 2009; online publication began in 2008. Substantive coverage here uses the earlier abstract titled Variance Risk Premia, DOI 10.2139/ssrn.577222. Published full text was not reviewed.

## What the source contributes

The working-paper abstract develops an option-portfolio approximation to the variance swap rate and compares this implied quantity with subsequent realized variance. It describes an empirical application to stock indexes and individual stocks.

## What it does not establish

Variance and volatility are different quantities. The subsequent realized value is an outcome, not the physical expectation that was known in advance. Finite strikes, quote quality, discretization and maturity matching complicate replication. The abstract defines realized variance minus the synthetic swap rate; other writers reverse that sign.

## Connection to ParadoxTrader — interpretation

Turns a vague claim that implied volatility looks high into a question about a defined quantity, horizon and source of compensation. It also prevents a single IV number from standing in for an entire distribution.

## An optional question to explore

Is the claim about future realized variance, insurance compensation, or a particular part of the option surface—and what observable result could distinguish those?

## Data that would be needed for a financial investigation

A sufficiently broad matched-maturity option surface, underlying observations for a predefined realized-variance estimator, rates, contract specifications and quote filters.

**Read alongside:** P03 · P05.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P05 — Demand-Based Option Pricing

**Nicolae Gârleanu; Lasse Heje Pedersen; Allen M. Poteshman · 2009**  
**Area:** Options  
**Evidence:** Equilibrium theory with historical positioning evidence  
**Review depth:** selected working-paper sections inspected  
**Horizon:** Sample and analysis include daily positions and option maturities; direct short-dated application requires separate evidence.

## Source and review basis

[Demand-Based Option Pricing](https://doi.org/10.1093/rfs/hhp005)

NBER Working Paper 11843, December 2005, downloaded unchanged. Inspected introduction, descriptive-statistics/data sections, selected empirical discussion and conclusion. PDF pp. 17–18 describe data and participant classifications. The related final article appeared in 2009; final-version equivalence was not checked.

## What the source contributes

When options cannot be perfectly hedged, end-user demand can affect prices through risks dealers cannot hedge away. In the working paper’s 1996–2001 sample, index and individual-stock options show different end-user net-demand patterns. The empirical work uses participant-classified positions rather than treating raw total open interest as signed dealer exposure.

## What it does not establish

The participant data are much richer than a generic retail chain. The study’s market structure and sample are historical. Demand-related expensiveness is not automatically exploitable mispricing: bearing the other side can require capital and compensation for risk.

## Connection to ParadoxTrader — interpretation

A close financial counterpart to the insurance and observation paradoxes. A price is affected by what participants need, the risks intermediaries can absorb and the cost of absorbing them.

## An optional question to explore

What distinguishes an unusually expensive option from one whose price reflects an identifiable demand or intermediation constraint?

## Data that would be needed for a financial investigation

Comparable option surfaces, liquidity measures and ideally signed participant positions or flow. With only volume and open interest, the positioning mechanism remains partly unidentified.

**Read alongside:** P04 · P06 · P08.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P06 — Gamma Fragility

**Andrea Barbon; Andrea Buraschi · 2020**  
**Area:** Options  
**Evidence:** Empirical working paper with a hedging-feedback mechanism  
**Review depth:** working-paper abstract inspected  
**Horizon:** Intraday; extrapolation to multiweek returns is unsupported by this abstract.

## Source and review basis

[Gamma Fragility](https://doi.org/10.2139/ssrn.3725454)

Crossref/SSRN record dated 2020. Abstract inspected; full text, precise sample, revisions and publication status beyond this record were not established.

## What the source contributes

The abstract links a proxy for aggregate dealer gamma imbalance to intraday momentum or reversal, with the relationship depending on underlying-market liquidity. It reports stronger effects in less liquid underlyings and a relationship with flash-crash frequency and size.

## What it does not establish

The dealer exposure is proxied. Aggregate open interest alone does not reveal who is long or short, who hedges, or when they hedge. Observational evidence and a joint mechanism test are not universal causal identification. This note does not endorse a commercial gamma estimate or establish current-market effects.

## Connection to ParadoxTrader — interpretation

Makes the observation and insurance paradoxes concrete: hedging a derivative exposure may alter the underlying market. Liquidity and position sign are essential conditions, rather than decorative qualifiers.

## An optional question to explore

If a gamma-feedback explanation were correct, what would we expect to observe that a news shock or ordinary momentum would not explain as well?

## Data that would be needed for a financial investigation

Intraday underlying quotes/returns, option Greeks with timestamps and model basis, a defensible position-sign estimate, and liquidity measures. Label inferred inputs as estimates.

**Read alongside:** P05 · P07.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P07 — Market Liquidity and Funding Liquidity

**Markus K. Brunnermeier; Lasse Heje Pedersen · 2009**  
**Area:** Market structure  
**Evidence:** Theoretical model motivated by observed market phenomena  
**Review depth:** selected working-paper sections inspected  
**Horizon:** Stress episodes and changing financing conditions; no fixed trade horizon follows from the model.

## Source and review basis

[Market Liquidity and Funding Liquidity](https://doi.org/10.1093/rfs/hhn098)

NBER Working Paper 12939, February 2007. Downloaded unchanged; inspected introductory mechanism and qualifications, especially printed pp. 1–4 (PDF pp. 3–6). Final journal article published in 2009.

## What the source contributes

Liquidity provision requires capital. Losses and higher collateral requirements can reduce the capacity to supply liquidity, leading to further price pressure. The model separates loss spirals from margin spirals and explains how common financing constraints can connect markets.

## What it does not establish

This is a model of conditional mechanisms, not a timetable for crises. The paper explicitly allows circumstances in which margins are stabilizing. A wider bid–ask spread alone cannot identify a funding spiral.

## Connection to ParadoxTrader — interpretation

The clearest formal support for the liquidity paradox in the supplied notes. It also explains why apparently unrelated markets may react together without requiring a direct causal link between each pair.

## An optional question to explore

Is a deterioration in liquidity consistent with common funding pressure, instrument-specific information, or both—and what evidence separates them?

## Data that would be needed for a financial investigation

Quoted spreads/depth and execution records where available; margin, financing or collateral measures; positions and market returns. Funding conditions may remain unobserved.

**Read alongside:** P06 · P08 · P12.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P08 — The Limits of Arbitrage

**Andrei Shleifer; Robert W. Vishny · 1997**  
**Area:** Market structure  
**Evidence:** Theoretical model of delegated and capital-constrained arbitrage  
**Review depth:** published and working-paper abstracts inspected  
**Horizon:** Convergence horizon and financing survival; these can differ substantially.

## Source and review basis

[The Limits of Arbitrage](https://doi.org/10.1111/j.1540-6261.1997.tb03807.x)

Published Journal of Finance abstract verified through Crossref; NBER Working Paper 5167, July 1995, landing-page abstract also inspected. Full paper not reviewed.

## What the source contributes

The authors replace frictionless, costless arbitrage with specialized investors deploying other people’s capital. Their model permits arbitrage capacity to become ineffective when apparent deviations from fundamental values are especially large.

## What it does not establish

A deviation needs a defensible valuation benchmark. The model does not establish that a particular discrepancy must converge, or that an agent can remain solvent until it does. Capital constraints on institutional arbitrageurs are not automatically the same as an agent’s token budget.

## Connection to ParadoxTrader — interpretation

A useful challenge to asymmetry hunting: recognizing a discrepancy and being able to finance or execute its correction are separate problems.

## An optional question to explore

What could prevent the discrepancy from closing within the position’s lifetime, even if the interpretation is eventually correct?

## Data that would be needed for a financial investigation

A defined relative-value benchmark, timing/exit rules, financing and margin assumptions, borrow where relevant, liquidity and stress scenarios.

**Read alongside:** P05 · P07.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P09 — Carry

**Ralph S. J. Koijen; Tobias J. Moskowitz; Lasse Heje Pedersen; Evert B. Vrugt · 2018**  
**Area:** Cross-market  
**Evidence:** Cross-asset return decomposition and historical empirical study  
**Review depth:** working-paper abstract inspected; published citation verified  
**Horizon:** Cross-asset investment horizons; separate the calculation horizon from an intended trade holding period.

## Source and review basis

[Carry](https://doi.org/10.1016/j.jfineco.2017.11.002)

NBER Working Paper 19325, issued August 2013 and revised December 2013, landing-page abstract inspected. Final Journal of Financial Economics article is 2018; final full text not reviewed.

## What the source contributes

The study separates carry from expected price appreciation and studies carry across several asset classes, including equity-index options. Its abstract reports periods when carry strategies across otherwise weakly correlated asset classes do poorly together, coinciding with global recessions.

## What it does not establish

Different instruments require different carry definitions. A return characteristic is not a free income stream, and historical low correlation does not prove independent tail exposure. No individual strategy allocation follows from this abstract.

## Connection to ParadoxTrader — interpretation

Connects options with currencies, bonds, futures and commodities through common economic exposures rather than a list of arbitrary correlations.

## An optional question to explore

Could positions that look different by instrument be paid for bearing a similar stress exposure?

## Data that would be needed for a financial investigation

Forward/futures curves or other instrument-appropriate carry measures, comparable returns, financing terms and a common timestamp/calendar convention.

**Read alongside:** P07 · P10 · P12.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P10 — Time Series Momentum

**Tobias J. Moskowitz; Yao Hua Ooi; Lasse Heje Pedersen · 2012**  
**Area:** Cross-market  
**Evidence:** Historical multi-asset empirical study  
**Review depth:** author-affiliated research summary inspected  
**Horizon:** The summary emphasizes past 12-month returns and roughly year-scale persistence; intraday transfer is unproven.

## Source and review basis

[Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)

AQR research page dated May 1, 2012, with authors and an extended summary; Crossref verifies the journal citation. Full journal article not reviewed.

## What the source contributes

The summary reports predictability from an instrument’s own past returns across 58 futures and forward contracts spanning equity indexes, currencies, commodities and sovereign bonds. It distinguishes time-series momentum from ranking assets against one another and describes persistence followed by partial reversal at longer horizons.

## What it does not establish

The cited signal horizons are months, not seconds. The result does not establish that a purchased call or put is an efficient expression of the signal. AQR’s affiliation and product interests are disclosed context, not independent replication.

## Connection to ParadoxTrader — interpretation

Provides a concrete cross-market mechanism and an alternative to assuming every apparent contradiction should reverse. A sustained trend can coexist with a persuasive contrarian narrative.

## An optional question to explore

Is this an instrument’s own trend, relative performance against peers, or a short-lived reaction—and is the proposed option horizon aligned with that claim?

## Data that would be needed for a financial investigation

Consistent excess-return histories, futures/forward contract and roll conventions, volatility estimates, and practical costs. An options expression additionally needs contract and surface data.

**Read alongside:** P08 · P09.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P11 — Micro Effects of Macro Announcements: Real-Time Price Discovery in Foreign Exchange

**Torben G. Andersen; Tim Bollerslev; Francis X. Diebold; Clara Vega · 2003**  
**Area:** Cross-market  
**Evidence:** High-frequency historical event study  
**Review depth:** published abstract and working-paper abstract inspected  
**Horizon:** Announcement windows and high-frequency price discovery.

## Source and review basis

[Micro Effects of Macro Announcements: Real-Time Price Discovery in Foreign Exchange](https://doi.org/10.1257/000282803321455151)

American Economic Review abstract available through Crossref, plus NBER Working Paper 8959 landing page. Full article not reviewed.

## What the source contributes

Using exchange-rate quotes, macroeconomic expectations and released figures, the study links announcement surprises to conditional jumps in exchange rates. The abstract also describes effects that depend on announcement timing and sign.

## What it does not establish

The surprise is measured relative to expectations, not simply whether a released number appears strong or weak. Historical FX responses do not establish a stable mapping from a given release to a stock or an option today. Release vintages and time zones are essential to a reconstruction.

## Connection to ParadoxTrader — interpretation

A concrete reason to give an options-focused participant awareness of currencies and macro releases. It also separates external information shocks from purely endogenous market feedback.

## An optional question to explore

Was the information surprising at release time, or merely dramatic when described afterward?

## Data that would be needed for a financial investigation

Contemporaneous consensus forecasts, original release values and timestamps, synchronized market quotes and the actual decision time. Revised macro data alone are insufficient.

**Read alongside:** P12 · P07.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P12 — Dilemma not Trilemma: The Global Financial Cycle and Monetary Policy Independence

**Hélène Rey · 2015**  
**Area:** Cross-market  
**Evidence:** Macro-financial empirical analysis and policy argument  
**Review depth:** working-paper abstract inspected  
**Horizon:** Macro cycles and policy transmission; trading-horizon applicability is a separate question.

## Source and review basis

[Dilemma not Trilemma: The Global Financial Cycle and Monetary Policy Independence](https://doi.org/10.3386/w21162)

NBER Working Paper 21162, issued May 2015 and revised February 2018. Landing-page abstract inspected; full paper not reviewed.

## What the source contributes

The paper describes a global cycle in capital flows, asset prices and credit, and a possible role for monetary policy in the financial center through leverage and financing conditions. It argues that free capital mobility limits monetary-policy independence more broadly than a simple exchange-rate-regime account suggests.

## What it does not establish

The broad policy conclusion is a debated interpretation. Comovement with VIX is not proof that VIX causes every asset move. A macro relationship is not an intraday entry rule or a fixed stock/FX correlation.

## Connection to ParadoxTrader — interpretation

Supports looking beyond the traded instrument to the financing environment. It also illustrates why a research library should retain genuinely competing interpretations.

## An optional question to explore

Which transmission channel is plausible here—financing, foreign-currency balance sheets, cash flows or risk appetite—and what would distinguish it?

## Data that would be needed for a financial investigation

Policy events, capital-flow/credit measures, leverage or funding proxies, exchange rates, rates and asset prices, with attention to release timing.

**Read alongside:** P07 · P09 · P21.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P13 — On the Impossibility of Informationally Efficient Markets

**Sanford J. Grossman; Joseph E. Stiglitz · 1980**  
**Area:** Judgment and information  
**Evidence:** Noisy rational-expectations model  
**Review depth:** selected original pages inspected  
**Horizon:** Information acquisition and price formation; the model is not a holding-period recommendation.

## Source and review basis

[On the Impossibility of Informationally Efficient Markets](https://www.aeaweb.org/aer/top20/70.3.393-408.pdf)

Original American Economic Review article hosted by the American Economic Association. Inspected opening argument and model setup, printed p. 393 onward. EconPapers bibliographic record also retrieved. Mathematical derivations were not fully reviewed.

## What the source contributes

If obtaining information is costly, perfectly revealing prices can eliminate the incentive to acquire the information that would make prices revealing. The model allows prices to convey information imperfectly while informed participants receive compensation.

## What it does not establish

This is a theoretical equilibrium result. It does not prove that a visible anomaly is profitable, that every agent acquires independent information, or that shared conclusions are necessarily groupthink.

## Connection to ParadoxTrader — interpretation

A rigorous counterpart to the observation and consensus themes in Six Market Paradoxes. It separates incentives for information production from the social process of agreeing with another participant.

## An optional question to explore

What new information is actually being acquired, at what cost, and what part is already embedded in the price or shared source?

## Data that would be needed for a financial investigation

Source provenance and information timestamps; evaluating a trading application additionally requires prices, implementation costs and a defined forecast target.

**Read alongside:** P14 · P15.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P14 — How social influence can undermine the wisdom of crowd effect

**Jan Lorenz; Heiko Rauhut; Frank Schweitzer; Dirk Helbing · 2011**  
**Area:** Judgment and information  
**Evidence:** Controlled human estimation experiment  
**Review depth:** full-text sections inspected  
**Horizon:** Repeated judgments around a common question; transfer to trading requires an explicit target and resolution window.

## Source and review basis

[How social influence can undermine the wisdom of crowd effect](https://doi.org/10.1073/pnas.1008636108)

PNAS article available as PMC3107299. Inspected abstract, aggregation/results discussion and discussion of experimental conditions. Human sample N=144. Supplementary materials were not reviewed.

## What the source contributes

In repeated factual-estimation tasks, access to others’ estimates reduced response diversity without a corresponding improvement in collective accuracy and increased confidence. The paper also shows why the aggregation method matters for its skewed numerical estimates.

## What it does not establish

The participants are humans answering factual questions, not LLM traders forecasting a changing market. The study does not show that all collaboration is harmful. Its geometric-mean treatment of positive numerical estimates cannot be imported indiscriminately into probabilities or option positions.

## Connection to ParadoxTrader — interpretation

A close empirical companion to the consensus paradox, while preserving the boundary between a human experiment and the project’s synthetic participants.

## An optional question to explore

When conclusions converge, did new evidence improve accuracy, or did exposure to others mainly change confidence and dispersion?

## Data that would be needed for a financial investigation

Comparable forecast targets, initial and later judgments where voluntarily made, source exposure and resolved outcomes. Disagreement itself should not be rewarded.

**Read alongside:** P16 · P15.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P15 — A Theory of Fads, Fashion, Custom, and Cultural Change as Informational Cascades

**Sushil Bikhchandani; David Hirshleifer; Ivo Welch · 1992**  
**Area:** Judgment and information  
**Evidence:** Theoretical model of sequential social learning  
**Review depth:** bibliography and indexed abstract inspected  
**Horizon:** Sequential information arrival and action.

## Source and review basis

[A Theory of Fads, Fashion, Custom, and Cultural Change as Informational Cascades](https://doi.org/10.1086/261849)

Crossref confirms the Journal of Political Economy citation; EconPapers provides the indexed abstract. Full text was not obtained in this pass, so detailed model assumptions remain to be checked.

## What the source contributes

The indexed abstract describes informational cascades: an individual may rationally follow predecessors’ behavior rather than act on their own information. The proposed mechanism connects localized conformity with fragile aggregate behavior.

## What it does not establish

A model of sequential decisions is not an empirical demonstration of the project’s community dynamics. Rational imitation, shared evidence and coercive conformity are distinct explanations. More detailed claims should wait for full-text review.

## Connection to ParadoxTrader — interpretation

Explains how agreement can emerge without stupidity or deliberate suppression of dissent. It is especially useful when later participants infer information from earlier actions.

## An optional question to explore

Is a participant adopting another’s evidence, inferring information from their action, or simply seeing the same source independently?

## Data that would be needed for a financial investigation

Timing and provenance of observations and communications, initial interpretations where available, and later decisions. No personality label identifies a cascade.

**Read alongside:** P13 · P14 · P16.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P16 — Psychological Strategies for Winning a Geopolitical Forecasting Tournament

**Barbara Mellers and twelve coauthors · 2014**  
**Area:** Judgment and information  
**Evidence:** Human probabilistic-forecasting field study  
**Review depth:** published abstract inspected  
**Horizon:** Event-specific forecast horizons; no direct option holding-period result.

## Source and review basis

[Psychological Strategies for Winning a Geopolitical Forecasting Tournament](https://doi.org/10.1177/0956797614524255)

Psychological Science bibliographic record and abstract from Crossref. Full text and supplementary methods not reviewed. Complete author list is retained in the source metadata.

## What the source contributes

The abstract reports improved calibration and resolution associated with probability training, teaming and performance tracking in a two-year geopolitical forecasting tournament. Collaboration allowed participants to share information and reasoning.

## What it does not establish

The tasks, incentives and participants differ from autonomous options trading. The abstract alone does not isolate every component’s causal contribution or show that selecting an agent by past P&L improves a future trading group.

## Connection to ParadoxTrader — interpretation

A deliberate counterweight to P14. Social interaction can add information and useful reasoning; preserving disagreement is not a requirement to remain isolated or never change one’s mind.

## An optional question to explore

Under what conditions does discussion add relevant evidence and improve forecasts, rather than merely make them more alike?

## Data that would be needed for a financial investigation

Explicit probabilistic forecasts when offered, clear resolution criteria, timestamped evidence and subsequent outcomes. Calibration and discrimination should remain separate observations.

**Read alongside:** P14 · P15.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P17 — The Probability of Backtest Overfitting

**David H. Bailey; Jonathan M. Borwein; Marcos López de Prado; Qiji Jim Zhu · 2017**  
**Area:** Evaluation  
**Evidence:** Statistical framework with simulation illustrations  
**Review depth:** selected author-manuscript sections inspected  
**Horizon:** Research-selection horizon and out-of-sample evaluation, rather than a specific trade horizon.

## Source and review basis

[The Probability of Backtest Overfitting](https://doi.org/10.21314/JCF.2016.322)

WMU institutional record identifies the 2017 publication. Downloaded author PDF is explicitly revised February 2015; inspected abstract, introduction and framework discussion, PDF pp. 2–5. Final published version was not compared line by line.

## What the source contributes

Searching many strategy variants can select a configuration that fits historical noise. The authors define a probability-of-backtest-overfitting framework and propose combinatorially symmetric cross-validation to investigate the problem.

## What it does not establish

PBO requires a defined set of tested configurations and performance observations; it is not a magic confidence score for any agent. It does not by itself repair timestamp leakage, changed market structure, optimistic fills or hidden model training knowledge. Future untouched observations still answer a different question from repeatedly reused historical data.

## Connection to ParadoxTrader — interpretation

Prompt variants, memory settings, model choices and discretionary narrative selection all enlarge the research search space, even without optimizing a numerical strategy parameter.

## An optional question to explore

How many alternative explanations or configurations were considered before this result was presented as promising?

## Data that would be needed for a financial investigation

A record of evaluated configurations, comparable return series, selection rules and data partitions. Financial data dependence and overlapping horizons need explicit treatment.

**Read alongside:** P18 · P19 · P20.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P18 — … and the Cross-Section of Expected Returns

**Campbell R. Harvey; Yan Liu; Heqing Zhu · 2016**  
**Area:** Evaluation  
**Evidence:** Multiple-testing framework applied to financial research  
**Review depth:** working-paper abstract inspected; journal citation verified  
**Horizon:** Research accumulation and repeated hypothesis selection.

## Source and review basis

[… and the Cross-Section of Expected Returns](https://doi.org/10.1093/rfs/hhv059)

NBER Working Paper 20592, October 2014, abstract inspected. Journal article published online in 2015 and in print in 2016. Full article not reviewed.

## What the source contributes

The authors argue that the accumulation of many proposed return factors changes the appropriate evidence threshold for a newly reported factor. Their framework addresses multiple testing and dependence among candidate tests.

## What it does not establish

A threshold discussed for a historical factor-discovery setting is not a universal pass mark for an agent, a Sharpe ratio or an options strategy. A persuasive mechanism still requires empirical support, and a statistically selected association need not explain causality.

## Connection to ParadoxTrader — interpretation

An antidote to treating every newly named market contradiction as a discovery. Naming and interpreting a pattern are part of research, not evidence that its selection was independent of outcomes.

## An optional question to explore

Would the finding still appear unusual after accounting for the other patterns and hypotheses that were searched?

## Data that would be needed for a financial investigation

Candidate hypotheses, selection history, test dependence and the actual data used. Hidden failed variants limit what can be concluded.

**Read alongside:** P17 · P19.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P19 — FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design

**Yangyang Yu; Haohang Li; Zhi Chen; Yuechen Jiang; Yang Li; Denghui Zhang; Rong Liu; Jordan W. Suchow; Khaldoun Khashanah · 2023**  
**Area:** Autonomous financial agents  
**Evidence:** LLM-agent architecture and historical stock-trading experiments; preprint  
**Review depth:** selected full-text sections inspected  
**Horizon:** Daily stock decisions in the reported experiments; options generalization is unproven.

## Source and review basis

[FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design](https://arxiv.org/abs/2311.13743v2)

arXiv v2, December 3, 2023. Inspected architecture, experiment/data setup and evaluation discussion, especially PDF pp. 10–15 and conclusion. Five named stocks appear in the comparison; the main testing window is October 2022–April 2023. No independent replication performed.

## What the source contributes

The framework separates profiling, layered memory and decisions. It processes news, filings and prices at different memory horizons and reports historical stock-trading comparisons and ablations.

## What it does not establish

On PDF p. 15 the authors state that the reported risk-inclination setting is selected by highest cumulative return during the testing phase. That makes those selected results unsuitable as an untouched comparison of the settings. It does not invalidate every architectural idea. The reviewed evaluation does not establish executable options returns, comprehensive trading costs or freedom from pretrained-model temporal contamination.

## Connection to ParadoxTrader — interpretation

Directly relevant to the interest in distinct participants, memory and changing perspectives. Layered retention is a design hypothesis; a fluent self-explanation is not proof of human-like cognition or a faithful causal account of a model’s decision.

## An optional question to explore

Which benefit comes from retained information, which from retrieval rules, and which from choosing a favorable configuration after seeing outcomes?

## Data that would be needed for a financial investigation

Archived observations, prompt/model and retrieval versions, decisions, source timestamps, costs and selection history. A model’s pretrained knowledge is a separate information channel to consider.

**Read alongside:** P17 · P18 · P20.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P20 — TradingAgents: Multi-Agents LLM Financial Trading Framework

**Yijia Xiao; Edward Sun; Di Luo; Wei Wang · 2025**  
**Area:** Autonomous financial agents  
**Evidence:** Multi-agent architecture and historical stock backtest; preprint  
**Review depth:** selected full-text sections inspected  
**Horizon:** Daily stock backtest in the described period; no demonstrated option-expiry, assignment or spread-execution coverage.

## Source and review basis

[TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138v7)

arXiv v7, June 3, 2025; initial submission December 2024. Inspected architecture, sections 5–7 and supplementary metric definitions. Section 5.1 states a January–March 2024 simulation; Table 1 reports AAPL, GOOGL and AMZN. No replication performed.

## What the source contributes

The framework assigns research, analysis, trading and risk roles and uses structured debate to combine their outputs. It reports favorable stock-backtest comparisons with rule-based baselines.

## What it does not establish

Historical stock backtests are not a demonstration of autonomous options execution. In the inspected setup, costs, fill assumptions and model-weight contamination are not established sufficiently to conclude net executable performance. Restricting supplied documents by date does not, by itself, constrain knowledge embedded in model weights. The relationship between the setup’s listed stock universe and the Table 1 subset also deserves clarification before replication.

## Connection to ParadoxTrader — interpretation

A close architecture comparison for eventual group trading. It should be read as one organization of an agent ensemble, not proof that agreement, debate or a hierarchy must improve this particular community.

## An optional question to explore

What information does group discussion add beyond the same participants’ initial evidence, and which results depend on role design or retrospective assumptions?

## Data that would be needed for a financial investigation

Versioned prompts, source access, model dates, decision records, execution/cost assumptions and equivalent baselines. A faithful reconstruction needs the exact paper version and configuration.

**Read alongside:** P14 · P16 · P17 · P19.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

# P21 — Trilemma, Not Dilemma: Financial Globalisation and Monetary Policy Effectiveness

**Georgios Georgiadis; Arnaud Mehl · 2015**  
**Area:** Cross-market counterpoint  
**Evidence:** Empirical macro-financial working paper  
**Review depth:** working-paper abstract inspected  
**Horizon:** Macro-policy transmission.

## Source and review basis

[Trilemma, Not Dilemma: Financial Globalisation and Monetary Policy Effectiveness](https://doi.org/10.2139/ssrn.2643948)

Crossref/SSRN 2015 abstract and metadata inspected. Full paper and any later published revision were not reviewed. This is an additional counterpoint beyond the twenty core readings.

## What the source contributes

The abstract argues that financial integration can transmit global financial shocks while foreign-currency balance-sheet valuation effects can strengthen domestic monetary-policy effectiveness. It disputes a simple replacement of the trilemma by a dilemma.

## What it does not establish

This note does not resolve the debate or establish comparable identification across P12 and P21. Policy conclusions and country exposures need full-text study; neither abstract alone specifies an options trade.

## Connection to ParadoxTrader — interpretation

Preserves a substantive disagreement about the same broad cross-market phenomenon. The disagreement is useful because the proposed channels and institutional conditions differ.

## An optional question to explore

Which balance-sheet and exchange-rate conditions would make the two accounts predict different outcomes?

## Data that would be needed for a financial investigation

Country-specific external balance sheets, currency exposures, exchange-rate regimes, policy shocks and outcome definitions.

**Read alongside:** P12.

This is an assistant-authored reading companion, not text from the paper or an instruction to an agent. Questions and proposed applications are interpretations. Source checked 2026-11-14; current provider entitlements and practical data availability are unverified.


---

## Sources

- **[P01]** Fischer Black; Myron Scholes (1973). [The Pricing of Options and Corporate Liabilities](https://doi.org/10.1086/260062). selected original pages inspected.
- **[P02]** Joshua D. Coval; Tyler Shumway (2001). [Expected Option Returns](https://doi.org/10.1111/0022-1082.00352). published abstract inspected.
- **[P03]** Gurdip Bakshi; Nikunj Kapadia (2003). [Delta-Hedged Gains and the Negative Market Volatility Risk Premium](https://doi.org/10.1093/rfs/hhg002). earlier working-paper abstract inspected; published citation verified.
- **[P04]** Peter Carr; Liuren Wu (2009). [Variance Risk Premiums](https://doi.org/10.1093/rfs/hhn038). working-paper abstract inspected; published citation verified.
- **[P05]** Nicolae Gârleanu; Lasse Heje Pedersen; Allen M. Poteshman (2009). [Demand-Based Option Pricing](https://doi.org/10.1093/rfs/hhp005). selected working-paper sections inspected.
- **[P06]** Andrea Barbon; Andrea Buraschi (2020). [Gamma Fragility](https://doi.org/10.2139/ssrn.3725454). working-paper abstract inspected.
- **[P07]** Markus K. Brunnermeier; Lasse Heje Pedersen (2009). [Market Liquidity and Funding Liquidity](https://doi.org/10.1093/rfs/hhn098). selected working-paper sections inspected.
- **[P08]** Andrei Shleifer; Robert W. Vishny (1997). [The Limits of Arbitrage](https://doi.org/10.1111/j.1540-6261.1997.tb03807.x). published and working-paper abstracts inspected.
- **[P09]** Ralph S. J. Koijen; Tobias J. Moskowitz; Lasse Heje Pedersen; Evert B. Vrugt (2018). [Carry](https://doi.org/10.1016/j.jfineco.2017.11.002). working-paper abstract inspected; published citation verified.
- **[P10]** Tobias J. Moskowitz; Yao Hua Ooi; Lasse Heje Pedersen (2012). [Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003). author-affiliated research summary inspected.
- **[P11]** Torben G. Andersen; Tim Bollerslev; Francis X. Diebold; Clara Vega (2003). [Micro Effects of Macro Announcements: Real-Time Price Discovery in Foreign Exchange](https://doi.org/10.1257/000282803321455151). published abstract and working-paper abstract inspected.
- **[P12]** Hélène Rey (2015). [Dilemma not Trilemma: The Global Financial Cycle and Monetary Policy Independence](https://doi.org/10.3386/w21162). working-paper abstract inspected.
- **[P13]** Sanford J. Grossman; Joseph E. Stiglitz (1980). [On the Impossibility of Informationally Efficient Markets](https://www.aeaweb.org/aer/top20/70.3.393-408.pdf). selected original pages inspected.
- **[P14]** Jan Lorenz; Heiko Rauhut; Frank Schweitzer; Dirk Helbing (2011). [How social influence can undermine the wisdom of crowd effect](https://doi.org/10.1073/pnas.1008636108). full-text sections inspected.
- **[P15]** Sushil Bikhchandani; David Hirshleifer; Ivo Welch (1992). [A Theory of Fads, Fashion, Custom, and Cultural Change as Informational Cascades](https://doi.org/10.1086/261849). bibliography and indexed abstract inspected.
- **[P16]** Barbara Mellers and twelve coauthors (2014). [Psychological Strategies for Winning a Geopolitical Forecasting Tournament](https://doi.org/10.1177/0956797614524255). published abstract inspected.
- **[P17]** David H. Bailey; Jonathan M. Borwein; Marcos López de Prado; Qiji Jim Zhu (2017). [The Probability of Backtest Overfitting](https://doi.org/10.21314/JCF.2016.322). selected author-manuscript sections inspected.
- **[P18]** Campbell R. Harvey; Yan Liu; Heqing Zhu (2016). [… and the Cross-Section of Expected Returns](https://doi.org/10.1093/rfs/hhv059). working-paper abstract inspected; journal citation verified.
- **[P19]** Yangyang Yu; Haohang Li; Zhi Chen; Yuechen Jiang; Yang Li; Denghui Zhang; Rong Liu; Jordan W. Suchow; Khaldoun Khashanah (2023). [FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design](https://arxiv.org/abs/2311.13743v2). selected full-text sections inspected.
- **[P20]** Yijia Xiao; Edward Sun; Di Luo; Wei Wang (2025). [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138v7). selected full-text sections inspected.
- **[P21]** Georgios Georgiadis; Arnaud Mehl (2015). [Trilemma, Not Dilemma: Financial Globalisation and Monetary Policy Effectiveness](https://doi.org/10.2139/ssrn.2643948). working-paper abstract inspected.

Bigdata.com was consulted for discovery; those searches did not supply the primary academic evidence used in these notes. Citations above lead to the original papers or their identified records. Bibliographic verification also used Crossref, NBER, AEA, arXiv, PMC and institutional/author records. No investment data were computed.

**Powered by Bigdata.com** - https://bigdata.com

## Disclaimer

This output is for informational and research-assistance purposes only. It does **not** constitute investment, legal, tax, accounting, or other professional advice, and it is **not** a recommendation to buy, sell, or hold any security or instrument or to pursue any strategy. Information may be incomplete, estimated, delayed, or inaccurate. Past performance does not guarantee future results. Verify material facts independently and consult qualified advisors before making decisions.
