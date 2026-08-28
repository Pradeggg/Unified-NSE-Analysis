# Screener.in 5-Year Fundamentals Fetcher

**Purpose:** Unblock 8 backlog items blocked on extended Screener.in data scraping.

## What This Script Does

Extends the existing `fetch_screener_fundamental_details.R` to extract:
1. **5-year P&L trends** (Revenue, PAT, EBITDA, EPS CAGR)
2. **5-year ROCE/ROE averages** (for quality screening)
3. **Cash flow statement** (CFO, Capex, FCF) — already scraped by `core/screenerdata.R`, now extracted
4. **8-quarter EPS series** (for earnings acceleration detection)
5. **Peers comparison table** (for relative valuation)

## Backlog Items Unblocked

| Item | Requirement | Output File |
|------|-------------|-------------|
| **A4** — Earnings Acceleration Screener | 8 quarters EPS + YoY growth | `data/quarterly_eps.csv` |
| **A7** — Quality Compounder Screener | 5yr Revenue/PAT CAGR, avg ROE | `data/quality_fundamentals.csv` |
| **D1** — DuPont Decomposition | 5yr P&L + Balance Sheet trends | `data/quality_fundamentals.csv` |
| **D2** — Earnings Quality Score | CFO data (cash conversion ratio) | `data/cashflow_data.csv` |
| **D5** — Forensic Accounting Suite | 5yr P&L/BS for Beneish/Piotroski/Altman | `data/quality_fundamentals.csv` |
| **D6** — Competitive Moat Score | 5yr margin stability, ROCE vs hurdle | `data/quality_fundamentals.csv` |
| **E2** — Peer Comparison Engine | Peers table (PE, ROE, Market Cap vs peers) | `data/peer_comparisons.csv` |
| **D2 (CFO)** | Cash flow from operations | `data/cashflow_data.csv` |

---

## Usage

### 1. Test Run (5 stocks, ~2 minutes)
```bash
cd /path/to/Unified-NSE-Analysis
Rscript working-sector/fetch_screener_5yr_fundamentals.R data/test_symbols.txt
```

**Expected output:**
- `data/quality_fundamentals.csv` — 5 rows with 30+ columns (5yr trends)
- `data/quarterly_eps.csv` — 40 rows (5 stocks × 8 quarters)
- `data/cashflow_data.csv` — 5 rows with CFO/Capex/FCF
- `data/peer_comparisons.csv` — ~25 rows (5 stocks × ~5 peers each)

### 2. Full Nifty 500 Run (~45 hours with 5-second rate limit)
```bash
# Create full symbols list from existing cache
Rscript -e "
  cache <- read.csv('data/_sector_rotation_fund_cache.csv')
  writeLines(unique(cache\$symbol), 'data/nifty500_symbols.txt')
"

# Run fetch (will take 500 symbols × 5 seconds = 2,500 seconds = ~42 minutes for scraping alone)
# But with data processing, expect 45-60 minutes
Rscript working-sector/fetch_screener_5yr_fundamentals.R data/nifty500_symbols.txt
```

**Tip:** Run overnight or use tmux:
```bash
tmux new -s screener-fetch
Rscript working-sector/fetch_screener_5yr_fundamentals.R data/nifty500_symbols.txt
# Ctrl+B, D to detach
# tmux attach -t screener-fetch to reattach
```

---

## Output File Schemas

### `data/quality_fundamentals.csv`
| Column | Type | Example | Description |
|--------|------|---------|-------------|
| `symbol` | string | "TATASTEEL" | NSE symbol |
| `SALES_Y1` to `SALES_Y5` | numeric | 245000 | Revenue (₹Cr) for years 1-5 (Y1 = latest) |
| `PAT_Y1` to `PAT_Y5` | numeric | 18500 | Net profit (₹Cr) for years 1-5 |
| `EBITDA_Y1` to `EBITDA_Y5` | numeric | 42000 | EBITDA (₹Cr) for years 1-5 |
| `EPS_Y1` to `EPS_Y5` | numeric | 14.52 | EPS (₹) for years 1-5 |
| `REV_CAGR_5Y` | numeric | 12.4 | 5-year revenue CAGR (%) |
| `PAT_CAGR_5Y` | numeric | 18.7 | 5-year PAT CAGR (%) |
| `ROCE_Y1` to `ROCE_Y5` | numeric | 22.5 | ROCE (%) for years 1-5 |
| `ROE_Y1` to `ROE_Y5` | numeric | 19.8 | ROE (%) for years 1-5 |
| `AVG_ROE_5Y` | numeric | 18.2 | 5-year average ROE (%) |
| `AVG_ROCE_5Y` | numeric | 20.1 | 5-year average ROCE (%) |
| `CFO_Y1` to `CFO_Y5` | numeric | 35000 | Cash from operations (₹Cr) |
| `CAPEX_Y1` to `CAPEX_Y5` | numeric | -12000 | Capital expenditure (₹Cr, negative) |
| `FCF_Y1` | numeric | 23000 | Free cash flow latest year (₹Cr) |

### `data/quarterly_eps.csv`
| Column | Type | Example | Description |
|--------|------|---------|-------------|
| `symbol` | string | "INFY" | NSE symbol |
| `quarter_num` | integer | 1 | Quarter sequence (1 = latest, 8 = oldest) |
| `quarter_name` | string | "Sep 2025" | Quarter label from Screener.in |
| `revenue` | numeric | 42500 | Quarterly revenue (₹Cr) |
| `net_profit` | numeric | 8200 | Quarterly net profit (₹Cr) |
| `eps` | numeric | 19.5 | Quarterly EPS (₹) |
| `op_margin` | numeric | 19.3 | Operating margin (%) = NP / Revenue |

### `data/cashflow_data.csv`
| Column | Type | Example | Description |
|--------|------|---------|-------------|
| `symbol` | string | "HDFCBANK" | NSE symbol |
| `CFO_Y1` to `CFO_Y5` | numeric | 125000 | Cash from operations (₹Cr) |
| `CAPEX_Y1` to `CAPEX_Y5` | numeric | -8500 | Capex (₹Cr, negative) |
| `FCF_Y1` | numeric | 116500 | FCF = CFO - Capex (₹Cr) |

### `data/peer_comparisons.csv`
| Column | Type | Example | Description |
|--------|------|---------|-------------|
| `Target_Symbol` | string | "TATASTEEL" | The stock whose peers these are |
| `Company` | string | "Tata Steel" | Peer company name (from Screener.in) |
| `CMP` | numeric | 145.2 | Current market price (₹) |
| `P/E` | numeric | 12.5 | Price-to-earnings ratio |
| `Market Cap` | numeric | 180000 | Market cap (₹Cr) |
| `Div Yld` | numeric | 2.4 | Dividend yield (%) |
| `NP Qtr` | numeric | 4500 | Latest quarter net profit (₹Cr) |
| `Qtr Profit Var` | numeric | 18.5 | QoQ profit growth (%) |
| `Sales Qtr` | numeric | 56000 | Latest quarter sales (₹Cr) |
| `ROCE` | numeric | 18.2 | Return on capital employed (%) |

---

## Rate Limiting & Best Practices

1. **Screener.in rate limit:** 5-second sleep enforced between requests (backlog spec).
2. **Cache TTL:** Output files should be cached for **30 days** (per backlog registry).
3. **Retry strategy:** Script does not retry on failure; failed symbols return `NULL` (non-fatal).
4. **Stale data handling:** If scrape fails, existing cache remains valid for 30 days.

---

## Integration into Sector Rotation Report

After running this script, update `sector_rotation_report.py`:

```python
# Load 5-year fundamentals
quality_fund = pd.read_csv("data/quality_fundamentals.csv")
quarterly_eps = pd.read_csv("data/quarterly_eps.csv")
peers = pd.read_csv("data/peer_comparisons.csv")
cashflow = pd.read_csv("data/cashflow_data.csv")

# Merge into candidates
candidates = candidates.merge(quality_fund, on="symbol", how="left")
candidates = candidates.merge(cashflow[["symbol", "CFO_Y1", "FCF_Y1"]], on="symbol", how="left")
```

---

## Troubleshooting

### Error: "core/screenerdata.R not found"
**Fix:** Run from project root, not from `working-sector/`:
```bash
cd /path/to/Unified-NSE-Analysis
Rscript working-sector/fetch_screener_5yr_fundamentals.R
```

### Error: "No symbols to fetch"
**Fix:** Create `data/nifty500_symbols.txt` or pass a symbols file as argument.

### Some symbols return NA
**Cause:** Screener.in may not have consolidated/standalone data, or the stock was delisted/renamed.
**Impact:** Non-fatal. These symbols will have `NA` in output CSVs.

### Peers table missing for some symbols
**Cause:** Screener.in only shows peers for stocks with enough comparable companies.
**Impact:** `peer_comparisons.csv` will have fewer rows than expected. Use market cap + sector as fallback.

---

## Next Steps

1. **Test run** with 5 symbols (`data/test_symbols.txt`)
2. **Validate output** — check CSVs have expected columns and non-NA values
3. **Full run** on Nifty 500 (schedule overnight)
4. **Integrate** into `sector_rotation_report.py` (see Integration section)
5. **Implement blocked screeners** (A4, A7, D1, D2, D5, D6, E2)

---

## Performance Estimates

| Dataset | Symbols | Time per Symbol | Total Time |
|---------|---------|-----------------|------------|
| Test set | 5 | ~25s (5 API calls × 5s) | 2 min |
| Nifty 100 | 100 | ~25s | 42 min |
| Nifty 500 | 500 | ~25s | 3.5 hours |

**Optimization tip:** Run in parallel batches of 10 with staggered start (5-second offset) to respect rate limit but parallelize.

---

## Maintenance

**Cache refresh schedule:**
- **Daily:** Not needed (fundamentals are quarterly/annual)
- **Monthly:** Recommended for active portfolios
- **Quarterly:** Minimum for earnings season updates
- **On-demand:** When backlog items are ready for implementation

**Stale data warning:** If last run > 45 days, trigger re-fetch before Sprint 5 work begins.
