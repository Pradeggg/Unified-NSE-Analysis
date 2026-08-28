# Top Investment Picks Analysis — 2026-08-28

*Agent Adda - Market Intelligence Agent*

**Generated:** 2026-08-28 22:31 IST  
**Sources:** Sector Rotation Report + Stage 2 Tracker + Swing Research Shortlist + PostgreSQL `scores.*`, `market.equity_eod`

> **Disclaimer:** This report is not investment advice. It is a learning journey demonstrating how AI and rules-based agents can be applied to financial markets. Validate all data, prices, liquidity, corporate events, and risk independently before making any financial decision.

## Executive Summary

This equity basket is designed to capture growth opportunities primarily in high-conviction sectors such as Capital Goods, Pharma, and FMCG, reflecting the robust macro environment supporting industrial and consumer demand. With a notable presence in cyclical sectors like Metals & Mining alongside resilient sectors such as FMCG and Chemicals, the portfolio aims for a balanced approach to capitalize on both recovery and consistent performance themes. The biggest cross-cutting risk remains high valuations and potential cyclical slowdowns that could adversely affect earnings across multiple holdings, particularly in the Capital Goods and Metals sectors.

**Macro context:** Snapshot 2026-08-28: 2631 stocks scanned; Stage 2 count 402 vs Stage 4 481; BUY/STRONG_BUY signals 402; mean RS vs Nifty 500 50.1%.

**Data freshness:** Latest available market snapshot used for this report is **2026-08-28**; generation time may be later than the EOD data date.

## Methodology

Top picks are not selected from a single indicator. The report looks for names where market structure, sector strength, price action, strategy evidence, and risk/reward all point in the same direction.

### Core Inputs

1. **Sector Rotation Report** — finds leading sectors and the highest investment-score stocks inside those sectors.
2. **Stage 2 / VCP Tracker** — prioritises Weinstein Stage 2 stocks and persisted `scores.stage2_vcp_picks` candidates.
3. **Swing Research Shortlist** — promotes latest deep-research names only when current EOD Stage 2 and bullish trend evidence remain intact.
4. **Portfolio Strategy Lab** — gives extra weight to symbols confirmed by the best-ranked paper strategy's open positions or next BUY orders.
5. **Technical Strength** — uses 260 trading days of EOD data: EMA20/50/200 stack, EMA50 slope, RSI(14), ATR(14), 52-week position, 1M/3M/6M/1Y returns, volume ratio, support/resistance, pivots, and volume profile.
6. **Fundamental and Risk Checks** — uses Piotroski F-score, Altman Z, Beneish M, ROE/ROCE, 3-year growth, debt/equity, promoter holding, cash-flow quality, valuation, stop loss, targets, and risk/reward.

### Weinstein Stage Framework

Stan Weinstein's stage analysis is the primary trend filter:

- **Stage 1 — Base / Accumulation:** price moves sideways after a decline, moving averages flatten, and institutions may be accumulating. This is a watchlist phase, not the preferred buying phase.
- **Stage 2 — Advancing / Uptrend:** price breaks out of the base, trades above key moving averages, the 50-day average rises, and relative strength improves. This is the preferred long-only buying zone.
- **Stage 3 — Top / Distribution:** price becomes volatile near highs, momentum fades, and moving averages flatten. This is a caution or profit-protection phase.
- **Stage 4 — Decline / Downtrend:** price trades below key moving averages with lower highs/lows. Long-only systems usually avoid these names.

The report therefore gives first preference to **Stage 2 leaders**, especially where the stock also shows sector leadership, VCP/breakout evidence, and strategy confirmation.

### How Ranking Works

The final rank balances several signals rather than blindly chasing the strongest one-day mover:

- **Stage and trend quality:** Stage 2, rising averages, and strong 52-week positioning rank higher.
- **Relative strength:** stocks outperforming the broader universe rank higher.
- **Sector leadership:** strong stocks in strong sectors get preference over isolated moves.
- **VCP / breakout evidence:** a Volatility Contraction Pattern means a strong stock has paused with tighter ranges and reduced supply before a potential breakout.
- **Swing research overlay:** names from the latest deep-research shortlist are promoted only when the current EOD snapshot still confirms Stage 2 with bullish trend state, and research actions such as avoid/deprioritize are not promoted.
- **Portfolio strategy confirmation:** paper-trading strategies such as breakout or Darvas-style systems add independent confirmation when they mark the stock as an open position or next BUY.
- **Risk/reward:** targets, stop-loss distance, ATR volatility, and risk score prevent high-momentum but poor-risk trades from dominating the list.
- **Fundamental quality:** profitability, leverage, cash-flow quality, growth, and valuation checks reduce false positives.

Triple-confirmed names, where sector rotation + Stage 2/VCP + portfolio strategy evidence agree, are prioritised. Dual-confirmed names can still qualify when their trend, relative strength, and risk/reward are strong.

### How to Read the Picks

A high-ranked pick should be read as a research shortlist candidate, not a direct investment instruction. The strongest candidates typically combine Stage 2 structure, leadership versus the market, constructive sector context, defined stop-loss, and acceptable reward-to-risk. The report is for research and learning only; it is not investment advice.

## Pick Summary

| # | Symbol | Sector | Sub-sector | Price | Stage | Inv.Score | RS% | 6M Tgt | RR(4M) | Risk | Extension | Source |
|---|---|---|---|---:|---|---:|---:|---:|---:|:---:|:---:|---|
| 1 | **OMAXE** | Realty | Unmapped | 131.74 | STAGE_2 | 90.34 | 99.2% | ₹192 | 0.90x | 9.5 | OVEREXTENDED | strategy+sector+s2 |
| 2 | **JSWSTEEL** | Metals & Mining | Unmapped | 1334.90 | STAGE_2 | 77.67 | 48.5% | ₹1,709 | 1.63x | 2.0 | NORMAL | strategy+sector+s2 |
| 3 | **APARINDS** | Capital Goods & Industrials | Industrial Products | 17803.00 | STAGE_2 | 96.72 | 94.1% | ₹23,326 | 1.38x | 3.5 | EXTENDED | vcp+sector |
| 4 | **UNIPARTS** | Capital Goods & Industrials | Industrial Products | 873.15 | STAGE_2 | 97.96 | 96.4% | ₹1,086 | 0.99x | 5.5 | OVEREXTENDED | sector+s2 |
| 5 | **JGCHEM** | Chemicals & Petrochemicals | Unmapped | 651.30 | STAGE_2 | 96.97 | 97.0% | ₹915 | 1.35x | 5.0 | OVEREXTENDED | strategy |
| 6 | **MACPOWER** | Capital Goods | Unmapped | 2007.10 | STAGE_2 | 99.38 | 99.8% | ₹3,009 | 1.24x | 7.0 | OVEREXTENDED | sector+s2 |
| 7 | **IRISDOREME** | Textiles | Unmapped | 58.70 | STAGE_2 | 97.40 | 98.6% | ₹79 | 1.04x | 7.0 | OVEREXTENDED | sector+s2 |
| 8 | **VADILALIND** | Fast Moving Consumer Goods | Unmapped | 7900.00 | STAGE_2 | 96.08 | 97.1% | ₹10,893 | 1.29x | 4.0 | EXTENDED | sector+s2 |
| 9 | **LAURUSLABS** | Pharma & Healthcare | Pharma APIs & Formulations | 1938.50 | STAGE_2 | 96.18 | 94.4% | ₹2,223 | 0.67x | 4.5 | OVEREXTENDED | vcp |
| 10 | **RADICO** | FMCG & Consumer Goods | Unmapped | 4605.00 | STAGE_2 | 94.68 | 91.4% | ₹6,005 | 1.37x | 1.0 | NORMAL | vcp |

## Per-Stock Deep Dive

### 1. OMAXE — Realty / Unmapped

**Why selected:** Portfolio lab best strategy `vcp_breakout_v1` confirms as open position; current Stage 2 inv=90.3, top sector strength=96

**Portfolio lab confirmation:** `vcp_breakout_v1` (VCP Breakout, rank 1, 6.44% return) marks this as **open position**.

**What the company does:** Omaxe ltd. is in the business of developing real estate properties for residential, commercial and retail purposes with a presence across 27 cities in 8 states of India. It has undertaken various projects in the areas of contractual construction, township development, building of commercial complexes, multi-storied apartments, etc. [1] [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/OMAXE/*

**Thesis:** Omaxe Ltd. shows a bullish setup with a technical score of 86.55 and an RSI of 82.27, indicating strong momentum. The stock price is currently at ₹131.74, close to its 52-week high at ₹134 with a one-month price change of +53.85%. Despite a challenging revenue trajectory with a Jun 2026 revenue of ₹406.17 Cr and a net PAT loss of ₹1.3 Cr, current sector strength is robust at 81.18, and insider activity signals potential confidence from stakeholders.

**Technical view:** Omaxe is positioned in Stage 2 of its technical cycle, above all EMA lines, with a strong price rally noted. The stock is currently 1.90% from its 52-week high, suggesting continued upward momentum in a bullish market regime with a volume surge during price increases.

**Fundamental view:** The latest quarterly results show revenues grew by 16.54% QoQ, although PAT reflects a drastic decline at -100.68% QoQ. The balance sheet shows rising debt, with borrowings increasing to ₹1,466 Cr, showcasing a weak interest coverage indicated by an OCF/PAT ratio of -0.42.

**Sector view:** Omaxe operates in a resilient sector with a strength of 81.18 and ranks favorably with 45 peers, supported by high institutional backing (68.5%).

**Valuation:** Current price-to-operating profit metrics suggest a stretch in valuation context given its persistent losses.

**Key catalysts:**
- Sector strength at 81.18
- 1M price increase of 53.85%
- Recent bullish technical patterns observed

**Key risks:**
- High debt growth with ₹670.0 Cr increase recently
- Negative operating profit margins at -57.94%
- Ongoing PAT losses could deter investment interest

**Research observation:** The stock shows potential as recovery efforts in a bullish market may align with constructive technical patterns.

**Model ref targets:** 2M ₹157 · 4M ₹175 · 6M ₹192 _(model reference only)_  
**Model inv. level:** ₹84 · **Reward/Risk (4M):** 0.90x  
**Risk score:** 9.5 / 10 (HIGH) · **Illustrative weight:** 3% _(not a personal allocation recommendation)_  
**Extension:** OVEREXTENDED — 30.3% above EMA20; 42.0% above EMA50; RSI 82; -1.9% from 52w high; 1M return +53.8%. Do not chase; prefer pullback toward EMA20/base reset or staged entry only.

**Conviction:** **MEDIUM** — While bullish signals exist, financial health concerns temper conviction.

**Snapshot:**

- Price ₹131.74 · 1D 16.2% · 1W 28.5% · 1M 53.8%
- Stage **STAGE_2** (score 99.51) · Stance **BULLISH** · Signal **BUY**
- Investment score 90.34 (tech 86.55, fund 64.61)
- Relative Strength 99.2% vs Nifty 500; Supertrend BULLISH around ₹97.47

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹131.74 |
| EMA 20 / 50 / 200 | ₹101.14 / ₹92.78 / ₹83.52 |
| EMA50 slope (20d) | 9.96% |
| RSI(14) | 82.27 |
| ATR(14) | ₹8.57 (6.50%) |
| 52W High / Low | ₹134.30 / ₹62.50 |
| Distance from 52W high | -1.9% |
| Returns 1M / 3M / 6M / 1Y | 53.8% / 71.4% / 69.8% / 47.1% |
| Last-day volume vs 20d avg | 5.18x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | -35.0% |
| ROCE | -10.6% |
| Debt / Equity | — |
| Promoter holding | 74.1% |

---

### 2. JSWSTEEL — Metals & Mining / Unmapped

**Why selected:** Portfolio lab best strategy `vcp_breakout_v1` confirms as open position; current Stage 2 inv=77.7, top sector strength=103

**Portfolio lab confirmation:** `vcp_breakout_v1` (VCP Breakout, rank 1, 6.44% return) marks this as **open position**.

**What the company does:** JSW Steel is primarily engaged in the business of manufacture and sale of Iron and Steel Products. [1] It is the flagship business of the diversified, US$ 23 billion JSW Group.The Group has interests in energy, infrastructure, cement, paints, sports, and venture capital. [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/JSWSTEEL/*

**Thesis:** JSW Steel boasts a robust growth profile with consistent revenue of ₹51,180 Cr for Mar 2026 and PAT of ₹19,243 Cr in the latest quarter. The stock holds an investment score of 77.67 and shows an RSI of 63.41, which reflects a bullish trend amid a supportive sector strength of 88.31. With a trailing 12-month EPS of ₹101.35 and recent PAT growth of 112.58% YoY, it shows potential for continued upward momentum.

**Technical view:** JSW Steel is in Stage 2 of its recovery, highlighted by 20/50/200 EMA alignment. Market action reveals the stock is only 1.19% away from its 52-week high, with volumes remaining stable at 79.70% of the 20-day average.

**Fundamental view:** The company's balance sheet is healthy with borrowings at ₹99,310 Cr and equity at ₹100,053 Cr, suggesting a manageable net debt position. OCF demonstrates strong operational performance at ₹25,152 Cr relative to PAT, leading to a favorable OCF/PAT ratio of 0.90, reflective of high earnings quality.

**Sector view:** In the metals and mining sector with a strength of 88.31, JSW is well-positioned among peers, continually outperforming with strong institutional backing at 76%.

**Valuation:** The current P/E at 27.1 suggests sustainable growth prospects; however, given sector fluctuations, valuation may be on the richer side.

**Key catalysts:**
- Strong revenue growth of 9.77% YoY
- PAT performance reflecting a robust increase of 112.58% YoY
- Solid balance sheet with a D/E ratio around 0.99

**Key risks:**
- Cyclical exposure could lead to revenue variability
- Increased competition may compress margins
- Rising debt levels of ₹99,310 Cr could impact liquidity

**Research observation:** JSW Steel's commitment to operational efficiency should be observed, supported by positive analyst sentiments and strong sector positioning.

**Model ref targets:** 2M ₹1,408 · 4M ₹1,486 · 6M ₹1,709 _(model reference only)_  
**Model inv. level:** ₹1,242 · **Reward/Risk (4M):** 1.63x  
**Risk score:** 2.0 / 10 (LOW) · **Illustrative weight:** 8% _(not a personal allocation recommendation)_  
**Extension:** NORMAL — -1.2% from 52w high. Extension is not the main risk flag; standard staged entry rules apply.

**Conviction:** **HIGH** — Strong revenue momentum and institutional support enhance conviction.

**Snapshot:**

- Price ₹1334.90 · 1D -0.2% · 1W 3.2% · 1M 5.0%
- Stage **STAGE_2** (score 86.96) · Stance **BULLISH** · Signal **BUY**
- Investment score 77.67 (tech 90.15, fund 64.75)
- Relative Strength 48.5% vs Nifty 500; Supertrend BULLISH around ₹1263.22

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹1334.90 |
| EMA 20 / 50 / 200 | ₹1300.69 / ₹1280.58 / ₹1221.23 |
| EMA50 slope (20d) | 2.22% |
| RSI(14) | 63.41 |
| ATR(14) | ₹24.39 (1.83%) |
| 52W High / Low | ₹1351.00 / ₹1022.30 |
| Distance from 52W high | -1.2% |
| Returns 1M / 3M / 6M / 1Y | 5.0% / 1.8% / 4.2% / 27.5% |
| Last-day volume vs 20d avg | 0.80x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 44.3% |

---

### 3. APARINDS — Capital Goods & Industrials / Industrial Products

**Why selected:** VCP-confirmed Stage 2 (vcp=84, inv=96.7) in top-ranked sector Capital Goods & Industrials (strength=87)

**What the company does:** Apar, founded by Mr. Dharmsinh D. Desai in 1958, is a market leader in India with a global presence. Contributing to India’s process of electrification it started from manufacturing power transmission cables to having three broad business segments, which are Conductors, Transformer and specialty oils (TSO), and Power/telecom Cables. [1] [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/APARINDS/*

**Thesis:** Apar Industries is positioned strongly within its sector with a trading price of ₹17,803.00 and significant long-term growth metrics. The stock has a technical score at 97.85, RSI at 65.61, and has demonstrated a strong EPS growth of 294.12% YoY, reinforcing a bullish trend for this capital goods company.

**Technical view:** With all EMA alignments displaying bullish configurations, and the stock just 3.58% off its 52-week high, the setup is primed for bullish action and further advancements.

**Fundamental view:** Latest quarterly results indicate revenue growth, with ₹6,591 Cr in Jun 2026 alongside a PAT growth of 77.57% YoY. The balance sheet appears steady with equity at ₹5,393 Cr, signifying low leverage.

**Sector view:** Operating in a robust capital goods sector with a strength of 82.4 and high ratings from peers, Apar Industries is favorably placed in its market.

**Valuation:** Apar trades with a high P/E of around 61.8, suggesting a premium valuation relative to earnings, highlighting investor optimism despite potential overvaluation.

**Key catalysts:**
- High technical score at 97.85
- Strong EPS growth of 294.12% YoY
- Robust cash flow generation with OCF at ₹968 Cr

**Key risks:**
- Valuation pressures from high P/E ratio
- Market downturns affecting order flow
- Operational risk due to commodity price volatility

**Research observation:** Apar Industries presents a favorable technical and fundamental backdrop amid solid sector performance, meriting careful monitoring.

**Model ref targets:** 2M ₹20,080 · 4M ₹21,598 · 6M ₹23,326 _(model reference only)_  
**Model inv. level:** ₹15,055 · **Reward/Risk (4M):** 1.38x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Illustrative weight:** 5% _(not a personal allocation recommendation)_  
**Extension:** EXTENDED — 7.3% above EMA20; 14.7% above EMA50; 1M return +29.5%. Buy only on controlled pullback or tight base; keep size capped.

**Conviction:** **MEDIUM** — Healthy growth metrics support a reasonable conviction stance amid higher valuation risks.

**Snapshot:**

- Price ₹17803.00 · 1D -0.5% · 1W 5.6% · 1M 29.5%
- Stage **STAGE_2** (score 97.99) · Stance **BULLISH** · Signal **BUY**
- Investment score 96.72 (tech 97.85, fund 75.60)
- Relative Strength 94.1% vs Nifty 500; Supertrend BULLISH around ₹15780.60

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹17803.00 |
| EMA 20 / 50 / 200 | ₹16594.61 / ₹15520.60 / ₹12224.12 |
| EMA50 slope (20d) | 11.56% |
| RSI(14) | 65.61 |
| ATR(14) | ₹759.00 (4.26%) |
| 52W High / Low | ₹18465.00 / ₹6801.00 |
| Distance from 52W high | -3.6% |
| Returns 1M / 3M / 6M / 1Y | 29.5% / 34.2% / 64.7% / 125.9% |
| Last-day volume vs 20d avg | 0.67x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 55.4% |

---

### 4. UNIPARTS — Capital Goods & Industrials / Industrial Products

**Why selected:** Stage 2 leader in top sector Capital Goods & Industrials (strength=87), inv=98.0

**What the company does:** Incorporatedin1994, Uniparts India provides engineering systems and solutions catering to international OEMs across the off-highway vehicle, agricultural machinery, and construction equipment sectors [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/UNIPARTS/*

**Thesis:** Uniparts India is showing strong technical momentum with a bullish stance supported by an RSI of 69.60 and an EMA stack indicating a solid uptrend. The company has demonstrated a 26.64% YoY revenue growth and a PAT CAGR of 67.65%, underscoring its operational efficiency with an OPM trend up by 516 bps. With a healthy financial strength score of 82.5 and low net debt of ₹-50 Cr, the balance sheet supports continued expansion.

**Technical view:** The stock is currently at a heightened technical stage with a trend confirmed by the EMA20 above the EMA50 and EMA200. It is approximately 0.76% away from its 52-week high of ₹880 and has recently exhibited strong volume support, near double the 20-day average.

**Fundamental view:** In the latest quarter, Uniparts reported a revenue of ₹347 Cr alongside a PAT of ₹57 Cr, reflecting a remarkable PAT QoQ growth of 11.76%. The balance sheet remains solid with increasing equity and a strong debt management profile, evidenced by a computed debt-to-equity ratio of approximately 0.18.

**Sector view:** The Capital Goods & Industrials sector is currently strong with a sector strength score of 82.4, positioning Uniparts favorably against its peers in the context of the broader market.

**Valuation:** The stock displays a P/E of 21.5, which appears reasonable given its growth metrics when compared to sector averages.

**Key catalysts:**
- Latest quarterly revenue of ₹347 Cr, up 26.64% YoY
- Strong OPM of 24.0%
- Institutional backing score of 73.5 indicating robust support

**Key risks:**
- Cyclical nature of capital goods market
- Potential margin compression
- Increased debt levels over time

**Research observation:** The current technical and fundamental condition suggests a favorable long-term outlook, although caution is advised given elevated valuations.

**Model ref targets:** 2M ₹964 · 4M ₹1,025 · 6M ₹1,086 _(model reference only)_  
**Model inv. level:** ₹719 · **Reward/Risk (4M):** 0.99x  
**Risk score:** 5.5 / 10 (MEDIUM) · **Illustrative weight:** 3% _(not a personal allocation recommendation)_  
**Extension:** OVEREXTENDED — 9.1% above EMA20; 17.8% above EMA50; RSI 70; -0.8% from 52w high; 1M return +18.3%. Do not chase; prefer pullback toward EMA20/base reset or staged entry only.

**Conviction:** **HIGH** — Strong growth metrics and favorable sector context validate high conviction.

**Snapshot:**

- Price ₹873.15 · 1D 8.0% · 1W 7.1% · 1M 18.3%
- Stage **STAGE_2** (score 98.98) · Stance **BULLISH** · Signal **BUY**
- Investment score 97.96 (tech 98.64, fund 72.51)
- Relative Strength 96.4% vs Nifty 500; Supertrend BULLISH around ₹747.08

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹873.15 |
| EMA 20 / 50 / 200 | ₹799.97 / ₹741.24 / ₹591.76 |
| EMA50 slope (20d) | 13.15% |
| RSI(14) | 69.61 |
| ATR(14) | ₹30.40 (3.48%) |
| 52W High / Low | ₹879.80 / ₹391.80 |
| Distance from 52W high | -0.8% |
| Returns 1M / 3M / 6M / 1Y | 18.3% / 45.7% / 87.4% / 114.1% |
| Last-day volume vs 20d avg | 1.96x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 65.9% |

---

### 5. JGCHEM — Chemicals & Petrochemicals / Unmapped

**Why selected:** Portfolio lab best strategy `vcp_breakout_v1` confirms as next buy; current Stage 2 inv=97.0

**Portfolio lab confirmation:** `vcp_breakout_v1` (VCP Breakout, rank 1, 6.44% return) marks this as **next buy**.

**What the company does:** Incorporated in 2001, J.G Chemicals is a leading Zinc Oxide Manufacturer having the capability to produce up to 80 grades of Zinc oxide [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/JGCHEM/*

**Thesis:** J.G Chemicals shows strong technical patterns with an RSI of 66.65 backing its continuing uptrend. The company has achieved a 44.95% YoY revenue growth and a PAT CAGR of 8.24% indicating operational resilience. Financial backing is strong, with a notable institutional support score of 68.5 and a robust promoter holding of 70.99%. Overall, these factors highlight JGCHEM's positive outlook within the chemical sector.

**Technical view:** The stock is positioned bullishly with both EMA20 and EMA50 trending above the EMA200. It stands just 3.51% off its 52-week high, suggesting strong momentum, and a volume surge was noted at a 5.9x increase over the 20-day average.

**Fundamental view:** The company reported a quarterly revenue growth of 44.95% YoY and a PAT of ₹26 Cr, showcasing a healthy operating profit margin of 11%. The balance sheet reflects a stable trend with net cash of ₹-130 Cr, coupled with an operating cash flow ratio of 0.564.

**Sector view:** Operating within a chemicals sector that has a strength score of 54.04, JGCHEM is among the strong performers against its relatively limited peer group.

**Valuation:** The P/E of 34 indicates a premium valuation compared to industry peers yet reflects growth narratives.

**Key catalysts:**
- Latest quarterly revenue of ₹316 Cr, up 44.95% YoY
- PAT QoQ increase of 36.84%
- High promoter ownership at 70.99%

**Key risks:**
- Market volatility
- Operational risks in production
- Valuation concerns given high multiples

**Research observation:** JGCHEM currently shows promising growth and technical patterns, although caution over market valuation is warranted.

**Model ref targets:** 2M ₹764 · 4M ₹840 · 6M ₹915 _(model reference only)_  
**Model inv. level:** ₹512 · **Reward/Risk (4M):** 1.35x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Illustrative weight:** 3% _(not a personal allocation recommendation)_  
**Extension:** OVEREXTENDED — 10.9% above EMA20; 22.8% above EMA50; 1M return +32.5%. Do not chase; prefer pullback toward EMA20/base reset or staged entry only.

**Conviction:** **MEDIUM** — While growth metrics are strong, the valuation presents a cautionary note.

**Snapshot:**

- Price ₹651.30 · 1D 11.2% · 1W 4.7% · 1M 32.5%
- Stage **STAGE_2** (score 98.72) · Stance **BULLISH** · Signal **BUY**
- Investment score 96.97 (tech 96.96, fund 77.36)
- Relative Strength 97.0% vs Nifty 500; Supertrend BULLISH around ₹537.54

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹651.30 |
| EMA 20 / 50 / 200 | ₹587.29 / ₹530.54 / ₹445.33 |
| EMA50 slope (20d) | 18.69% |
| RSI(14) | 66.65 |
| ATR(14) | ₹37.68 (5.79%) |
| 52W High / Low | ₹675.00 / ₹298.40 |
| Distance from 52W high | -3.5% |
| Returns 1M / 3M / 6M / 1Y | 32.5% / 51.0% / 83.7% / 36.7% |
| Last-day volume vs 20d avg | 4.56x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 71.0% |

---

### 6. MACPOWER — Capital Goods / Unmapped

**Why selected:** Stage 2 leader in top sector Capital Goods (strength=91), inv=99.4

**What the company does:** Macpower CNC Machines Limited is engaged in the manufacture of Computerized Numerically Controlled (CNC) machines and Lathe Machines. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/MACPOWER/*

**Thesis:** Macpower CNC Machines is on a strong bullish trajectory, confirmed by an RSI of 69.50 and strong price performance resulting in a 35.51% increase in the last month alone. The financials reflect robust growth with 56.05% YoY revenue increase and a PAT CAGR of 31.61%, backed by improving OPM trends. Low debt levels with net debt at ₹1 Cr illustrate healthy leverage conditions, supporting long-term expansion.

**Technical view:** The technical setup is very bullish with EMA20 above EMA50 and a price near only 2.09% off its 52-week high of ₹2050. A recent volume surge indicated institutional involvement, with trading volume at 1.57x the 20-day average.

**Fundamental view:** The latest quarter indicates strong financial performance with revenue of ₹95.24 Cr and a PAT of ₹9.58 Cr, demonstrating a healthy operating margin at 16.19%. The cash flow generation is positive, although the OCF/PAT ratio is 0.36, requiring attention to cash management.

**Sector view:** With a significant sector strength score of 90.54 in Capital Goods, Macpower stands out among its peers, enhancing its competitive landscape.

**Valuation:** The P/E ratio of 51.6 indicates higher valuation compared to historical standards, presenting potential near-term risk without substantial growth.

**Key catalysts:**
- Latest quarterly revenue of ₹95.24 Cr
- PAT growth of 110% YoY
- Strong promoter holding of 73.22%

**Key risks:**
- High valuation metrics
- Cyclical market dependence
- Potentially high operational costs

**Research observation:** Macpower is in a favorable location for growth, although technical readiness at current levels suggests prudent positioning.

**Model ref targets:** 2M ₹2,373 · 4M ₹2,617 · 6M ₹3,009 _(model reference only)_  
**Model inv. level:** ₹1,516 · **Reward/Risk (4M):** 1.24x  
**Risk score:** 7.0 / 10 (HIGH) · **Illustrative weight:** 3% _(not a personal allocation recommendation)_  
**Extension:** OVEREXTENDED — 12.4% above EMA20; 28.4% above EMA50; RSI 69; -2.1% from 52w high; 1M return +35.5%. Do not chase; prefer pullback toward EMA20/base reset or staged entry only.

**Conviction:** **MEDIUM** — Supported by strong growth trends yet tempered by high valuation concerns.

**Snapshot:**

- Price ₹2007.10 · 1D 7.4% · 1W 7.1% · 1M 35.5%
- Stage **STAGE_2** (score 99.63) · Stance **BULLISH** · Signal **BUY**
- Investment score 99.38 (tech 99.20, fund 50.27)
- Relative Strength 99.8% vs Nifty 500; Supertrend BULLISH around ₹1606.96

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹2007.10 |
| EMA 20 / 50 / 200 | ₹1785.26 / ₹1563.09 / ₹1181.95 |
| EMA50 slope (20d) | 24.71% |
| RSI(14) | 69.50 |
| ATR(14) | ₹121.91 (6.07%) |
| 52W High / Low | ₹2050.00 / ₹761.00 |
| Distance from 52W high | -2.1% |
| Returns 1M / 3M / 6M / 1Y | 35.5% / 115.5% / 100.1% / 145.8% |
| Last-day volume vs 20d avg | 1.57x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 73.2% |

---

### 7. IRISDOREME — Textiles / Unmapped

**Why selected:** Stage 2 leader in top sector Textiles (strength=93), inv=97.4

**What the company does:** IRIS Clothings Limited, incorporated in 1956, is engaged in designing, manufacturing, branding and selling garments for kids. [1] Iris Clothings Limited is a fast-growing readymade garment company and is engaged in designing, manufacturing, branding and selling garments for kids wear under the brand name DOREME in India. It produces a broad range of unique apparels for infants, toddlers and junior boys and girls.

*Company profile source: screener.in (live) — https://www.screener.in/company/IRISDOREME/*

**Thesis:** IRIS Clothings Ltd exhibits strong short-term technical performance with an RSI of 71.82, confirming its bullish stage with a price change of +18.3% over the past month. Despite a recent quarterly revenue decline of 21.89% QoQ, the year-on-year revenue growth remains healthy at +26.31%. PAT shows a robust growth of +52.47% YoY, and the company demonstrates a solid financial strength with an equity to debt ratio of 4.18, providing a cushion against downturns.

**Technical view:** IRISDOREME is currently above its EMA20 and EMA50, with the moving average convergence suggesting ongoing strength. It is just 2.49% below its 52-week high, reflecting a strong momentum with a recent +18.28% monthly return.

**Fundamental view:** In the latest quarter (Jun 2026), revenue was ₹47.24 Cr with a PAT of ₹4.01 Cr, signaling an operational improvement given the preceding quarters. The company sustained a positive OCF in FY Mar 2025 at ₹3.0 Cr, but recent cash flow quality appears weak with an OCF/PAT ratio of -0.39, indicating potential liquidity issues going forward.

**Sector view:** Aligned with a strong textiles sector strength score of 92.51, IRISDOREME holds a solid position among its 80 sector peers, with an RS of 98.64% versus the Nifty 500.

**Valuation:** While the stock’s P/E at 63.6 suggests a stretch in valuation relative to earnings, its revenue growth trajectory supports a premium multiple.

**Key catalysts:**
- PAT CAGR 22.47%
- Op margin increase of 97 bps QoQ
- Promoter holding at 61.17%

**Key risks:**
- Negative cash flow with OCF at -₹7.0 Cr
- High valuation relative to earnings at a P/E of 63.6
- Potential operational volatility due to competitive pressures

**Research observation:** IRISDOREME shows strong uptrend momentum with supportive technicals and sector strength, despite facing cash-flow challenges.

**Model ref targets:** 2M ₹65 · 4M ₹69 · 6M ₹79 _(model reference only)_  
**Model inv. level:** ₹49 · **Reward/Risk (4M):** 1.04x  
**Risk score:** 7.0 / 10 (HIGH) · **Illustrative weight:** 3% _(not a personal allocation recommendation)_  
**Extension:** OVEREXTENDED — 15.9% above EMA50; RSI 72; -2.5% from 52w high; 1M return +18.3%. Do not chase; prefer pullback toward EMA20/base reset or staged entry only.

**Conviction:** **HIGH** — Strong technical and sector performance offset by liquidity risks.

**Snapshot:**

- Price ₹58.70 · 1D 1.3% · 1W 3.0% · 1M 18.3%
- Stage **STAGE_2** (score 99.29) · Stance **BULLISH** · Signal **BUY**
- Investment score 97.40 (tech 96.87, fund 56.27)
- Relative Strength 98.6% vs Nifty 500; Supertrend None around ₹—

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹58.70 |
| EMA 20 / 50 / 200 | ₹56.00 / ₹50.66 / ₹40.37 |
| EMA50 slope (20d) | 18.29% |
| RSI(14) | 71.82 |
| ATR(14) | ₹1.99 (3.39%) |
| 52W High / Low | ₹60.20 / ₹26.35 |
| Distance from 52W high | -2.5% |
| Returns 1M / 3M / 6M / 1Y | 18.3% / 64.8% / 76.5% / 84.0% |
| Last-day volume vs 20d avg | 0.28x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 61.2% |

---

### 8. VADILALIND — Fast Moving Consumer Goods / Unmapped

**Why selected:** Stage 2 leader in top sector Fast Moving Consumer Goods (strength=90), inv=96.1

**What the company does:** Vadilal was started as a soda company in 1907, the founder Vadilal Gandhi used to make ice cream by the traditional Kothi method. Vadilal Gandhi passed on the business to his son, Ranchod Lal Gandhi, who ran a one-man operation with a hand-cranked machine, started a small retail outlet in 1926. [1] The Company is engaged in the business of manufacturing Ice-cream, Frozen Dessert, Juicy, and Candy and processing and exporting Processed Food products, such as Frozen Fruits and Vegetables, Canned Fruit Pulp.

*Company profile source: screener.in (live) — https://www.screener.in/company/VADILALIND/*

**Thesis:** Vadilal Industries demonstrates a robust technical profile as indicated by a very high investment score of 96.08 and an RSI of 71.34, alongside a stable annual growth with a revenue CAGR of 12.19%. The latest quarterly revenue reached ₹680 Cr, showcasing a solid QoQ revenue growth of 63.46% and a substantial PAT growth of 138.18%. The company also maintains a healthy OPM of 24% in the latest quarter and a strong earnings quality score of 88.0%, reflecting a solid operational foundation.

**Technical view:** With current price levels testing near the EMA20 and EMA50, Vadilal markets itself as technically positioned well within a bullish formation. The RSI of 71 does suggest an overbought condition yet reflects strong buyer interest.

**Fundamental view:** The latest result showed increased revenue to ₹680 Cr with PAT growing to ₹131 Cr, leading to an impressive OPM of 24%. Vadilal’s debt management seems efficient with a computed debt ratio of 0.27 and a positive OCF of ₹143 Cr, although cash flow generation remains a focus area for ongoing operations.

**Sector view:** Vadilal operates in the FMCG space, which has a solid score of 89.71 in sector strength, placing it in the upper percentile among competitors in the industry.

**Valuation:** Current valuation at a P/E of 25.9 is moderate relative to peers and justified given the earnings momentum in past quarters.

**Key catalysts:**
- PAT growth of 138.18% QoQ
- Revenue growth of 34.12% YoY
- Strong institutional backing with 63.5% score

**Key risks:**
- Overvaluation potential if growth slows
- Rising costs affecting margins
- Market competitiveness leading to revenue uncertainties

**Research observation:** Vadilal Industries is positioned for potential growth driven by solid technical indicators and robust quarterly results, warranting close monitoring of market dynamics.

**Model ref targets:** 2M ₹8,843 · 4M ₹9,472 · 6M ₹10,893 _(model reference only)_  
**Model inv. level:** ₹6,686 · **Reward/Risk (4M):** 1.29x  
**Risk score:** 4.0 / 10 (MEDIUM) · **Illustrative weight:** 5% _(not a personal allocation recommendation)_  
**Extension:** EXTENDED — 7.1% above EMA20; 14.6% above EMA50; RSI 71. Buy only on controlled pullback or tight base; keep size capped.

**Conviction:** **MEDIUM** — Good technicals and earnings momentum tempered by competitive risks.

**Snapshot:**

- Price ₹7900.00 · 1D 6.1% · 1W 6.5% · 1M 8.8%
- Stage **STAGE_2** (score 98.30) · Stance **BULLISH** · Signal **BUY**
- Investment score 96.08 (tech 95.66, fund 81.64)
- Relative Strength 97.1% vs Nifty 500; Supertrend BULLISH around ₹7041.15

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹7900.00 |
| EMA 20 / 50 / 200 | ₹7378.53 / ₹6892.40 / ₹5811.62 |
| EMA50 slope (20d) | 10.97% |
| RSI(14) | 71.34 |
| ATR(14) | ₹314.43 (3.98%) |
| 52W High / Low | ₹8447.00 / ₹3996.00 |
| Distance from 52W high | -6.5% |
| Returns 1M / 3M / 6M / 1Y | 8.8% / 46.7% / 61.8% / 59.9% |
| Last-day volume vs 20d avg | 1.07x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 64.7% |

---

### 9. LAURUSLABS — Pharma & Healthcare / Pharma APIs & Formulations

**Why selected:** VCP-confirmed Stage 2 (vcp=91, inv=96.2); sector Pharma & Healthcare not in current top-10 rotation

**What the company does:** Founded in 2005, Laurus Labs is a research-driven pharmaceutical and biotechnology company having a global leadership position in select Active Pharmaceutical Ingredients (APIs) including anti-retroviral, oncology drugs (including High Potent APIs), Cardiovascular, and Gastro therapeutics. They also offer integrated CMO and CDMO services to Global Innovators from Clinical phase drug development to commercial manufacturing. Laurus employs 6,500+ people, including around 1,050+ scientists, at more than 11 facilities.

*Company profile source: screener.in (live) — https://www.screener.in/company/LAURUSLABS/*

**Thesis:** Laurus Labs is benefiting from a robust technical backdrop, indicated by an RSI of 74.76 and strong momentum reflected in recent price performance (+123.16% YoY). The company showcases a stable revenue base with TTM revenue of ₹7270 Cr and recent quarterly revenue growth of 11.81% QoQ. Critical operational metrics demonstrate efficiency with a high OPM of 32% in the latest results, elevating its competitive positioning in the pharma sector.

**Technical view:** With price currently situated at an all-time high and just at the EMA20, the stock is revealing clear upward momentum marked by the technicals. An RSI of 74.76 suggests optimism among investors, although it also hints at overbought conditions.

**Fundamental view:** The latest quarter showed revenue of ₹2026 Cr and a PAT of ₹362 Cr, with the company achieving a 28.36% increase in PAT QoQ, signaling effective cost management. The firm’s OCF was notably strong at ₹1624 Cr, yielding an OCF/PAT ratio of 1.49, indicating solid cash generation.

**Sector view:** Operating within the pharma subsector, which scores 83.36 in sector strength, Laurus is well-positioned amid strong industry fundamentals acting as a tailwind relative to peers.

**Valuation:** Valuation remains stretched with a P/E of 96.3; however, given the high growth rates and improved margins, it aligns with expected industry standards.

**Key catalysts:**
- PAT growth of +28.37% QoQ
- Introduction of new product lines
- Robust institutional backing with 76.0% score

**Key risks:**
- Valuation pressure if growth decelerates
- Currency fluctuations impacting exports
- Regulatory hurdles in the pharma space

**Research observation:** Laurus Labs is in a strong position due to its technical setup and consistent financial growth, although management must remain vigilant regarding any external market impacts.

**Model ref targets:** 2M ₹2,058 · 4M ₹2,137 · 6M ₹2,223 _(model reference only)_  
**Model inv. level:** ₹1,641 · **Reward/Risk (4M):** 0.67x  
**Risk score:** 4.5 / 10 (MEDIUM) · **Illustrative weight:** 3% _(not a personal allocation recommendation)_  
**Extension:** OVEREXTENDED — 6.3% above EMA20; 14.6% above EMA50; RSI 75; new 52w high +0.0%. Do not chase; prefer pullback toward EMA20/base reset or staged entry only.

**Conviction:** **MEDIUM** — Significant operational efficiency matched with potential regulatory risks.

**Snapshot:**

- Price ₹1938.50 · 1D 0.5% · 1W 7.6% · 1M 8.8%
- Stage **STAGE_2** (score 98.60) · Stance **BULLISH** · Signal **BUY**
- Investment score 96.18 (tech 96.95, fund 81.72)
- Relative Strength 94.4% vs Nifty 500; Supertrend BULLISH around ₹1805.47

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹1938.50 |
| EMA 20 / 50 / 200 | ₹1823.64 / ₹1691.98 / ₹1314.19 |
| EMA50 slope (20d) | 12.59% |
| RSI(14) | 74.76 |
| ATR(14) | ₹39.71 (2.05%) |
| 52W High / Low | ₹1938.50 / ₹823.10 |
| Distance from 52W high | 0.0% |
| Returns 1M / 3M / 6M / 1Y | 8.8% / 40.2% / 77.4% / 123.2% |
| Last-day volume vs 20d avg | 1.14x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 27.5% |

---

### 10. RADICO — FMCG & Consumer Goods / Unmapped

**Why selected:** VCP-confirmed Stage 2 (vcp=87, inv=94.7); sector FMCG & Consumer Goods not in current top-10 rotation

**What the company does:** Incorporated in the year 1943, Radico Khaitan is one of the most recognised IMFL (Indian Made Foreign Liquor) brands in India. [1] The company was initially known as Rampur Distillery Company and was focussed on distillation and bottling for branded players and canteen stores of armed forces. Later on in the year 1997, Radico Khaitan ventured into its own branded IMFL products and launched its first brand 8PM whisky which became its millionarie brand within a year of its launch. [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/RADICO/*

**Thesis:** Radico Khaitan is positioned strongly with a current price of ₹4605 and a robust RSI of 61.85. The company’s latest quarterly revenue saw a QoQ uptick of 11.97%, while PAT surged 28.49%, highlighting excellent earnings momentum. With a significantly improved financial profile reflected in a net debt reduction from ₹552 Cr to ₹258 Cr over three years and a solid OCF/PAT ratio of 1.06, Radico maintains a healthy balance sheet. The stock is also showing great technical strength, confirmed by a Stage 2 score of 97.41 and a technical score of 96.08.

**Technical view:** The current bullish setup is reinforced by the EMA stack with EMA20 above EMA50 and EMA200. The price is merely 2.99% off its 52-week high, indicating strong momentum. The RSI near the 61.85 level supports ongoing bullish tendencies while the distance from the average volume observed over the past 20 days is approximately 0.46 times, suggesting reduced volatility.

**Fundamental view:** The company reported revenue of ₹1684 Cr in Jun 2026 with a PAT of ₹230 Cr, reflecting a notable OPM improvement of 210 bps QoQ to 21%. The 3-year balance sheet trend indicates decreasing debt levels which enhances financial stability, while the 4-year EPS CAGR stands at 33.62%, showcasing strong profitability trends.

**Sector view:** In the context of the FMCG & Consumer Goods sector, Radico exhibits strength with a sector strength of 76.79 and ranks above its peers with an average RS percentile of 80.42, reflecting market leadership.

**Valuation:** The stock appears to be on the higher side of valuation metrics with a P/E of 86.8. Given the EPS CAGR of 33.62%, there seems to be underlying growth potential that may justify this multiple.

**Key catalysts:**
- Strong revenue growth with revenue YoY growth at 11.82%
- Decreasing net debt trend with a computed debt ratio of 0.15
- Significant EPS CAGR of 33.62% over the last four years

**Key risks:**
- Potential for earnings disappointments if growth tapers
- Sector-wide economic slowdown impacting consumer spending
- Reliance on promotional pricing strategies

**Research observation:** The current setup suggests a technically healthy and fundamentally sound investment; however, market participants should remain cautious of broader economic influences and technical patterns indicating potential resistance.

**Model ref targets:** 2M ₹4,862 · 4M ₹5,222 · 6M ₹6,005 _(model reference only)_  
**Model inv. level:** ₹4,154 · **Reward/Risk (4M):** 1.37x  
**Risk score:** 1.0 / 10 (LOW) · **Illustrative weight:** 8% _(not a personal allocation recommendation)_  
**Extension:** NORMAL — -3.0% from 52w high. Extension is not the main risk flag; standard staged entry rules apply.

**Conviction:** **HIGH** — Radico Khaitan's strong financial and operational metrics coupled with positive technical trends foster a high level of conviction in maintaining an openness to investment.

**Snapshot:**

- Price ₹4605.00 · 1D -0.0% · 1W -0.8% · 1M 5.5%
- Stage **STAGE_2** (score 97.41) · Stance **BULLISH** · Signal **BUY**
- Investment score 94.68 (tech 96.08, fund 81.13)
- Relative Strength 91.4% vs Nifty 500; Supertrend BULLISH around ₹4431.24

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-28) | ₹4605.00 |
| EMA 20 / 50 / 200 | ₹4552.12 / ₹4282.49 / ₹3573.57 |
| EMA50 slope (20d) | 10.20% |
| RSI(14) | 61.85 |
| ATR(14) | ₹85.51 (1.86%) |
| 52W High / Low | ₹4747.00 / ₹2500.00 |
| Distance from 52W high | -3.0% |
| Returns 1M / 3M / 6M / 1Y | 5.5% / 32.0% / 70.5% / 58.1% |
| Last-day volume vs 20d avg | 0.46x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | — |
| ROCE | — |
| Debt / Equity | — |
| Promoter holding | 40.2% |

---

## Portfolio Construction

The portfolio is constructed with an overweight position in HIGH conviction stocks, allocating approximately 30% to standout names like JSWSTEEL and UNIPARTS that manifest strong growth momentum and robust fundamentals. MEDIUM conviction stocks will be allocated about 20%, capturing growth while maintaining some caution against overvaluation or market corrections. The remaining allocations will include a blend of lower-weight positions in the MEDIUM conviction category, roughly 10-15% for stocks like IRISDOREME and LAURUSLABS. Sector cap limits are established at 25% for any single sector to mitigate concentration risk, with a moderate cash buffer of around 10% to take advantage of market fluctuations. Stop-loss discipline is advised around 10-15% from peak prices to protect against downside risks while maintaining a medium-term investment horizon of 6-12 months.

**Sector spread:**

- Capital Goods & Industrials: **2** name(s)
- Realty: **1** name(s)
- Metals & Mining: **1** name(s)
- Chemicals & Petrochemicals: **1** name(s)
- Capital Goods: **1** name(s)
- Textiles: **1** name(s)
- Fast Moving Consumer Goods: **1** name(s)
- Pharma & Healthcare: **1** name(s)
- FMCG & Consumer Goods: **1** name(s)

## Full Disclaimer

This report is provided strictly for educational, research, and learning purposes as part of a journey to understand how AI agents and rules-based agents can be applied to financial-market data. It is not investment advice, trading advice, portfolio advice, a research recommendation, or a solicitation to buy, sell, hold, short, or otherwise transact in any security, derivative, index, fund, or financial instrument. The information, scores, signals, narratives, charts, model outputs, and examples in this report must not be replicated, redistributed, automated, or used with any intent of trading, recommending trades, advising others, managing money, or making financial decisions. Anyone choosing to use, interpret, adapt, copy, replicate, distribute, or act on this information does so entirely at their own risk, responsibility, and legal and regulatory obligation. Agent Adda is not a SEBI-registered investment adviser, research analyst, portfolio manager, broker, or any other SEBI-registered market intermediary. Agent Adda, its creators, contributors, systems, agents, and associated persons accept no responsibility or liability for losses, damages, legal consequences, regulatory consequences, tax consequences, opportunity costs, or any other implications arising directly or indirectly from the use of this information by any person or organization. All market data can be delayed, incomplete, inaccurate, stale, or affected by corporate actions, liquidity, data-provider issues, model limitations, prompt limitations, or rule-design limitations. Users must consult qualified SEBI-registered professionals and independently verify all facts before making any financial or legal decision.
