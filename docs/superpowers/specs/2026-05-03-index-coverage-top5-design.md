# Index Coverage And Top 5 Stocks Design

## Goal

Extend the Index Intelligence dashboard so it lists all cached NSE indices and shows the top five investable stocks for every sectoral or thematic index with usable constituent data.

## Scope

The feature belongs in `index_intelligence.py` because that module already owns cross-index breadth, local index constituent mapping, and the generated `reports/latest/index_intelligence.html` dashboard. The sector rotation report may later embed or link to this view, but it should not own the index coverage logic.

## Data Inputs

- `data/nse_indices_catalog.csv`: cached NSE index catalog with category, display name, API symbol, valuation, and high/low fields.
- `data/index_stock_mapping.csv`: local index-to-stock constituent mapping.
- `data/nse_sec_full_data.csv`: local OHLC and volume history used to compute stock metrics.

## Outputs

- `reports/latest/index_intelligence.html`: adds Index Coverage and Top 5 Stocks sections.
- `reports/latest/index_intelligence.csv`: existing breadth output remains unchanged.
- `reports/latest/index_coverage.csv`: all catalog indices with coverage status.
- `reports/latest/index_top5_stocks.csv`: top five stocks per sectoral/thematic index.

## Behavior

Index coverage shows index name, category, API symbol, constituent count, mapping status, and whether it is included in the dashboard breadth table. Mapping status is `Available` when constituents exist locally, `Inferred` when data is produced by a fallback such as Smallcap 250, and `Missing` otherwise.

Top five stocks are generated only for `Sectoral` and `Thematic` indices. Ranking uses local technical data only: DMA participation, proximity to 52-week high, recovery from 52-week low, one-day return, and liquidity. This keeps the feature deterministic and available offline.

## Testing

Tests cover coverage status classification, top five filtering/ranking, and HTML rendering of the new sections. Existing breadth tests remain valid.
