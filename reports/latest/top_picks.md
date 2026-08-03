# Top Investment Picks Analysis — 2026-08-03

*Agent Adda - Market Intelligence Agent*

**Generated:** 2026-08-03 19:37 IST  
**Sources:** Sector Rotation Report + Stage 2 Tracker + Swing Research Shortlist + PostgreSQL `scores.*`, `market.equity_eod`

> **Disclaimer:** This report is not investment advice. It is a learning journey demonstrating how AI and rules-based agents can be applied to financial markets. Validate all data, prices, liquidity, corporate events, and risk independently before making any financial decision.

## Executive Summary

Mechanically-synthesised basket of 10 stocks combining sector-rotation leadership and Weinstein stage-2 momentum, deep-screened across P&L, BS, CF, fundamental scores and corporate events. LLM unavailable — rule-based narrative.

**Macro context:** Snapshot 2026-08-03: 992 stocks scanned; Stage 2 count 326 vs Stage 4 146; BUY/STRONG_BUY signals 103; mean RS vs Nifty 500 4.7%.

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

| # | Symbol | Sector | Sub-sector | Price | Stage | Inv.Score | RS% | 6M Tgt | RR(4M) | Risk | Source |
|---|---|---|---|---:|---|---:|---:|---:|---:|:---:|---|
| 1 | **RADICO** | FMCG & Consumer Goods | Unmapped | 4459.10 | STAGE_2 | 54.70 | 20.1% | ₹5,776 | 0.84x | 3.0 | strategy+sector+s2 |
| 2 | **ATHERENERG** | EV & Auto Ancillaries | Auto Ancillaries | 1272.70 | STAGE_2 | 66.30 | 38.9% | ₹1,658 | 1.50x | 1.5 | vcp+sector |
| 3 | **SKYGOLD** | Consumer Durables | Consumer Durables | 691.85 | STAGE_2 | 65.20 | 42.1% | ₹977 | 1.17x | 5.0 | vcp+sector |
| 4 | **RPTECH** | IT & Technology | IT Hardware Distribution | 883.65 | STAGE_2 | 67.30 | 56.9% | ₹1,166 | 0.98x | 5.0 | vcp+sector |
| 5 | **RAINBOW** | Chemicals & Specialty | Specialty Chemicals | 1545.60 | STAGE_2 | 59.90 | 9.0% | ₹1,829 | 1.29x | 2.5 | vcp+sector |
| 6 | **CUPID** | Pharma & Healthcare | Medical Devices & Sexual Wellness | 230.95 | STAGE_2 | 60.20 | 86.9% | ₹316 | 1.02x | 2.0 | vcp+sector |
| 7 | **MBAPL** | Metals & Mining | Unmapped | 160.01 | STAGE_2 | 54.50 | 15.4% | ₹220 | 2.00x | 2.5 | vcp+sector |
| 8 | **BHARATFORG** | EV & Auto Ancillaries | Auto Ancillaries | 2211.00 | STAGE_2 | 57.00 | 11.4% | ₹2,560 | 1.31x | 1.5 | vcp+sector |
| 9 | **NITCO** | FMCG & Consumer Goods | Unmapped | 108.09 | STAGE_2 | 55.00 | 7.2% | ₹142 | 2.00x | 3.0 | vcp+sector |
| 10 | **NYKAA** | Other | Unmapped | 344.90 | STAGE_2 | 61.40 | 19.3% | ₹439 | 0.78x | 3.5 | strategy+vcp |

## Per-Stock Deep Dive

### 1. RADICO — FMCG & Consumer Goods / Unmapped

**Why selected:** Portfolio lab best strategy `stage2_continuation_v1` confirms as open position; current Stage 2 inv=54.7, top sector strength=72

**Portfolio lab confirmation:** `stage2_continuation_v1` (Stage 2 Continuation, rank 1, 11.02% return) marks this as **open position**.

**What the company does:** Incorporated in the year 1943, Radico Khaitan is one of the most recognised IMFL (Indian Made Foreign Liquor) brands in India. [1] The company was initially known as Rampur Distillery Company and was focussed on distillation and bottling for branded players and canteen stores of armed forces. Later on in the year 1997, Radico Khaitan ventured into its own branded IMFL products and launched its first brand 8PM whisky which became its millionarie brand within a year of its launch. [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/RADICO/*

**Thesis:** Stage-2 EMA stack (Price ₹4459 > EMA20 > EMA50 > EMA200) · Within 5% of 52w high · PAT YoY +76% · PAT 4Y CAGR 34% · OCF/PAT 1.06

**Technical view:** RSI 76.8, 1Y return 65.0%, dist from 52w high -0.8%.

**Fundamental view:** Latest qtr revenue 11.8% YoY, PAT 75.6% YoY; 4Y CAGR revenue 18.7% / PAT 33.7%; ROCE —%; debt trend falling; OCF/PAT 1.06.

**Sector view:** Sector strength 66.80

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 517bps vs 4Q avg

**Key risks:**
- RSI 77 overbought

**Action:** Enter ₹4163-₹4459; stop ₹3786; signal HOLD.

**Targets:** 2M ₹4,797 · 4M ₹5,023 · 6M ₹5,776  
**Stop:** ₹3,786 · **Risk/Reward (4M):** 0.84x  
**Risk score:** 3.0 / 10 (LOW) · **Suggested size:** 4%

**Conviction:** **HIGH** — 5 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹4459.10 · 1D 2.7% · 1W 7.5% · 1M 8.6%
- Stage **STAGE_2** (score 0.74) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 54.70 (tech 46.70, fund 82.62)
- Relative Strength 20.1% vs Nifty 500; Supertrend BULLISH around ₹4039.58

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹4459.10 |
| EMA 20 / 50 / 200 | ₹4163.42 / ₹3903.16 / ₹3367.79 |
| EMA50 slope (20d) | 9.74% |
| RSI(14) | 76.78 |
| ATR(14) | ₹112.69 (2.53%) |
| 52W High / Low | ₹4494.40 / ₹2500.00 |
| Distance from 52W high | -0.8% |
| Returns 1M / 3M / 6M / 1Y | 14.6% / 33.5% / 65.1% / 65.0% |
| Last-day volume vs 20d avg | 0.75x |

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

### 2. ATHERENERG — EV & Auto Ancillaries / Auto Ancillaries

**Why selected:** VCP-confirmed Stage 2 (vcp=74, inv=66.6) in top-ranked sector EV & Auto Ancillaries (strength=84)

**What the company does:** Incorporated in 2013, Ather Energy ltd is an Indian electric two-wheeler (E2W) company engaged in the design, development, and in-house assembly of electric scooters, battery packs, charging infrastructure, and supporting software systems [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/ATHERENERG/*

**Thesis:** Stage-2 EMA stack (Price ₹1273 > EMA20 > EMA50 > EMA200) · Momentum RSI 63

**Technical view:** RSI 63.4, 1Y return 275.5%, dist from 52w high -5.4%.

**Fundamental view:** Latest qtr revenue —% YoY, PAT —% YoY; —Y CAGR revenue —% / PAT —%; ROCE -19.8%; debt trend —; OCF/PAT —.

**Sector view:** Sector strength 68.66

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 1080bps vs 4Q avg

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹1218-₹1273; stop ₹1090; signal BUY.

**Targets:** 2M ₹1,438 · 4M ₹1,548 · 6M ₹1,658  
**Stop:** ₹1,090 · **Risk/Reward (4M):** 1.50x  
**Risk score:** 1.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **LOW** — 2 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹1272.70 · 1D 1.0% · 1W 4.8% · 1M 13.1%
- Stage **STAGE_2** (score 0.78) · Stance **BULLISH** · Signal **BUY**
- Investment score 66.30 (tech 73.30, fund 63.36)
- Relative Strength 38.9% vs Nifty 500; Supertrend BULLISH around ₹1128.22

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹1272.70 |
| EMA 20 / 50 / 200 | ₹1217.70 / ₹1123.56 / ₹850.35 |
| EMA50 slope (20d) | 14.64% |
| RSI(14) | 63.41 |
| ATR(14) | ₹54.99 (4.32%) |
| 52W High / Low | ₹1345.00 / ₹336.35 |
| Distance from 52W high | -5.4% |
| Returns 1M / 3M / 6M / 1Y | 12.6% / 35.7% / 111.6% / 275.5% |
| Last-day volume vs 20d avg | 0.84x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | -33.4% |
| ROCE | -19.8% |
| Debt / Equity | — |
| Promoter holding | 39.6% |

---

### 3. SKYGOLD — Consumer Durables / Consumer Durables

**Why selected:** VCP-confirmed Stage 2 (vcp=73, inv=63.6) in top-ranked sector Consumer Durables (strength=64)

**What the company does:** Sky Gold Limited is engaged in the business of designing, manufacturing, and marketing gold jewellery. The co. follows a B2B model where the products are mainly sold to mid-range jewellers and boutique stores who sell these products through online platforms and retail stores. [1] [2] [3]

*Company profile source: screener.in (live) — https://www.screener.in/company/SKYGOLD/*

**Thesis:** Momentum RSI 69 · Within 5% of 52w high · PAT YoY +139% · Revenue YoY +81% · PAT 4Y CAGR 102%

**Technical view:** RSI 69.3, 1Y return —%, dist from 52w high -1.2%.

**Fundamental view:** Latest qtr revenue 80.7% YoY, PAT 139.5% YoY; 4Y CAGR revenue 68.2% / PAT 101.8%; ROCE —%; debt trend rising; OCF/PAT -0.16.

**Sector view:** Sector strength 48.54

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 60bps vs 4Q avg

**Key risks:**
- Debt rising ₹+539 Cr (3Y)
- OCF/PAT -0.16 weak earnings quality

**Action:** Enter ₹633-₹692; stop ₹558; signal BUY.

**Targets:** 2M ₹786 · 4M ₹849 · 6M ₹977  
**Stop:** ₹558 · **Risk/Reward (4M):** 1.17x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 6%

**Conviction:** **HIGH** — 5 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹691.85 · 1D 7.5% · 1W 3.0% · 1M 24.5%
- Stage **STAGE_2** (score 0.79) · Stance **BULLISH** · Signal **BUY**
- Investment score 65.20 (tech 55.30, fund 78.60)
- Relative Strength 42.1% vs Nifty 500; Supertrend BULLISH around ₹585.04

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹691.85 |
| EMA 20 / 50 / 200 | ₹633.21 / ₹575.10 / ₹— |
| EMA50 slope (20d) | 17.19% |
| RSI(14) | 69.32 |
| ATR(14) | ₹31.47 (4.55%) |
| 52W High / Low | ₹700.00 / ₹297.95 |
| Distance from 52W high | -1.2% |
| Returns 1M / 3M / 6M / 1Y | 23.5% / 51.5% / 119.5% / — |
| Last-day volume vs 20d avg | 0.85x |

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
| Promoter holding | 51.7% |

---

### 4. RPTECH — IT & Technology / IT Hardware Distribution

**Why selected:** VCP-confirmed Stage 2 (vcp=75, inv=62.3) in top-ranked sector IT & Technology (strength=80)

**What the company does:** Incorporated in 1989, Rashi Peripherals Ltd operates in ICT product distribution business and after-sale services [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/RPTECH/*

**Thesis:** Stage-2 EMA stack (Price ₹884 > EMA20 > EMA50 > EMA200) · RS 57% vs Nifty 500 · Within 5% of 52w high · PAT YoY +64% · Revenue YoY +51%

**Technical view:** RSI 73.5, 1Y return 205.0%, dist from 52w high -0.6%.

**Fundamental view:** Latest qtr revenue 51.0% YoY, PAT 64.2% YoY; 4Y CAGR revenue 14.2% / PAT 11.4%; ROCE —%; debt trend rising; OCF/PAT 0.40.

**Sector view:** Sector strength 65.06

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- RSI 73 overbought
- Debt rising ₹+291 Cr (3Y)

**Action:** Enter ₹780-₹884; stop ₹683; signal BUY.

**Targets:** 2M ₹1,001 · 4M ₹1,080 · 6M ₹1,166  
**Stop:** ₹683 · **Risk/Reward (4M):** 0.98x  
**Risk score:** 5.0 / 10 (MEDIUM) · **Suggested size:** 4%

**Conviction:** **HIGH** — 5 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹883.65 · 1D 6.0% · 1W 10.3% · 1M 16.1%
- Stage **STAGE_2** (score 0.80) · Stance **BULLISH** · Signal **BUY**
- Investment score 67.30 (tech 77.30, fund 55.77)
- Relative Strength 56.9% vs Nifty 500; Supertrend BULLISH around ₹740.63

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹883.65 |
| EMA 20 / 50 / 200 | ₹780.25 / ₹704.56 / ₹499.84 |
| EMA50 slope (20d) | 15.84% |
| RSI(14) | 73.50 |
| ATR(14) | ₹39.26 (4.44%) |
| 52W High / Low | ₹889.00 / ₹275.60 |
| Distance from 52W high | -0.6% |
| Returns 1M / 3M / 6M / 1Y | 16.6% / 75.9% / 146.1% / 205.0% |
| Last-day volume vs 20d avg | 2.22x |

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

### 5. RAINBOW — Chemicals & Specialty / Specialty Chemicals

**Why selected:** VCP-confirmed Stage 2 (vcp=72, inv=61.4) in top-ranked sector Chemicals & Specialty (strength=70)

**What the company does:** Rainbow Children's Medicare Limited operates a multi-specialty pediatric, obstetrics, and gynecology hospital chain in India. The company offers a wide range of services such as newborn and pediatric intensive care, pediatric multi-specialty services, pediatric quaternary care, obstetrics, and gynecology. [1] It is country’s largest pediatric hospital chain with 16 hospitals spread across 6 cities. [2]

*Company profile source: screener.in (live) — https://www.screener.in/company/RAINBOW/*

**Thesis:** Momentum RSI 70 · Within 5% of 52w high · Revenue YoY +33% · OCF/PAT 1.45

**Technical view:** RSI 69.7, 1Y return —%, dist from 52w high -1.9%.

**Fundamental view:** Latest qtr revenue 33.1% YoY, PAT 16.7% YoY; 4Y CAGR revenue 11.6% / PAT 8.1%; ROCE —%; debt trend rising; OCF/PAT 1.45.

**Sector view:** Sector strength 54.78

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- Debt rising ₹+126 Cr (3Y)

**Action:** Enter ₹1484-₹1546; stop ₹1388; signal HOLD.

**Targets:** 2M ₹1,667 · 4M ₹1,748 · 6M ₹1,829  
**Stop:** ₹1,388 · **Risk/Reward (4M):** 1.29x  
**Risk score:** 2.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **MEDIUM** — 4 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹1545.60 · 1D 1.3% · 1W 4.2% · 1M 7.2%
- Stage **STAGE_2** (score 0.63) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 59.90 (tech 57.30, fund 74.88)
- Relative Strength 9.0% vs Nifty 500; Supertrend BULLISH around ₹1420.31

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹1545.60 |
| EMA 20 / 50 / 200 | ₹1483.68 / ₹1431.43 / ₹— |
| EMA50 slope (20d) | 5.16% |
| RSI(14) | 69.67 |
| ATR(14) | ₹40.54 (2.62%) |
| 52W High / Low | ₹1574.80 / ₹1084.00 |
| Distance from 52W high | -1.9% |
| Returns 1M / 3M / 6M / 1Y | 7.3% / 22.6% / 30.0% / — |
| Last-day volume vs 20d avg | 1.82x |

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
| Promoter holding | 49.8% |

---

### 6. CUPID — Pharma & Healthcare / Medical Devices & Sexual Wellness

**Why selected:** VCP-confirmed Stage 2 (vcp=75, inv=60.6) in top-ranked sector Pharma & Healthcare (strength=78)

**What the company does:** Established in 1993, CUPID Limited is India's premier manufacturer of male and female condoms, personal lubricant, and IVD kits. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/CUPID/*

**Thesis:** RS 87% vs Nifty 500 · Momentum RSI 68 · PAT YoY +200% · Revenue YoY +114% · PAT 3Y CAGR 55% · Net cash ₹19 Cr

**Technical view:** RSI 67.6, 1Y return 671.9%, dist from 52w high -56.2%.

**Fundamental view:** Latest qtr revenue 114.3% YoY, PAT 200.0% YoY; 3Y CAGR revenue 33.9% / PAT 55.0%; ROCE —%; debt trend stable; OCF/PAT 0.43.

**Sector view:** Sector strength 62.66

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 140bps vs 4Q avg

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹215-₹231; stop ₹188; signal HOLD.

**Targets:** 2M ₹257 · 4M ₹275 · 6M ₹316  
**Stop:** ₹188 · **Risk/Reward (4M):** 1.02x  
**Risk score:** 2.0 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **HIGH** — 6 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹230.95 · 1D 0.1% · 1W 4.3% · 1M 8.4%
- Stage **STAGE_2** (score 0.96) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 60.20 (tech 56.00, fund 52.86)
- Relative Strength 86.9% vs Nifty 500; Supertrend BULLISH around ₹209.39

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹230.95 |
| EMA 20 / 50 / 200 | ₹214.98 / ₹193.36 / ₹198.87 |
| EMA50 slope (20d) | 18.91% |
| RSI(14) | 67.58 |
| ATR(14) | ₹8.82 (3.82%) |
| 52W High / Low | ₹526.95 / ₹29.60 |
| Distance from 52W high | -56.2% |
| Returns 1M / 3M / 6M / 1Y | 16.1% / 76.5% / -40.8% / 671.9% |
| Last-day volume vs 20d avg | 0.25x |

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
| Promoter holding | 46.2% |

---

### 7. MBAPL — Metals & Mining / Unmapped

**Why selected:** VCP-confirmed Stage 2 (vcp=79, inv=59.9) in top-ranked sector Metals & Mining (strength=58)

**What the company does:** Madhya Bharat Agro Products Ltd, part of Ostwal Group, is engaged in the business of manufacturing fertiliser and chemical products. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/MBAPL/*

**Thesis:** ROE 31%

**Technical view:** RSI 29.3, 1Y return —%, dist from 52w high -73.8%.

**Fundamental view:** Latest qtr revenue —% YoY, PAT —% YoY; —Y CAGR revenue —% / PAT —%; ROCE 19.3%; debt trend —; OCF/PAT —.

**Sector view:** Sector strength 52.66

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹156-₹160; stop ₹139; signal HOLD.

**Targets:** 2M ₹186 · 4M ₹203 · 6M ₹220  
**Stop:** ₹139 · **Risk/Reward (4M):** 2.00x  
**Risk score:** 2.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **LOW** — 1 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹160.01 · 1D -0.1% · 1W -2.4% · 1M 34.0%
- Stage **STAGE_2** (score 0.86) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 54.50 (tech 61.30, fund 66.71)
- Relative Strength 15.4% vs Nifty 500; Supertrend BULLISH around ₹139.16

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹160.01 |
| EMA 20 / 50 / 200 | ₹195.47 / ₹310.70 / ₹— |
| EMA50 slope (20d) | -39.45% |
| RSI(14) | 29.32 |
| ATR(14) | ₹8.59 (5.37%) |
| 52W High / Low | ₹610.90 / ₹109.75 |
| Distance from 52W high | -73.8% |
| Returns 1M / 3M / 6M / 1Y | 27.9% / -70.8% / -60.1% / — |
| Last-day volume vs 20d avg | 0.31x |

**Fundamentals:**

| Metric | Value |
|---|---:|
| Piotroski F-score | — / 9 |
| Altman Z-score | — |
| Beneish M-score | — |
| Forensic risk | — |
| Revenue growth 3Y | — |
| PAT growth 3Y | — |
| ROE | 31.3% |
| ROCE | 19.3% |
| Debt / Equity | — |
| Promoter holding | 74.8% |

---

### 8. BHARATFORG — EV & Auto Ancillaries / Auto Ancillaries

**Why selected:** VCP-confirmed Stage 2 (vcp=78, inv=59.3) in top-ranked sector EV & Auto Ancillaries (strength=84)

**What the company does:** Bharat Forge is engaged in the manufacturing and selling of forged and machined Compoundant for auto and industry sector.(Source : 201903 Annual Report Page No: 123)

*Company profile source: screener.in (live) — https://www.screener.in/company/BHARATFORG/*

**Thesis:** Stage-2 EMA stack (Price ₹2211 > EMA20 > EMA50 > EMA200) · Momentum RSI 63 · Within 5% of 52w high · Revenue YoY +18% · OCF/PAT 1.37

**Technical view:** RSI 62.6, 1Y return 83.6%, dist from 52w high -1.2%.

**Fundamental view:** Latest qtr revenue 17.5% YoY, PAT -17.7% YoY; 4Y CAGR revenue 12.6% / PAT 0.3%; ROCE —%; debt trend falling; OCF/PAT 1.37.

**Sector view:** Sector strength 68.66

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- No quantitative red flag in dossier

**Action:** Enter ₹2158-₹2211; stop ₹2019; signal HOLD.

**Targets:** 2M ₹2,351 · 4M ₹2,462 · 6M ₹2,560  
**Stop:** ₹2,019 · **Risk/Reward (4M):** 1.31x  
**Risk score:** 1.5 / 10 (LOW) · **Suggested size:** 8%

**Conviction:** **HIGH** — 5 positive · 0 negative factors flagged

**Snapshot:**

- Price ₹2211.00 · 1D 0.5% · 1W 1.4% · 1M 3.4%
- Stage **STAGE_2** (score 0.65) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 57.00 (tech 63.30, fund 54.83)
- Relative Strength 11.4% vs Nifty 500; Supertrend BULLISH around ₹2089.76

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹2211.00 |
| EMA 20 / 50 / 200 | ₹2157.61 / ₹2081.38 / ₹1731.00 |
| EMA50 slope (20d) | 5.03% |
| RSI(14) | 62.60 |
| ATR(14) | ₹46.56 (2.11%) |
| 52W High / Low | ₹2238.00 / ₹1100.50 |
| Distance from 52W high | -1.2% |
| Returns 1M / 3M / 6M / 1Y | 3.5% / 18.5% / 53.8% / 83.6% |
| Last-day volume vs 20d avg | 0.79x |

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
| Promoter holding | 44.1% |

---

### 9. NITCO — FMCG & Consumer Goods / Unmapped

**Why selected:** VCP-confirmed Stage 2 (vcp=74, inv=59.1) in top-ranked sector FMCG & Consumer Goods (strength=72)

**What the company does:** Incorporated in 1966, NITCO Ltd is in the tiles and marble business [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/NITCO/*

**Thesis:** Stage-2 EMA stack (Price ₹108 > EMA20 > EMA50 > EMA200) · PAT YoY +169% · Revenue YoY +63%

**Technical view:** RSI 53.2, 1Y return -19.2%, dist from 52w high -23.9%.

**Fundamental view:** Latest qtr revenue 62.9% YoY, PAT 168.6% YoY; 4Y CAGR revenue 7.2% / PAT —%; ROCE —%; debt trend falling; OCF/PAT -5.28.

**Sector view:** Sector strength 66.80

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- Watch next quarterly print

**Key risks:**
- OCF/PAT -5.28 weak earnings quality

**Action:** Enter ₹106-₹108; stop ₹96; signal HOLD.

**Targets:** 2M ₹123 · 4M ₹132 · 6M ₹142  
**Stop:** ₹96 · **Risk/Reward (4M):** 2.00x  
**Risk score:** 3.0 / 10 (LOW) · **Suggested size:** 10%

**Conviction:** **MEDIUM** — 3 positive · 1 negative factors flagged

**Snapshot:**

- Price ₹108.09 · 1D 0.5% · 1W 0.5% · 1M -6.0%
- Stage **STAGE_2** (score 0.50) · Stance **NEUTRAL** · Signal **HOLD**
- Investment score 55.00 (tech 44.70, fund 71.55)
- Relative Strength 7.2% vs Nifty 500; Supertrend BULLISH around ₹98.15

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹108.09 |
| EMA 20 / 50 / 200 | ₹106.13 / ₹103.71 / ₹100.99 |
| EMA50 slope (20d) | 3.14% |
| RSI(14) | 53.17 |
| ATR(14) | ₹4.84 (4.48%) |
| 52W High / Low | ₹141.99 / ₹64.00 |
| Distance from 52W high | -23.9% |
| Returns 1M / 3M / 6M / 1Y | -7.1% / 13.2% / 32.7% / -19.2% |
| Last-day volume vs 20d avg | 0.81x |

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
| Promoter holding | 20.2% |

---

### 10. NYKAA — Other / Unmapped

**Why selected:** Portfolio lab best strategy `stage2_continuation_v1` confirms as open position; current Stage 2 inv=61.4, VCP=76

**Portfolio lab confirmation:** `stage2_continuation_v1` (Stage 2 Continuation, rank 1, 11.02% return) marks this as **open position**.

**What the company does:** FSN E-commerce Ventures Ltd. (FSNEV) popularly known as "Nykaa" is a digitally native consumer technology platform, delivering a content-led, lifestyle retail experience to consumers. The company has a diverse portfolio of beauty, personal care, and fashion products, including owned brand products manufactured by it. [1]

*Company profile source: screener.in (live) — https://www.screener.in/company/NYKAA/*

**Thesis:** Stage-2 EMA stack (Price ₹345 > EMA20 > EMA50 > EMA200) · Within 5% of 52w high · PAT YoY +316% · Revenue YoY +28% · PAT 4Y CAGR 49% · OCF/PAT 3.16

**Technical view:** RSI 74.8, 1Y return 65.2%, dist from 52w high 0.0%.

**Fundamental view:** Latest qtr revenue 28.4% YoY, PAT 315.8% YoY; 4Y CAGR revenue 27.7% / PAT 49.4%; ROCE —%; debt trend rising; OCF/PAT 3.16.

**Sector view:** Sector strength 78.56

**Valuation:** Quantitative valuation not in dossier — defer to qualitative read.

**Key catalysts:**
- OPM expanded 120bps vs 4Q avg

**Key risks:**
- RSI 75 overbought
- Debt rising ₹+269 Cr (3Y)

**Action:** Enter ₹325-₹345; stop ₹298; signal BUY.

**Targets:** 2M ₹367 · 4M ₹382 · 6M ₹439  
**Stop:** ₹298 · **Risk/Reward (4M):** 0.78x  
**Risk score:** 3.5 / 10 (MEDIUM) · **Suggested size:** 4%

**Conviction:** **HIGH** — 6 positive · 2 negative factors flagged

**Snapshot:**

- Price ₹344.90 · 1D 3.5% · 1W 5.5% · 1M 10.0%
- Stage **STAGE_2** (score 0.73) · Stance **BULLISH** · Signal **BUY**
- Investment score 61.40 (tech 57.30, fund 79.13)
- Relative Strength 19.3% vs Nifty 500; Supertrend BULLISH around ₹316.68

**Technicals:**

| Metric | Value |
|---|---:|
| Close (2026-08-03) | ₹344.90 |
| EMA 20 / 50 / 200 | ₹324.89 / ₹306.99 / ₹271.93 |
| EMA50 slope (20d) | 9.11% |
| RSI(14) | 74.75 |
| ATR(14) | ₹7.39 (2.14%) |
| 52W High / Low | ₹344.90 / ₹200.14 |
| Distance from 52W high | 0.0% |
| Returns 1M / 3M / 6M / 1Y | 11.2% / 27.7% / 45.0% / 65.2% |
| Last-day volume vs 20d avg | 1.16x |

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
| Promoter holding | 52.1% |

---

## Portfolio Construction

Equal-weight 10% per name baseline. Overweight HIGH-conviction names by +2%, halve LOW-conviction sizes. Cap sector exposure at 30%. Scale gross to 60-70% in elevated VIX regimes; cap per-trade risk at 1-2% of NAV via stop-distance × size.

**Sector spread:**

- FMCG & Consumer Goods: **2** name(s)
- EV & Auto Ancillaries: **2** name(s)
- Consumer Durables: **1** name(s)
- IT & Technology: **1** name(s)
- Chemicals & Specialty: **1** name(s)
- Pharma & Healthcare: **1** name(s)
- Metals & Mining: **1** name(s)
- Other: **1** name(s)

## Full Disclaimer

This report is provided strictly for educational, research, and learning purposes as part of a journey to understand how AI agents and rules-based agents can be applied to financial-market data. It is not investment advice, trading advice, portfolio advice, a research recommendation, or a solicitation to buy, sell, hold, short, or otherwise transact in any security, derivative, index, fund, or financial instrument. The information, scores, signals, narratives, charts, model outputs, and examples in this report must not be replicated, redistributed, automated, or used with any intent of trading, recommending trades, advising others, managing money, or making financial decisions. Anyone choosing to use, interpret, adapt, copy, replicate, distribute, or act on this information does so entirely at their own risk, responsibility, and legal and regulatory obligation. Agent Adda is not a SEBI-registered investment adviser, research analyst, portfolio manager, broker, or any other SEBI-registered market intermediary. Agent Adda, its creators, contributors, systems, agents, and associated persons accept no responsibility or liability for losses, damages, legal consequences, regulatory consequences, tax consequences, opportunity costs, or any other implications arising directly or indirectly from the use of this information by any person or organization. All market data can be delayed, incomplete, inaccurate, stale, or affected by corporate actions, liquidity, data-provider issues, model limitations, prompt limitations, or rule-design limitations. Users must consult qualified SEBI-registered professionals and independently verify all facts before making any financial or legal decision.
