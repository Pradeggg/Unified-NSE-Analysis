# Portfolio Analyzer – Phased Design (LLM + Rules)

AI agent that analyzes CDSL/NSDL statements and PnL reports: PnL summary, sectoral assessment (NSE + market research), technical and fundamental analysis per holding, **risk modeling and projection scenarios**, **market sentiment** (search + LLM synthesis), stock narratives, and a comprehensive report. Combines **rule-based** risk profilers (VaR, Sharpe, beta, drawdown, etc.) with **LLM + search** for sentiment and scenario narrative.

---

## Inputs

| Input | Format | Description |
|-------|--------|-------------|
| **CAS / CDSL report** | PDF (NSDLe-CAS_*.pdf) or CSV export | Consolidated Account Statement: current holdings (scrip, ISIN, quantity, value). |
| **PnL report** | CSV (e.g. `*_EQProfitLossDetails.csv`) | Equity profit/loss: symbol, ISIN, qty, sale/purchase dates and rates, P/L per line. |

The PnL CSV structure (from your sample):
- Header: `Account`, `Name`, then section headers (Intraday, <= 1 Year, > 1 Year).
- Data columns: `Stock Symbol`, `ISIN`, `Qty`, `Sale Date`, `Sale Rate`, `Sale Value`, `Purchase Date`, `Purchase Rate`, `Purchase Value`, `Profit/Loss(-)`.

---

## Architecture: LLM + Rules + Search

- **Rules-based**: Parsing, aggregation, screening thresholds, score calculations, **risk metrics** (VaR, Sharpe, beta, drawdown), **scenario math**, report assembly.
- **LLM-based**: Sector narrative, “bought at right time” reasoning, technical/fundamental narrative per stock, **market sentiment synthesis**, **scenario narrative**, summary commentary. Structured prompts + optional tool use (Ollama/OpenAI).
- **Search-based**: Agent performs **iterative web searches** using **DDGS (DuckDuckGo) and SERP** (SerpAPI or Google); **sector-level** and **stock-level** sentiment from news and broker reports; results combined with portfolio/risk and synthesized by the LLM with cited sources and dates.

**LLM analysis (technical + financial):** The LLM must analyse **technical indicators** (price, returns, RSI, relative strength, trend, buy timing) and **financial strength** using: **balance sheet** (equity, debt, cash, D/E), **P&L** (sales, net profit, YoY), **quarterly results** (progression), and key **ratios** — **EPS, PE, PB, ROCE** (and ROE, OPM, NPM where available). Credit ratings (Screener) and **call transcript** takeaways feed into financial health and future growth (qualitative + quantitative).

---

## Phases (Step-by-Step)

### Phase 0: Ingest and normalize
**Goal:** Single source of truth for holdings and closed PnL.

- Parse PnL CSV (skip section header rows, normalize dates and numeric columns).
- If CAS is PDF: extract tables (e.g. PyMuPDF/pdfplumber) or accept user-provided holdings CSV.
- Output:
  - `holdings.csv`: Symbol, ISIN, Quantity, AvgCost (optional), Sector (from NSE/mapping).
  - `closed_pnl.csv`: Symbol, ISIN, Qty, PurchaseDate, PurchaseRate, SaleDate, SaleRate, PnL, TenureBucket (intraday / STCG / LTCG).
  - `portfolio_summary.json`: Account name, report period, total positions, total realized PnL.

**Rules:** Date parsing (DD-MON-YYYY), tenure = sale_date - purchase_date, PnL = sale_value - purchase_value.

---

### Phase 1: PnL and portfolio summary
**Goal:** Human-readable PnL summary and portfolio-level insights.

- **Rules:** Aggregate PnL by symbol, by tenure bucket (intraday / <=1Y / >1Y), total realized, count of trades.
- **LLM:** Short summary: “Realized PnL is Rs X; top gainers/losers; STCG vs LTCG mix; any concentration or tax implications.”
- Output: `pnl_summary.md`, `pnl_aggregates.csv`.

---

### Phase 2: Sectoral assessment
**Goal:** For each sector represented in holdings, deep sector view using NSE + market research.

- **Rules:** Map each holding to NSE industry/sector (reuse project’s sector mapping or NSE data).
- **Data:** NSE index/sector performance, universe metrics (reuse `working-sector` style: phase2_data, NSE indices).
- **Research:** Web/search or cached reports: sector outlook, growth, risks (similar to `run_sector_research` in working-sector).
- **LLM:** One short sector note per sector in the portfolio: outlook, how the portfolio’s exposure fits.
- Output: `sector_assessment.md`, optional `sector_metrics.csv` per sector.

---

### Phase 3: Technical analysis (per holding)
**Goal:** For each current holding and for key sold names: “Was it bought at the right time?” and current technical recommendation.

- **Rules:**
  - Fetch or use cached NSE/price data: current price, 1M/3M/6M returns, RSI, moving averages.
  - Compare purchase price (or avg cost) to price at purchase date and subsequent path: e.g. “Price was at 52-week high at purchase” vs “Bought near pullback.”
  - Compute a **technical score** (0–100) from RSI, trend, relative strength vs Nifty 500 (reuse working-sector logic).
  - **Recommendation:** BUY / HOLD / REDUCE / SELL from score + rules (e.g. RSI >70 → caution, RS < 0 → weak).
- **LLM:** Short justification: “Bought at right time because …” or “Bought rich because …”; “Current technical recommendation: HOLD because ….”
- Output: `technical_by_stock.csv` (Symbol, PurchaseDate, PurchaseRate, CurrentPrice, RSI, TechnicalScore, Recommendation, BuyTimingNote), `technical_summary.md`.

---

### Phase 4: Fundamental analysis (per holding)
**Goal:** Fundamental scores, **call transcripts**, **credit ratings**, and narrative on **financial health** and **future growth** (qualitative + quantitative).

- **Rules:** For each holding symbol:
  - Pull from `fundamental_scores_database.csv` and `fundamental_details.csv` (Screener pipeline): earnings quality, sales growth, financial strength, institutional backing; P&L, quarterly results, balance sheet, ratios (EPS, PE, PB, ROCE, ROE, OPM, NPM).
  - **Call transcripts:** Fetch **latest earnings/concall transcripts** from **NSE** (corporate announcements / transcripts) or **Screener** (concall/earnings transcript links). Use in narrative for management commentary and growth outlook.
  - **Credit ratings:** From **Screener** (credit rating / rating agencies). Use to build **financial health** and **future growth prospect** in both **qualitative** (narrative) and **quantitative** (score/rating) form.
- **Data:** Reuse working-sector: organized/data fundamentals; optional R/Python fetch for Screener detail pages (P&L, BS, quarterly, ratios, transcripts, credit ratings).
- **LLM:** Fundamental narrative per stock: (1) **Financial health** (balance sheet, debt, liquidity, credit rating), (2) **Future growth prospect** (earnings trajectory, management view from transcripts, sector alignment), in both qualitative summary and key numbers (scores, ratios, rating).
- Output: `fundamental_by_stock.csv`, `fundamental_details.csv`, optional `call_transcripts_summary.csv` or per-stock transcript snippets, `credit_ratings.csv`; all used in narratives.

---

### Phase 5: Stock narratives
**Goal:** One coherent narrative per stock combining PnL, sector, **technical + financial** analysis, and recommendation.

- **Inputs:** Outputs of Phases 0–4 (holdings, PnL, sector note, technical summary, fundamental summary including transcripts and credit ratings).
- **LLM analysis:** For each holding the LLM must analyze **both**:
  - **Technical indicators:** Price, returns, RSI, relative strength, trend, “bought at right time?” and current technical recommendation.
  - **Financial strength:** Using **balance sheet** (equity, debt, cash, D/E), **P&L** (sales, net profit, YoY), **quarterly results** (progression), and **ratios**: **EPS, PE, PB, ROCE**, plus ROE, OPM, NPM where available. Use **credit ratings** (Screener) and **call transcript** takeaways for financial health and growth prospect.
- **LLM output:** 3–5 sentences: (1) position and cost, (2) sector context, (3) technical view + “bought at right time?”, (4) fundamental view (financial health + growth; cite BS, PnL, quarterly, EPS, PE, PB, ROCE, rating/transcript), (5) overall recommendation (HOLD/ADD/REDUCE/SELL).
- Output: `stock_narratives.json`, `stock_narratives.md`.

---

### Phase 6: Comprehensive report
**Goal:** Single report (MD + HTML, optionally XLSX) for the portfolio.

- **Rules:** Assemble sections in order: Portfolio summary, PnL summary, **Risk & scenarios**, **Market sentiment**, Sectoral assessment, Technical summary table, Fundamental summary table, Per-stock narratives, Appendix (data as-of date, sources).
- **Format:** Mirror `working-sector/build_comprehensive_report.py`: Markdown, interactive HTML (tabs, sortable tables), optional Excel multi-sheet.
- Output: `portfolio_comprehensive_report.md`, `portfolio_comprehensive_report.html`, optional `portfolio_comprehensive_report.xlsx`.

---

## Risk modeling and projection scenarios

**Goal:** Use **popular financial risk profilers** and **scenario projections** based on market situations and current portfolio composition.

### Risk profiler metrics (rules-based)

| Metric | Description | Use |
|--------|--------------|-----|
| **Value at Risk (VaR)** | e.g. 95% / 99% 1-day or 10-day VaR (Rs and %). Historical or parametric from portfolio returns. | Downside risk in Rs and % of portfolio. |
| **Conditional VaR (CVaR / Expected Shortfall)** | Average loss beyond VaR. | Tail risk. |
| **Sharpe ratio** | (Portfolio return − risk-free rate) / volatility (annualized). | Risk-adjusted return. |
| **Beta** | Portfolio beta vs Nifty 50 / Nifty 500 (from constituent returns and weights). | Market sensitivity. |
| **Max drawdown** | Peak-to-trough decline (%). | Worst historical loss from a peak. |
| **Volatility** | Annualized standard deviation of portfolio returns. | Total risk. |
| **Concentration** | Herfindahl or top-N weight; sector/stock concentration. | Diversification check. |
| **Correlation / contribution to risk** | Per-stock contribution to portfolio volatility. | Where risk is coming from. |

- **Inputs:** Holdings (weights), historical returns from NSE data (or proxy), risk-free rate (e.g. 91-day T-bill or config).
- **Output:** `risk_metrics.json` and `risk_metrics.csv` (per-stock and portfolio-level); summary in report.

### Projection scenarios (rules + LLM)

- **Rules:** Define 3–5 **market situations** (e.g. “Nifty +10%”, “Nifty −15%”, “Sector X outperforms”, “Broad sell-off”, “Sideways”). For each scenario, apply assumed index/segment returns and (where available) betas/correlations to **current portfolio** to get projected P&L (Rs and %).
- **LLM:** Short narrative per scenario: “If … then portfolio could …; implications for rebalancing / hedging.”
- **Output:** `scenario_projections.csv` (scenario name, portfolio return %, portfolio P&L Rs, key drivers), `scenario_narrative.md` (LLM summary).

### Data flow

- Portfolio weights from `holdings.csv` + latest prices (Phase 0 / 3).
- Historical returns from `nse_sec_full_data.csv` (and index) for VaR, beta, volatility, drawdown.
- Risk-free rate from config or external series (optional).

---

## Market sentiment and research (search + LLM)

**Goal:** **Comprehensive** sentiment and research at **sector level** and **individual stock level**, from **news** and **broker research reports**, combined with portfolio/risk via LLM.

- **Search strategy:** **Iterative** multi-round search. Use **both DDGS (DuckDuckGo)** and **SERP** (SerpAPI for Google; or googlesearch-python when SerpAPI not configured). Run each query on both engines, merge and dedupe by URL for breadth and recency.
- **Sector-level:** For each sector represented in the portfolio: search “sector name India outlook 2026”, “sector name broker report”, “sector name CRISIL/ICRA”; targeted site searches (Moneycontrol, ET, NSE, BSE, CRISIL, RBI, PIB, broker sites). LLM synthesizes one **sector sentiment** note per sector with sources and dates.
- **Stock-level:** For each holding: search “stock name stock symbol news”, “stock name analyst report”, “stock name earnings concall”; news and broker research. LLM synthesizes a short **stock-level sentiment** (news flow, analyst view, risks) with sources and dates.
- **Rules:** Iterative rounds (e.g. 2–3); multi-engine (DDGS + SERP); deduplicate by URL; add retrieval_date to every result; pass to LLM with strict “cite sources and dates”.
- **LLM:** One **market-level** summary (India equity, Nifty, macro) plus **per-sector** and **per-stock** sentiment; relate to portfolio (sector tilt, concentration, beta). All outputs must list **Sources (retrieved [date])** for verification.
- **Output:** `market_sentiment.md` (overall + sector + stock summary), `market_sentiment_sources.json`; optional `sector_sentiment_<name>.md`, `stock_sentiment_<symbol>.md` for detailed per-entity notes. Section included in comprehensive report.

Agent tools: `web_search`, `web_search_iterative` (iterative, **engines = DDGS + SERP**), `run_market_sentiment` (comprehensive: market + sector + stock, multi-engine iterative search + LLM synthesis).

---

## Agent and tools

- **Agent:** Same pattern as `working-sector/agent.py`: conversational loop with tool calling (e.g. Ollama Granite4 or OpenAI).
- **Tools:**  
  - `run_phase0` – Ingest CAS + PnL → holdings + closed_pnl.  
  - `run_phase1` – PnL summary.  
  - `run_phase2` – Sectoral assessment.  
  - `run_phase3` – Technical analysis per holding.  
  - `run_phase4` – Fundamental analysis per holding.  
  - `run_phase5` – Stock narratives.  
  - `run_phase6` – Build comprehensive report.  
  - **`run_phase7_risk`** – Risk metrics (VaR, Sharpe, beta, drawdown, concentration) + scenario projections; writes `risk_metrics.csv`, `scenario_projections.csv`, `scenario_narrative.md`.  
  - **`run_market_sentiment`** – Web search (India markets, sectors, macro) + LLM synthesis; writes `market_sentiment.md`, `market_sentiment_sources.json`.  
  - **`web_search`** – Single query (e.g. “Nifty outlook India 2026”).  
  - **`web_search_iterative`** – Multi-round search for deeper sentiment/research.  
  - `run_full_pipeline` – Run phases 0 → 7 in order, then market sentiment, then report (phase 6).  
  - `list_outputs` – List generated files.

Phases 2–4 can share code with `working-sector` (NSE data, fundamentals, technicals) where applicable.

---

## File layout (portfolio-analyzer/)

```
portfolio-analyzer/
├── PORTFOLIO_ANALYZER_DESIGN.md   # This document
├── README.md
├── config.py
├── phase0_ingest.py               # Parse CAS + PnL → holdings, closed_pnl
├── phase1_pnl_summary.py          # PnL aggregation + LLM summary
├── phase2_sectoral.py             # Sector assessment (NSE + research)
├── phase3_technical.py            # Per-stock technical + “bought right time?”
├── phase4_fundamental.py          # Per-stock fundamental (reuse working-sector)
├── phase4_fundamental.py          # Fundamental + call transcripts (NSE/Screener) + credit ratings (Screener)
├── phase5_narratives.py           # Stock narratives (LLM: technical + financial, see stock_narrative_prompt.md)
├── phase6_report.py               # Comprehensive report (MD/HTML/XLSX)
├── phase7_risk.py                 # Risk metrics (VaR, Sharpe, beta, drawdown) + scenario projections
├── market_sentiment.py            # Comprehensive sentiment: market + sector + stock (iterative DDGS + SERP)
├── stock_narrative_prompt.md      # LLM prompt: analyse technical + financial (BS, PnL, quarterly, EPS, PE, PB, ROCE)
├── pipeline_tools.py              # Agent tool definitions (incl. web_search, run_market_sentiment)
├── agent.py                       # Interactive agent loop
├── output/                        # All generated outputs
│   ├── holdings.csv
│   ├── closed_pnl.csv
│   ├── portfolio_summary.json
│   ├── pnl_summary.md
│   ├── risk_metrics.csv
│   ├── risk_metrics.json
│   ├── scenario_projections.csv
│   ├── scenario_narrative.md
│   ├── market_sentiment.md
│   ├── market_sentiment_sources.json
│   ├── sector_assessment.md
│   ├── technical_by_stock.csv
│   ├── fundamental_by_stock.csv
│   ├── stock_narratives.json
│   ├── stock_narratives.md
│   ├── portfolio_comprehensive_report.md
│   └── portfolio_comprehensive_report.html
└── data/                          # Optional: cached NSE/fundamental data
```

---

## Execution order

1. **One-time / when statements change:** Run Phase 0 (ingest).
2. **When you want full analysis:** Run Phase 0 → 1 → 2 → 3 → 4 → **7 (risk + scenarios)** → **market sentiment** → 5 → 6 (or use `run_full_pipeline`).
3. **When only PnL summary:** Phase 0 → 1.
4. **When only risk view:** Phase 0 → 7; optionally run market sentiment.
5. **When only report refresh:** If holdings/pnl unchanged, run Phase 5 → 6 (narratives + report); include risk/sentiment sections if Phase 7 and sentiment outputs exist.

---

## Dependencies

- Python 3.10+
- pandas, numpy
- For PDF: PyMuPDF or pdfplumber (Phase 0 CAS parsing).
- For LLM: ollama (local) or openai (optional).
- Reuse from project: working-sector (phase2_data, config paths), organized/data (fundamental_scores_database.csv), data/ (nse_sec_full_data.csv, nse_index_data.csv).

---

## Next steps (implementation)

1. Implement **Phase 0**: PnL CSV parser + (optional) CAS PDF/CSV → `holdings.csv`, `closed_pnl.csv`.
2. Implement **Phase 1**: PnL aggregation + stub LLM summary.
3. Wire **Phase 2**: Call working-sector sector logic or standalone NSE + web research.
4. Implement **Phase 3**: NSE price fetch, technical score, recommendation rules + LLM “bought at right time?”
5. Implement **Phase 4**: Load fundamental_scores_database + optional details; LLM narrative.
6. Implement **Phase 7**: Risk metrics (VaR, Sharpe, beta, max drawdown, concentration) from NSE returns; scenario projections (rules + LLM narrative).
7. Implement **market_sentiment.py**: Web search (reuse working-sector search) + LLM synthesis; write `market_sentiment.md` and sources JSON with dates.
8. Implement **Phase 5**: Combined narrative prompt; write JSON/MD.
9. Implement **Phase 6**: Report builder including risk, scenarios, and market sentiment sections.
10. Add **pipeline_tools.py** (with `web_search`, `web_search_iterative`, `run_market_sentiment`, `run_phase7_risk`) and **agent.py** for interactive runs.
