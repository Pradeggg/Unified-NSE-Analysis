# Agent Adda Midcap Leaders Portfolio Research Update

Date: 2026-08-27
Status: Research preselection. No paper order is approved.
Universe: Nifty Midcap 50, Midcap 100, Midcap 150, Midcap Select, with LargeMidcap/Nifty 500 confirmation tags.

## Mandate Filters

- Stage 2 structure or proxy confirmation.
- Growth score and high EPS/earnings-quality proxy.
- YoY sales-growth score.
- Sector theme.
- Government-investment theme alignment.
- Liquidity and no-chase controls.

## Current State

- Symbols scored: 15
- Core candidates: 3
- Refresh first: 0
- Bucket counts: {'CORE CANDIDATE': 3, 'WATCH / PREPARE': 11, 'RETEST ONLY': 1}
- Paper order allowed: NO. Technical scores are current to 2026-08-07 (via PostgreSQL daily_scores). Fundamental sub-scores (EQ/SG/FS) are sourced from v_latest_fundamental_scores which aggregates the latest per-symbol filings. Individual Q1 FY27 result verification on exchange filings is still required before any paper order can be raised.

## Top Candidates

| Symbol | Score | Bucket | Sector | Gov Theme | Stage | Growth | EPS | Sales | Blockers |
|---|---|---|---|---|---|---|---|---|---|
| OFSS | 84.1 | CORE CANDIDATE | IT / Digital | Digital infrastructure | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| SONACOMS | 82.7 | CORE CANDIDATE | Auto / Auto Components | EV and mobility | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| NYKAA | 80.6 | CORE CANDIDATE | IT / Digital | Digital infrastructure | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| OBEROIRLTY | 79.4 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| KEI | 78.8 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| COFORGE | 76.6 | WATCH / PREPARE | IT / Digital | Digital infrastructure | STAGE_2 | WATCH | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| KALYANKJIL | 76.0 | WATCH / PREPARE | Consumer Durables | No direct government-investment tag | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_GOVERNMENT_INVESTMENT_CONFIRMATION |
| PAYTM | 75.8 | RETEST ONLY | Financial Services | Digital infrastructure | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; EXTENDED_RSI_RETEST_ONLY |
| UNOMINDA | 75.1 | WATCH / PREPARE | Auto / Auto Components | EV and mobility | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| MEDANTA | 73.4 | WATCH / PREPARE | Healthcare | No direct government-investment tag | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_GOVERNMENT_INVESTMENT_CONFIRMATION |
| NAM-INDIA | 72.8 | WATCH / PREPARE | Capital Markets | No direct government-investment tag | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_GOVERNMENT_INVESTMENT_CONFIRMATION |
| BHEL | 72.6 | WATCH / PREPARE | Energy | Energy infrastructure | STAGE_2 | WATCH | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| PERSISTENT | 72.5 | WATCH / PREPARE | IT / Digital | Digital infrastructure | STAGE_1 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_STAGE2_CONFIRMATION |
| POLYCAB | 71.3 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_1 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_STAGE2_CONFIRMATION |
| UNIONBANK | 69.9 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |

## Source Trail

- Score source: `reports/generated_csv/2026/comprehensive_nse_enhanced_20260817.csv`.
- Universe source: `data/index_stock_mapping.csv`.
- Government-investment source trail: Union Budget 2026-27 highlights: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2221455; Budget speech: https://www.indiabudget.gov.in/doc/budget_speech.pdf; Capital goods/public capex: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2222521; Infrastructure: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2270740; Defence budget: https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2221612.
- Official result/filing refresh is still required before any paper order.
