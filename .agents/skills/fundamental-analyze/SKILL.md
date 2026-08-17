---
name: fundamental-analyze
description: Research and value a listed company using the newest company filings, investor materials, exchange disclosures, Screener history, and current market data. Use for fundamental analysis, investment theses, earnings updates, financial-quality reviews, valuation scenarios, fair-value ranges, or requests to compare reported and normalized performance.
---

# Fundamental Analyze

Produce an evidence-led, reproducible company analysis. Treat the bundled CLI as the calculator and renderer; do not treat it as a source of financial facts.

## Workflow

1. Resolve the exact company, exchange, symbol, reporting currency, fiscal year-end, and consolidated versus standalone scope. Default to consolidated results.
2. Establish an explicit as-of date. Search for the newest filing available on that date before using aggregators.
3. Collect evidence in this order, using the repository helpers in [references/tool-integrations.md](references/tool-integrations.md) rather than inventing figures:
   - exchange filing or company investor-relations document (`search_nse_announcements`);
   - audited annual report and latest quarterly result/presentation/transcript;
   - credit-rating rationale or regulator filing;
   - Screener for normalized history, ratios, shareholding, and cross-checking (`scrape_screener_in`);
   - current price from `get_symbol_snapshot` or the NSE quote page;
   - reputable secondary reporting only for context.
4. Record source title, direct URL, publication/reporting date, source tier, and the facts it supports. Never cite a search-results page.
5. Reconcile units, fiscal periods, restatements, consolidated scope, exceptional items, and diluted share count. State unresolved conflicts instead of silently choosing a value.
6. Create an input JSON file following [references/input-schema.md](references/input-schema.md). Use null for unknown values; never invent a value to satisfy the tool.
7. Run:

   ```bash
   python3 .agents/skills/fundamental-analyze/scripts/fundamental_analyzer.py INPUT.json --format markdown --output REPORT.md
   ```

   From Claude's compatibility wrapper, use the same repository-root command. For a machine-readable result, select `--format json`. For a portable report with embedded styling, select `--format html --output REPORT.html`.
8. Review the generated calculations against source documents. Add qualitative material that cannot be computed: moat, industry structure, management execution, capital allocation, governance, catalysts, and key monitorables.
9. Deliver the conclusion first via `qualitative.verdict`: business quality, financial quality, growth durability, valuation comfort, and stance. Clearly separate reported facts, calculations, management claims, and analyst assumptions.

## Required analytical standards

- Show at least three full fiscal years and the latest quarter when available.
- Calculate revenue, operating-profit, PAT and EPS growth; margins; ROE/ROCE; leverage; cash conversion; and free-cash-flow conversion when inputs permit.
- Normalize material exceptional income/expense. Show both reported and normalized earnings.
- Use at least three valuation scenarios. Each scenario must expose the earnings assumption, valuation multiple or DCF assumptions, implied value, and upside/downside from the as-of price.
- Do not call a price “intrinsic value” when it is only a P/E scenario. Call it an implied value or fair-value range.
- Discuss downside before upside. Include cyclicality, customer/geography concentration, working capital, dilution, related parties, pledging, capitalized costs, contingent liabilities, and auditor qualifications when relevant.
- Flag stale market prices and filings. Never describe data as “latest” without an as-of date.
- End with a research-only disclaimer; do not personalize a buy/sell recommendation.

## Output order

1. Snapshot and as-of date
2. Thesis and verdict
3. Historical financial table
4. Latest-quarter update
5. Balance sheet, cash flow, and capital allocation
6. Business model and moat
7. Growth drivers and catalysts
8. Risks, governance, and shareholding
9. Valuation scenarios and margin of safety
10. Monitorables, source list, and disclaimer

## Resources

- Read [references/input-schema.md](references/input-schema.md) before preparing tool input.
- Read [references/institutional-analysis.md](references/institutional-analysis.md) when the user asks for deep research, peer/segment/shareholding detail, or a shareable report.
- Read [references/tool-integrations.md](references/tool-integrations.md) before gathering filings, Screener history, or prices, and when configuring Agent Adda, Cursor, Claude, or Copilot.
- Run `scripts/fundamental_analyzer.py` for validation, calculations, scenarios, and report rendering.
