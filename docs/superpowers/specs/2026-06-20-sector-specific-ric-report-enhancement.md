# Sector-Specific RIC Report Enhancement

## Objective

Upgrade focused Agent Adda sector reports from rotation-only extracts into publishable sector intelligence reports with company-level RIC evidence.

## Current State

The focused `/report sector <sector> <format>` flow extracts a requested sector from the latest sector rotation markdown and wraps it in the Agent Adda report shell. This works for:

- Sector rank and leadership context.
- Candidate map.
- Technical notes.
- Peak-resilience names.
- Editor opinion.
- Methodology and source trail.

It does not yet collect stock-by-stock evidence beyond the sector rotation output.

## Required Enhancements

1. Add a sector thesis section.
   - Sector business model and demand drivers.
   - Policy, capex, order-cycle, export, commodity, or regulatory drivers.
   - Structural versus tactical setup.
   - Thesis invalidation.

2. Add company profile cards for top candidates.
   - Symbol, company name, sector fit, business description.
   - Market-cap/liquidity/F&O note where available.
   - Technical setup, key levels, stage, signal, relative strength.
   - Fundamental snapshot and evidence status.

3. Add a company-level RIC evidence matrix.
   - Technical.
   - Latest results/fundamentals.
   - News/events/announcements.
   - Forensic/governance.
   - Investor call or presentation insights.
   - Liquidity/F&O where relevant.

4. Add latest results impact.
   - Revenue/sales, operating profit or EBITDA, PAT/net profit, EPS, margin direction.
   - YoY/QoQ direction where available.
   - Result quality and missing evidence.

5. Add news and announcement impact.
   - Dated NSE/BSE filings and credible news.
   - Order wins, credit ratings, board actions, investor meets, policy events, governance events.
   - Positive/negative/mixed/neutral impact with rationale and confidence.

6. Add forensic and quality evidence.
   - Debt, cash conversion, working capital, receivables/inventory, pledge, auditor/governance flags.
   - Existing Agent Adda forensic outputs where available.

7. Add investor-call or presentation insights.
   - Order book, guidance, execution, capex/capacity, margin drivers, risk language.
   - Management tone and what changed.

8. Add stock-level verdicts.
   - Research long watch, breakout watch, retest watch, avoid/repair, or missing-evidence watch.
   - Bull case, bear case, invalidation, and what would change the view.

## Implementation Plan

1. Extend the focused sector command parser to support `deep` or `ric`.
2. Add parameters for `--max-companies`, `--lookback-days`, and `--no-web`.
3. In `terminal.reports._build_sector_specific_content()`, keep the current rotation extraction as the base layer.
4. Build an enrichment collector for the top N candidates using existing project capabilities:
   - Screener/fundamentals.
   - Latest results.
   - NSE/BSE announcements.
   - Forensic analysis.
   - Investor-call or presentation search.
   - Sector context and technical setup.
5. Render the enriched markdown sections after the candidate map.
6. Preserve the existing Agent Adda HTML shell and add cards/tables for the enriched sections.
7. Add tests for:
   - `deep` command parsing.
   - Enrichment collector partial-failure behavior.
   - Required section headings.
   - Missing evidence labels.
   - No internal PG/schema wording in reader-facing output.

## Acceptance Criteria

- `/report sector NIFTY DEFENCE deep html` produces a focused sector report with RIC-enriched company evidence.
- The report still works when one or more evidence branches fail; missing evidence is visible per company.
- No company receives an actionable verdict from only one evidence branch.
- HTML, Markdown, and latest artifact copies are generated.
- Existing sector rotation tests continue to pass.
