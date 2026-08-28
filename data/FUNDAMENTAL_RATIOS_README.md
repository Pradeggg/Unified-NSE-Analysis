# Optional quarterly ratios for the dashboard

Copy `fundamental_quarterly_ratios.example.csv` to **`fundamental_quarterly_ratios.csv`** (same `data/` folder) and replace rows with your universe.

## Columns in `fundamental_scores_database.csv` (R refresh)

When you re-run the R fundamental job (`core/generate_fundamental_scores.R` → `fn_get_enhanced_fund_score` → `fn_screener_public_ratios`), the main database CSV can include:

| Column | Meaning |
|--------|--------|
| `PROFIT_YOY_PCT` | Reported profit growth YoY from screener comparison table (%) |
| `SALES_REPORTED_YOY_PCT` | Reported sales growth YoY (%) |
| `MARGIN_PP_CHANGE` | Change in net/operating margin vs prior period (**percentage points**) |
| `PE_TTM` | Trailing P/E from ratios table (best-effort) |
| `CFO_YOY_PCT` | YoY % change in operating cash flow (best-effort row match) |
| `DEBT_YOY_PCT` | YoY % change in borrowings / debt line (best-effort) |
| `RATIOS_PERIOD` | Usually the scrape date |

The Python dashboard maps these into the **Fundamentals** tab without requiring `fundamental_quarterly_ratios.csv`. Older CSV rows missing these columns show `—` until you refresh fundamentals.

## Expected columns

| Column | Meaning |
|--------|--------|
| `SYMBOL` | NSE symbol (same as analysis CSV), case-insensitive |
| `EPS_GROWTH_YOY` | EPS change vs year-ago quarter (%, e.g. `10.5` = +10.5%) |
| `PROFIT_MARGIN_GROWTH_YOY` | Net (or operating) margin change vs year-ago (percentage points or % — be consistent) |
| `PE_TTM` | Trailing P/E |
| `CFO_CHANGE_YOY` | Operating cash flow change vs year-ago (%) |
| `DEBT_CHANGE_YOY` | Total / net debt change vs year-ago (%) |
| `RATIOS_PERIOD` | Label shown in UI (e.g. quarter end date) |

## Aliases (auto-detected)

The dashboard also looks for these alternate headers if the primary name is missing:

- EPS: `EPS_GROWTH_QOQ`, `EPS_GROWTH`, `eps_growth_yoy`
- Margin: `NET_MARGIN_GROWTH_YOY`, `profit_margin_growth_yoy`, …
- PE: `PE`, `P_E`, `pe_ttm`, `trailing_pe`
- Cashflow: `OCF_CHANGE_YOY`, `CASHFLOW_CHANGE_YOY`, …
- Debt: `NET_DEBT_CHANGE_YOY`, `TOTAL_DEBT_CHANGE_YOY`, …
- Period: `RATIO_AS_OF`, `QUARTER_END`, `FUNDAMENTAL_PERIOD`, `period`

After updating the CSV, run:

`python python/core/generate_nse_interactive_dashboard.py`
