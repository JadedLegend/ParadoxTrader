# Empirical Evidence Behind the "Contradiction" Options Thesis (US equity/index options)

Scope note: The owner's framing (library/originals/TheOptionsParadox.docx, SixMarketParadoxes.docx, README.md) treats contradictions such as "being right on direction and still losing", "expected vs. priced volatility", "perceived stability vs. structural resilience", and liquidity that disappears when needed as hypotheses to test, explicitly "without assuming that every contradiction represents mispricing" (TheOptionsParadox.docx, abstract). Its proposed "Dissonance Ledger" (record discrepancies, exposures and later outcomes) fits the testing approach below. Each contradiction is mapped to a known quantitative strategy.

Mapping used:
| Owner's contradiction | Known quantitative strategy / signal |
|---|---|
| Implied vs. realized volatility | Volatility (variance) risk premium harvesting: index put-writing, covered calls, short strangles/condors, delta-hedged short options; cross-sectional IV-RV gap (Goyal-Saretto) |
| Time horizons | IV term-structure slope; event (earnings) volatility vs. normal-day volatility |
| Payoff structure / participants' assumptions | Skew/smirk signals; put-call parity deviations (IV spread); retail "lottery" demand for OTM / 0DTE options |
| Price vs. narrative | News/social/LLM sentiment signals vs. price drift |
| Incentives / informed vs. uninformed participants | Options-flow signals: put-call ratios, O/S volume ratio, unusual activity |

Source quality: most of the figures below were confirmed this session from abstracts, journal listings, or reputable secondary summaries (CXO Advisory, Quantpedia, CFA Institute, BIS). The full texts were usually not read, so the exact numbers should be checked against the original papers before anyone relies on them.

---

## 1. Volatility risk premium (implied > realized): evidence, magnitude, tail risk, retail implementation, crash performance

### Takeaway
The index volatility/variance risk premium is one of the best-documented, persistent premia in options. Index options, especially puts, are on average priced above what later realizes, and this holds after bid-ask spreads in the academic tests. But it is a risk premium, not an arbitrage. Returns come as frequent small gains with rare, very large losses (2008, Feb 2018, March 2020, and short-dated short premium in early 2025). Retail-accessible forms (PUT/BXM-style put-writing, covered calls, condors) captured it over long samples, but their edge over the S&P 500 has shrunk sharply since about 2015. Most of a covered call's risk is plain equity exposure, not the volatility premium.

### Cited Findings
- Carr & Wu (Review of Financial Studies, 2009) find average variance risk premiums are "strongly negative" for the S&P 500, S&P 100 and Dow indexes, so variance buyers accept negative average excess returns to hedge volatility spikes. The premiums remain strongly negative after accounting for option bid-ask spreads. — [Carr & Wu 2009, RFS (NYU copy)](https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf)
- Bondarenko's "overpriced puts puzzle": historical S&P 500 put prices have been too high to fit canonical asset-pricing models. The CBOE PutWrite Index methodology (Ungar & Moran 2009) is the standard put-writing benchmark. — [Quantpedia VRP effect summary](https://quantpedia.com/strategies/volatility-risk-premium-effect/); [Bollerslev & Todorov, NBER](https://projects.nber.org/confer/2010/APf10/Bollerslev_Todorov.pdf)
- Volatility-selling strategies show "relatively frequent (small) gains but occasional losses of excessive magnitude." Quantpedia cites a put-seller loss of as much as -800% in one case and stresses large margin reserves. (The figure's context is unclear, so treat it with caution.) — [Quantpedia](https://quantpedia.com/strategies/volatility-risk-premium-effect/)
- CBOE PutWrite (PUT) index: from July 1986 to Dec 2015 it outperformed the S&P 500 Total Return Index on a *gross* risk-adjusted basis. Turnover is much higher than the index, and BXM-tracking ETPs "substantially underperform BXM". — [Options-based benchmark indices review (vLex)](https://law-journals-books.vlex.com/vid/optionsbased-benchmark-indicesa-review-855598600)
- In a CBOE-commissioned backtest (ACG study, through Dec 2011), $1 growth from June 1986 was +1153% for PUT, +830% for BXM and +807% for the S&P 500. PUT, BXM and CLL had about 30% lower volatility than the S&P 500. (Commissioned by CBOE, and much of the pre-2007 history is back-filled.) — [Benzinga press release of the study](https://www.benzinga.com/pressreleases/12/02/n2344187/new-study-compares-25-year-performance-of-options-strategy-benchmarks-t); [CXO Advisory on PUT](https://www.cxoadvisory.com/equity-options/performance-of-cboe-putwrite-indexes)
- Post-2015 erosion: one analysis finds PUT's average monthly outperformance over BXM/benchmark fell from 0.15%/month before 2015 to 0.014%/month after. PUT beat BXM in about 68% of years (blog analysis, not peer-reviewed). — [R-bloggers "Writing conundrums" (2020)](https://www.r-bloggers.com/2020/09/writing-conundrums/)
- WisdomTree: 2008-2009 were among PUT's *best relative* years versus the S&P 500, because premium collected was high when VIX was high. Relative performance is driven mainly by total premium collected, which depends on the average VIX level. PUT still lost money in absolute terms in 2008 (it is short downside). — [WisdomTree](https://www.wisdomtree.com/us/insights/blog/a-strategy-for-volatile-markets/pdf)
- Israelov & Nielsen, "Covered Calls Uncovered" (FAJ 2015): a covered call = long equity + short volatility + an uncompensated "equity reversal" (market-timing) exposure. Equity exposure provides most of the risk and return. The short-volatility piece had a Sharpe ratio near 1.0 but only about 10% of risk. The reversal piece was about 25% of risk with little return. — [CFA Institute abstract](https://rpc.cfainstitute.org/research/financial-analysts-journal/2015/covered-calls-uncovered); [AQR "One Fact and Eight Myths"](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/FAJ-Covered-Call-Strategies-One-Fact-and-Eight-Myths.pdf)
- Delta-hedging away that timing component raised the Sharpe ratio from 0.37 (BXM) to 0.52 (Mar 1996-Dec 2014), before frictions. Daily hedge trading costs would work against this gain. Israelov, Klein & Tummala find the decomposition consistent across 11 global indexes, with equity-timing returns insignificant everywhere. — [CXO Advisory](https://www.cxoadvisory.com/equity-options/enhancement-of-index-covered-calls-via-hedging); [Journal of Risk](https://www.risk.net/journal-of-risk/5943741/covering-the-world-global-evidence-on-covered-calls)
- **Feb 2018 "Volmageddon":** on Feb 5, 2018 VIX roughly doubled (about 17 to 37, +116%). Short-volatility ETPs lost more than 90% in one day (FAJ). BIS puts XIV's drop at 84%, and XIV was terminated. Exact figures vary by source and window. — [CFA Institute FAJ 2021](https://rpc.cfainstitute.org/research/financial-analysts-journal/2021/volmageddon-failure-short-volatility-products); [BIS Quarterly Review, Mar 2018](https://www.bis.org/publ/qtrpdf/r_qt1803t.htm)
- **2020 vs 2022:** a Parametric (manager) piece says the VRP has averaged above 6.5 vol points since Q1 2020 and is most pronounced after volatility events. Protective hedges worked better in 2020 than in 2022 (a slow grind-down with high implied vol). This is marketing material, so treat it with caution. — [CAIA/Parametric](https://caia.org/node/6885)
- **April 2025 tariff shock:** a practitioner note reports short 1-DTE delta-hedged SPX straddles had a 10-day losing streak, with damage starting in January 2025 before the shock. Long VIX futures rallied into April. Hedgeweek reports Universa (tail-hedge fund) posted about +100% in April 2025 (unconfirmed by the founder). — [VolVibes Substack](https://volvibes.substack.com/p/market-overview-april-13th-2025); [Hedgeweek](https://www.hedgeweek.com/?p=90524)

### Inferences
- The VRP is real and persistent at the index level because there are structural buyers of protection (institutions with mandates and hedging needs). This matches the owner's "incentives" contradiction: hedgers rationally overpay. The premium compensates for crash risk, so a strategy that "works" for years can lose years of gains in a week.
- For modest capital, defined-risk versions (put spreads, iron condors) cap the tail but also give up a large part of the premium, because the premium is concentrated in the OTM puts. Whether a wing-hedged VRP strategy keeps a positive net edge after costs is an open, testable question, not something the literature settles.
- The post-2015 erosion of PUT's edge over the S&P 500 is consistent with crowding (growth of option-income ETFs and systematic short-volatility). It is not proven. Owner should test on post-2015 data only.
- Regime conditioning is the testable "contradiction" version: sell volatility when implied minus trailing realized vol is wide and VIX futures are in contango. Avoid or hedge when realized vol exceeds implied or the term structure inverts. Practitioners use this widely, but I did not verify a peer-reviewed out-of-sample test this session.

### Gaps
- No verified exact PUT/BXM calendar-year returns for 2008, 2018, 2020, 2022 or 2025 were retrieved. They can be downloaded from Cboe's index data pages for the owner's own analysis.
- Exact Carr-Wu magnitudes (implied minus realized variance in variance points) were not retrieved this session.
- No peer-reviewed post-publication decay study specific to the index VRP was found.
- No rigorous after-cost study of retail-style iron condors or short strangles was found. Most material is broker or vendor content.

---

## 2. Term structure, skew anomalies, earnings IV crush, and event-volatility mispricing

### Takeaway
Several cross-sectional option-implied signals have strong in-sample evidence: the IV-RV gap (Goyal-Saretto), smirk steepness (Xing-Zhang-Zhao), and pre-earnings straddles (Gao-Xing-Zhang). Some later work weakens them: risk-adjusting with conditional factor models, using real-time IV, accounting for frictions, and noting concentration in small, illiquid, expensive-to-trade names and around expiration days. The earnings evidence points in conflicting directions: long pre-announcement straddles were historically profitable, yet retail buyers overpay for high-expected-volatility announcements. This contradiction is itself worth testing.

### Cited Findings
- **IV-RV gap (cross-section):** Goyal & Saretto (JFE 2009) sort stocks on historical realized minus ATM implied volatility. Long (short) option portfolios with a large positive (negative) gap earn significant monthly returns that standard factors don't explain, across market conditions and option liquidity. — [EconPapers JFE 2009](https://econpapers.repec.org/RePEc:eee:jfinec:v:94:y:2009:i:2:p:310-326)
- A later Goyal-Saretto paper reports a monthly spread of about 3.5% (t about 20) for RV-IV sorts. Their 2022 IPCA paper argues these returns are not abnormal under a conditional factor model. Other work finds the premium depends on market and funding liquidity, and largely disappears with alternative real-time IV estimates. — [Dallas Fed WP 2214 (2022)](https://www.dallasfed.org/-/media/documents/research/papers/2022/wp2214.pdf); [CFR Cologne WP](https://www.cfr-cologne.de/download/workingpaper/cfr-16-08.pdf)
- **Expiration concentration:** Garcia-Ares & Muravyev (2025) find expiration rollover days account for about half of abnormal delta-hedged option returns across stocks, and all of the predictability in S&P 500 stocks. — [Garcia-Ares & Muravyev, Derivatives 2025 conference](https://fmai.memberclicks.net/assets/docs/Derivatives2025/GarciaAres.pdf)
- Delta-hedged option returns are lower for more overpriced stocks (Hofmann, Thimme & Uhrig-Homburg 2019), consistent with option traders acting on stock mispricing. — [KIT working paper](https://derivate.fbv.kit.edu/download/Hofmann_Thimme_Uhrig-Homburg_2019.pdf)
- **Skew/smirk:** Xing, Zhang & Zhao (JFQA 2010): steeper smirks (OTM put IV minus ATM call IV) predict lower future stock returns. The working paper reports a 10.9%/yr spread between steepest and flattest. Predictability lasts at least 6 months, and steep-smirk firms have worse next-quarter earnings shocks. The authors interpret this as informed traders using OTM puts. — [Cambridge JFQA](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/what-does-the-individual-option-volatility-smirk-tell-us-about-future-equity-returns/ECFD16BA9ACBDC8D577D1BD866FBEA72); [CXO Advisory](https://www.cxoadvisory.com/volatility-effects/smirking-because-they-know-something/)
- **Earnings, long side:** Gao, Xing & Zhang (JFQA 2018, "Anticipating Uncertainty: Straddles around Earnings Announcements"): ATM straddles bought 3 days before the announcement and held to the announcement earn a significant 3.34% on average (2.10%-3.34% across holding periods). The gains are larger for small, high-volatility, high-kurtosis, low-volume, high-transaction-cost firms. The authors read it as the market *underestimating* earnings-day uncertainty. — [Cambridge JFQA 2018](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/anticipating-uncertainty-straddles-around-earnings-announcements/7B34877AD5E06304BA3C55FBA3219FDD); [IDEAS](https://ideas.repec.org/a/cup/jfinqa/v53y2018i06p2587-2617_00.html)
- A conflicting study, Chung & Louis (2017), finds earnings straddle returns unrelated to historical vol, implied vol, or the HV-IV difference. — [summary via Cambridge/JFQA search result](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/anticipating-uncertainty-straddles-around-earnings-announcements/7B34877AD5E06304BA3C55FBA3219FDD) (secondary; not independently confirmed)
- **Earnings, short side / retail overpayment:** de Silva, Smith & So, "Losing is Optional" (Review of Finance, 2025): retail options trading concentrates around earnings and rises with expected announcement volatility. Retail buyers push up option prices before high-volatility announcements. Retail loses about 5-9% on average around earnings and 10-14% for high-expected-volatility announcements. The loss channels are overpaying relative to realized volatility, wide spreads, and slow closing after the IV crush. Market makers are the main counterparty. — [Stanford GSB](https://www.gsb.stanford.edu/faculty-research/publications/losing-optional-retail-option-trading-expected-announcement); [Q-Group slides 2024](https://qgroup.wildapricot.org/resources/2024%20Spring%20Seminar/Presentations/LosingIsOptional_20240430%20So.pdf); [Quantpedia](https://quantpedia.com/how-retail-losses-money-in-option-trading/)

### Inferences
- The earnings evidence is a ready-made "contradiction": Gao-Xing-Zhang say earnings-day IV is too low (buy pre-earnings straddles), while de Silva et al. say retail-heavy, high-expected-vol announcements are overpriced (sell them, or at least don't buy). A plausible reconciliation is that it depends on the subsample (small, illiquid names vs. names with heavy retail attention) and the period. The owner can test it directly by conditioning on retail attention or expected move.
- The post-earnings "IV crush" is mechanically certain (event variance leaves the term structure). Profit depends only on whether the implied event move exceeds the realized move, net of spreads, which are widest exactly at earnings.
- Many single-stock option anomalies are strongest where spreads are widest. A modest-capital trader paying quoted spreads may be unable to capture them (see Q5 on costs).

### Gaps
- Vasquez (JFQA 2017) on IV term-structure slope predicting straddle returns was not verified this session (search returned only a citation). Treat it as a lead to check.
- No post-2018 out-of-sample replication of the Gao-Xing-Zhang pre-earnings straddle was found.
- No verified data were found on how 0DTE/weekly options changed the term structure or event-pricing anomalies after 2022.

---

## 3. Price vs. narrative: news/social/LLM sentiment signals and decay after publication

### Takeaway
LLM-scored news (GPT-4-class models) predicts short-horizon drift, especially in small stocks and after negative news. The authors' own latest version reports that strategy returns *decline as LLM adoption grows*, which is direct evidence of decay. Retail social-media attention (WallStreetBets) correlates with retail options buying, which tends to lose money. That makes social narrative more useful as a "who is overpaying" contrarian/volatility input than as a direction signal.

### Cited Findings
- Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?" (arXiv 2304.07619, latest version Oct 2025): GPT-4 headline scores significantly predict subsequent drift, especially for small stocks and negative news. GPT-1, GPT-2 and BERT cannot, so predictability is an "emerging capacity" of large models. Strategy returns decline as LLM adoption rises, consistent with improving price efficiency. The authors' model predicts some predictability persists in equilibrium because of underreaction and limits to arbitrage. — [arXiv v6](https://arxiv.org/abs/2304.07619v3); [arXiv HTML v6](https://arxiv.org/html/2304.07619v6)
- Lopez-Lira (CNBC, April 2023, a personal guess, not a paper result): as more people use these tools markets become more efficient, and he guessed near-zero predictability within about five years. — [CNBC 2023](https://www.cnbc.com/2023/04/12/chatgpt-may-be-able-to-predict-stock-movements-finance-professor-says.html)
- Retail options trading is positively correlated with WallStreetBets ticker mentions (Bryzgalova, Pavlova & Sikorskaya, JF 2023). — [LBS research](https://lbsresearch.london.edu/id/eprint/2827)
- General anomaly decay benchmark: McLean & Pontiff (2016) find average stock-anomaly returns fall about 58% from in-sample to post-publication (0.58% to 0.26%/month), with part of the drop attributed to post-publication trading. Chen & Velikov find decay begins about 3 years *before* publication. — [CXO Advisory summary](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)

### Inferences
- As a direction signal, LLM sentiment is a crowded, decaying edge for anyone trading liquid large caps at retail speed. Any residual is likely in small, illiquid names, which also have the most expensive options.
- A more distinctive use that fits the thesis: measure the *gap* between narrative intensity (LLM-scored news and social attention) and what options price (IV relative to realized vol, skew). Then test whether high narrative attention plus rich IV predicts negative option returns for buyers (consistent with de Silva et al.). Combining these signals in this way is untested as far as I found.
- Use only point-in-time, timestamped news to avoid look-ahead. LLMs trained on data covering the backtest period can leak future knowledge. Lopez-Lira & Tang address this by testing after the model's training cutoff.

### Gaps
- No independent peer-reviewed replication of Lopez-Lira & Tang was found.
- No verified study was found using LLM sentiment specifically to trade *options* (as opposed to stocks).
- The size of the decay (bps per period) in Lopez-Lira & Tang's latest version was not extracted.

---

## 4. Options-flow / informed-trading signals (put-call ratios, IV spread, O/S, unusual activity)

### Takeaway
Academic evidence confirms that options volume and prices contain information about future stock returns. But the strongest results either depend on non-public signed or opening-trade data (Pan-Poteshman), are short-lived (a weekly horizon), or shrank over the sample period (Cremers-Weinbaum). Signals built from public data (O/S ratio, IV spread, smirk) are the accessible versions. Retail "unusual options activity" feeds have no direct peer-reviewed support that I found.

### Cited Findings
- Pan & Poteshman (RFS 2006): put-call ratios built from *buyer-initiated, open-position* volume (proprietary CBOE data) are negatively related to next-day and next-week returns. The information reflects informed trading rather than inefficiency. — [NBER working version](https://users.nber.org/~confer/2003/aps03/pan.pdf); [NBER w10925 summary](https://causalclaims.trfetzer.com/paper/w10925.html)
- Johnson & So (JFE 2012): the option-to-stock volume ratio (O/S, from *public* volume) negatively predicts future weekly stock returns, and predicts the sign and size of earnings surprises and announcement returns. A comparison study finds O/S predicts negative returns at daily, weekly and monthly horizons, while P/C ratio predictability is "fleeting" at the weekly horizon. — [SJTU conference paper (review)](https://www.acem.sjtu.edu.cn/sffs/2020/pdf/paper4.pdf); [NBER w19590](https://www.nber.org/papers/w19590.pdf)
- Ge, Lin & Pearson (2016) split O/S into eight signed measures that also predict weekly returns. — [SJTU conference paper (review)](https://www.acem.sjtu.edu.cn/sffs/2020/pdf/paper4.pdf)
- Cremers & Weinbaum (JFQA 2010), sample 1996-2005: stocks with relatively expensive calls (positive IV spread, i.e. put-call parity deviation) beat stocks with expensive puts by about 50 bps/week. **Predictability decreased over the sample period**, consistent with mispricing being gradually arbitraged away. It is strongest when option liquidity is high and stock liquidity is low, and not explained by short-sale constraints. — [Cambridge JFQA](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/deviations-from-putcall-parity-and-stock-return-predictability/D9BA8F97580328AAFD7988B092FE5D50); [CXO Advisory](https://www.cxoadvisory.com/volatility-effects/do-informed-traders-tip-their-hands-via-option-purchases/)
- Xing-Zhang-Zhao smirk predictability (see Q2), interpreted as informed put buying. — [Cambridge JFQA](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/what-does-the-individual-option-volatility-smirk-tell-us-about-future-equity-returns/ECFD16BA9ACBDC8D577D1BD866FBEA72)

### Inferences
- These signals predict the *stock*, mostly at 1-week horizons and mostly through negative returns (bad news). For a small trader, the cheapest way to use them may be as a filter or overlay (e.g. avoid selling puts on names with steep smirks, high O/S or negative IV spread), not as standalone directional option trades.
- Post-2020 retail and 0DTE volume probably adds noise to raw volume and P/C signals, since much volume is now uninformed lottery demand. That is a reason to prefer signed, opening, or price-based (IV spread, skew) measures. This is a hypothesis, not a verified result.
- Commercial flow feeds (including the Unusual Whales connector available in this environment) can supply O/S, flow and skew inputs. Their "unusual activity" alerts should be treated as unvalidated until backtested point-in-time.

### Gaps
- No peer-reviewed post-2015 out-of-sample test of O/S or IV spread was found this session.
- No academic evaluation of retail "unusual options activity" alert services was found.

---

## 5. Retail options trading outcomes and transaction costs (realistic expectations)

### Takeaway
Retail options traders lose money in aggregate, and costs (spreads and wholesaler execution), not just bad forecasts, explain a large share of it. Losses are concentrated in exactly the products and moments the thesis is drawn to: short-dated or 0DTE, lottery-like OTM contracts, and earnings. Sophisticated traders who time their executions pay far less than quoted spreads, so execution skill is itself a large part of any edge.

### Cited Findings
- Bryzgalova, Pavlova & Sikorskaya, "Retail Trading in Options and the Rise of the Big Three Wholesalers" (Journal of Finance 78(6), 2023): retail investors lost about $1.14B on options from Nov 2019 to June 2021 (assuming a 10-day hold). Press reports put it at more than $5B including costs paid to market makers. Retail favors lottery-like contracts. "The more they trade, the more they lose" because of bid-ask spreads. Dollar options volume grew 143% from Nov 2019 to Jul 2021. — [LBS research](https://lbsresearch.london.edu/id/eprint/2827); [IDEAS/CEPR DP17688](https://ideas.repec.org/p/cpr/ceprdp/17688.html); [FA Magazine](https://www.fa-mag.com/news/mom-and-pop-investors-took-a-billion-dollar-bath-trading-options-during-the-pandemic-67571.html?section=43)
- Beckmeyer, Branger & Gayda, "Retail Traders Love 0DTE Options... But Should They?" (SSRN 2023): 0DTE made up more than 75% of retail S&P 500 index-option volume. Retail lost about $184k per average day (Feb 2021-Feb 2023), rising to about $358k/day after daily expirations began in May 2022. About 60% of losses came from transaction costs. Motives appear to be gambling and entertainment. — [BNN Bloomberg](https://www.bnnbloomberg.ca/day-traders-lose-358-000-per-day-gambling-on-zero-day-options-1.1910634); [CXO Advisory](https://www.cxoadvisory.com/individual-investing/retail-0dte-option-trader-performance); [Neudata review](https://www.neudata.co/literature-reviews/zero-day-to-expiry-options-a-losing-bet-for-retail-traders)
- de Silva, Smith & So (Review of Finance 2025): retail loses about 5-9% around earnings, 10-14% for high-expected-volatility announcements (see Q2). — [Stanford GSB](https://www.gsb.stanford.edu/faculty-research/publications/losing-optional-retail-option-trading-expected-announcement)
- Muravyev & Pearson, "Options Trading Costs Are Lower than You Think" (RFS 2020): traders who time executions pay effective spreads under 40% of conventional measures. The average adjusted effective spread is about 1.3 cents versus an 8.1-cent quoted spread and a 6.2-cent conventional effective spread. A summary of the paper states that conventional half-spreads would consume about 80% of the high pre-cost returns of option anomaly strategies (about 40% at algo-timed costs). Ordinary investors still bear conventional spreads. — [EconPapers RFS 2020](https://econpapers.repec.org/RePEc:oup:rfinst:v:33:y:2020:i:11:p:4973-5014.); [CXO Advisory](https://www.cxoadvisory.com/equity-options/timing-option-trades-to-suppress-trading-frictions/); [thread summary (verify against paper)](https://threadreaderapp.com/thread/1346160221408829441.html)

### Inferences
- Realistic baseline: the default outcome for an active retail options trader is negative, and the counterparty (wholesalers and market makers) is structurally advantaged. Any strategy that *buys* short-dated, OTM, or pre-earnings options has to clear a high bar.
- The thesis's natural position is to be the *other side* of documented retail and hedger overpayment (selling rich premium with defined risk), while respecting tail risk. Execution through limit orders near mid, avoiding the open and close, and trading liquid underlyings (SPX/SPY/QQQ, mega-caps) matters as much as signal choice.
- Paper trading through Alpaca, which the project plans, will *understate* costs unless the backtester models fills at mid minus/plus a realistic fraction of the spread and per-contract fees.

### Gaps
- No verified estimates were found of Alpaca options fill quality or payment-for-order-flow effects specifically.
- The exact Bryzgalova et al. cost decomposition was not extracted from the full paper.

---

## 6. Which 2-3 contradiction strategies are most testable with modest capital and API data, and key pitfalls

### Takeaway
Ranked by evidence strength x testability x survivability for modest capital:
1. **Index "implied vs. realized" premium with defined risk and regime filters.** SPY/SPX/XSP put spreads, iron condors, or a PUT-style put-write, conditioned on the IV-RV spread and VIX term structure. The evidence is strongest here, and free benchmarks (Cboe PUT/BXM history) exist.
2. **Earnings event-volatility contradiction.** Compare the implied earnings move (from the front-month straddle and term-structure kink) with historical realized earnings moves. Test both directions: sell where retail attention and expected volatility are high (de Silva et al.), and buy pre-announcement where IV understates history (Gao-Xing-Zhang). It is limited to liquid large caps to keep spreads tolerable.
3. **Options-implied information as a filter** (smirk steepness, IV spread, O/S) layered on strategy 1 or 2, or on stock positions. It is not a standalone trade. LLM or narrative sentiment fits here as an additional "narrative intensity vs. priced volatility" filter, with the expectation that its standalone edge is decaying.

### Cited Findings
- The VRP is robust to bid-ask spreads at the index level (Carr & Wu 2009) but carries extreme tail risk (Feb 2018 ETP collapse of more than 90%). — [Carr & Wu](https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf); [CFA FAJ](https://rpc.cfainstitute.org/research/financial-analysts-journal/2021/volmageddon-failure-short-volatility-products)
- PUT index outperformance versus the S&P 500 eroded sharply after 2015. — [R-bloggers](https://www.r-bloggers.com/2020/09/writing-conundrums/)
- Covered-call / put-write returns are mostly equity beta, and the timing component is uncompensated. So test against a beta-matched benchmark, not cash. — [CFA Institute](https://rpc.cfainstitute.org/research/financial-analysts-journal/2015/covered-calls-uncovered)
- Option anomaly profits are heavily eroded by conventional spreads (about 80%) unless execution is timed. — [thread summary of Muravyev & Pearson](https://threadreaderapp.com/thread/1346160221408829441.html)
- Half of abnormal delta-hedged returns sit on expiration rollover days, and all of the S&P 500 predictability does. This is a key look-ahead/microstructure pitfall in backtests. — [Garcia-Ares & Muravyev 2025](https://fmai.memberclicks.net/assets/docs/Derivatives2025/GarciaAres.pdf)
- Some IV-RV anomaly returns disappear with real-time IV estimates, a stale or closing-quote pitfall. — [Dallas Fed WP 2214](https://www.dallasfed.org/-/media/documents/research/papers/2022/wp2214.pdf)
- Anomalies decay about 58% after publication on average, and decay can start about 3 years before publication. — [CXO Advisory](https://www.cxoadvisory.com/big-ideas/effects-of-market-adaptation)
- BXM-tracking ETPs substantially underperform their index, so implementation drag is real. — [vLex review](https://law-journals-books.vlex.com/vid/optionsbased-benchmark-indicesa-review-855598600)

### Inferences (pitfalls checklist for the owner)
- **Overfitting:** dozens of strike, DTE, exit and filter choices on one index makes data-mining easy. Pre-register a small parameter grid, hold out post-2020 data, and report the full distribution of variants, not the best one. Check the 2018, 2020, 2022 and Apr 2025 episodes individually.
- **Transaction costs:** model fills at mid plus 25-50% of the half-spread at minimum, plus per-contract fees. Run sensitivity to 100% of the half-spread. Four-leg condors pay spreads four times.
- **Tail/margin:** size by maximum loss, not premium. Undefined-risk short strangles are inappropriate for modest capital. Margin expansion in spikes forces liquidation at the worst time (the owner's "liquidity paradox").
- **Assignment/exercise:** American-style single-stock and ETF options (SPY) can be assigned early, especially ITM short calls before ex-dividend. SPX/XSP are European and cash-settled (also Section 1256 tax treatment in the US). Pin risk at expiry applies.
- **Data:** API data (Alpaca, Unusual Whales, etc.) often lack long, survivorship-free, timestamped historical chains with bid/ask. Without them, backtests of single-stock strategies are unreliable. Index strategies can be sanity-checked against Cboe PUT/BXM history.
- **Look-ahead:** earnings dates must be known before entry, IV must be measured at trade time (not close), and LLM sentiment must come from post-training-cutoff news.
- **Benchmarking:** compare against beta-matched SPY exposure and Cboe PUT/BXM, after costs. The README already asks for win rate plus win/loss size, drawdown and after-cost results, which is appropriate for negatively skewed strategies with high win rates.

### Gaps
- No peer-reviewed after-cost evaluation was found of retail-sized defined-risk VRP strategies (condors, put spreads) on post-2015 data. This is the owner's most valuable first experiment.
- No verified data were found on the historical depth and quality of options chain data available via Alpaca or the other connected APIs.
- Vasquez (2017) term-structure evidence, Coval & Shumway (2001), Bakshi & Kapadia (2003) delta-hedged gains, and the Ni, Pan & Poteshman volatility-demand work are standard references not verified this session. They are worth retrieving before building the term-structure strategy.
