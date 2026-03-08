# Auto Components Pipeline (Phases 2–5) – Python

Step-by-step Python pipeline for **Phase 2 (Data)** through **Phase 5 (Report)** of the enhanced research approach.

---

## Quick run

From the **project root**:

```bash
python3 working-sector/run_pipeline.py
```

Or from `working-sector`:

```bash
python3 run_pipeline.py
```

Outputs are written to **`working-sector/output/`**.

### With Screener fetch for missing fundamentals

If you want to **download fundamental data from Screener.in** for any universe symbols that are not yet in `fundamental_scores_database.csv`, use:

```bash
python3 working-sector/run_pipeline_with_screener.py
```

This will:

1. Compare the auto components universe with existing fundamental scores.
2. For any **missing** symbols, run the R script `fetch_screener_fundamentals.R` (uses `core/screenerdata.R` and Screener.in).
3. Merge new scores into `organized/data/fundamental_scores_database.csv` (or `data/` if that file does not exist).
4. Run Phase 2 → Phase 5 as usual.

**Requirements:** R installed with packages `dplyr`, `rvest`, and `readr`; `Rscript` on PATH. Rate limiting (~0.8 s per symbol) is applied to avoid overloading Screener.

### Optional: P&L, quarterly, balance sheet, and financial ratios (for richer narratives)

To add **P&L** (Sales, Net Profit, EPS, YoY), **quarterly results**, **balance sheet** (Equity, Debt, Cash, Debt/Equity), and **financial ratios** (ROCE, ROE, EPS, PE, PB, OPM, NPM, Interest Coverage, Div Yield) to stock narratives, run the R script that fetches these from Screener.in and writes `output/fundamental_details.csv`:

```bash
Rscript working-sector/fetch_screener_fundamental_details.R
```

If no argument is given, it uses `output/symbols_to_fetch.txt` if present, else **`auto_components_universe.csv`** (SYMBOL column). Then re-run the narrative generator so it picks up the new CSV:

```bash
python3 working-sector/generate_stock_narratives.py
```

Narratives will then include P&L, quarterly progression, balance sheet, and ratios (ROCE, ROE, EPS, PE, PB, etc.). The comprehensive report (MD/HTML/XLSX) will show these when available.

---

## Steps (in order)

| Phase | Script | What it does |
|-------|--------|---------------|
| **2** | `phase2_data.py` | Loads universe (`auto_components_universe.csv`), NSE stock and index data; filters to universe; computes returns (1M, 3M, 6M), RS vs Nifty Auto and Nifty 500, RSI, technical score; merges fundamentals from `fundamental_scores_database.csv`. Writes **phase2_universe_metrics.csv**. |
| **3** | `phase3_screens.py` | Builds composite score (0.4×fund + 0.4×tech + 0.2×RS rank); applies screen (FUND_SCORE ≥ 70, RS_6M > 0); produces shortlist (top 15 by composite). Writes **phase3_shortlist.csv** and **phase3_full_with_composite.csv**. |
| **4** | `phase4_backtest.py` | Backtest: at each rebalance date (monthly), applies momentum screen (RS_6M > 0), equal-weight portfolio; forward 1Y return vs Nifty 500. Writes **phase4_backtest_results.csv**. *(Uses only price-based criteria; no historical fundamental data.)* |
| **5** | `phase5_report.py` | Generates **auto_components_sector_note.md** (definition, universe, shortlist, backtest summary, sources) and **auto_components_dashboard.html** (table of universe metrics). |

---

## Config

Edit **`config.py`** to change:

- Paths (universe, stock, index, fundamental CSVs)
- Index names (Nifty Auto, Nifty 500)
- Lookbacks (1M / 3M / 6M trading days)
- Screen thresholds (`MIN_FUND_SCORE`, `MIN_RS_6M`)
- Composite weights and shortlist size
- Backtest start year and forward return window

---

## Dependencies

- **Python 3**
- **pandas**, **numpy**

No optional packages (talib/pandas_ta) required; RSI and technical score are computed inline.

---

## Output files

| File | Description |
|------|--------------|
| `output/phase2_universe_metrics.csv` | One row per stock: returns, RS, RSI, technical score, fund score. |
| `output/phase3_full_with_composite.csv` | Same + composite score and pass flags. |
| `output/phase3_shortlist.csv` | Top N by composite (with valid fund + RS). |
| `output/phase4_backtest_results.csv` | Per rebalance: portfolio 1Y return, benchmark return, excess. |
| `output/auto_components_sector_note.md` | Sector note for reporting. |
| `output/auto_components_dashboard.html` | Simple HTML table of universe metrics. |

---

## Running a single phase

```bash
python3 working-sector/phase2_data.py
python3 working-sector/phase3_screens.py   # reads phase2 output
python3 working-sector/phase4_backtest.py
python3 working-sector/phase5_report.py    # reads phase2/3/4 outputs
```

Phase 3 and 5 read from `output/` when not given in-memory inputs.
