# Portfolio Analyzer

LLM + rules-based AI agent for portfolio analysis: ingest CDSL/NSDL and PnL reports, summarize PnL, **risk modeling and projection scenarios** (VaR, Sharpe, beta, drawdown, concentration), **market sentiment** (web search + LLM synthesis), sectoral assessment (NSE + research), technical and fundamental analysis per holding, and comprehensive report.

## Inputs

- **CAS / CDSL report:** PDF (e.g. `NSDLe-CAS_*.pdf`) or CSV export of current holdings. If the CAS PDF is **password-protected**, set `CAS_PDF_PASSWORD` in the environment so Phase 0 can extract holdings; otherwise export holdings to `holdings_export.csv` manually.
- **PnL report:** CSV (e.g. `*_EQProfitLossDetails.csv`) with equity profit/loss by trade.

Place inputs in `portfolio-analyzer/` or set paths in `config.py`.

## Phases (step-by-step)

| Phase | Purpose | Main outputs |
|-------|---------|--------------|
| **0** | Ingest | `holdings.csv`, `closed_pnl.csv`, `portfolio_summary.json` |
| **1** | PnL & portfolio summary | `pnl_summary.md`, `pnl_aggregates.csv` |
| **7** | **Risk + scenarios** | `risk_metrics.csv`, `risk_metrics.json`, `scenario_projections.csv`, `scenario_narrative.md` |
| **Sentiment** | **Market sentiment** (search + LLM) | `market_sentiment.md`, `market_sentiment_sources.json` |
| **2** | Sectoral assessment | `sector_assessment.md` (NSE + research) |
| **3** | Technical analysis | `technical_by_stock.csv`, “bought at right time?” + recommendation |
| **4** | Fundamental analysis | `fundamental_by_stock.csv`, call transcripts (NSE/Screener), credit ratings (Screener), financial health + growth (qual + quant) |
| **5** | Stock narratives | `stock_narratives.json`, `stock_narratives.md` |
| **6** | Comprehensive report | `portfolio_comprehensive_report.md`, `.html` |

**Risk profiler metrics (Phase 7):** VaR, CVaR, Sharpe, Beta, max drawdown, volatility, concentration. **Scenarios:** Nifty +10%, −15%, stress −20%, etc. **Market sentiment:** **Comprehensive** at **sector** and **stock** level (news, broker reports); **iterative search** using **DDGS (DuckDuckGo) + SERP** (Google; optional SerpAPI); LLM synthesis with cited sources. **Fundamental (Phase 4):** Call transcripts (NSE/Screener), **credit ratings** (Screener) for financial health and growth (qual + quant). **LLM narrative (Phase 5):** Analyses **technical indicators** and **financial strength** (balance sheet, P&L, quarterly, **EPS, PE, PB, ROCE**); prompt in `stock_narrative_prompt.md`.

See **PORTFOLIO_ANALYZER_DESIGN.md** for full architecture, risk metrics, scenarios, and sentiment flow.

## Quick start

```bash
# From repo root
cd "Unified-NSE-Analysis"
python portfolio-analyzer/phase0_ingest.py   # Ingest PnL (and optional holdings)
python portfolio-analyzer/phase1_pnl_summary.py
# ... then phase2–6 or run full pipeline via agent
```

## Agent (interactive)

Requires Ollama (e.g. `ollama pull granite4`) or OpenAI-compatible API. Agent can run phases, **run market sentiment** (search + LLM), and **web search** for one-off lookups.

```bash
python portfolio-analyzer/agent.py
# Then: "Run full pipeline", "Run Phase 0 and 1", "Run Phase 7 risk", "Run market sentiment", "Web search Nifty outlook India 2026", "List outputs", etc.
```

## Outputs

All generated files go to `portfolio-analyzer/output/`.

## Relation to working-sector

- Reuses NSE data paths, fundamental scores (`organized/data/fundamental_scores_database.csv`), and patterns from `working-sector` for sector view, technical/fundamental scores, and report building.
- Portfolio analyzer is **holding-centric** (your positions + PnL); working-sector is **sector-universe-centric** (screens and shortlists).
