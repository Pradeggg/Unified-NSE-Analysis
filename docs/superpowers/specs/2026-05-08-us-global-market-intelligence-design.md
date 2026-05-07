# US / Global Market Intelligence Design

Date: 2026-05-08
Owner: Agent Adda / Codex
Status: Design approved for backlog; implementation plan pending user review

## Purpose

Extend Agent Adda from an NSE-first market intelligence platform into a phased global-market platform, starting with first-class US indices, ETFs, liquid US stocks, and India read-through analysis.

The goal is not to create a separate US tool. The goal is to add a US/global layer that behaves like the existing NSE experience: local caching, repeatable technical calculations, screeners, LLM-ready summaries, terminal commands, and HTML report output.

## Scope

Phase 1 covers:

- US index and ETF market context.
- Starter US stock universe across megacap tech, semiconductors, financials, energy, defense, consumer, and software/cloud.
- Daily OHLCV loading through `yfinance` with cache-first behavior.
- Technical metrics similar to the NSE flow: returns, RS, SMA, RSI, MACD, 52-week high distance, VCP, support/resistance.
- US screeners: Stage 2 leaders, VCP setups, 52-week high momentum, sector ETF rotation, risk-on/risk-off dashboard.
- India read-through rules that translate US/global moves into likely NSE sector implications.
- Terminal commands and an HTML report.

Out of scope for Phase 1:

- Paid market data feeds.
- US fundamentals, SEC filings, earnings-call parsing, and options flow.
- Intraday US scanning.
- Full S&P 500 constituent maintenance beyond a starter universe.
- Trading recommendations or automated execution.

## Design Choice

Use a hybrid phased build.

Phase 1 creates `global_market_intelligence.py` and nearby tests with clear interfaces that are market-agnostic in spirit, but avoids a broad refactor of the NSE pipeline. Once the US workflow proves useful, shared NSE/US calculations can be extracted into a common technical engine.

This avoids a large up-front rewrite while preventing the US capability from becoming a one-off script.

## Architecture

### `USUniverse`

Defines the initial US/global universe:

- Indices: `^GSPC`, `^IXIC`, `^NDX`, `^DJI`, `^RUT`, `^VIX`
- Core ETFs: `SPY`, `QQQ`, `DIA`, `IWM`
- Sector ETFs: `XLK`, `XLF`, `XLE`, `XLY`, `XLI`, `XLU`, `XLV`, `XLP`, `XLB`, `XLRE`
- Theme and macro ETFs: `SMH`, `SOXX`, `ARKK`, `TLT`, `HYG`, `LQD`, `GLD`, `USO`, `UUP`
- Starter stocks:
  - MAG7: `AAPL`, `MSFT`, `NVDA`, `AMZN`, `META`, `GOOGL`, `TSLA`
  - Semiconductors / AI: `AMD`, `AVGO`, `MU`, `ARM`, `TSM`, `ASML`, `MRVL`
  - Banks / financials: `JPM`, `BAC`, `GS`, `MS`, `V`, `MA`
  - Energy / industrial / defense: `XOM`, `CVX`, `CAT`, `GE`, `LMT`, `RTX`
  - Consumer / retail: `WMT`, `COST`, `HD`, `MCD`, `NKE`
  - Software / cloud: `CRM`, `ORCL`, `ADBE`, `NOW`, `SNOW`, `PLTR`

Each symbol carries metadata:

- `symbol`
- `name`
- `asset_type`: index, ETF, stock, commodity, currency, rates proxy
- `group`
- `benchmark`: usually `SPY` for broad assets and `QQQ` for growth/tech assets
- `india_readthrough_tags`

### `GlobalMarketDataLoader`

Fetches OHLCV through `yfinance`, then writes deterministic local cache files under:

- `data/global_market/prices.csv`
- `data/global_market/universe.json`
- `data/global_market/latest_snapshot.csv`

Behavior:

- Cache-first with 24-hour TTL for daily workflows.
- `--force` bypasses cache.
- Missing tickers are warnings, not blockers.
- Outputs normalized columns: `SYMBOL`, `DATE`, `OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`, `SOURCE`.

### `GlobalTechnicalEngine`

Computes:

- 1D, 5D, 1M, 3M returns.
- SMA 20, 50, 200 and alignment.
- RSI 14.
- MACD line, signal, histogram, and signal state.
- 52-week high and distance from high.
- Support and resistance from recent swing windows.
- Relative strength vs `SPY` and `QQQ`.
- VCP-style contraction flag using volatility compression, range contraction, and proximity to highs.
- Stage classification compatible with existing Stage 2 logic.

### `USScreeners`

Produces:

- `us_stage2_leaders`: Stage 2 stocks/ETFs with strong RS and constructive SMA alignment.
- `us_vcp_setups`: contraction setups near resistance or recent highs.
- `us_52w_high_momentum`: leaders near 52-week highs with positive RS.
- `us_sector_rotation`: sector ETF rank by 1M/3M returns, RS vs SPY, and trend quality.
- `us_risk_dashboard`: risk-on/risk-off view using QQQ/SPY, IWM/SPY, HYG/LQD, TLT, VIX, DXY/UUP, crude, and gold.

### `IndiaReadthroughEngine`

Translates US/global signals into India sector context.

Initial rule examples:

- Nasdaq, QQQ, SMH, SOXX strong: positive read-through for Indian IT, electronics, EMS, and semiconductor supply-chain beneficiaries.
- Crude strong: positive for upstream energy; negative or margin-risk for aviation, paints, tyres, and OMCs.
- DXY/UUP and yields/TLT pressure: caution for EM risk appetite and FII flows; mixed for IT due to FX translation.
- Russell/IWM strong: risk-on signal supportive for Indian mid/small caps.
- VIX up with HYG/LQD weak: risk-off signal for high-beta and leveraged sectors.
- US financials strong: supportive global bank risk appetite; map cautiously to Indian private banks and NBFCs.
- Gold strong during equity weakness: defensive/risk-aversion signal.

Outputs:

- `global_regime`: risk-on, neutral, risk-off.
- `india_sector_implications`: ranked list of positive, negative, and watch items.
- `source_signals`: exact US symbols and metrics that triggered each implication.

### `GlobalMarketReport`

Generates:

- `reports/global/us_market_report_YYYYMMDD.html`
- `reports/latest/us_market_report.html`
- `reports/global/us_market_snapshot_YYYYMMDD.csv`

Sections:

- Global summary and risk regime.
- US index tape.
- US sector ETF rotation.
- US screeners.
- India read-through.
- Watchlist and risk items.
- Data freshness and disclaimer.

The report must use the same Agent Adda disclaimer style: research and learning only, not investment advice.

### `sector_rotation_report.py` Integration

Add an optional "Global / US Context" section or tab. If global data is unavailable, the sector rotation report should still generate and show a short unavailable-data message.

### `nse_agent.py` Integration

New commands:

- `/us`
- `/us indices`
- `/us sectors`
- `/us stage2`
- `/us vcp`
- `/us stock NVDA`
- `/global readthrough`

NLP routing:

- "show me US market"
- "what is happening in Nasdaq"
- "NVDA technical setup"
- "how will US markets impact India today"
- "US sector rotation"

The command output should be concise in the terminal, with links or file paths to the full HTML report.

## Data Flow

1. Load US/global universe.
2. Check daily cache freshness.
3. Fetch missing/stale OHLCV through `yfinance`.
4. Normalize and persist OHLCV.
5. Compute indicators and RS metrics.
6. Build screeners and risk dashboard.
7. Generate India read-through.
8. Render HTML/CSV outputs.
9. Expose terminal commands and report integration.

## Error Handling

- If `yfinance` is not installed, return an actionable dependency message.
- If a ticker fails, continue with available symbols and record it in warnings.
- If benchmark data is missing, RS columns become unavailable and screeners degrade gracefully.
- If no US/global data is available, terminal/report output returns a clear unavailable state instead of raising.
- Cache reads must tolerate partial/corrupt files by refetching with `--force` guidance.

## Testing Strategy

Unit tests:

- Universe config validates required fields and benchmark presence.
- OHLCV normalization handles yfinance-style output.
- RSI, SMA, MACD, RS, VCP, and stage calculations work on fixture data.
- Sector ETF rotation ranks expected leaders in deterministic fixture data.
- India read-through rules produce expected sector implications.
- Missing dependency and missing ticker paths return structured warnings.

Smoke tests:

- Tiny fixture universe: `SPY`, `QQQ`, `XLK`, `SMH`, `NVDA`, `AAPL`.
- Live smoke: `python global_market_intelligence.py --force --universe smoke`.
- HTML smoke: generated report contains summary, indices, sectors, screeners, read-through, data freshness, and disclaimer.

## Backlog Mapping

- G0: US/Global Market Intelligence Design
- G1: US Universe + yfinance Cache
- G2: US Technical Engine + RS
- G3: US Screeners
- G4: India Read-Through Engine
- G5: US/Global HTML Report
- G6: Terminal + NLP Integration
- G7: Sector Report Global Tab
- G8: Intraday US Extension

## Acceptance Criteria For Phase 1

- A user can run one command and generate a US/global report from local cache or fresh data.
- `/us` and `/global readthrough` work in the terminal without breaking existing NSE workflows.
- US indices, ETFs, and starter stocks are ranked with the same broad technical language as NSE.
- India read-through lists sector implications with source signals.
- Missing data and dependency problems are visible but non-fatal.
- Tests cover the deterministic calculations and rule engine.
