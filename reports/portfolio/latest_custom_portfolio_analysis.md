# Custom Portfolio Deep Analysis — 2026-06-10

Generated: 2026-06-10 23:27 IST  
Sources: pasted stock list, Agent Adda PostgreSQL `scores.stage_snapshots`, local EOD history, latest enhanced NSE comprehensive report, and selected external checks for unresolved BSE-only names.

> Not investment advice. This is a research portfolio diagnostic. Validate liquidity, position size, corporate actions, and risk independently.

## Resolution Summary

- Raw rows in pasted list: **82**
- Resolved unique NSE symbols in Agent Adda: **77**
- Duplicate/merged entries: **2**
- Unresolved / excluded from local NSE analysis: **3**

### Merged / Duplicate Inputs

- **SEPC**: SEPC LTD, SEPC RS.5 PPD UP, SEPC LIMITED

### Excluded / Needs Separate Handling

- **CAPTAIN POLYPLAST LTD** — not in local Agent Adda NSE universe; appears BSE/Screener-listed, analyze separately
- **ALUFLUORIDE LTD.** — not in local Agent Adda NSE universe; appears BSE/Screener-listed, analyze separately
- **CASPIAN CORPORATE SERVICES LIM** — not in local Agent Adda NSE universe; appears BSE-only/illiquid, analyze separately

## Portfolio Health Snapshot

- Stage distribution: {'STAGE_2': 11, 'STAGE_1': 28, 'STAGE_3': 2, 'UNKNOWN': 5, 'STAGE_4': 31}
- Signal distribution: {'BUY': 1, 'HOLD': 33, 'WEAK_HOLD': 10, 'SELL': 33}
- Rating distribution: {'ACCUMULATE / CORE WATCH': 7, 'HOLD / WATCH': 26, 'WATCH ON PULLBACK': 2, 'AVOID / REVIEW EXIT': 42}
- Average portfolio score: **21.4**
- Average technical score: **37.7**
- Average investment score: **38.4**
- Average enhanced fundamental score: **53.6**
- Average RS: **2.4**

### Sector Concentration

- —: 37
- Other: 19
- PSU / CPSE: 5
- Defence & Aerospace: 3
- EV & Auto Ancillaries: 2
- MNC: 2
- Capital Goods & Industrials: 1
- Railways & PSU Infra: 1
- Metals & Mining: 1
- Chemicals & Specialty: 1
- Capital Markets: 1
- Infrastructure: 1

## Portfolio Construction View

The list is broad and speculative-heavy. I would not treat all resolved names as equal-quality long-term holdings. A cleaner portfolio should separate **core candidates**, **watchlist/pullback candidates**, and **exit/review candidates**. Equal-weighting the entire list would dilute capital into many Stage 4, SELL, or low-RS names.

### Core / Accumulate Watch Candidates

| Symbol | Sector | Price | Stage | Signal | Score | Tech | Fund | RS% | 1M% | Note |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---|
| MANINDS | Capital Goods & Industrials | ₹528.75 | STAGE_2 | BUY | 80.5 | 60.7 | 69.2 | 47.4% | 1.5% | Stage 2, strong RS, strong tech, fund score >60 |
| DATAPATTNS | Defence & Aerospace | ₹4,354 | STAGE_2 | HOLD | 69.2 | 68.0 | 52.8 | 29.9% | 7.2% | Stage 2, strong RS, strong tech |
| PAISALO | — | ₹59.51 | STAGE_2 | HOLD | 66.4 | 65.0 | — | 22.3% | 22.3% | Stage 2, strong RS, strong tech |
| INDOTECH | — | ₹2,470 | STAGE_2 | HOLD | 65.8 | 60.0 | — | 33.8% | 33.8% | Stage 2, strong RS |
| MOTHERSON | EV & Auto Ancillaries | ₹142.21 | STAGE_2 | HOLD | 64.6 | 62.0 | 51.6 | 20.2% | 14.4% | Stage 2, strong RS, strong tech |
| IDEA | — | ₹13.88 | STAGE_2 | HOLD | 62.2 | 60.0 | — | 14.0% | 14.0% | Stage 2 |
| BELRISE | Defence & Aerospace | ₹227.13 | STAGE_2 | HOLD | 62.0 | 58.7 | 53.3 | 11.1% | 10.6% | Stage 2 |

### Watch / Hold Candidates

| Symbol | Sector | Price | Stage | Signal | Score | Tech | Fund | RS% | 1M% | Issue to Watch |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---|
| VARDHACRLC | — | ₹44.17 | STAGE_2 | HOLD | 64.5 | 70.0 | — | -2.9% | -2.9% | negative RS |
| MOREPENLAB | — | ₹49.37 | STAGE_1 | HOLD | 64.4 | 85.0 | — | 7.8% | 7.8% | not Stage 2 |
| HFCL | Railways & PSU Infra | ₹169.11 | STAGE_2 | HOLD | 63.9 | 49.3 | 10.0 | 132.9% | 14.4% | confirmation needed |
| ENRIN | Other | ₹3,425 | STAGE_2 | HOLD | 58.4 | 49.3 | — | 18.0% | 12.1% | confirmation needed |
| PYRAMID | — | ₹163.27 | STAGE_2 | HOLD | 55.9 | 55.0 | — | -6.6% | -6.6% | negative RS |
| EXIDEIND | EV & Auto Ancillaries | ₹386.35 | STAGE_1 | HOLD | 54.5 | 62.0 | 51.1 | 20.2% | 11.6% | not Stage 2 |
| IFGLEXPOR | — | ₹191.37 | STAGE_1 | HOLD | 53.2 | 65.0 | — | 4.6% | 4.6% | not Stage 2 |
| NIBE | Other | ₹1,503 | STAGE_1 | WEAK_HOLD | 52.7 | 47.3 | — | 58.8% | 53.1% | not Stage 2 |
| HCC | — | ₹22.35 | STAGE_1 | HOLD | 52.3 | 65.0 | — | -0.4% | -0.4% | not Stage 2, negative RS |
| YESBANK | — | ₹22.60 | STAGE_1 | HOLD | 52.3 | 65.0 | — | -0.4% | -0.4% | not Stage 2, negative RS |
| ABB | MNC | ₹6,801 | STAGE_1 | HOLD | 51.4 | 55.3 | 61.3 | 3.9% | 7.5% | not Stage 2 |
| HINDALCO | Metals & Mining | ₹1,039 | STAGE_1 | HOLD | 51.4 | 58.7 | 52.9 | 14.1% | -0.2% | not Stage 2 |
| TMPV | Other | ₹381.00 | STAGE_1 | HOLD | 49.7 | 54.7 | 48.0 | 14.3% | 13.1% | not Stage 2 |
| AAATECH | — | ₹94.71 | STAGE_3 | HOLD | 49.4 | 70.0 | — | -3.4% | -3.4% | not Stage 2, negative RS |
| SIEMENS | MNC | ₹3,583 | STAGE_1 | HOLD | 48.6 | 54.0 | 51.3 | 10.0% | 0.2% | not Stage 2 |
| GEOJITFSL | — | ₹72.24 | STAGE_1 | HOLD | 47.7 | 55.0 | — | 3.4% | 3.4% | not Stage 2 |
| SUZLON | — | ₹54.08 | STAGE_1 | HOLD | 47.3 | 55.0 | — | 1.5% | 1.5% | not Stage 2 |
| GENSOL | — | ₹24.92 | STAGE_1 | HOLD | 45.2 | 45.0 | — | 19.2% | 19.2% | not Stage 2 |
| COALINDIA | PSU / CPSE | ₹451.00 | STAGE_1 | WEAK_HOLD | 43.7 | 40.7 | 71.2 | -3.9% | -2.6% | not Stage 2, negative RS, weak tech |
| GUFICBIO | Other | ₹364.05 | STAGE_1 | WEAK_HOLD | 43.7 | 48.0 | — | 18.0% | 22.8% | not Stage 2 |
| ATLANTAELE | — | ₹2,050 | UNKNOWN | HOLD | 43.5 | 65.0 | — | 23.0% | 23.0% | not Stage 2 |
| QUADFUTURE | Other | ₹338.40 | STAGE_1 | WEAK_HOLD | 41.1 | 46.0 | — | 10.7% | 11.7% | not Stage 2 |
| PPLPHARMA | Other | ₹164.07 | STAGE_1 | WEAK_HOLD | 39.2 | 42.0 | — | 10.8% | -7.1% | not Stage 2, weak tech |
| PCBL | Chemicals & Specialty | ₹287.15 | STAGE_1 | WEAK_HOLD | 37.3 | 38.7 | — | 0.9% | 3.3% | not Stage 2, weak tech |
| DEEPAKNTR | — | ₹1,665 | STAGE_1 | HOLD | 37.2 | 40.0 | — | -10.7% | -10.7% | not Stage 2, negative RS, weak tech |

### Avoid / Review Exit Candidates

| Symbol | Sector | Price | Stage | Signal | Score | Tech | Fund | RS% | 1M% | Main Problem |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---|
| JPPOWER | — | ₹18.00 | STAGE_3 | HOLD | 23.1 | 20.0 | — | -2.3% | -2.3% | low tech score |
| MCX | Capital Markets | ₹2,744 | STAGE_1 | SELL | 23.0 | 31.3 | — | 5.8% | -13.1% | SELL |
| TATACAP | Other | ₹321.30 | STAGE_1 | SELL | 21.6 | 28.7 | — | -6.7% | 3.8% | SELL |
| MRPL | PSU / CPSE | ₹163.62 | STAGE_1 | SELL | 20.3 | 34.0 | — | -17.6% | 6.2% | SELL, negative RS |
| ONGC | PSU / CPSE | ₹251.90 | STAGE_1 | SELL | 19.3 | 24.7 | 64.8 | -12.3% | -14.5% | SELL, low tech score |
| IRB | — | ₹20.52 | STAGE_1 | HOLD | 17.2 | — | — | -3.7% | -3.7% | low tech score |
| KPEL | Other | ₹340.90 | STAGE_4 | WEAK_HOLD | 17.2 | 38.7 | — | 18.3% | -5.1% | Stage 4 downtrend |
| UMESLTD | — | ₹5.04 | STAGE_1 | HOLD | 16.7 | 5.0 | — | -21.5% | -21.5% | low tech score, negative RS |
| DCXINDIA | Defence & Aerospace | ₹181.87 | STAGE_4 | WEAK_HOLD | 16.6 | 40.0 | 62.1 | 1.1% | -7.6% | Stage 4 downtrend |
| UJJIVANSFB | — | ₹52.94 | STAGE_1 | HOLD | 16.0 | — | — | -10.4% | -10.4% | low tech score |
| CRIZAC | Other | ₹207.89 | STAGE_4 | WEAK_HOLD | 14.2 | 38.7 | 51.4 | 1.7% | 0.9% | Stage 4 downtrend |
| PRECAM | Other | ₹140.66 | STAGE_4 | WEAK_HOLD | 13.9 | 38.0 | — | 12.4% | -11.1% | Stage 4 downtrend |
| SAIFL-SM | — | ₹5.05 | UNKNOWN | HOLD | 4.9 | — | — | — | — | low tech score |
| PINELABS | Other | ₹150.32 | UNKNOWN | SELL | 4.4 | 20.0 | — | -14.1% | -20.1% | SELL, low tech score |
| TMCV | Other | ₹364.90 | UNKNOWN | SELL | -1.3 | 12.0 | — | -21.0% | -5.7% | SELL, low tech score, negative RS |
| HGINFRA | Infrastructure | ₹557.25 | STAGE_4 | SELL | -1.5 | 30.7 | — | 9.4% | -12.2% | Stage 4 downtrend, SELL |
| FIVESTAR | Other | ₹430.15 | STAGE_4 | SELL | -2.0 | 30.0 | — | 6.9% | -8.4% | Stage 4 downtrend, SELL |
| PROSTARM | Other | ₹140.35 | STAGE_4 | SELL | -5.0 | 24.7 | — | 3.0% | -7.0% | Stage 4 downtrend, SELL, low tech score |
| KITEX | Housing & Building Materials | ₹142.79 | STAGE_4 | SELL | -5.6 | 32.7 | 52.7 | -16.1% | -8.9% | Stage 4 downtrend, SELL, negative RS |
| MAZDOCK | PSU / CPSE | ₹2,368 | STAGE_4 | SELL | -5.7 | 22.7 | — | -0.6% | -3.1% | Stage 4 downtrend, SELL, low tech score |
| HUHTAMAKI | Other | ₹170.91 | STAGE_4 | SELL | -6.5 | 18.0 | — | -2.0% | -1.2% | Stage 4 downtrend, SELL, low tech score |
| HDFCBANK | Banking - Private | ₹746.85 | STAGE_4 | SELL | -8.0 | 20.7 | — | -10.1% | -0.5% | Stage 4 downtrend, SELL, low tech score |
| IREDA | PSU / CPSE | ₹120.58 | STAGE_4 | SELL | -9.7 | 14.7 | — | -4.4% | -3.3% | Stage 4 downtrend, SELL, low tech score |
| JIOFIN | Other | ₹230.17 | STAGE_4 | SELL | -10.5 | 12.0 | — | -8.6% | -0.1% | Stage 4 downtrend, SELL, low tech score |
| VOLTAS | Consumer Durables | ₹1,290 | STAGE_4 | SELL | -10.9 | 12.0 | — | -11.3% | 1.6% | Stage 4 downtrend, SELL, low tech score |
| PGEL | Other | ₹465.90 | STAGE_4 | SELL | -10.9 | 14.0 | — | -15.5% | -5.7% | Stage 4 downtrend, SELL, low tech score, negative RS |
| NAGAFERT | — | ₹3.89 | STAGE_4 | SELL | -12.6 | 20.0 | — | -6.3% | -6.3% | Stage 4 downtrend, SELL, low tech score |
| SBFC | — | ₹91.63 | STAGE_4 | SELL | -12.6 | 20.0 | — | -5.9% | -5.9% | Stage 4 downtrend, SELL, low tech score |
| SWIGGY | Other | ₹242.30 | STAGE_4 | SELL | -12.7 | 13.3 | — | -18.0% | -5.3% | Stage 4 downtrend, SELL, low tech score, negative RS |
| CENTRALBK | — | ₹30.76 | STAGE_4 | SELL | -14.0 | 20.0 | — | -13.7% | -13.7% | Stage 4 downtrend, SELL, low tech score |
| TRENT | Other | ₹2,755 | STAGE_4 | SELL | -15.5 | 16.7 | — | -26.4% | -32.0% | Stage 4 downtrend, SELL, low tech score, negative RS |
| XCHANGING | — | ₹63.02 | STAGE_4 | SELL | -20.8 | 5.0 | — | -7.5% | -7.5% | Stage 4 downtrend, SELL, low tech score |
| IRFC | — | ₹94.80 | STAGE_4 | SELL | -20.9 | 5.0 | — | -8.0% | -8.0% | Stage 4 downtrend, SELL, low tech score |
| ABLBL | — | ₹97.37 | STAGE_4 | SELL | -21.2 | 5.0 | — | -9.6% | -9.6% | Stage 4 downtrend, SELL, low tech score |
| TPHQ | — | ₹0.50 | STAGE_4 | SELL | -21.7 | 5.0 | — | -12.3% | -12.3% | Stage 4 downtrend, SELL, low tech score |
| AURIONPRO | — | ₹746.60 | STAGE_4 | SELL | -22.1 | 5.0 | — | -14.7% | -14.7% | Stage 4 downtrend, SELL, low tech score |
| SJVN | — | ₹71.81 | STAGE_4 | SELL | -23.4 | — | — | -7.2% | -7.2% | Stage 4 downtrend, SELL, low tech score |
| INVENTURE | — | ₹0.93 | STAGE_4 | SELL | -23.4 | — | — | -7.0% | -7.0% | Stage 4 downtrend, SELL, low tech score |
| DMCC | — | ₹245.30 | STAGE_4 | SELL | -23.7 | 5.0 | — | -23.4% | -23.4% | Stage 4 downtrend, SELL, low tech score, negative RS |
| ABFRL | — | ₹58.76 | STAGE_4 | SELL | -23.8 | — | — | -9.6% | -9.6% | Stage 4 downtrend, SELL, low tech score |
| SEPC | — | ₹6.43 | STAGE_4 | SELL | -25.3 | — | — | -17.8% | -17.8% | Stage 4 downtrend, SELL, low tech score, negative RS |
| PLATIND | — | ₹210.27 | STAGE_4 | SELL | -25.8 | — | — | -20.4% | -20.4% | Stage 4 downtrend, SELL, low tech score, negative RS |

## Full Resolved Portfolio Table

| # | Symbol | Original Input | Sector | MCap | Price | Stage | Signal | Score | Inv | Tech | Fund | RS% | 1D% | 1W% | 1M% | RSI | ADX | 52W Dist | Rating |
|---:|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | **MANINDS** | MAN INDUSTRIES (I) LTD. | Capital Goods & Industrials | MID_CAP | ₹528.75 | STAGE_2 | BUY | 80.5 | 58.9 | 60.7 | 69.2 | 47.4% | 1.9% | 6.6% | 1.5% | 51.9 | 30.1 | -12.8% | ACCUMULATE / CORE WATCH |
| 2 | **DATAPATTNS** | DATA PATTERNS INDIA LTD | Defence & Aerospace | LARGE_CAP | ₹4,354 | STAGE_2 | HOLD | 69.2 | 60.7 | 68.0 | 52.8 | 29.9% | -4.5% | 9.1% | 7.2% | 59.3 | 25.4 | -7.8% | ACCUMULATE / CORE WATCH |
| 3 | **PAISALO** | PAISALO DIGITAL LIMITED | — | — | ₹59.51 | STAGE_2 | HOLD | 66.4 | 65.0 | 65.0 | — | 22.3% | -1.1% | 10.4% | 22.3% | 79.4 | 64.3 | -2.4% | ACCUMULATE / CORE WATCH |
| 4 | **INDOTECH** | INDO TECH TRANSFORM LTD. | — | — | ₹2,470 | STAGE_2 | HOLD | 65.8 | 60.0 | 60.0 | — | 33.8% | -5.0% | -9.5% | 33.8% | 55.9 | 53.9 | -17.1% | ACCUMULATE / CORE WATCH |
| 5 | **MOTHERSON** | SAMVRDHNA MTHRSN INTL LTD | EV & Auto Ancillaries | MICRO_CAP | ₹142.21 | STAGE_2 | HOLD | 64.6 | 57.1 | 62.0 | 51.6 | 20.2% | -1.3% | -2.3% | 14.4% | 58.9 | 50.0 | -6.3% | ACCUMULATE / CORE WATCH |
| 6 | **VARDHACRLC** | VARDHAMAN ACRYLICS LTD | — | — | ₹44.17 | STAGE_2 | HOLD | 64.5 | 70.0 | 70.0 | — | -2.9% | -2.0% | 2.1% | -2.9% | 56.6 | 48.1 | -18.6% | HOLD / WATCH |
| 7 | **MOREPENLAB** | MOREPEN LAB. LTD | — | — | ₹49.37 | STAGE_1 | HOLD | 64.4 | 85.0 | 85.0 | — | 7.8% | 1.5% | 8.7% | 7.8% | 66.5 | 32.3 | -30.0% | HOLD / WATCH |
| 8 | **HFCL** | HFCL LIMITED | Railways & PSU Infra | MICRO_CAP | ₹169.11 | STAGE_2 | HOLD | 63.9 | 47.4 | 49.3 | 10.0 | 132.9% | -5.0% | -15.2% | 14.4% | 57.3 | 55.9 | -19.1% | WATCH ON PULLBACK |
| 9 | **IDEA** | VODAFONE IDEA LIMITED | — | — | ₹13.88 | STAGE_2 | HOLD | 62.2 | 60.0 | 60.0 | — | 14.0% | -1.8% | -6.5% | 14.0% | 60.4 | 51.0 | -9.0% | ACCUMULATE / CORE WATCH |
| 10 | **BELRISE** | BELRISE INDUSTRIES LTD | Defence & Aerospace | SMALL_CAP | ₹227.13 | STAGE_2 | HOLD | 62.0 | 55.2 | 58.7 | 53.3 | 11.1% | -3.2% | 3.5% | 10.6% | 59.9 | 18.2 | -4.0% | ACCUMULATE / CORE WATCH |
| 11 | **ENRIN** | SIEMENS ENERGY INDIA LTD | Other | LARGE_CAP | ₹3,425 | STAGE_2 | HOLD | 58.4 | 53.9 | 49.3 | — | 18.0% | -3.5% | -7.1% | 12.1% | 49.8 | 33.6 | -13.7% | WATCH ON PULLBACK |
| 12 | **PYRAMID** | PYRAMID TECHNOPLAST LTD | — | — | ₹163.27 | STAGE_2 | HOLD | 55.9 | 55.0 | 55.0 | — | -6.6% | -0.7% | -0.8% | -6.6% | 47.6 | 22.3 | -14.1% | HOLD / WATCH |
| 13 | **EXIDEIND** | EXIDE INDUSTRIES LTD | EV & Auto Ancillaries | SMALL_CAP | ₹386.35 | STAGE_1 | HOLD | 54.5 | 56.9 | 62.0 | 51.1 | 20.2% | -1.7% | -3.2% | 11.6% | 57.9 | 40.2 | -10.4% | HOLD / WATCH |
| 14 | **IFGLEXPOR** | IFGL REFRACTORIES LIMITED | — | — | ₹191.37 | STAGE_1 | HOLD | 53.2 | 65.0 | 65.0 | — | 4.6% | -3.5% | -3.1% | 4.6% | 57.4 | 38.7 | -43.4% | HOLD / WATCH |
| 15 | **NIBE** | NIBE LIMITED | Other | LARGE_CAP | ₹1,503 | STAGE_1 | WEAK_HOLD | 52.7 | 55.8 | 47.3 | — | 58.8% | -2.5% | 0.0% | 53.1% | 64.2 | 60.3 | -24.9% | HOLD / WATCH |
| 16 | **HCC** | HINDUSTAN CONSTRUCTION CO | — | — | ₹22.35 | STAGE_1 | HOLD | 52.3 | 65.0 | 65.0 | — | -0.4% | -4.6% | -4.9% | -0.4% | 51.2 | 23.5 | -40.2% | HOLD / WATCH |
| 17 | **YESBANK** | YES BANK LIMITED | — | — | ₹22.60 | STAGE_1 | HOLD | 52.3 | 65.0 | 65.0 | — | -0.4% | -3.3% | -1.4% | -0.4% | 54.7 | 23.3 | -7.0% | HOLD / WATCH |
| 18 | **ABB** | ABB INDIA LIMITED | MNC | LARGE_CAP | ₹6,801 | STAGE_1 | HOLD | 51.4 | 55.0 | 55.3 | 61.3 | 3.9% | -1.9% | -5.5% | 7.5% | 46.6 | 25.4 | -13.1% | HOLD / WATCH |
| 19 | **HINDALCO** | HINDALCO  INDUSTRIES  LTD | Metals & Mining | LARGE_CAP | ₹1,039 | STAGE_1 | HOLD | 51.4 | 51.0 | 58.7 | 52.9 | 14.1% | -3.5% | -8.8% | -0.2% | 42.0 | 35.4 | -11.6% | HOLD / WATCH |
| 20 | **TMPV** | TATA MOTORS PASS VEH LTD | Other | SMALL_CAP | ₹381.00 | STAGE_1 | HOLD | 49.7 | 53.0 | 54.7 | 48.0 | 14.3% | -1.8% | -4.3% | 13.1% | 54.7 | 39.2 | -9.1% | HOLD / WATCH |
| 21 | **AAATECH** | AAA TECHNOLOGIES LIMITED | — | — | ₹94.71 | STAGE_3 | HOLD | 49.4 | 70.0 | 70.0 | — | -3.4% | -0.4% | 2.8% | -3.4% | 50.4 | 33.3 | -30.4% | HOLD / WATCH |
| 22 | **SIEMENS** | SIEMENS LTD | MNC | LARGE_CAP | ₹3,583 | STAGE_1 | HOLD | 48.6 | 49.6 | 54.0 | 51.3 | 10.0% | -1.0% | -3.4% | 0.2% | 44.3 | 19.3 | -9.0% | HOLD / WATCH |
| 23 | **GEOJITFSL** | GEOJIT FINANCIAL SER L | — | — | ₹72.24 | STAGE_1 | HOLD | 47.7 | 55.0 | 55.0 | — | 3.4% | -2.2% | -0.5% | 3.4% | 51.0 | 21.8 | -23.8% | HOLD / WATCH |
| 24 | **SUZLON** | SUZLON ENERGY LIMITED | — | — | ₹54.08 | STAGE_1 | HOLD | 47.3 | 55.0 | 55.0 | — | 1.5% | -2.1% | -0.6% | 1.5% | 50.7 | 16.8 | -27.2% | HOLD / WATCH |
| 25 | **GENSOL** | GENSOL ENGINEERING LTD | — | — | ₹24.92 | STAGE_1 | HOLD | 45.2 | 45.0 | 45.0 | — | 19.2% | — | 19.9% | 19.2% | 77.4 | 69.1 | -64.5% | HOLD / WATCH |
| 26 | **COALINDIA** | COAL INDIA LTD | PSU / CPSE | SMALL_CAP | ₹451.00 | STAGE_1 | WEAK_HOLD | 43.7 | 49.4 | 40.7 | 71.2 | -3.9% | -3.4% | -4.5% | -2.6% | 41.8 | 16.8 | -8.2% | HOLD / WATCH |
| 27 | **GUFICBIO** | GUFIC BIOSCIENCES LTD. | Other | SMALL_CAP | ₹364.05 | STAGE_1 | WEAK_HOLD | 43.7 | 48.3 | 48.0 | — | 18.0% | -5.9% | 0.6% | 22.8% | 65.2 | 69.0 | -10.7% | HOLD / WATCH |
| 28 | **ATLANTAELE** | ATLANTA ELECTRICALS LTD | — | — | ₹2,050 | UNKNOWN | HOLD | 43.5 | 65.0 | 65.0 | — | 23.0% | 5.0% | 14.6% | 23.0% | 72.3 | 39.8 | -0.4% | HOLD / WATCH |
| 29 | **QUADFUTURE** | QUADRANT FUTURE TEK LTD | Other | SMALL_CAP | ₹338.40 | STAGE_1 | WEAK_HOLD | 41.1 | 45.6 | 46.0 | — | 10.7% | -1.4% | 5.4% | 11.7% | 65.0 | 60.1 | -36.3% | HOLD / WATCH |
| 30 | **PPLPHARMA** | PIRAMAL PHARMA LIMITED | Other | MICRO_CAP | ₹164.07 | STAGE_1 | WEAK_HOLD | 39.2 | 42.3 | 42.0 | — | 10.8% | -2.8% | -1.8% | -7.1% | 43.4 | 18.2 | -27.4% | HOLD / WATCH |
| 31 | **PCBL** | PCBL CHEMICAL LIMITED | Chemicals & Specialty | SMALL_CAP | ₹287.15 | STAGE_1 | WEAK_HOLD | 37.3 | 45.7 | 38.7 | — | 0.9% | 1.1% | -1.3% | 3.3% | 50.0 | 14.3 | -34.3% | HOLD / WATCH |
| 32 | **DEEPAKNTR** | DEEPAK NITRITE LTD | — | — | ₹1,665 | STAGE_1 | HOLD | 37.2 | 40.0 | 40.0 | — | -10.7% | -0.8% | -2.0% | -10.7% | 42.8 | 40.2 | -23.4% | HOLD / WATCH |
| 33 | **SHALBY** | SHALBY LIMITED | — | — | ₹165.87 | STAGE_1 | HOLD | 36.5 | 35.0 | 35.0 | — | 0.2% | -1.9% | -5.9% | 0.2% | 47.3 | 18.6 | -39.6% | HOLD / WATCH |
| 34 | **ASHIMASYN** | ASHIMA LTD | — | — | ₹16.07 | STAGE_1 | HOLD | 36.0 | 35.0 | 35.0 | — | -2.5% | -0.6% | -3.2% | -2.5% | 48.5 | 17.9 | -55.1% | HOLD / WATCH |
| 35 | **JPPOWER** | JAIPRAKASH POWER VEN. LTD | — | — | ₹18.00 | STAGE_3 | HOLD | 23.1 | 20.0 | 20.0 | — | -2.3% | -3.1% | -6.9% | -2.3% | 44.4 | 17.4 | -35.0% | AVOID / REVIEW EXIT |
| 36 | **MCX** | MULTI COMMODITY EXCHANGE | Capital Markets | LARGE_CAP | ₹2,744 | STAGE_1 | SELL | 23.0 | 41.2 | 31.3 | — | 5.8% | -2.9% | -3.2% | -13.1% | 34.8 | 52.6 | -21.2% | AVOID / REVIEW EXIT |
| 37 | **SIKA** | SIKA INTERPLANT SYSTEMS L | — | — | ₹904.75 | UNKNOWN | HOLD | 22.0 | 35.0 | 35.0 | — | -7.8% | -1.0% | 0.1% | -7.8% | 48.8 | 21.4 | -24.6% | HOLD / WATCH |
| 38 | **TATACAP** | TATA CAPITAL LIMITED | Other | SMALL_CAP | ₹321.30 | STAGE_1 | SELL | 21.6 | 47.6 | 28.7 | — | -6.7% | -0.5% | 4.0% | 3.8% | 56.8 | 26.6 | -12.5% | AVOID / REVIEW EXIT |
| 39 | **MRPL** | MRPL | PSU / CPSE | MICRO_CAP | ₹163.62 | STAGE_1 | SELL | 20.3 | 44.1 | 34.0 | — | -17.6% | 2.0% | 6.1% | 6.2% | 57.3 | 26.4 | -22.9% | AVOID / REVIEW EXIT |
| 40 | **ONGC** | OIL AND NATURAL GAS CORP. | PSU / CPSE | SMALL_CAP | ₹251.90 | STAGE_1 | SELL | 19.3 | 29.3 | 24.7 | 64.8 | -12.3% | -2.7% | -5.9% | -14.5% | 25.3 | 46.8 | -18.1% | AVOID / REVIEW EXIT |
| 41 | **IRB** | IRB INFRA DEV LTD. | — | — | ₹20.52 | STAGE_1 | HOLD | 17.2 | 0.0 | — | — | -3.7% | 0.1% | -3.6% | -3.7% | 41.5 | 17.9 | -24.4% | AVOID / REVIEW EXIT |
| 42 | **KPEL** | K.P. ENERGY LIMITED | Other | SMALL_CAP | ₹340.90 | STAGE_4 | WEAK_HOLD | 17.2 | 52.5 | 38.7 | — | 18.3% | -1.3% | -3.5% | -5.1% | 43.3 | 22.0 | -41.6% | AVOID / REVIEW EXIT |
| 43 | **UMESLTD** | USHA MARTIN EDU & SOL LTD | — | — | ₹5.04 | STAGE_1 | HOLD | 16.7 | 5.0 | 5.0 | — | -21.5% | 4.6% | -7.7% | -21.5% | 33.9 | 63.9 | -29.4% | AVOID / REVIEW EXIT |
| 44 | **DCXINDIA** | DCX SYSTEMS LIMITED | Defence & Aerospace | MICRO_CAP | ₹181.87 | STAGE_4 | WEAK_HOLD | 16.6 | 46.2 | 40.0 | 62.1 | 1.1% | -4.3% | -8.2% | -7.6% | 39.9 | 23.0 | -50.0% | AVOID / REVIEW EXIT |
| 45 | **UJJIVANSFB** | UJJIVAN SMALL FINANC BANK | — | — | ₹52.94 | STAGE_1 | HOLD | 16.0 | 0.0 | — | — | -10.4% | -1.9% | -1.6% | -10.4% | 41.9 | 16.4 | -22.1% | AVOID / REVIEW EXIT |
| 46 | **CRIZAC** | CRIZAC LIMITED | Other | SMALL_CAP | ₹207.89 | STAGE_4 | WEAK_HOLD | 14.2 | 47.2 | 38.7 | 51.4 | 1.7% | -2.1% | -3.6% | 0.9% | 44.6 | 19.5 | -46.4% | AVOID / REVIEW EXIT |
| 47 | **PRECAM** | PRECISION CAMSHAFTS LTD. | Other | MICRO_CAP | ₹140.66 | STAGE_4 | WEAK_HOLD | 13.9 | 44.4 | 38.0 | — | 12.4% | -2.1% | -5.7% | -11.1% | 36.2 | 16.5 | -46.3% | AVOID / REVIEW EXIT |
| 48 | **SAIFL-SM** | SAMEERA AGRO AND INFRA L | — | — | ₹5.05 | UNKNOWN | HOLD | 4.9 | 0.0 | — | — | — | — | — | — | — | 0.0 | -2.9% | AVOID / REVIEW EXIT |
| 49 | **PINELABS** | PINE LABS LIMITED | Other | MICRO_CAP | ₹150.32 | UNKNOWN | SELL | 4.4 | 45.6 | 20.0 | — | -14.1% | -1.3% | 5.1% | -20.1% | 43.5 | 30.1 | -47.1% | AVOID / REVIEW EXIT |
| 50 | **TMCV** | TATA MOTORS LIMITED | Other | SMALL_CAP | ₹364.90 | UNKNOWN | SELL | -1.3 | 37.0 | 12.0 | — | -21.0% | 0.4% | -2.4% | -5.7% | 34.1 | 33.8 | -28.3% | AVOID / REVIEW EXIT |
| 51 | **HGINFRA** | H.G.INFRA ENGINEERING LTD | Infrastructure | MID_CAP | ₹557.25 | STAGE_4 | SELL | -1.5 | 41.1 | 30.7 | — | 9.4% | -1.9% | -0.4% | -12.2% | 39.4 | 33.6 | -56.3% | AVOID / REVIEW EXIT |
| 52 | **FIVESTAR** | FIVE-STAR BUS FIN LTD | Other | SMALL_CAP | ₹430.15 | STAGE_4 | SELL | -2.0 | 41.8 | 30.0 | — | 6.9% | -0.2% | -1.1% | -8.4% | 40.2 | 35.6 | -48.0% | AVOID / REVIEW EXIT |
| 53 | **PROSTARM** | PROSTARM INFO SYSTEMS LTD | Other | MICRO_CAP | ₹140.35 | STAGE_4 | SELL | -5.0 | 38.6 | 24.7 | — | 3.0% | -0.1% | 1.8% | -7.0% | 44.5 | 11.0 | -44.6% | AVOID / REVIEW EXIT |
| 54 | **KITEX** | KITEX GARMENTS LTD | Housing & Building Materials | MICRO_CAP | ₹142.79 | STAGE_4 | SELL | -5.6 | 34.0 | 32.7 | 52.7 | -16.1% | -2.3% | -11.9% | -8.9% | 28.5 | 35.9 | -56.0% | AVOID / REVIEW EXIT |
| 55 | **MAZDOCK** | MAZAGON DOCK SHIPBUIL LTD | PSU / CPSE | LARGE_CAP | ₹2,368 | STAGE_4 | SELL | -5.7 | 40.5 | 22.7 | — | -0.6% | -2.8% | -3.0% | -3.1% | 37.4 | 16.6 | -37.3% | AVOID / REVIEW EXIT |
| 56 | **HUHTAMAKI** | HUHTAMAKI INDIA LIMITED | Other | MICRO_CAP | ₹170.91 | STAGE_4 | SELL | -6.5 | 43.6 | 18.0 | — | -2.0% | -0.1% | 3.2% | -1.2% | 51.5 | 23.6 | -37.3% | AVOID / REVIEW EXIT |
| 57 | **HDFCBANK** | HDFC BANK LTD | Banking - Private | MID_CAP | ₹746.85 | STAGE_4 | SELL | -8.0 | 40.6 | 20.7 | — | -10.1% | 1.1% | -0.9% | -0.5% | 42.9 | 24.0 | -26.8% | AVOID / REVIEW EXIT |
| 58 | **IREDA** | INDIAN RENEWABLE ENERGY | PSU / CPSE | MICRO_CAP | ₹120.58 | STAGE_4 | SELL | -9.7 | 36.4 | 14.7 | — | -4.4% | -1.5% | -1.8% | -3.3% | 37.9 | 17.6 | -35.4% | AVOID / REVIEW EXIT |
| 59 | **JIOFIN** | JIO FIN SERVICES LTD | Other | SMALL_CAP | ₹230.17 | STAGE_4 | SELL | -10.5 | 39.3 | 12.0 | — | -8.6% | -1.7% | -2.1% | -0.1% | 41.9 | 34.3 | -32.0% | AVOID / REVIEW EXIT |
| 60 | **VOLTAS** | VOLTAS LTD | Consumer Durables | LARGE_CAP | ₹1,290 | STAGE_4 | SELL | -10.9 | 39.5 | 12.0 | — | -11.3% | -1.1% | 4.5% | 1.6% | 48.6 | 22.8 | -18.5% | AVOID / REVIEW EXIT |
| 61 | **PGEL** | PG ELECTROPLAST LTD | Other | SMALL_CAP | ₹465.90 | STAGE_4 | SELL | -10.9 | 40.4 | 14.0 | — | -15.5% | -2.9% | -1.2% | -5.7% | 41.7 | 24.7 | -48.1% | AVOID / REVIEW EXIT |
| 62 | **NAGAFERT** | NAGARJUN FERT AND CHE LTD | — | — | ₹3.89 | STAGE_4 | SELL | -12.6 | 20.0 | 20.0 | — | -6.3% | -0.3% | 0.3% | -6.3% | 43.6 | 43.3 | -40.5% | AVOID / REVIEW EXIT |
| 63 | **SBFC** | SBFC FINANCE LIMITED | — | — | ₹91.63 | STAGE_4 | SELL | -12.6 | 20.0 | 20.0 | — | -5.9% | -0.2% | -1.3% | -5.9% | 47.1 | 19.5 | -25.5% | AVOID / REVIEW EXIT |
| 64 | **SWIGGY** | SWIGGY LIMITED | Other | SMALL_CAP | ₹242.30 | STAGE_4 | SELL | -12.7 | 35.8 | 13.3 | — | -18.0% | -3.1% | -3.8% | -5.3% | 39.8 | 18.5 | -48.9% | AVOID / REVIEW EXIT |
| 65 | **CENTRALBK** | CENTRAL BANK OF INDIA | — | — | ₹30.76 | STAGE_4 | SELL | -14.0 | 20.0 | 20.0 | — | -13.7% | -1.0% | 1.6% | -13.7% | 35.9 | 47.4 | -25.3% | AVOID / REVIEW EXIT |
| 66 | **TRENT** | TRENT LTD | Other | LARGE_CAP | ₹2,755 | STAGE_4 | SELL | -15.5 | 26.7 | 16.7 | — | -26.4% | -0.6% | -35.3% | -32.0% | 19.8 | 48.4 | -56.0% | AVOID / REVIEW EXIT |
| 67 | **XCHANGING** | XCHANGING SOLUTIONS LTD | — | — | ₹63.02 | STAGE_4 | SELL | -20.8 | 5.0 | 5.0 | — | -7.5% | -3.0% | -3.6% | -7.5% | 40.2 | 25.1 | -39.7% | AVOID / REVIEW EXIT |
| 68 | **IRFC** | INDIAN RAILWAY FIN CORP L | — | — | ₹94.80 | STAGE_4 | SELL | -20.9 | 5.0 | 5.0 | — | -8.0% | -1.3% | -1.0% | -8.0% | 37.7 | 25.3 | -36.4% | AVOID / REVIEW EXIT |
| 69 | **ABLBL** | ADITYA BIRLA LIFES BRAN L | — | — | ₹97.37 | STAGE_4 | SELL | -21.2 | 5.0 | 5.0 | — | -9.6% | -1.4% | -0.9% | -9.6% | 40.9 | 27.3 | -44.4% | AVOID / REVIEW EXIT |
| 70 | **TPHQ** | TEAMO PRODUCTIONS HQ LTD | — | — | ₹0.50 | STAGE_4 | SELL | -21.7 | 5.0 | 5.0 | — | -12.3% | 2.0% | — | -12.3% | 40.3 | 40.6 | -46.2% | AVOID / REVIEW EXIT |
| 71 | **AURIONPRO** | AURIONPRO SOLN LTD | — | — | ₹746.60 | STAGE_4 | SELL | -22.1 | 5.0 | 5.0 | — | -14.7% | -2.6% | -7.8% | -14.7% | 40.1 | 30.5 | -55.2% | AVOID / REVIEW EXIT |
| 72 | **SJVN** | SJVN LTD | — | — | ₹71.81 | STAGE_4 | SELL | -23.4 | 0.0 | — | — | -7.2% | -1.4% | -1.9% | -7.2% | 41.3 | 14.1 | -33.2% | AVOID / REVIEW EXIT |
| 73 | **INVENTURE** | INVENTURE GRO & SEC LTD | — | — | ₹0.93 | STAGE_4 | SELL | -23.4 | 0.0 | — | — | -7.0% | -2.1% | -3.1% | -7.0% | 36.5 | 23.4 | -48.3% | AVOID / REVIEW EXIT |
| 74 | **DMCC** | DMCC SPECIALITY CHEMICALS | — | — | ₹245.30 | STAGE_4 | SELL | -23.7 | 5.0 | 5.0 | — | -23.4% | -1.2% | -6.6% | -23.4% | 36.1 | 38.6 | -29.9% | AVOID / REVIEW EXIT |
| 75 | **ABFRL** | ADITYA BIRLA FASHION & RT | — | — | ₹58.76 | STAGE_4 | SELL | -23.8 | 0.0 | — | — | -9.6% | -2.8% | -2.9% | -9.6% | 37.7 | 18.5 | -40.4% | AVOID / REVIEW EXIT |
| 76 | **SEPC** | SEPC LTD, SEPC RS.5 PPD UP, SEPC LIMITED | — | — | ₹6.43 | STAGE_4 | SELL | -25.3 | 0.0 | — | — | -17.8% | -3.3% | -8.1% | -17.8% | 32.8 | 23.1 | -59.3% | AVOID / REVIEW EXIT |
| 77 | **PLATIND** | PLATINUM INDUSTRIES LTD | — | — | ₹210.27 | STAGE_4 | SELL | -25.8 | 0.0 | — | — | -20.4% | -2.1% | -4.0% | -20.4% | 36.9 | 15.3 | -38.6% | AVOID / REVIEW EXIT |

## Technical Interpretation Rules Used

- **Best technical state:** Stage 2, price above SMA20/50/200, positive RS, BUY/HOLD signal, ADX confirming trend, and not extended too far above support.
- **Weak technical state:** Stage 4/UNKNOWN, SELL signal, negative RS, below SMA50/SMA200, or deep distance from 52-week high.
- **Overheated watch:** very high RSI with poor reward/risk or recent vertical move; wait for consolidation.

## Fundamental Interpretation Rules Used

- **Higher-quality candidates:** enhanced fundamental score above 60, positive earnings/cash-flow quality signals in the Agent Adda snapshot, and manageable leverage.
- **Turnaround candidates:** improving sales/EPS but weak technical trend; these stay on watchlist until price confirms.
- **Speculative candidates:** missing fund score, micro-cap profile, Stage 4 trend, or weak RS; these need smaller sizing or exclusion.
