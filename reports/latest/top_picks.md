# Top Investment Picks Analysis — 2026-06-19

*Agent Adda - Market Intelligence Agent*

**Generated:** 2026-06-20 10:59 IST  
**Sources:** Sector Rotation Report + Stage 2 Tracker + PostgreSQL `scores.*`, `market.equity_eod`

> **Disclaimer:** This report is not investment advice. It is a learning journey demonstrating how AI and rules-based agents can be applied to financial markets. Validate all data, prices, liquidity, corporate events, and risk independently before making any financial decision.

## Executive Summary

Mechanically-synthesised basket of 10 stocks combining sector-rotation leadership and Weinstein stage-2 momentum, deep-screened across P&L, BS, CF, fundamental scores and corporate events. LLM unavailable — rule-based narrative.

**Macro context:** Snapshot 2026-06-19: 975 stocks scanned; Stage 2 count 349 vs Stage 4 173; BUY/STRONG_BUY signals 123; mean RS vs Nifty 500 12.7%.

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
| 1 | **MTARTECH** | PSU / CPSE | 8374.50 | STAGE_2 | 59.90 | 97.7% | ₹12,222 | 1.39x | 3.5 | strategy+sector+s2 |
| 2 | **PANAMAPET** | Other | 483.25 | STAGE_2 | 52.80 | 70.7% | ₹684 | 0.83x | 7.5 | strategy |
| 3 | **RPTECH** | IT & Technology | 750.65 | STAGE_2 | 49.70 | 95.2% | ₹1,016 | 0.79x | 6.5 | strategy+sector+s2 |
| 4 | **WALCHANNAG** | Other | 312.05 | STAGE_2 | 48.30 | 82.8% | ₹436 | 1.02x | 5.0 | strategy |
| 5 | **CUPID** | Other | 176.92 | STAGE_2 | 47.50 | 88.1% | ₹247 | 0.88x | 3.5 | strategy |
| 6 | **PARAS** | Defence & Aerospace | 1408.65 | STAGE_2 | 46.30 | 106.7% | ₹2,123 | 0.82x | 6.5 | strategy+sector+s2 |
| 7 | **LAURUSLABS** | Pharma & Healthcare | 1412.90 | STAGE_2 | 68.00 | 26.0% | ₹1,690 | 1.18x | 0.5 | vcp+sector |
| 8 | **SASKEN** | IT & Technology | 2586.10 | STAGE_2 | 66.00 | 104.0% | ₹3,766 | 1.08x | 5.0 | vcp+sector |
| 9 | **POLYCAB** | Capital Goods & Industrials | 10083.00 | STAGE_2 | 65.20 | 28.1% | ₹12,856 | 0.82x | 3.5 | vcp+sector |
| 10 | **SATIN** | Financial Services | 235.43 | STAGE_2 | 62.70 | 46.4% | ₹337 | 1.74x | 3.0 | vcp+sector |

## Per-Stock Deep Dive

### 1. MTARTECH — PSU / CPSE

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=59.9, top sector strength=58

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 4.88% return) marks this as **open position**.

**What the company does:** MTAR develops and manufactures components and equipment for the defense, aerospace, nuclear and clean energy sectors. The company was incorporated in 1970 by the promoters, Mr PR Reddy, Mr KSN Reddy and Mr PJ Reddy, to cater to the technical and engineering needs of the Indian government in the post embargo regime. MTAR has manufacturing footprints in Hyderabad with seven units spread across a 4 km radius and a dedicated export facility as well. [1] In addition, the company also supplies specialised products such.

*Company profile source: screener.in (live) — https://www.screener.in/company/MTARTECH/*

**Thesis:** RS 98% vs Nifty 500 · Momentum RSI 63 · Within 5% of 52w high · PAT YoY +214% · Revenue YoY +67% · OCF/PAT 2.10

**Technical view:** RSI 62.8, 1Y return —%, dist from 52w high -3.9%.

**Fundamental view:** Latest qtr revenue 67.2% YoY, PAT 214.3% YoY; 4Y CAGR revenue 28.4% / PAT 11.4%; ROCE —%; debt trend rising; OCF/PAT 2.10.

**Sector view:** Sector strength 57.60

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 160bps vs 4Q avg

**Key risks:**
- Debt rising ₹+186 Cr (3Y)

**Action:** Enter ₹7493-₹8374; stop ₹6393; signal HOLD.

**Targets:** 2M ₹10,024 · 4M ₹11,123 · 6M ₹12,222  
**Stop:** ₹6,393 · **Risk/Reward (4M):** 1.39x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 8%

**Conviction:** **HIGH** — 6 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹8374.50 · 1D 0.8% · 1W 17.0% · 1M 5.4%
- Stage **STAGE_2** (score 0.95) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 59.90 (tech 56.70, fund 50.93)
- Relative Strength 97.7% vs Nifty 500; Supertrend BEARISH around ₹8397.85

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹8374.50 |
| EMA 20 / 50 / 200 | ₹7492.67 / ₹6593.05 / ₹— |
| EMA50 slope (20d) | 23.10% |
| RSI(14) | 62.82 |
| ATR(14) | ₹549.68 (6.56%) |
| 52W High / Low | ₹8714.00 / ₹1866.20 |
| Distance from 52W high | -3.9% |
| Returns 1M / 3M / 6M / 1Y | 12.3% / 143.6% / 261.6% / — |
| Last-day volume vs 20d avg | 1.15x |

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

### 2. PANAMAPET — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=52.8

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 4.88% return) marks this as **next buy**.

**What the company does:** Panama Petrochem Ltd. was incorporated in 1982 by Amirali E Rayani and is engaged in the conversion and manufacturing of crude oil derivatives to 80+ specialty products across segments. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/PANAMAPET/*

**Thesis:** RS 71% vs Nifty 500 · Within 5% of 52w high · PAT YoY +61% · Revenue YoY +18%

**Technical view:** RSI 80.8, 1Y return —%, dist from 52w high -1.4%.

**Fundamental view:** Latest qtr revenue 18.4% YoY, PAT 61.4% YoY; 4Y CAGR revenue 9.5% / PAT -2.0%; ROCE —%; debt trend rising; OCF/PAT -0.33.

**Sector view:** Sector strength 78.52

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 240bps vs 4Q avg

**Key risks:**
- RSI 81 overbought
- Debt rising ₹+85 Cr (3Y)
- OCF/PAT -0.33 weak earnings quality

**Action:** Enter ₹367-₹483; stop ₹310; signal BUY.

**Targets:** 2M ₹569 · 4M ₹626 · 6M ₹684  
**Stop:** ₹310 · **Risk/Reward (4M):** 0.83x  
**Risk score:** 7.5 / 10 (HIGH) · **Suggested size:** 4%

**Conviction:** **MEDIUM** — 4 positive · 3 negative factors flagged

**Snapshot:**

- Price ₹483.25 · 1D 18.4% · 1W 28.1% · 1M 49.3%
- Stage **STAGE_2** (score 0.99) · Stance **BULLISH** · Signal **BUY**
- Investment score 52.80 (tech 61.30, fund 69.06)
- Relative Strength 70.7% vs Nifty 500; Supertrend BULLISH around ₹358.34

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹483.25 |
| EMA 20 / 50 / 200 | ₹366.99 / ₹330.21 / ₹— |
| EMA50 slope (20d) | 15.80% |
| RSI(14) | 80.76 |
| ATR(14) | ₹28.64 (5.93%) |
| 52W High / Low | ₹489.90 / ₹229.00 |
| Distance from 52W high | -1.4% |
| Returns 1M / 3M / 6M / 1Y | 49.8% / 88.6% / 73.7% / — |
| Last-day volume vs 20d avg | 6.42x |

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
| Promoter holding | 63.2% |

---

### 3. RPTECH — IT & Technology

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=49.7, top sector strength=68

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 4.88% return) marks this as **open position**.

**What the company does:** Incorporated in 1989, Rashi Peripherals Ltd operates in ICT product distribution business and after-sale services [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/RPTECH/*

**Thesis:** RS 95% vs Nifty 500 · Within 5% of 52w high · PAT YoY +64% · Revenue YoY +51%

**Technical view:** RSI 85.4, 1Y return —%, dist from 52w high -1.6%.

**Fundamental view:** Latest qtr revenue 51.0% YoY, PAT 64.2% YoY; 4Y CAGR revenue 14.2% / PAT 11.4%; ROCE —%; debt trend rising; OCF/PAT 0.40.

**Sector view:** Sector strength 67.62

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 60bps vs 4Q avg

**Key risks:**
- RSI 85 overbought
- Debt rising ₹+291 Cr (3Y)

**Action:** Enter ₹595-₹751; stop ₹512; signal HOLD.

**Targets:** 2M ₹864 · 4M ₹940 · 6M ₹1,016  
**Stop:** ₹512 · **Risk/Reward (4M):** 0.79x  
**Risk score:** 6.5 / 10 (HIGH) · **Suggested size:** 4%

**Conviction:** **MEDIUM** — 4 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹750.65 · 1D 2.8% · 1W 34.4% · 1M 36.2%
- Stage **STAGE_2** (score 0.99) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 49.70 (tech 56.70, fund 55.77)
- Relative Strength 95.2% vs Nifty 500; Supertrend BULLISH around ₹604.79

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹750.65 |
| EMA 20 / 50 / 200 | ₹594.59 / ₹527.96 / ₹— |
| EMA50 slope (20d) | 16.47% |
| RSI(14) | 85.45 |
| ATR(14) | ₹37.88 (5.05%) |
| 52W High / Low | ₹762.90 / ₹316.30 |
| Distance from 52W high | -1.6% |
| Returns 1M / 3M / 6M / 1Y | 38.1% / 115.1% / 123.9% / — |
| Last-day volume vs 20d avg | 1.62x |

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
| Promoter holding | 64.0% |

---

### 4. WALCHANNAG — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=48.3

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 4.88% return) marks this as **open position**.

**What the company does:** Incorporated in 1908, Walchandnagar Industries Ltd is in the Heavy engineering and Foundry & Machine Shop business [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/WALCHANNAG/*

**Thesis:** RS 83% vs Nifty 500 · Within 5% of 52w high

**Technical view:** RSI 75.3, 1Y return —%, dist from 52w high -1.2%.

**Fundamental view:** Latest qtr revenue —% YoY, PAT —% YoY; —Y CAGR revenue —% / PAT —%; ROCE 4.3%; debt trend —; OCF/PAT —.

**Sector view:** Sector strength 78.52

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- RSI 75 overbought

**Action:** Enter ₹261-₹312; stop ₹225; signal HOLD.

**Targets:** 2M ₹365 · 4M ₹401 · 6M ₹436  
**Stop:** ₹225 · **Risk/Reward (4M):** 1.02x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **LOW** — 2 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹312.05 · 1D 3.5% · 1W 17.6% · 1M 29.2%
- Stage **STAGE_2** (score 0.89) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 48.30 (tech 51.30, fund 52.40)
- Relative Strength 82.8% vs Nifty 500; Supertrend BULLISH around ₹249.01

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹312.05 |
| EMA 20 / 50 / 200 | ₹260.59 / ₹235.98 / ₹— |
| EMA50 slope (20d) | 13.95% |
| RSI(14) | 75.30 |
| ATR(14) | ₹17.71 (5.68%) |
| 52W High / Low | ₹315.80 / ₹131.15 |
| Distance from 52W high | -1.2% |
| Returns 1M / 3M / 6M / 1Y | 31.0% / 107.2% / 103.3% / — |
| Last-day volume vs 20d avg | 1.52x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | -3.8% |
| ROCE | 4.3% |
| Debt / Equity | — |
| Promoter holding | 31.6% |

---

### 5. CUPID — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=47.5

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 4.88% return) marks this as **open position**.

**What the company does:** Established in 1993, CUPID Limited is India's premier manufacturer of male and female condoms, personal lubricant, and IVD kits. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/CUPID/*

**Thesis:** RS 88% vs Nifty 500 · PAT YoY +200% · Revenue YoY +114% · PAT 3Y CAGR 55% · Net cash ₹19 Cr

**Technical view:** RSI 85.3, 1Y return —%, dist from 52w high -66.4%.

**Fundamental view:** Latest qtr revenue 114.3% YoY, PAT 200.0% YoY; 3Y CAGR revenue 33.9% / PAT 55.0%; ROCE —%; debt trend stable; OCF/PAT 0.43.

**Sector view:** Sector strength 78.52

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 140bps vs 4Q avg

**Key risks:**
- RSI 85 overbought

**Action:** Enter ₹149-₹177; stop ₹134; signal BUY.

**Targets:** 2M ₹200 · 4M ₹215 · 6M ₹247  
**Stop:** ₹134 · **Risk/Reward (4M):** 0.88x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 4%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹176.92 · 1D 4.6% · 1W 10.6% · 1M 47.2%
- Stage **STAGE_2** (score 0.85) · Stance **BULLISH** · Signal **BUY**
- Investment score 47.50 (tech 64.00, fund 52.86)
- Relative Strength 88.1% vs Nifty 500; Supertrend BULLISH around ₹147.24

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹176.92 |
| EMA 20 / 50 / 200 | ₹149.12 / ₹149.76 / ₹— |
| EMA50 slope (20d) | -1.40% |
| RSI(14) | 85.28 |
| ATR(14) | ₹7.59 (4.29%) |
| 52W High / Low | ₹526.95 / ₹74.60 |
| Distance from 52W high | -66.4% |
| Returns 1M / 3M / 6M / 1Y | 48.1% / 124.7% / -55.1% / — |
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
| Promoter holding | 46.0% |

---

### 6. PARAS — Defence & Aerospace

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=46.3, top sector strength=70

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 4.88% return) marks this as **open position**.

**What the company does:** Paras Defence and Space Technologies (PDST) is an Private sector company primarily engaged in the designing, developing, manufacturing, and testing of a variety of defence and space engineering products and solutions. The company caters to four major segments - Defence & Space Optics, Defence Electronics, Heavy Engineering and Electromagnetic Pulse Protection Solutions. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/PARAS/*

**Thesis:** RS 107% vs Nifty 500 · Within 5% of 52w high · PAT YoY +86% · Revenue YoY +58% · PAT 4Y CAGR 35% · Net cash ₹6 Cr

**Technical view:** RSI 84.9, 1Y return —%, dist from 52w high -2.4%.

**Fundamental view:** Latest qtr revenue 58.3% YoY, PAT 85.7% YoY; 4Y CAGR revenue 27.1% / PAT 34.7%; ROCE —%; debt trend stable; OCF/PAT 0.28.

**Sector view:** Sector strength 70.40

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- RSI 85 overbought
- OCF/PAT 0.28 weak earnings quality

**Action:** Enter ₹1047-₹1409; stop ₹872; signal BUY.

**Targets:** 2M ₹1,671 · 4M ₹1,846 · 6M ₹2,123  
**Stop:** ₹872 · **Risk/Reward (4M):** 0.82x  
**Risk score:** 6.5 / 10 (HIGH) · **Suggested size:** 4%

**Conviction:** **HIGH** — 6 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹1408.65 · 1D 7.5% · 1W 28.4% · 1M 78.2%
- Stage **STAGE_2** (score 1.00) · Stance **BULLISH** · Signal **BUY**
- Investment score 46.30 (tech 59.30, fund —)
- Relative Strength 106.7% vs Nifty 500; Supertrend BULLISH around ₹1085.49

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹1408.65 |
| EMA 20 / 50 / 200 | ₹1047.17 / ₹904.06 / ₹— |
| EMA50 slope (20d) | 21.00% |
| RSI(14) | 84.89 |
| ATR(14) | ₹87.44 (6.21%) |
| 52W High / Low | ₹1443.00 / ₹580.50 |
| Distance from 52W high | -2.4% |
| Returns 1M / 3M / 6M / 1Y | 84.9% / 122.0% / 111.1% / — |
| Last-day volume vs 20d avg | 3.09x |

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

### 7. LAURUSLABS — Pharma & Healthcare

**Why selected:** VCP-confirmed Stage 2 (vcp=77, inv=68.0) in top-ranked sector Pharma & Healthcare (strength=70)

**What the company does:** Founded in 2005, Laurus Labs is a research-driven pharmaceutical and biotechnology company having a global leadership position in select Active Pharmaceutical Ingredients (APIs) including anti-retroviral, oncology drugs (including High Potent APIs), Cardiovascular, and Gastro therapeutics. They also offer integrated CMO and CDMO services to Global Innovators from Clinical phase drug development to commercial manufacturing. Laurus employs 6,500+ people, including around 1,050+ scientists, at more than 11 facilities.

*Company profile source: screener.in (live) — https://www.screener.in/company/LAURUSLABS/*

**Thesis:** Momentum RSI 64 · Within 5% of 52w high · PAT YoY +21% · OCF/PAT 1.82

**Technical view:** RSI 63.8, 1Y return —%, dist from 52w high -3.0%.

**Fundamental view:** Latest qtr revenue 5.3% YoY, PAT 21.0% YoY; 4Y CAGR revenue 8.4% / PAT 1.7%; ROCE —%; debt trend falling; OCF/PAT 1.82.

**Sector view:** Sector strength 70.40

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 420bps vs 4Q avg

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹1371-₹1413; stop ₹1246; signal BUY.

**Targets:** 2M ₹1,532 · 4M ₹1,611 · 6M ₹1,690  
**Stop:** ₹1,246 · **Risk/Reward (4M):** 1.18x  
**Risk score:** 0.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **MEDIUM** — 4 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹1412.90 · 1D 3.2% · 1W 1.3% · 1M 4.6%
- Stage **STAGE_2** (score 0.67) · Stance **BULLISH** · Signal **BUY**
- Investment score 68.00 (tech 77.30, fund 73.10)
- Relative Strength 26.0% vs Nifty 500; Supertrend BULLISH around ₹1351.98

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹1412.90 |
| EMA 20 / 50 / 200 | ₹1371.17 / ₹1284.49 / ₹— |
| EMA50 slope (20d) | 11.20% |
| RSI(14) | 63.84 |
| ATR(14) | ₹39.54 (2.80%) |
| 52W High / Low | ₹1457.00 / ₹864.70 |
| Distance from 52W high | -3.0% |
| Returns 1M / 3M / 6M / 1Y | 3.8% / 47.1% / 38.6% / — |
| Last-day volume vs 20d avg | 1.30x |

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

### 8. SASKEN — IT & Technology

**Why selected:** VCP-confirmed Stage 2 (vcp=80, inv=66.0) in top-ranked sector IT & Technology (strength=68)

**What the company does:** Established in 1989, Sasken is a specialist in Product Engineering and Digital Transformation providing concept-to-market, chip-to-cognition R&D services to global leaders in Semiconductor, Automotive, Industrials, Consumer Electronics, Enterprise Devices, SatCom, and Transportation industries, etc. Located in India, the company has presence all over the world

*Company profile source: screener.in (live) — https://www.screener.in/company/SASKEN/*

**Thesis:** RS 104% vs Nifty 500 · PAT YoY +142% · Revenue YoY +126% · Net cash ₹249 Cr

**Technical view:** RSI 70.9, 1Y return —%, dist from 52w high -7.0%.

**Fundamental view:** Latest qtr revenue 125.7% YoY, PAT 141.7% YoY; 4Y CAGR revenue 26.5% / PAT -17.6%; ROCE —%; debt trend stable; OCF/PAT -0.39.

**Sector view:** Sector strength 67.62

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 400bps vs 4Q avg

**Key risks:**
- RSI 71 overbought
- OCF/PAT -0.39 weak earnings quality

**Action:** Enter ₹2185-₹2586; stop ₹1808; signal HOLD.

**Targets:** 2M ₹3,092 · 4M ₹3,429 · 6M ₹3,766  
**Stop:** ₹1,808 · **Risk/Reward (4M):** 1.08x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **MEDIUM** — 4 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹2586.10 · 1D -2.3% · 1W 21.9% · 1M 49.3%
- Stage **STAGE_2** (score 0.80) · Stance **BULLISH** · Signal **HOLD**
- Investment score 66.00 (tech 59.30, fund 72.25)
- Relative Strength 104.0% vs Nifty 500; Supertrend BULLISH around ₹2116.41

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹2586.10 |
| EMA 20 / 50 / 200 | ₹2185.20 / ₹1864.27 / ₹— |
| EMA50 slope (20d) | 32.61% |
| RSI(14) | 70.87 |
| ATR(14) | ₹168.58 (6.52%) |
| 52W High / Low | ₹2780.20 / ₹991.00 |
| Distance from 52W high | -7.0% |
| Returns 1M / 3M / 6M / 1Y | 50.5% / 157.7% / 115.5% / — |
| Last-day volume vs 20d avg | 1.67x |

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
| Promoter holding | 43.0% |

---

### 9. POLYCAB — Capital Goods & Industrials

**Why selected:** VCP-confirmed Stage 2 (vcp=76, inv=65.2) in top-ranked sector Capital Goods & Industrials (strength=68)

**What the company does:** Polycab is India’s leading manufacturers of cables and wires and allied products such as uPVC conduits and lugs and glands. We have a range of cables and wires for practically every application. More recently Polycab has also launched a wide range of consumer electrical products like Fans, Switches, Switchgear, LED lights and Luminaries, Solar Inverters, and Pumps.

*Company profile source: screener.in (live) — https://www.screener.in/company/POLYCAB/*

**Thesis:** Within 5% of 52w high · Revenue YoY +27% · PAT 4Y CAGR 31% · Net cash ₹3169 Cr · OCF/PAT 1.41

**Technical view:** RSI 72.8, 1Y return —%, dist from 52w high -0.4%.

**Fundamental view:** Latest qtr revenue 26.9% YoY, PAT 7.1% YoY; 4Y CAGR revenue 24.0% / PAT 31.1%; ROCE —%; debt trend rising; OCF/PAT 1.41.

**Sector view:** Sector strength 67.88

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- RSI 73 overbought
- Debt rising ₹+75 Cr (3Y)

**Action:** Enter ₹9554-₹10083; stop ₹8743; signal BUY.

**Targets:** 2M ₹10,741 · 4M ₹11,179 · 6M ₹12,856  
**Stop:** ₹8,743 · **Risk/Reward (4M):** 0.82x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 4%

**Conviction:** **HIGH** — 5 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹10083.00 · 1D 1.3% · 1W 5.5% · 1M 9.7%
- Stage **STAGE_2** (score 0.70) · Stance **BULLISH** · Signal **BUY**
- Investment score 65.20 (tech 77.30, fund 60.69)
- Relative Strength 28.1% vs Nifty 500; Supertrend BULLISH around ₹9316.75

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹10083.00 |
| EMA 20 / 50 / 200 | ₹9554.50 / ₹9012.93 / ₹— |
| EMA50 slope (20d) | 9.22% |
| RSI(14) | 72.80 |
| ATR(14) | ₹219.21 (2.17%) |
| 52W High / Low | ₹10120.00 / ₹6663.00 |
| Distance from 52W high | -0.4% |
| Returns 1M / 3M / 6M / 1Y | 9.6% / 41.5% / 39.7% / — |
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
| Promoter holding | 61.5% |

---

### 10. SATIN — Financial Services

**Why selected:** VCP-confirmed Stage 2 (vcp=74, inv=62.7) in top-ranked sector Financial Services (strength=58)

**What the company does:** Satin Network Limited (SCNL) is a leading microfinance institution (MFI) with presence in 23 states & union territory and 95,000 villages. The company offers a bouquet of financial products in the Non‐MFI segment (comprising loans to MSMEs), a housing finance subsidiary, and business correspondent services and similar services to other financial Institutions through Taraashna Financial Services Limited (TFSL), a business correspondent company and a 100% subsidiary of SCNL. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/SATIN/*

**Thesis:** Within 5% of 52w high · PAT YoY +636% · Revenue YoY +50% · PAT 4Y CAGR 99%

**Technical view:** RSI 59.5, 1Y return —%, dist from 52w high -4.7%.

**Fundamental view:** Latest qtr revenue 49.6% YoY, PAT 636.4% YoY; 4Y CAGR revenue 22.9% / PAT 99.4%; ROCE —%; debt trend —; OCF/PAT -2.93.

**Sector view:** Sector strength 58.14

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- OCF/PAT -2.93 weak earnings quality

**Action:** Enter ₹228-₹235; stop ₹203; signal BUY.

**Targets:** 2M ₹270 · 4M ₹293 · 6M ₹337  
**Stop:** ₹203 · **Risk/Reward (4M):** 1.74x  
**Risk score:** 3.0 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **MEDIUM** — 4 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹235.43 · 1D 1.7% · 1W 4.0% · 1M 8.2%
- Stage **STAGE_2** (score 0.76) · Stance **BULLISH** · Signal **BUY**
- Investment score 62.70 (tech 66.00, fund 53.26)
- Relative Strength 46.4% vs Nifty 500; Supertrend BULLISH around ₹204.33

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-19) | ₹235.43 |
| EMA 20 / 50 / 200 | ₹227.75 / ₹208.77 / ₹— |
| EMA50 slope (20d) | 14.48% |
| RSI(14) | 59.46 |
| ATR(14) | ₹11.47 (4.87%) |
| 52W High / Low | ₹247.00 / ₹135.81 |
| Distance from 52W high | -4.7% |
| Returns 1M / 3M / 6M / 1Y | 5.8% / 62.8% / 65.0% / — |
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
| Promoter holding | 36.2% |

---

## Portfolio Construction

Equal-weight 10% per name baseline. Overweight HIGH-conviction names by +2%, halve LOW-conviction sizes. Cap sector exposure at 30%. Scale gross to 60-70% in elevated VIX regimes; cap per-trade risk at 1-2% of NAV via stop-distance × size.

**Sector spread:**

- Other: **3** name(s)
- IT & Technology: **2** name(s)
- PSU / CPSE: **1** name(s)
- Defence & Aerospace: **1** name(s)
- Pharma & Healthcare: **1** name(s)
- Capital Goods & Industrials: **1** name(s)
- Financial Services: **1** name(s)

## Full Disclaimer

This report is provided strictly for educational, research, and learning purposes as part of a journey to understand how AI agents and rules-based agents can be applied to financial-market data. It is not investment advice, trading advice, portfolio advice, a research recommendation, or a solicitation to buy, sell, hold, short, or otherwise transact in any security, derivative, index, fund, or financial instrument. The information, scores, signals, narratives, charts, model outputs, and examples in this report must not be replicated, redistributed, automated, or used with any intent of trading, recommending trades, advising others, managing money, or making financial decisions. Anyone choosing to use, interpret, adapt, copy, replicate, distribute, or act on this information does so entirely at their own risk, responsibility, and legal and regulatory obligation. Agent Adda is not a SEBI-registered investment adviser, research analyst, portfolio manager, broker, or any other SEBI-registered market intermediary. Agent Adda, its creators, contributors, systems, agents, and associated persons accept no responsibility or liability for losses, damages, legal consequences, regulatory consequences, tax consequences, opportunity costs, or any other implications arising directly or indirectly from the use of this information by any person or organization. All market data can be delayed, incomplete, inaccurate, stale, or affected by corporate actions, liquidity, data-provider issues, model limitations, prompt limitations, or rule-design limitations. Users must consult qualified SEBI-registered professionals and independently verify all facts before making any financial or legal decision.
