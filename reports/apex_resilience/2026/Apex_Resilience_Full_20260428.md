# Apex Resilience Screener — full report (20260428)

Generated (run time): 2026-04-29T10:54:31

## Methodology

- Universe: index_stock_mapping constituents for NIFTY MIDCAP SELECT, NIFTY 500, NIFTY INDIA DEFENCE, NIFTY CPSE, NIFTY MICROCAP 250.
- Price screen: same as Apex Resilience (≤30% from rolling 52-week high of HIGH, close > SMA50, recovery/volume metrics; composite excludes proxy fund Z). Stock data date range (filtered): 2023-01-02 00:00:00 → 2026-04-28 00:00:00; benchmark range: 2019-05-20 00:00:00 → 2026-04-28 00:00:00.
- Fundamentals: refreshed from live www.screener.in on each run (HTTP GET with Cache-Control: no-cache via R/httr); prior Apex_Resilience_screener_fundamentals_<date>.csv is removed before re-fetch unless --reuse-screener-csv. Batched fetch: --screener-batch-size 20, --screener-workers 1 (parallel R jobs per batch; consolidated into one CSV). working-sector/fetch_screener_fundamental_details.R formats P&L, last 3 quarters, balance sheet, ratios. Column SCREENER_FETCH_AT records UTC time of this pull (or file mtime when reusing CSV). No substitution from fundamental_scores_database.csv.
- CAN SLIM / Minervini / TRADING_SIGNAL: merged from the selected comprehensive_nse_enhanced CSV (TECHNICAL_SCORE-based rules in fixed_nse_universe_analysis.determine_trading_signal).
- APEX_GUIDANCE: if Screener data incomplete → REVIEW_DATA; else if TRADING_SIGNAL missing → REVIEW_NO_TECH; else if COMPOSITE ≥ batch median (0.5931) keep TRADING_SIGNAL; else one-step downgrade.
- Index narrative: 60-session total return of stock vs benchmark index series in nse_index_data.csv; tags from INDEX_TAGS map to benchmarks via INDEX_TO_BENCHMARK_SYMBOL (documented fallbacks).

## Inputs

- **Comprehensive analysis CSV:** `reports/comprehensive_nse_enhanced_20260428.csv`
- **Screener.in extract CSV:** `/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/reports/Apex_Resilience_screener_fundamentals_20260428.csv`

## Holdings table

| SYMBOL | INDEX_TAGS | APEX_GUIDANCE | TRADING_SIGNAL | COMPOSITE | CAN_SLIM | MINERVINI | SCREENER_OK |
|--------|--------------|---------------|----------------|-----------|----------|-----------|-------------|
| STLTECH | NIFTY MICROCAP 250 | HOLD | HOLD | 3.057 | 15.0 | 11.0 | Y |
| TRITURBINE | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.845 | 13.0 | 9.0 | Y |
| KIRLPNU | NIFTY MICROCAP 250 | HOLD | HOLD | 1.656 | 20.0 | 6.0 | Y |
| LUXIND | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.638 | 15.0 | 6.0 | Y |
| ARE&M | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.549 | 6.0 | 7.0 | Y |
| AZAD | NIFTY MICROCAP 250 | HOLD | HOLD | 1.527 | 15.0 | 6.0 | Y |
| MTARTECH | NIFTY INDIA DEFENCE,NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.450 | 15.0 | 6.0 | Y |
| KRN | NIFTY MICROCAP 250 | HOLD | HOLD | 1.450 | 16.0 | 6.0 | Y |
| POWERINDIA | NIFTY 500 | HOLD | HOLD | 1.424 | 15.0 | 9.0 | Y |
| BBL | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 1.341 | nan | nan | Y |
| ADANIGREEN | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.334 | 15.0 | 6.0 | Y |
| TDPOWERSYS | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.281 | 15.0 | 6.0 | Y |
| TIPSMUSIC | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.236 | 13.0 | 4.0 | Y |
| NEOGEN | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 1.218 | nan | nan | Y |
| WELCORP | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.212 | 15.0 | 9.0 | Y |
| GALLANTT | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.170 | 15.0 | 6.0 | Y |
| NAVA | NIFTY 500 | HOLD | HOLD | 1.107 | 13.0 | 11.0 | Y |
| HSCL | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.101 | 16.0 | 6.0 | Y |
| VOLTAMP | NIFTY MICROCAP 250 | HOLD | HOLD | 1.100 | 18.0 | 11.0 | Y |
| BHEL | NIFTY 500,NIFTY MIDCAP SELECT | HOLD | HOLD | 1.100 | 15.0 | 6.0 | Y |
| VTL | NIFTY 500 | HOLD | HOLD | 1.097 | 16.0 | 11.0 | Y |
| DATAPATTNS | NIFTY 500,NIFTY INDIA DEFENCE | HOLD | HOLD | 1.085 | 15.0 | 4.0 | Y |
| HFCL | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.079 | 15.0 | 6.0 | Y |
| RELINFRA | NIFTY 500 | REVIEW_NO_TECH | nan | 1.012 | nan | nan | Y |
| OFSS | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.003 | 16.0 | 4.0 | Y |
| ADANIENSOL | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.950 | 15.0 | 6.0 | Y |
| TVSSCS | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.902 | nan | nan | Y |
| KIRLOSENG | NIFTY 500 | HOLD | HOLD | 0.880 | 16.0 | 8.0 | Y |
| AVANTIFEED | NIFTY MICROCAP 250 | HOLD | HOLD | 0.859 | 15.0 | 8.0 | Y |
| ACMESOLAR | NIFTY 500 | HOLD | HOLD | 0.850 | 15.0 | 8.0 | Y |
| NLCINDIA | NIFTY 500,NIFTY CPSE | HOLD | HOLD | 0.799 | 16.0 | 8.0 | Y |
| PREMIERENE | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.785 | 15.0 | 8.0 | Y |
| TORNTPOWER | NIFTY 500 | HOLD | HOLD | 0.756 | 14.0 | 6.0 | Y |
| SUNTECK | NIFTY MICROCAP 250 | SELL | SELL | 0.748 | 5.0 | 8.0 | Y |
| APARINDS | NIFTY 500 | HOLD | HOLD | 0.737 | 15.0 | 8.0 | Y |
| RRKABEL | NIFTY 500 | HOLD | HOLD | 0.678 | 18.0 | 16.0 | Y |
| INDIACEM | NIFTY 500 | SELL | SELL | 0.667 | 6.0 | 8.0 | Y |
| STAR | NIFTY MICROCAP 250 | HOLD | HOLD | 0.636 | 13.0 | 4.0 | Y |
| PRSMJOHNSN | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 0.622 | 9.0 | 8.0 | Y |
| INOXINDIA | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.608 | 15.0 | 6.0 | Y |
| CESC | NIFTY 500 | WEAK_HOLD | HOLD | 0.578 | 16.0 | 8.0 | Y |
| HONASA | NIFTY 500 | WEAK_HOLD | HOLD | 0.573 | 13.0 | 8.0 | Y |
| THERMAX | NIFTY 500 | WEAK_HOLD | HOLD | 0.569 | 15.0 | 8.0 | Y |
| SANSERA | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.561 | 15.0 | 8.0 | Y |
| KTKBANK | NIFTY MICROCAP 250 | HOLD | BUY | 0.560 | 16.0 | 18.0 | Y |
| LLOYDSME | NIFTY 500 | WEAK_HOLD | HOLD | 0.546 | 16.0 | 6.0 | Y |
| VIJAYA | NIFTY 500 | WEAK_HOLD | HOLD | 0.545 | 12.0 | 8.0 | Y |
| SCHNEIDER | NIFTY 500 | REVIEW_NO_TECH | nan | 0.542 | nan | nan | Y |
| SHAILY | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.541 | 11.0 | 0.0 | Y |
| TATACHEM | NIFTY 500 | WEAK_HOLD | HOLD | 0.538 | 18.0 | 14.0 | Y |
| ASTERDM | NIFTY 500 | HOLD | BUY | 0.527 | 14.0 | 8.0 | Y |
| SHARDACROP | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.519 | 6.0 | 16.0 | Y |
| PNBHOUSING | NIFTY 500 | SELL | WEAK_HOLD | 0.519 | 15.0 | 6.0 | Y |
| CGPOWER | NIFTY 500 | WEAK_HOLD | HOLD | 0.511 | 15.0 | 8.0 | Y |
| RADICO | NIFTY 500 | WEAK_HOLD | HOLD | 0.507 | 16.0 | 11.0 | Y |
| PTC | NIFTY MICROCAP 250 | HOLD | BUY | 0.505 | 16.0 | 16.0 | Y |
| SUNFLAG | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.503 | 13.0 | 6.0 | Y |
| IMFA | NIFTY MICROCAP 250 | HOLD | BUY | 0.498 | 18.0 | 14.0 | Y |
| ABB | NIFTY 500 | WEAK_HOLD | HOLD | 0.495 | 15.0 | 8.0 | Y |
| YATHARTH | NIFTY MICROCAP 250 | HOLD | BUY | 0.494 | 18.0 | 16.0 | Y |
| CHENNPETRO | NIFTY 500 | HOLD | BUY | 0.492 | 16.0 | 14.0 | Y |
| RATNAMANI | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.491 | nan | nan | Y |
| TATAPOWER | NIFTY 500 | WEAK_HOLD | HOLD | 0.484 | 18.0 | 10.0 | Y |
| AUROPHARMA | NIFTY 500,NIFTY MIDCAP SELECT | WEAK_HOLD | HOLD | 0.482 | 13.0 | 10.0 | Y |
| KSB | NIFTY 500 | SELL | WEAK_HOLD | 0.481 | 15.0 | 8.0 | Y |
| JSWENERGY | NIFTY 500 | WEAK_HOLD | HOLD | 0.477 | 16.0 | 10.0 | Y |
| AARTIIND | NIFTY 500 | WEAK_HOLD | HOLD | 0.471 | 14.0 | 6.0 | Y |
| ADVENZYMES | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.462 | 18.0 | 6.0 | Y |
| ENGINERSIN | NIFTY 500 | SELL | WEAK_HOLD | 0.457 | 15.0 | 6.0 | Y |
| JSFB | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.448 | 16.0 | 7.0 | Y |
| INGERRAND | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.436 | nan | nan | Y |
| DMART | NIFTY 500 | WEAK_HOLD | HOLD | 0.426 | 13.0 | 8.0 | Y |
| GESHIP | NIFTY 500 | WEAK_HOLD | HOLD | 0.426 | 8.0 | 18.0 | Y |
| VSTIND | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.426 | 11.0 | 11.0 | Y |
| ADANIENT | NIFTY 500 | WEAK_HOLD | HOLD | 0.422 | 14.0 | 14.0 | Y |
| CEIGALL | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.420 | 13.0 | 8.0 | Y |
| ISGEC | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.416 | nan | nan | Y |
| NTPCGREEN | NIFTY 500 | WEAK_HOLD | HOLD | 0.411 | 15.0 | 8.0 | Y |
| SAIL | NIFTY 500 | WEAK_HOLD | HOLD | 0.408 | 13.0 | 8.0 | Y |
| LLOYDSENT | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.407 | nan | nan | Y |

## Screener summaries (verbatim columns)

### STLTECH
- **pnl_summary:** Sales: 4363 Cr (YoY +9.2%); NetProfit: -43 Cr (YoY +65%); EPS: -0.89
- **quarterly_summary:** Sales last 3Q: 1020, 1034, 1257 Cr; Net Profit last 3Q: 10, 4, -17 Cr
- **balance_sheet_summary:** Debt: 1921 Cr
- **ratios_summary:** ROCE: 0%; EPS: -0.89; NPM: -0.99%

### TRITURBINE
- **pnl_summary:** Sales: 2040 Cr (YoY +1.7%); NetProfit: 342 Cr (YoY -4.7%); EPS: 10.75
- **quarterly_summary:** Sales last 3Q: 371, 506, 624 Cr; Net Profit last 3Q: 64, 91, 92 Cr
- **balance_sheet_summary:** Debt: 38 Cr
- **ratios_summary:** ROCE: 48%; EPS: 10.75; NPM: 16.76%

### KIRLPNU
- **pnl_summary:** Sales: 1787 Cr (YoY +9%); NetProfit: 254 Cr (YoY +20.4%); EPS: 39.43
- **quarterly_summary:** Sales last 3Q: 386, 407, 712 Cr; Net Profit last 3Q: 44, 42, 144 Cr
- **balance_sheet_summary:** Debt: 3 Cr
- **ratios_summary:** ROCE: 30%; EPS: 39.43; NPM: 14.21%

### LUXIND
- **pnl_summary:** Sales: 2873 Cr (YoY +11.2%); NetProfit: 107 Cr (YoY -35.2%); EPS: 35.92
- **quarterly_summary:** Sales last 3Q: 604, 779, 673 Cr; Net Profit last 3Q: 23, 23, 13 Cr
- **balance_sheet_summary:** Debt: 575 Cr
- **ratios_summary:** ROCE: 13%; EPS: 35.92; NPM: 3.72%

### ARE&M
- **pnl_summary:** Sales: 13338 Cr (YoY +3.8%); NetProfit: 743 Cr (YoY -21.4%); EPS: 40.6
- **quarterly_summary:** Sales last 3Q: 3401, 3467, 3410 Cr; Net Profit last 3Q: 165, 276, 140 Cr
- **balance_sheet_summary:** Debt: 310 Cr
- **ratios_summary:** ROCE: 17%; EPS: 40.6; NPM: 5.57%

### AZAD
- **pnl_summary:** Sales: 568 Cr (YoY +24.3%); NetProfit: 122 Cr (YoY +40.2%); EPS: 18.92
- **quarterly_summary:** Sales last 3Q: 137, 146, 159 Cr; Net Profit last 3Q: 29, 33, 35 Cr
- **balance_sheet_summary:** Debt: 312 Cr
- **ratios_summary:** ROCE: 12%; EPS: 18.92; NPM: 21.48%

### MTARTECH
- **pnl_summary:** Sales: 753 Cr (YoY +11.4%); NetProfit: 63 Cr (YoY +18.9%); EPS: 20.63
- **quarterly_summary:** Sales last 3Q: 157, 136, 278 Cr; Net Profit last 3Q: 11, 4, 35 Cr
- **balance_sheet_summary:** Debt: 186 Cr
- **ratios_summary:** ROCE: 11%; EPS: 20.63; NPM: 8.37%

### KRN
- **pnl_summary:** Sales: 552 Cr (YoY +28.4%); NetProfit: 68 Cr (YoY +28.3%); EPS: 10.94
- **quarterly_summary:** Sales last 3Q: 115, 152, 153 Cr; Net Profit last 3Q: 12, 18, 23 Cr
- **balance_sheet_summary:** Debt: 30 Cr
- **ratios_summary:** ROCE: 21%; EPS: 10.94; NPM: 12.32%

### POWERINDIA
- **pnl_summary:** Sales: 7277 Cr (YoY +14%); NetProfit: 841 Cr (YoY +119%); EPS: 188.74
- **quarterly_summary:** Sales last 3Q: 1479, 1833, 2082 Cr; Net Profit last 3Q: 132, 264, 261 Cr
- **balance_sheet_summary:** Debt: 84 Cr
- **ratios_summary:** ROCE: 19%; EPS: 188.74; NPM: 11.56%

### BBL
- **pnl_summary:** Sales: 2126 Cr (YoY +11.8%); NetProfit: 131 Cr (YoY -2.2%); EPS: 115.99
- **quarterly_summary:** Sales last 3Q: 465, 473, 568 Cr; Net Profit last 3Q: 28, 28, 25 Cr
- **balance_sheet_summary:** Debt: 191 Cr
- **ratios_summary:** ROCE: 10%; EPS: 115.99; NPM: 6.16%

### ADANIGREEN
- **pnl_summary:** Sales: 12928 Cr (YoY +15.3%); NetProfit: 1987 Cr (YoY -0.7%); EPS: 10.03
- **quarterly_summary:** Sales last 3Q: 3008, 2618, 3502 Cr; Net Profit last 3Q: 644, 5, 514 Cr
- **balance_sheet_summary:** Debt: 103545 Cr
- **ratios_summary:** ROCE: 6%; EPS: 10.03; NPM: 15.37%

### TDPOWERSYS
- **pnl_summary:** Sales: 1615 Cr (YoY +26.3%); NetProfit: 220 Cr (YoY +25.7%); EPS: 14.06
- **quarterly_summary:** Sales last 3Q: 372, 452, 443 Cr; Net Profit last 3Q: 50, 60, 56 Cr
- **balance_sheet_summary:** Debt: 36 Cr
- **ratios_summary:** ROCE: 28%; EPS: 14.06; NPM: 13.62%

### TIPSMUSIC
- **pnl_summary:** Sales: 376 Cr (YoY +20.9%); NetProfit: 217 Cr (YoY +29.9%); EPS: 16.96
- **quarterly_summary:** Sales last 3Q: 89, 94, 104 Cr; Net Profit last 3Q: 53, 59, 59 Cr
- **balance_sheet_summary:** Debt: 5 Cr
- **ratios_summary:** ROCE: 122%; EPS: 16.96; NPM: 57.71%

### NEOGEN
- **pnl_summary:** Sales: 818 Cr (YoY +5.1%); NetProfit: 20 Cr (YoY -42.9%); EPS: 7.48
- **quarterly_summary:** Sales last 3Q: 187, 209, 220 Cr; Net Profit last 3Q: 10, 3, 4 Cr
- **balance_sheet_summary:** Debt: 1132 Cr
- **ratios_summary:** ROCE: 11%; EPS: 7.48; NPM: 2.44%

### WELCORP
- **pnl_summary:** Sales: 16383 Cr (YoY +17.2%); NetProfit: 1948 Cr (YoY +2.4%); EPS: 73.77
- **quarterly_summary:** Sales last 3Q: 3551, 4374, 4532 Cr; Net Profit last 3Q: 349, 444, 456 Cr
- **balance_sheet_summary:** Debt: 1545 Cr
- **ratios_summary:** ROCE: 18%; EPS: 73.77; NPM: 11.89%

### GALLANTT
- **pnl_summary:** Sales: 4286 Cr (YoY -0.2%); NetProfit: 479 Cr (YoY +19.5%); EPS: 19.87
- **quarterly_summary:** Sales last 3Q: 1128, 1013, 1074 Cr; Net Profit last 3Q: 174, 89, 100 Cr
- **balance_sheet_summary:** Debt: 657 Cr
- **ratios_summary:** ROCE: 19%; EPS: 19.87; NPM: 11.18%

### NAVA
- **pnl_summary:** Sales: 4166 Cr (YoY +4.6%); NetProfit: 1205 Cr (YoY -16%); EPS: 31.58
- **quarterly_summary:** Sales last 3Q: 1193, 964, 991 Cr; Net Profit last 3Q: 399, 178, 326 Cr
- **balance_sheet_summary:** Debt: 1596 Cr
- **ratios_summary:** ROCE: 14%; EPS: 31.58; NPM: 28.92%

### HSCL
- **pnl_summary:** Sales: 4661 Cr (YoY +1%); NetProfit: 755 Cr (YoY +36%); EPS: 14.89
- **quarterly_summary:** Sales last 3Q: 1071, 1184, 1288 Cr; Net Profit last 3Q: 176, 192, 208 Cr
- **balance_sheet_summary:** Debt: 768 Cr
- **ratios_summary:** ROCE: 23%; EPS: 14.89; NPM: 16.2%

### VOLTAMP
- **pnl_summary:** Sales: 2161 Cr (YoY +11.7%); NetProfit: 354 Cr (YoY +8.9%); EPS: 350.21
- **quarterly_summary:** Sales last 3Q: 424, 483, 630 Cr; Net Profit last 3Q: 80, 79, 99 Cr
- **balance_sheet_summary:** Debt: 1 Cr
- **ratios_summary:** ROCE: 29%; EPS: 350.21; NPM: 16.38%

### BHEL
- **pnl_summary:** Sales: 30465 Cr (YoY +7.5%); NetProfit: 814 Cr (YoY +52.4%); EPS: 2.34
- **quarterly_summary:** Sales last 3Q: 5487, 7512, 8473 Cr; Net Profit last 3Q: -456, 375, 390 Cr
- **balance_sheet_summary:** Debt: 10969 Cr
- **ratios_summary:** ROCE: 5%; EPS: 2.34; NPM: 2.67%

### VTL
- **pnl_summary:** Sales: 9880 Cr (YoY +1%); NetProfit: 802 Cr (YoY -9.6%); EPS: 27.59
- **quarterly_summary:** Sales last 3Q: 2386, 2480, 2505 Cr; Net Profit last 3Q: 208, 188, 168 Cr
- **balance_sheet_summary:** Debt: 1479 Cr
- **ratios_summary:** ROCE: 11%; EPS: 27.59; NPM: 8.12%

### DATAPATTNS
- **pnl_summary:** Sales: 976 Cr (YoY +37.9%); NetProfit: 247 Cr (YoY +11.3%); EPS: 44.13
- **quarterly_summary:** Sales last 3Q: 99, 307, 173 Cr; Net Profit last 3Q: 26, 49, 58 Cr
- **balance_sheet_summary:** Debt: 6 Cr
- **ratios_summary:** ROCE: 21%; EPS: 44.13; NPM: 25.31%

### HFCL
- **pnl_summary:** Sales: 3926 Cr (YoY -3.4%); NetProfit: 62 Cr (YoY -64.2%); EPS: 0.33
- **quarterly_summary:** Sales last 3Q: 871, 1043, 1211 Cr; Net Profit last 3Q: -29, 72, 102 Cr
- **balance_sheet_summary:** Debt: 1580 Cr
- **ratios_summary:** ROCE: 8%; EPS: 0.33; NPM: 1.58%

### RELINFRA
- **pnl_summary:** Sales: 20547 Cr (YoY -15.9%); NetProfit: 11460 Cr (YoY +24.9%); EPS: 159.25
- **quarterly_summary:** Sales last 3Q: 5908, 6235, 4297 Cr; Net Profit last 3Q: 305, 2575, 317 Cr
- **balance_sheet_summary:** Debt: 5737 Cr
- **ratios_summary:** ROCE: -1%; EPS: 159.25; NPM: 55.77%

### OFSS
- **pnl_summary:** Sales: 7672 Cr (YoY +12%); NetProfit: 2639 Cr (YoY +10.9%); EPS: 303.25
- **quarterly_summary:** Sales last 3Q: 1789, 1966, 2065 Cr; Net Profit last 3Q: 546, 610, 842 Cr
- **balance_sheet_summary:** Debt: 32 Cr
- **ratios_summary:** ROCE: 49%; EPS: 303.25; NPM: 34.4%

### ADANIENSOL
- **pnl_summary:** Sales: 27588 Cr (YoY +16.1%); NetProfit: 2393 Cr (YoY +159.5%); EPS: 19
- **quarterly_summary:** Sales last 3Q: 6596, 6730, 7443 Cr; Net Profit last 3Q: 557, 574, 723 Cr
- **balance_sheet_summary:** Debt: 49176 Cr
- **ratios_summary:** ROCE: 5%; EPS: 19; NPM: 8.67%

### TVSSCS
- **pnl_summary:** Sales: 10470 Cr (YoY +4.7%); NetProfit: 95 Cr (YoY +1050%); EPS: 2.08
- **quarterly_summary:** Sales last 3Q: 2592, 2663, 2716 Cr; Net Profit last 3Q: 71, 16, 11 Cr
- **balance_sheet_summary:** Debt: 2221 Cr
- **ratios_summary:** ROCE: 4%; EPS: 2.08; NPM: 0.91%

### KIRLOSENG
- **pnl_summary:** Sales: 7334 Cr (YoY +15.5%); NetProfit: 534 Cr (YoY +12.2%); EPS: 37.64
- **quarterly_summary:** Sales last 3Q: 1764, 1948, 1873 Cr; Net Profit last 3Q: 139, 159, 109 Cr
- **balance_sheet_summary:** Debt: 5526 Cr
- **ratios_summary:** ROCE: 18%; EPS: 37.64; NPM: 7.28%

### AVANTIFEED
- **pnl_summary:** Sales: 5981 Cr (YoY +6.6%); NetProfit: 675 Cr (YoY +21.2%); EPS: 46.44
- **quarterly_summary:** Sales last 3Q: 1606, 1609, 1384 Cr; Net Profit last 3Q: 186, 169, 163 Cr
- **balance_sheet_summary:** Debt: 15 Cr
- **ratios_summary:** ROCE: 29%; EPS: 46.44; NPM: 11.29%

### ACMESOLAR
- **pnl_summary:** Sales: 1962 Cr (YoY +39.6%); NetProfit: 482 Cr (YoY +92%); EPS: 7.98
- **quarterly_summary:** Sales last 3Q: 511, 468, 497 Cr; Net Profit last 3Q: 131, 115, 114 Cr
- **balance_sheet_summary:** Debt: 12998 Cr
- **ratios_summary:** ROCE: 8%; EPS: 7.98; NPM: 24.57%

### NLCINDIA
- **pnl_summary:** Sales: 16283 Cr (YoY +6.3%); NetProfit: 2756 Cr (YoY +1.5%); EPS: 18.83
- **quarterly_summary:** Sales last 3Q: 3826, 4178, 4443 Cr; Net Profit last 3Q: 839, 725, 724 Cr
- **balance_sheet_summary:** Debt: 24368 Cr
- **ratios_summary:** ROCE: 9%; EPS: 18.83; NPM: 16.93%

### PREMIERENE
- **pnl_summary:** Sales: 7215 Cr (YoY +10.7%); NetProfit: 1331 Cr (YoY +42%); EPS: 29.44
- **quarterly_summary:** Sales last 3Q: 1821, 1837, 1936 Cr; Net Profit last 3Q: 308, 353, 392 Cr
- **balance_sheet_summary:** Debt: 1622 Cr
- **ratios_summary:** ROCE: 12%; EPS: 29.44; NPM: 18.45%

### TORNTPOWER
- **pnl_summary:** Sales: 29017 Cr (YoY -0.5%); NetProfit: 3215 Cr (YoY +5.1%); EPS: 62.67
- **quarterly_summary:** Sales last 3Q: 7906, 7876, 6778 Cr; Net Profit last 3Q: 742, 742, 655 Cr
- **balance_sheet_summary:** Debt: 10431 Cr
- **ratios_summary:** ROCE: 17%; EPS: 62.67; NPM: 11.08%

### SUNTECK
- **pnl_summary:** Sales: 1124 Cr (YoY +31.8%); NetProfit: 202 Cr (YoY +34.7%); EPS: 13.92
- **quarterly_summary:** Sales last 3Q: 252, 344, 339 Cr; Net Profit last 3Q: 49, 57, 63 Cr
- **balance_sheet_summary:** Debt: 774 Cr
- **ratios_summary:** ROCE: 1%; EPS: 13.92; NPM: 17.97%

### APARINDS
- **pnl_summary:** Sales: 21509 Cr (YoY +15.8%); NetProfit: 974 Cr (YoY +18.6%); EPS: 242.35
- **quarterly_summary:** Sales last 3Q: 5104, 5715, 5480 Cr; Net Profit last 3Q: 263, 252, 209 Cr
- **balance_sheet_summary:** Debt: 704 Cr
- **ratios_summary:** ROCE: 33%; EPS: 242.35; NPM: 4.53%

### RRKABEL
- **pnl_summary:** Sales: 8976 Cr (YoY +17.8%); NetProfit: 453 Cr (YoY +45.2%); EPS: 40.1
- **quarterly_summary:** Sales last 3Q: 2059, 2164, 2536 Cr; Net Profit last 3Q: 90, 116, 118 Cr
- **balance_sheet_summary:** Debt: 393 Cr
- **ratios_summary:** ROCE: 20%; EPS: 40.1; NPM: 5.05%

### INDIACEM
- **pnl_summary:** Sales: 4485 Cr (YoY +8.1%); NetProfit: -67 Cr (YoY +53.5%); EPS: -2.17
- **quarterly_summary:** Sales last 3Q: 1117, 1114, 1229 Cr; Net Profit last 3Q: 9, -3, 60 Cr
- **balance_sheet_summary:** Debt: 1305 Cr
- **ratios_summary:** ROCE: 2%; EPS: -2.17; NPM: -1.49%

### STAR
- **pnl_summary:** Sales: 4726 Cr (YoY +3.5%); NetProfit: 531 Cr (YoY -85.2%); EPS: 55.48
- **quarterly_summary:** Sales last 3Q: 1120, 1221, 1195 Cr; Net Profit last 3Q: 106, 132, 208 Cr
- **balance_sheet_summary:** Debt: 1844 Cr
- **ratios_summary:** ROCE: 5%; EPS: 55.48; NPM: 11.24%

### PRSMJOHNSN
- **pnl_summary:** Sales: 7723 Cr (YoY +5.6%); NetProfit: 167 Cr (YoY +271.1%); EPS: 3.89
- **quarterly_summary:** Sales last 3Q: 1922, 1855, 1844 Cr; Net Profit last 3Q: -6, 2, 50 Cr
- **balance_sheet_summary:** Debt: 1694 Cr
- **ratios_summary:** ROCE: 3%; EPS: 3.89; NPM: 2.16%

### INOXINDIA
- **pnl_summary:** Sales: 1496 Cr (YoY +14.5%); NetProfit: 248 Cr (YoY +9.7%); EPS: 27.34
- **quarterly_summary:** Sales last 3Q: 340, 358, 429 Cr; Net Profit last 3Q: 61, 61, 61 Cr
- **balance_sheet_summary:** Debt: 99 Cr
- **ratios_summary:** ROCE: 37%; EPS: 27.34; NPM: 16.58%

### CESC
- **pnl_summary:** Sales: 18351 Cr (YoY +7.9%); NetProfit: 1541 Cr (YoY +7.9%); EPS: 11.11
- **quarterly_summary:** Sales last 3Q: 5202, 5267, 4005 Cr; Net Profit last 3Q: 404, 448, 304 Cr
- **balance_sheet_summary:** Debt: 18811 Cr
- **ratios_summary:** ROCE: 10%; EPS: 11.11; NPM: 8.4%

### HONASA
- **pnl_summary:** Sales: 2268 Cr (YoY +9.7%); NetProfit: 156 Cr (YoY +113.7%); EPS: 4.79
- **quarterly_summary:** Sales last 3Q: 595, 538, 602 Cr; Net Profit last 3Q: 41, 39, 50 Cr
- **balance_sheet_summary:** Debt: 142 Cr
- **ratios_summary:** ROCE: 7%; EPS: 4.79; NPM: 6.88%

### THERMAX
- **pnl_summary:** Sales: 10351 Cr (YoY -0.4%); NetProfit: 681 Cr (YoY +8.6%); EPS: 57.24
- **quarterly_summary:** Sales last 3Q: 2158, 2474, 2635 Cr; Net Profit last 3Q: 151, 119, 205 Cr
- **balance_sheet_summary:** Debt: 1811 Cr
- **ratios_summary:** ROCE: 17%; EPS: 57.24; NPM: 6.58%

### SANSERA
- **pnl_summary:** Sales: 3281 Cr (YoY +8.8%); NetProfit: 263 Cr (YoY +21.2%); EPS: 42.21
- **quarterly_summary:** Sales last 3Q: 766, 825, 908 Cr; Net Profit last 3Q: 63, 71, 69 Cr
- **balance_sheet_summary:** Debt: 439 Cr
- **ratios_summary:** ROCE: 13%; EPS: 42.21; NPM: 8.02%

### KTKBANK
- **pnl_summary:** Revenue: 8919 Cr (YoY -1.1%); NetProfit: 1155 Cr (YoY -9.3%); EPS: 30.55
- **quarterly_summary:** Sales last 3Q: 2261, 2179, 2220 Cr; Net Profit last 3Q: 292, 319, 291 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 11%; EPS: 30.55; NPM: 12.95%

### LLOYDSME
- **pnl_summary:** Sales: 12286 Cr (YoY +82.8%); NetProfit: 2500 Cr (YoY +72.4%); EPS: 46.23
- **quarterly_summary:** Sales last 3Q: 2384, 3651, 5058 Cr; Net Profit last 3Q: 642, 567, 1090 Cr
- **balance_sheet_summary:** Debt: 8163 Cr
- **ratios_summary:** ROCE: 38%; EPS: 46.23; NPM: 20.35%

### VIJAYA
- **pnl_summary:** Sales: 768 Cr (YoY +12.8%); NetProfit: 160 Cr (YoY +11.1%); EPS: 15.55
- **quarterly_summary:** Sales last 3Q: 188, 202, 205 Cr; Net Profit last 3Q: 39, 43, 43 Cr
- **balance_sheet_summary:** Debt: 365 Cr
- **ratios_summary:** ROCE: 20%; EPS: 15.55; NPM: 20.83%

### SCHNEIDER
- **pnl_summary:** Sales: 2888 Cr (YoY +9.5%); NetProfit: 245 Cr (YoY -8.6%); EPS: 10.25
- **quarterly_summary:** Sales last 3Q: 622, 650, 1029 Cr; Net Profit last 3Q: 41, 52, 97 Cr
- **balance_sheet_summary:** Debt: 527 Cr
- **ratios_summary:** ROCE: 41%; EPS: 10.25; NPM: 8.48%

### SHAILY
- **pnl_summary:** Sales: 972 Cr (YoY +23.5%); NetProfit: 158 Cr (YoY +69.9%); EPS: 34.45
- **quarterly_summary:** Sales last 3Q: 247, 257, 250 Cr; Net Profit last 3Q: 41, 51, 37 Cr
- **balance_sheet_summary:** Debt: 189 Cr
- **ratios_summary:** ROCE: 17%; EPS: 34.45; NPM: 16.26%

### TATACHEM
- **pnl_summary:** Sales: 14655 Cr (YoY -1.6%); NetProfit: 352 Cr (YoY -9%); EPS: 7.06
- **quarterly_summary:** Sales last 3Q: 3719, 3877, 3550 Cr; Net Profit last 3Q: 316, 154, -69 Cr
- **balance_sheet_summary:** Debt: 7495 Cr
- **ratios_summary:** ROCE: 4%; EPS: 7.06; NPM: 2.4%

### ASTERDM
- **pnl_summary:** Sales: 4461 Cr (YoY +7.8%); NetProfit: 359 Cr (YoY -93.4%); EPS: 6.36
- **quarterly_summary:** Sales last 3Q: 1078, 1197, 1186 Cr; Net Profit last 3Q: 94, 121, 59 Cr
- **balance_sheet_summary:** Debt: 2089 Cr
- **ratios_summary:** ROCE: 139%; EPS: 6.36; NPM: 8.05%

### SHARDACROP
- **pnl_summary:** Sales: 5031 Cr (YoY +16.5%); NetProfit: 566 Cr (YoY +86.2%); EPS: 62.72
- **quarterly_summary:** Sales last 3Q: 985, 929, 1289 Cr; Net Profit last 3Q: 143, 74, 145 Cr
- **balance_sheet_summary:** Debt: 4 Cr
- **ratios_summary:** ROCE: 16%; EPS: 62.72; NPM: 11.25%

### PNBHOUSING
- **pnl_summary:** Revenue: 8505 Cr (YoY +10.7%); NetProfit: 2291 Cr (YoY +18.3%); EPS: 87.94
- **quarterly_summary:** Sales last 3Q: 2128, 2119, 2182 Cr; Net Profit last 3Q: 582, 520, 656 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 12%; EPS: 87.94; NPM: 26.94%

### CGPOWER
- **pnl_summary:** Sales: 11729 Cr (YoY +18.4%); NetProfit: 1109 Cr (YoY +14%); EPS: 7.17
- **quarterly_summary:** Sales last 3Q: 2878, 2923, 3175 Cr; Net Profit last 3Q: 267, 284, 284 Cr
- **balance_sheet_summary:** Debt: 117 Cr
- **ratios_summary:** ROCE: 36%; EPS: 7.17; NPM: 9.46%

### RADICO
- **pnl_summary:** Sales: 5851 Cr (YoY +20.8%); NetProfit: 517 Cr (YoY +49.4%); EPS: 38.62
- **quarterly_summary:** Sales last 3Q: 1506, 1494, 1547 Cr; Net Profit last 3Q: 131, 140, 155 Cr
- **balance_sheet_summary:** Debt: 624 Cr
- **ratios_summary:** ROCE: 16%; EPS: 38.62; NPM: 8.84%

### PTC
- **pnl_summary:** Sales: 15797 Cr (YoY -2.7%); NetProfit: 968 Cr (YoY -0.8%); EPS: 28.78
- **quarterly_summary:** Sales last 3Q: 4009, 5459, 3405 Cr; Net Profit last 3Q: 243, 222, 131 Cr
- **balance_sheet_summary:** Debt: 2264 Cr
- **ratios_summary:** ROCE: 12%; EPS: 28.78; NPM: 6.13%

### SUNFLAG
- **pnl_summary:** Sales: 3822 Cr (YoY +8.1%); NetProfit: 211 Cr (YoY +30.2%); EPS: 11.73
- **quarterly_summary:** Sales last 3Q: 1023, 973, 942 Cr; Net Profit last 3Q: 63, 46, 60 Cr
- **balance_sheet_summary:** Debt: 580 Cr
- **ratios_summary:** ROCE: 4%; EPS: 11.73; NPM: 5.52%

### IMFA
- **pnl_summary:** Sales: 2630 Cr (YoY +2.5%); NetProfit: 369 Cr (YoY -2.6%); EPS: 68.28
- **quarterly_summary:** Sales last 3Q: 642, 719, 703 Cr; Net Profit last 3Q: 93, 98, 131 Cr
- **balance_sheet_summary:** Debt: 435 Cr
- **ratios_summary:** ROCE: 21%; EPS: 68.28; NPM: 14.03%

### ABB
- **pnl_summary:** Sales: 13203 Cr (YoY +8.3%); NetProfit: 1668 Cr (YoY -10.9%); EPS: 78.73
- **quarterly_summary:** Sales last 3Q: 3175, 3311, 3557 Cr; Net Profit last 3Q: 352, 409, 433 Cr
- **balance_sheet_summary:** Debt: 85 Cr
- **ratios_summary:** ROCE: 30%; EPS: 78.73; NPM: 12.63%

### YATHARTH
- **pnl_summary:** Sales: 1089 Cr (YoY +26.6%); NetProfit: 165 Cr (YoY +26%); EPS: 17.37
- **quarterly_summary:** Sales last 3Q: 258, 279, 320 Cr; Net Profit last 3Q: 42, 41, 43 Cr
- **balance_sheet_summary:** Debt: 26 Cr
- **ratios_summary:** ROCE: 10%; EPS: 17.37; NPM: 15.15%

### CHENNPETRO
- **pnl_summary:** Sales: 63640 Cr (YoY +7.9%); NetProfit: 3103 Cr (YoY +1350%); EPS: 208.36
- **quarterly_summary:** Sales last 3Q: 16327, 15683, 16817 Cr; Net Profit last 3Q: 719, 1002, 1422 Cr
- **balance_sheet_summary:** Debt: 1964 Cr
- **ratios_summary:** ROCE: 36%; EPS: 208.36; NPM: 4.88%

### RATNAMANI
- **pnl_summary:** Sales: 5124 Cr (YoY -1.2%); NetProfit: 622 Cr (YoY +14.8%); EPS: 83.46
- **quarterly_summary:** Sales last 3Q: 1152, 1192, 1066 Cr; Net Profit last 3Q: 127, 156, 135 Cr
- **balance_sheet_summary:** Debt: 241 Cr
- **ratios_summary:** ROCE: 22%; EPS: 83.46; NPM: 12.14%

### TATAPOWER
- **pnl_summary:** Sales: 64624 Cr (YoY -1.3%); NetProfit: 5008 Cr (YoY +4.9%); EPS: 11.88
- **quarterly_summary:** Sales last 3Q: 18035, 15545, 13948 Cr; Net Profit last 3Q: 1262, 1245, 1194 Cr
- **balance_sheet_summary:** Debt: 70083 Cr
- **ratios_summary:** ROCE: 15%; EPS: 11.88; NPM: 7.75%

### AUROPHARMA
- **pnl_summary:** Sales: 33182 Cr (YoY +4.6%); NetProfit: 3485 Cr (YoY +0%); EPS: 60.04
- **quarterly_summary:** Sales last 3Q: 7868, 8286, 8646 Cr; Net Profit last 3Q: 824, 848, 910 Cr
- **balance_sheet_summary:** Debt: 7794 Cr
- **ratios_summary:** ROCE: 11%; EPS: 60.04; NPM: 10.5%

### KSB
- **pnl_summary:** Sales: 2696 Cr (YoY +6.4%); NetProfit: 270 Cr (YoY +9.3%); EPS: 15.54
- **quarterly_summary:** Sales last 3Q: 667, 650, 784 Cr; Net Profit last 3Q: 70, 68, 81 Cr
- **balance_sheet_summary:** Debt: 5 Cr
- **ratios_summary:** ROCE: 25%; EPS: 15.54; NPM: 10.01%

### JSWENERGY
- **pnl_summary:** Sales: 17592 Cr (YoY +49.8%); NetProfit: 2603 Cr (YoY +31.3%); EPS: 13.01
- **quarterly_summary:** Sales last 3Q: 5143, 5177, 4082 Cr; Net Profit last 3Q: 836, 824, 529 Cr
- **balance_sheet_summary:** Debt: 69104 Cr
- **ratios_summary:** ROCE: 6%; EPS: 13.01; NPM: 14.8%

### AARTIIND
- **pnl_summary:** Sales: 8042 Cr (YoY +10.6%); NetProfit: 378 Cr (YoY +14.2%); EPS: 10.43
- **quarterly_summary:** Sales last 3Q: 1675, 2100, 2318 Cr; Net Profit last 3Q: 43, 106, 133 Cr
- **balance_sheet_summary:** Debt: 3973 Cr
- **ratios_summary:** ROCE: 6%; EPS: 10.43; NPM: 4.7%

### ADVENZYMES
- **pnl_summary:** Sales: 710 Cr (YoY +11.5%); NetProfit: 155 Cr (YoY +15.7%); EPS: 13.61
- **quarterly_summary:** Sales last 3Q: 186, 185, 172 Cr; Net Profit last 3Q: 40, 45, 43 Cr
- **balance_sheet_summary:** Debt: 35 Cr
- **ratios_summary:** ROCE: 20%; EPS: 13.61; NPM: 21.83%

### ENGINERSIN
- **pnl_summary:** Sales: 4012 Cr (YoY +29.9%); NetProfit: 776 Cr (YoY +33.8%); EPS: 13.81
- **quarterly_summary:** Sales last 3Q: 870, 921, 1210 Cr; Net Profit last 3Q: 65, 83, 347 Cr
- **balance_sheet_summary:** Debt: 20 Cr
- **ratios_summary:** ROCE: 24%; EPS: 13.81; NPM: 19.34%

### JSFB
- **pnl_summary:** Revenue: 5140 Cr (YoY +9.1%); NetProfit: 310 Cr (YoY -38.1%); EPS: 29.49
- **quarterly_summary:** Sales last 3Q: 1252, 1305, 1384 Cr; Net Profit last 3Q: 102, 75, 10 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 13%; EPS: 29.49; NPM: 6.03%

### INGERRAND
- **pnl_summary:** Sales: 1415 Cr (YoY +5.9%); NetProfit: 259 Cr (YoY -3.4%); EPS: 82
- **quarterly_summary:** Sales last 3Q: 315, 322, 455 Cr; Net Profit last 3Q: 59, 60, 72 Cr
- **balance_sheet_summary:** Debt: 10 Cr
- **ratios_summary:** ROCE: 60%; EPS: 82; NPM: 18.3%

### DMART
- **pnl_summary:** Sales: 66009 Cr (YoY +11.2%); NetProfit: 2864 Cr (YoY +5.8%); EPS: 44.03
- **quarterly_summary:** Sales last 3Q: 16360, 16676, 18101 Cr; Net Profit last 3Q: 773, 685, 856 Cr
- **balance_sheet_summary:** Debt: 1609 Cr
- **ratios_summary:** ROCE: 18%; EPS: 44.03; NPM: 4.34%

### GESHIP
- **pnl_summary:** Sales: 5121 Cr (YoY -3.8%); NetProfit: 2262 Cr (YoY -3.5%); EPS: 158.4
- **quarterly_summary:** Sales last 3Q: 1201, 1242, 1454 Cr; Net Profit last 3Q: 504, 581, 813 Cr
- **balance_sheet_summary:** Debt: 1254 Cr
- **ratios_summary:** ROCE: 15%; EPS: 158.4; NPM: 44.17%

### VSTIND
- **pnl_summary:** Sales: 471 Cr (YoY +23.9%); NetProfit: 62 Cr (YoY +0%); EPS: 3.65
- **quarterly_summary:** Sales last 3Q: 336, 373, 457 Cr; Net Profit last 3Q: 59, 60, 117 Cr
- **balance_sheet_summary:** Debt: 0 Cr
- **ratios_summary:** ROCE: 28%; EPS: 3.65; NPM: 13.16%

### ADANIENT
- **pnl_summary:** Sales: 94995 Cr (YoY -3%); NetProfit: 14132 Cr (YoY +76.5%); EPS: 103.69
- **quarterly_summary:** Sales last 3Q: 21961, 21249, 24820 Cr; Net Profit last 3Q: 976, 3414, 5727 Cr
- **balance_sheet_summary:** Debt: 109465 Cr
- **ratios_summary:** ROCE: 13%; EPS: 103.69; NPM: 14.88%

### CEIGALL
- **pnl_summary:** Sales: 3648 Cr (YoY +6.1%); NetProfit: 252 Cr (YoY -12.2%); EPS: 14.88
- **quarterly_summary:** Sales last 3Q: 838, 807, 991 Cr; Net Profit last 3Q: 51, 56, 72 Cr
- **balance_sheet_summary:** Debt: 1343 Cr
- **ratios_summary:** ROCE: 22%; EPS: 14.88; NPM: 6.91%

### ISGEC
- **pnl_summary:** Sales: 6515 Cr (YoY +1.4%); NetProfit: 297 Cr (YoY +12.5%); EPS: 34.98
- **quarterly_summary:** Sales last 3Q: 1341, 1691, 1739 Cr; Net Profit last 3Q: 59, 56, 84 Cr
- **balance_sheet_summary:** Debt: 925 Cr
- **ratios_summary:** ROCE: 17%; EPS: 34.98; NPM: 4.56%

### NTPCGREEN
- **pnl_summary:** Sales: 2568 Cr (YoY +16.2%); NetProfit: 557 Cr (YoY +17.5%); EPS: 0.66
- **quarterly_summary:** Sales last 3Q: 680, 612, 653 Cr; Net Profit last 3Q: 220, 86, 17 Cr
- **balance_sheet_summary:** Debt: 21826 Cr
- **ratios_summary:** ROCE: 6%; EPS: 0.66; NPM: 21.69%

### SAIL
- **pnl_summary:** Sales: 109313 Cr (YoY +6.7%); NetProfit: 2788 Cr (YoY +17.5%); EPS: 6.75
- **quarterly_summary:** Sales last 3Q: 25922, 26704, 27371 Cr; Net Profit last 3Q: 745, 419, 374 Cr
- **balance_sheet_summary:** Debt: 33663 Cr
- **ratios_summary:** ROCE: 7%; EPS: 6.75; NPM: 2.55%

### LLOYDSENT
- **pnl_summary:** Sales: 1526 Cr (YoY +2.6%); NetProfit: 373 Cr (YoY +203.3%); EPS: 1.66
- **quarterly_summary:** Sales last 3Q: 331, 407, 299 Cr; Net Profit last 3Q: 249, 62, 38 Cr
- **balance_sheet_summary:** Debt: 671 Cr
- **ratios_summary:** ROCE: 1%; EPS: 1.66; NPM: 24.44%
