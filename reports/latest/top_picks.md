# Top Investment Picks Analysis — 2026-06-11

*Agent Adda - Market Intelligence Agent*

**Generated:** 2026-06-11 20:30 IST  
**Sources:** Sector Rotation Report + Stage 2 Tracker + PostgreSQL `scores.*`, `market.equity_eod`

> **Disclaimer:** This report is not investment advice. It is a learning journey demonstrating how AI and rules-based agents can be applied to financial markets. Validate all data, prices, liquidity, corporate events, and risk independently before making any financial decision.

## Executive Summary

Mechanically-synthesised basket of 10 stocks combining sector-rotation leadership and Weinstein stage-2 momentum, deep-screened across P&L, BS, CF, fundamental scores and corporate events. LLM unavailable — rule-based narrative.

**Macro context:** Snapshot 2026-06-11: 909 stocks scanned; Stage 2 count 224 vs Stage 4 273; BUY/STRONG_BUY signals 85; mean RS vs Nifty 500 15.6%.

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
| 1 | **APARINDS** | Capital Goods & Industrials | 14551.00 | STAGE_2 | 66.10 | 34.2% | ₹19,298 | 1.26x | 3.5 | strategy+sector+s2 |
| 2 | **JNKINDIA** | Other | 470.00 | STAGE_2 | 64.80 | 111.5% | ₹696 | 1.25x | 4.0 | strategy |
| 3 | **HONASA** | MNC | 417.65 | STAGE_2 | 63.00 | 37.1% | ₹551 | 1.44x | 1.5 | strategy+sector+s2 |
| 4 | **APOLLO** | Other | 381.75 | STAGE_2 | 61.20 | 98.5% | ₹599 | 2.00x | 5.0 | strategy+vcp |
| 5 | **CUPID** | Other | 155.18 | STAGE_2 | 50.10 | 80.4% | ₹208 | 0.80x | 3.5 | strategy |
| 6 | **HFCL** | Railways & PSU Infra | 163.68 | STAGE_2 | 47.60 | 128.3% | ₹247 | 2.00x | 5.0 | strategy+vcp |
| 7 | **ADANIGREEN** | Energy - Power | 1454.50 | STAGE_2 | 47.00 | 71.8% | ₹1,989 | 1.42x | 2.5 | strategy+vcp |
| 8 | **CPPLUS** | Other | 3343.50 | STAGE_2 | 46.80 | 80.1% | ₹4,980 | 1.18x | 5.0 | strategy |
| 9 | **AKUMS** | Other | 609.10 | STAGE_2 | 37.60 | 25.4% | ₹766 | 1.06x | 3.5 | strategy |
| 10 | **BAJAJCON** | FMCG & Consumer Goods | 566.25 | STAGE_2 | 67.30 | 58.8% | ₹747 | 1.60x | 1.5 | vcp+sector |

## Per-Stock Deep Dive

### 1. APARINDS — Capital Goods & Industrials

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=66.1, top sector strength=66

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **next buy**.

**What the company does:** Apar, founded by Mr. Dharmsinh D. Desai in 1958, is a market leader in India with a global presence. Contributing to India’s process of electrification it started from manufacturing power transmission cables to having three broad business segments, which are Conductors, Transformer and specialty oils (TSO), and Power/telecom Cables. [1] [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/APARINDS/*

**Thesis:** Stage-2 EMA stack (Price ₹14551 > EMA20 > EMA50 > EMA200) · Momentum RSI 68 · Within 5% of 52w high · Revenue YoY +27% · OCF/PAT 0.99

**Technical view:** RSI 68.4, 1Y return 80.7%, dist from 52w high -2.8%.

**Fundamental view:** Latest qtr revenue 26.7% YoY, PAT 1.2% YoY; 4Y CAGR revenue 10.7% / PAT 11.2%; ROCE —%; debt trend rising; OCF/PAT 0.99.

**Sector view:** Sector strength 66.42

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- Debt rising ₹+371 Cr (3Y)

**Action:** Enter ₹13254-₹14551; stop ₹11927; signal BUY.

**Targets:** 2M ₹16,541 · 4M ₹17,868 · 6M ₹19,298  
**Stop:** ₹11,927 · **Risk/Reward (4M):** 1.26x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 8%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹14551.00 · 1D 3.3% · 1W 6.1% · 1M 17.1%
- Stage **STAGE_2** (score 0.76) · Stance **BULLISH** · Signal **BUY**
- Investment score 66.10 (tech 80.00, fund 57.41)
- Relative Strength 34.2% vs Nifty 500; Supertrend BULLISH around ₹12447.60

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹14551.00 |
| EMA 20 / 50 / 200 | ₹13253.93 / ₹12318.04 / ₹10184.89 |
| EMA50 slope (20d) | 10.21% |
| RSI(14) | 68.36 |
| ATR(14) | ₹663.43 (4.56%) |
| 52W High / Low | ₹14970.00 / ₹6801.00 |
| Distance from 52W high | -2.8% |
| Returns 1M / 3M / 6M / 1Y | 16.8% / 43.5% / 63.5% / 80.7% |
| Last-day volume vs 20d avg | 2.99x |

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

### 2. JNKINDIA — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=64.8

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **open position**.

**What the company does:** JIncorporated in 2010, JNK India Ltd is in the business of Technology based EPC Contracts and Solutions in Renewable Energy [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/JNKINDIA/*

**Thesis:** Stage-2 EMA stack (Price ₹470 > EMA20 > EMA50 > EMA200) · RS 112% vs Nifty 500 · Momentum RSI 68 · PAT YoY +154% · Revenue YoY +77%

**Technical view:** RSI 67.7, 1Y return 39.1%, dist from 52w high -8.0%.

**Fundamental view:** Latest qtr revenue 77.0% YoY, PAT 153.8% YoY; 4Y CAGR revenue 29.0% / PAT 15.9%; ROCE —%; debt trend stable; OCF/PAT -0.03.

**Sector view:** Sector strength 78.54

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 600bps vs 4Q avg

**Key risks:**
- OCF/PAT -0.03 weak earnings quality

**Action:** Enter ₹406-₹470; stop ₹341; signal HOLD.

**Targets:** 2M ₹567 · 4M ₹631 · 6M ₹696  
**Stop:** ₹341 · **Risk/Reward (4M):** 1.25x  
**Risk score:** 4.0 / 10 (MEDIUM) · **Suggested size:** 8%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹470.00 · 1D -5.6% · 1W 11.5% · 1M 38.1%
- Stage **STAGE_2** (score 0.91) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 64.80 (tech 47.30, fund 81.85)
- Relative Strength 111.5% vs Nifty 500; Supertrend BULLISH around ₹389.44

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹470.00 |
| EMA 20 / 50 / 200 | ₹405.93 / ₹359.25 / ₹310.32 |
| EMA50 slope (20d) | 17.01% |
| RSI(14) | 67.70 |
| ATR(14) | ₹32.28 (6.87%) |
| 52W High / Low | ₹511.00 / ₹200.92 |
| Distance from 52W high | -8.0% |
| Returns 1M / 3M / 6M / 1Y | 33.7% / 109.5% / 107.6% / 39.1% |
| Last-day volume vs 20d avg | 0.96x |

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

### 3. HONASA — MNC

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=63.0, top sector strength=57

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **next buy**.

**What the company does:** Incorporated in 2016, Honasa Consumer Limited (HCL) provides beauty and personal care products through its digital platform. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/HONASA/*

**Thesis:** Stage-2 EMA stack (Price ₹418 > EMA20 > EMA50 > EMA200) · Momentum RSI 70 · Within 5% of 52w high · PAT YoY +176% · Revenue YoY +23% · Net cash ₹137 Cr · OCF/PAT 0.90

**Technical view:** RSI 69.5, 1Y return 31.1%, dist from 52w high -4.7%.

**Fundamental view:** Latest qtr revenue 23.0% YoY, PAT 176.0% YoY; 4Y CAGR revenue 11.0% / PAT —%; ROCE —%; debt trend stable; OCF/PAT 0.90.

**Sector view:** Sector strength 57.06

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 683bps vs 4Q avg

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹395-₹418; stop ₹353; signal BUY.

**Targets:** 2M ₹473 · 4M ₹510 · 6M ₹551  
**Stop:** ₹353 · **Risk/Reward (4M):** 1.44x  
**Risk score:** 1.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **HIGH** — 7 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹417.65 · 1D 0.7% · 1W 0.1% · 1M 20.3%
- Stage **STAGE_2** (score 0.93) · Stance **BULLISH** · Signal **BUY**
- Investment score 63.00 (tech 76.00, fund 59.69)
- Relative Strength 37.1% vs Nifty 500; Supertrend BULLISH around ₹377.23

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹417.65 |
| EMA 20 / 50 / 200 | ₹394.60 / ₹364.41 / ₹318.03 |
| EMA50 slope (20d) | 12.03% |
| RSI(14) | 69.51 |
| ATR(14) | ₹18.47 (4.42%) |
| 52W High / Low | ₹438.35 / ₹248.40 |
| Distance from 52W high | -4.7% |
| Returns 1M / 3M / 6M / 1Y | 20.0% / 45.6% / 50.2% / 31.1% |
| Last-day volume vs 20d avg | 2.12x |

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
| Promoter holding | 35.5% |

---

### 4. APOLLO — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=61.2, VCP=83

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **open position**.

**What the company does:** Apollo Micro Systems Ltd is a pioneer in design, development, assembly and testing of electronic and electro mechanical solutions. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/APOLLO/*

**Thesis:** RS 98% vs Nifty 500 · PAT YoY +164% · Revenue YoY +81% · PAT 4Y CAGR 63%

**Technical view:** RSI 54.0, 1Y return 85.3%, dist from 52w high -14.6%.

**Fundamental view:** Latest qtr revenue 80.9% YoY, PAT 164.3% YoY; 4Y CAGR revenue 38.9% / PAT 63.4%; ROCE —%; debt trend rising; OCF/PAT -1.21.

**Sector view:** Sector strength 78.54

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- Debt rising ₹+335 Cr (3Y)
- OCF/PAT -1.21 weak earnings quality

**Action:** Enter ₹368-₹382; stop ₹312; signal HOLD.

**Targets:** 2M ₹465 · 4M ₹521 · 6M ₹599  
**Stop:** ₹312 · **Risk/Reward (4M):** 2.00x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **MEDIUM** — 4 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹381.75 · 1D -4.1% · 1W -8.9% · 1M 25.4%
- Stage **STAGE_2** (score 0.81) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 61.20 (tech 58.00, fund 54.74)
- Relative Strength 98.5% vs Nifty 500; Supertrend BULLISH around ₹333.95

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹381.75 |
| EMA 20 / 50 / 200 | ₹382.48 / ₹333.17 / ₹272.43 |
| EMA50 slope (20d) | 26.21% |
| RSI(14) | 53.97 |
| ATR(14) | ₹27.88 (7.30%) |
| 52W High / Low | ₹446.90 / ₹162.34 |
| Distance from 52W high | -14.6% |
| Returns 1M / 3M / 6M / 1Y | 29.5% / 82.0% / 45.8% / 85.3% |
| Last-day volume vs 20d avg | 0.52x |

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

### 5. CUPID — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=50.1

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **open position**.

**What the company does:** Established in 1993, CUPID Limited is India's premier manufacturer of male and female condoms, personal lubricant, and IVD kits. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/CUPID/*

**Thesis:** RS 80% vs Nifty 500 · PAT YoY +200% · Revenue YoY +114% · PAT 3Y CAGR 55% · Net cash ₹19 Cr

**Technical view:** RSI 76.3, 1Y return 604.1%, dist from 52w high -70.6%.

**Fundamental view:** Latest qtr revenue 114.3% YoY, PAT 200.0% YoY; 3Y CAGR revenue 33.9% / PAT 55.0%; ROCE —%; debt trend stable; OCF/PAT 0.43.

**Sector view:** Sector strength 78.54

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 140bps vs 4Q avg

**Key risks:**
- RSI 76 overbought

**Action:** Enter ₹134-₹155; stop ₹124; signal BUY.

**Targets:** 2M ₹170 · 4M ₹181 · 6M ₹208  
**Stop:** ₹124 · **Risk/Reward (4M):** 0.80x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 4%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹155.18 · 1D 3.0% · 1W 16.6% · 1M 27.1%
- Stage **STAGE_2** (score 0.82) · Stance **BULLISH** · Signal **BUY**
- Investment score 50.10 (tech 72.70, fund 52.86)
- Relative Strength 80.4% vs Nifty 500; Supertrend BULLISH around ₹135.20

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹155.18 |
| EMA 20 / 50 / 200 | ₹133.76 / ₹144.04 / ₹161.74 |
| EMA50 slope (20d) | -9.13% |
| RSI(14) | 76.29 |
| ATR(14) | ₹5.08 (3.28%) |
| 52W High / Low | ₹526.95 / ₹17.68 |
| Distance from 52W high | -70.6% |
| Returns 1M / 3M / 6M / 1Y | 29.7% / 69.4% / -57.5% / 604.1% |
| Last-day volume vs 20d avg | 2.77x |

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

### 6. HFCL — Railways & PSU Infra

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=47.6, VCP=74

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **open position**.

**What the company does:** HFCL Ltd (Himachal Futuristic Communications Limited) is a diverse telecom infrastructure enabler with active interest spanning telecom infrastructure development, system integration, and manufacture and supply of high end telecom equipment, Optical Fiber and Optic Fiber Cable (OFC). [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/HFCL/*

**Thesis:** RS 128% vs Nifty 500 · Revenue YoY +128%

**Technical view:** RSI 53.4, 1Y return 84.1%, dist from 52w high -21.7%.

**Fundamental view:** Latest qtr revenue 127.7% YoY, PAT -321.7% YoY; 4Y CAGR revenue 1.2% / PAT 0.2%; ROCE —%; debt trend rising; OCF/PAT -1.15.

**Sector view:** Sector strength 43.88

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 700bps vs 4Q avg

**Key risks:**
- Debt rising ₹+753 Cr (3Y)
- OCF/PAT -1.15 weak earnings quality

**Action:** Enter ₹158-₹164; stop ₹134; signal HOLD.

**Targets:** 2M ₹200 · 4M ₹223 · 6M ₹247  
**Stop:** ₹134 · **Risk/Reward (4M):** 2.00x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **LOW** — 2 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹163.68 · 1D -3.2% · 1W -16.9% · 1M 6.7%
- Stage **STAGE_2** (score 0.62) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 47.60 (tech 50.00, fund 10.00)
- Relative Strength 128.3% vs Nifty 500; Supertrend BEARISH around ₹202.02

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹163.68 |
| EMA 20 / 50 / 200 | ₹166.15 / ₹138.37 / ₹97.75 |
| EMA50 slope (20d) | 38.14% |
| RSI(14) | 53.35 |
| ATR(14) | ₹11.95 (7.30%) |
| 52W High / Low | ₹208.98 / ₹59.82 |
| Distance from 52W high | -21.7% |
| Returns 1M / 3M / 6M / 1Y | 10.8% / 139.3% / 137.1% / 84.1% |
| Last-day volume vs 20d avg | 0.91x |

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

### 7. ADANIGREEN — Energy - Power

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=47.0, VCP=77

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **open position**.

**What the company does:** Adani Green Energy Limited, incorporated in 2015, is a holding company of several subsidiaries carrying business of renewable power generation within the group and is primarily involved in renewable power generation and other ancillary activities. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/ADANIGREEN/*

**Thesis:** Stage-2 EMA stack (Price ₹1454 > EMA20 > EMA50 > EMA200) · RS 72% vs Nifty 500 · PAT YoY +34% · PAT 4Y CAGR 42% · OCF/PAT 5.10

**Technical view:** RSI 57.1, 1Y return 44.9%, dist from 52w high -5.8%.

**Fundamental view:** Latest qtr revenue 14.0% YoY, PAT 34.2% YoY; 4Y CAGR revenue 26.0% / PAT 42.0%; ROCE —%; debt trend rising; OCF/PAT 5.10.

**Sector view:** Sector strength 51.60

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- Debt rising ₹+38687 Cr (3Y)

**Action:** Enter ₹1427-₹1454; stop ₹1260; signal HOLD.

**Targets:** 2M ₹1,620 · 4M ₹1,730 · 6M ₹1,989  
**Stop:** ₹1,260 · **Risk/Reward (4M):** 1.42x  
**Risk score:** 2.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹1454.50 · 1D -1.9% · 1W 2.2% · 1M 6.4%
- Stage **STAGE_2** (score 0.73) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 47.00 (tech 48.00, fund 10.00)
- Relative Strength 71.8% vs Nifty 500; Supertrend BULLISH around ₹1342.14

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹1454.50 |
| EMA 20 / 50 / 200 | ₹1428.63 / ₹1299.07 / ₹1104.20 |
| EMA50 slope (20d) | 15.84% |
| RSI(14) | 57.08 |
| ATR(14) | ₹55.06 (3.79%) |
| 52W High / Low | ₹1544.80 / ₹765.00 |
| Distance from 52W high | -5.8% |
| Returns 1M / 3M / 6M / 1Y | 11.2% / 70.3% / 42.9% / 44.9% |
| Last-day volume vs 20d avg | 0.52x |

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

### 8. CPPLUS — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as open position; current Stage 2 inv=46.8

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **open position**.

**What the company does:** Aditya Infotech Limited (AIL) manufactures and provides video security and surveillance products, solutions, and services under the brand name 'CP Plus'. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/CPPLUS/*

**Thesis:** Stage-2 EMA stack (Price ₹3344 > EMA20 > EMA50 > EMA200) · RS 80% vs Nifty 500 · PAT YoY +207% · Revenue YoY +46% · PAT 4Y CAGR 40%

**Technical view:** RSI 72.4, 1Y return —%, dist from 52w high -10.0%.

**Fundamental view:** Latest qtr revenue 45.5% YoY, PAT 207.3% YoY; 4Y CAGR revenue 26.5% / PAT 39.6%; ROCE —%; debt trend falling; OCF/PAT 0.04.

**Sector view:** Sector strength 78.54

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 800bps vs 4Q avg

**Key risks:**
- RSI 72 overbought
- OCF/PAT 0.04 weak earnings quality

**Action:** Enter ₹3027-₹3344; stop ₹2507; signal HOLD.

**Targets:** 2M ₹3,935 · 4M ₹4,330 · 6M ₹4,980  
**Stop:** ₹2,507 · **Risk/Reward (4M):** 1.18x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **HIGH** — 5 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹3343.50 · 1D -2.7% · 1W -5.5% · 1M 33.6%
- Stage **STAGE_2** (score 0.76) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 46.80 (tech 52.00, fund 40.08)
- Relative Strength 80.1% vs Nifty 500; Supertrend BULLISH around ₹2912.18

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹3343.50 |
| EMA 20 / 50 / 200 | ₹3026.70 / ₹2584.98 / ₹1781.72 |
| EMA50 slope (20d) | 24.91% |
| RSI(14) | 72.36 |
| ATR(14) | ₹197.32 (5.90%) |
| 52W High / Low | ₹3714.40 / ₹1015.00 |
| Distance from 52W high | -10.0% |
| Returns 1M / 3M / 6M / 1Y | 33.2% / 103.8% / 121.1% / — |
| Last-day volume vs 20d avg | 0.87x |

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
| Promoter holding | 74.8% |

---

### 9. AKUMS — Other

**Why selected:** Portfolio lab best strategy `darvas_box_breakout_v1` confirms as next buy; current Stage 2 inv=37.6

**Portfolio lab confirmation:** `darvas_box_breakout_v1` (Darvas Box Breakout, rank 1, 101.77% return) marks this as **next buy**.

**What the company does:** Established in 2004, Akums Drugs and Pharmaceuticals Limited is a pharmaceutical contract development and manufacturing organization (CDMO) offering a comprehensive range of pharmaceutical products and services. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/AKUMS/*

**Thesis:** Stage-2 EMA stack (Price ₹609 > EMA20 > EMA50 > EMA200) · Within 5% of 52w high · OCF/PAT 4.61

**Technical view:** RSI 74.8, 1Y return 8.3%, dist from 52w high -1.9%.

**Fundamental view:** Latest qtr revenue 9.7% YoY, PAT -46.0% YoY; 4Y CAGR revenue 4.4% / PAT —%; ROCE —%; debt trend falling; OCF/PAT 4.61.

**Sector view:** Sector strength 78.54

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 180bps vs 4Q avg

**Key risks:**
- RSI 75 overbought

**Action:** Enter ₹548-₹609; stop ₹503; signal HOLD.

**Targets:** 2M ₹676 · 4M ₹721 · 6M ₹766  
**Stop:** ₹503 · **Risk/Reward (4M):** 1.06x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 8%

**Conviction:** **MEDIUM** — 3 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹609.10 · 1D 2.9% · 1W 9.7% · 1M 12.7%
- Stage **STAGE_2** (score 0.78) · Stance **BEARISH** · Signal **HOLD**
- Investment score 37.60 (tech 62.00, fund 10.00)
- Relative Strength 25.4% vs Nifty 500; Supertrend BULLISH around ₹531.88

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹609.10 |
| EMA 20 / 50 / 200 | ₹547.88 / ₹529.17 / ₹501.51 |
| EMA50 slope (20d) | 3.16% |
| RSI(14) | 74.78 |
| ATR(14) | ₹22.42 (3.68%) |
| 52W High / Low | ₹621.00 / ₹409.30 |
| Distance from 52W high | -1.9% |
| Returns 1M / 3M / 6M / 1Y | 15.3% / 28.4% / 44.7% / 8.3% |
| Last-day volume vs 20d avg | 4.69x |

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
| Promoter holding | 75.3% |

---

### 10. BAJAJCON — FMCG & Consumer Goods

**Why selected:** VCP-confirmed Stage 2 (vcp=77, inv=65.3) in top-ranked sector FMCG & Consumer Goods (strength=56)

**What the company does:** Bajaj Consumer Care is engaged in the business of cosmetics, toiletries and other personal care products. The Company has presence in both domestic and international markets.(Source : 201903 Annual Report Page No: 98)

*Company profile source: screener.in (live) — https://www.screener.in/company/BAJAJCON/*

**Thesis:** Stage-2 EMA stack (Price ₹566 > EMA20 > EMA50 > EMA200) · RS 59% vs Nifty 500 · Within 5% of 52w high · PAT YoY +106% · Revenue YoY +31% · Net cash ₹351 Cr · OCF/PAT 1.04

**Technical view:** RSI 59.2, 1Y return 225.4%, dist from 52w high -4.8%.

**Fundamental view:** Latest qtr revenue 30.8% YoY, PAT 106.5% YoY; 4Y CAGR revenue 7.3% / PAT 2.8%; ROCE —%; debt trend stable; OCF/PAT 1.04.

**Sector view:** Sector strength 55.88

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 800bps vs 4Q avg

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹550-₹566; stop ₹485; signal BUY.

**Targets:** 2M ₹644 · 4M ₹696 · 6M ₹747  
**Stop:** ₹485 · **Risk/Reward (4M):** 1.60x  
**Risk score:** 1.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **HIGH** — 7 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹566.25 · 1D 0.6% · 1W 1.3% · 1M 7.8%
- Stage **STAGE_2** (score 0.70) · Stance **BULLISH** · Signal **BUY**
- Investment score 67.30 (tech 72.70, fund 61.40)
- Relative Strength 58.8% vs Nifty 500; Supertrend BULLISH around ₹509.91

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-06-11) | ₹566.25 |
| EMA 20 / 50 / 200 | ₹550.00 / ₹500.49 / ₹361.37 |
| EMA50 slope (20d) | 16.10% |
| RSI(14) | 59.24 |
| ATR(14) | ₹25.86 (4.57%) |
| 52W High / Low | ₹594.80 / ₹168.25 |
| Distance from 52W high | -4.8% |
| Returns 1M / 3M / 6M / 1Y | 3.3% / 52.6% / 110.5% / 225.4% |
| Last-day volume vs 20d avg | 1.26x |

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

## Portfolio Construction

Equal-weight 10% per name baseline. Overweight HIGH-conviction names by +2%, halve LOW-conviction sizes. Cap sector exposure at 30%. Scale gross to 60-70% in elevated VIX regimes; cap per-trade risk at 1-2% of NAV via stop-distance × size.

**Sector spread:**

- Other: **5** name(s)
- Capital Goods & Industrials: **1** name(s)
- MNC: **1** name(s)
- Railways & PSU Infra: **1** name(s)
- Energy - Power: **1** name(s)
- FMCG & Consumer Goods: **1** name(s)

## Full Disclaimer

This report is provided strictly for educational, research, and learning purposes as part of a journey to understand how AI agents and rules-based agents can be applied to financial-market data. It is not investment advice, trading advice, portfolio advice, a research recommendation, or a solicitation to buy, sell, hold, short, or otherwise transact in any security, derivative, index, fund, or financial instrument. The information, scores, signals, narratives, charts, model outputs, and examples in this report must not be replicated, redistributed, automated, or used with any intent of trading, recommending trades, advising others, managing money, or making financial decisions. Anyone choosing to use, interpret, adapt, copy, replicate, distribute, or act on this information does so entirely at their own risk, responsibility, and legal and regulatory obligation. Agent Adda is not a SEBI-registered investment adviser, research analyst, portfolio manager, broker, or any other SEBI-registered market intermediary. Agent Adda, its creators, contributors, systems, agents, and associated persons accept no responsibility or liability for losses, damages, legal consequences, regulatory consequences, tax consequences, opportunity costs, or any other implications arising directly or indirectly from the use of this information by any person or organization. All market data can be delayed, incomplete, inaccurate, stale, or affected by corporate actions, liquidity, data-provider issues, model limitations, prompt limitations, or rule-design limitations. Users must consult qualified SEBI-registered professionals and independently verify all facts before making any financial or legal decision.
