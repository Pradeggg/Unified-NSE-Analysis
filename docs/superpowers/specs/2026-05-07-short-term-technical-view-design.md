# Short-Term Technical View Tab Design

## Goal

Add a separate **Short-Term Technical View** tab to the Sector Rotation HTML report. The tab should give a market-first technical read of broader Indian markets and major sector indices using local EOD data, with a comprehensive narrative at the top and charts/tables below it.

The feature is for research and learning only. It must inherit the existing report disclaimer stance and must not create buy/sell recommendations.

## Approved Direction

Use the **Market First** layout:

1. A top narrative summarizing the broader market regime.
2. Compact index cards for the approved basket.
3. Charts that validate the narrative.
4. A signal matrix for fast comparison across indices.

Approved index basket:

- Nifty 50
- Nifty Bank
- Nifty Next 50
- Nifty Midcap 100
- Nifty Smallcap 100
- Nifty IT
- Nifty Pharma
- Nifty Metal
- Nifty Auto
- Nifty FMCG
- Nifty Realty
- Nifty Energy
- Nifty Oil & Gas

## Alternatives Considered

### A. Market First

Narrative first, followed by cards, charts, and matrix. This is the approved approach because it reads like a daily market brief while still showing the evidence.

### B. Index Workbench

Interactive selector with one index at a time. This is richer but better suited for a terminal or dedicated dashboard than a generated report.

### C. Signal Matrix

Compact table first. This is efficient for scanning but too terse for the report’s narrative-first style.

## Data Source

Use the existing local `data/nse_index_data.csv` EOD index history. Do not introduce network fetches for this first version.

The tab should degrade gracefully if one or more index names are missing from the local CSV:

- Exclude missing indices from computed charts.
- Add a small data-quality note listing missing indices.
- Still render the tab if at least one approved index is available.

## Metrics

Compute these per index from EOD OHLC data where available:

- Close and latest data date.
- 1 week, 1 month, and 3 month returns.
- Relative strength versus Nifty 50 over 1 month and 3 months.
- SMA 20, SMA 50, SMA 200.
- Price position versus SMA 20/50/200.
- RSI 14.
- MACD 12/26/9 and histogram direction.
- Trend classification: Bullish, Constructive, Neutral, Weak, or Bearish.
- Support and resistance from recent swing low/high over a practical short-term window.
- VCP-style contraction flag using recent volatility/range contraction.
- VWAP only if usable volume exists in the local index data; otherwise label VWAP as unavailable rather than fabricating it.

## Narrative

Add a comprehensive top narrative that summarizes:

- Broad-market trend and risk regime.
- Breadth across broad, size, and sector indices.
- Leadership and laggards by relative strength.
- SMA alignment and momentum condition.
- RSI/MACD confirmation or divergence.
- Support/resistance areas for key indices.
- VCP/contraction setups where visible.
- Data limitations, especially VWAP if volume is unavailable.

Use the existing report narrative style:

- Prefer OpenAI LLM narrative if configured.
- Fall back to deterministic rule-based narrative.
- Keep language educational and non-advisory.
- Avoid buy/sell recommendations, targets, or trade instructions.

## Charts

Add lightweight self-contained HTML charts using the report’s existing chart style. The first version should avoid external dependencies.

Charts to include:

- Normalized 1 month performance chart for the approved basket.
- RS ranking bar chart versus Nifty 50.
- SMA alignment / trend score bar chart.
- RSI and MACD condition summary chart.

The charts should be visible in the generated HTML and printable PDF. They can be simple SVG or HTML/CSS charts generated server-side.

## HTML Placement

Add the new tab near the existing tab group in `Sector_Rotation_Report_YYYYMMDD.html`:

- Tab label: `Technical View`
- Anchor-friendly tab id: `technical-view`
- Existing `#screeners` links should continue to work.

The tab should not replace the existing Market Brief or Screeners sections. It complements them.

## Error Handling

If index history is missing or insufficient:

- Show a clear empty-state panel.
- Explain which input file is needed.
- Keep report generation successful.

If LLM generation fails:

- Log the skip reason.
- Use the rule-based narrative.
- Do not block report generation.

## Testing

Add unit tests for:

- Technical metrics computation from synthetic index history.
- Missing-index graceful handling.
- VWAP unavailable when volume is missing.
- HTML includes the `Technical View` tab and narrative.
- Existing `#screeners` tab/link behavior remains intact.

Add a compile check for touched Python modules.

## Out of Scope For First Version

- Intraday technical view.
- Live NSE scraping.
- Candlestick charting with external JS libraries.
- Trade signals, targets, stop-losses, or recommendation language.
- Per-stock technical deep dives inside this report tab.

