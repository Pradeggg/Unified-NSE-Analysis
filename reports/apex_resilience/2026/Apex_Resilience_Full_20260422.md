# Apex Resilience Screener — full report (20260422)

Generated (run time): 2026-04-24T07:35:29

## Methodology

- Universe context: index_stock_mapping — NIFTY MIDCAP SELECT, NIFTY 500, NIFTY INDIA DEFENCE, NIFTY CPSE, NIFTY MICROCAP 250.
- This artifact was **patched** by refill_apex_screener_review.py: re-fetched Screener.in for symbols that previously had APEX_GUIDANCE=REVIEW_DATA (2 symbols).
- Composite median after patch: 0.249301; APEX_GUIDANCE recomputed from TRADING_SIGNAL + COMPOSITE vs median + Screener completeness.
- VERIFY figures on screener.in.

## Inputs

- **Comprehensive analysis CSV:** `/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/reports/comprehensive_nse_enhanced_20260422.csv`
- **Screener.in extract CSV:** `/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/reports/Apex_Resilience_screener_fundamentals_20260422.csv`

## Holdings table

| SYMBOL | INDEX_TAGS | APEX_GUIDANCE | TRADING_SIGNAL | COMPOSITE | CAN_SLIM | MINERVINI | SCREENER_OK |
|--------|--------------|---------------|----------------|-----------|----------|-----------|-------------|
| ABB | NIFTY 500 | BUY | BUY | 0.948 | 20.0 | 16.0 | Y |
| BALRAMCHIN | NIFTY 500 | BUY | BUY | 0.556 | 20.0 | 12.0 | Y |
| AZAD | NIFTY MICROCAP 250 | BUY | BUY | 0.911 | 20.0 | 14.0 | Y |
| CHENNPETRO | NIFTY 500 | BUY | BUY | 0.540 | 14.0 | 14.0 | Y |
| CEIGALL | NIFTY MICROCAP 250 | BUY | BUY | 0.423 | 18.0 | 15.0 | Y |
| ASTERDM | NIFTY 500 | BUY | BUY | 0.387 | 14.0 | 15.0 | Y |
| DATAPATTNS | NIFTY 500,NIFTY INDIA DEFENCE | BUY | BUY | 1.040 | 20.0 | 9.0 | Y |
| AUROPHARMA | NIFTY 500,NIFTY MIDCAP SELECT | BUY | BUY | 0.563 | 13.0 | 13.0 | Y |
| SANSERA | NIFTY MICROCAP 250 | BUY | BUY | 0.562 | 20.0 | 16.0 | Y |
| TIMKEN | NIFTY 500 | REVIEW_DATA | BUY | 0.400 | 18.0 | 18.0 | N |
| CGPOWER | NIFTY 500 | BUY | BUY | 0.535 | 16.0 | 11.0 | Y |
| ASTRAMICRO | NIFTY INDIA DEFENCE,NIFTY MICROCAP 250 | BUY | BUY | 0.713 | 13.0 | 8.0 | Y |
| DYNAMATECH | NIFTY INDIA DEFENCE,NIFTY MICROCAP 250 | BUY | BUY | 0.368 | 20.0 | 16.0 | Y |
| ELGIEQUIP | NIFTY 500 | HOLD | BUY | 0.084 | 18.0 | 18.0 | Y |
| BANDHANBNK | NIFTY 500 | HOLD | BUY | -0.006 | 13.0 | 11.0 | Y |
| CIEINDIA | NIFTY MICROCAP 250 | HOLD | BUY | -0.061 | 10.0 | 12.0 | Y |
| JKPAPER | NIFTY MICROCAP 250 | HOLD | BUY | 0.181 | 18.0 | 16.0 | Y |
| APOLLOHOSP | NIFTY 500 | HOLD | BUY | 0.110 | 8.0 | 12.0 | Y |
| TRIVENI | NIFTY 500 | HOLD | BUY | -0.011 | 11.0 | 18.0 | Y |
| NEOGEN | NIFTY MICROCAP 250 | HOLD | HOLD | 1.189 | 20.0 | 14.0 | Y |
| AVANTIFEED | NIFTY MICROCAP 250 | HOLD | HOLD | 1.019 | 15.0 | 8.0 | Y |
| NETWEB | NIFTY 500 | WEAK_HOLD | HOLD | 0.088 | 20.0 | 11.0 | Y |
| VOLTAMP | NIFTY MICROCAP 250 | HOLD | HOLD | 1.073 | 20.0 | 14.0 | Y |
| WELCORP | NIFTY 500 | HOLD | HOLD | 0.840 | 20.0 | 14.0 | Y |
| ADANIENSOL | NIFTY 500 | HOLD | HOLD | 0.691 | 20.0 | 14.0 | Y |
| CCL | NIFTY 500 | WEAK_HOLD | HOLD | 0.220 | 11.0 | 10.0 | Y |
| SUNFLAG | NIFTY MICROCAP 250 | HOLD | HOLD | 0.700 | 18.0 | 14.0 | Y |
| NTPC | NIFTY 500,NIFTY CPSE | HOLD | HOLD | 0.396 | 12.0 | 18.0 | Y |
| CUMMINSIND | NIFTY 500,NIFTY MIDCAP SELECT | HOLD | HOLD | 0.364 | 15.0 | 10.0 | Y |
| DEEPAKNTR | NIFTY 500 | HOLD | HOLD | 0.291 | 14.0 | 9.0 | Y |
| NATIONALUM | NIFTY 500 | HOLD | HOLD | 0.376 | 13.0 | 16.0 | Y |
| EDELWEISS | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.082 | 14.0 | 18.0 | Y |
| APARINDS | NIFTY 500 | HOLD | HOLD | 0.884 | 15.0 | 8.0 | Y |
| BHARATFORG | NIFTY 500,NIFTY INDIA DEFENCE,NIFTY MIDCAP SELECT | HOLD | HOLD | 0.301 | 13.0 | 13.0 | Y |
| ATGL | NIFTY 500 | WEAK_HOLD | HOLD | 0.175 | 13.0 | 14.0 | Y |
| DELHIVERY | NIFTY 500 | WEAK_HOLD | HOLD | 0.148 | 9.0 | 10.0 | Y |
| SAILIFE | NIFTY 500 | WEAK_HOLD | HOLD | 0.138 | 13.0 | 10.0 | Y |
| GRANULES | NIFTY 500 | WEAK_HOLD | HOLD | 0.154 | 14.0 | 13.0 | Y |
| ARE&M | NIFTY 500 | HOLD | HOLD | 0.931 | 11.0 | 12.0 | Y |
| ANANDRATHI | NIFTY 500 | HOLD | HOLD | 0.481 | 15.0 | 8.0 | Y |
| KAJARIACER | NIFTY 500 | WEAK_HOLD | HOLD | 0.105 | 18.0 | 9.0 | Y |
| AMBER | NIFTY 500 | WEAK_HOLD | HOLD | 0.005 | 15.0 | 8.0 | Y |
| GAEL | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.226 | 14.0 | 10.0 | Y |
| INOXINDIA | NIFTY 500 | HOLD | HOLD | 1.340 | 18.0 | 12.0 | Y |
| AETHER | NIFTY MICROCAP 250 | HOLD | HOLD | 0.333 | 13.0 | 10.0 | Y |
| SCHAEFFLER | NIFTY 500 | WEAK_HOLD | HOLD | 0.056 | 12.0 | 14.0 | Y |
| WELENT | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.043 | 14.0 | 14.0 | Y |
| LAURUSLABS | NIFTY 500 | WEAK_HOLD | HOLD | -0.030 | 14.0 | 10.0 | Y |
| ISGEC | NIFTY MICROCAP 250 | HOLD | HOLD | 0.356 | 15.0 | 15.0 | Y |
| ANURAS | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.209 | 8.0 | 10.0 | Y |
| ETHOSLTD | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.174 | 13.0 | 16.0 | Y |
| IREDA | NIFTY 500 | WEAK_HOLD | HOLD | -0.065 | 14.0 | 16.0 | Y |
| SARDAEN | NIFTY 500 | HOLD | HOLD | 0.528 | 13.0 | 18.0 | Y |
| EXIDEIND | NIFTY 500 | WEAK_HOLD | HOLD | -0.047 | 13.0 | 18.0 | Y |
| AARTIIND | NIFTY 500 | HOLD | HOLD | 0.303 | 10.0 | 16.0 | Y |
| JINDALSAW | NIFTY 500 | HOLD | HOLD | 0.302 | 16.0 | 12.0 | Y |
| FORTIS | NIFTY 500 | WEAK_HOLD | HOLD | -0.059 | 12.0 | 13.0 | Y |
| ACMESOLAR | NIFTY 500 | HOLD | HOLD | 0.986 | 15.0 | 14.0 | Y |
| ARVIND | NIFTY MICROCAP 250 | HOLD | HOLD | 0.473 | 7.0 | 10.0 | Y |
| LLOYDSME | NIFTY 500 | HOLD | HOLD | 0.357 | 15.0 | 11.0 | Y |
| CESC | NIFTY 500 | HOLD | HOLD | 0.338 | 13.0 | 8.0 | Y |
| TORNTPOWER | NIFTY 500 | WEAK_HOLD | HOLD | 0.217 | 14.0 | 11.0 | Y |
| AUBANK | NIFTY 500 | WEAK_HOLD | HOLD | 0.200 | 9.0 | 10.0 | Y |
| SAIL | NIFTY 500 | HOLD | HOLD | 0.360 | 13.0 | 10.0 | Y |
| J&KBANK | NIFTY 500 | WEAK_HOLD | HOLD | 0.129 | 15.0 | 13.0 | Y |
| BHEL | NIFTY 500,NIFTY MIDCAP SELECT | HOLD | HOLD | 0.444 | 15.0 | 4.0 | Y |
| SHARDACROP | NIFTY MICROCAP 250 | HOLD | HOLD | 0.290 | 7.0 | 16.0 | Y |
| GRSE | NIFTY 500,NIFTY INDIA DEFENCE | HOLD | HOLD | 0.283 | 13.0 | 11.0 | Y |
| ENGINERSIN | NIFTY 500 | HOLD | HOLD | 0.277 | 16.0 | 9.0 | Y |
| MAHSEAMLES | NIFTY 500 | WEAK_HOLD | HOLD | 0.116 | 15.0 | 10.0 | Y |
| TIINDIA | NIFTY 500 | WEAK_HOLD | HOLD | 0.005 | 14.0 | 10.0 | Y |
| HBLENGINE | NIFTY 500 | WEAK_HOLD | HOLD | -0.008 | 11.0 | 16.0 | Y |
| VEDL | NIFTY 500 | WEAK_HOLD | HOLD | -0.031 | 13.0 | 10.0 | Y |
| STAR | NIFTY MICROCAP 250 | HOLD | HOLD | 0.411 | 13.0 | 13.0 | Y |
| HINDALCO | NIFTY 500 | HOLD | HOLD | 0.293 | 11.0 | 15.0 | Y |
| GLENMARK | NIFTY 500 | WEAK_HOLD | HOLD | 0.120 | 11.0 | 15.0 | Y |
| COALINDIA | NIFTY 500,NIFTY CPSE | WEAK_HOLD | HOLD | 0.093 | 1.0 | 13.0 | Y |
| LUMAXTECH | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.081 | 13.0 | 13.0 | Y |
| HFCL | NIFTY 500 | HOLD | HOLD | 1.055 | 16.0 | 11.0 | Y |
| BLUESTARCO | NIFTY 500 | WEAK_HOLD | HOLD | 0.167 | 4.0 | 9.0 | Y |
| AXISBANK | NIFTY 500 | WEAK_HOLD | HOLD | -0.002 | 8.0 | 10.0 | Y |
| NATCOPHARM | NIFTY 500 | HOLD | HOLD | 0.323 | 15.0 | 10.0 | Y |
| TATACONSUM | NIFTY 500 | HOLD | HOLD | 0.254 | 11.0 | 16.0 | Y |
| SHRIPISTON | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.137 | 13.0 | 11.0 | Y |
| NAM-INDIA | NIFTY 500 | WEAK_HOLD | HOLD | -0.008 | 14.0 | 8.0 | Y |
| VTL | NIFTY 500 | HOLD | HOLD | 0.788 | 11.0 | 12.0 | Y |
| HONASA | NIFTY 500 | HOLD | HOLD | 0.700 | 15.0 | 8.0 | Y |
| DMART | NIFTY 500 | HOLD | HOLD | 0.635 | 15.0 | 8.0 | Y |
| KTKBANK | NIFTY MICROCAP 250 | HOLD | HOLD | 0.448 | 13.0 | 10.0 | Y |
| HSCL | NIFTY 500 | HOLD | HOLD | 0.351 | 13.0 | 8.0 | Y |
| FINCABLES | NIFTY 500 | HOLD | HOLD | 0.318 | 15.0 | 6.0 | Y |
| SONACOMS | NIFTY 500 | WEAK_HOLD | HOLD | 0.187 | 13.0 | 10.0 | Y |
| GPIL | NIFTY 500 | WEAK_HOLD | HOLD | 0.091 | 13.0 | 10.0 | Y |
| WABAG | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.064 | 15.0 | 8.0 | Y |
| JINDALSTEL | NIFTY 500 | WEAK_HOLD | HOLD | 0.033 | 11.0 | 10.0 | Y |
| LUXIND | NIFTY MICROCAP 250 | HOLD | HOLD | 2.440 | 15.0 | 14.0 | Y |
| ZENTEC | NIFTY 500,NIFTY INDIA DEFENCE | HOLD | HOLD | 0.755 | 16.0 | 4.0 | Y |
| ELECON | NIFTY 500 | HOLD | HOLD | 0.463 | 18.0 | 4.0 | Y |
| PRIVISCL | NIFTY MICROCAP 250 | WEAK_HOLD | HOLD | 0.159 | 12.0 | 9.0 | Y |
| ABSLAMC | NIFTY 500 | WEAK_HOLD | HOLD | 0.134 | 13.0 | 10.0 | Y |
| GALLANTT | NIFTY MICROCAP 250 | HOLD | HOLD | 2.385 | 15.0 | 9.0 | Y |
| IMFA | NIFTY MICROCAP 250 | HOLD | HOLD | 0.303 | 13.0 | 8.0 | Y |
| JSWENERGY | NIFTY 500 | HOLD | HOLD | 0.291 | 13.0 | 6.0 | Y |
| SUNTV | NIFTY 500 | WEAK_HOLD | HOLD | 0.138 | 13.0 | 8.0 | Y |
| BEL | NIFTY 500,NIFTY CPSE,NIFTY INDIA DEFENCE | WEAK_HOLD | HOLD | 0.040 | 2.0 | 10.0 | Y |
| AADHARHFC | NIFTY 500 | WEAK_HOLD | HOLD | 0.024 | 6.0 | 12.0 | Y |
| GICRE | NIFTY 500 | WEAK_HOLD | HOLD | 0.010 | 9.0 | 15.0 | Y |
| JSWSTEEL | NIFTY 500 | WEAK_HOLD | HOLD | -0.041 | 9.0 | 10.0 | Y |
| TATASTEEL | NIFTY 500 | WEAK_HOLD | HOLD | -0.059 | 11.0 | 13.0 | Y |
| POWERINDIA | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.258 | 15.0 | 8.0 | Y |
| KIRLOSENG | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.775 | 15.0 | 8.0 | Y |
| ABDL | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 0.492 | 11.0 | 6.0 | Y |
| NLCINDIA | NIFTY 500,NIFTY CPSE | WEAK_HOLD | WEAK_HOLD | 0.483 | 13.0 | 7.0 | Y |
| PFC | NIFTY 500 | SELL | WEAK_HOLD | 0.185 | 13.0 | 10.0 | Y |
| YATHARTH | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.176 | 13.0 | 8.0 | Y |
| KEI | NIFTY 500 | SELL | WEAK_HOLD | 0.025 | 13.0 | 10.0 | Y |
| STLTECH | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 3.707 | 15.0 | 11.0 | Y |
| TDPOWERSYS | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.065 | 15.0 | 7.0 | Y |
| KSB | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.599 | 15.0 | 11.0 | Y |
| NAVA | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.972 | 15.0 | 6.0 | Y |
| THERMAX | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.793 | 15.0 | 6.0 | Y |
| SOLARINDS | NIFTY 500,NIFTY INDIA DEFENCE | WEAK_HOLD | WEAK_HOLD | 0.456 | 13.0 | 8.0 | Y |
| ADANIGREEN | NIFTY 500 | SELL | WEAK_HOLD | 0.230 | 15.0 | 14.0 | Y |
| EPL | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.108 | 11.0 | 8.0 | Y |
| FACT | NIFTY 500 | SELL | WEAK_HOLD | 0.041 | 13.0 | 9.0 | Y |
| WAAREEENER | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.404 | 11.0 | 6.0 | Y |
| PREMIERENE | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.291 | 15.0 | 6.0 | Y |
| STARHEALTH | NIFTY 500 | SELL | WEAK_HOLD | 0.158 | 11.0 | 8.0 | Y |
| CANFINHOME | NIFTY 500 | SELL | WEAK_HOLD | 0.059 | 6.0 | 8.0 | Y |
| KRN | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.006 | 15.0 | 4.0 | Y |
| NTPCGREEN | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.589 | 15.0 | 4.0 | Y |
| HEG | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.496 | 15.0 | 4.0 | Y |
| POWERGRID | NIFTY 500,NIFTY CPSE | WEAK_HOLD | WEAK_HOLD | 0.489 | 11.0 | 8.0 | Y |
| PNGJL | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 0.411 | 15.0 | 8.0 | Y |
| TATAPOWER | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.389 | 11.0 | 8.0 | Y |
| VIJAYA | NIFTY 500 | SELL | WEAK_HOLD | 0.217 | 9.0 | 10.0 | Y |
| OBEROIRLTY | NIFTY 500 | SELL | WEAK_HOLD | 0.045 | 13.0 | 10.0 | Y |
| ONGC | NIFTY 500,NIFTY CPSE | WEAK_HOLD | WEAK_HOLD | 0.371 | 7.0 | 12.0 | Y |
| KSL | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 0.251 | 11.0 | 4.0 | Y |
| TITAN | NIFTY 500 | SELL | WEAK_HOLD | 0.154 | 9.0 | 10.0 | Y |
| GMDCLTD | NIFTY 500 | SELL | WEAK_HOLD | 0.036 | 13.0 | 2.0 | Y |
| MTARTECH | NIFTY INDIA DEFENCE,NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 1.809 | 15.0 | 6.0 | Y |
| GESHIP | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.572 | 9.0 | 8.0 | Y |
| SYRMA | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.449 | 13.0 | 4.0 | Y |
| LUPIN | NIFTY 500,NIFTY MIDCAP SELECT | SELL | WEAK_HOLD | 0.154 | 5.0 | 10.0 | Y |
| KIRLOSBROS | NIFTY 500 | SELL | WEAK_HOLD | -0.002 | 13.0 | 8.0 | Y |
| RADICO | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.329 | 13.0 | 4.0 | Y |
| GRAPHITE | NIFTY 500 | SELL | WEAK_HOLD | 0.152 | 13.0 | 6.0 | Y |
| SKIPPER | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.035 | 14.0 | 4.0 | Y |
| SCI | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.347 | 15.0 | 2.0 | Y |
| NIACL | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 2.405 | 11.0 | 6.0 | Y |
| FEDERALBNK | NIFTY 500 | SELL | WEAK_HOLD | 0.033 | 8.0 | 10.0 | Y |
| VSTIND | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 0.546 | 13.0 | 6.0 | Y |
| RRKABEL | NIFTY 500 | SELL | WEAK_HOLD | 0.023 | 3.0 | 13.0 | Y |
| TRITURBINE | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 1.647 | 13.0 | 4.0 | Y |
| HAL | NIFTY 500,NIFTY INDIA DEFENCE | SELL | WEAK_HOLD | -0.016 | 8.0 | 11.0 | Y |
| DIVISLAB | NIFTY 500 | SELL | WEAK_HOLD | -0.057 | 6.0 | 8.0 | Y |
| VOLTAS | NIFTY 500 | WEAK_HOLD | WEAK_HOLD | 0.450 | 6.0 | 8.0 | Y |
| PRSMJOHNSN | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.196 | 7.0 | 6.0 | Y |
| ADANIPORTS | NIFTY 500 | SELL | WEAK_HOLD | 0.072 | 6.0 | 10.0 | Y |
| SUNTECK | NIFTY MICROCAP 250 | WEAK_HOLD | WEAK_HOLD | 0.525 | 10.0 | 14.0 | Y |
| GNFC | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.234 | 8.0 | 8.0 | Y |
| PTC | NIFTY MICROCAP 250 | SELL | WEAK_HOLD | 0.047 | 6.0 | 6.0 | Y |
| MIDHANI | NIFTY INDIA DEFENCE,NIFTY MICROCAP 250 | SELL | WEAK_HOLD | -0.011 | 9.0 | 6.0 | Y |
| WELSPUNLIV | NIFTY 500 | SELL | WEAK_HOLD | 0.001 | 6.0 | 10.0 | Y |
| GSPL | NIFTY 500 | SELL | SELL | 0.014 | 3.0 | 4.0 | Y |
| RELINFRA | NIFTY 500 | REVIEW_NO_TECH | nan | 0.981 | nan | nan | Y |
| TVSSCS | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.736 | nan | nan | Y |
| KIRLPNU | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.575 | nan | nan | Y |
| BBL | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.478 | nan | nan | Y |
| SCHNEIDER | NIFTY 500 | REVIEW_NO_TECH | nan | 0.450 | nan | nan | Y |
| LLOYDSENT | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.439 | nan | nan | Y |
| INGERRAND | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.423 | nan | nan | Y |
| MAHABANK | NIFTY 500 | REVIEW_NO_TECH | nan | 0.356 | nan | nan | Y |
| BOSCHLTD | NIFTY 500 | REVIEW_NO_TECH | nan | 0.275 | nan | nan | Y |
| KPIL | NIFTY 500 | REVIEW_NO_TECH | nan | 0.273 | nan | nan | Y |
| LINDEINDIA | NIFTY 500 | REVIEW_NO_TECH | nan | 0.253 | nan | nan | Y |
| JPPOWER | NIFTY 500 | REVIEW_NO_TECH | nan | 0.248 | nan | nan | Y |
| AIAENG | NIFTY 500 | REVIEW_NO_TECH | nan | 0.247 | nan | nan | Y |
| ENTERO | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.233 | nan | nan | Y |
| NMDC | NIFTY 500 | REVIEW_NO_TECH | nan | 0.162 | nan | nan | Y |
| SUZLON | NIFTY 500,NIFTY MIDCAP SELECT | REVIEW_NO_TECH | nan | 0.161 | nan | nan | Y |
| LLOYDSENGG | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.150 | nan | nan | Y |
| EMCURE | NIFTY 500 | REVIEW_NO_TECH | nan | 0.149 | nan | nan | Y |
| RATNAMANI | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.147 | nan | nan | Y |
| AHLUCONT | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.146 | nan | nan | Y |
| FINEORG | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.132 | nan | nan | Y |
| RENUKA | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.105 | nan | nan | Y |
| GRWRHITECH | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.090 | nan | nan | Y |
| ZFCVINDIA | NIFTY 500 | REVIEW_NO_TECH | nan | 0.078 | nan | nan | Y |
| ATUL | NIFTY 500 | REVIEW_NO_TECH | nan | 0.029 | nan | nan | Y |
| PRUDENT | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.028 | nan | nan | Y |
| IFCI | NIFTY 500 | REVIEW_NO_TECH | nan | 0.026 | nan | nan | Y |
| HONAUT | NIFTY 500 | REVIEW_NO_TECH | nan | 0.015 | nan | nan | Y |
| CARBORUNIV | NIFTY 500 | REVIEW_NO_TECH | nan | 0.010 | nan | nan | Y |
| MEDPLUS | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | 0.004 | nan | nan | Y |
| CENTURYPLY | NIFTY 500 | REVIEW_NO_TECH | nan | 0.004 | nan | nan | Y |
| NSLNISP | NIFTY 500 | REVIEW_NO_TECH | nan | -0.023 | nan | nan | Y |
| NHPC | NIFTY 500,NIFTY CPSE | REVIEW_NO_TECH | nan | -0.028 | nan | nan | Y |
| POWERMECH | NIFTY MICROCAP 250 | REVIEW_NO_TECH | nan | -0.028 | nan | nan | Y |

## Screener summaries (verbatim columns)

### ABB
- **pnl_summary:** Sales: 13203 Cr (YoY +8.3%); NetProfit: 1668 Cr (YoY -10.9%); EPS: 78.73
- **quarterly_summary:** Sales last 3Q: 3175, 3311, 3557 Cr; Net Profit last 3Q: 352, 409, 433 Cr
- **balance_sheet_summary:** Debt: 85 Cr
- **ratios_summary:** ROCE: 30%; EPS: 78.73; NPM: 12.63%

### BALRAMCHIN
- **pnl_summary:** Sales: 6171 Cr (YoY +14%); NetProfit: 448 Cr (YoY +2.5%); EPS: 22.19
- **quarterly_summary:** Sales last 3Q: 1542, 1671, 1454 Cr; Net Profit last 3Q: 52, 54, 113 Cr
- **balance_sheet_summary:** Debt: 774 Cr
- **ratios_summary:** ROCE: 10%; EPS: 22.19; NPM: 7.26%

### AZAD
- **pnl_summary:** Sales: 568 Cr (YoY +24.3%); NetProfit: 122 Cr (YoY +40.2%); EPS: 18.92
- **quarterly_summary:** Sales last 3Q: 137, 146, 159 Cr; Net Profit last 3Q: 29, 33, 35 Cr
- **balance_sheet_summary:** Debt: 312 Cr
- **ratios_summary:** ROCE: 12%; EPS: 18.92; NPM: 21.48%

### CHENNPETRO
- **pnl_summary:** Sales: 64072 Cr (YoY +8.6%); NetProfit: 2151 Cr (YoY +905.1%); EPS: 144.43
- **quarterly_summary:** Sales last 3Q: 14812, 16327, 15683 Cr; Net Profit last 3Q: -40, 719, 1002 Cr
- **balance_sheet_summary:** Debt: 1933 Cr
- **ratios_summary:** ROCE: 4%; EPS: 144.43; NPM: 3.36%

### CEIGALL
- **pnl_summary:** Sales: 3648 Cr (YoY +6.1%); NetProfit: 252 Cr (YoY -12.2%); EPS: 14.88
- **quarterly_summary:** Sales last 3Q: 838, 807, 991 Cr; Net Profit last 3Q: 51, 56, 72 Cr
- **balance_sheet_summary:** Debt: 1343 Cr
- **ratios_summary:** ROCE: 22%; EPS: 14.88; NPM: 6.91%

### ASTERDM
- **pnl_summary:** Sales: 4461 Cr (YoY +7.8%); NetProfit: 359 Cr (YoY -93.4%); EPS: 6.36
- **quarterly_summary:** Sales last 3Q: 1078, 1197, 1186 Cr; Net Profit last 3Q: 94, 121, 59 Cr
- **balance_sheet_summary:** Debt: 2089 Cr
- **ratios_summary:** ROCE: 139%; EPS: 6.36; NPM: 8.05%

### DATAPATTNS
- **pnl_summary:** Sales: 976 Cr (YoY +37.9%); NetProfit: 247 Cr (YoY +11.3%); EPS: 44.13
- **quarterly_summary:** Sales last 3Q: 99, 307, 173 Cr; Net Profit last 3Q: 26, 49, 58 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** nan

### AUROPHARMA
- **pnl_summary:** Sales: 33182 Cr (YoY +4.6%); NetProfit: 3485 Cr (YoY +0%); EPS: 60.04
- **quarterly_summary:** Sales last 3Q: 7868, 8286, 8646 Cr; Net Profit last 3Q: 824, 848, 910 Cr
- **balance_sheet_summary:** Debt: 7794 Cr
- **ratios_summary:** ROCE: 11%; EPS: 60.04; NPM: 10.5%

### SANSERA
- **pnl_summary:** Sales: 3281 Cr (YoY +8.8%); NetProfit: 263 Cr (YoY +21.2%); EPS: 42.21
- **quarterly_summary:** Sales last 3Q: 766, 825, 908 Cr; Net Profit last 3Q: 63, 71, 69 Cr
- **balance_sheet_summary:** Debt: 439 Cr
- **ratios_summary:** ROCE: 13%; EPS: 42.21; NPM: 8.02%

### TIMKEN
- **pnl_summary:** —
- **quarterly_summary:** Sales last 3Q: 683, 786, 780 Cr; Net Profit last 3Q: 78, 94, 55 Cr
- **balance_sheet_summary:** —
- **ratios_summary:** ROCE: 21%; EPS: 61.45; NPM: 14.46%

### CGPOWER
- **pnl_summary:** Sales: 11729 Cr (YoY +18.4%); NetProfit: 1109 Cr (YoY +14%); EPS: 7.17
- **quarterly_summary:** Sales last 3Q: 2878, 2923, 3175 Cr; Net Profit last 3Q: 267, 284, 284 Cr
- **balance_sheet_summary:** Debt: 117 Cr
- **ratios_summary:** ROCE: 36%; EPS: 7.17; NPM: 9.46%

### ASTRAMICRO
- **pnl_summary:** Sales: 1082 Cr (YoY +2.9%); NetProfit: 160 Cr (YoY +3.9%); EPS: 16.9
- **quarterly_summary:** Sales last 3Q: 200, 215, 260 Cr; Net Profit last 3Q: 16, 24, 47 Cr
- **balance_sheet_summary:** Debt: 278 Cr
- **ratios_summary:** ROCE: 18%; EPS: 16.9; NPM: 14.79%

### DYNAMATECH
- **pnl_summary:** Sales: 1569 Cr (YoY +11.8%); NetProfit: 36 Cr (YoY -16.3%); EPS: 56.67
- **quarterly_summary:** Sales last 3Q: 371, 392, 425 Cr; Net Profit last 3Q: 11, 3, 6 Cr
- **balance_sheet_summary:** Debt: 594 Cr
- **ratios_summary:** ROCE: 10%; EPS: 56.67; NPM: 2.29%

### ELGIEQUIP
- **pnl_summary:** Sales: 3831 Cr (YoY +9.1%); NetProfit: 404 Cr (YoY +15.4%); EPS: 12.75
- **quarterly_summary:** Sales last 3Q: 867, 968, 1003 Cr; Net Profit last 3Q: 86, 121, 95 Cr
- **balance_sheet_summary:** Debt: 528 Cr
- **ratios_summary:** ROCE: 28%; EPS: 12.75; NPM: 10.55%

### BANDHANBNK
- **pnl_summary:** Revenue: 21695 Cr (YoY -1.2%); NetProfit: 1007 Cr (YoY -63.3%); EPS: 6.25
- **quarterly_summary:** Sales last 3Q: 5476, 5354, 5431 Cr; Net Profit last 3Q: 372, 112, 206 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 12%; EPS: 6.25; NPM: 4.64%

### CIEINDIA
- **pnl_summary:** Sales: 9746 Cr (YoY +3.6%); NetProfit: 871 Cr (YoY +5.2%); EPS: 22.97
- **quarterly_summary:** Sales last 3Q: 2372, 2393, 2612 Cr; Net Profit last 3Q: 214, 204, 249 Cr
- **balance_sheet_summary:** Debt: 426 Cr
- **ratios_summary:** ROCE: 15%; EPS: 22.97; NPM: 8.94%

### JKPAPER
- **pnl_summary:** Sales: 6875 Cr (YoY +2.3%); NetProfit: 268 Cr (YoY -35%); EPS: 15.33
- **quarterly_summary:** Sales last 3Q: 1674, 1749, 1763 Cr; Net Profit last 3Q: 85, 78, 28 Cr
- **balance_sheet_summary:** Debt: 2118 Cr
- **ratios_summary:** ROCE: 9%; EPS: 15.33; NPM: 3.9%

### APOLLOHOSP
- **pnl_summary:** Sales: 24215 Cr (YoY +11.1%); NetProfit: 1866 Cr (YoY +24%); EPS: 125.32
- **quarterly_summary:** Sales last 3Q: 5842, 6304, 6477 Cr; Net Profit last 3Q: 441, 494, 516 Cr
- **balance_sheet_summary:** Debt: 7987 Cr
- **ratios_summary:** ROCE: 16%; EPS: 125.32; NPM: 7.71%

### TRIVENI
- **pnl_summary:** Sales: 6412 Cr (YoY +12.7%); NetProfit: 288 Cr (YoY +21%); EPS: 13.58
- **quarterly_summary:** Sales last 3Q: 1598, 1706, 1478 Cr; Net Profit last 3Q: 2, 21, 78 Cr
- **balance_sheet_summary:** Debt: 768 Cr
- **ratios_summary:** ROCE: 9%; EPS: 13.58; NPM: 4.49%

### NEOGEN
- **pnl_summary:** Sales: 818 Cr (YoY +5.1%); NetProfit: 20 Cr (YoY -42.9%); EPS: 7.48
- **quarterly_summary:** Sales last 3Q: 187, 209, 220 Cr; Net Profit last 3Q: 10, 3, 4 Cr
- **balance_sheet_summary:** Debt: 1132 Cr
- **ratios_summary:** ROCE: 11%; EPS: 7.48; NPM: 2.44%

### AVANTIFEED
- **pnl_summary:** Sales: 5981 Cr (YoY +6.6%); NetProfit: 675 Cr (YoY +21.2%); EPS: 46.44
- **quarterly_summary:** Sales last 3Q: 1606, 1609, 1384 Cr; Net Profit last 3Q: 186, 169, 163 Cr
- **balance_sheet_summary:** Debt: 15 Cr
- **ratios_summary:** ROCE: 29%; EPS: 46.44; NPM: 11.29%

### NETWEB
- **pnl_summary:** Sales: 1825 Cr (YoY +58.8%); NetProfit: 178 Cr (YoY +56.1%); EPS: 31.39
- **quarterly_summary:** Sales last 3Q: 301, 304, 805 Cr; Net Profit last 3Q: 30, 31, 73 Cr
- **balance_sheet_summary:** Debt: 18 Cr
- **ratios_summary:** ROCE: 32%; EPS: 31.39; NPM: 9.75%

### VOLTAMP
- **pnl_summary:** Sales: 2161 Cr (YoY +11.7%); NetProfit: 354 Cr (YoY +8.9%); EPS: 350.21
- **quarterly_summary:** Sales last 3Q: 424, 483, 630 Cr; Net Profit last 3Q: 80, 79, 99 Cr
- **balance_sheet_summary:** Debt: 1 Cr
- **ratios_summary:** ROCE: 29%; EPS: 350.21; NPM: 16.38%

### WELCORP
- **pnl_summary:** Sales: 16383 Cr (YoY +17.2%); NetProfit: 1948 Cr (YoY +2.4%); EPS: 73.77
- **quarterly_summary:** Sales last 3Q: 3551, 4374, 4532 Cr; Net Profit last 3Q: 349, 444, 456 Cr
- **balance_sheet_summary:** Debt: 1545 Cr
- **ratios_summary:** ROCE: 18%; EPS: 73.77; NPM: 11.89%

### ADANIENSOL
- **pnl_summary:** Sales: 27588 Cr (YoY +16.1%); NetProfit: 2393 Cr (YoY +159.5%); EPS: 19
- **quarterly_summary:** Sales last 3Q: 6596, 6730, 7443 Cr; Net Profit last 3Q: 557, 574, 723 Cr
- **balance_sheet_summary:** Debt: 49176 Cr
- **ratios_summary:** ROCE: 5%; EPS: 19; NPM: 8.67%

### CCL
- **pnl_summary:** Sales: 4069 Cr (YoY +31%); NetProfit: 375 Cr (YoY +21%); EPS: 28.12
- **quarterly_summary:** Sales last 3Q: 1056, 1127, 1051 Cr; Net Profit last 3Q: 72, 101, 100 Cr
- **balance_sheet_summary:** Debt: 1628 Cr
- **ratios_summary:** ROCE: 10%; EPS: 28.12; NPM: 9.22%

### SUNFLAG
- **pnl_summary:** Sales: 3822 Cr (YoY +8.1%); NetProfit: 211 Cr (YoY +30.2%); EPS: 11.73
- **quarterly_summary:** Sales last 3Q: 1023, 973, 942 Cr; Net Profit last 3Q: 63, 46, 60 Cr
- **balance_sheet_summary:** Debt: 580 Cr
- **ratios_summary:** ROCE: 4%; EPS: 11.73; NPM: 5.52%

### NTPC
- **pnl_summary:** Sales: 187531 Cr (YoY -0.3%); NetProfit: 24828 Cr (YoY +3.7%); EPS: 24.94
- **quarterly_summary:** Sales last 3Q: 47065, 44786, 45846 Cr; Net Profit last 3Q: 6108, 5225, 5597 Cr
- **balance_sheet_summary:** Debt: 254876 Cr
- **ratios_summary:** ROCE: 12%; EPS: 24.94; NPM: 13.24%

### CUMMINSIND
- **pnl_summary:** Sales: 11602 Cr (YoY +11.7%); NetProfit: 2242 Cr (YoY +12.1%); EPS: 80.87
- **quarterly_summary:** Sales last 3Q: 2907, 3170, 3055 Cr; Net Profit last 3Q: 604, 622, 486 Cr
- **balance_sheet_summary:** Debt: 24 Cr
- **ratios_summary:** ROCE: 38%; EPS: 80.87; NPM: 19.32%

### DEEPAKNTR
- **pnl_summary:** Sales: 7946 Cr (YoY -4.1%); NetProfit: 533 Cr (YoY -23.5%); EPS: 39.09
- **quarterly_summary:** Sales last 3Q: 1890, 1902, 1975 Cr; Net Profit last 3Q: 112, 119, 100 Cr
- **balance_sheet_summary:** Debt: 1244 Cr
- **ratios_summary:** ROCE: 10%; EPS: 39.09; NPM: 6.71%

### NATIONALUM
- **pnl_summary:** Sales: 18098 Cr (YoY +7.8%); NetProfit: 6142 Cr (YoY +16.6%); EPS: 33.45
- **quarterly_summary:** Sales last 3Q: 3807, 4292, 4731 Cr; Net Profit last 3Q: 1049, 1430, 1595 Cr
- **balance_sheet_summary:** Debt: 56 Cr
- **ratios_summary:** ROCE: 44%; EPS: 33.45; NPM: 33.94%

### EDELWEISS
- **pnl_summary:** Sales: 10796 Cr (YoY +14.7%); NetProfit: 707 Cr (YoY +31.9%); EPS: 5.97
- **quarterly_summary:** Sales last 3Q: 2246, 1861, 4404 Cr; Net Profit last 3Q: 103, 175, 270 Cr
- **balance_sheet_summary:** Debt: 19459 Cr
- **ratios_summary:** ROCE: 3%; EPS: 5.97; NPM: 6.55%

### APARINDS
- **pnl_summary:** Sales: 21509 Cr (YoY +15.8%); NetProfit: 974 Cr (YoY +18.6%); EPS: 242.35
- **quarterly_summary:** Sales last 3Q: 5104, 5715, 5480 Cr; Net Profit last 3Q: 263, 252, 209 Cr
- **balance_sheet_summary:** Debt: 704 Cr
- **ratios_summary:** ROCE: 33%; EPS: 242.35; NPM: 4.53%

### BHARATFORG
- **pnl_summary:** Sales: 16136 Cr (YoY +6.7%); NetProfit: 1139 Cr (YoY +24.8%); EPS: 23.62
- **quarterly_summary:** Sales last 3Q: 3909, 4032, 4343 Cr; Net Profit last 3Q: 284, 299, 273 Cr
- **balance_sheet_summary:** Debt: 6658 Cr
- **ratios_summary:** ROCE: 15%; EPS: 23.62; NPM: 7.06%

### ATGL
- **pnl_summary:** Sales: 5678 Cr (YoY +13.6%); NetProfit: 642 Cr (YoY -1.8%); EPS: 5.84
- **quarterly_summary:** Sales last 3Q: 1379, 1451, 1507 Cr; Net Profit last 3Q: 165, 163, 159 Cr
- **balance_sheet_summary:** Debt: 2007 Cr
- **ratios_summary:** ROCE: 17%; EPS: 5.84; NPM: 11.31%

### DELHIVERY
- **pnl_summary:** Sales: 9850 Cr (YoY +10.3%); NetProfit: 153 Cr (YoY -5.6%); EPS: 2.05
- **quarterly_summary:** Sales last 3Q: 2294, 2559, 2805 Cr; Net Profit last 3Q: 91, -50, 40 Cr
- **balance_sheet_summary:** Debt: 1642 Cr
- **ratios_summary:** ROCE: 3%; EPS: 2.05; NPM: 1.55%

### SAILIFE
- **pnl_summary:** Sales: 2170 Cr (YoY +28%); NetProfit: 333 Cr (YoY +95.9%); EPS: 15.89
- **quarterly_summary:** Sales last 3Q: 496, 537, 556 Cr; Net Profit last 3Q: 60, 84, 100 Cr
- **balance_sheet_summary:** Debt: 418 Cr
- **ratios_summary:** ROCE: 14%; EPS: 15.89; NPM: 15.35%

### GRANULES
- **pnl_summary:** Sales: 5092 Cr (YoY +13.6%); NetProfit: 545 Cr (YoY +8.6%); EPS: 22.48
- **quarterly_summary:** Sales last 3Q: 1210, 1297, 1388 Cr; Net Profit last 3Q: 113, 131, 150 Cr
- **balance_sheet_summary:** Debt: 1807 Cr
- **ratios_summary:** ROCE: 11%; EPS: 22.48; NPM: 10.7%

### ARE&M
- **pnl_summary:** Sales: 13338 Cr (YoY +3.8%); NetProfit: 743 Cr (YoY -21.4%); EPS: 40.6
- **quarterly_summary:** Sales last 3Q: 3401, 3467, 3410 Cr; Net Profit last 3Q: 165, 276, 140 Cr
- **balance_sheet_summary:** Debt: 310 Cr
- **ratios_summary:** ROCE: 17%; EPS: 40.6; NPM: 5.57%

### ANANDRATHI
- **pnl_summary:** Sales: 1149 Cr (YoY +17.2%); NetProfit: 397 Cr (YoY +31.9%); EPS: 47.69
- **quarterly_summary:** Sales last 3Q: 297, 290, 288 Cr; Net Profit last 3Q: 100, 100, 103 Cr
- **balance_sheet_summary:** Debt: 83 Cr
- **ratios_summary:** ROCE: 57%; EPS: 47.69; NPM: 34.55%

### KAJARIACER
- **pnl_summary:** Sales: 4679 Cr (YoY +0.9%); NetProfit: 374 Cr (YoY +24.7%); EPS: 23.37
- **quarterly_summary:** Sales last 3Q: 1103, 1186, 1168 Cr; Net Profit last 3Q: 110, 134, 86 Cr
- **balance_sheet_summary:** Debt: 290 Cr
- **ratios_summary:** ROCE: 17%; EPS: 23.37; NPM: 7.99%

### AMBER
- **pnl_summary:** Sales: 11793 Cr (YoY +18.2%); NetProfit: 183 Cr (YoY -27.1%); EPS: 47.89
- **quarterly_summary:** Sales last 3Q: 3449, 1647, 2943 Cr; Net Profit last 3Q: 106, -32, -9 Cr
- **balance_sheet_summary:** Debt: 2793 Cr
- **ratios_summary:** ROCE: 12%; EPS: 47.89; NPM: 1.55%

### GAEL
- **pnl_summary:** Sales: 5529 Cr (YoY +19.9%); NetProfit: 201 Cr (YoY -19.3%); EPS: 4.39
- **quarterly_summary:** Sales last 3Q: 1291, 1487, 1484 Cr; Net Profit last 3Q: 65, 38, 66 Cr
- **balance_sheet_summary:** Debt: 288 Cr
- **ratios_summary:** ROCE: 12%; EPS: 4.39; NPM: 3.64%

### INOXINDIA
- **pnl_summary:** Sales: 1496 Cr (YoY +14.5%); NetProfit: 248 Cr (YoY +9.7%); EPS: 27.34
- **quarterly_summary:** Sales last 3Q: 340, 358, 429 Cr; Net Profit last 3Q: 61, 61, 61 Cr
- **balance_sheet_summary:** Debt: 99 Cr
- **ratios_summary:** ROCE: 37%; EPS: 27.34; NPM: 16.58%

### AETHER
- **pnl_summary:** Sales: 1094 Cr (YoY +30.4%); NetProfit: 216 Cr (YoY +36.7%); EPS: 16.27
- **quarterly_summary:** Sales last 3Q: 256, 280, 317 Cr; Net Profit last 3Q: 47, 54, 64 Cr
- **balance_sheet_summary:** Debt: 215 Cr
- **ratios_summary:** ROCE: 10%; EPS: 16.27; NPM: 19.74%

### SCHAEFFLER
- **pnl_summary:** Sales: 9686 Cr (YoY +17.7%); NetProfit: 1150 Cr (YoY +22.5%); EPS: 73.6
- **quarterly_summary:** Sales last 3Q: 2353, 2435, 2724 Cr; Net Profit last 3Q: 287, 289, 322 Cr
- **balance_sheet_summary:** Debt: 55 Cr
- **ratios_summary:** ROCE: 28%; EPS: 73.6; NPM: 11.87%

### WELENT
- **pnl_summary:** Sales: 3470 Cr (YoY -3.2%); NetProfit: 335 Cr (YoY -5.4%); EPS: 21.66
- **quarterly_summary:** Sales last 3Q: 845, 784, 787 Cr; Net Profit last 3Q: 101, 98, 31 Cr
- **balance_sheet_summary:** Debt: 1941 Cr
- **ratios_summary:** ROCE: 16%; EPS: 21.66; NPM: 9.65%

### LAURUSLABS
- **pnl_summary:** Sales: 6722 Cr (YoY +21%); NetProfit: 841 Cr (YoY +134.9%); EPS: 15.62
- **quarterly_summary:** Sales last 3Q: 1570, 1653, 1778 Cr; Net Profit last 3Q: 162, 194, 252 Cr
- **balance_sheet_summary:** Debt: 2212 Cr
- **ratios_summary:** ROCE: 9%; EPS: 15.62; NPM: 12.51%

### ISGEC
- **pnl_summary:** Sales: 6515 Cr (YoY +1.4%); NetProfit: 297 Cr (YoY +12.5%); EPS: 34.98
- **quarterly_summary:** Sales last 3Q: 1341, 1691, 1739 Cr; Net Profit last 3Q: 59, 56, 84 Cr
- **balance_sheet_summary:** Debt: 925 Cr
- **ratios_summary:** ROCE: 17%; EPS: 34.98; NPM: 4.56%

### ANURAS
- **pnl_summary:** Sales: 2230 Cr (YoY +55.2%); NetProfit: 229 Cr (YoY +43.1%); EPS: 15.36
- **quarterly_summary:** Sales last 3Q: 486, 731, 512 Cr; Net Profit last 3Q: 48, 57, 61 Cr
- **balance_sheet_summary:** Debt: 1223 Cr
- **ratios_summary:** ROCE: 5%; EPS: 15.36; NPM: 10.27%

### ETHOSLTD
- **pnl_summary:** Sales: 1510 Cr (YoY +20.6%); NetProfit: 96 Cr (YoY +0%); EPS: 35.86
- **quarterly_summary:** Sales last 3Q: 346, 383, 469 Cr; Net Profit last 3Q: 19, 24, 31 Cr
- **balance_sheet_summary:** Debt: 314 Cr
- **ratios_summary:** ROCE: 14%; EPS: 35.86; NPM: 6.36%

### IREDA
- **pnl_summary:** Revenue: 8039 Cr (YoY +19%); NetProfit: 1883 Cr (YoY +10.9%); EPS: 6.79
- **quarterly_summary:** Sales last 3Q: 1948, 2057, 2130 Cr; Net Profit last 3Q: 247, 549, 585 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 18%; EPS: 6.79; NPM: 23.42%

### SARDAEN
- **pnl_summary:** Sales: 5676 Cr (YoY +22.2%); NetProfit: 1055 Cr (YoY +50.3%); EPS: 29.97
- **quarterly_summary:** Sales last 3Q: 1633, 1528, 1276 Cr; Net Profit last 3Q: 437, 328, 190 Cr
- **balance_sheet_summary:** Debt: 2681 Cr
- **ratios_summary:** ROCE: 17%; EPS: 29.97; NPM: 18.59%

### EXIDEIND
- **pnl_summary:** Sales: 17596 Cr (YoY +2.1%); NetProfit: 831 Cr (YoY +3.9%); EPS: 9.71
- **quarterly_summary:** Sales last 3Q: 4695, 4365, 4201 Cr; Net Profit last 3Q: 275, 174, 195 Cr
- **balance_sheet_summary:** Debt: 1645 Cr
- **ratios_summary:** ROCE: 10%; EPS: 9.71; NPM: 4.72%

### AARTIIND
- **pnl_summary:** Sales: 8042 Cr (YoY +10.6%); NetProfit: 378 Cr (YoY +14.2%); EPS: 10.43
- **quarterly_summary:** Sales last 3Q: 1675, 2100, 2318 Cr; Net Profit last 3Q: 43, 106, 133 Cr
- **balance_sheet_summary:** Debt: 3973 Cr
- **ratios_summary:** ROCE: 6%; EPS: 10.43; NPM: 4.7%

### JINDALSAW
- **pnl_summary:** Sales: 18308 Cr (YoY -12.1%); NetProfit: 889 Cr (YoY -39%); EPS: 17.59
- **quarterly_summary:** Sales last 3Q: 4085, 4234, 4943 Cr; Net Profit last 3Q: 415, 139, 248 Cr
- **balance_sheet_summary:** Debt: 5194 Cr
- **ratios_summary:** ROCE: 21%; EPS: 17.59; NPM: 4.86%

### FORTIS
- **pnl_summary:** Sales: 8770 Cr (YoY +12.7%); NetProfit: 981 Cr (YoY +21.3%); EPS: 12.72
- **quarterly_summary:** Sales last 3Q: 2167, 2331, 2265 Cr; Net Profit last 3Q: 267, 329, 197 Cr
- **balance_sheet_summary:** Debt: 3195 Cr
- **ratios_summary:** ROCE: 3%; EPS: 12.72; NPM: 11.19%

### ACMESOLAR
- **pnl_summary:** Sales: 1962 Cr (YoY +39.6%); NetProfit: 482 Cr (YoY +92%); EPS: 7.98
- **quarterly_summary:** Sales last 3Q: 511, 468, 497 Cr; Net Profit last 3Q: 131, 115, 114 Cr
- **balance_sheet_summary:** Debt: 12998 Cr
- **ratios_summary:** ROCE: 8%; EPS: 7.98; NPM: 24.57%

### ARVIND
- **pnl_summary:** Sales: 8971 Cr (YoY +7.7%); NetProfit: 417 Cr (YoY +13.6%); EPS: 15.46
- **quarterly_summary:** Sales last 3Q: 2006, 2371, 2373 Cr; Net Profit last 3Q: 55, 107, 101 Cr
- **balance_sheet_summary:** Debt: 1537 Cr
- **ratios_summary:** ROCE: 13%; EPS: 15.46; NPM: 4.65%

### LLOYDSME
- **pnl_summary:** Sales: 12286 Cr (YoY +82.8%); NetProfit: 2500 Cr (YoY +72.4%); EPS: 46.23
- **quarterly_summary:** Sales last 3Q: 2384, 3651, 5058 Cr; Net Profit last 3Q: 642, 567, 1090 Cr
- **balance_sheet_summary:** Debt: 8163 Cr
- **ratios_summary:** ROCE: 38%; EPS: 46.23; NPM: 20.35%

### CESC
- **pnl_summary:** Sales: 18351 Cr (YoY +7.9%); NetProfit: 1541 Cr (YoY +7.9%); EPS: 11.11
- **quarterly_summary:** Sales last 3Q: 5202, 5267, 4005 Cr; Net Profit last 3Q: 404, 448, 304 Cr
- **balance_sheet_summary:** Debt: 18811 Cr
- **ratios_summary:** ROCE: 10%; EPS: 11.11; NPM: 8.4%

### TORNTPOWER
- **pnl_summary:** Sales: 29017 Cr (YoY -0.5%); NetProfit: 3215 Cr (YoY +5.1%); EPS: 62.67
- **quarterly_summary:** Sales last 3Q: 7906, 7876, 6778 Cr; Net Profit last 3Q: 742, 742, 655 Cr
- **balance_sheet_summary:** Debt: 10431 Cr
- **ratios_summary:** ROCE: 17%; EPS: 62.67; NPM: 11.08%

### AUBANK
- **pnl_summary:** Revenue: 1429 Cr (YoY +18.5%); NetProfit: 762 Cr (YoY +208.5%); EPS: 13.4
- **quarterly_summary:** Sales last 3Q: 4378, 4511, 4727 Cr; Net Profit last 3Q: 581, 561, 668 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 14%; EPS: 13.4; NPM: 53.32%

### SAIL
- **pnl_summary:** Sales: 109313 Cr (YoY +6.7%); NetProfit: 2788 Cr (YoY +17.5%); EPS: 6.75
- **quarterly_summary:** Sales last 3Q: 25922, 26704, 27371 Cr; Net Profit last 3Q: 745, 419, 374 Cr
- **balance_sheet_summary:** Debt: 33663 Cr
- **ratios_summary:** ROCE: 7%; EPS: 6.75; NPM: 2.55%

### J&KBANK
- **pnl_summary:** Revenue: 13091 Cr (YoY +4.4%); NetProfit: 2143 Cr (YoY +2.9%); EPS: 19.45
- **quarterly_summary:** Sales last 3Q: 3269, 3293, 3315 Cr; Net Profit last 3Q: 485, 495, 581 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 16%; EPS: 19.45; NPM: 16.37%

### BHEL
- **pnl_summary:** Sales: 30465 Cr (YoY +7.5%); NetProfit: 814 Cr (YoY +52.4%); EPS: 2.34
- **quarterly_summary:** Sales last 3Q: 5487, 7512, 8473 Cr; Net Profit last 3Q: -456, 375, 390 Cr
- **balance_sheet_summary:** Debt: 10969 Cr
- **ratios_summary:** ROCE: 5%; EPS: 2.34; NPM: 2.67%

### SHARDACROP
- **pnl_summary:** Sales: 5031 Cr (YoY +16.5%); NetProfit: 566 Cr (YoY +86.2%); EPS: 62.72
- **quarterly_summary:** Sales last 3Q: 985, 929, 1289 Cr; Net Profit last 3Q: 143, 74, 145 Cr
- **balance_sheet_summary:** Debt: 4 Cr
- **ratios_summary:** ROCE: 16%; EPS: 62.72; NPM: 11.25%

### GRSE
- **pnl_summary:** Sales: 6525 Cr (YoY +28.5%); NetProfit: 689 Cr (YoY +30.7%); EPS: 60.15
- **quarterly_summary:** Sales last 3Q: 1310, 1677, 1896 Cr; Net Profit last 3Q: 120, 154, 171 Cr
- **balance_sheet_summary:** Debt: 32 Cr
- **ratios_summary:** ROCE: 37%; EPS: 60.15; NPM: 10.56%

### ENGINERSIN
- **pnl_summary:** Sales: 4012 Cr (YoY +29.9%); NetProfit: 776 Cr (YoY +33.8%); EPS: 13.81
- **quarterly_summary:** Sales last 3Q: 870, 921, 1210 Cr; Net Profit last 3Q: 65, 83, 347 Cr
- **balance_sheet_summary:** Debt: 20 Cr
- **ratios_summary:** ROCE: 24%; EPS: 13.81; NPM: 19.34%

### MAHSEAMLES
- **pnl_summary:** Sales: 4812 Cr (YoY -8.7%); NetProfit: 840 Cr (YoY +8.1%); EPS: 62.73
- **quarterly_summary:** Sales last 3Q: 1145, 1159, 1090 Cr; Net Profit last 3Q: 230, 125, 243 Cr
- **balance_sheet_summary:** Debt: 10 Cr
- **ratios_summary:** ROCE: 17%; EPS: 62.73; NPM: 17.46%

### TIINDIA
- **pnl_summary:** Sales: 21783 Cr (YoY +11.9%); NetProfit: 1042 Cr (YoY -1.1%); EPS: 30.9
- **quarterly_summary:** Sales last 3Q: 5309, 5523, 5801 Cr; Net Profit last 3Q: 303, 302, 279 Cr
- **balance_sheet_summary:** Debt: 705 Cr
- **ratios_summary:** ROCE: 32%; EPS: 30.9; NPM: 4.78%

### HBLENGINE
- **pnl_summary:** Sales: 3174 Cr (YoY +61.4%); NetProfit: 795 Cr (YoY +188%); EPS: 28.72
- **quarterly_summary:** Sales last 3Q: 602, 1223, 874 Cr; Net Profit last 3Q: 143, 387, 220 Cr
- **balance_sheet_summary:** Debt: 87 Cr
- **ratios_summary:** ROCE: 27%; EPS: 28.72; NPM: 25.05%

### VEDL
- **pnl_summary:** Sales: 120395 Cr (YoY -21.3%); NetProfit: 20704 Cr (YoY +0.8%); EPS: 36.25
- **quarterly_summary:** Sales last 3Q: 37824, 18747, 23369 Cr; Net Profit last 3Q: 4457, 3479, 7807 Cr
- **balance_sheet_summary:** Debt: 85065 Cr
- **ratios_summary:** ROCE: 19%; EPS: 36.25; NPM: 17.2%

### STAR
- **pnl_summary:** Sales: 4726 Cr (YoY +3.5%); NetProfit: 531 Cr (YoY -85.2%); EPS: 55.48
- **quarterly_summary:** Sales last 3Q: 1120, 1221, 1195 Cr; Net Profit last 3Q: 106, 132, 208 Cr
- **balance_sheet_summary:** Debt: 1844 Cr
- **ratios_summary:** ROCE: 5%; EPS: 55.48; NPM: 11.24%

### HINDALCO
- **pnl_summary:** Sales: 261701 Cr (YoY +9.7%); NetProfit: 16078 Cr (YoY +0.5%); EPS: 71.55
- **quarterly_summary:** Sales last 3Q: 64232, 66058, 66521 Cr; Net Profit last 3Q: 4004, 4741, 2049 Cr
- **balance_sheet_summary:** Debt: 74878 Cr
- **ratios_summary:** ROCE: 13%; EPS: 71.55; NPM: 6.14%

### GLENMARK
- **pnl_summary:** Sales: 16468 Cr (YoY +23.6%); NetProfit: 1065 Cr (YoY +1.7%); EPS: 37.74
- **quarterly_summary:** Sales last 3Q: 3264, 6047, 3901 Cr; Net Profit last 3Q: 47, 610, 403 Cr
- **balance_sheet_summary:** Debt: 1224 Cr
- **ratios_summary:** ROCE: 10%; EPS: 37.74; NPM: 6.47%

### COALINDIA
- **pnl_summary:** Sales: 138778 Cr (YoY -3.2%); NetProfit: 29755 Cr (YoY -15.7%); EPS: 48.45
- **quarterly_summary:** Sales last 3Q: 35842, 30187, 34924 Cr; Net Profit last 3Q: 8734, 4263, 7166 Cr
- **balance_sheet_summary:** Debt: 13786 Cr
- **ratios_summary:** ROCE: 97%; EPS: 48.45; NPM: 21.44%

### LUMAXTECH
- **pnl_summary:** Sales: 4586 Cr (YoY +26.1%); NetProfit: 319 Cr (YoY +39.3%); EPS: 36.56
- **quarterly_summary:** Sales last 3Q: 1026, 1156, 1271 Cr; Net Profit last 3Q: 54, 78, 108 Cr
- **balance_sheet_summary:** Debt: 1111 Cr
- **ratios_summary:** ROCE: 11%; EPS: 36.56; NPM: 6.96%

### HFCL
- **pnl_summary:** Sales: 3926 Cr (YoY -3.4%); NetProfit: 62 Cr (YoY -64.2%); EPS: 0.33
- **quarterly_summary:** Sales last 3Q: 871, 1043, 1211 Cr; Net Profit last 3Q: -29, 72, 102 Cr
- **balance_sheet_summary:** Debt: 1580 Cr
- **ratios_summary:** ROCE: 8%; EPS: 0.33; NPM: 1.58%

### BLUESTARCO
- **pnl_summary:** Sales: 12349 Cr (YoY +3.2%); NetProfit: 494 Cr (YoY -16.4%); EPS: 24.04
- **quarterly_summary:** Sales last 3Q: 2982, 2422, 2925 Cr; Net Profit last 3Q: 121, 99, 81 Cr
- **balance_sheet_summary:** Debt: 1030 Cr
- **ratios_summary:** ROCE: 23%; EPS: 24.04; NPM: 4%

### AXISBANK
- **pnl_summary:** Revenue: 130820 Cr (YoY +2.7%); NetProfit: 26415 Cr (YoY -6.3%); EPS: 84.66
- **quarterly_summary:** Sales last 3Q: 32348, 32310, 33709 Cr; Net Profit last 3Q: 6279, 5567, 7060 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 16%; EPS: 84.66; NPM: 20.19%

### NATCOPHARM
- **pnl_summary:** Sales: 4560 Cr (YoY +2.9%); NetProfit: 1556 Cr (YoY -17.4%); EPS: 86.94
- **quarterly_summary:** Sales last 3Q: 1329, 1363, 647 Cr; Net Profit last 3Q: 480, 518, 151 Cr
- **balance_sheet_summary:** Debt: 261 Cr
- **ratios_summary:** ROCE: 32%; EPS: 86.94; NPM: 34.12%

### TATACONSUM
- **pnl_summary:** Sales: 19465 Cr (YoY +10.5%); NetProfit: 1472 Cr (YoY +14.4%); EPS: 14.85
- **quarterly_summary:** Sales last 3Q: 4779, 4966, 5112 Cr; Net Profit last 3Q: 332, 407, 385 Cr
- **balance_sheet_summary:** Debt: 2576 Cr
- **ratios_summary:** ROCE: 10%; EPS: 14.85; NPM: 7.56%

### SHRIPISTON
- **pnl_summary:** Sales: 3991 Cr (YoY +12.4%); NetProfit: 554 Cr (YoY +7.4%); EPS: 123.29
- **quarterly_summary:** Sales last 3Q: 963, 1016, 1023 Cr; Net Profit last 3Q: 135, 142, 126 Cr
- **balance_sheet_summary:** Debt: 537 Cr
- **ratios_summary:** ROCE: 27%; EPS: 123.29; NPM: 13.88%

### NAM-INDIA
- **pnl_summary:** Sales: 2537 Cr (YoY +0.8%); NetProfit: 1443 Cr (YoY +12.2%); EPS: 22.68
- **quarterly_summary:** Sales last 3Q: 607, 658, 705 Cr; Net Profit last 3Q: 396, 345, 404 Cr
- **balance_sheet_summary:** Debt: 85 Cr
- **ratios_summary:** ROCE: 42%; EPS: 22.68; NPM: 56.88%

### VTL
- **pnl_summary:** Sales: 9880 Cr (YoY +1%); NetProfit: 802 Cr (YoY -9.6%); EPS: 27.59
- **quarterly_summary:** Sales last 3Q: 2386, 2480, 2505 Cr; Net Profit last 3Q: 208, 188, 168 Cr
- **balance_sheet_summary:** Debt: 1479 Cr
- **ratios_summary:** ROCE: 11%; EPS: 27.59; NPM: 8.12%

### HONASA
- **pnl_summary:** Sales: 2268 Cr (YoY +9.7%); NetProfit: 156 Cr (YoY +113.7%); EPS: 4.79
- **quarterly_summary:** Sales last 3Q: 595, 538, 602 Cr; Net Profit last 3Q: 41, 39, 50 Cr
- **balance_sheet_summary:** Debt: 142 Cr
- **ratios_summary:** ROCE: 7%; EPS: 4.79; NPM: 6.88%

### DMART
- **pnl_summary:** Sales: 66009 Cr (YoY +11.2%); NetProfit: 2864 Cr (YoY +5.8%); EPS: 44.03
- **quarterly_summary:** Sales last 3Q: 16360, 16676, 18101 Cr; Net Profit last 3Q: 773, 685, 856 Cr
- **balance_sheet_summary:** Debt: 1609 Cr
- **ratios_summary:** ROCE: 18%; EPS: 44.03; NPM: 4.34%

### KTKBANK
- **pnl_summary:** Revenue: 8919 Cr (YoY -1.1%); NetProfit: 1155 Cr (YoY -9.3%); EPS: 30.55
- **quarterly_summary:** Sales last 3Q: 2261, 2179, 2220 Cr; Net Profit last 3Q: 292, 319, 291 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 11%; EPS: 30.55; NPM: 12.95%

### HSCL
- **pnl_summary:** Sales: 4661 Cr (YoY +1%); NetProfit: 755 Cr (YoY +36%); EPS: 14.89
- **quarterly_summary:** Sales last 3Q: 1071, 1184, 1288 Cr; Net Profit last 3Q: 176, 192, 208 Cr
- **balance_sheet_summary:** Debt: 768 Cr
- **ratios_summary:** ROCE: 23%; EPS: 14.89; NPM: 16.2%

### FINCABLES
- **pnl_summary:** Sales: 5965 Cr (YoY +12.1%); NetProfit: 681 Cr (YoY -2.9%); EPS: 44.53
- **quarterly_summary:** Sales last 3Q: 1396, 1376, 1599 Cr; Net Profit last 3Q: 163, 163, 164 Cr
- **balance_sheet_summary:** Debt: 22 Cr
- **ratios_summary:** ROCE: 16%; EPS: 44.53; NPM: 11.42%

### SONACOMS
- **pnl_summary:** Sales: 4057 Cr (YoY +14.4%); NetProfit: 606 Cr (YoY +1%); EPS: 9.86
- **quarterly_summary:** Sales last 3Q: 854, 1138, 1200 Cr; Net Profit last 3Q: 122, 170, 150 Cr
- **balance_sheet_summary:** Debt: 211 Cr
- **ratios_summary:** ROCE: 18%; EPS: 9.86; NPM: 14.94%

### GPIL
- **pnl_summary:** Sales: 5238 Cr (YoY -2.5%); NetProfit: 743 Cr (YoY -8.6%); EPS: 11.09
- **quarterly_summary:** Sales last 3Q: 1323, 1308, 1139 Cr; Net Profit last 3Q: 216, 162, 143 Cr
- **balance_sheet_summary:** Debt: 192 Cr
- **ratios_summary:** ROCE: 23%; EPS: 11.09; NPM: 14.18%

### WABAG
- **pnl_summary:** Sales: 3686 Cr (YoY +11.9%); NetProfit: 341 Cr (YoY +15.6%); EPS: 54.92
- **quarterly_summary:** Sales last 3Q: 734, 834, 961 Cr; Net Profit last 3Q: 66, 85, 91 Cr
- **balance_sheet_summary:** Debt: 240 Cr
- **ratios_summary:** ROCE: 23%; EPS: 54.92; NPM: 9.25%

### JINDALSTEL
- **pnl_summary:** Sales: 50190 Cr (YoY +0.1%); NetProfit: 2016 Cr (YoY -29.2%); EPS: 19.45
- **quarterly_summary:** Sales last 3Q: 12294, 11686, 13027 Cr; Net Profit last 3Q: 1496, 635, 189 Cr
- **balance_sheet_summary:** Debt: 19156 Cr
- **ratios_summary:** ROCE: 12%; EPS: 19.45; NPM: 4.02%

### LUXIND
- **pnl_summary:** Sales: 2873 Cr (YoY +11.2%); NetProfit: 107 Cr (YoY -35.2%); EPS: 35.92
- **quarterly_summary:** Sales last 3Q: 604, 779, 673 Cr; Net Profit last 3Q: 23, 23, 13 Cr
- **balance_sheet_summary:** Debt: 575 Cr
- **ratios_summary:** ROCE: 13%; EPS: 35.92; NPM: 3.72%

### ZENTEC
- **pnl_summary:** Sales: 835 Cr (YoY -14.3%); NetProfit: 284 Cr (YoY -5%); EPS: 29.13
- **quarterly_summary:** Sales last 3Q: 158, 174, 178 Cr; Net Profit last 3Q: 53, 62, 56 Cr
- **balance_sheet_summary:** Debt: 18 Cr
- **ratios_summary:** ROCE: 33%; EPS: 29.13; NPM: 34.01%

### ELECON
- **pnl_summary:** Sales: 2366 Cr (YoY +6.2%); NetProfit: 341 Cr (YoY -17.8%); EPS: 15.2
- **quarterly_summary:** Sales last 3Q: 578, 552, 746 Cr; Net Profit last 3Q: 88, 72, 6 Cr
- **balance_sheet_summary:** Debt: 273 Cr
- **ratios_summary:** nan

### PRIVISCL
- **pnl_summary:** Sales: 2456 Cr (YoY +16.9%); NetProfit: 287 Cr (YoY +55.1%); EPS: 76.82
- **quarterly_summary:** Sales last 3Q: 559, 679, 605 Cr; Net Profit last 3Q: 58, 90, 75 Cr
- **balance_sheet_summary:** Debt: 1072 Cr
- **ratios_summary:** ROCE: 18%; EPS: 76.82; NPM: 11.69%

### ABSLAMC
- **pnl_summary:** Sales: 1845 Cr (YoY -6.9%); NetProfit: 975 Cr (YoY +4.7%); EPS: 33.76
- **quarterly_summary:** Sales last 3Q: 461, 478, 458 Cr; Net Profit last 3Q: 241, 270, 187 Cr
- **balance_sheet_summary:** Debt: 64 Cr
- **ratios_summary:** ROCE: 33%; EPS: 33.76; NPM: 52.85%

### GALLANTT
- **pnl_summary:** Sales: 4286 Cr (YoY -0.2%); NetProfit: 479 Cr (YoY +19.5%); EPS: 19.87
- **quarterly_summary:** Sales last 3Q: 1128, 1013, 1074 Cr; Net Profit last 3Q: 174, 89, 100 Cr
- **balance_sheet_summary:** Debt: 657 Cr
- **ratios_summary:** ROCE: 19%; EPS: 19.87; NPM: 11.18%

### IMFA
- **pnl_summary:** Sales: 2630 Cr (YoY +2.5%); NetProfit: 369 Cr (YoY -2.6%); EPS: 68.28
- **quarterly_summary:** Sales last 3Q: 642, 719, 703 Cr; Net Profit last 3Q: 93, 98, 131 Cr
- **balance_sheet_summary:** Debt: 435 Cr
- **ratios_summary:** ROCE: 21%; EPS: 68.28; NPM: 14.03%

### JSWENERGY
- **pnl_summary:** Sales: 17592 Cr (YoY +49.8%); NetProfit: 2603 Cr (YoY +31.3%); EPS: 13.01
- **quarterly_summary:** Sales last 3Q: 5143, 5177, 4082 Cr; Net Profit last 3Q: 836, 824, 529 Cr
- **balance_sheet_summary:** Debt: 69104 Cr
- **ratios_summary:** ROCE: 6%; EPS: 13.01; NPM: 14.8%

### SUNTV
- **pnl_summary:** Sales: 4394 Cr (YoY +9.4%); NetProfit: 1579 Cr (YoY -7.3%); EPS: 40.05
- **quarterly_summary:** Sales last 3Q: 1290, 1300, 862 Cr; Net Profit last 3Q: 529, 355, 324 Cr
- **balance_sheet_summary:** Debt: 146 Cr
- **ratios_summary:** ROCE: 20%; EPS: 40.05; NPM: 35.94%

### BEL
- **pnl_summary:** Sales: 26535 Cr (YoY +11.6%); NetProfit: 5963 Cr (YoY +12%); EPS: 8.16
- **quarterly_summary:** Sales last 3Q: 4440, 5792, 7154 Cr; Net Profit last 3Q: 969, 1287, 1580 Cr
- **balance_sheet_summary:** Debt: 59 Cr
- **ratios_summary:** ROCE: 39%; EPS: 8.16; NPM: 22.47%

### AADHARHFC
- **pnl_summary:** Revenue: 3521 Cr (YoY +13.3%); NetProfit: 1030 Cr (YoY +12.9%); EPS: 23.8
- **quarterly_summary:** Sales last 3Q: 848, 897, 943 Cr; Net Profit last 3Q: 237, 266, 281 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 17%; EPS: 23.8; NPM: 29.25%

### GICRE
- **pnl_summary:** Sales: 53176 Cr (YoY +7.2%); NetProfit: 9629 Cr (YoY +29.6%); EPS: 54.88
- **quarterly_summary:** Sales last 3Q: 14623, 12755, 12589 Cr; Net Profit last 3Q: 2531, 2874, 1726 Cr
- **balance_sheet_summary:** Debt: 0 Cr
- **ratios_summary:** ROCE: 16%; EPS: 54.88; NPM: 18.11%

### JSWSTEEL
- **pnl_summary:** Sales: 179109 Cr (YoY +6.1%); NetProfit: 7766 Cr (YoY +122.5%); EPS: 30.47
- **quarterly_summary:** Sales last 3Q: 43147, 45152, 45991 Cr; Net Profit last 3Q: 2209, 1646, 2410 Cr
- **balance_sheet_summary:** Debt: 101107 Cr
- **ratios_summary:** ROCE: 10%; EPS: 30.47; NPM: 4.34%

### TATASTEEL
- **pnl_summary:** Sales: 225088 Cr (YoY +3%); NetProfit: 9122 Cr (YoY +187.4%); EPS: 7.33
- **quarterly_summary:** Sales last 3Q: 53178, 58689, 57002 Cr; Net Profit last 3Q: 2007, 3183, 2730 Cr
- **balance_sheet_summary:** Debt: 95643 Cr
- **ratios_summary:** ROCE: 13%; EPS: 7.33; NPM: 4.05%

### POWERINDIA
- **pnl_summary:** Sales: 7277 Cr (YoY +14%); NetProfit: 841 Cr (YoY +119%); EPS: 188.74
- **quarterly_summary:** Sales last 3Q: 1479, 1833, 2082 Cr; Net Profit last 3Q: 132, 264, 261 Cr
- **balance_sheet_summary:** Debt: 84 Cr
- **ratios_summary:** ROCE: 19%; EPS: 188.74; NPM: 11.56%

### KIRLOSENG
- **pnl_summary:** Sales: 7334 Cr (YoY +15.5%); NetProfit: 534 Cr (YoY +12.2%); EPS: 37.64
- **quarterly_summary:** Sales last 3Q: 1764, 1948, 1873 Cr; Net Profit last 3Q: 139, 159, 109 Cr
- **balance_sheet_summary:** Debt: 5526 Cr
- **ratios_summary:** ROCE: 18%; EPS: 37.64; NPM: 7.28%

### ABDL
- **pnl_summary:** Sales: 3837 Cr (YoY +9%); NetProfit: 261 Cr (YoY +33.8%); EPS: 9.51
- **quarterly_summary:** Sales last 3Q: 923, 990, 1003 Cr; Net Profit last 3Q: 56, 63, 64 Cr
- **balance_sheet_summary:** Debt: 1056 Cr
- **ratios_summary:** ROCE: 21%; EPS: 9.51; NPM: 6.8%

### NLCINDIA
- **pnl_summary:** Sales: 16283 Cr (YoY +6.3%); NetProfit: 2756 Cr (YoY +1.5%); EPS: 18.83
- **quarterly_summary:** Sales last 3Q: 3826, 4178, 4443 Cr; Net Profit last 3Q: 839, 725, 724 Cr
- **balance_sheet_summary:** Debt: 24368 Cr
- **ratios_summary:** ROCE: 9%; EPS: 18.83; NPM: 16.93%

### PFC
- **pnl_summary:** Revenue: 115789 Cr (YoY +8.1%); NetProfit: 33386 Cr (YoY +9.4%); EPS: 76.42
- **quarterly_summary:** Sales last 3Q: 28539, 28890, 29095 Cr; Net Profit last 3Q: 8981, 7834, 8212 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 20%; EPS: 76.42; NPM: 28.83%

### YATHARTH
- **pnl_summary:** Sales: 1089 Cr (YoY +26.6%); NetProfit: 165 Cr (YoY +26%); EPS: 17.37
- **quarterly_summary:** Sales last 3Q: 258, 279, 320 Cr; Net Profit last 3Q: 42, 41, 43 Cr
- **balance_sheet_summary:** Debt: 26 Cr
- **ratios_summary:** ROCE: 10%; EPS: 17.37; NPM: 15.15%

### KEI
- **pnl_summary:** Sales: 11186 Cr (YoY +14.9%); NetProfit: 861 Cr (YoY +23.7%); EPS: 90.06
- **quarterly_summary:** Sales last 3Q: 2590, 2726, 2955 Cr; Net Profit last 3Q: 196, 204, 235 Cr
- **balance_sheet_summary:** Debt: 235 Cr
- **ratios_summary:** ROCE: 21%; EPS: 90.06; NPM: 7.7%

### STLTECH
- **pnl_summary:** Sales: 4363 Cr (YoY +9.2%); NetProfit: -43 Cr (YoY +65%); EPS: -0.89
- **quarterly_summary:** Sales last 3Q: 1020, 1034, 1257 Cr; Net Profit last 3Q: 10, 4, -17 Cr
- **balance_sheet_summary:** Debt: 1921 Cr
- **ratios_summary:** ROCE: 0%; EPS: -0.89; NPM: -0.99%

### TDPOWERSYS
- **pnl_summary:** Sales: 1615 Cr (YoY +26.3%); NetProfit: 220 Cr (YoY +25.7%); EPS: 14.06
- **quarterly_summary:** Sales last 3Q: 372, 452, 443 Cr; Net Profit last 3Q: 50, 60, 56 Cr
- **balance_sheet_summary:** Debt: 36 Cr
- **ratios_summary:** ROCE: 28%; EPS: 14.06; NPM: 13.62%

### KSB
- **pnl_summary:** Sales: 2696 Cr (YoY +6.4%); NetProfit: 270 Cr (YoY +9.3%); EPS: 15.54
- **quarterly_summary:** Sales last 3Q: 667, 650, 784 Cr; Net Profit last 3Q: 70, 68, 81 Cr
- **balance_sheet_summary:** Debt: 5 Cr
- **ratios_summary:** ROCE: 25%; EPS: 15.54; NPM: 10.01%

### NAVA
- **pnl_summary:** Sales: 4166 Cr (YoY +4.6%); NetProfit: 1205 Cr (YoY -16%); EPS: 31.58
- **quarterly_summary:** Sales last 3Q: 1193, 964, 991 Cr; Net Profit last 3Q: 399, 178, 326 Cr
- **balance_sheet_summary:** Debt: 1596 Cr
- **ratios_summary:** ROCE: 14%; EPS: 31.58; NPM: 28.92%

### THERMAX
- **pnl_summary:** Sales: 10351 Cr (YoY -0.4%); NetProfit: 681 Cr (YoY +8.6%); EPS: 57.24
- **quarterly_summary:** Sales last 3Q: 2158, 2474, 2635 Cr; Net Profit last 3Q: 151, 119, 205 Cr
- **balance_sheet_summary:** Debt: 1811 Cr
- **ratios_summary:** ROCE: 17%; EPS: 57.24; NPM: 6.58%

### SOLARINDS
- **pnl_summary:** Sales: 8952 Cr (YoY +18.7%); NetProfit: 1527 Cr (YoY +18.6%); EPS: 160.47
- **quarterly_summary:** Sales last 3Q: 2154, 2082, 2548 Cr; Net Profit last 3Q: 353, 361, 467 Cr
- **balance_sheet_summary:** Debt: 876 Cr
- **ratios_summary:** ROCE: 37%; EPS: 160.47; NPM: 17.06%

### ADANIGREEN
- **pnl_summary:** Sales: 12499 Cr (YoY +11.5%); NetProfit: 1856 Cr (YoY -7.2%); EPS: 9.13
- **quarterly_summary:** Sales last 3Q: 3800, 3008, 2618 Cr; Net Profit last 3Q: 824, 644, 5 Cr
- **balance_sheet_summary:** Debt: 88153 Cr
- **ratios_summary:** ROCE: 9%; EPS: 9.13; NPM: 14.85%

### EPL
- **pnl_summary:** Sales: 4568 Cr (YoY +8.4%); NetProfit: 406 Cr (YoY +11.5%); EPS: 12.52
- **quarterly_summary:** Sales last 3Q: 1108, 1206, 1149 Cr; Net Profit last 3Q: 101, 106, 83 Cr
- **balance_sheet_summary:** Debt: 850 Cr
- **ratios_summary:** ROCE: 20%; EPS: 12.52; NPM: 8.89%

### FACT
- **pnl_summary:** Sales: 5293 Cr (YoY +30.7%); NetProfit: 28 Cr (YoY -31.7%); EPS: 0.43
- **quarterly_summary:** Sales last 3Q: 1043, 1629, 1568 Cr; Net Profit last 3Q: 4, 21, -68 Cr
- **balance_sheet_summary:** Debt: 3837 Cr
- **ratios_summary:** ROCE: 9%; EPS: 0.43; NPM: 0.53%

### WAAREEENER
- **pnl_summary:** Sales: 22060 Cr (YoY +52.7%); NetProfit: 3402 Cr (YoY +76.5%); EPS: 113.71
- **quarterly_summary:** Sales last 3Q: 4426, 6066, 7565 Cr; Net Profit last 3Q: 773, 878, 1107 Cr
- **balance_sheet_summary:** Debt: 2941 Cr
- **ratios_summary:** ROCE: 34%; EPS: 113.71; NPM: 15.42%

### PREMIERENE
- **pnl_summary:** Sales: 7215 Cr (YoY +10.7%); NetProfit: 1331 Cr (YoY +42%); EPS: 29.44
- **quarterly_summary:** Sales last 3Q: 1821, 1837, 1936 Cr; Net Profit last 3Q: 308, 353, 392 Cr
- **balance_sheet_summary:** Debt: 1622 Cr
- **ratios_summary:** ROCE: 12%; EPS: 29.44; NPM: 18.45%

### STARHEALTH
- **pnl_summary:** Sales: 17258 Cr (YoY +7.2%); NetProfit: 446 Cr (YoY -31%); EPS: 7.59
- **quarterly_summary:** Sales last 3Q: 4233, 4378, 4566 Cr; Net Profit last 3Q: 263, 55, 128 Cr
- **balance_sheet_summary:** Debt: 470 Cr
- **ratios_summary:** ROCE: 12%; EPS: 7.59; NPM: 2.58%

### CANFINHOME
- **pnl_summary:** Revenue: 4141 Cr (YoY +6.8%); NetProfit: 974 Cr (YoY +13.7%); EPS: 73.15
- **quarterly_summary:** Sales last 3Q: 1020, 1049, 1073 Cr; Net Profit last 3Q: 224, 251, 265 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 18%; EPS: 73.15; NPM: 23.52%

### KRN
- **pnl_summary:** Sales: 552 Cr (YoY +28.4%); NetProfit: 68 Cr (YoY +28.3%); EPS: 10.94
- **quarterly_summary:** Sales last 3Q: 115, 152, 153 Cr; Net Profit last 3Q: 12, 18, 23 Cr
- **balance_sheet_summary:** Debt: 30 Cr
- **ratios_summary:** ROCE: 21%; EPS: 10.94; NPM: 12.32%

### NTPCGREEN
- **pnl_summary:** Sales: 2568 Cr (YoY +16.2%); NetProfit: 557 Cr (YoY +17.5%); EPS: 0.66
- **quarterly_summary:** Sales last 3Q: 680, 612, 653 Cr; Net Profit last 3Q: 220, 86, 17 Cr
- **balance_sheet_summary:** Debt: 21826 Cr
- **ratios_summary:** ROCE: 6%; EPS: 0.66; NPM: 21.69%

### HEG
- **pnl_summary:** Sales: 2515 Cr (YoY +16.5%); NetProfit: 381 Cr (YoY +231.3%); EPS: 19.77
- **quarterly_summary:** Sales last 3Q: 617, 699, 656 Cr; Net Profit last 3Q: 105, 143, 207 Cr
- **balance_sheet_summary:** Debt: 644 Cr
- **ratios_summary:** ROCE: 5%; EPS: 19.77; NPM: 15.15%

### POWERGRID
- **pnl_summary:** Sales: 47343 Cr (YoY +3.4%); NetProfit: 15524 Cr (YoY +0%); EPS: 16.68
- **quarterly_summary:** Sales last 3Q: 11196, 11476, 12395 Cr; Net Profit last 3Q: 3631, 3566, 4185 Cr
- **balance_sheet_summary:** Debt: 135984 Cr
- **ratios_summary:** ROCE: 13%; EPS: 16.68; NPM: 32.79%

### PNGJL
- **pnl_summary:** Sales: 8783 Cr (YoY +15.8%); NetProfit: 382 Cr (YoY +75.2%); EPS: 28.11
- **quarterly_summary:** Sales last 3Q: 1715, 2178, 3303 Cr; Net Profit last 3Q: 69, 79, 171 Cr
- **balance_sheet_summary:** Debt: 1291 Cr
- **ratios_summary:** ROCE: 19%; EPS: 28.11; NPM: 4.35%

### TATAPOWER
- **pnl_summary:** Sales: 64624 Cr (YoY -1.3%); NetProfit: 5008 Cr (YoY +4.9%); EPS: 11.88
- **quarterly_summary:** Sales last 3Q: 18035, 15545, 13948 Cr; Net Profit last 3Q: 1262, 1245, 1194 Cr
- **balance_sheet_summary:** Debt: 70083 Cr
- **ratios_summary:** ROCE: 15%; EPS: 11.88; NPM: 7.75%

### VIJAYA
- **pnl_summary:** Sales: 768 Cr (YoY +12.8%); NetProfit: 160 Cr (YoY +11.1%); EPS: 15.55
- **quarterly_summary:** Sales last 3Q: 188, 202, 205 Cr; Net Profit last 3Q: 39, 43, 43 Cr
- **balance_sheet_summary:** Debt: 365 Cr
- **ratios_summary:** ROCE: 20%; EPS: 15.55; NPM: 20.83%

### OBEROIRLTY
- **pnl_summary:** Sales: 5409 Cr (YoY +2.3%); NetProfit: 2237 Cr (YoY +0.5%); EPS: 61.53
- **quarterly_summary:** Sales last 3Q: 988, 1779, 1493 Cr; Net Profit last 3Q: 421, 760, 623 Cr
- **balance_sheet_summary:** Debt: 3027 Cr
- **ratios_summary:** ROCE: 15%; EPS: 61.53; NPM: 41.36%

### ONGC
- **pnl_summary:** Sales: 659254 Cr (YoY +7.7%); NetProfit: 44972 Cr (YoY +17.3%); EPS: 30.14
- **quarterly_summary:** Sales last 3Q: 163108, 157911, 167423 Cr; Net Profit last 3Q: 11554, 12615, 11946 Cr
- **balance_sheet_summary:** Debt: 176018 Cr
- **ratios_summary:** ROCE: 15%; EPS: 30.14; NPM: 6.82%

### KSL
- **pnl_summary:** Sales: 1906 Cr (YoY -3.8%); NetProfit: 266 Cr (YoY +3.9%); EPS: 61.02
- **quarterly_summary:** Sales last 3Q: 443, 456, 462 Cr; Net Profit last 3Q: 62, 63, 62 Cr
- **balance_sheet_summary:** Debt: 428 Cr
- **ratios_summary:** ROCE: 16%; EPS: 61.02; NPM: 13.96%

### TITAN
- **pnl_summary:** Sales: 75580 Cr (YoY +25%); NetProfit: 4766 Cr (YoY +42.8%); EPS: 53.69
- **quarterly_summary:** Sales last 3Q: 16523, 18725, 25416 Cr; Net Profit last 3Q: 1091, 1120, 1684 Cr
- **balance_sheet_summary:** Debt: 12465 Cr
- **ratios_summary:** ROCE: 17%; EPS: 53.69; NPM: 6.31%

### GMDCLTD
- **pnl_summary:** Sales: 2626 Cr (YoY -7.9%); NetProfit: 989 Cr (YoY +44.2%); EPS: 31.09
- **quarterly_summary:** Sales last 3Q: 733, 528, 579 Cr; Net Profit last 3Q: 164, 466, 133 Cr
- **balance_sheet_summary:** Debt: 278 Cr
- **ratios_summary:** ROCE: 14%; EPS: 31.09; NPM: 37.66%

### MTARTECH
- **pnl_summary:** Sales: 753 Cr (YoY +11.4%); NetProfit: 63 Cr (YoY +18.9%); EPS: 20.63
- **quarterly_summary:** Sales last 3Q: 157, 136, 278 Cr; Net Profit last 3Q: 11, 4, 35 Cr
- **balance_sheet_summary:** Debt: 186 Cr
- **ratios_summary:** ROCE: 11%; EPS: 20.63; NPM: 8.37%

### GESHIP
- **pnl_summary:** Sales: 5121 Cr (YoY -3.8%); NetProfit: 2262 Cr (YoY -3.5%); EPS: 158.4
- **quarterly_summary:** Sales last 3Q: 1201, 1242, 1454 Cr; Net Profit last 3Q: 504, 581, 813 Cr
- **balance_sheet_summary:** Debt: 1254 Cr
- **ratios_summary:** ROCE: 15%; EPS: 158.4; NPM: 44.17%

### SYRMA
- **pnl_summary:** Sales: 4278 Cr (YoY +13%); NetProfit: 298 Cr (YoY +62%); EPS: 15.12
- **quarterly_summary:** Sales last 3Q: 944, 1146, 1264 Cr; Net Profit last 3Q: 50, 66, 110 Cr
- **balance_sheet_summary:** Debt: 332 Cr
- **ratios_summary:** ROCE: 6%; EPS: 15.12; NPM: 6.97%

### LUPIN
- **pnl_summary:** Sales: 26150 Cr (YoY +15.2%); NetProfit: 4669 Cr (YoY +41.2%); EPS: 101.7
- **quarterly_summary:** Sales last 3Q: 6268, 7048, 7168 Cr; Net Profit last 3Q: 1221, 1485, 1181 Cr
- **balance_sheet_summary:** Debt: 6217 Cr
- **ratios_summary:** ROCE: 22%; EPS: 101.7; NPM: 17.85%

### KIRLOSBROS
- **pnl_summary:** Sales: 4404 Cr (YoY -2%); NetProfit: 403 Cr (YoY -3.8%); EPS: 50.26
- **quarterly_summary:** Sales last 3Q: 979, 1028, 1116 Cr; Net Profit last 3Q: 68, 72, 125 Cr
- **balance_sheet_summary:** Debt: 219 Cr
- **ratios_summary:** ROCE: 21%; EPS: 50.26; NPM: 9.15%

### RADICO
- **pnl_summary:** Sales: 5851 Cr (YoY +20.8%); NetProfit: 517 Cr (YoY +49.4%); EPS: 38.62
- **quarterly_summary:** Sales last 3Q: 1506, 1494, 1547 Cr; Net Profit last 3Q: 131, 140, 155 Cr
- **balance_sheet_summary:** Debt: 624 Cr
- **ratios_summary:** ROCE: 16%; EPS: 38.62; NPM: 8.84%

### GRAPHITE
- **pnl_summary:** Sales: 2702 Cr (YoY +5.5%); NetProfit: 325 Cr (YoY -29%); EPS: 16.84
- **quarterly_summary:** Sales last 3Q: 665, 729, 642 Cr; Net Profit last 3Q: 133, 76, 67 Cr
- **balance_sheet_summary:** Debt: 269 Cr
- **ratios_summary:** ROCE: 10%; EPS: 16.84; NPM: 12.03%

### SKIPPER
- **pnl_summary:** Sales: 5174 Cr (YoY +11.9%); NetProfit: 183 Cr (YoY +22.8%); EPS: 16.22
- **quarterly_summary:** Sales last 3Q: 1254, 1262, 1371 Cr; Net Profit last 3Q: 45, 37, 53 Cr
- **balance_sheet_summary:** Debt: 801 Cr
- **ratios_summary:** ROCE: 24%; EPS: 16.22; NPM: 3.54%

### SCI
- **pnl_summary:** Sales: 5592 Cr (YoY -0.2%); NetProfit: 1133 Cr (YoY +34.2%); EPS: 24.32
- **quarterly_summary:** Sales last 3Q: 1316, 1339, 1612 Cr; Net Profit last 3Q: 354, 189, 405 Cr
- **balance_sheet_summary:** Debt: 2811 Cr
- **ratios_summary:** ROCE: 10%; EPS: 24.32; NPM: 20.26%

### NIACL
- **pnl_summary:** Sales: 48902 Cr (YoY +12.8%); NetProfit: 1193 Cr (YoY +14.9%); EPS: 7.25
- **quarterly_summary:** Sales last 3Q: 11719, 13450, 12069 Cr; Net Profit last 3Q: 402, 55, 380 Cr
- **balance_sheet_summary:** Debt: 0 Cr
- **ratios_summary:** ROCE: 4%; EPS: 7.25; NPM: 2.44%

### FEDERALBNK
- **pnl_summary:** Revenue: 28835 Cr (YoY +2.6%); NetProfit: 4219 Cr (YoY -0.4%); EPS: 16.65
- **quarterly_summary:** Sales last 3Q: 7151, 7216, 7360 Cr; Net Profit last 3Q: 951, 1023, 1125 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 13%; EPS: 16.65; NPM: 14.63%

### VSTIND
- **pnl_summary:** Sales: 471 Cr (YoY +23.9%); NetProfit: 62 Cr (YoY +0%); EPS: 3.65
- **quarterly_summary:** Sales last 3Q: 336, 373, 457 Cr; Net Profit last 3Q: 59, 60, 117 Cr
- **balance_sheet_summary:** Debt: 0 Cr
- **ratios_summary:** ROCE: 28%; EPS: 3.65; NPM: 13.16%

### RRKABEL
- **pnl_summary:** Sales: 8976 Cr (YoY +17.8%); NetProfit: 453 Cr (YoY +45.2%); EPS: 40.1
- **quarterly_summary:** Sales last 3Q: 2059, 2164, 2536 Cr; Net Profit last 3Q: 90, 116, 118 Cr
- **balance_sheet_summary:** Debt: 393 Cr
- **ratios_summary:** ROCE: 20%; EPS: 40.1; NPM: 5.05%

### TRITURBINE
- **pnl_summary:** Sales: 2040 Cr (YoY +1.7%); NetProfit: 342 Cr (YoY -4.7%); EPS: 10.75
- **quarterly_summary:** Sales last 3Q: 371, 506, 624 Cr; Net Profit last 3Q: 64, 91, 92 Cr
- **balance_sheet_summary:** Debt: 38 Cr
- **ratios_summary:** ROCE: 48%; EPS: 10.75; NPM: 16.76%

### HAL
- **pnl_summary:** Sales: 32846 Cr (YoY +6%); NetProfit: 8896 Cr (YoY +6.4%); EPS: 133.02
- **quarterly_summary:** Sales last 3Q: 4819, 6629, 7699 Cr; Net Profit last 3Q: 1384, 1669, 1867 Cr
- **balance_sheet_summary:** Debt: 11 Cr
- **ratios_summary:** ROCE: 34%; EPS: 133.02; NPM: 27.08%

### DIVISLAB
- **pnl_summary:** Sales: 10314 Cr (YoY +10.2%); NetProfit: 2479 Cr (YoY +13.1%); EPS: 93.38
- **quarterly_summary:** Sales last 3Q: 2410, 2715, 2604 Cr; Net Profit last 3Q: 545, 689, 583 Cr
- **balance_sheet_summary:** Debt: 90 Cr
- **ratios_summary:** ROCE: 21%; EPS: 93.38; NPM: 24.04%

### VOLTAS
- **pnl_summary:** Sales: 14124 Cr (YoY -8.4%); NetProfit: 492 Cr (YoY -41%); EPS: 15.13
- **quarterly_summary:** Sales last 3Q: 3939, 2347, 3071 Cr; Net Profit last 3Q: 141, 32, 84 Cr
- **balance_sheet_summary:** Debt: 1755 Cr
- **ratios_summary:** ROCE: 13%; EPS: 15.13; NPM: 3.48%

### PRSMJOHNSN
- **pnl_summary:** Sales: 7723 Cr (YoY +5.6%); NetProfit: 167 Cr (YoY +271.1%); EPS: 3.89
- **quarterly_summary:** Sales last 3Q: 1922, 1855, 1844 Cr; Net Profit last 3Q: -6, 2, 50 Cr
- **balance_sheet_summary:** Debt: 1694 Cr
- **ratios_summary:** ROCE: 3%; EPS: 3.89; NPM: 2.16%

### ADANIPORTS
- **pnl_summary:** Sales: 36487 Cr (YoY +19.7%); NetProfit: 12497 Cr (YoY +13%); EPS: 56.93
- **quarterly_summary:** Sales last 3Q: 9126, 9167, 9705 Cr; Net Profit last 3Q: 3311, 3120, 3043 Cr
- **balance_sheet_summary:** Debt: 56851 Cr
- **ratios_summary:** ROCE: 9%; EPS: 56.93; NPM: 34.25%

### SUNTECK
- **pnl_summary:** Sales: 1124 Cr (YoY +31.8%); NetProfit: 202 Cr (YoY +34.7%); EPS: 13.92
- **quarterly_summary:** Sales last 3Q: 252, 344, 339 Cr; Net Profit last 3Q: 49, 57, 63 Cr
- **balance_sheet_summary:** Debt: 774 Cr
- **ratios_summary:** ROCE: 1%; EPS: 13.92; NPM: 17.97%

### GNFC
- **pnl_summary:** Sales: 7620 Cr (YoY -3.4%); NetProfit: 623 Cr (YoY +4.2%); EPS: 42.4
- **quarterly_summary:** Sales last 3Q: 1601, 1968, 1996 Cr; Net Profit last 3Q: 83, 179, 150 Cr
- **balance_sheet_summary:** Debt: 13 Cr
- **ratios_summary:** ROCE: 10%; EPS: 42.4; NPM: 8.18%

### PTC
- **pnl_summary:** Sales: 15797 Cr (YoY -2.7%); NetProfit: 968 Cr (YoY -0.8%); EPS: 28.78
- **quarterly_summary:** Sales last 3Q: 4009, 5459, 3405 Cr; Net Profit last 3Q: 243, 222, 131 Cr
- **balance_sheet_summary:** Debt: 2264 Cr
- **ratios_summary:** ROCE: 12%; EPS: 28.78; NPM: 6.13%

### MIDHANI
- **pnl_summary:** Sales: 1066 Cr (YoY -0.7%); NetProfit: 110 Cr (YoY -0.9%); EPS: 5.86
- **quarterly_summary:** Sales last 3Q: 170, 210, 276 Cr; Net Profit last 3Q: 13, 13, 28 Cr
- **balance_sheet_summary:** Debt: 338 Cr
- **ratios_summary:** ROCE: 11%; EPS: 5.86; NPM: 10.32%

### WELSPUNLIV
- **pnl_summary:** Sales: 9610 Cr (YoY -8.9%); NetProfit: 240 Cr (YoY -62.7%); EPS: 2.42
- **quarterly_summary:** Sales last 3Q: 2261, 2441, 2262 Cr; Net Profit last 3Q: 89, 15, 3 Cr
- **balance_sheet_summary:** Debt: 2685 Cr
- **ratios_summary:** ROCE: 14%; EPS: 2.42; NPM: 2.5%

### GSPL
- **pnl_summary:** Sales: 16290 Cr (YoY -6.2%); NetProfit: 1585 Cr (YoY -3.2%); EPS: 18.65
- **quarterly_summary:** Sales last 3Q: 4107, 4008, 3885 Cr; Net Profit last 3Q: 465, 389, 379 Cr
- **balance_sheet_summary:** Debt: 140 Cr
- **ratios_summary:** ROCE: 10%; EPS: 18.65; NPM: 9.73%

### RELINFRA
- **pnl_summary:** Sales: 20547 Cr (YoY -15.9%); NetProfit: 11460 Cr (YoY +24.9%); EPS: 159.25
- **quarterly_summary:** Sales last 3Q: 5908, 6235, 4297 Cr; Net Profit last 3Q: 305, 2575, 317 Cr
- **balance_sheet_summary:** Debt: 5737 Cr
- **ratios_summary:** ROCE: -1%; EPS: 159.25; NPM: 55.77%

### TVSSCS
- **pnl_summary:** Sales: 10470 Cr (YoY +4.7%); NetProfit: 95 Cr (YoY +1050%); EPS: 2.08
- **quarterly_summary:** Sales last 3Q: 2592, 2663, 2716 Cr; Net Profit last 3Q: 71, 16, 11 Cr
- **balance_sheet_summary:** Debt: 2221 Cr
- **ratios_summary:** ROCE: 4%; EPS: 2.08; NPM: 0.91%

### KIRLPNU
- **pnl_summary:** Sales: 1667 Cr (YoY +1.6%); NetProfit: 191 Cr (YoY -9.5%); EPS: 29.67
- **quarterly_summary:** Sales last 3Q: 282, 386, 407 Cr; Net Profit last 3Q: 25, 44, 42 Cr
- **balance_sheet_summary:** Debt: 9 Cr
- **ratios_summary:** ROCE: 28%; EPS: 29.67; NPM: 11.46%

### BBL
- **pnl_summary:** Sales: 2126 Cr (YoY +11.8%); NetProfit: 131 Cr (YoY -2.2%); EPS: 115.99
- **quarterly_summary:** Sales last 3Q: 465, 473, 568 Cr; Net Profit last 3Q: 28, 28, 25 Cr
- **balance_sheet_summary:** Debt: 191 Cr
- **ratios_summary:** ROCE: 10%; EPS: 115.99; NPM: 6.16%

### SCHNEIDER
- **pnl_summary:** Sales: 2888 Cr (YoY +9.5%); NetProfit: 245 Cr (YoY -8.6%); EPS: 10.25
- **quarterly_summary:** Sales last 3Q: 622, 650, 1029 Cr; Net Profit last 3Q: 41, 52, 97 Cr
- **balance_sheet_summary:** Debt: 527 Cr
- **ratios_summary:** ROCE: 41%; EPS: 10.25; NPM: 8.48%

### LLOYDSENT
- **pnl_summary:** Sales: 1526 Cr (YoY +2.6%); NetProfit: 373 Cr (YoY +203.3%); EPS: 1.66
- **quarterly_summary:** Sales last 3Q: 331, 407, 299 Cr; Net Profit last 3Q: 249, 62, 38 Cr
- **balance_sheet_summary:** Debt: 671 Cr
- **ratios_summary:** ROCE: 1%; EPS: 1.66; NPM: 24.44%

### INGERRAND
- **pnl_summary:** Sales: 1415 Cr (YoY +5.9%); NetProfit: 259 Cr (YoY -3.4%); EPS: 82
- **quarterly_summary:** Sales last 3Q: 315, 322, 455 Cr; Net Profit last 3Q: 59, 60, 72 Cr
- **balance_sheet_summary:** Debt: 10 Cr
- **ratios_summary:** ROCE: 60%; EPS: 82; NPM: 18.3%

### MAHABANK
- **pnl_summary:** Revenue: 29282 Cr (YoY +17.4%); NetProfit: 7017 Cr (YoY +26.6%); EPS: 9.12
- **quarterly_summary:** Sales last 3Q: 7128, 7344, 7755 Cr; Net Profit last 3Q: 1669, 1799, 2045 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 23%; EPS: 9.12; NPM: 23.96%

### BOSCHLTD
- **pnl_summary:** Sales: 19380 Cr (YoY +7.1%); NetProfit: 2757 Cr (YoY +36.8%); EPS: 934.68
- **quarterly_summary:** Sales last 3Q: 4789, 4795, 4886 Cr; Net Profit last 3Q: 1116, 554, 533 Cr
- **balance_sheet_summary:** Debt: 109 Cr
- **ratios_summary:** ROCE: 21%; EPS: 934.68; NPM: 14.23%

### KPIL
- **pnl_summary:** Sales: 26432 Cr (YoY +18.4%); NetProfit: 818 Cr (YoY +44.3%); EPS: 48.68
- **quarterly_summary:** Sales last 3Q: 6171, 6529, 6665 Cr; Net Profit last 3Q: 214, 237, 149 Cr
- **balance_sheet_summary:** Debt: 4828 Cr
- **ratios_summary:** ROCE: 15%; EPS: 48.68; NPM: 3.09%

### LINDEINDIA
- **pnl_summary:** Sales: 2508 Cr (YoY +0.9%); NetProfit: 590 Cr (YoY +29.7%); EPS: 69.17
- **quarterly_summary:** Sales last 3Q: 571, 644, 701 Cr; Net Profit last 3Q: 107, 171, 193 Cr
- **balance_sheet_summary:** Debt: 67 Cr
- **ratios_summary:** ROCE: 17%; EPS: 69.17; NPM: 23.52%

### JPPOWER
- **pnl_summary:** Sales: 5518 Cr (YoY +1%); NetProfit: 620 Cr (YoY -23.8%); EPS: 0.92
- **quarterly_summary:** Sales last 3Q: 1583, 1438, 1156 Cr; Net Profit last 3Q: 278, 182, 4 Cr
- **balance_sheet_summary:** Debt: 3519 Cr
- **ratios_summary:** ROCE: 10%; EPS: 0.92; NPM: 11.24%

### AIAENG
- **pnl_summary:** Sales: 4311 Cr (YoY +0.6%); NetProfit: 1161 Cr (YoY +9.5%); EPS: 124.53
- **quarterly_summary:** Sales last 3Q: 1039, 1048, 1067 Cr; Net Profit last 3Q: 305, 277, 293 Cr
- **balance_sheet_summary:** Debt: 1022 Cr
- **ratios_summary:** ROCE: 19%; EPS: 124.53; NPM: 26.93%

### ENTERO
- **pnl_summary:** Sales: 6020 Cr (YoY +18.1%); NetProfit: 132 Cr (YoY +23.4%); EPS: 25.9
- **quarterly_summary:** Sales last 3Q: 1404, 1571, 1707 Cr; Net Profit last 3Q: 30, 37, 34 Cr
- **balance_sheet_summary:** Debt: 443 Cr
- **ratios_summary:** ROCE: 5%; EPS: 25.9; NPM: 2.19%

### NMDC
- **pnl_summary:** Sales: 27732 Cr (YoY +16%); NetProfit: 6900 Cr (YoY +5.8%); EPS: 7.85
- **quarterly_summary:** Sales last 3Q: 6739, 6378, 7611 Cr; Net Profit last 3Q: 1968, 1698, 1757 Cr
- **balance_sheet_summary:** Debt: 3640 Cr
- **ratios_summary:** ROCE: 30%; EPS: 7.85; NPM: 24.88%

### SUZLON
- **pnl_summary:** Sales: 15029 Cr (YoY +38%); NetProfit: 3230 Cr (YoY +55.9%); EPS: 2.38
- **quarterly_summary:** Sales last 3Q: 3132, 3871, 4236 Cr; Net Profit last 3Q: 324, 1279, 445 Cr
- **balance_sheet_summary:** Debt: 397 Cr
- **ratios_summary:** ROCE: 36%; EPS: 2.38; NPM: 21.49%

### LLOYDSENGG
- **pnl_summary:** Sales: 1038 Cr (YoY +22.7%); NetProfit: 171 Cr (YoY +62.9%); EPS: 1.28
- **quarterly_summary:** Sales last 3Q: 217, 317, 272 Cr; Net Profit last 3Q: 30, 54, 67 Cr
- **balance_sheet_summary:** Debt: 189 Cr
- **ratios_summary:** ROCE: 23%; EPS: 1.28; NPM: 16.47%

### EMCURE
- **pnl_summary:** Sales: 8850 Cr (YoY +12.1%); NetProfit: 895 Cr (YoY +26.6%); EPS: 45.89
- **quarterly_summary:** Sales last 3Q: 2101, 2270, 2363 Cr; Net Profit last 3Q: 215, 251, 231 Cr
- **balance_sheet_summary:** Debt: 1659 Cr
- **ratios_summary:** ROCE: 14%; EPS: 45.89; NPM: 10.11%

### RATNAMANI
- **pnl_summary:** Sales: 5124 Cr (YoY -1.2%); NetProfit: 622 Cr (YoY +14.8%); EPS: 83.46
- **quarterly_summary:** Sales last 3Q: 1152, 1192, 1066 Cr; Net Profit last 3Q: 127, 156, 135 Cr
- **balance_sheet_summary:** Debt: 241 Cr
- **ratios_summary:** ROCE: 22%; EPS: 83.46; NPM: 12.14%

### AHLUCONT
- **pnl_summary:** Sales: 4459 Cr (YoY +8.8%); NetProfit: 267 Cr (YoY +32.2%); EPS: 39.88
- **quarterly_summary:** Sales last 3Q: 1005, 1177, 1061 Cr; Net Profit last 3Q: 51, 79, 54 Cr
- **balance_sheet_summary:** Debt: 75 Cr
- **ratios_summary:** ROCE: 18%; EPS: 39.88; NPM: 5.99%

### FINEORG
- **pnl_summary:** Sales: 2347 Cr (YoY +3.4%); NetProfit: 397 Cr (YoY -3.2%); EPS: 129.38
- **quarterly_summary:** Sales last 3Q: 588, 597, 555 Cr; Net Profit last 3Q: 117, 109, 74 Cr
- **balance_sheet_summary:** Debt: 16 Cr
- **ratios_summary:** ROCE: 26%; EPS: 129.38; NPM: 16.92%

### RENUKA
- **pnl_summary:** Sales: 9398 Cr (YoY -13.8%); NetProfit: -578 Cr (YoY -92.7%); EPS: -2.72
- **quarterly_summary:** Sales last 3Q: 2010, 2423, 2273 Cr; Net Profit last 3Q: -264, -369, -38 Cr
- **balance_sheet_summary:** Debt: 6266 Cr
- **ratios_summary:** ROCE: 10%; EPS: -2.72; NPM: -6.15%

### GRWRHITECH
- **pnl_summary:** Sales: 2071 Cr (YoY -1.8%); NetProfit: 308 Cr (YoY -6.9%); EPS: 132.5
- **quarterly_summary:** Sales last 3Q: 495, 570, 459 Cr; Net Profit last 3Q: 83, 91, 56 Cr
- **balance_sheet_summary:** Debt: 18 Cr
- **ratios_summary:** ROCE: 21%; EPS: 132.5; NPM: 14.87%

### ZFCVINDIA
- **pnl_summary:** Sales: 3976 Cr (YoY +3.8%); NetProfit: 498 Cr (YoY +8%); EPS: 262.32
- **quarterly_summary:** Sales last 3Q: 976, 913, 1075 Cr; Net Profit last 3Q: 122, 108, 140 Cr
- **balance_sheet_summary:** Debt: 62 Cr
- **ratios_summary:** ROCE: 20%; EPS: 262.32; NPM: 12.53%

### ATUL
- **pnl_summary:** Sales: 6055 Cr (YoY +8.5%); NetProfit: 608 Cr (YoY +21.8%); EPS: 201.85
- **quarterly_summary:** Sales last 3Q: 1478, 1552, 1574 Cr; Net Profit last 3Q: 132, 182, 164 Cr
- **balance_sheet_summary:** Debt: 186 Cr
- **ratios_summary:** ROCE: 12%; EPS: 201.85; NPM: 10.04%

### PRUDENT
- **pnl_summary:** Sales: 1240 Cr (YoY +9.4%); NetProfit: 215 Cr (YoY +9.7%); EPS: 51.86
- **quarterly_summary:** Sales last 3Q: 294, 320, 343 Cr; Net Profit last 3Q: 52, 54, 58 Cr
- **balance_sheet_summary:** Debt: 32 Cr
- **ratios_summary:** ROCE: 45%; EPS: 51.86; NPM: 17.34%

### IFCI
- **pnl_summary:** Revenue: 2012 Cr (YoY +7.1%); NetProfit: 661 Cr (YoY +89.4%); EPS: 1.46
- **quarterly_summary:** Sales last 3Q: 407, 735, 456 Cr; Net Profit last 3Q: 62, 317, 21 Cr
- **balance_sheet_summary:** nan
- **ratios_summary:** ROE: 3%; EPS: 1.46; NPM: 32.85%

### HONAUT
- **pnl_summary:** Sales: 4616 Cr (YoY +10.2%); NetProfit: 505 Cr (YoY -3.6%); EPS: 571.4
- **quarterly_summary:** Sales last 3Q: 1183, 1149, 1169 Cr; Net Profit last 3Q: 125, 120, 121 Cr
- **balance_sheet_summary:** Debt: 93 Cr
- **ratios_summary:** ROCE: 18%; EPS: 571.4; NPM: 10.94%

### CARBORUNIV
- **pnl_summary:** Sales: 5025 Cr (YoY +2.7%); NetProfit: 238 Cr (YoY -20.4%); EPS: 12.68
- **quarterly_summary:** Sales last 3Q: 1219, 1298, 1291 Cr; Net Profit last 3Q: 60, 74, 73 Cr
- **balance_sheet_summary:** Debt: 308 Cr
- **ratios_summary:** ROCE: 18%; EPS: 12.68; NPM: 4.74%

### MEDPLUS
- **pnl_summary:** Sales: 6538 Cr (YoY +6.6%); NetProfit: 207 Cr (YoY +38%); EPS: 17.28
- **quarterly_summary:** Sales last 3Q: 1543, 1679, 1806 Cr; Net Profit last 3Q: 42, 56, 58 Cr
- **balance_sheet_summary:** Debt: 1193 Cr
- **ratios_summary:** ROCE: 5%; EPS: 17.28; NPM: 3.17%

### CENTURYPLY
- **pnl_summary:** Sales: 5103 Cr (YoY +12.7%); NetProfit: 242 Cr (YoY +30.1%); EPS: 10.66
- **quarterly_summary:** Sales last 3Q: 1169, 1386, 1350 Cr; Net Profit last 3Q: 53, 71, 65 Cr
- **balance_sheet_summary:** Debt: 1643 Cr
- **ratios_summary:** ROCE: 15%; EPS: 10.66; NPM: 4.74%

### NSLNISP
- **pnl_summary:** Sales: 12601 Cr (YoY +48.2%); NetProfit: -807 Cr (YoY +66%); EPS: -2.75
- **quarterly_summary:** Sales last 3Q: 3365, 3390, 3008 Cr; Net Profit last 3Q: 26, -115, -244 Cr
- **balance_sheet_summary:** Debt: 5310 Cr
- **ratios_summary:** ROCE: -13%; EPS: -2.75; NPM: -6.4%

### NHPC
- **pnl_summary:** Sales: 11147 Cr (YoY +7.4%); NetProfit: 3591 Cr (YoY +5.2%); EPS: 3.15
- **quarterly_summary:** Sales last 3Q: 3214, 3365, 2221 Cr; Net Profit last 3Q: 1131, 1219, 321 Cr
- **balance_sheet_summary:** Debt: 44923 Cr
- **ratios_summary:** ROCE: 7%; EPS: 3.15; NPM: 32.21%

### POWERMECH
- **pnl_summary:** Sales: 5804 Cr (YoY +10.9%); NetProfit: 388 Cr (YoY +11.5%); EPS: 107.12
- **quarterly_summary:** Sales last 3Q: 1293, 1238, 1420 Cr; Net Profit last 3Q: 81, 78, 100 Cr
- **balance_sheet_summary:** Debt: 960 Cr
- **ratios_summary:** ROCE: 21%; EPS: 107.12; NPM: 6.69%
