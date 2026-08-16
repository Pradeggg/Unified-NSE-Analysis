# Agent Adda Midcap Leaders Portfolio Research Update

Date: 2026-08-10
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
- Core candidates: 0
- Refresh first: 0
- Bucket counts: {'WATCH / PREPARE': 12, 'RETEST ONLY': 3}
- Paper order allowed: NO. Technical scores are current to 2026-08-07 (via PostgreSQL daily_scores). Fundamental sub-scores (EQ/SG/FS) are sourced from v_latest_fundamental_scores which aggregates the latest per-symbol filings. Individual Q1 FY27 result verification on exchange filings is still required before any paper order can be raised.

## Top Candidates

| Symbol | Score | Bucket | Sector | Gov Theme | Stage | Growth | EPS | Sales | Blockers |
|---|---|---|---|---|---|---|---|---|---|
| OFSS | 76.1 | WATCH / PREPARE | IT / Digital | Digital infrastructure | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| COFORGE | 75.9 | RETEST ONLY | IT / Digital | Digital infrastructure | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; EXTENDED_RSI_RETEST_ONLY |
| NYKAA | 73.6 | WATCH / PREPARE | IT / Digital | Digital infrastructure | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| LLOYDSME | 73.2 | WATCH / PREPARE | Metals | No direct government-investment tag | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_GOVERNMENT_INVESTMENT_CONFIRMATION |
| KALYANKJIL | 72.2 | WATCH / PREPARE | Consumer Durables | No direct government-investment tag | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_GOVERNMENT_INVESTMENT_CONFIRMATION |
| GODREJPROP | 70.5 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| SONACOMS | 70.5 | WATCH / PREPARE | Auto / Auto Components | EV and mobility | STAGE_1 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_STAGE2_CONFIRMATION |
| PRESTIGE | 67.3 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| AUROPHARMA | 66.7 | WATCH / PREPARE | Healthcare | Manufacturing / PLI | STAGE_1 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_STAGE2_CONFIRMATION |
| OBEROIRLTY | 66.6 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_2 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED |
| TATATECH | 66.0 | RETEST ONLY | EV / Mobility | EV and mobility | STAGE_2 | WATCH | WATCH | PASS | FUNDAMENTAL_REFRESH_REQUIRED; EXTENDED_RSI_RETEST_ONLY |
| BHARATFORG | 65.0 | WATCH / PREPARE | Auto / Auto Components | EV and mobility | STAGE_1 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_STAGE2_CONFIRMATION |
| FEDERALBNK | 64.7 | WATCH / PREPARE | Banks | Housing and urban infra | STAGE_2 | WATCH | PASS | WATCH | FUNDAMENTAL_REFRESH_REQUIRED |
| POLYCAB | 64.2 | WATCH / PREPARE | Housing | Housing and urban infra | STAGE_1 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_STAGE2_CONFIRMATION |
| HEROMOTOCO | 64.0 | RETEST ONLY | Auto / Auto Components | EV and mobility | STAGE_1 | PASS | PASS | PASS | FUNDAMENTAL_REFRESH_REQUIRED; NO_STAGE2_CONFIRMATION; EXTENDED_RSI_RETEST_ONLY |

## Source Trail

- Score source: `reports/generated_csv/2026/comprehensive_nse_enhanced_20260807.csv`.
- Universe source: `data/index_stock_mapping.csv`.
- Government-investment source trail: Union Budget 2026-27 highlights: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2221455; Budget speech: https://www.indiabudget.gov.in/doc/budget_speech.pdf; Capital goods/public capex: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2222521; Infrastructure: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2270740; Defence budget: https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2221612.
- Official result/filing refresh is still required before any paper order.
