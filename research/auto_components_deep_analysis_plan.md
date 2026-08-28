# Auto Components Sector – Deep Analysis & Research Plan

**Context:** Use the “unsexy industries” framing (Auto Components: ₹6.2L Cr, 830+ organized companies) and combine **NSE, BSE, indices, sectors, stocks, fundamentals (Screener), and technicals** for a single, repeatable deep-dive.

**Important:** This implementation plan is now **governed by the enhanced research approach**. Before building, complete **Phase 0 (hypothesis)** and **Phase 1 (definition + literature)** from `working-sector/ENHANCED_RESEARCH_APPROACH.md`. Use `hypothesis_template.md`, `literature_notes_template.md`, and `screen_spec_template.md` as needed.

---

## 1. What You Already Have (Current Stack)

| Layer | Source | What Exists |
|-------|--------|-------------|
| **Equity prices** | NSE (`nse_sec_full_data.csv`, cache) | OHLCV, ~2.8K stocks, 2023–2026 |
| **Indices** | `nse_index_data.csv` | 136 indices including **Nifty Auto**, date range from 2019 |
| **Index ↔ stocks** | `data/index_stock_mapping.csv` | NIFTY AUTO / Nifty Auto → constituent symbols |
| **Sectors** | `analyze_all_sectors.R` | “Auto & Auto Ancillaries” keyword list (MARUTI, TATAMOTORS, BHARATFORG, MOTHERSON, BOSCH, etc.) |
| **Fundamentals** | `core/screenerdata.R` | Screener.in: P&L, balance sheet, cash flow, ratios, quarterly results, shareholding, ROCE; `superperformance()`, `get_screener_*`, enhanced fundamental score (earnings/sales/financial/institutional) |
| **Technicals** | Same + `fixed_nse_universe_analysis.R` | DMA, RSI, Bollinger, relative strength vs Nifty 50/500, technical score, trend/signal |
| **BSE** | Reports/CSV | BSE as a **stock** (symbol BSE) in NSE data; no separate BSE exchange time series in repo |
| **Outputs** | Reports/dashboards | Comprehensive CSV, enhanced dashboard HTML, long-term screeners |

So: **NSE + indices + sector keywords + Screener fundamentals + your technical engine** are in place. BSE is only present as one listed stock, not as a separate exchange dataset.

---

## 2. Defining “Auto Components” Universe

- **Option A – Index-only:**  
  Use **Nifty Auto** constituents from `index_stock_mapping.csv` (e.g. MARUTI, EICHERMOT, M&M, BHARATFORG, TVSMOTOR, ASHOKLEY, BAJAJ-AUTO, BOSCHLTD, EXIDEIND, MOTHERSON, APOLLOTYRE, MRF, etc.).  
  Clean and dedupe (you have both "NIFTY AUTO" and "Nifty Auto" in the file).

- **Option B – Sector keywords (broader):**  
  Use “Auto & Auto Ancillaries” from `analyze_all_sectors.R`: adds more ancillaries (e.g. MOTHERSUMI, SANDHAR, WHEELS, etc.).

- **Option C – Hybrid (recommended):**  
  Start with **Nifty Auto** constituents, then add names from your sector list that are **not** in Nifty Auto but are pure auto components (e.g. tyre, battery, forgings, wiring). Optionally tag “OEM vs ancillary” for later breakdowns.

**Deliverable:** One canonical list (e.g. `working-sector/auto_components_universe.csv`) with columns: `SYMBOL`, `NAME` (if available), `SOURCE` (Nifty Auto / Sector list / Manual), `SUBSECTOR` (OEM / Tyre / Battery / Forgings / Electrical / Other).

---

## 3. Data You’ll Use (By Source)

### 3.1 NSE

- **Stocks:** `data/nse_sec_full_data.csv` (or cache) filtered to Auto Components universe.  
  Columns: SYMBOL, TIMESTAMP, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY, TOTTRDVAL (and PREVCLOSE if present).
- **Index:** Nifty Auto series from `data/nse_index_data.csv` (same TIMESTAMP range as stocks for alignment).

**Gaps:** None for price/volume. Optional: official NSE industry/sector field if you ever ingest it (e.g. from NSE bhav copy or another feed).

### 3.2 BSE

- **Current:** Only “BSE” as an NSE-listed stock in your data.
- **For real BSE comparison:** You’d need BSE equity/index data (e.g. BSE Sensex, BSE Auto index, or BSE stock EOD). Not in repo today.
- **Practical approach:**  
  - Phase 1: Ignore BSE; do everything on NSE + Nifty Auto.  
  - Phase 2: If you add BSE data later, same pipeline (universe → fundamentals → technicals) can be run for BSE Auto index / BSE-listed auto component stocks.

### 3.3 Indices

- **Nifty Auto:** Primary benchmark for the sector (performance, relative strength).
- **Optional:** Nifty 50, Nifty 500 (for broad market relative strength); Nifty MidCap 50 if many components are mid-cap.

**Use:** Index level and returns (1D, 1W, 1M, 3M, 6M, 1Y) and volatility; same for stocks; then RS (stock vs index).

### 3.4 Sectors

- **Internal:** Your “Auto & Auto Ancillaries” list and the new **Auto Components** universe (Section 2).
- **External:** If you later add industry codes (e.g. ICB / NSE industry), you can filter “Auto Components” by code and compare with this universe.

### 3.5 Fundamental Data (Screener)

From `core/screenerdata.R` and related:

- **Quarterly results** (sales, profit, margins).
- **P&L, balance sheet, cash flow** (for ratios and quality).
- **Ratios** (PE, PB, ROE, ROCE, debt/equity, etc.).
- **Shareholding** (promoter, FII, DII).
- **Existing scores:** e.g. enhanced fundamental score (earnings quality, sales growth, financial strength, institutional backing).

**Use:**

- Per-stock fundamentals for the Auto Components universe.
- Sector aggregates: median/mean PE, ROE, revenue growth, debt/equity; compare to Nifty 50 or sector benchmarks if you have them.
- Screens: e.g. “ROCE > 15%”, “Revenue growth (YoY) > 10%”, “Net debt/EBITDA < 2”, “FII + DII increasing”.

**Gaps:** Screener is scrape/API-based; rate limits and robustness. Optional: backup from another fundamental source (e.g. CMIE, annual report parsing) later.

### 3.6 Technical Data

From your existing pipeline:

- **Price-based:** DMAs (e.g. 20, 50, 200), structure (higher highs/lows), breakouts.
- **Indicators:** RSI, Bollinger Bands, stochastic, Williams %R (from `screenerdata.R`).
- **Relative strength:** Stock vs Nifty 50 / Nifty 500 / **Nifty Auto** (you already do Nifty 50/500; add Nifty Auto).
- **Scores/signals:** Technical score, trend (e.g. STRONG_BULLISH / BEARISH), trading signal (BUY/SELL/WEAK_HOLD).

**Use:**

- Rank components by technical score and RS vs Nifty Auto.
- Identify leaders (outperforming sector) vs laggards (underperforming sector).
- Overlay with fundamentals: e.g. “high technical score + improving fundamentals”.

**Gaps:** None for the logic; ensure Nifty Auto is available in the same date range as stock data when computing RS.

---

## 4. What It Would Take – Checklist

### 4.1 Universe & Metadata

- [ ] **Create `auto_components_universe.csv`**  
  Nifty Auto constituents + optional sector-keyword additions; columns: SYMBOL, NAME, SOURCE, SUBSECTOR.
- [ ] **Resolve duplicate index names** in `index_stock_mapping.csv` (NIFTY AUTO vs Nifty Auto) and use one convention.
- [ ] (Optional) **Map BSE symbols** to NSE symbols if you add BSE data later (e.g. for dual-listed names).

### 4.2 Data Pipeline

- [ ] **Filter NSE stock data** to Auto Components universe only (script or parameter in existing loader).
- [ ] **Align Nifty Auto index** to same date range; ensure no NA in CLOSE for that index.
- [ ] **Relative strength vs Nifty Auto:** Add to your technical module (same as Nifty 50/500): for each stock, RS = f(stock return, Nifty Auto return) over 1M/3M/6M.
- [ ] **BSE:** Skip for Phase 1, or add a separate BSE data load + universe for Phase 2.

### 4.3 Fundamentals (Screener)

- [ ] **Batch run** existing Screener functions for all symbols in `auto_components_universe.csv` (quarterly results, P&L, balance sheet, cash flow, ratios, shareholding).
- [ ] **Rate limiting / robustness:** Throttle requests; cache results (e.g. by symbol + date); retry logic.
- [ ] **Store** in a structured format: e.g. one CSV/table per metric type or one row per stock with key ratios + your enhanced fundamental score.
- [ ] **Sector-level summary:** Median/mean PE, ROE, ROCE, revenue growth, debt/equity for the universe.

### 4.4 Technicals

- [ ] **Run existing technical pipeline** (DMA, RSI, BB, trend, signal) on the Auto Components universe only.
- [ ] **Add Nifty Auto relative strength** (and optionally Nifty 50) in the same way you do for the full universe.
- [ ] **Output:** Technical score, trend, signal, RS vs Nifty Auto (and vs Nifty 50 if desired) per stock.

### 4.5 Integration & Screens

- [ ] **Merge** fundamentals + technicals + index RS into one table: one row per stock, columns = key ratios, technical score, RS vs Nifty Auto, trend, signal.
- [ ] **Define screens,** e.g.:  
  - RS vs Nifty Auto > 0 (outperforming sector)  
  - Technical score > 70  
  - ROCE > 15%, revenue growth > 10%  
  - Combined “TechnoFunda” or custom score for Auto Components.
- [ ] **Ranking:** Sort by composite score or by “RS vs sector + fundamental quality” for a shortlist.

### 4.6 Research & Reporting

- [ ] **Sector note:**  
  - Auto Components industry size (₹6.2L Cr, 830+ companies) and source.  
  - Nifty Auto index performance (1M, 3M, 6M, 1Y) and volatility.  
  - Top/bottom names by return and by RS vs Nifty Auto.  
  - Summary fundamentals (sector median PE, ROE, growth).
- [ ] **Dashboard / HTML report:**  
  - Table of Auto Components stocks with fundamentals + technicals + RS vs Nifty Auto.  
  - Charts: Nifty Auto vs Nifty 50; distribution of technical scores; bar chart of RS vs Nifty Auto.
- [ ] **Export:** CSV/Excel of the merged table and a short markdown summary (like your existing NSE reports).

### 4.7 Automation (Optional)

- [ ] **Single entry point:** e.g. `run_auto_components_analysis.R` that:  
  - Loads universe from `working-sector/auto_components_universe.csv`.  
  - Loads NSE + index data (existing).  
  - Runs Screener batch (with cache).  
  - Runs technical + RS (existing logic, filtered to universe).  
  - Merges and writes report + dashboard.
- [ ] **Scheduling:** Run weekly or after market close (e.g. cron or Task Scheduler) once the script is stable.

---

## 5. Suggested Order of Implementation

1. **Universe:** Build and save `auto_components_universe.csv`; fix index name in mapping if needed.  
2. **NSE + Nifty Auto:** Filter stocks to universe; ensure Nifty Auto series is loaded; add RS vs Nifty Auto in your existing R script.  
3. **Technicals:** Run current technical pipeline on this universe; attach RS vs Nifty Auto.  
4. **Fundamentals:** Batch Screener for universe; cache; build one summary table (ratios + your score).  
5. **Merge + screens:** One table; 2–3 screens (e.g. RS + technical + ROCE/revenue growth).  
6. **Report + dashboard:** Markdown summary + HTML table/charts for Auto Components.  
7. **BSE (later):** If you add BSE data, replicate the same flow for BSE Auto index / BSE-listed auto component stocks.

---

## 6. Files and Folders to Add/Change

| Item | Purpose |
|------|--------|
| `working-sector/auto_components_universe.csv` | Canonical list of Auto Components stocks (Nifty Auto + optional extras). |
| `working-sector/auto_components_deep_analysis_plan.md` | This plan. |
| New R script(s) in `working-sector/` or `organized/core_scripts/` | Load universe; filter NSE; add RS vs Nifty Auto; call Screener batch; merge; export. |
| Optional: `working-sector/screener_cache/` | Cached Screener outputs by symbol (and maybe date). |
| Reports: e.g. `reports/auto_components_YYYYMMDD.csv` and `reports/auto_components_dashboard_YYYYMMDD.html` | Final outputs. |

---

## 7. One-Paragraph Summary

**To do a deeper Auto Components analysis:** (1) Define the universe (Nifty Auto + optional sector keywords) and save it. (2) Use your existing NSE and index data, add **relative strength vs Nifty Auto**, and run your current technical pipeline on this universe. (3) Batch-pull Screener fundamentals for the same universe and cache. (4) Merge fundamentals + technicals + RS vs Nifty Auto into one table, apply a few screens (e.g. RS, technical score, ROCE, growth). (5) Produce a sector note and a small dashboard (table + charts). BSE can be skipped until you have BSE data; then the same design applies to BSE Auto. Most of the work is wiring your existing pieces (data loader, technical engine, Screener, report/dashboard) to a single sector universe and adding Nifty Auto as the sector benchmark.
