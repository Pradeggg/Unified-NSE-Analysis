# Visual Scan Capability Design

Date: 2026-05-22

## Goal

Build a first-class visual scan workflow for prompts such as:

```text
Perform a visual scan of DMART
/visual-scan DMART
```

The v1 scope is a swing/EOD visual scan. It should assess daily and weekly chart structure, detect major visual patterns from local OHLCV evidence, generate annotated chart assets, and produce a high-quality HTML report with a grounded research stance. TradingView screenshots are optional corroboration only; local computed evidence is the source of truth.

## Non-Goals

- Do not make TradingView required for report generation.
- Do not infer chart patterns only from screenshots.
- Do not produce unqualified buy/sell recommendations.
- Do not include live intraday execution logic in v1.
- Do not depend on an LLM to decide whether a VCP, cup-with-handle, or breakout exists.

## User Experience

Supported inputs:

```text
/visual-scan DMART
Perform a visual scan of DMART
Visual scan DMART
```

Expected result:

- A terminal summary with the verdict, key trigger, invalidation, report path, and missing evidence.
- A rich HTML report under `reports/visual_scan/`.
- A replayable JSON evidence pack.
- Local chart assets for daily and weekly views.
- Optional TradingView screenshot assets when browser capture succeeds.

The report uses the existing Agent Adda standard report theme.

## Architecture

Proposed module layout:

```text
terminal/visual_scan/
  __init__.py
  models.py
  data_loader.py
  detectors.py
  chart_renderer.py
  tradingview.py
  report.py
  command.py
```

Responsibilities:

- `models.py`: dataclasses for visual scan packs, pattern evidence, zones, chart annotations, and final verdicts.
- `data_loader.py`: resolves symbols and loads daily, weekly, monthly, snapshot, volume, sector, and MTF evidence.
- `detectors.py`: deterministic chart-pattern and volume detectors.
- `chart_renderer.py`: renders local annotated daily and weekly chart assets.
- `tradingview.py`: optional Playwright/browser capture for TradingView screenshots.
- `report.py`: renders the balanced HTML report using the shared standard style.
- `command.py`: exposes the deterministic command handler used by slash command routing and natural-language routing.

## Data Flow

1. Resolve the requested entity to a canonical NSE symbol.
2. Load local market evidence:
   - Daily OHLCV.
   - Weekly resampled OHLCV.
   - Monthly context when available.
   - Volume history.
   - Existing technical snapshot, including stage, RS, RSI, MACD, and moving-average alignment.
   - Sector context.
   - Existing MTF alignment from `terminal.mtf`.
3. Run deterministic visual-pattern detectors.
4. Build a `VisualScanPack` with all evidence, annotations, zones, caveats, and missing data.
5. Render annotated local charts.
6. Attempt optional TradingView screenshot capture.
7. Generate HTML report and JSON evidence pack.
8. Return a concise terminal summary.

## Pattern Detector Contract

Every detector returns structured evidence:

```json
{
  "pattern": "VCP",
  "status": "candidate",
  "confidence": 0.72,
  "evidence": [
    "Three contractions detected over last 11 weeks",
    "Range narrowed from 12.4% to 5.1%",
    "Volume fell below 20-week average during base"
  ],
  "zones": {
    "pivot": 4210,
    "support": 3890,
    "invalidation": 3740,
    "target_1": 4550
  },
  "caveats": [
    "Breakout volume not confirmed yet"
  ]
}
```

Valid detector statuses:

- `confirmed`
- `candidate`
- `absent`
- `insufficient_data`

Detectors must not return binary yes/no labels when evidence is weak. They must expose confidence, evidence, caveats, and missing inputs.

## v1 Detectors

### Trend Structure

Inputs:

- Daily and weekly OHLCV.
- SMA20, SMA50, SMA200.
- 52-week high/low.
- Relative strength vs NIFTY.
- Stage snapshot when available.

Outputs:

- Trend state.
- Moving-average stack.
- Distance from 52-week high.
- Trend caveats.

### VCP / Tight Contraction

Inputs:

- Weekly and daily OHLCV.
- Volume history.

Logic:

- Detect 2-4 narrowing pullbacks.
- Measure contraction widths.
- Check volume dry-up during the base.
- Require proximity to pivot or resistance for higher confidence.

Outputs:

- VCP status and confidence.
- Contraction sequence.
- Pivot, support, invalidation, and caveats.

### Cup-With-Handle Candidate

Inputs:

- Daily and weekly OHLCV over a configurable lookback.
- Volume history.

Logic:

- Detect rounded base depth and recovery.
- Detect handle drift or pullback.
- Check handle volume dry-up.
- Mark as `candidate` unless breakout confirmation is present.

Outputs:

- Cup/handle status.
- Base depth.
- Handle low.
- Pivot and invalidation.

### Breakout / Retest

Inputs:

- Recent daily candles.
- Pivot/resistance zones from trend and base detectors.
- Volume history.

Logic:

- Detect close above pivot/resistance.
- Check breakout volume expansion.
- Detect retest hold or failed breakout.

Outputs:

- Breakout status.
- Retest status.
- Failed breakout caveats.

### Volume Quality

Inputs:

- Daily and weekly volume.

Logic:

- Compare up-day vs down-day volume.
- Measure dry-up inside the base.
- Measure breakout volume vs 20-day and 50-day average.

Outputs:

- Accumulation/distribution read.
- Dry-up evidence.
- Breakout confirmation status.

### Multi-Timeframe Alignment

Inputs:

- Existing `terminal.mtf` readings.

Outputs:

- MTF score.
- Monthly, weekly, and daily alignment.
- Conflicts and missing timeframes.

## Recommendation Model

The final stance is evidence-gated.

Labels:

- `Actionable on breakout confirmation`
- `Actionable after retest hold`
- `Watchlist / base building`
- `Avoid fresh entry`
- `Manual review`

Scoring:

```text
Trend structure          25
MTF alignment            20
Base quality             20
Volume quality           15
Breakout/retest quality  15
Risk/reward clarity       5
```

The report always includes:

- Trigger.
- Invalidation.
- Target zones.
- Risk/reward frame.
- What would improve the view.
- What would weaken the view.
- Missing evidence and caveats.

Example stance:

```text
DMART is a watchlist/base-building candidate. Act only if it closes above the pivot with confirming volume. Invalidate below the handle low or the defined support zone.
```

## TradingView Policy

TradingView is optional corroboration.

Behavior:

1. Build a TradingView URL such as `NSE:DMART`.
2. Open the chart with Playwright or system browser when available.
3. Wait for chart canvas.
4. Capture screenshot.
5. Attach screenshot to the HTML report.

Failure behavior:

- If login, network, canvas loading, or timeout fails, continue report generation.
- Add a report caveat:

```text
TradingView screenshot unavailable; report generated from local OHLCV evidence.
```

Grounding rule:

- No chart-pattern conclusion may depend only on a TradingView screenshot.
- If image-based vision is added later, it should verify or challenge computed detector evidence, not replace it.

## Report Output

Report structure uses the approved balanced layout: a compact verdict strip first, visual evidence immediately after, and detailed audit evidence below.

1. Verdict strip.
2. Annotated daily chart.
3. Weekly context chart.
4. Decision panel.
5. Pattern evidence.
6. MTF alignment.
7. Source and audit trail.
8. Optional TradingView screenshot.
9. Missing data and caveats.

Files:

```text
reports/visual_scan/DMART_<timestamp>.html
reports/visual_scan/DMART_<timestamp>.json
reports/visual_scan/assets/DMART_<timestamp>_daily.png
reports/visual_scan/assets/DMART_<timestamp>_weekly.png
reports/visual_scan/assets/DMART_<timestamp>_tradingview_daily.png
```

## Routing

Deterministic routing should handle:

```text
/visual-scan DMART
visual scan DMART
perform a visual scan of DMART
deep visual QA of DMART chart
```

Routing must not fall through to general LLM planning. It should resolve the symbol and call the visual scan command handler.

## Error Handling

- Unknown symbol: return a clarification with near matches.
- Insufficient OHLCV: return `Manual review` and explain missing history.
- Missing weekly/monthly data: continue with reduced confidence.
- Detector conflicts: show conflicts in the report and lower confidence.
- TradingView unavailable: continue and mark screenshot as unavailable.
- Chart rendering failure: still write JSON evidence and terminal summary, but mark HTML chart assets missing.

## Testing

Test files:

```text
tests/test_visual_scan_detectors.py
tests/test_visual_scan_report.py
tests/test_visual_scan_command.py
```

Required fixtures:

- VCP candidate.
- Cup-with-handle candidate.
- Breakout with volume.
- Failed breakout.
- Weak/no setup.
- Insufficient history.

Test coverage:

- Detector statuses and confidence.
- Zone calculations.
- Missing evidence propagation.
- Report section rendering.
- TradingView mocked success/failure.
- Natural-language and slash-command routing.
- No ungrounded recommendation when evidence is missing.

## Acceptance Criteria

- `/visual-scan DMART` generates an HTML report and JSON evidence pack.
- `Perform a visual scan of DMART` routes to the same deterministic handler.
- The report includes a verdict strip, annotated chart, pattern evidence, MTF alignment, trigger, invalidation, targets, and caveats.
- TradingView failure does not block report generation.
- Every final stance is traceable to detector evidence.
- Tests cover VCP, cup-with-handle, breakout, failed breakout, weak setup, and missing data paths.
