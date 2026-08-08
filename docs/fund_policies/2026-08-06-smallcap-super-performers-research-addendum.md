# Smallcap Super Performers Research Addendum 001

Date: 2026-08-06
Status: Research addendum to the Smallcap Super Performers Portfolio policy
Applies to: `docs/fund_policies/2026-08-06-smallcap-super-performers-fund-policy.md`
Corpus reference: Rs. 5,00,000 maximum paper capital
Current posture: Research-first, no forced deployment

## 1. Purpose

This addendum converts the recent Smallcap Super Performers research into a portfolio-ready preselection board. It does not replace the policy. It narrows the research universe into decision tiers, identifies blockers, and defines the next work needed before any paper trade can be created.

The main conclusion is clear: the recent research produced a useful watchlist, but it did not produce an immediate broad buy list. The portfolio should remain in Phase 0 or early Phase 1 until result freshness, filing/news checks, liquidity checks, and technical triggers are completed stock by stock.

## 2. Evidence Used

Local research artifacts used:

- `docs/fund_policies/evidence_packs/2026-08-06-rainbow-evidence-pack.md`
- `docs/fund_policies/refresh_queues/2026-08-06-shortlist-refresh-queue.md`
- `Mutual Funds/reports/agent_adda_smallcap_phase1_evidence_packs_20260806.html`
- `Mutual Funds/extracted/agent_adda_smallcap_phase1_evidence_packs_20260806.csv`
- `Mutual Funds/extracted/agent_adda_smallcap_preselection_scores_20260806.csv`
- `Mutual Funds/extracted/agent_adda_smallcap_policy_gate_20260806.csv`
- `Mutual Funds/reports/agent_adda_smallcap_preselection_scored_report_20260806.html`
- `reports/latest/agent_adda_smallcap_super_performers.html`
- `reports/latest/kotak_vs_agent_adda_smallcap_positioning.html`
- `reports/latest/kotak_vs_agent_adda_smallcap_stage2_overlap.csv`
- `reports/research/micro_cap_super_performers_20260804.md`
- `Mutual Funds/README.md`

Source timing:

- Preselection scored report generated: 2026-08-06 19:02 IST.
- Preselection universe: 30 Agent Adda plus sampled small-cap mutual-fund overlap stocks.
- Technical snapshot date: 2026-08-06.
- Small/micro-cap screen generated: 2026-08-06 16:56 IST.
- Micro-cap screen snapshot: local `scores.stage_snapshots` as of 2026-08-03.

## 3. Research Stack Summary

### 3.1 Broad Small/Micro-Cap Screen

The broad local small/micro-cap report screened 502 unique names from the Smallcap 50/100/250 and Microcap 250 universe. It found 109 Stage 2 candidates and 44 BUY flags, but the desk stance remained `WAIT`, with no fresh executable trade from the intraday monitor. This supports watchlist preparation and retest discipline rather than broad chasing.

Sector concentration among Stage 2 names was highest in:

- Capital Goods: 18 Stage 2 names.
- Healthcare: 16 Stage 2 names.
- Financial Services: 12 Stage 2 names.
- Automobile and Auto Components: 11 Stage 2 names.
- Chemicals: 10 Stage 2 names.

Portfolio implication: initial portfolio themes should prioritize capex/capital goods, healthcare, financial platforms, auto ancillaries, and chemicals, but stock-level gates still control allocation.

### 3.2 Mutual-Fund Overlap Research

The Kotak overlap comparison used Kotak small-cap holdings from 2025-02-28 and compared them with the 2026-08-06 Agent Adda small/micro-cap screen. It found:

- 293 Kotak unique holdings across the active Small Cap, Smallcap 50 Index, and Smallcap 250 Index funds.
- 42 Kotak-held names that also appeared in the Agent Adda Stage 2 screen.
- 6 active Kotak Small Cap Fund overlaps in current Stage 2.
- 11 best-balanced watch names.

Portfolio implication: mutual-fund overlap is a validation signal, not a buy signal. It helps prioritize research, but it does not override entry quality, result freshness, technical extension, liquidity, or governance checks.

### 3.3 Preselection Scorecard

The newest preselection model scored 30 overlap stocks using:

- Institutional score out of 25.
- Technical score out of 30.
- Fundamental score out of 30.
- Entry-risk score out of 15.
- Total selection score out of 100.

Decision-bucket result:

| Decision Bucket | Count | Average Score | Stage 2 Count | Fresh Result Count | Symbols |
|---|---:|---:|---:|---:|---|
| Selection Review - Phased Candidate | 2 | 72.8 | 2 | 2 | RAINBOW, KARURVYSYA |
| Shortlist - Refresh Results | 6 | 71.8 | 6 | 1 | RUBICON, GLAND, SANSERA, SKYGOLD, CPPLUS, RRKABEL |
| Watch - Retest / Verify | 18 | 62.8 | 18 | 11 | VMART, WABAG, SYRMA, NETWEB, SHAILY, JAMNAAUTO, MINDACORP, KIRLOSBROS, SONACOMS, WEWORK, GABRIEL, WELCORP, AEGISVOPAK, SUDARSCHEM, FIVESTAR, BALRAMCHIN, VARROC, PRICOLLTD |
| Reject / No Fresh Buy | 1 | 59.0 | 0 | 1 | SFL |
| Hold / Reject | 3 | 53.9 | 3 | 0 | AVL, GOKEX, MANAPPURAM |

There were no `Selection Review - Core Candidate` names in the current preselection run.

Policy-gate overlay:

The later policy-gate run is a stricter trade-construction overlay, not the same as the preselection decision bucket. It produced a Phase 1 evidence-pack HTML report with:

- Clean trigger-map names: SYRMA, AEGISVOPAK, KARURVYSYA, VMART, FIVESTAR.
- Retest-only trigger-map names: SONACOMS, NETWEB, WELCORP, RAINBOW, WEWORK.

These are not paper orders. They are trigger maps that still require governance/filing review, source reconciliation, and live trigger confirmation.

## 4. Current Candidate Tiers

### 4.1 Tier 1 - Phased Candidate

RAINBOW and KARURVYSYA are the current `Selection Review - Phased Candidate` names. RAINBOW was taken first because it had the cleanest healthcare-services fit for the initial focused markdown evidence pack.

| Symbol | Company | Sector | Score | MF Count | Stage | Signal | RSI | Freshness | Action |
|---|---|---|---:|---:|---|---|---:|---|---|
| RAINBOW | Rainbow Childrens Medicare Limited | Healthcare Services | 74.2 | 2 | STAGE_2 | HOLD | 66.5 | Fresh Jun 2026 result | Final filing/news check, then trigger map |
| KARURVYSYA | Karur Vysya Bank Limited | Banks | 71.5 | 2 | STAGE_2 | HOLD | 68.3 | Fresh Jun 2026 result | Build bank-specific asset-quality and liquidity evidence pack |

Interpretation:

- RAINBOW has the best current combination of healthcare theme fit, institutional overlap, fresh result evidence, Stage 2 trend, and non-extended RSI.
- KARURVYSYA is also eligible for evidence-pack work, but it needs bank-specific asset-quality, NIM, credit-cost, CASA, slippage, and liquidity checks.
- Neither name is an automatic paper buy because both current signals are HOLD, not BUY.
- The correct action is to build a full evidence pack and define the entry trigger, stop, and position size.

Provisional paper portfolio handling:

- Eligible for first review slot.
- Maximum initial paper entry: Rs. 15,000 to Rs. 20,000.
- Risk budget: 0.50% to 0.75% of NAV, depending on stop distance.
- No entry unless reward/risk is at least 2:1 after slippage and the trigger confirms.

### 4.2 Tier 2 - Shortlist, Refresh Results

These names scored well enough for shortlist review, but most require Q1 FY27 result or filing/news refresh before capital.

| Symbol | Company | Sector | Score | Stage / Signal | RSI | MF Count | Key Blocker |
|---|---|---|---:|---|---:|---:|---|
| RUBICON | Rubicon Research Limited | Pharmaceuticals & Biotechnology | 74.3 | STAGE_2 / BUY | 61.2 | 1 | Fundamental refresh pending |
| GLAND | Gland Pharma Limited | Pharmaceuticals & Biotechnology | 73.6 | STAGE_2 / BUY | 65.1 | 1 | Fundamental refresh pending |
| SANSERA | Sansera Engineering Ltd. | Auto Components | 73.3 | STAGE_2 / HOLD | 76.8 | 2 | Extended RSI and fundamental refresh pending |
| SKYGOLD | Sky Gold And Diamonds Limited | Consumer Durables | 70.3 | STAGE_2 / BUY | 66.0 | 1 | Fundamental refresh pending |
| CPPLUS | Aditya Infotech Limited | IT - Software | 70.0 | STAGE_2 / BUY | 51.9 | 1 | Fundamental refresh pending |
| RRKABEL | R R KABEL LTD | Industrial Products | 69.0 | STAGE_2 / HOLD | 85.0 | 2 | Extended RSI and provisional setup sample |

Portfolio interpretation:

- RUBICON, GLAND, SKYGOLD, and CPPLUS have better entry-shape potential because RSI is not extremely extended and current signal is BUY.
- SANSERA and RRKABEL have stronger institutional overlap but are extended; they are retest candidates, not chase candidates.
- RRKABEL has fresh Jun 2026 result evidence, but RSI extension and provisional setup sample still block immediate promotion.

Required work before paper entry:

- Refresh latest exchange filings, quarterly results, investor presentation/concall, and recent news.
- Confirm current price, stop zone, liquidity, and gap risk.
- Reject if the refreshed result shows weak quality, one-off growth, governance risk, or poor cash conversion.
- Convert only the cleanest names into Phase 1 trigger cards.

### 4.3 Tier 3 - Watch, Retest, Or Verify

These names are strong enough for watchlist inclusion but not for current paper allocation.

| Symbol | Sector | Score | Current State | Main Reason To Wait |
|---|---|---:|---|---|
| WABAG | Other Utilities | 67.4 | Stage 2 HOLD | Fundamental refresh pending |
| SYRMA | Industrial Manufacturing | 66.9 | Stage 2 HOLD | Fundamental refresh pending; provisional setup sample |
| NETWEB | Technology Hardware & Equipment | 66.2 | Stage 2 HOLD | Retest-only policy gate; fundamental score still weak |
| SHAILY | Industrial Products | 64.9 | Stage 2 BUY | RSI 94.1, too extended |
| JAMNAAUTO | Auto Components | 64.4 | Stage 2 HOLD | Fundamental refresh pending |
| MINDACORP | Auto Components | 63.7 | Stage 2 HOLD | Fundamental refresh pending; provisional setup sample |
| WEWORK | Commercial Services & Supplies | 62.9 | Stage 2 BUY | Fundamental refresh pending |
| VMART | Retailing | 61.7 | Stage 2 HOLD | Clean trigger-map eligible, but needs governance/source review |
| AEGISVOPAK | Oil | 61.7 | Stage 2 HOLD | Clean trigger-map eligible, but weak policy score and provisional setup sample |
| KIRLOSBROS | Industrial Products | 61.3 | Stage 2 BUY | Fundamental refresh pending; weak policy score; provisional setup sample |
| WELCORP | Industrial Products | 60.7 | Stage 2 HOLD | Extended RSI |
| SUDARSCHEM | Chemicals & Petrochemicals | 60.5 | Stage 2 HOLD | Fundamental refresh pending |
| FIVESTAR | Finance | 60.4 | Stage 2 HOLD | Clean trigger-map eligible, but NBFC asset-quality/governance and weak RS need review |

Portfolio interpretation:

- This tier is the main source for the 15-25 stock research bench.
- The portfolio should not allocate capital to this tier until the specific blocker is cleared.
- Stocks with no financial cache need identity and financial-source repair before any quality judgment.
- Stocks with RSI above 75 need retest, base, or moving-average support before entry.

### 4.4 Tier 4 - Reject, Hold, Or Rebuild

| Symbol | Decision | Reason |
|---|---|---|
| SFL | Reject / No Fresh Buy | Current Stage 1 and fresh price shock; revisit only after Stage 2 rebuild |
| GOKEX | Hold / Reject | Fundamental refresh pending and weak fundamental score |
| AVL | Hold / Reject | Weak fundamental score |
| MANAPPURAM | Hold / Reject | Extended RSI, fundamental refresh pending, weak fundamental score |

Portfolio interpretation:

- This tier should not receive paper capital now.
- SFL is a useful example of why the policy must be dynamic: earlier local overlap work treated it as a cleaner active mutual-fund overlap, but the latest preselection snapshot moved it out because the current trend/base gate failed.
- NETWEB also shows why a strong technical score is insufficient when the financial cache or fundamental score is weak.

## 5. Micro-Cap Super Performer Carry-Forward

The 2026-08-04 micro-cap screen remains useful as a separate bottom-up research channel. Its top super performers were:

| Symbol | Market Cap Cr | Score | Stage | 3M | 6M | Quality | Tech | Avg Turnover Cr | Action |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| SOTL | 4,147 | 68.3 | STAGE_2 | 50.0% | 118.7% | 62.5 | 69.8 | 36.11 | Build evidence pack |
| TINNARUBR | 1,706 | 67.8 | STAGE_2 | 37.7% | 106.5% | 68.0 | 60.7 | 35.61 | Build evidence pack |
| SILVERTUC | 2,516 | 66.3 | STAGE_2 | 11.7% | 90.2% | 74.4 | 66.9 | 12.39 | Build evidence pack |

These names did not come through the same mutual-fund overlap preselection stack, so they should be treated as pure bottom-up super performer candidates. They need updated price, financial, governance, liquidity, and trigger checks before they compete with the mutual-fund overlap shortlist.

## 6. Portfolio Action Plan

### 6.1 Immediate Work

Build or refresh full evidence packs for:

1. RAINBOW - first evidence pack created at `docs/fund_policies/evidence_packs/2026-08-06-rainbow-evidence-pack.md`
2. SYRMA - clean trigger-map candidate, but valuation/governance must clear
3. AEGISVOPAK - clean trigger-map candidate, but weak policy score/provisional setup require caution
4. KARURVYSYA - clean trigger-map candidate and phased candidate; requires bank-specific pack
5. VMART - clean trigger-map candidate; needs governance/source review
6. FIVESTAR - clean trigger-map candidate; needs NBFC asset-quality and governance review
7. GLAND - priority refresh now; official FY27 Q1 materials visible
8. RUBICON - direct exchange search plus retest review
9. SKYGOLD - result refresh plus cash-conversion review
10. CPPLUS - wait for result and resolve bearish Supertrend conflict
11. SANSERA
12. RRKABEL
13. SOTL
14. TINNARUBR
15. SILVERTUC

Each pack must include:

- Identity and symbol validation.
- Business model summary.
- Latest result and filing/news check.
- Sales, PAT, EPS, margin, ROCE/ROE, leverage, and cash conversion.
- Management and governance check.
- Liquidity and circuit-risk check.
- Technical setup: stage, moving averages, RS, RSI, support, resistance, volume.
- Entry trigger, stop, target, and reward/risk.
- Rs. 5,00,000 corpus position-size calculation.
- Reject/hold/buy-watch decision.

### 6.2 Paper Entry Gate

A stock can move from research to paper order only when all are true:

- Decision bucket is `Selection Review - Phased Candidate` or upgraded after refresh.
- Current stage is STAGE_2.
- Current signal is BUY or a defined retest trigger fires.
- RSI is preferably 50-70, or a retest neutralizes extension risk.
- Latest result and filing/news checks are complete.
- Fundamental score is not weak.
- Liquidity cap passes.
- Stop is within 12% of entry.
- Reward/risk is at least 2:1.
- Sector cap, position cap, and open-risk cap pass.

### 6.3 Phase 1 Portfolio Construction

With Rs. 5,00,000 paper capital, Phase 1 should not exceed Rs. 2,00,000 deployed exposure.

Recommended Phase 1 shape:

- 4-6 initial positions maximum.
- Rs. 15,000 to Rs. 20,000 initial paper entry per position.
- Maximum Rs. 35,000 to Rs. 40,000 after successful add.
- Single-stock hard cap Rs. 50,000.
- Sector cap Rs. 1,25,000.
- Risk per new trade Rs. 2,500 to Rs. 3,750.
- Total open risk cap Rs. 30,000.

No position should start at full size. The first paper entries are meant to test process quality, not maximize early exposure.

## 7. Strategy Implication

The current research supports a `smallcap_super_performers_v1` strategy variant, but only as a design and backtest candidate until evidence packs are complete.

Draft strategy definition:

- Universe: 30-stock preselection board plus micro-cap super performer carry-forward.
- Entry: Stage 2, BUY or retest trigger, RSI 50-70 preferred, price above key moving averages, relative strength improving.
- Confirmation: volume expansion or retest hold, sector breadth positive, no unresolved filing/result gap.
- Fundamental gate: latest result refreshed, no weak policy score, no critical governance issue.
- Stop: structure stop or 2 ATR, maximum 12% from entry.
- Sizing: true stop-risk sizing with 0.50-0.75% NAV risk per entry.
- Max position: 8% normal full size, 10% hard cap.
- Exit: stop hit, close below 50DMA with distribution, Stage 3/4 deterioration, RS failure, or thesis break.
- No-trade: WAIT market stance, stale results, RSI extension without retest, weak liquidity, weak fundamental score, or no logical stop.

This variant should be backtested separately against:

- `momentum_rotation_v1`
- `darvas_box_breakout_v1`
- `stage2_continuation_v1`
- Nifty Smallcap 250 TRI
- Nifty 500 TRI

## 8. Decision For Now

Current portfolio decision: `WAIT / PREPARE`.

Do not deploy broadly. Build the evidence packs, upgrade or reject candidates after refresh, and then run a Phase 1 paper portfolio with small initial sizes only when technical triggers appear.

Research only. Not investment advice. Not a recommendation to buy, sell, or hold any security.
