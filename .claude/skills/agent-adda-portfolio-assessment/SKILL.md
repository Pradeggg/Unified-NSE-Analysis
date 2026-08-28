---
name: agent-adda-portfolio-assessment
description: Review the latest ICICI Direct equity portfolio CSV and the generated assessment HTML. Use for add/trim/hold/exit rankings, concentration risk, ETF separation, unresolved symbols, and refreshing the sortable portfolio report.
---

# Agent Adda Portfolio Assessment

Use this skill when the user asks to analyze or refresh the latest portfolio download, open the assessment HTML, or rank holdings for cleanup, trims, holds, and add-on-pullback candidates.

## Workflow

1. Find the newest ICICI Direct portfolio CSV in Downloads, usually `8500589913_PortFolioEqtSummary-*.csv`.
2. Rebuild the assessment with:

```bash
cd /Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis
python tools/build_equity_portfolio_assessment.py --portfolio /Users/pradeepgorai/Downloads/8500589913_PortFolioEqtSummary-aug22.csv
```

3. Use the generated files in `reports/portfolio_assessments/`:
   - `*.json` for summary numbers
   - `*.csv` for row-level ranking
   - `*.md` for a text review
   - `*.html` for the visual report
4. Treat ETFs separately from the stock book unless the user explicitly wants ETF analysis.
5. Rank the output in this order:
   - must-sells / cleanup exits
   - trims
   - holds
   - add-on-pullback candidates
   - unresolved / manual-review names

## Reading the report

- Open the HTML directly with the local preview helper:

```bash
python scripts/preview_html_report.py reports/portfolio_assessments/equity_portfolio_assessment_YYYYMMDD.html
```

- If the user says “open it”, open the HTML in the browser and inspect the rendered page.
- If the user says “refresh it”, rebuild first, then reopen the new HTML.

## Evidence order

When explaining a holding, use this order:

1. Position size and cost basis
2. Latest stage / technical snapshot
3. Latest fundamental snapshot and quarterly trend
4. Recent price / P&L context
5. Sector and index context
6. Public research notes, when available

## Guardrails

- Flag concentration risk before recommending new adds.
- Treat stage 4, weak RS, or broken trend as exit evidence.
- Keep unresolved symbols separate from true exit calls.
- Keep the answer research-only. Do not phrase recommendations as personal financial advice.

