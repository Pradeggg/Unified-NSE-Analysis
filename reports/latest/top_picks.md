# Top Investment Picks Analysis — 2026-06-12

*Agent Adda - Market Intelligence Agent*

**Generated:** 2026-06-12 19:53 IST  
**Sources:** Sector Rotation Report + Stage 2 Tracker + PostgreSQL `scores.*`, `market.equity_eod`

> **Disclaimer:** This report is not investment advice. It is a learning journey demonstrating how AI and rules-based agents can be applied to financial markets. Validate all data, prices, liquidity, corporate events, and risk independently before making any financial decision.

## Executive Summary

Mechanically-synthesised basket of 10 stocks combining sector-rotation leadership and Weinstein stage-2 momentum, deep-screened across P&L, BS, CF, fundamental scores and corporate events. LLM unavailable — rule-based narrative.

**Macro context:** Snapshot 2026-06-12: 947 stocks scanned; Stage 2 count 260 vs Stage 4 231; BUY/STRONG_BUY signals 168; mean RS vs Nifty 500 18.7%.

## Methodology

Top picks are not selected from a single indicator. The report looks for names where market structure, sector strength, price action, strategy evidence, and risk/reward all point in the same direction.

### Core Inputs

1. **Sector Rotation Report** — finds leading sectors and the highest investment-score stocks inside those sectors.
2. **Stage 2 / VCP Tracker** — prioritises Weinstein Stage 2 stocks and persisted `scores.stage2_vcp_picks` candidates.
3. **Portfolio Strategy Lab** — gives extra weight to symbols confirmed by the best-ranked paper strategy's open positions or next BUY orders.
4. **Technical Strength** — uses 260 trading days of EOD data: EMA20/50/200 stack, EMA50 slope, RSI(14), ATR(14), 52-week position, 1M/3M/6M/1Y returns, volume ratio, support/resistance, pivots, and volume profile.
5. **Fundamental and Risk Checks** — uses Piotroski F-score, Altman Z, Beneish M, ROE/ROCE, 3-year growth, debt/equity, promoter holding, cash-flow quality, valuation, stop loss, targets, and risk/reward.

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
- **Portfolio strategy confirmation:** paper-trading strategies such as breakout or Darvas-style systems add independent confirmation when they mark the stock as an open position or next BUY.
- **Risk/reward:** targets, stop-loss distance, ATR volatility, and risk score prevent high-momentum but poor-risk trades from dominating the list.
- **Fundamental quality:** profitability, leverage, cash-flow quality, growth, and valuation checks reduce false positives.

Triple-confirmed names, where sector rotation + Stage 2/VCP + portfolio strategy evidence agree, are prioritised. Dual-confirmed names can still qualify when their trend, relative strength, and risk/reward are strong.

### How to Read the Picks

A high-ranked pick should be read as a research shortlist candidate, not a direct investment instruction. The strongest candidates typically combine Stage 2 structure, leadership versus the market, constructive sector context, defined stop-loss, and acceptable reward-to-risk. The report is for research and learning only; it is not investment advice.

## Pick Summary

| # | Symbol | Sector | Price | Stage | Inv.Score | RS% | 6M Tgt | RR(4M) | Risk | Source |
|---|---|---|---:|---|---:|---:|---:|---:|:---:|---|
| 1 | **NETWEB** | IT & Technology | 4587.40 | STAGE_2 | 71.80 | 40.5% | ₹6,723 | 1.73x | 2.5 | strategy+sector+s2 |
| 2 | **DATAPATTNS** | Defence & Aerospace | 4545.70 | STAGE_2 | 64.90 | 42.2% | ₹6,238 | 1.38x | 2.5 | strategy+sector+s2 |
| 3 | **APOLLO** | Other | 409.40 | STAGE_2 | 63.60 | 117.2% | ₹637 | 1.74x | 5.0 | strategy+vcp |
| 4 | **PARAS** | Defence & Aerospace | 1097.15 | STAGE_2 | 63.20 | 76.8% | ₹1,625 | 1.01x | 6.0 | strategy+sector+s2 |
| 5 | **JNKINDIA** | Other | 504.05 | STAGE_2 | 62.50 | 132.5% | ₹733 | 1.06x | 6.0 | strategy |
| 6 | **APARINDS** | Capital Goods & Industrials | 15221.00 | STAGE_2 | 62.30 | 46.5% | ₹20,162 | 1.09x | 4.5 | strategy+sector+s2 |
| 7 | **MTARTECH** | PSU / CPSE | 7159.50 | STAGE_2 | 57.50 | 99.0% | ₹10,966 | 2.00x | 3.5 | strategy+sector+s2 |
| 8 | **ADANIGREEN** | Energy - Power | 1485.70 | STAGE_2 | 47.60 | 76.6% | ₹2,031 | 1.28x | 2.5 | strategy+vcp |
| 9 | **HFCL** | Railways & PSU Infra | 171.86 | STAGE_2 | 47.40 | 145.7% | ₹256 | 1.65x | 5.0 | strategy |
| 10 | **CUPID** | Other | 159.97 | STAGE_2 | 46.70 | 85.0% | ₹214 | 0.77x | 3.5 | strategy |

## Per-Stock Deep Dive

### 1. NETWEB — IT & Technology

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=71.8, top sector strength=64

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **next buy**.

**What the company does:** Incorporated in 1999, Netweb Technologies India (NTI) is one of India‘s leading high-end computing solutions (HCS) providers, with fully integrated design and manufacturing capabilities. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/NETWEB/*

**Thesis:** Stage-2 EMA stack (Price ₹4587 > EMA20 > EMA50 > EMA200) · ROCE 38% · ROE 33%

**Technical view:** RSI 58.0, 1Y return 132.1%, dist from 52w high -7.6%.

**Fundamental view:** Latest qtr revenue —% YoY, PAT —% YoY; —Y CAGR revenue —% / PAT —%; ROCE 37.5%; debt trend —; OCF/PAT —.

**Sector view:** Sector strength 64.40

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹4315-₹4587; stop ₹3705; signal STRONG_BUY.

**Targets:** 2M ₹5,502 · 4M ₹6,113 · 6M ₹6,723  
**Stop:** ₹3,705 · **Risk/Reward (4M):** 1.73x  
**Risk score:** 2.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **MEDIUM** — 3 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹4587.40 · 1D 9.4% · 1W -1.7% · 1M 17.4%
- Stage **STAGE_2** (score 0.64) · Stance **BULLISH** · Signal **STRONG_BUY**
- Investment score 71.80 (tech 82.00, fund 73.99)
- Relative Strength 40.5% vs Nifty 500; Supertrend BULLISH around ₹4018.74

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹4587.40 |
| EMA 20 / 50 / 200 | ₹4314.69 / ₹4037.82 / ₹3362.73 |
| EMA50 slope (20d) | 8.63% |
| RSI(14) | 57.96 |
| ATR(14) | ₹305.03 (6.65%) |
| 52W High / Low | ₹4965.00 / ₹1700.10 |
| Distance from 52W high | -7.6% |
| Returns 1M / 3M / 6M / 1Y | 16.6% / 38.0% / 51.0% / 132.1% |
| Last-day volume vs 20d avg | 1.76x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | 32.8% |
| ROCE | 37.5% |
| Debt / Equity | — |
| Promoter holding | 67.0% |

---

### 2. DATAPATTNS — Defence & Aerospace

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=64.9, top sector strength=67

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **next buy**.

**What the company does:** Data Patterns (India) Limited is one of the fastest-growing companies in the Defence and Aerospace Electronics sector in India. It is among the few vertically integrated defence and aerospace electronics solutions providers catering to the indigenously developed defence products industry. It is focused on in-house development and manufacturing facilities led by innovation and design and development efforts. It is in the business for over 35 years. It has supplied products catering to all the platforms, viz.

*Company profile source: screener.in (live) — https://www.screener.in/company/DATAPATTNS/*

**Thesis:** Stage-2 EMA stack (Price ₹4546 > EMA20 > EMA50 > EMA200) · Momentum RSI 62 · Within 5% of 52w high · ROCE 23%

**Technical view:** RSI 62.1, 1Y return 48.3%, dist from 52w high -3.7%.

**Fundamental view:** Latest qtr revenue —% YoY, PAT —% YoY; —Y CAGR revenue —% / PAT —%; ROCE 23.3%; debt trend —; OCF/PAT —.

**Sector view:** Sector strength 66.78

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹4152-₹4546; stop ₹3668; signal BUY.

**Targets:** 2M ₹5,271 · 4M ₹5,754 · 6M ₹6,238  
**Stop:** ₹3,668 · **Risk/Reward (4M):** 1.38x  
**Risk score:** 2.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **MEDIUM** — 4 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹4545.70 · 1D 8.1% · 1W 7.9% · 1M 13.3%
- Stage **STAGE_2** (score 0.81) · Stance **BULLISH** · Signal **BUY**
- Investment score 64.90 (tech 76.00, fund 52.76)
- Relative Strength 42.2% vs Nifty 500; Supertrend BULLISH around ₹3781.92

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹4545.70 |
| EMA 20 / 50 / 200 | ₹4151.70 / ₹3894.08 / ₹3251.64 |
| EMA50 slope (20d) | 7.55% |
| RSI(14) | 62.11 |
| ATR(14) | ₹241.71 (5.32%) |
| 52W High / Low | ₹4722.00 / ₹2131.00 |
| Distance from 52W high | -3.7% |
| Returns 1M / 3M / 6M / 1Y | 8.3% / 32.1% / 75.7% / 48.3% |
| Last-day volume vs 20d avg | 1.91x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | 16.7% |
| ROCE | 23.3% |
| Debt / Equity | — |
| Promoter holding | 42.4% |

---

### 3. APOLLO — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=63.6, VCP=79

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **open position**.

**What the company does:** Apollo Micro Systems Ltd is a pioneer in design, development, assembly and testing of electronic and electro mechanical solutions. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/APOLLO/*

**Thesis:** Stage-2 EMA stack (Price ₹409 > EMA20 > EMA50 > EMA200) · RS 117% vs Nifty 500 · Momentum RSI 61 · PAT YoY +164% · Revenue YoY +81% · PAT 4Y CAGR 63%

**Technical view:** RSI 60.5, 1Y return 99.7%, dist from 52w high -8.4%.

**Fundamental view:** Latest qtr revenue 80.9% YoY, PAT 164.3% YoY; 4Y CAGR revenue 38.9% / PAT 63.4%; ROCE —%; debt trend rising; OCF/PAT -1.21.

**Sector view:** Sector strength 80.80

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- Debt rising ₹+335 Cr (3Y)
- OCF/PAT -1.21 weak earnings quality

**Action:** Enter ₹385-₹409; stop ₹326; signal BUY.

**Targets:** 2M ₹496 · 4M ₹554 · 6M ₹637  
**Stop:** ₹326 · **Risk/Reward (4M):** 1.74x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **HIGH** — 6 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹409.40 · 1D 7.2% · 1W -2.8% · 1M 34.0%
- Stage **STAGE_2** (score 0.90) · Stance **BULLISH** · Signal **BUY**
- Investment score 63.60 (tech 66.00, fund 54.74)
- Relative Strength 117.2% vs Nifty 500; Supertrend BULLISH around ₹333.95

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹409.40 |
| EMA 20 / 50 / 200 | ₹385.05 / ₹336.16 / ₹274.15 |
| EMA50 slope (20d) | 26.56% |
| RSI(14) | 60.55 |
| ATR(14) | ₹28.95 (7.07%) |
| 52W High / Low | ₹446.90 / ₹162.34 |
| Distance from 52W high | -8.4% |
| Returns 1M / 3M / 6M / 1Y | 34.5% / 88.1% / 64.5% / 99.7% |
| Last-day volume vs 20d avg | 0.62x |

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
| Promoter holding | 52.0% |

---

### 4. PARAS — Defence & Aerospace

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=63.2, top sector strength=67

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **next buy**.

**What the company does:** Paras Defence and Space Technologies (PDST) is an Private sector company primarily engaged in the designing, developing, manufacturing, and testing of a variety of defence and space engineering products and solutions. The company caters to four major segments - Defence & Space Optics, Defence Electronics, Heavy Engineering and Electromagnetic Pulse Protection Solutions. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/PARAS/*

**Thesis:** Stage-2 EMA stack (Price ₹1097 > EMA20 > EMA50 > EMA200) · RS 77% vs Nifty 500 · Within 5% of 52w high · PAT YoY +86% · Revenue YoY +58% · PAT 4Y CAGR 35% · Net cash ₹6 Cr

**Technical view:** RSI 74.8, 1Y return 33.2%, dist from 52w high -0.7%.

**Fundamental view:** Latest qtr revenue 58.3% YoY, PAT 85.7% YoY; 4Y CAGR revenue 27.1% / PAT 34.7%; ROCE —%; debt trend stable; OCF/PAT 0.28.

**Sector view:** Sector strength 66.78

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- RSI 75 overbought
- OCF/PAT 0.28 weak earnings quality

**Action:** Enter ₹911-₹1097; stop ₹785; signal BUY.

**Targets:** 2M ₹1,287 · 4M ₹1,413 · 6M ₹1,625  
**Stop:** ₹785 · **Risk/Reward (4M):** 1.01x  
**Risk score:** 6.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **HIGH** — 7 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹1097.15 · 1D 10.9% · 1W 14.3% · 1M 40.1%
- Stage **STAGE_2** (score 0.95) · Stance **BULLISH** · Signal **BUY**
- Investment score 63.20 (tech 60.70, fund 84.38)
- Relative Strength 76.8% vs Nifty 500; Supertrend BULLISH around ₹853.68

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹1097.15 |
| EMA 20 / 50 / 200 | ₹911.19 / ₹829.04 / ₹749.90 |
| EMA50 slope (20d) | 11.18% |
| RSI(14) | 74.82 |
| ATR(14) | ₹63.12 (5.75%) |
| 52W High / Low | ₹1105.20 / ₹580.50 |
| Distance from 52W high | -0.7% |
| Returns 1M / 3M / 6M / 1Y | 38.2% / 56.0% / 65.6% / 33.2% |
| Last-day volume vs 20d avg | 1.63x |

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
| Promoter holding | 53.2% |

---

### 5. JNKINDIA — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=62.5

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **open position**.

**What the company does:** JIncorporated in 2010, JNK India Ltd is in the business of Technology based EPC Contracts and Solutions in Renewable Energy [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/JNKINDIA/*

**Thesis:** Stage-2 EMA stack (Price ₹504 > EMA20 > EMA50 > EMA200) · RS 132% vs Nifty 500 · Within 5% of 52w high · PAT YoY +154% · Revenue YoY +77%

**Technical view:** RSI 72.1, 1Y return 46.4%, dist from 52w high -1.4%.

**Fundamental view:** Latest qtr revenue 77.0% YoY, PAT 153.8% YoY; 4Y CAGR revenue 29.0% / PAT 15.9%; ROCE —%; debt trend stable; OCF/PAT -0.03.

**Sector view:** Sector strength 80.80

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 600bps vs 4Q avg

**Key risks:**
- RSI 72 overbought
- OCF/PAT -0.03 weak earnings quality

**Action:** Enter ₹415-₹504; stop ₹350; signal HOLD.

**Targets:** 2M ₹602 · 4M ₹668 · 6M ₹733  
**Stop:** ₹350 · **Risk/Reward (4M):** 1.06x  
**Risk score:** 6.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **HIGH** — 5 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹504.05 · 1D 7.2% · 1W 19.6% · 1M 46.1%
- Stage **STAGE_2** (score 1.00) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 62.50 (tech 48.00, fund 81.85)
- Relative Strength 132.5% vs Nifty 500; Supertrend BULLISH around ₹389.44

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹504.05 |
| EMA 20 / 50 / 200 | ₹415.28 / ₹364.92 / ₹312.16 |
| EMA50 slope (20d) | 18.28% |
| RSI(14) | 72.05 |
| ATR(14) | ₹32.73 (6.49%) |
| 52W High / Low | ₹511.00 / ₹200.92 |
| Distance from 52W high | -1.4% |
| Returns 1M / 3M / 6M / 1Y | 48.1% / 113.0% / 128.6% / 46.4% |
| Last-day volume vs 20d avg | 1.08x |

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
| Promoter holding | 67.8% |

---

### 6. APARINDS — Capital Goods & Industrials

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=62.3, top sector strength=66

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **next buy**.

**What the company does:** Apar, founded by Mr. Dharmsinh D. Desai in 1958, is a market leader in India with a global presence. Contributing to India’s process of electrification it started from manufacturing power transmission cables to having three broad business segments, which are Conductors, Transformer and specialty oils (TSO), and Power/telecom Cables. [1] [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/APARINDS/*

**Thesis:** Stage-2 EMA stack (Price ₹15221 > EMA20 > EMA50 > EMA200) · Within 5% of 52w high · Revenue YoY +27% · OCF/PAT 0.99

**Technical view:** RSI 72.7, 1Y return 87.8%, dist from 52w high -0.8%.

**Fundamental view:** Latest qtr revenue 26.7% YoY, PAT 1.2% YoY; 4Y CAGR revenue 10.7% / PAT 11.2%; ROCE —%; debt trend rising; OCF/PAT 0.99.

**Sector view:** Sector strength 65.74

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- RSI 73 overbought
- Debt rising ₹+371 Cr (3Y)

**Action:** Enter ₹13441-₹15221; stop ₹12059; signal BUY.

**Targets:** 2M ₹17,290 · 4M ₹18,668 · 6M ₹20,162  
**Stop:** ₹12,059 · **Risk/Reward (4M):** 1.09x  
**Risk score:** 4.5 / 10 (MEDIUM) · **Suggested size:** 8%

**Conviction:** **MEDIUM** — 4 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹15221.00 · 1D 4.6% · 1W 9.7% · 1M 19.5%
- Stage **STAGE_2** (score 0.79) · Stance **BULLISH** · Signal **BUY**
- Investment score 62.30 (tech 66.70, fund 57.41)
- Relative Strength 46.5% vs Nifty 500; Supertrend BULLISH around ₹12971.90

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹15221.00 |
| EMA 20 / 50 / 200 | ₹13441.27 / ₹12431.88 / ₹10236.99 |
| EMA50 slope (20d) | 10.62% |
| RSI(14) | 72.73 |
| ATR(14) | ₹689.50 (4.53%) |
| 52W High / Low | ₹15340.00 / ₹6801.00 |
| Distance from 52W high | -0.8% |
| Returns 1M / 3M / 6M / 1Y | 22.5% / 52.3% / 76.1% / 87.8% |
| Last-day volume vs 20d avg | 1.79x |

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
| Promoter holding | 57.8% |

---

### 7. MTARTECH — PSU / CPSE

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=57.5, top sector strength=59

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **open position**.

**What the company does:** MTAR develops and manufactures components and equipment for the defense, aerospace, nuclear and clean energy sectors. The company was incorporated in 1970 by the promoters, Mr PR Reddy, Mr KSN Reddy and Mr PJ Reddy, to cater to the technical and engineering needs of the Indian government in the post embargo regime. MTAR has manufacturing footprints in Hyderabad with seven units spread across a 4 km radius and a dedicated export facility as well. [1] In addition, the company also supplies specialised products such.

*Company profile source: screener.in (live) — https://www.screener.in/company/MTARTECH/*

**Thesis:** Stage-2 EMA stack (Price ₹7160 > EMA20 > EMA50 > EMA200) · RS 99% vs Nifty 500 · PAT YoY +214% · Revenue YoY +67% · OCF/PAT 2.10

**Technical view:** RSI 52.1, 1Y return 304.3%, dist from 52w high -15.3%.

**Fundamental view:** Latest qtr revenue 67.2% YoY, PAT 214.3% YoY; 4Y CAGR revenue 28.4% / PAT 11.4%; ROCE —%; debt trend rising; OCF/PAT 2.10.

**Sector view:** Sector strength 59.34

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 160bps vs 4Q avg

**Key risks:**
- Debt rising ₹+186 Cr (3Y)

**Action:** Enter ₹6888-₹7160; stop ₹5800; signal BUY.

**Targets:** 2M ₹8,791 · 4M ₹9,879 · 6M ₹10,966  
**Stop:** ₹5,800 · **Risk/Reward (4M):** 2.00x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 10%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹7159.50 · 1D 13.5% · 1W -5.0% · 1M -5.7%
- Stage **STAGE_2** (score 0.82) · Stance **BULLISH** · Signal **BUY**
- Investment score 57.50 (tech 64.70, fund 50.93)
- Relative Strength 99.0% vs Nifty 500; Supertrend BEARISH around ₹8397.85

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹7159.50 |
| EMA 20 / 50 / 200 | ₹7132.16 / ₹6302.04 / ₹3916.97 |
| EMA50 slope (20d) | 26.55% |
| RSI(14) | 52.06 |
| ATR(14) | ₹543.82 (7.60%) |
| 52W High / Low | ₹8449.50 / ₹1390.50 |
| Distance from 52W high | -15.3% |
| Returns 1M / 3M / 6M / 1Y | 5.9% / 92.9% / 207.5% / 304.3% |
| Last-day volume vs 20d avg | 1.95x |

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
| Promoter holding | 30.4% |

---

### 8. ADANIGREEN — Energy - Power

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=47.6, VCP=76

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **open position**.

**What the company does:** Adani Green Energy Limited, incorporated in 2015, is a holding company of several subsidiaries carrying business of renewable power generation within the group and is primarily involved in renewable power generation and other ancillary activities. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/ADANIGREEN/*

**Thesis:** Stage-2 EMA stack (Price ₹1486 > EMA20 > EMA50 > EMA200) · RS 77% vs Nifty 500 · Momentum RSI 60 · Within 5% of 52w high · PAT YoY +34% · PAT 4Y CAGR 42% · OCF/PAT 5.10

**Technical view:** RSI 60.1, 1Y return 45.8%, dist from 52w high -3.8%.

**Fundamental view:** Latest qtr revenue 14.0% YoY, PAT 34.2% YoY; 4Y CAGR revenue 26.0% / PAT 42.0%; ROCE —%; debt trend rising; OCF/PAT 5.10.

**Sector view:** Sector strength 51.46

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- Debt rising ₹+38687 Cr (3Y)

**Action:** Enter ₹1434-₹1486; stop ₹1267; signal HOLD.

**Targets:** 2M ₹1,654 · 4M ₹1,766 · 6M ₹2,031  
**Stop:** ₹1,267 · **Risk/Reward (4M):** 1.28x  
**Risk score:** 2.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **HIGH** — 7 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹1485.70 · 1D 2.1% · 1W -2.6% · 1M 5.0%
- Stage **STAGE_2** (score 0.76) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 47.60 (tech 50.00, fund 10.00)
- Relative Strength 76.6% vs Nifty 500; Supertrend BULLISH around ₹1342.14

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹1485.70 |
| EMA 20 / 50 / 200 | ₹1434.07 / ₹1306.38 / ₹1108.30 |
| EMA50 slope (20d) | 15.31% |
| RSI(14) | 60.11 |
| ATR(14) | ₹56.13 (3.78%) |
| 52W High / Low | ₹1544.80 / ₹765.00 |
| Distance from 52W high | -3.8% |
| Returns 1M / 3M / 6M / 1Y | 8.7% / 73.4% / 49.5% / 45.8% |
| Last-day volume vs 20d avg | 0.45x |

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
| Promoter holding | 62.4% |

---

### 9. HFCL — Railways & PSU Infra

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=47.4

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **open position**.

**What the company does:** HFCL Ltd (Himachal Futuristic Communications Limited) is a diverse telecom infrastructure enabler with active interest spanning telecom infrastructure development, system integration, and manufacture and supply of high end telecom equipment, Optical Fiber and Optic Fiber Cable (OFC). [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/HFCL/*

**Thesis:** Stage-2 EMA stack (Price ₹172 > EMA20 > EMA50 > EMA200) · RS 146% vs Nifty 500 · Revenue YoY +128%

**Technical view:** RSI 58.1, 1Y return 88.0%, dist from 52w high -17.8%.

**Fundamental view:** Latest qtr revenue 127.7% YoY, PAT -321.7% YoY; 4Y CAGR revenue 1.2% / PAT 0.2%; ROCE —%; debt trend rising; OCF/PAT -1.15.

**Sector view:** Sector strength 56.54

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 700bps vs 4Q avg

**Key risks:**
- Debt rising ₹+753 Cr (3Y)
- OCF/PAT -1.15 weak earnings quality

**Action:** Enter ₹166-₹172; stop ₹135; signal HOLD.

**Targets:** 2M ₹208 · 4M ₹232 · 6M ₹256  
**Stop:** ₹135 · **Risk/Reward (4M):** 1.65x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **MEDIUM** — 3 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹171.86 · 1D 5.0% · 1W -8.2% · 1M 13.4%
- Stage **STAGE_2** (score 0.67) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 47.40 (tech 49.30, fund 10.00)
- Relative Strength 145.7% vs Nifty 500; Supertrend BEARISH around ₹202.02

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹171.86 |
| EMA 20 / 50 / 200 | ₹166.70 / ₹139.69 / ₹98.46 |
| EMA50 slope (20d) | 36.70% |
| RSI(14) | 58.06 |
| ATR(14) | ₹11.97 (6.97%) |
| 52W High / Low | ₹208.98 / ₹59.82 |
| Distance from 52W high | -17.8% |
| Returns 1M / 3M / 6M / 1Y | 12.0% / 146.2% / 158.5% / 88.0% |
| Last-day volume vs 20d avg | 0.17x |

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
| Promoter holding | 28.3% |

---

### 10. CUPID — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=46.7

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 70.22% return) marks this as **open position**.

**What the company does:** Established in 1993, CUPID Limited is India's premier manufacturer of male and female condoms, personal lubricant, and IVD kits. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/CUPID/*

**Thesis:** RS 85% vs Nifty 500 · PAT YoY +200% · Revenue YoY +114% · PAT 3Y CAGR 55% · Net cash ₹19 Cr

**Technical view:** RSI 78.6, 1Y return 640.6%, dist from 52w high -69.6%.

**Fundamental view:** Latest qtr revenue 114.3% YoY, PAT 200.0% YoY; 3Y CAGR revenue 33.9% / PAT 55.0%; ROCE —%; debt trend stable; OCF/PAT 0.43.

**Sector view:** Sector strength 80.80

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 140bps vs 4Q avg

**Key risks:**
- RSI 79 overbought

**Action:** Enter ₹136-₹160; stop ₹126; signal HOLD.

**Targets:** 2M ₹176 · 4M ₹186 · 6M ₹214  
**Stop:** ₹126 · **Risk/Reward (4M):** 0.77x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 4%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹159.97 · 1D 3.1% · 1W 16.7% · 1M 30.0%
- Stage **STAGE_2** (score 0.82) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 46.70 (tech 61.30, fund 52.86)
- Relative Strength 85.0% vs Nifty 500; Supertrend BULLISH around ₹140.73

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-12) | ₹159.97 |
| EMA 20 / 50 / 200 | ₹136.25 / ₹144.66 / ₹162.56 |
| EMA50 slope (20d) | -7.93% |
| RSI(14) | 78.64 |
| ATR(14) | ₹5.24 (3.28%) |
| 52W High / Low | ₹526.95 / ₹17.68 |
| Distance from 52W high | -69.6% |
| Returns 1M / 3M / 6M / 1Y | 31.0% / 72.3% / -57.9% / 640.6% |
| Last-day volume vs 20d avg | 1.33x |

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
| Promoter holding | 46.0% |

---

## Portfolio Construction

Equal-weight 10% per name baseline. Overweight HIGH-conviction names by +2%, halve LOW-conviction sizes. Cap sector exposure at 30%. Scale gross to 60-70% in elevated VIX regimes; cap per-trade risk at 1-2% of NAV via stop-distance × size.

**Sector spread:**

- Other: **3** name(s)
- Defence & Aerospace: **2** name(s)
- IT & Technology: **1** name(s)
- Capital Goods & Industrials: **1** name(s)
- PSU / CPSE: **1** name(s)
- Energy - Power: **1** name(s)
- Railways & PSU Infra: **1** name(s)

## Full Disclaimer

This report is provided strictly for educational, research, and learning purposes as part of a journey to understand how AI agents and rules-based agents can be applied to financial-market data. It is not investment advice, trading advice, portfolio advice, a research recommendation, or a solicitation to buy, sell, hold, short, or otherwise transact in any security, derivative, index, fund, or financial instrument. The information, scores, signals, narratives, charts, model outputs, and examples in this report must not be replicated, redistributed, automated, or used with any intent of trading, recommending trades, advising others, managing money, or making financial decisions. Anyone choosing to use, interpret, adapt, copy, replicate, distribute, or act on this information does so entirely at their own risk, responsibility, and legal and regulatory obligation. Agent Adda is not a SEBI-registered investment adviser, research analyst, portfolio manager, broker, or any other SEBI-registered market intermediary. Agent Adda, its creators, contributors, systems, agents, and associated persons accept no responsibility or liability for losses, damages, legal consequences, regulatory consequences, tax consequences, opportunity costs, or any other implications arising directly or indirectly from the use of this information by any person or organization. All market data can be delayed, incomplete, inaccurate, stale, or affected by corporate actions, liquidity, data-provider issues, model limitations, prompt limitations, or rule-design limitations. Users must consult qualified SEBI-registered professionals and independently verify all facts before making any financial or legal decision.
