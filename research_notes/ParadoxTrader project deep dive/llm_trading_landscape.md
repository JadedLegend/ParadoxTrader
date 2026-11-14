# LLM-Based Multi-Agent Trading Systems: State of the Art and Real-World Evidence (as of Nov 2026)

Research date: 2026-11-14. Labels used: **[BACKTEST]** = historical simulation; **[LIVE/FORWARD]** = decisions made in real time on data that did not exist at model training time (paper or real money); **[PRIOR-KNOWLEDGE]** = from the researcher's background knowledge of well-known papers, with the arXiv link given but not re-fetched this session. Verify those before quoting them as figures.

Method note: GitHub API access was blocked in this session, so repo stats come from fetching the GitHub web pages (TradingAgents, ai-hedge-fund only). Several leads (ThinkAdvisor/Bloomberg piece, the "Alpha Illusion" review) returned 403/429 and could not be read in full.

---

## 1. What open-source and academic multi-agent LLM trading frameworks exist, how are they built, how active are they, and what is reusable?

### Takeaway
The field has converged on one pattern, popularized by TradingAgents: parallel specialist analysts, a bull/bear researcher debate, a trader, then risk management and a portfolio-manager gate. TradingAgents (Tauric Research) is by far the most active and most reusable codebase as of late 2026. In 2026 it added point-in-time data and look-ahead fixes, which ParadoxTrader would otherwise have to build itself. virattt/ai-hedge-fund is the other big one, built on "investor persona" agents. Most academic frameworks (FinMem, FinAgent, FinCon, StockAgent) are research artifacts, not maintained platforms. **None of them is options-native.**

### Cited Findings
**TradingAgents (Tauric Research)**
- Original paper, arXiv 2412.20138 (Dec 2024). It describes a firm-like multi-agent system and claims that agents use only data available up to each trading day, "eliminating look-ahead bias." It reports gains over baselines in cumulative return, Sharpe ratio and max drawdown **[BACKTEST]**. — [arXiv 2412.20138](https://arxiv.org/pdf/2412.20138)
- Architecture, per the README as of Nov 2026 (LangGraph-based):
  - an Analyst team (Fundamentals, Sentiment, News, Technical) that runs concurrently
  - Bullish and Bearish researchers who debate the analyst reports
  - a Trader who turns reports and debate into a decision
  - Risk management reviews that feed a Portfolio Manager, who approves or rejects the proposal; approved orders go to a simulated exchange
  — [GitHub TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- Activity, as shown on the GitHub page when fetched 2026-11-14: about 122.5k stars, 23.5k forks, 516 commits, Apache-2.0 license. The star count was read from a page summary; confirm it before quoting. — [GitHub](https://github.com/TauricResearch/TradingAgents)
- Release cadence in 2026: — [GitHub](https://github.com/TauricResearch/TradingAgents)
  - v0.4.0 (Aug 2026): look-ahead and point-in-time fixes, checkpoint resume
  - v0.5.0 (Sep 2026): point-in-time data integrity, SEC EDGAR fundamentals "as filed," backtesting over a ticker × date grid, portfolio-aware runs
  - v0.5.2: analysts run in parallel; non-interactive CLI
  - v0.6.0 (Oct 2026): a different provider per model tier, so cheap analysts and strong managers can be mixed
  - v0.7.0 / v0.7.1 (Oct 2026): backtests scored from the first close after each decision; a fix for a bug where models could read filings made after the run date
  - A sibling project, Trading-R1 v0.1.0 (Nov 2026), is in early access.
- Supported providers include OpenAI, Anthropic, Gemini, xAI, DeepSeek, Qwen, GLM, Mistral, Kimi, Groq, OpenRouter, Azure and Bedrock, plus local servers (Ollama, vLLM). — [GitHub](https://github.com/TauricResearch/TradingAgents)
- Data sources: SEC EDGAR, Yahoo Finance, StockTwits/Reddit sentiment, FRED macro, Polymarket and Alpha Vantage. **There is no options-chain or implied-volatility data source.** — [GitHub](https://github.com/TauricResearch/TradingAgents)
- Its own disclaimers: "designed for research purposes"; outputs are non-deterministic; backtests are not guaranteed to match published figures. — [GitHub](https://github.com/TauricResearch/TradingAgents)

**AI Hedge Fund (virattt)**
- About 64.7k stars, 11.4k forks and 964 commits (fetched 2026-11-14). It offers paper trading over completed sessions with an approval step, a kill switch and a hash-chained ledger, plus a backtesting mode. — [GitHub virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)
- It calls itself "a proof of concept... for educational purposes only... not intended for real trading," and says "the system does not actually make any trades." — [GitHub](https://github.com/virattt/ai-hedge-fund)
- Data comes from Financial Datasets (financialdatasets.ai, paid key or x402 micropayments). The current README does not list the persona agents (famous-investor personas such as Buffett and Munger are the project's known design **[PRIOR-KNOWLEDGE]**). — [GitHub](https://github.com/virattt/ai-hedge-fund)

**Academic frameworks [PRIOR-KNOWLEDGE, links not re-fetched]**
- **FinMem** (Nov 2023): a single agent with layered memory (short/mid/long-term) and a character profile. — [arXiv 2311.13743](https://arxiv.org/abs/2311.13743)
- **FinAgent** (Feb 2024): a multimodal agent (price charts plus text) with reflection modules. — [arXiv 2402.18485](https://arxiv.org/abs/2402.18485)
- **FinCon** (Jul 2024, NeurIPS 2024): a manager–analyst hierarchy with "conceptual verbal reinforcement" and risk-control belief updates. — [arXiv 2407.06567](https://arxiv.org/abs/2407.06567)
- **FinRobot** (AI4Finance, May 2024): an agent platform for financial analysis and report generation more than for execution. — [arXiv 2405.14767](https://arxiv.org/abs/2405.14767)
- **StockAgent** (Jul 2024): simulates a market of LLM investor agents to study behavior, not to generate alpha. — [arXiv 2407.18957](https://arxiv.org/abs/2407.18957)

**Newer frameworks (2025–2026)**
- A fine-grained multi-agent trading paper (Feb 2026) runs systematic ablations by removing and replacing agents. It notes that most earlier LLM trading work used single-agent designs. — [arXiv 2602.23330](https://arxiv.org/html/2602.23330)
- A macro multi-agent framework (Jun 2026) has Hawkish, Dovish and Rule agents plus a Debate agent for commodity ETF portfolios. — [arXiv 2606.08283](https://arxiv.org/abs/2606.08283)
- TriAgent (2026) proposes divergence-aware committees aimed at cost efficiency. — [alphaXiv 2607.19794](https://www.alphaxiv.org/abs/2607.19794.md)
- A taxonomy paper (Mar 2026, PAKDD 2026 workshop) classifies 12 financial multi-agent systems and 2 single-agent baselines on four axes: architecture pattern, coordination mechanism, memory and tool integration. — [arXiv 2603.27539](https://arxiv.org/abs/2603.27539)
- Trading-R1 (Tauric) is a reasoning-trained trading model, now in early access. — [GitHub TradingAgents](https://github.com/TauricResearch/TradingAgents)

### Inferences
- ParadoxTrader's seven personas map closely onto TradingAgents' roles:
  - momentum/volatility ≈ Technical analyst
  - sentiment/narrative ≈ Sentiment and News analysts
  - macro ≈ the FRED-backed analyst inputs
  - dissent/devil's advocate ≈ the Bear researcher
  - contradiction-synthesis ≈ the Trader / Portfolio Manager

  The genuinely new parts are the **options-structure** and **correlations** personas and the options data and execution layer.
- The most valuable reusable assets in TradingAgents are its data-integrity and backtest scoring work (point-in-time data, filings "as filed," scoring from the next close), the per-tier model routing for cost control, and the LangGraph orchestration. These are tedious to rebuild correctly.

### Gaps
- Exact star counts and last-commit dates for FinMem, FinCon, FinRobot, FinGPT and StockAgent could not be retrieved (GitHub API blocked); their maintenance status is unverified.
- I did not fetch the current ai-hedge-fund persona list.

---

## 2. What do rigorous evaluations show: live benchmarks, competitions, and look-ahead/contamination critiques?

### Takeaway
The best evidence (live tests and leakage-safe backtests from 2025–2026) is that **LLM agents mostly fail to beat buy-and-hold or passive benchmarks**. In live competitions most models lose money, and winners vary from season to season. Published backtest alpha largely disappears under longer horizons, broader universes, point-in-time data and cost-aware, multiple-testing-corrected evaluation.

### Cited Findings
**Live competitions [LIVE/FORWARD]**
- **Alpha Arena Season 1** (nof1.ai, Oct 18 – Nov 3, 2025): six frontier models each got $10k of real crypto capital. More than half finished in the red. Qwen 3 Max won. GPT-5 and Gemini 2.5 Pro lost more than 28%. Disciplined, low-frequency strategies did better than overtrading. — [iWeaver summary](https://iweaver.ai/blog/alpha-arena-ai-trading-season-1-results); [ForkLog](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/); [Decrypt](https://decrypt.co/345006/ai-crypto-trading-showdown-deepseek-grok-winning-gemini-implodes). These are secondary news sources.
- **Alpha Arena Season 1.5** (US stocks, about two weeks, reported 8 Dec 2025): four modes ran, namely New Baseline, Monk Mode (capital preservation), Situational Awareness (sees competitors' rankings) and Max Leverage. An undisclosed "Mystery Model," later identified as Grok 4.20, won with an average return of about +12% and was profitable in all four modes. GPT-5.1 came second and Gemini 3 third. As of Dec 8 every other model was at a loss. — [ForkLog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/)
- A later aggregate figure: across the four US tech-stock contests (32 model × mode results), only 6 finished positive and the overall portfolio fell about 33%. This comes from a KuCoin flash summary and a Nov 2026 briefing. It is secondary, and its structure does not fully match ForkLog's. — [KuCoin](https://www.kucoin.com/news/flash/ai-trading-models-struggle-in-live-market-tests-majority-of-systems-report-losses)
- The nof1 founder said it is not yet feasible to hand money to an LLM and let it trade on its own. Season 2 (web search, longer reasoning, multi-step) was described as "upcoming" as of May–Nov 2026, and I found no published Season 2 results. — [ThinkAdvisor/Bloomberg, May 2026](https://www.thinkadvisor.com/amp/2026/05/06/why-ai-bots-arent-ready-to-replace-your-fund-manager/) (search snippet only; page returned 403)
- **LiveTradeBench** (UIUC, arXiv 2511.03628, Nov 2025) ran a 50-day live evaluation (Aug 18 – Oct 24, 2025) of 21 LLMs on US stocks and Polymarket. Findings:
  - High LMArena scores do not imply better trading.
  - Models show distinct risk styles.
  - The benchmark omits transaction costs, slippage and liquidity, which flatters high-turnover strategies.

  — [arXiv 2511.03628](https://arxiv.org/html/2511.03628v1)
- **Agent Market Arena (AMA)** (arXiv 2510.11695, Oct 2025) is a "lifelong, real-time" benchmark on crypto and stocks. It compares agent frameworks (InvestorAgent, TradeAgent, HedgeFundAgent, DeepFundAgent) across GPT-4o/4.1, Claude 3.5 Haiku / Sonnet 4 and Gemini 2.0 Flash. Key finding: **the agent framework explains more outcome variation than the model backbone does.** — [arXiv 2510.11695](https://arxiv.org/abs/2510.11695)
- **AI-Trader** (HKUDS, arXiv 2512.10971) is a live benchmark across US stocks, A-shares and crypto. — [arXiv 2512.10971](https://www.arxiv.org/pdf/2512.10971)

**Contamination-aware or long-horizon backtests [BACKTEST]**
- **StockBench** (arXiv 2510.02209, Oct 2025, revised Mar 2026) is a multi-month benchmark designed to avoid contamination. "Most models struggle to outperform the simple buy-and-hold baseline," though some show better returns or risk control. — [arXiv 2510.02209](https://arxiv.org/abs/2510.02209)
- **FINSABER** ("Can LLM-based Financial Investing Strategies Outperform the Market in Long Run?", arXiv 2505.07078; KDD 2026 D&B oral; v6 June 2026) tested over 20 years and more than 100 symbols. Previously reported LLM advantages "deteriorate significantly." LLM strategies are **too conservative in bull markets and too aggressive in bear markets**. The authors recommend focusing on trend detection and regime-aware risk control rather than more framework complexity. — [arXiv 2505.07078](https://arxiv.org/abs/2505.07078)
- The same paper lists TradingAgents among systems evaluated over short windows and narrow universes, which it says are prone to survivorship, data-snooping and look-ahead bias. — [arXiv 2505.07078 v1](https://arxiv.org/html/2505.07078v1)
- **"What survives honest evaluation?"** (Gençay, arXiv 2608.27734, Aug 27 2026) used a 453-stock point-in-time US universe and 39 ETFs, with transaction, impact and borrow costs. Results:
  - A deliberately leaky oracle with Sharpe 35 *passed* the Deflated Sharpe and PBO tests, so statistical correction alone cannot catch leakage.
  - Across two frontier models, up to 100-candidate search budgets and 5 repeats, **every LLM-discovered strategy was rejected**, while passive benchmarks passed.
  - The best in-sample Sharpe rises with search, but the deflation threshold rises faster.

  This paper covers LLM *strategy discovery*, not agent trading. — [arXiv 2608.27734](https://arxiv.org/abs/2608.27734)
- The taxonomy paper (arXiv 2603.27539) names five pervasive evaluation failures: look-ahead bias, survivorship bias, backtest overfitting, neglected transaction costs and blindness to regime shifts. It says these "can reverse the sign of reported returns." It proposes a "Coordination Breakeven Spread" metric for whether coordination pays for itself after costs. — [arXiv 2603.27539](https://arxiv.org/abs/2603.27539)
- Commentary notes that LLM contamination can come from semantic memory absorbed in pretraining or from retrieval corpora, even when the backtest code is clean. A model "knowing" 2024 outcomes biases any backtest dated before its training cutoff. — via search summary of [arXiv 2603.22567](https://arxiv.org/html/2603.22567v1) (not fetched in full)
- TradingAgents' own 2026 changelog fixes a bug where models could read filings made after the run date. This is concrete evidence that even the flagship framework had leakage paths until Oct 2026. — [GitHub](https://github.com/TauricResearch/TradingAgents)

**Older benchmarks [PRIOR-KNOWLEDGE]**
- FinBen (Feb 2024) is a broad financial-NLP and LLM benchmark that includes a trading task. — [arXiv 2402.12659](https://arxiv.org/abs/2402.12659)
- InvestorBench (Dec 2024) is an agent benchmark across stocks, crypto and ETFs. — [arXiv 2412.18174](https://arxiv.org/abs/2412.18174)
- DeepFund (Mar 2025) is a live-arena-style evaluation designed to avoid look-ahead. — [arXiv 2503.18313](https://arxiv.org/abs/2503.18313)

### Inferences
- Any ParadoxTrader backtest over periods before the models' training cutoffs is suspect by default. Only forward or paper testing after the cutoff gives clean evidence.
- Live competitions are tiny samples (two-week windows, a handful of models). "Winners" (Qwen in S1, Grok 4.20 in S1.5) are statistically indistinguishable from luck, and a different model won each season.

### Gaps
- I did not obtain full numeric StockBench, AMA or LiveTradeBench leaderboards (abstract pages lack the numbers).
- I found no official nof1.ai leaderboard data; all Alpha Arena figures are from secondary news.
- I found no published Alpha Arena Season 2 results as of Nov 2026.

---

## 3. Does multi-agent debate or persona diversity beat a single model or simple baselines? Any evidence on options specifically?

### Takeaway
Controlled 2025–2026 ablations give **weak to negative** evidence that debate or persona ensembles add value beyond a well-chosen single agent. When debate helps, it mostly seems to average out a badly calibrated agent, not to produce genuine deliberation. Diversity of *information and tools* matters more than the number of personas. Options-specific evidence is thin: LLMs struggle with raw option-chain data, and the best results come from making the LLM a parser into a deterministic options engine.

### Cited Findings
- **Macro ETF debate paper** (arXiv 2606.08283, Jun 2026): over 124 weekly rebalancing dates (2023–2025), the Debate Agent did **not** beat the best single agent (ΔSharpe = −0.004, p = 0.769). Compared with a Rule Agent: Debate gained ΔSharpe +0.040 and Hawkish +0.044 (both p < 0.10, not adjusted for multiple comparisons). The authors attribute debate's value to bias correction (averaging out the Dovish agent's miscalibrated prior), with gains concentrated in one sub-period. — [arXiv 2606.08283](https://arxiv.org/abs/2606.08283)
- **TriAgent** (2026): a same-size multi-agent persona panel scored *below* the single-agent baseline (F1 0.66 vs 0.69), which the authors blame on a lack of real diversity. This is a financial classification task, not trading. — [alphaXiv 2607.19794](https://www.alphaxiv.org/abs/2607.19794.md) (via search summary)
- **DS@GT StockTron** (CLEF 2026 notebook): tool ablations on TSLA and BTC conclude that tool and information quality matter more than architectural complexity. — [CEUR-WS Vol-4283 paper196](https://ceur-ws.org/Vol-4283/paper196.pdf) (via search summary)
- **Market-dependent communication** (arXiv 2511.13614, NeurIPS 2025 workshop): 450 experiments across five organizational structures, including an isolated baseline. Communication helped for tech and general stocks but not for financials. — [arXiv 2511.13614](https://www.arxiv.org/pdf/2511.13614) (via search summary)
- **AMA** (arXiv 2510.11695): the framework matters more than the backbone model. This is mild support for architecture mattering, but no single architecture consistently wins. — [arXiv 2510.11695](https://arxiv.org/abs/2510.11695)
- The taxonomy paper offers its "Coordination Primacy Hypothesis" (coordination design drives decision quality more than model scale) explicitly as an *untested* hypothesis. — [arXiv 2603.27539](https://arxiv.org/abs/2603.27539)
- FINSABER: adding framework complexity does not fix the regime problems; it recommends regime-aware risk controls instead. — [arXiv 2505.07078](https://arxiv.org/abs/2505.07078)

**Options**
- "From Natural Language to Executable Option Strategies via LLMs" (arXiv 2603.16434, Mar 2026) builds a benchmark of 200 option trading instructions. Direct LLM generation is "overwhelmed" by multi-dimensional option-chain data with strict constraints. Their fix is an Option Query Language (OQL) intermediate layer: the LLM acts as a semantic parser and a deterministic engine executes. The authors report this "significantly improves execution accuracy and logical consistency over direct baselines" (no numbers on the abstract page). — [arXiv 2603.16434](https://arxiv.org/abs/2603.16434)
- TraderBench (arXiv 2603.00285, Feb 2026) has an options section scored on P&L accuracy, Greeks accuracy, strategy quality and risk management, with Greeks and IV tooling. Extended thinking helped tool use but had **no effect on trading performance**. — [arXiv 2603.00285](https://arxiv.org/html/2603.00285) (via search summary)
- I found no live or forward test showing LLM agents earning edge in options.

### Inferences
- For ParadoxTrader, the seven personas should be justified by *distinct data and tools* (an IV surface for the options-structure persona, a correlation matrix for the correlations persona, macro series for macro), not by distinct prompts over the same context. Otherwise the TriAgent and macro-debate results suggest the ensemble collapses toward a single view or merely averages out bias.
- The dissent/devil's-advocate persona may be best framed as a bias-correction device (like the debate paper's finding), and its value should be measured against a "best single persona" baseline.
- The options-structure persona should emit a structured spec (legs, strikes, DTE, delta targets) that a deterministic engine validates and prices. It should never produce raw trade tickets from chain text.

### Gaps
- I found no rigorous study comparing debate with a single agent on *options* P&L.
- I did not fetch the TraderBench options numbers.

---

## 4. What failure modes are commonly reported?

### Takeaway
The recurring failures are:
- regime miscalibration (too timid in bulls, too aggressive in bears)
- overtrading
- leverage blowups in live arenas
- non-determinism
- leakage through data or pretraining memory
- ignored costs
- performance that does not track general model capability
- homogeneous agent panels that add cost without diversity

### Cited Findings
- Overtrading lost money in Alpha Arena S1; disciplined low-frequency strategies did better; GPT-5 and Gemini 2.5 Pro lost more than 28%. — [iWeaver](https://iweaver.ai/blog/alpha-arena-ai-trading-season-1-results); [Decrypt](https://decrypt.co/345006/ai-crypto-trading-showdown-deepseek-grok-winning-gemini-implodes)
- S1.5 had a mandatory "Max Leverage" mode, and most models were at a loss. — [ForkLog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/)
- Regime miscalibration: too conservative in bulls, too aggressive in bears. — [arXiv 2505.07078](https://arxiv.org/abs/2505.07078)
- Non-determinism: identical inputs can give different decisions, and backtests may not match published figures. — [TradingAgents README](https://github.com/TauricResearch/TradingAgents)
- Leakage bugs, such as filings from after the run date reaching the model, were fixed in TradingAgents v0.7.1 (Oct 2026). — [GitHub](https://github.com/TauricResearch/TradingAgents)
- Leakage can survive standard overfitting statistics (the Sharpe-35 oracle passed DSR and PBO), and search over LLM-proposed strategies inflates in-sample results. — [arXiv 2608.27734](https://arxiv.org/abs/2608.27734)
- Cost neglect can flip the sign of returns. — [arXiv 2603.27539](https://arxiv.org/abs/2603.27539)
- LiveTradeBench ignores costs and slippage. — [arXiv 2511.03628](https://arxiv.org/html/2511.03628v1)
- General benchmark rank (LMArena) does not predict trading skill. — [arXiv 2511.03628](https://arxiv.org/html/2511.03628v1)
- Same-model persona panels lack diversity and underperform a single agent. — [TriAgent](https://www.alphaxiv.org/abs/2607.19794.md)
- LLMs are overwhelmed by raw option-chain data, producing constraint violations and logical inconsistency. — [arXiv 2603.16434](https://arxiv.org/abs/2603.16434)

### Inferences
- I found no 2025–2026 source that directly quantifies hallucinated data or sycophancy *among trading agents*. The TriAgent diversity-collapse result is the closest evidence.
- Cost blowups: multi-agent pipelines multiply the number of LLM calls. TradingAgents v0.6.0 added cheap-analyst / strong-manager model tiers, which suggests token cost is a real pain point. That is an inference from the feature, not a measured figure.

### Gaps
- I found no source with measured API cost per trading decision for multi-agent frameworks.
- I found no systematic study of hallucinated prices or fundamentals in trading agents.

---

## 5. Lessons for a solo builder: build vs. fork?

### Takeaway
Fork or borrow from TradingAgents for orchestration, point-in-time data integrity and backtest scoring. Build the options-specific layer yourself: chain/IV data, a deterministic strategy and pricing engine, and Greeks-based risk. Treat the whole thing as a research environment whose job is to *falsify* edge through forward paper-testing against simple baselines, not to assume it.

### Cited Findings
- TradingAgents already provides the following, under Apache-2.0: — [GitHub](https://github.com/TauricResearch/TradingAgents)
  - an analyst → debate → trader → risk → portfolio-manager graph
  - parallel analysts
  - per-tier provider routing
  - point-in-time SEC data
  - next-close scoring
  - grid backtesting
  - checkpoint resume
- ai-hedge-fund provides paper-trading scaffolding: an approval step, a kill switch and a hash-chained ledger. — [GitHub](https://github.com/virattt/ai-hedge-fund)
- Options execution works best through a structured intermediate language and a deterministic engine. — [arXiv 2603.16434](https://arxiv.org/abs/2603.16434)
- Use honest evaluation:
  - point-in-time data
  - costs, impact and borrow
  - deflated Sharpe, plus a separate leakage guardrail
  - pre-registered hypotheses, which "warrant lower evidential bars than brute-force search"

  — [arXiv 2608.27734](https://arxiv.org/abs/2608.27734)
- Prioritize regime-aware risk controls over framework complexity. — [arXiv 2505.07078](https://arxiv.org/abs/2505.07078)
- Report debate vs. best-single-agent comparisons with block-bootstrap tests. — [arXiv 2606.08283](https://arxiv.org/abs/2606.08283)

### Inferences
- **Baselines to beat, at minimum:**
  - buy-and-hold / SPY
  - a simple rules-based options strategy, e.g. a systematic covered call or put-write, or the CBOE BXM/PUT index analogues
  - the single best persona alone
  - all seven personas run on one model with no debate
- **Evaluate forward only.** Use paper trading after the models' training cutoffs, and log every decision with timestamps to be immutable, as ai-hedge-fund's ledger does.
- **Measure persona value by ablation:** drop one persona at a time and check whether the dissent and synthesis personas change decisions or just restate consensus. This guards against sycophantic collapse.
- **Budget for tokens.** Seven personas plus debate rounds per underlying per day multiplies cost. Use cheap models for data-summarizing personas and a strong model only for synthesis.

### Gaps
- I found no public example of a forked TradingAgents extended to options.
- I found no evidence about solo builders' real-money results with any of these frameworks.
