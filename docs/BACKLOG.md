# NSE Analysis Platform — Feature Backlog
**Version:** 2.0  
**Date:** 2026-05-02  
**Owner:** Pradeep Gorai  
**Scope:** Unified-NSE-Analysis — futuristic market intelligence system roadmap

---

## 0. HOW TO USE THIS DOCUMENT

This backlog is written for a coding assistant. Each item contains:
- **What exists** — exact file names and functions already built
- **What to build** — precise spec with inputs, outputs, algorithm
- **Files to create / modify** — exact paths
- **Dependencies** — what must exist before this item can be built
- **Acceptance criteria** — how to verify it works

Items are grouped into **Phases** (P0 = foundation, P1 = core intelligence, P2 = advanced, P3 = futuristic).  
Each item has a **size estimate**: S (< 4h), M (4–16h), L (1–3 days), XL (3–7 days).

### Data Sources — Master Registry

Every external and internal data source the platform uses or will use. Items marked **NEW** are required by backlog items but not yet implemented.

#### A. Price & Volume Data (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE EOD Bhavcopy (equities) | `https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{DDMMYY}.zip` | Daily | `data/nse_sec_full_data.csv`, `data/nse_stock_cache.RData` | All analysis |
| NSE Index Data | `https://www.nseindia.com/api/allIndices`, `https://www.nseindia.com/api/equity-stockIndices?index={INDEX}` | Daily | `data/nse_index_data.csv`, `data/nse_index_cache.RData` | Regime detector, RS calc |
| NSE Index–Stock Mapping | NSE allIndices API | On-demand | `data/index_stock_mapping.csv`, `data/nse_indices_catalog.csv` | Sector classification |

#### B. Fundamental Data (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Screener.in Company Page | `https://www.screener.in/company/{SYMBOL}/` — HTML scrape via R (`rvest`) | On-demand (cache 30d) | `data/_sector_rotation_fund_cache.csv` | Fundamental scores, LLM narratives |
| Screener.in Quarterly Screen | `https://www.screener.in/screens/325075/all-latest-quarterly-results/` | On-demand | Transient | Quarterly results scan |

#### C. F&O / Derivatives Data (NEW — P1-2)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE FO Bhavcopy | `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{DDMMYYYY}_F_0000.csv.zip` | Daily | `data/_fno_signals.csv` | P1-2: OI, PCR, max pain |
| NSE Participant-wise OI | `https://archives.nseindia.com/content/nsccl/fao_participant_oi_{DATE}.csv` | Daily | `data/_fno_participant_oi.csv` | P1-2: FII net long/short |

#### D. Institutional Flow Data (NEW — P1-3)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE FII/DII Trade Activity | `https://www.nseindia.com/api/fiidiiTradeReact` | Daily | `data/fii_dii_flows.csv` | P1-3: flow signals |
| NSDL Sector-wise FII Holdings | `https://www.fpi.nsdl.co.in/web/Reports/ReportDetail.aspx` (quarterly) | Quarterly | `data/_fii_sector_holdings.csv` | P1-3: sector-level FII preference |

#### E. Insider / Promoter Data (NEW — P1-4)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE Bulk Deals | `https://archives.nseindia.com/content/equities/bulk.csv` | Daily | `data/_bulk_deals.csv` | P1-4: bulk deal alerts |
| BSE Bulk Deals | `https://api.bseindia.com/BseIndiaAPI/api/BulkDealDownload/w` | Daily | `data/_bulk_deals.csv` | P1-4: bulk deal alerts |
| NSE Promoter Pledging | `https://archives.nseindia.com/content/equities/pledge.csv` | Quarterly | `data/_promoter_pledging.csv` | P1-4: pledging alerts |
| SEBI Insider Trading Disclosures | BSE corporate filings / SEBI SAST | Event-driven | `data/_insider_alerts.csv` | P1-4: insider buy/sell |

#### F. Macro-Economic Proxy Data (NEW — P1-6)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| S&P Global / IHS Markit PMI | Public press release scrape | Monthly | `data/macro_proxy_signals.csv` | P1-6: PMI trend |
| MoSPI IIP (Industrial Production) | `https://mospi.gov.in/iip` CSV download | Monthly | `data/macro_proxy_signals.csv` | P1-6: industrial activity |
| GST Collections | MoF press release / PIB | Monthly | `data/macro_proxy_signals.csv` | P1-6: consumption proxy |
| CEA Power Generation | `https://cea.nic.in/dashboard/` daily reports | Daily | `data/macro_proxy_signals.csv` | P1-6: industrial demand proxy |
| FADA Auto Sales | FADA website monthly release | Monthly | `data/macro_proxy_signals.csv` | P1-6: auto sector signal |

#### G. Earnings Call / Concall Data (NEW — P2-5)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| BSE Corporate Filings | `https://www.bseindia.com/corporates/ann.html` — search for outcome/transcript | Quarterly | `data/concall_transcripts/{SYMBOL}_{QTR}.txt` | P2-5: concall sentiment |
| Trendlyne Concall Summaries | `https://trendlyne.com/` (free tier, limited) | Quarterly | `data/concall_transcripts/{SYMBOL}_{QTR}.txt` | P2-5: fallback source |
| Company IR Pages | Varies per company | Quarterly | `data/concall_transcripts/{SYMBOL}_{QTR}.txt` | P2-5: direct transcript |

#### H. Knowledge Graph Data (NEW — P2-1)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Screener.in Peer Comparison | `https://www.screener.in/company/{SYMBOL}/` → peers section | On-demand | `data/nse_graph.json` | P2-1: supply chain edges |
| Screener.in Company Description | Same page → about section | On-demand | `data/nse_graph.json` | P2-1: sector/promoter nodes |
| NSE Promoter Holding | Quarterly shareholding pattern | Quarterly | `data/nse_graph.json` | P2-1: promoter group edges |

#### I. LLM / AI Services (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| OpenAI API | `https://api.openai.com/v1/chat/completions` (model: `gpt-4o` or env override) | Per report run | None (transient) | LLM narratives, concall NLP |
| Ollama (local) | `http://localhost:11434` (model: `granite4:latest`) | Per report run | None (transient) | Fallback LLM |

#### J. Distribution / Output (Already Built)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Office 365 SMTP | `smtp.office365.com:587` | On-demand | None | Email reports |

#### K. Market Breadth Data (NEW — Phase 4 Branch C)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| NSE Advance/Decline | `https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500` — count advances/declines from constituent data | Daily | `data/breadth_history.csv` | C1: McClellan, C2: TRIN |
| NSE Volume by Stock | Already in `data/nse_sec_full_data.csv` — up-volume/down-volume computed from price direction | Daily | `data/breadth_history.csv` | C2: TRIN/Arms Index |
| NSE New 52W High/Low | Derived from `data/nse_sec_full_data.csv` — tag stocks at/near 52W extremes | Daily | `data/breadth_history.csv` | C1: HL breadth line |

#### L. Global Index / FX Data (NEW — Phase 4 Branch B)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Yahoo Finance Global Indices | `yfinance` or `curl` to Yahoo Finance API for SPX, FTSE, HSI, N225, DXY, USDINR | Daily | `data/global_indices.csv` | B2: Global correlation |
| Gold / Oil / Copper (commodities) | `yfinance` for GC=F, CL=F, HG=F | Daily | `data/global_indices.csv` | B2: commodity correlation |
| USDINR rate | `https://finance.yahoo.com/quote/USDINR%3DX/` or RBI API | Daily | `data/global_indices.csv` | B2, D3: FX exposure screening |

#### M. Corporate Events Data (NEW — Phase 4 Branch E)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| BSE Corporate Actions Calendar | `https://api.bseindia.com/BseIndiaAPI/api/CorpactionbulkSearch/w` | Daily | `data/corporate_events.csv` | E4: Event-driven alerts |
| NSE Corporate Actions | `https://www.nseindia.com/api/corporates-corporateActions?index=equities` | Daily | `data/corporate_events.csv` | E4: Dividends, splits, bonus |
| BSE Board Meeting Announcements | `https://api.bseindia.com/BseIndiaAPI/api/AnnualResultSearch/w` (search by announcement type) | Daily | `data/corporate_events.csv` | E4: Result date alerts |
| NSE Earnings Calendar | `https://www.nseindia.com/api/event-calendar` | Weekly | `data/corporate_events.csv` | E4: Result announcement dates |

#### N. Screener.in Peers & Deep Fundamentals (NEW — Phase 4 Branch D/E)

| Source | URL / Method | Frequency | Local Cache | Used By |
|---|---|---|---|---|
| Screener.in Peers Table | `https://www.screener.in/company/{SYMBOL}/` → `#peers` table (HTML scrape) | On-demand (cache 30d) | `data/peer_comparisons.csv` | E2: Peer comparison, D6: Moat |
| Screener.in Cash Flow Statement | Same page → `#cash-flow` table | On-demand (cache 30d) | `data/_sector_rotation_fund_cache.csv` | D2: Earnings quality (CFO data) |
| Screener.in 5-Year P&L | Same page → `#profit-loss` (5-year trend) | On-demand (cache 30d) | `data/_sector_rotation_fund_cache.csv` | D1: DuPont, A7: Quality compounder |

#### Access Notes

1. **NSE APIs require browser-like headers**: `User-Agent: Mozilla/5.0`, `Referer: https://www.nseindia.com`. Always use `curl` subprocess or `requests` with timeout + retry (macOS hang issue).
2. **Rate limiting**: 2-second sleep between NSE API calls. Screener.in: 5-second sleep.
3. **All sources are free / public**. No Bloomberg, Reuters, or paid data subscriptions required.
4. **Cache TTL defaults**: daily data = 24h, fundamental data = 30d, quarterly data = 100d, macro data = 45d.
5. **Missing data is never a blocker**: if a NEW source is unavailable, the corresponding column fills with `None` and the report still generates.

---

### Status Legend
| Icon | Meaning |
|---|---|
| 🔒 IN PROGRESS | Currently being implemented — do not start, check with owner |
| ✅ DONE | Implemented and merged into `sector_rotation_report.py` |
| 🔜 READY | Spec complete, not yet started — free to pick up |
| ⏳ BLOCKED | Waiting on a dependency item |
| 💤 DEFERRED | Intentionally deferred to a later sprint |

### Sprint 1 Status (2026-05-02)
| Item | Status | Assignee | Notes |
|---|---|---|---|
| P0-1 Signal Performance Logger | ✅ DONE | Claude | `_log_signals()` in `sector_rotation_report.py`; `resolve_signals.py` |
| P0-2 A+ Setup Classification | ✅ DONE | Claude | `_classify_setup()`, `SETUP_CLASS` column + badge in HTML |
| P0-3 Entry/Stop/Target Levels | ✅ DONE | Claude | `_compute_entry_levels()`, `ENTRY_LOW/HIGH/STOP_LOSS/TARGET_1/TARGET_2` |
| P0-4 Consolidate Data Sources | ✅ DONE | Optimus | Single cache `_sector_rotation_fund_cache.csv`; legacy sources removed; `scripts/migrate_fund_cache.py` |
| P1-1 Market Regime Detector | ✅ DONE | Claude | `regime_detector.py`; regime banner in HTML; signal log records regime |
| P1-2 F&O OI + PCR Signals | ✅ DONE | Optimus | `fetch_fno_data.py`; PCR/OI/MaxPain/Buildup/Composite signal; F&O badge in HTML |
| P1-3 FII/DII Flow Signals | ✅ DONE | Optimus | `fetch_fii_dii_flows.py`; flow banner in HTML; LLM narrative context; signal log |
| P1-4 Promoter/Insider Alerts | ✅ DONE | Optimus | `fetch_insider_alerts.py`; bulk/block/PIT/pledge alerts; insider badge in HTML; LLM narrative context; signal log |
| P1-5 Enhanced HTML Dashboard | ✅ DONE | Optimus | Paired-row sort, localStorage state, narrative search, heatmap toggle, print/PDF, 15-col mobile responsive |
| P2-1 NSE Knowledge Graph | 🔜 READY | — | P1-2 + P1-3 now complete; can proceed |
| P2-2 Counterfactual Scenarios | 🔜 READY | — | Independent. `scenario_engine.py`. |
| P2-3 Learning Loop | ⏳ BLOCKED | — | Needs P0-1 signal log to accumulate 90+ days of data |
| P2-4 Portfolio-Aware Narratives | 🔜 READY | — | Needs `portfolio-analyzer/output/holdings.csv` to exist |
| P3-1 Causal Inference Model | ⏳ BLOCKED | — | Needs 6+ months of P0-1 signal data |
| P3-2 Voice Briefing | 🔜 READY | — | `generate_voice_briefing.py`. Needs OpenAI TTS key. |
| P3-3 Real-Time Mode | 💤 DEFERRED | — | Needs live NSE data subscription |
| **Phase 4 — Branch A: Advanced Screeners** | | | |
| A1 Stage Analysis Screener | 🔜 READY | — | William O'Neil 4-stage classification; Stage 2 only buy zone |
| A2 Darvas Box Breakout | 🔜 READY | — | Box top/bottom detection; breakout + volume confirmation |
| A3 52W High Momentum | 🔜 READY | — | Near-high + rising RS; simpler variant of stage analysis |
| A4 Earnings Acceleration | ⏳ BLOCKED | — | Needs quarterly EPS series from Screener.in cash flow scrape |
| A5 Institutional Accumulation | ⏳ BLOCKED | — | Needs P1-2 (F&O OI buildup) + price analysis |
| A6 Turnaround Detector | 🔜 READY | — | Deep-dip + recovery pattern; uses existing indicators |
| A7 Quality Compounder | ⏳ BLOCKED | — | Needs 5-year P&L trend from Screener.in (source N) |
| A8 Hidden Champions | ⏳ BLOCKED | — | Needs A7 fundamentals + small-cap filter |
| **Phase 4 — Branch B: Index Reports** | | | |
| B1 Cross-Index Breadth Dashboard | ✅ DONE | Codex | `index_intelligence.py`; standalone HTML/CSV; breadth strip in sector report |
| B2 Global Correlation Monitor | 🔜 READY | — | yfinance for SPX/HSI/Gold/Oil; rolling 30d correlation |
| B3 Sectoral Heat Calendar | 🔜 READY | — | 12×N_sectors heatmap of avg monthly returns |
| B4 FII/DII Flow Battle Tracker | ⏳ BLOCKED | — | Needs P1-3 (FII/DII flows) fully running |
| B5 Economic Cycle Tracker | ⏳ BLOCKED | — | Needs P1-6 macro proxies + P1-1 regime detector |
| **Phase 4 — Branch C: Market Breadth** | | | |
| C1 McClellan Oscillator | 🔜 READY | — | Derives from Nifty500 constituent advance/decline data |
| C2 TRIN / Arms Index | 🔜 READY | — | Volume-weighted breadth; derives from existing OHLCV |
| C3 Sector Breadth Divergence | 🔜 READY | — | Sector-level % above 50/200DMA; divergence alerts |
| C4 Smart Money Flow Index | ⏳ BLOCKED | — | Needs P1-2 F&O + block deal data |
| **Phase 4 — Branch D: Deep Fundamentals** | | | |
| D1 DuPont Decomposition Engine | ⏳ BLOCKED | — | Needs 5-year P&L + balance sheet from Screener.in |
| D2 Earnings Quality Score | ⏳ BLOCKED | — | Needs CFO data from Screener.in cash flow scrape |
| D3 Business Cycle Positioning | ⏳ BLOCKED | — | Needs P1-6 macro proxies |
| D4 Concall Sentiment NLP | 🔜 READY | — | Same as P2-5; BSE filings + LLM extraction |
| D5 Forensic Accounting Suite | ⏳ BLOCKED | — | Needs Screener.in 5-year P&L + balance sheet (source N) |
| D6 Competitive Moat Score | ⏳ BLOCKED | — | Needs D1 + D2 data; peer comparison data (source N) |
| **Phase 4 — Branch E: Company Analysis** | | | |
| E1 360° Company Dashboard | ⏳ BLOCKED | — | Needs D1–D6 data; E2 peer data; E4 events |
| E2 Peer Comparison Engine | ⏳ BLOCKED | — | Needs Screener.in peers scrape (source N) |
| E3 Management Quality Score | ⏳ BLOCKED | — | Needs P1-4 insider data + concall history (D4) |
| E4 Event-Driven Alert Engine | 🔜 READY | — | BSE/NSE corporate actions API (source M) |

---

## 1. CURRENT STATE ASSESSMENT

### 1.1 What Is Already Built (Do Not Rebuild)

| Capability | File(s) | Status | Quality |
|---|---|---|---|
| NSE OHLCV data load (all stocks) | `load_latest_nse_data_comprehensive.R`, `data/nse_sec_full_data.csv` | ✅ Done | Production |
| NSE index data load | `data/nse_index_data.csv`, `data/nse_index_cache.RData` | ✅ Done | Production |
| Sector rotation ranking (RS vs Nifty500) | `sector_rotation_report.py` → `_build_sector_rank()` | ✅ Done | Production |
| Investment candidate screening (37 stocks) | `sector_rotation_report.py` → `screen_candidates()` | ✅ Done | Production |
| Technical indicators: RSI, Supertrend, Volume, Patterns | `sector_rotation_report.py`, `core/technical_analysis_engine.R` | ✅ Done | Production |
| LLM narratives (gpt-5.5 via OpenAI, two-phase) | `sector_rotation_report.py` → `_generate_llm_narratives()` | ✅ Done | Production |
| Fundamental data fetch (Screener.in via R) | `working-sector/fetch_screener_fundamental_details.R` | ✅ Done | Production |
| Persistent fundamental cache | `data/_sector_rotation_fund_cache.csv` | ✅ Done | Production |
| HTML report (sector pills, table, narratives) | `sector_rotation_report.py` → `_build_html()` | ✅ Done | Production |
| CAN-SLIM scoring | `apex_resilience_full_report.py` | ✅ Done | Good |
| Minervini score | `apex_resilience_full_report.py` | ✅ Done | Good |
| Portfolio analyzer (7-phase) | `portfolio-analyzer/run_pipeline.py` | ✅ Done | Good |
| Market breadth (DMA breakouts) | `analyze_comprehensive_market_breadth.R` | ✅ Done | Good |
| Backtesting framework | `run_comprehensive_backtesting_all_stocks.R`, `working-sector/phase4_backtest.py` | ✅ Done | Good |
| Email distribution | `email_nse_reports.py` | ✅ Done | Good |
| SQLite results database | `nse_analysis.db` | ✅ Done | Partial |

### 1.2 What Is Partially Built (Needs Completion)

| Capability | File(s) | Gap |
|---|---|---|
| Signal performance tracking | `backlog.md` (planned), no impl | No outcome tracking; signals never measured |
| A+ setup classification | `backlog.md` (specified), no impl | Current: generic BUY/HOLD/SELL signals |
| Entry / stop / target levels | `sector_rotation_report.py` (resistance/support exist) | No formal entry zones, only raw levels |
| F&O open interest integration | Not started | F&O data not fetched or used |
| Regime detection | Not started | All signals applied uniformly regardless of market regime |
| Portfolio-aware narrative | Not started | Narratives are generic, not portfolio-context-aware |

### 1.3 What Does Not Exist Yet (New Build Required)

- Market regime detector (HMM / changepoint)
- F&O OI + PCR signals
- FII/DII institutional flow signals
- Knowledge graph (supply chain + promoter linkages)
- Causal inference model
- Counterfactual scenario engine
- Promoter pledging / insider activity alerts
- Learning loop (signal outcome tracking + weight recalibration)
- Macro-economic proxy signals (GST e-way bills, PMI, IIP, power generation)
- Earnings call NLP / concall sentiment scoring
- Voice / WhatsApp briefing output
- Real-time / streaming mode

---

## 2. BACKLOG — PHASE 0: FOUNDATIONS (No New Features, Fix & Standardise)

### P0-1 — Signal Performance Logger
**Size:** M  
**Priority:** Critical (feeds the learning loop in P2)

**What exists:** Signals are generated in `sector_rotation_report.py` but never persisted for outcome measurement.

**What to build:**
```
File to create: data/signal_log.csv
Columns: date_issued, symbol, sector, signal (BUY/HOLD/SELL), 
         investment_score, price_at_issue, target_price (resistance),
         stop_price (supertrend_value), horizon_days (5/22/66),
         date_resolved, price_at_resolution, hit_target (bool),
         hit_stop (bool), return_pct, regime_at_issue
```

**Implementation in `sector_rotation_report.py`:**
1. After `screen_candidates()` finishes, call `_log_signals(candidates, date)`.
2. `_log_signals()`: for each candidate row, append one row to `data/signal_log.csv` if not already logged for that date+symbol.
3. Separately, a weekly job `resolve_signals.py` reads the log, checks current prices, marks `hit_target`/`hit_stop`, computes `return_pct`.

**Acceptance criteria:**
- `data/signal_log.csv` grows by ~37 rows each time `sector_rotation_report.py` runs.
- Re-running on the same date does not duplicate rows.
- `resolve_signals.py --days 5` marks all 5-day-old signals as resolved.

---

### P0-2 — A+ Setup Classification
**Size:** M  
**Priority:** High

**What exists:** `sector_rotation_report.py` has `TRADING_SIGNAL` (BUY/HOLD/SELL/WEAK_SELL) and `PATTERN` (CONSOLIDATION_BREAKOUT etc). The existing `backlog.md` has a spec.

**What to build:**  
Add a new column `SETUP_CLASS` to candidates with these values (in priority order):

| Setup Class | Conditions | Meaning |
|---|---|---|
| `LEADER_BREAKOUT` | PATTERN=CONSOLIDATION_BREAKOUT AND VOL_RATIO>1.5 AND RSI 55-72 AND SUPERTREND=BULLISH | High-conviction institutional breakout |
| `FAST_RECOVERY` | ret_5d > +3% AND ret_1m > +8% AND was below 50DMA 10 days ago | Post-correction momentum recovery |
| `BASE_NEAR_HIGH` | price within 5% of 52-week high AND RSI 50-65 AND vol_ratio < 1.2 | Quiet accumulation near highs |
| `PULLBACK_IN_UPTREND` | SUPERTREND=BULLISH AND RSI 38-52 AND ret_5d < -2% | Buy-the-dip in established uptrend |
| `MOMENTUM_EXTENDED` | RSI > 72 AND ret_1m > +15% | Overbought — reduce/trail only |
| `WEAK_TREND` | SUPERTREND=BEARISH OR ret_1m < -5% | Avoid / exit |
| `NEUTRAL` | Everything else | Monitor |

**Files to modify:**
- `sector_rotation_report.py` → `screen_candidates()` — add `SETUP_CLASS` column using `pd.cut` / `np.select` logic after all indicators are computed.
- HTML template — add `SETUP_CLASS` as a color-coded badge next to the signal badge.

**Acceptance criteria:**
- Every candidate row has a non-null `SETUP_CLASS`.
- `LEADER_BREAKOUT` and `FAST_RECOVERY` appear prominently in the HTML with distinct badge colors.

---

### P0-3 — Formal Entry / Stop / Target Levels
**Size:** S  
**Priority:** High

**What exists:** `RESISTANCE`, `SUPPORT`, `SUPERTREND_VALUE` are already computed and shown in the table.

**What to build:**  
Compute three new columns using existing values:

```python
# Entry zone
ENTRY_LOW  = current_price * 0.99          # 1% below current (limit order zone)
ENTRY_HIGH = min(resistance * 0.995, current_price * 1.02)  # just below resistance

# Stop loss (tightest of: Supertrend level, 2% below support, 6% below entry)
STOP_LOSS = max(supertrend_value, support * 0.98, entry_low * 0.94)

# Target (first resistance, then 1.5x risk-reward above entry)
RISK = entry_low - STOP_LOSS
TARGET_1 = resistance
TARGET_2 = entry_low + (RISK * 2.5)        # 2.5:1 risk-reward
```

**Files to modify:**  
`sector_rotation_report.py` → add computation after existing indicator calc → include in HTML table and LLM prompt.

---

### P0-4 — Deduplicate and Consolidate Data Sources
**Size:** S  
**Priority:** Medium

**What exists:** Fundamental data comes from 3 overlapping sources:
- `reports/Apex_Resilience_screener_fundamentals_20260428.csv`
- `working-sector/output/fundamental_details.csv`
- `data/_sector_rotation_fund_cache.csv` (now primary)

**What to build:**  
- Remove the two legacy sources from `_load_fundamental_details()` — use only `_sector_rotation_fund_cache.csv`.
- Add a one-time migration script `scripts/migrate_fund_cache.py` that merges all three into the cache (already done manually; formalise it).
- Delete `data/_sector_rotation_fund_tmp.csv` after each successful merge.

---

## 3. BACKLOG — PHASE 1: CORE INTELLIGENCE (High ROI, Buildable Now)

### P1-1 — Market Regime Detector
**Size:** L  
**Priority:** Critical — gates all signal weighting in P1-2 onward

**What exists:** Nothing. All signals applied uniformly regardless of market state.

**What to build:**  
**File to create:** `regime_detector.py`

**Algorithm:**  
Use a 4-state Hidden Markov Model (HMM) on daily Nifty500 returns + volatility:

```python
# Input features (daily, last 252 trading days):
features = [
    nifty500_daily_return,      # % change
    rolling_20d_volatility,     # std of daily returns
    advance_decline_ratio,      # from analyze_comprehensive_market_breadth.R output
    pct_stocks_above_200dma,    # from breadth analysis
]

# States (4):
BULL_TREND    = 0  # sustained uptrend, low vol, broad participation
ROTATION      = 1  # mixed returns, sector divergence, churning
CHOP          = 2  # low directional movement, high noise
BEAR_TREND    = 3  # sustained downtrend, high vol, narrow breadth

# Library: hmmlearn (pip install hmmlearn)
from hmmlearn.hmm import GaussianHMM
model = GaussianHMM(n_components=4, covariance_type="full", n_iter=200)
```

**Signal weight multipliers by regime:**

| Signal Type | BULL_TREND | ROTATION | CHOP | BEAR_TREND |
|---|---|---|---|---|
| Momentum (RSI>60, breakout) | 1.5x | 1.2x | 0.4x | 0.2x |
| Sector RS | 1.0x | 2.0x | 0.8x | 0.5x |
| Mean reversion (pullback) | 0.5x | 0.8x | 1.5x | 1.0x |
| Fundamental quality | 1.0x | 1.5x | 2.0x | 2.5x |
| Defensive sectors | 0.5x | 0.8x | 1.5x | 3.0x |

**Output:**
```python
{
  "current_regime": "ROTATION",
  "confidence": 0.81,
  "regime_duration_days": 12,
  "previous_regime": "BULL_TREND",
  "regime_history": [...],  # last 90 days
}
```

**Integration into `sector_rotation_report.py`:**
1. Call `detect_regime()` at start of `generate_report()`.
2. Pass `regime` into `screen_candidates()` → multiply `INVESTMENT_SCORE` by regime weights.
3. Add regime badge to HTML header: `🔄 ROTATION (confidence: 81%)`.
4. Pass regime to LLM prompt: "Current market regime: ROTATION (12 days). Weight sector RS signals heavily."

**Dependencies:** `hmmlearn`, breadth CSV output from `analyze_comprehensive_market_breadth.R`  
**Acceptance criteria:**
- Regime output is deterministic for the same input date.
- Regime changes are logged in `data/regime_history.csv`.
- HTML report shows current regime badge.

---

### P1-2 — F&O Open Interest + Put-Call Ratio Signals
**Size:** L  
**Priority:** High

**What exists:** Nothing. Price/volume data only.

**What to build:**  
**File to create:** `fetch_fno_data.py`

**Data source:** NSE FO bhavcopy (free, daily)
```
URL pattern: https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{DDMMYYYY}_F_0000.csv.zip
Headers required: {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com"}
```

**Signals to compute per symbol (where F&O data exists):**

```python
# 1. Put-Call Ratio (PCR) — by Open Interest
PCR = sum(put_OI) / sum(call_OI)
# PCR > 1.2: bullish (more puts = fear, contrarian positive)
# PCR < 0.7: bearish (complacency, too many calls)
# PCR 0.9-1.1: neutral

# 2. OI Change % (5-day rolling)
OI_CHANGE_5D = (current_oi - oi_5d_ago) / oi_5d_ago * 100
# OI_CHANGE > +20% with price up: strong bull conviction
# OI_CHANGE > +20% with price down: strong bear conviction (short buildup)

# 3. Max Pain (price where maximum options expire worthless)
# Compute for each expiry: sum of pain for all strikes
MAX_PAIN = argmin(sum(strike_pain for all_strikes))

# 4. COT-style: net institutional positioning
# From participant-wise OI: FII vs Client positions
FII_NET_LONG = fii_long_oi - fii_short_oi
```

**Output:** `data/fno_signals.csv` with columns: `date, symbol, pcr, oi_change_5d, max_pain, fii_net_long, signal (BULL/BEAR/NEUTRAL)`

**Integration:**  
- Merge `fno_signals.csv` into `screen_candidates()` on `SYMBOL`.
- Add `FNO_SIGNAL` column to candidates.
- Add `FNO_SIGNAL` to LLM prompt data and HTML table.

**Acceptance criteria:**
- `fetch_fno_data.py --date 2026-05-02` downloads and processes FO bhavcopy.
- PCR and OI change computed for all F&O-eligible symbols.
- Missing for non-F&O stocks: fill with `None`.

---

### P1-3 — FII / DII Daily Flow Signals
**Size:** M  
**Priority:** High

**What exists:** Nothing.

**What to build:**  
**File to create:** `fetch_fii_dii_flows.py`

**Data source:** NSE institutional activity report (free)
```
URL: https://www.nseindia.com/api/fiidiiTradeReact
Fallback URL: https://archives.nseindia.com/content/nsccl/fao_participant_oi_{date}.csv
```

**Signals:**
```python
# Rolling 5-day FII net buy/sell
FII_NET_5D = sum(fii_net_daily for last 5 days)  # crores
DII_NET_5D = sum(dii_net_daily for last 5 days)

# Signal rules:
if FII_NET_5D > 3000:  signal = "FII_BUYING" 
if FII_NET_5D < -3000: signal = "FII_SELLING"
if DII_NET_5D > 2000 and FII_NET_5D > 0: signal = "BOTH_BUYING"  # strongest
if DII_NET_5D > 2000 and FII_NET_5D < 0: signal = "DII_ABSORBING"  # support

# Sector-level FII preference (from sector FII holdings data - quarterly)
# Use NSDL sector-wise FII holding % change as sector-level signal
```

**Output:** `data/fii_dii_flows.csv` — daily: `date, fii_net, dii_net, fii_net_5d, dii_net_5d, flow_signal`

**Integration into `sector_rotation_report.py`:**
- Compute `FII_FLOW_SIGNAL` and append to sector rank table.
- In sector narrative prompt: "FII net last 5 days: +₹4,230 Cr (BUYING)"
- Regime detector: use `FII_NET_5D` as one of the features.

---

### P1-4 — Promoter Pledging & Insider Activity Alerts
**Size:** M  
**Priority:** Medium

**What exists:** Nothing.

**What to build:**  
**File to create:** `fetch_insider_alerts.py`

**Data source:** BSE/NSE bulk/block deal files + SEBI insider trading disclosures
```
BSE bulk deals: https://api.bseindia.com/BseIndiaAPI/api/BulkDealDownload/w
NSE bulk deals: https://archives.nseindia.com/content/equities/bulk.csv (daily)
Promoter pledging: https://archives.nseindia.com/content/equities/pledge.csv (quarterly)
```

**Signals:**
```python
# Alert types:
PROMOTER_PLEDGING_INCREASE  # pledged % rose > 5pp in last quarter → RED FLAG
PROMOTER_BUYING             # promoter acquired open market shares → POSITIVE
BULK_DEAL_BUY               # large investor bought > 0.5% in single session → POSITIVE  
BULK_DEAL_SELL              # large investor sold > 0.5% → NEGATIVE
INSIDER_BUY                 # director/officer bought → MODERATE POSITIVE
```

**Output:** `data/insider_alerts.csv` — `date, symbol, alert_type, qty, value_cr, entity`

**Integration:**
- Merge alerts into candidates (last 30 days).
- Add `INSIDER_ALERT` badge in HTML table.
- Include in LLM prompt: "Promoter bought 0.3% last week — insider conviction signal."

---

### P1-5 — Enhanced HTML Dashboard (UX Pass)
**Size:** M  
**Priority:** Medium

**What exists:** `sector_rotation_report.py` HTML is functional. Pills slide, table has fixed layout.

**What to add:**

1. **Regime banner at top of page**: colored stripe (green=BULL, amber=ROTATION, grey=CHOP, red=BEAR) with regime name, confidence %, duration days.

2. **Sortable table columns**: add `data-sort` attributes; JS click handler sorts by that column ascending/descending.

3. **Persistent sort/filter state**: store in `localStorage` so refreshing page keeps user's selected sector + sort.

4. **Heatmap view toggle**: button switches table to a 10-column heatmap (investment score → red/amber/green cells) for quick visual scanning.

5. **Narrative search**: text box filters stocks whose narratives contain the typed keyword.

6. **Print / PDF export**: `window.print()` with `@media print` CSS hiding nav/controls.

**Files to modify:** `sector_rotation_report.py` → `_build_html()` CSS and JS sections.

---

### P1-6 — Macro-Economic Proxy Signals
**Size:** L  
**Priority:** Medium

**What exists:** Nothing. No macro data ingested; all signals are price/volume-only.

**What to build:**  
**File to create:** `fetch_macro_proxies.py`

**Data sources (all free / public):**

| Indicator | Source | Frequency | URL / Method |
|---|---|---|---|
| GST e-way bills | GST portal monthly release | Monthly | Parse press releases or MoF dashboard CSV |
| Manufacturing PMI | IHS Markit / S&P Global | Monthly | Scrape headline PMI from public release |
| IIP (Index of Industrial Production) | MoSPI | Monthly | `https://mospi.gov.in/iip` CSV download |
| Power generation (thermal + renewables) | CEA daily reports | Daily | `https://cea.nic.in/dashboard/` |
| Cement dispatches | CMA monthly | Monthly | Manual / press release |
| Auto sales (SIAM / FADA) | FADA website | Monthly | Parse FADA monthly release |

**Signals to compute:**
```python
# 1. PMI trend
PMI_TREND = "EXPANDING" if pmi > 50 and pmi > pmi_prev else "CONTRACTING"

# 2. Power generation momentum (proxy for industrial activity)
POWER_GEN_MOM = (power_gen_this_month - power_gen_same_month_last_year) / power_gen_same_month_last_year * 100

# 3. GST collection growth (proxy for consumption + economic activity)
GST_GROWTH = (gst_current - gst_same_month_ly) / gst_same_month_ly * 100

# 4. Sector mapping:
# High PMI + rising power → boost Industrials, Capital Goods, Metals
# Rising GST + auto sales → boost Consumer Discretionary, Auto
# Falling PMI + falling power → boost Defensives (FMCG, Pharma, IT)

SECTOR_MACRO_BOOST = {
    "Capital Goods": pmi_score * 0.4 + power_score * 0.3 + iip_score * 0.3,
    "Metals & Mining": pmi_score * 0.3 + power_score * 0.4 + iip_score * 0.3,
    "Auto": auto_sales_score * 0.5 + gst_score * 0.3 + pmi_score * 0.2,
    "FMCG": gst_score * 0.5 + (-pmi_score) * 0.2,  # inverse: benefits from defensive rotation
    # ... other sectors
}
```

**Output:** `data/macro_proxy_signals.csv` — monthly: `date, indicator, value, yoy_change_pct, trend, sector_impact`

**Integration into `sector_rotation_report.py`:**
- Load latest macro signals at start of `generate_report()`.
- Add `MACRO_TAILWIND` score to sector rank table (sum of sector-mapped macro boosts).
- Pass macro context to LLM prompt: "Macro backdrop: PMI 56.2 (expanding), power generation +8% YoY, GST collections +12% YoY — supportive for industrials."
- Regime detector (P1-1): use macro scores as additional HMM features for regime classification.

**Dependencies:** None (standalone data ingestion)  
**Acceptance criteria:**
- `fetch_macro_proxies.py --refresh` downloads and caches latest available data.
- Stale data (>45 days) triggers a warning but does not block report generation.
- `data/macro_proxy_signals.csv` has at least PMI + power generation rows.
- Sector rank table includes `MACRO_TAILWIND` column.

---

## 4. BACKLOG — PHASE 2: ADVANCED INTELLIGENCE

### P2-1 — NSE Knowledge Graph
**Size:** XL  
**Priority:** High (structural edge, hard to replicate)

**What exists:** `data/index_stock_mapping.csv` has stock↔index membership. Company descriptions exist via Screener.in.

**What to build:**  
**Files to create:** `knowledge_graph.py`, `data/nse_graph.json`

**Graph schema:**
```python
Nodes: {
  "COCHINSHIP": {
    "type": "stock",
    "sector": "Defence & Shipbuilding",
    "market_cap_cr": 45000,
    "promoter_name": "Cochin Shipyard Ltd (Govt of India)",
    "promoter_holding_pct": 72.86,
  }
}

Edges: [
  # Supply chain (from screener.in 'peers' + sector classification)
  {"from": "ONGC", "to": "WELCORP", "type": "supply_chain", "weight": 0.6, "note": "steel pipes for oil & gas"},
  {"from": "ONGC", "to": "BHEL", "type": "supply_chain", "weight": 0.5, "note": "equipment"},
  
  # Promoter group (same promoter entity)
  {"from": "TATASTEEL", "to": "TATAPOWER", "type": "promoter_group", "weight": 1.0, "note": "Tata Sons"},
  
  # Sector peers (high correlation in returns)
  {"from": "COCHINSHIP", "to": "MAZDOCK", "type": "sector_peer", "weight": 0.85},
  
  # Debt exposure (same lender)
  {"from": "ADANIPORTS", "to": "ADANIGREEN", "type": "group_debt", "weight": 0.9},
]
```

**Build process:**
1. `build_graph.py` — one-time script: parse company descriptions, sector tags, promoter data from `data/_sector_rotation_fund_cache.csv` and Screener.in JSON → build `data/nse_graph.json`.
2. `knowledge_graph.py` — runtime module: load graph, expose `get_downstream_impact(symbol, shock_magnitude)`.

**Shock propagation algorithm:**
```python
def propagate_shock(graph, source_symbol, shock_pct, depth=2):
    """
    If ONGC gets SELL signal (-8%), compute impact on connected nodes.
    Returns: dict of {symbol: estimated_impact_pct}
    """
    visited = {source_symbol: shock_pct}
    queue = [(source_symbol, shock_pct)]
    for _ in range(depth):
        next_queue = []
        for node, impact in queue:
            for edge in graph.edges(node):
                if edge.type in ["supply_chain", "promoter_group"]:
                    child_impact = impact * edge.weight * 0.4  # 40% propagation
                    if abs(child_impact) > 1.0:  # only meaningful impacts
                        visited[edge.to] = child_impact
                        next_queue.append((edge.to, child_impact))
        queue = next_queue
    return visited
```

**Integration:** Call `propagate_shock()` in `sector_rotation_report.py`; add `GRAPH_SIGNAL` column (upstream shock warning / beneficiary).

---

### P2-2 — Counterfactual Scenario Engine
**Size:** L  
**Priority:** Medium

**What exists:** Single deterministic run. No scenario analysis.

**What to build:**  
**File to create:** `scenario_engine.py`

**Design:**
```python
SCENARIOS = [
    {
        "name": "RBI Rate Cut -25bps",
        "macro_shocks": {"rate_sensitive_sectors": +0.06},  # 6% boost to rate-sensitive
        "sector_adjustments": {
            "Real Estate": +8, "Banking": +5, "Energy": +3, "IT": -2
        },
        "trigger": "rbi_rate_decision_next_week",
    },
    {
        "name": "FII Sell-off ₹5,000 Cr",
        "flow_shock": -5000,
        "sector_adjustments": {
            "Smallcap": -10, "Midcap": -7, "Largecap": -4, "FMCG": +2
        },
    },
    {
        "name": "USDINR crosses ₹85",
        "fx_shock": 85.5,
        "sector_adjustments": {
            "IT": +8, "Pharma": +5, "Metals": -6, "Oil & Gas": -8
        },
    },
    {
        "name": "China slowdown (commodity demand drop)",
        "sector_adjustments": {
            "Metals": -12, "Mining": -10, "Chemical": -5, "Defence": +3
        },
    },
]

def run_scenario(base_candidates, base_sector_rank, scenario) -> dict:
    """Apply macro shocks to base scores, return adjusted rankings."""
    adjusted = base_candidates.copy()
    for sector, delta in scenario["sector_adjustments"].items():
        mask = adjusted["SECTOR_NAME"] == sector
        adjusted.loc[mask, "INVESTMENT_SCORE"] += delta
        adjusted.loc[mask, "SCENARIO_ADJUSTMENT"] = delta
    return adjusted
```

**HTML integration:** Add a "Scenarios" tab to the existing pills bar. Each scenario shows the re-ranked candidates and which sectors benefit/suffer.

---

### P2-3 — Learning Loop (Signal Outcome Tracking)
**Size:** L  
**Priority:** High (requires P0-1 signal logger to exist first)

**What exists:** P0-1 signal logger (to be built). No outcome tracking today.

**What to build:**  
**File to create:** `learning_loop.py`

**Weekly job:**
```python
def analyze_signal_performance(log_path="data/signal_log.csv", lookback_days=90):
    """
    Read resolved signals. Compute hit rates by:
    - signal type (BUY/HOLD/SELL)
    - setup class (LEADER_BREAKOUT / FAST_RECOVERY etc)
    - regime at issue (BULL/ROTATION/CHOP/BEAR)
    - sector
    - horizon (5d / 22d / 66d)
    
    Output:
    - data/signal_performance_summary.csv
    - Calibration adjustments: which setups/regimes outperform
    """
    df = pd.read_csv(log_path)
    resolved = df[df["date_resolved"].notna()]
    
    # Hit rate by setup class + regime
    perf = resolved.groupby(["setup_class", "regime_at_issue", "horizon_days"]).agg(
        hit_rate=("hit_target", "mean"),
        avg_return=("return_pct", "mean"),
        n=("symbol", "count"),
    ).reset_index()
    
    # Output calibration multipliers
    # e.g.: LEADER_BREAKOUT in ROTATION regime, 22d: hit_rate=0.68, avg_return=+9.2%
    # → confidence multiplier = 0.68 / 0.50 (baseline) = 1.36
    perf["calibration_multiplier"] = perf["hit_rate"] / 0.50
    perf.to_csv("data/signal_calibration.csv", index=False)
    return perf
```

**Integration into `sector_rotation_report.py`:**
- Load `data/signal_calibration.csv` at start.
- Apply calibration multipliers to `INVESTMENT_SCORE` before ranking.
- Add to HTML: "Signal calibration: LEADER_BREAKOUT in ROTATION regime → 68% hit rate (last 90 days)"

---

### P2-4 — Portfolio-Aware Personalised Narratives
**Size:** L  
**Priority:** High

**What exists:** `portfolio-analyzer/` has holdings data. LLM narratives are generic.

**What to build:**  
In `sector_rotation_report.py`:

1. **Load portfolio holdings** at start of `generate_report()`:
   ```python
   portfolio = _load_portfolio()  # reads portfolio-analyzer/output/holdings.csv
   # Returns: {symbol: {avg_cost, qty, current_value, unrealised_pnl_pct, weight_pct}}
   ```

2. **Enrich LLM prompt** with portfolio context per stock:
   ```python
   if sym in portfolio:
       p = portfolio[sym]
       stock_line += f"\n    PORTFOLIO: Held {p['qty']} shares @ avg ₹{p['avg_cost']:.2f} "
       stock_line += f"(unrealised: {p['unrealised_pnl_pct']:+.1f}%, weight: {p['weight_pct']:.1f}%)"
   ```

3. **Add portfolio-specific LLM instruction:**
   ```
   - If stock is already held: tailor advice to position management (when to add, when to trail, when to book).
   - If stock is NOT held: tailor advice to entry decision.
   - If concentration > 5% in sector: flag as overweight, recommend trim rather than add.
   ```

**Acceptance criteria:** LLM narrative for a held stock mentions: avg cost, unrealised P&L %, and gives hold/trim/add guidance instead of a generic entry signal.

---

### P2-5 — Earnings Call NLP / Concall Sentiment Scoring
**Size:** L  
**Priority:** Medium

**What exists:** Nothing. No earnings call data ingested; fundamental analysis relies on static ratios from Screener.in.

**What to build:**  
**Files to create:** `fetch_concall_transcripts.py`, `concall_sentiment.py`

**Data sources:**

| Source | Coverage | Access |
|---|---|---|
| BSE corporate filings (outcome / transcript PDFs) | All listed companies | Free — `https://www.bseindia.com/corporates/ann.html` |
| Trendlyne concall summaries | Top 500 | Free tier (limited); API for premium |
| Screener.in annual report PDFs | Top 500 | Free |
| Company investor relations pages | Varies | Free (manual scrape per company) |

**Pipeline:**
```python
# Step 1: Fetch latest earnings call transcript (PDF / text)
def fetch_latest_concall(symbol: str) -> str:
    """
    Try BSE filings first (search for 'outcome' or 'transcript' in recent filings).
    Fallback: Trendlyne concall summary page.
    Return: raw text of the earnings call / management commentary.
    """

# Step 2: Extract sentiment and key signals using LLM
def score_concall_sentiment(transcript_text: str, symbol: str) -> dict:
    """
    Use existing _llm_call() to extract structured signals from concall text.
    
    LLM prompt extracts:
    - management_tone: CONFIDENT | CAUTIOUS | DEFENSIVE | EVASIVE
    - guidance_direction: RAISED | MAINTAINED | LOWERED | WITHDRAWN
    - key_themes: list of 3-5 themes (e.g., 'capacity expansion', 'margin pressure')
    - risk_flags: list of concerns mentioned (e.g., 'raw material cost', 'demand slowdown')
    - capex_signal: EXPANDING | STABLE | CUTTING
    - order_book_trend: GROWING | STABLE | DECLINING (for capital goods / infra)
    - sentiment_score: -1.0 to +1.0 (overall tone)
    
    Returns: dict with all above fields
    """
    prompt = f"""
    Analyse this earnings call transcript for {symbol}.
    Extract:
    1. Management tone (CONFIDENT/CAUTIOUS/DEFENSIVE/EVASIVE)
    2. Guidance direction (RAISED/MAINTAINED/LOWERED/WITHDRAWN)
    3. Top 3-5 key themes discussed
    4. Risk flags or concerns raised
    5. Capex outlook (EXPANDING/STABLE/CUTTING)
    6. Order book trend if applicable (GROWING/STABLE/DECLINING)
    7. Overall sentiment score from -1.0 (very bearish) to +1.0 (very bullish)
    
    Respond as JSON only.
    
    Transcript:
    {transcript_text[:8000]}  # truncate to fit context
    """
    return _llm_call(prompt, parse_json=True)
```

**Output:** `data/concall_sentiment.csv` — per earnings call:
```
symbol, quarter, call_date, management_tone, guidance_direction,
sentiment_score, capex_signal, key_themes, risk_flags, transcript_source
```

**Integration into `sector_rotation_report.py`:**
- Load latest concall sentiment per candidate symbol.
- Add `CONCALL_TONE` and `CONCALL_SENTIMENT` columns to candidates.
- Include in LLM narrative prompt: "Latest concall (Q4FY26): management tone CONFIDENT, guidance RAISED, capex EXPANDING. Key themes: capacity expansion, export order wins."
- Adjust `INVESTMENT_SCORE`: sentiment_score > 0.5 adds +3 to score; sentiment_score < -0.3 subtracts -3.

**Cache strategy:**
- Concall data is quarterly; cache TTL = 100 days.
- Store raw transcript text in `data/concall_transcripts/{symbol}_{quarter}.txt` for audit.
- Re-fetch only when a new quarter's filing is detected.

**Dependencies:** `_llm_call()` from `sector_rotation_report.py`, BSE filing access  
**Acceptance criteria:**
- `fetch_concall_transcripts.py --symbol TATASTEEL` downloads latest available transcript.
- `concall_sentiment.py --symbol TATASTEEL` returns valid JSON with all required fields.
- Missing transcripts result in `CONCALL_TONE = None` (not an error).
- At least 60% of Nifty 500 stocks have concall data within 120 days of latest results.

---

## 5. BACKLOG — PHASE 3: FUTURISTIC (High Complexity, High Impact)

### P3-1 — Causal Inference Model (Replace Technical Indicators)
**Size:** XL  
**Priority:** Medium (requires 2+ years of signal log data from P0-1)

**What to build:**  
Replace RSI/Supertrend scoring with causal model predictions using `econml` or `dowhy`.

**Design:**
```python
# Treatment variable: FII_NET_5D_POSITIVE (binary: >1500cr = 1, else 0)
# Outcome: forward_return_22d
# Confounders: sector_momentum, market_regime, macro_state

from econml.dml import CausalForestDML
model = CausalForestDML(
    model_t=RandomForestClassifier(),
    model_y=RandomForestRegressor(),
    discrete_treatment=True,
    n_estimators=200,
)
model.fit(Y=forward_returns, T=treatment, X=features, W=confounders)
# Effect: heterogeneous treatment effect per stock
effect, lb, ub = model.effect_interval(X_test)
```

**Note:** Requires minimum 500 resolved signals (2–3 years at current pace). Start building signal log (P0-1) immediately.

---

### P3-2 — Voice Briefing (60-Second Daily Audio)
**Size:** M  
**Priority:** Low-medium

**What to build:**  
**File to create:** `generate_voice_briefing.py`

```python
# After report generates, synthesise a 60-second script:
script = f"""
NSE Market Briefing for {today}.
Market regime: {regime['current_regime']} with {regime['confidence']*100:.0f}% confidence.
Top rotating sector: {top_sector['SECTOR_NAME']}, rotation score {top_sector['ROTATION_SCORE']:.1f}.
FII flows: net {fii_net_5d:+,.0f} crores over 5 days — {flow_signal}.
Top investment candidates: {', '.join(top_3_candidates)}.
Watch: {watch_stock} approaching resistance at {resistance:.0f} rupees.
"""

# TTS via OpenAI:
import openai
response = openai.audio.speech.create(model="tts-1", voice="nova", input=script)
response.stream_to_file(f"reports/briefing_{today}.mp3")
```

---

### P3-3 — Real-Time / Intraday Mode
**Size:** XL  
**Priority:** Low (requires live NSE data subscription)

**What exists:** `core/intraday_yahoo.R` has intraday analysis using Yahoo Finance.

**What to build:**  
Replace batch daily run with a streaming mode:
- Intraday price updates every 15 minutes via Yahoo Finance (free, `yfinance`)
- Re-score candidates when any stock crosses resistance or drops below stop
- Push alert to terminal / desktop notification when actionable signal fires

**Note:** Yahoo Finance 15-min data is free but rate-limited. NSE's official EODS data subscription (~₹2,000/month) needed for production intraday.

---

## 6. BACKLOG — PHASE 4: ADVANCED SCREENERS, INDEX INTELLIGENCE & DEEP FUNDAMENTALS

> **Origin:** TOT/POT brainstorm session 2026-05-02. All items are additive — none break existing pipelines.
> Grouped by branch (A–E) from the TOT exploration tree.

---

### BRANCH A — ADVANCED SCREENERS

These screeners complement the existing sector-rotation candidates. Each produces a separate shortlist that can be merged into `candidates` or served as a separate HTML tab.

**Shared architecture pattern:**
```python
# All Branch A screeners follow this pattern in screeners.py:
# Input:  universe DataFrame (all NSE stocks with OHLCV + basic fundamentals)
# Output: filtered + scored DataFrame with SCREENER_CLASS column
# Integration: merged into sector_rotation_report.py candidates at report time
```

**File to create:** `screeners.py` (all Branch A functions)  
**File to modify:** `sector_rotation_report.py` → add "Screeners" tab to HTML

---

#### A1 — William O'Neil Stage Analysis Screener
**Size:** M | **Priority:** High — prevents buying into Stage 3/4 traps

**What exists:** Nothing. RSI + Supertrend approximate stage but do not formally classify.

**What to build:**
```python
def classify_stage(df: pd.DataFrame) -> pd.Series:
    """
    Input columns required per stock: CLOSE, SMA_50, SMA_200, VOL_20D_AVG, RSI, DISTANCE_FROM_52W_HIGH_PCT
    Output: pd.Series of {'STAGE_1', 'STAGE_2', 'STAGE_3', 'STAGE_4', 'UNKNOWN'}

    STAGE 1 — Base Building:
      price ≤ 200DMA ± 5%, SMA_50 flat or declining, volume contracting (vol_20d < vol_200d_avg × 0.8)

    STAGE 2 — Markup (THE BUY ZONE — only entry allowed):
      price > SMA_50 > SMA_200 (golden cross),
      SMA_50 slope positive (10-day pct_change > 0.001),
      SMA_200 slope positive (> 0.0005),
      price within 20% of 52W high,
      RS rank in top 30th percentile

    STAGE 3 — Distribution / Top:
      price near 52W high but SMA_50 flattening (slope < 0.001),
      ATR expanding relative to 3m avg, volume heavy on down-days

    STAGE_4 — Markdown:
      price < SMA_50 < SMA_200 (death cross), SMA_200 slope < -0.001
    """
    close = df["CLOSE"].astype(float)
    sma50 = df["SMA_50"].astype(float)
    sma200 = df["SMA_200"].astype(float)
    sma50_slope = sma50.pct_change(10).fillna(0)
    sma200_slope = sma200.pct_change(10).fillna(0)

    stage_2 = (
        (close > sma50) & (sma50 > sma200) &
        (sma50_slope > 0.001) & (sma200_slope > 0.0005) &
        (df.get("DISTANCE_FROM_52W_HIGH_PCT", pd.Series(0, index=df.index)) > -20)
    )
    stage_4 = (close < sma50) & (sma50 < sma200) & (sma200_slope < -0.001)
    stage_3 = (close > sma200) & (~stage_2) & (sma50_slope < 0.001)
    result = pd.Series("STAGE_1", index=df.index)
    result[stage_4] = "STAGE_4"
    result[stage_3] = "STAGE_3"
    result[stage_2] = "STAGE_2"
    return result

def stage_analysis_screener(universe: pd.DataFrame) -> pd.DataFrame:
    universe["STAGE"] = classify_stage(universe)
    stage2 = universe[universe["STAGE"] == "STAGE_2"].copy()
    stage2["STAGE_SCORE"] = (
        stage2["RS_RANK_PCT"] * 0.4 +
        (1 - stage2["DISTANCE_FROM_52W_HIGH_PCT"].abs() / 20) * 0.3 +
        stage2["VOL_RATIO"].clip(0.5, 3.0) * 0.3
    )
    return stage2.sort_values("STAGE_SCORE", ascending=False)
```

**New columns to add in `sector_rotation_report.py`:**
- `DISTANCE_FROM_52W_HIGH_PCT`: `(close / rolling_252_max - 1) * 100`
- `RS_RANK_PCT`: percentile rank of 66d return vs all NSE stocks
- `SMA_50_SLOPE`, `SMA_200_SLOPE`: 10-day pct_change of respective SMA

**Files to create/modify:**
- `screeners.py` — `classify_stage()`, `stage_analysis_screener()`
- `sector_rotation_report.py` — add `STAGE` column; demote Stage 3/4 in scoring; add stage badge in HTML

**Acceptance criteria:**
- Every candidate has `STAGE` value. Stage 3/4 stocks get -8 `INVESTMENT_SCORE` penalty.
- HTML shows stage badge: green=S2, amber=S1/S3, red=S4.

---

#### A2 — Darvas Box Breakout Screener
**Size:** M | **Priority:** Medium — box top/bottom gives mechanical entry and stop levels

**What exists:** `PATTERN == "CONSOLIDATION_BREAKOUT"` is a rough approximation; no formal box.

**What to build:**
```python
def detect_darvas_box(prices: pd.Series, lookback: int = 52) -> dict | None:
    """
    Darvas Box rules:
    1. Stock makes a new N-week high  → box TOP candidate
    2. Stays below that high for 3+ days (consolidation)
    3. Price fails to make new high for 3 days → box TOP locked
    4. Lowest low during consolidation = box BOTTOM
    5. BREAKOUT: last close > box_top AND volume > 1.5× 20d avg
    6. NEAR_TOP: price within 2% of box top (pre-breakout alert)

    Returns: {box_top, box_bottom, box_width_pct, days_in_box,
              breakout_confirmed, stop_loss (= box_bottom × 0.99)}
    or None if no valid box found.
    """
    recent = prices.tail(lookback)
    box_top = recent.max()
    box_top_idx = recent.idxmax()
    post_high = recent.loc[box_top_idx:]
    if len(post_high) < 3:
        return None
    if post_high.max() > box_top * 1.001:  # new high → box not formed
        return None
    box_bottom = post_high.iloc[1:].min()
    box_width_pct = (box_top - box_bottom) / box_bottom * 100
    if box_width_pct > 25:  # box too wide to be valid
        return None
    return {
        "box_top": round(box_top, 2),
        "box_bottom": round(box_bottom, 2),
        "box_width_pct": round(box_width_pct, 2),
        "days_in_box": len(post_high) - 1,
        "breakout_confirmed": bool(prices.iloc[-1] > box_top),
        "stop_loss": round(box_bottom * 0.99, 2),
    }
```

**Files to create/modify:**
- `screeners.py` — `detect_darvas_box()`, `darvas_screener()`
- Requires `price_history` dict: `{symbol: pd.Series of 52-week closes}` built from `data/nse_sec_full_data.csv`

**Acceptance criteria:**
- Returns 5–30 candidates on a typical day.
- Box top, box bottom, box width %, stop loss shown in HTML output.

---

#### A3 — 52-Week High Momentum Screener
**Size:** S | **Priority:** High — simplest implementation, strong historical hit rate

**What exists:** `DISTANCE_FROM_52W_HIGH_PCT` derivable but not used.

**What to build:**
```python
def momentum_52w_high_screener(universe: pd.DataFrame) -> pd.DataFrame:
    """
    Selection: price within 0–5% below 52W high + Stage 2 + RS top 25% + vol not contracting
    Score: rs_percentile×0.35 + proximity×0.30 + vol_ratio×0.20 + rsi_norm×0.15
    """
    df = universe.copy()
    df["DIST_52W_HIGH"] = (df["CLOSE"] / df["HIGH_52W"] - 1) * 100
    screened = df[
        df["DIST_52W_HIGH"].between(-5, 0.5) &
        (df["SMA_50_SLOPE"] > 0) &
        (df["RS_RANK_PCT"] >= 0.75) &
        (df["VOL_RATIO"] >= 1.0) &
        (df["RSI"].between(50, 80))
    ].copy()
    screened["MOMENTUM_SCORE"] = (
        screened["RS_RANK_PCT"] * 0.35 +
        (1 - screened["DIST_52W_HIGH"].abs() / 5) * 0.30 +
        screened["VOL_RATIO"].clip(0.8, 2.5) / 2.5 * 0.20 +
        ((screened["RSI"] - 50) / 30).clip(0, 1) * 0.15
    )
    return screened.sort_values("MOMENTUM_SCORE", ascending=False)
```

**Files to create/modify:**
- `screeners.py` — `momentum_52w_high_screener()`
- `sector_rotation_report.py` — add `HIGH_52W` column: rolling 252-day max of CLOSE

**Acceptance criteria:** Returns 10–40 candidates. Shown as a "52W High Momentum" screener tab in HTML.

---

#### A4 — Earnings Acceleration Screener
**Size:** M | **Priority:** High — strongest fundamental catalyst for sustained price moves

**What exists:** Latest-quarter EPS in `_sector_rotation_fund_cache.csv`. No multi-quarter series.

**Data enrichment required (R):**
```r
# Extend fetch_screener_fundamental_details.R:
# Scrape quarterly P&L from screener.in/#quarters table
# Extract: Sales, Net Profit, EPS, Operating Margin — last 8 quarters
# Save to: data/quarterly_eps.csv with columns: symbol, quarter_num, revenue, net_profit, eps, op_margin
```

**Screener logic (Python):**
```python
def earnings_acceleration_screener(quarterly_eps: pd.DataFrame) -> pd.DataFrame:
    """
    Acceleration criteria (all required):
    1. EPS growth YoY (Q1 vs Q5): > 25%
    2. EPS growth QoQ (Q1 vs Q2): > 5%
    3. Revenue growth YoY: > 15%
    4. Operating margin not deteriorating vs 4Q average: delta > -1pp

    ACC_SCORE = eps_yoy/100×0.35 + eps_qoq/50×0.20 + rev_yoy/100×0.25 + margin_delta/10×0.20
    """
    pivoted = quarterly_eps.pivot_table(index="symbol", columns="quarter_num",
                                         values=["eps", "revenue", "op_margin"])
    pivoted["EPS_YOY"] = (pivoted["eps"][1] / pivoted["eps"][5].abs() - 1) * 100
    pivoted["EPS_QOQ"] = (pivoted["eps"][1] / pivoted["eps"][2].abs() - 1) * 100
    pivoted["REV_YOY"] = (pivoted["revenue"][1] / pivoted["revenue"][5] - 1) * 100
    pivoted["MARGIN_DELTA"] = pivoted["op_margin"][1] - pivoted["op_margin"][[2,3,4,5]].mean(axis=1)
    accel = pivoted[
        (pivoted["EPS_YOY"] > 25) & (pivoted["EPS_QOQ"] > 5) &
        (pivoted["REV_YOY"] > 15) & (pivoted["MARGIN_DELTA"] > -1)
    ]
    return accel.sort_values("EPS_YOY", ascending=False)
```

**Files to create/modify:**
- `working-sector/fetch_screener_fundamental_details.R` — add quarterly scrape
- `data/quarterly_eps.csv` — new data file
- `screeners.py` — `earnings_acceleration_screener()`

**Dependencies:** Screener.in quarterly table scrape for top 200 Nifty500 stocks

---

#### A5 — Institutional Accumulation Screener
**Size:** M | **Priority:** Medium — requires F&O OI data (P1-2) for full confirmation

**What to build:**
```python
def institutional_accumulation_screener(universe: pd.DataFrame, price_history: dict) -> pd.DataFrame:
    """
    IBD-style Accumulation/Distribution rating based on up-volume vs down-volume.

    For last 65 trading days per stock:
      up_vol = sum(volume on days where close > prev_close)
      down_vol = sum(volume on days where close ≤ prev_close)
      ud_ratio = up_vol / down_vol

    Grades: A+ (>2.0), A (1.5-2.0), B (1.2-1.5), C (0.8-1.2), D (<0.8)
    Only include grade B or better.

    Supplementary confirmation (if P1-2 available):
    OI buildup signal (OI_CHANGE_5D > +15%) adds +0.2 to effective ud_ratio.
    """
    results = []
    for sym, row in universe.iterrows():
        ph = price_history.get(sym)
        if ph is None or len(ph) < 65:
            continue
        recent = ph.tail(65)
        up_mask = recent["CLOSE"] > recent["CLOSE"].shift(1)
        up_vol = recent.loc[up_mask, "VOLUME"].sum()
        down_vol = recent.loc[~up_mask, "VOLUME"].sum()
        ud_ratio = up_vol / max(down_vol, 1)
        if ud_ratio >= 1.2:
            grade = "A+" if ud_ratio > 2.0 else "A" if ud_ratio > 1.5 else "B"
            results.append({**row.to_dict(), "UD_RATIO": round(ud_ratio, 2), "ACCUM_GRADE": grade})
    return pd.DataFrame(results).sort_values("UD_RATIO", ascending=False)
```

**Dependencies:** P1-2 (optional OI confirmation); `price_history` dict with CLOSE + VOLUME (65d)

---

#### A6 — Turnaround Detector
**Size:** S | **Priority:** Medium — finds recovery candidates before institutional attention arrives

**What to build:**
```python
def turnaround_screener(universe: pd.DataFrame, price_history: dict) -> pd.DataFrame:
    """
    Turnaround = deep fall + early recovery signal

    Criteria:
    1. Max drawdown from peak in last 120 days: < -30%  (was in significant downtrend)
    2. Current price > SMA_50 (crossed up recently)
    3. RSI recovering: 35 ≤ RSI ≤ 58
    4. SUPERTREND_STATE in {'BULLISH', 'NEUTRAL'}

    Score: lower RSI (=earlier in recovery) ranked first.
    Shows MAX_DRAWDOWN_PCT so user understands the fall magnitude.
    """
    results = []
    for sym, row in universe.iterrows():
        ph = price_history.get(sym)
        if ph is None or len(ph) < 120:
            continue
        close = ph["CLOSE"].tail(120)
        drawdown = (close / close.cummax() - 1).min() * 100  # most negative
        if drawdown > -30:
            continue
        if (row.get("CLOSE", 0) > row.get("SMA_50", 0) and
            35 <= row.get("RSI", 50) <= 58 and
            row.get("SUPERTREND_STATE", "") in ("BULLISH", "NEUTRAL")):
            results.append({**row.to_dict(), "MAX_DRAWDOWN_PCT": round(drawdown, 1),
                             "TURNAROUND_SIGNAL": "EARLY_RECOVERY"})
    return pd.DataFrame(results).sort_values("RSI", ascending=True)
```

**Acceptance criteria:** Candidates shown with `MAX_DRAWDOWN_PCT`; sorted by RSI ascending (earlier in recovery = lower RSI).

---

#### A7 — Quality Compounder Screener
**Size:** M | **Priority:** High — long-term wealth creation; lowest turnover, highest conviction

**What exists:** Single-year ROE + Debt/Equity in cache. No 5-year trend.

**Data enrichment (R):** Add 5-year P&L and ROCE to `fetch_screener_fundamental_details.R`:
```r
# Scrape #profit-loss table (annual, last 5 years): Revenue, PAT, ROCE
# Compute: REV_CAGR_5Y, PAT_CAGR_5Y, AVG_ROE_5Y, AVG_ROCE_5Y
# Save to: data/quality_fundamentals.csv
```

**Screener logic:**
```python
def quality_compounder_screener(fundamentals: pd.DataFrame) -> pd.DataFrame:
    """
    Criteria (ALL must be met):
    Rev CAGR 5Y > 15%, PAT CAGR 5Y > 18%, avg ROE > 20%, Debt/Equity < 0.3, Promoter > 45%

    QUALITY_SCORE (0-100):
    = rev_cagr/30×20 + pat_cagr/35×20 + avg_roe/30×20 + avg_roce/28×20 + (1-D/E/0.5)×10 + promoter_bonus×10
    """
    df = fundamentals.dropna(subset=["REV_CAGR_5Y", "PAT_CAGR_5Y", "AVG_ROE_5Y", "DEBT_EQUITY"])
    quality = df[
        (df["REV_CAGR_5Y"] > 15) & (df["PAT_CAGR_5Y"] > 18) &
        (df["AVG_ROE_5Y"] > 20) & (df["DEBT_EQUITY"] < 0.3) & (df["PROMOTER_HOLDING"] > 45)
    ].copy()
    quality["QUALITY_SCORE"] = (
        quality["REV_CAGR_5Y"].clip(0, 30) / 30 * 20 +
        quality["PAT_CAGR_5Y"].clip(0, 35) / 35 * 20 +
        quality["AVG_ROE_5Y"].clip(0, 30) / 30 * 20 +
        quality["AVG_ROCE_5Y"].clip(0, 28) / 28 * 20 +
        (1 - quality["DEBT_EQUITY"].clip(0, 0.5) / 0.5) * 10 +
        quality["PROMOTER_HOLDING"].apply(lambda x: 10 if x > 50 else 5)
    )
    return quality.sort_values("QUALITY_SCORE", ascending=False)
```

**Files to create/modify:**
- `working-sector/fetch_screener_fundamental_details.R` — add 5yr P&L + ROCE
- `data/quality_fundamentals.csv` — 5-year fundamentals per symbol
- `screeners.py` — `quality_compounder_screener()`

**Acceptance criteria:** Returns 20–60 quality compounders from Nifty500. `QUALITY_SCORE` shown with component breakdown.

---

#### A8 — Hidden Champions (Small/Mid Cap Niche Leaders)
**Size:** M | **Priority:** Medium — highest alpha potential; requires A7 as input

**What to build:**
```python
def hidden_champions_screener(fundamentals: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """
    Hidden Champion: niche leader with quality fundamentals and low analyst coverage

    Criteria:
    - Market cap: 500–8,000 Cr (small/mid cap)
    - Rev CAGR 3Y > 20%, Operating Margin > 15%, ROE > 18%, D/E < 0.5, Promoter > 50%
    - NOT in Nifty100 (lower coverage = more mispricing opportunity)

    HIDDEN_SCORE = QUALITY_SCORE×0.5 + growth_score×0.3 + niche_bonus×0.2
    niche_bonus: 100 if not in Nifty100, else 30
    """
    small_mid = fundamentals[
        fundamentals["MARKET_CAP_CR"].between(500, 8000) &
        (fundamentals["REV_CAGR_3Y"] > 20) & (fundamentals["OP_MARGIN"] > 15) &
        (fundamentals["ROE"] > 18) & (fundamentals["DEBT_EQUITY"] < 0.5) &
        (fundamentals["PROMOTER_HOLDING"] > 50)
    ].copy()
    nifty100 = _load_index_constituents("Nifty 100")
    small_mid["NICHE_BONUS"] = small_mid["SYMBOL"].apply(lambda s: 100 if s not in nifty100 else 30)
    small_mid["HIDDEN_SCORE"] = (
        small_mid.get("QUALITY_SCORE", 50) * 0.5 +
        (small_mid["REV_CAGR_3Y"].clip(0, 30) / 30 * 50) * 0.3 +
        small_mid["NICHE_BONUS"] * 0.2
    )
    return small_mid.sort_values("HIDDEN_SCORE", ascending=False).head(30)
```

**Dependencies:** A7 quality fundamentals; Nifty100 constituent list from `data/nse_indices_catalog.csv`

---

### BRANCH B — INDEX & INTER-MARKET INTELLIGENCE

**File to create:** `index_intelligence.py`  
**Output:** data embedded in main report HTML + optional standalone `reports/index_intelligence_{date}.html`

---

#### B1 — Cross-Index Breadth Dashboard
**Size:** M | **Priority:** High — shows market-wide health at a glance

**What exists:** `analyze_comprehensive_market_breadth.R` covers Nifty500 only. No multi-index comparison.

**What to build:**
```python
def cross_index_breadth(index_constituent_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Input: {index_name: DataFrame with SYMBOL, CLOSE, SMA_50, SMA_200, HIGH_52W, LOW_52W, RET_1D}

    For each index compute:
    - pct_above_200dma:  (CLOSE > SMA_200).mean() × 100
    - pct_above_50dma:   (CLOSE > SMA_50).mean() × 100
    - pct_near_52wh:     (CLOSE / HIGH_52W > 0.95).mean() × 100  (within 5% of 52W high)
    - pct_near_52wl:     (CLOSE / LOW_52W < 1.05).mean() × 100   (within 5% of 52W low)
    - ad_ratio:          advances / max(declines, 1)

    Breadth signal:
    STRONG  : pct_above_200 > 70 AND ad_ratio > 1.8
    HEALTHY : pct_above_200 60–70
    NEUTRAL : pct_above_200 45–60
    WEAK    : pct_above_200 30–45
    BEARISH : pct_above_200 < 30 OR pct_near_52wl > 15

    Indices to cover: Nifty50, Nifty500, MidCap150, SmallCap250,
                      Bank Nifty, IT, Pharma, Auto, FMCG, Metal
    """
```

**Integration:** Breadth signal of Nifty50 + SmallCap divergence → input to regime detector.  
If Nifty50=STRONG but SmallCap=WEAK → selective/ROTATION regime signal.

**Files to create/modify:**
- `index_intelligence.py` — `cross_index_breadth()`
- `sector_rotation_report.py` — import and add breadth row to regime banner HTML

---

#### B2 — Global Correlation Monitor
**Size:** M | **Priority:** Medium — identifies contagion risk and decoupling opportunity

**What to build:**
```python
GLOBAL_TICKERS = {
    "S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Euro Stoxx 50": "^STOXX50E",
    "Hang Seng": "^HSI", "Nikkei 225": "^N225", "Gold": "GC=F",
    "Crude Oil": "CL=F", "Copper": "HG=F", "DXY": "DX-Y.NYB", "USDINR": "USDINR=X",
}

def fetch_global_indices(tickers: dict, lookback_days: int = 120) -> pd.DataFrame:
    """Fetch via yfinance, cache to data/global_indices.csv (TTL: 24h)."""
    import yfinance as yf
    data = {}
    for name, ticker in tickers.items():
        try:
            data[name] = yf.Ticker(ticker).history(period="6mo")["Close"]
        except Exception:
            pass  # missing global index is non-fatal
    return pd.DataFrame(data).dropna(how="all")

def compute_correlations(nifty_series: pd.Series, global_df: pd.DataFrame) -> pd.DataFrame:
    """
    30d and 60d rolling correlation of Nifty500 vs each global asset.

    Alert: DECOUPLING when |corr_30d - corr_60d| > 0.20
    (Decoupling = potential India-specific story forming or unwinding)

    Output: asset, corr_30d, corr_60d, change, alert
    """
```

**Files to create/modify:**
- `index_intelligence.py` — `fetch_global_indices()`, `compute_correlations()`
- `data/global_indices.csv` — new data file

**Dependencies:** `yfinance` (`pip install yfinance` into .venv)  
**Acceptance criteria:** Correlation table in < 30s. Decoupling alert fires when 30d vs 60d diverges > 20pp.

---

#### B3 — Sectoral Heat Calendar
**Size:** M | **Priority:** High — seasonal alpha is one of the most reliable edges in NSE

**What to build:**
```python
def build_seasonal_heat_calendar(sector_monthly_returns: pd.DataFrame, lookback_years: int = 7) -> tuple:
    """
    Input: monthly returns per sector index (from data/nse_index_data.csv, last 7 years)
    Output: (matrix, heat) where matrix = 12-row × N-sector avg monthly return table

    Seasonal signal per sector:
    TAILWIND : avg monthly return > +2% in current month (n ≥ 5 observations)
    HEADWIND : avg monthly return < -1%
    NEUTRAL  : otherwise

    Examples:
    FMCG:     Aug/Sep/Oct strong (festive pre-stocking)
    Metals:   Feb/Mar weak (budget), Apr/May strong (infra season)
    Auto:     Sep/Oct strong (festive), Jan/Feb weak (post-festive)
    IT:       Oct-Dec strong (deal wins), Apr weak (guidance season)
    """
    df = sector_monthly_returns.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.month
    heat = df.groupby(["sector", "month"])["return_pct"].agg(avg="mean", std="std", n="count").reset_index()
    matrix = heat.pivot_table(index="month", columns="sector", values="avg")
    matrix.index = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return matrix, heat

def render_heat_calendar_html(matrix: pd.DataFrame) -> str:
    """
    Returns HTML table with green/red color gradient per cell.
    Current month column outlined in blue.
    Each cell: avg return % + arrow icon (↑↓→).
    """
```

**Integration:** `SEASONAL_SIGNAL` column in sector rank table; passed to LLM prompt as seasonal context.

**Acceptance criteria:** Calendar renders for 8+ NSE sector indices. Current month highlighted. `SEASONAL_SIGNAL` in sector rank.

---

#### B4 — FII/DII Flow Battle Tracker
**Size:** M | **Priority:** High — who is winning between FII and DII drives medium-term direction

**What to build:**
```python
def fii_dii_battle_tracker(flows: pd.DataFrame, lookback_days: int = 60) -> dict:
    """
    Input: flows DataFrame (from P1-3) with [date, fii_net, dii_net]

    Battle signals:
    FII_DOMINANT  : fii_net_20d > +5,000 Cr AND dii_net_20d < 0
    DII_DEFENDING : dii_net_20d > 3,000 Cr (domestic absorption offsets FII)
    FII_FLEEING   : fii_net_20d < -8,000 Cr (sustained selling)
    BOTH_BUYING   : fii_net_20d > 0 AND dii_net_20d > 2,000 Cr → strongest bull signal
    STANDOFF      : both flows < 1,000 Cr absolute

    Output dict:
    {battle_signal, fii_net_5d, fii_net_20d, dii_net_5d, dii_net_20d,
     narrative, sector_fii_preference (from P1-2 participant OI)}
    """
```

**Dependencies:** P1-3 (FII/DII flows), P1-2 participant OI for sector allocation  
**Acceptance criteria:** Battle signal + 5d/20d flows shown in regime banner HTML.

---

#### B5 — Economic Cycle Tracker
**Size:** L | **Priority:** Medium — strategic positioning framework; maps macro to sector preference

**What to build:**
```python
CYCLE_PHASES = {
    "EARLY_EXPANSION": {
        "definition": "PMI rising from < 50, IIP accelerating, GST growth improving",
        "preferred_sectors": ["Banking", "Consumer Discretionary", "Real Estate", "Auto"],
        "avoid_sectors": ["Utilities", "FMCG"],
    },
    "LATE_EXPANSION": {
        "definition": "PMI > 55, inflation rising, yield curve flattening",
        "preferred_sectors": ["Energy", "Metals", "Capital Goods"],
        "avoid_sectors": ["Rate-sensitive (Banking, NBFC, Real Estate)"],
    },
    "SLOWDOWN": {
        "definition": "PMI falling from peak, IIP decelerating",
        "preferred_sectors": ["FMCG", "Pharma", "IT"],
        "avoid_sectors": ["Metals", "Auto", "Real Estate"],
    },
    "RECOVERY": {
        "definition": "PMI at trough and reversing, fiscal stimulus active",
        "preferred_sectors": ["Banking", "Capital Goods", "Infrastructure", "Cement"],
        "avoid_sectors": ["Defensives (underperform in recovery)"],
    },
}

def detect_economic_cycle_phase(macro_signals: pd.DataFrame, market_regime: str) -> dict:
    """
    Decision tree using PMI, IIP YoY, GST growth from P1-6.
    Cross-check with market regime (P1-1):
    - Cycle EXPANSION but market BEAR → potential opportunity
    - Cycle SLOWDOWN but market BULL → market ahead of fundamentals (be cautious)
    Returns: {cycle_phase, confidence, preferred_sectors, regime_cycle_alignment}
    """
```

**Integration:** Cycle phase adjusts sector scoring: `CYCLE_FAVOURED` → +4, `CYCLE_UNFAVOURED` → -3  
**Dependencies:** P1-6 (macro proxies), P1-1 (regime detector)

---

### BRANCH C — MARKET BREADTH INTELLIGENCE

**File to create:** `market_breadth.py`  
**Output:** `data/breadth_history.csv` (daily cumulative); breadth section in main HTML report

---

#### C1 — McClellan Oscillator & Summation Index
**Size:** M | **Priority:** High — leading indicator for market tops and breadth divergences

**What exists:** `analyze_comprehensive_market_breadth.R` has basic A/D. No McClellan.

**What to build:**
```python
def compute_mcclellan(net_advance_decline: pd.Series) -> pd.DataFrame:
    """
    McClellan Oscillator = EMA_19(net_AD) - EMA_39(net_AD)
    Summation Index = cumulative sum of Oscillator

    Signals:
    > +70  → overbought breadth
    < -70  → oversold breadth (potential bounce)
    Cross zero from below → BULLISH_CROSS
    Cross zero from above → BEARISH_CROSS
    Summation > 0 and rising → bull market breadth
    Summation < 0 and falling → bear market breadth

    Divergence detection:
    BULLISH_DIVERGENCE : price new low but Oscillator higher low → potential reversal
    BEARISH_DIVERGENCE : price new high but Oscillator lower high → distribution
    """
    ema19 = net_advance_decline.ewm(span=19, adjust=False).mean()
    ema39 = net_advance_decline.ewm(span=39, adjust=False).mean()
    oscillator = ema19 - ema39
    summation = oscillator.cumsum()
    signal = pd.Series("NEUTRAL", index=oscillator.index)
    signal[oscillator > 70] = "OVERBOUGHT"
    signal[oscillator < -70] = "OVERSOLD"
    signal[(oscillator > 0) & (oscillator.shift(1) <= 0)] = "BULLISH_CROSS"
    signal[(oscillator < 0) & (oscillator.shift(1) >= 0)] = "BEARISH_CROSS"
    return pd.DataFrame({"oscillator": oscillator.round(1), "summation": summation.round(0), "signal": signal})

def get_advance_decline_series(universe_df: pd.DataFrame) -> pd.Series:
    """Compute daily net A/D from Nifty500 universe (CLOSE > PREV_CLOSE = advance)."""
    daily = universe_df.copy()
    daily["ADV"] = daily["CLOSE"] > daily["CLOSE"].shift(1)
    ad = daily.groupby("DATE").agg(advances=("ADV", "sum"), declines=("ADV", lambda x: (~x).sum()))
    return (ad["advances"] - ad["declines"]).rename("net_ad")
```

**Files to create/modify:**
- `market_breadth.py` — `compute_mcclellan()`, `get_advance_decline_series()`
- `data/breadth_history.csv` — add `oscillator`, `summation`, `signal` columns
- `sector_rotation_report.py` — McClellan value in HTML header badge

**Acceptance criteria:** Oscillator value and signal displayed in HTML. Divergence alerts show when detected.

---

#### C2 — TRIN / Arms Index (Volume Breadth)
**Size:** S | **Priority:** Medium — volume-weighted breadth captures institutional activity better than price A/D

**What to build:**
```python
def compute_trin(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    TRIN = (Advances / Declines) / (Advancing Volume / Declining Volume)

    < 0.5  → very bullish (volume overwhelmingly on advancing stocks)
    0.5–0.8 → bullish
    0.8–1.2 → neutral
    1.2–2.0 → bearish
    > 2.0  → very bearish / panic selling (contrarian: potential washout low)

    5-day avg TRIN < 0.75 → internally strong despite surface weakness
    5-day avg TRIN > 1.40 → internally weak despite surface strength
    """
    daily = universe_df.copy()
    daily["UP"] = daily["CLOSE"] > daily["CLOSE"].shift(1)
    def trin_for_day(g):
        adv = g["UP"].sum(); dec = (~g["UP"]).sum()
        avol = g.loc[g["UP"], "VOLUME"].sum(); dvol = g.loc[~g["UP"], "VOLUME"].sum()
        return (adv / max(dec, 1)) / (avol / max(dvol, 1))
    trin_series = universe_df.groupby("DATE").apply(trin_for_day)
    df = pd.DataFrame({"trin": trin_series})
    df["trin_5d"] = df["trin"].rolling(5).mean()
    df["signal"] = df["trin"].map(lambda t:
        "VERY_BULLISH" if t < 0.5 else "BULLISH" if t < 0.8 else
        "NEUTRAL" if t < 1.2 else "BEARISH" if t < 2.0 else "PANIC")
    return df
```

**Files to create/modify:** `market_breadth.py` — `compute_trin()`; `data/breadth_history.csv` — add `trin`, `trin_5d`

---

#### C3 — Sector Breadth Divergence Monitor
**Size:** M | **Priority:** High — early warning for sector distribution

**What to build:**
```python
def sector_breadth_divergence(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each sector:
    - pct_above_50dma:  (CLOSE > SMA_50).mean() × 100
    - pct_above_200dma: (CLOSE > SMA_200).mean() × 100
    - change_5d:        compare vs breadth_history 5 days ago

    Divergence alerts:
    BULLISH_DIV  : sector index new low BUT pct_above_50dma higher low → accumulation
    BEARISH_DIV  : sector index new high BUT pct_above_50dma falling → distribution
    INT_WEAKNESS : index flat BUT pct_above_50dma fell > 10pp in 5d (few large caps holding index)

    breadth_signal: HEALTHY (pct50 > 60), NEUTRAL (40–60), WEAK (< 40)
    """
```

**Integration:** `sector_breadth_pct50` column added to sector rank table alongside RS score.  
**Files to create/modify:** `market_breadth.py` — `sector_breadth_divergence()`; `sector_rotation_report.py` — merge into sector rank

---

#### C4 — Smart Money Flow Index
**Size:** M | **Priority:** Medium — tracks institutional vs retail behavior

**What to build:**
```python
def smart_money_flow_index(price_volume_df: pd.DataFrame) -> pd.DataFrame:
    """
    EOD Smart Money approximation:
    SMFI_daily = Close × Volume × ((Close - Open) / (High - Low + 0.01))

    Positive SMFI: closed near high on high volume → buying pressure
    Negative SMFI: closed near low on high volume → selling pressure

    5d SMFI sum vs 20d SMFI sum:
    5d > 20d × 1.05 → ACCUMULATING
    5d < 20d × 0.95 → DISTRIBUTING
    else            → NEUTRAL

    Composite (if P1-2 + P1-4 available):
    SMFI_TREND + block_deal_net + fii_oi_net → ACCUMULATING / DISTRIBUTING / NEUTRAL
    """
    df = price_volume_df.copy()
    price_range = (df["HIGH"] - df["LOW"]).clip(lower=0.01)
    df["SMFI"] = df["CLOSE"] * df["VOLUME"] * ((df["CLOSE"] - df["OPEN"]) / price_range)
    df["SMFI_5D"] = df["SMFI"].rolling(5).sum()
    df["SMFI_20D"] = df["SMFI"].rolling(20).sum()
    df["SMFI_SIGNAL"] = df.apply(
        lambda r: "ACCUMULATING" if r["SMFI_5D"] > r["SMFI_20D"] * 1.05 else
                  "DISTRIBUTING" if r["SMFI_5D"] < r["SMFI_20D"] * 0.95 else "NEUTRAL", axis=1
    )
    return df
```

**Dependencies:** SMFI alone is independent; full composite needs P1-2 + P1-4.

---

### BRANCH D — DEEP FUNDAMENTAL INTELLIGENCE

**File to create:** `deep_fundamentals.py`  
**Data dependency:** Screener.in 5-year P&L + balance sheet + cash flow (source N in registry)

---

#### D1 — DuPont Decomposition Engine
**Size:** M | **Priority:** High — distinguishes real quality from leverage-driven ROE

**What exists:** Single-year ROE in `_sector_rotation_fund_cache.csv`. No decomposition or trend.

**What to build:**
```python
def dupont_decompose(fundamentals_5yr: pd.DataFrame) -> pd.DataFrame:
    """
    3-Factor DuPont:
    ROE = Net Profit Margin × Asset Turnover × Equity Multiplier
        = (NP / Revenue) × (Revenue / Assets) × (Assets / Equity)

    5-Factor extended:
    ROE = Tax Burden × Interest Burden × EBIT Margin × Asset Turnover × Leverage

    YoY ROE change attribution:
    MARGIN_DRIVEN    : margin contribution > turnover + leverage contribution
    EFFICIENCY_DRIVEN: turnover contribution dominates
    LEVERAGE_DRIVEN  : leverage contribution dominates → RED FLAG (quality concern)

    Per stock: compute for each of 5 years, show trend and current year driver.
    """
    result = fundamentals_5yr.copy()
    result["NET_MARGIN"]       = result["NET_PROFIT"] / result["REVENUE"]
    result["ASSET_TURNOVER"]   = result["REVENUE"] / result["TOTAL_ASSETS"]
    result["EQUITY_MULTIPLIER"]= result["TOTAL_ASSETS"] / result["SHAREHOLDERS_EQUITY"]
    result["ROE_DECOMPOSED"]   = result["NET_MARGIN"] * result["ASSET_TURNOVER"] * result["EQUITY_MULTIPLIER"]

    def flag_driver(row):
        margin_delta   = abs(row.get("MARGIN_CONTRIBUTION", 0))
        turnover_delta = abs(row.get("TURNOVER_CONTRIBUTION", 0))
        leverage_delta = abs(row.get("LEVERAGE_CONTRIBUTION", 0))
        if leverage_delta and leverage_delta == max(margin_delta, turnover_delta, leverage_delta):
            return "LEVERAGE_DRIVEN_RED_FLAG"
        return "MARGIN_DRIVEN" if margin_delta >= max(turnover_delta, leverage_delta) else "EFFICIENCY_DRIVEN"

    result["ROE_DRIVER"] = result.apply(flag_driver, axis=1)
    return result
```

**Integration:** `LEVERAGE_DRIVEN_RED_FLAG` stocks get -5 `INVESTMENT_SCORE` penalty; badge in HTML.  
**Files to create/modify:** `deep_fundamentals.py` — `dupont_decompose()`; `data/quality_fundamentals.csv`

---

#### D2 — Earnings Quality Score
**Size:** M | **Priority:** High — single best fraud proxy; cash > accruals = genuine earnings

**Data enrichment (R):**
```r
# Extend fetch_screener_fundamental_details.R:
# Scrape #cash-flow table (last 5 years): CFO, Capex, FCF
# Add to data/_sector_rotation_fund_cache.csv or separate data/cashflow_data.csv
```

**What to build:**
```python
def earnings_quality_score(merged: pd.DataFrame) -> pd.DataFrame:
    """
    4 components:

    1. Cash Conversion Ratio (CCR) = CFO / Net_Profit
       > 1.0 → cash exceeds earnings (high quality)
       < 0.0 → operating cash negative despite profit → RED FLAG

    2. Accruals Ratio (Sloan) = (Net_Profit - CFO) / Avg_Total_Assets
       < 0.0 → CFO > earnings → high quality

    3. FCF Yield = (CFO - Capex) / Market_Cap
       > 5% → attractive

    4. DSO Trend = (Receivables / Revenue × 365) — rising = channel stuffing risk

    EQ_SCORE (0–100):
    = ccr_score×30 + accruals_score×30 + fcf_yield_score×25 + dso_score×15

    CCR < 0 → CCR_CONCERN flag regardless of other scores.
    """
    merged["CCR"] = merged["CFO"] / merged["NET_PROFIT"].replace(0, 0.001)
    merged["ACCRUALS"] = (merged["NET_PROFIT"] - merged["CFO"]) / merged["TOTAL_ASSETS"]
    merged["FCF"] = merged["CFO"] - merged["CAPEX"]
    merged["FCF_YIELD"] = merged["FCF"] / (merged["MARKET_CAP_CR"] * 1e7)
    merged["CCR_CONCERN"] = merged["CCR"] < 0
    merged["EQ_SCORE"] = (
        merged["CCR"].clip(0, 1.5) / 1.5 * 100 * 0.30 +
        (1 - merged["ACCRUALS"].clip(0, 0.05) / 0.05) * 100 * 0.30 +
        merged["FCF_YIELD"].clip(0, 0.08) / 0.08 * 100 * 0.25 +
        # DSO score: approximated as 25 if unavailable
        pd.Series(25, index=merged.index) * 0.15
    ).round(1)
    return merged
```

**Acceptance criteria:** `EQ_SCORE` (0–100) in HTML. `CCR_CONCERN` badge. Score adjusts `INVESTMENT_SCORE` by `(EQ_SCORE - 50) / 20`.

---

#### D3 — Business Cycle Sector Positioning
*Stock-level extension of B5. See B5 spec.*

```python
def map_stocks_to_cycle(universe: pd.DataFrame, cycle_phase: str) -> pd.DataFrame:
    """Tag each stock CYCLE_FAVOURED / CYCLE_NEUTRAL / CYCLE_UNFAVOURED
    based on sector and current cycle phase from B5.
    Adjust INVESTMENT_SCORE: +4 for favoured, -3 for unfavoured."""
    phase = CYCLE_PHASES.get(cycle_phase, {})
    universe["CYCLE_TAG"] = universe["SECTOR"].apply(
        lambda s: "CYCLE_FAVOURED" if any(x.lower() in s.lower() for x in phase.get("preferred_sectors", []))
                  else "CYCLE_UNFAVOURED" if any(x.lower() in s.lower() for x in phase.get("avoid_sectors", []))
                  else "CYCLE_NEUTRAL"
    )
    return universe
```

---

#### D4 — Concall Sentiment NLP
*This is the same as P2-5 in Phase 2 above. Refer to P2-5 spec for full implementation.*  
Branch D cross-references D4 → P2-5. **Do not duplicate implementation.**

---

#### D5 — Forensic Accounting Suite (Beneish + Piotroski + Altman)
**Size:** L | **Priority:** High — prevents buying accounting frauds; saves capital

**What exists:** Nothing. No multi-model scoring.

**What to build:**
```python
def beneish_mscore(fin: dict) -> float:
    """
    Beneish M-Score: detects earnings manipulation via 8 variables.
    M > -1.78 → likely manipulator (RED FLAG)
    M < -2.22 → unlikely manipulator

    Variables:
    DSRI  = (Rec_t/Sales_t) / (Rec_t-1/Sales_t-1)          [receivables inflation]
    GMI   = GrossMargin_t-1 / GrossMargin_t                  [margin deterioration]
    AQI   = (1-(CA+PPE)/TA)_t / (1-(CA+PPE)/TA)_t-1        [asset quality]
    SGI   = Sales_t / Sales_t-1                              [sales growth incentive]
    DEPI  = DepRate_t-1 / DepRate_t                          [depreciation manipulation]
    SGAI  = (SGA/Sales)_t / (SGA/Sales)_t-1                 [overhead bloat]
    LVGI  = Leverage_t / Leverage_t-1                        [covenant pressure]
    TATA  = (ΔWorkingCapital - Depreciation) / TotalAssets   [accruals]

    M = -4.84 + 0.920×DSRI + 0.528×GMI + 0.404×AQI + 0.892×SGI
            + 0.115×DEPI - 0.172×SGAI + 4.679×TATA - 0.327×LVGI
    """

def piotroski_fscore(fin: dict) -> tuple[int, dict]:
    """
    9-point binary scoring system.

    PROFITABILITY (4 pts): ROA>0, CFO>0, ΔROA>0, CFO>Net_Income
    LEVERAGE/LIQUIDITY (3 pts): ΔLeverage<0, ΔCurrentRatio>0, No_new_shares
    EFFICIENCY (2 pts): ΔGrossMargin>0, ΔAssetTurnover>0

    F ≥ 7 → strong (buy candidate)
    F ≤ 2 → weak (avoid or short)
    """

def altman_zscore(fin: dict) -> tuple[float, str]:
    """
    Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5
    X1=WorkCap/TA, X2=RetainedEarnings/TA, X3=EBIT/TA, X4=MktCap/Debt, X5=Sales/TA

    Z > 2.99 → SAFE | 1.81–2.99 → GREY | < 1.81 → DISTRESS
    """

def forensic_composite_score(symbol: str, fin: dict) -> dict:
    """
    FORENSIC_PASS  : Beneish < -2.22 AND Piotroski ≥ 6 AND Altman SAFE
    FORENSIC_WATCH : any one model in caution range
    FORENSIC_FAIL  : Beneish > -1.78 OR Piotroski ≤ 2 OR Altman DISTRESS

    FORENSIC_FAIL → block BUY recommendation regardless of technical signal
    Penalty: FORENSIC_FAIL → INVESTMENT_SCORE -= 10
    """
```

**Files to create/modify:**
- `deep_fundamentals.py` — all three models + `forensic_composite_score()`
- `data/forensic_scores.csv` — cached results (TTL: 30d)
- `sector_rotation_report.py` — forensic badge in HTML; FORENSIC_FAIL → -10 penalty

**Dependencies:** 2-year P&L + balance sheet + cash flow from Screener.in (source N)  
**Acceptance criteria:**
- Forensic badge in HTML: green=PASS, amber=WATCH, red=FAIL.
- Computed for > 80% of Nifty500.
- FORENSIC_FAIL stocks never appear in BUY recommendations.

---

#### D6 — Competitive Moat Score
**Size:** L | **Priority:** Medium — identifies stocks with durable pricing power

**What to build:**
```python
def competitive_moat_score(fundamentals_5yr: pd.DataFrame, peers: pd.DataFrame) -> pd.DataFrame:
    """
    Moat Score = composite of 5 proxies (0–100)

    1. PRICING POWER (0–25):
       Gross margin stability: avg_GM / 50 × 25 × (1 - min(CV_GM, 0.3)/0.3)
       High stable margin = pricing power moat

    2. SWITCHING COSTS (0–20):
       Revenue retention rate stability + sector bonus (IT, Specialty Chem: auto +5)

    3. COST ADVANTAGE (0–20):
       Operating margin vs peer average: (op_margin - peer_avg) / 20 × 20

    4. NETWORK EFFECT (0–15):
       Revenue growth acceleration + op leverage improvement
       Auto 15 points: Exchange, Payment, Marketplace sectors

    5. EFFICIENT SCALE (0–20):
       Economic profit = ROCE - 12% (hurdle rate)
       (ROCE - 12).clip(0, 20) / 20 × 20

    MOAT_CLASS: WIDE (≥70), NARROW (40–69), NONE (<40)
    WIDE_MOAT → +3 bonus on INVESTMENT_SCORE
    """
```

**Acceptance criteria:** MOAT_CLASS badge in HTML. Score breakdown in tooltip (pricing power %, ROCE vs hurdle).

---

### BRANCH E — COMPANY INTELLIGENCE LAYER

**File to create:** `company_intelligence.py`  
**Output:** `reports/company_{SYMBOL}_{date}.html` (on-demand per company)

---

#### E1 — 360° Company Deep-Dive Dashboard
**Size:** XL | **Priority:** Medium — run on-demand, not in bulk daily batch

**What to build:**
```python
def generate_company_dashboard(symbol: str, force_refresh: bool = False) -> Path:
    """
    Cache: data/company_cache/{SYMBOL}.json  (TTL: 7 days)
    CLI:   python company_intelligence.py --symbol TATASTEEL [--open]

    HTML sections:
    1. IDENTITY: company name, sector, market cap, business description
    2. PRICE & TECHNICAL CANVAS: 12m chart, 50/200DMA, Supertrend, Stage, Darvas box, Entry/Stop/Target
    3. FINANCIAL SCORECARD: 5yr Revenue/PAT/EPS bar chart, DuPont table (D1), EQ Score (D2), Forensic scores (D5)
    4. MOAT & COMPETITIVE POSITION: Moat score (D6) + Peer comparison table (E2)
    5. MANAGEMENT QUALITY: Promoter holding trend, insider events (P1-4), concall sentiment history (D4)
    6. UPCOMING EVENTS: next result date, ex-dividend, AGM, pending approvals (E4)
    7. LLM SYNTHESIS: full analyst-grade narrative integrating all 6 sections, 
                      investment thesis, key risks, valuation range
    """
```

---

#### E2 — Peer Comparison Engine
**Size:** M | **Priority:** High — relative valuation is the most-used technique

**What to build:**
```python
def fetch_peer_comparison(symbol: str) -> pd.DataFrame:
    """
    Scrape #peers table from https://www.screener.in/company/{symbol}/
    Columns: Name, CMP, P/E, Market Cap, Div Yield, NP Qtr, Qtr Profit Var, Sales Qtr, ROCE

    Processing:
    1. Compute percentile rank of target vs peers on each metric
    2. REL_VAL_SCORE = -pe_pct×0.25 + roe_pct×0.25 + growth_pct×0.25 + roce_pct×0.25
       > 0.5 → cheap vs peers on quality-adjusted basis
    3. Highlight: top-25th = green, bottom-25th = red

    Cache: data/peer_comparisons.csv (TTL: 30d)
    Rate limit: 5s sleep after each scrape
    """
```

**Acceptance criteria:** Peer table in company dashboard (E1). Target company row highlighted. Relative percentile shown for PE, ROE, Growth, ROCE.

---

#### E3 — Management Quality Score
**Size:** M | **Priority:** Medium — key differentiator between same-sector stocks

**What to build:**
```python
def management_quality_score(symbol: str, insider_data: pd.DataFrame,
                               concall_history: pd.DataFrame, fundamentals_5yr: pd.DataFrame) -> dict:
    """
    MQS = 4-component score (0–100)

    1. CAPITAL ALLOCATION (0–30):
       Buybacks done (+10), dividend CAGR > 10% (+10), D/E falling 5yr (+5), no dilutive equity raise (+5)

    2. PROMOTER COMMITMENT (0–25):
       Holding > 50% → 15 pts, trend RISING → +10, trend FALLING → -10
       Pledging: zero pledging → +5, pledging > 20% of promoter stake → -15

    3. CONCALL TONE TREND (0–20):
       Avg tone last 4 quarters: CONFIDENT=20, CAUTIOUS=12, DEFENSIVE=5
       Guidance raised → +5 bonus; cut → -5

    4. GOVERNANCE (0–25):
       Related party txn < 5% revenue → 15, ind directors > 33% board → 5,
       Auditor tenure > 5yr → 3, no SEBI action → 7

    MQS_CLASS: EXCELLENT (≥80), GOOD (60–79), ADEQUATE (40–59), POOR (<40)
    POOR management → -5 INVESTMENT_SCORE penalty
    """
```

**Acceptance criteria:** MQS badge in company dashboard + main report. Promoter holding sparkline in HTML.

---

#### E4 — Event-Driven Alert Engine
**Size:** M | **Priority:** High — time-sensitive catalysts are highest-value for active trading

**What to build:**
```python
def fetch_corporate_events(symbols: list[str], lookforward_days: int = 30) -> pd.DataFrame:
    """
    Sources:
    1. NSE: https://www.nseindia.com/api/corporates-corporateActions?index=equities
       Returns: ex-date, record date, purpose (dividend/bonus/rights/split/buyback)
    2. BSE: https://api.bseindia.com/BseIndiaAPI/api/AnnualResultSearch/w
       Returns: result announcement dates

    Event types and trading implications:
    RESULT_ANNOUNCEMENT : high volatility day; setup pre-result if earnings acceleration expected
    EX_DIVIDEND         : price drops by dividend; buy ex-date dip if uptrend intact
    BONUS / SPLIT       : psychological buying before ex-date; consolidation post-split
    BUYBACK             : company floor signal; check buyback_price vs CMP
    AGM                 : watch for guidance, capex, dividend policy changes

    INVESTMENT_SCORE adjustments:
    +3 : buyback above CMP (floor protection)
    +2 : result in 5–14 days + earnings acceleration expected
    -1 : result in next 3 days (uncertainty, reduce position sizing)

    Returns DataFrame: symbol, event_type, event_date, days_until, details
    Cache: data/corporate_events.csv (TTL: 24h)
    """

def generate_event_alerts(candidates: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Merge next event per symbol into candidates DataFrame.
    Add columns: NEXT_EVENT, NEXT_EVENT_DATE, NEXT_EVENT_DAYS.
    Generate alert text: 'RESULT in 3d — pre-result setup if RSI dip entry available'"""
```

**Files to create/modify:**
- `company_intelligence.py` — `fetch_corporate_events()`, `generate_event_alerts()`
- `data/corporate_events.csv` — daily cache
- `sector_rotation_report.py` — merge events; show `NEXT_EVENT` badge in HTML

**Acceptance criteria:**
- Events fetched daily and cached.
- Stocks with results in next 7 days flagged with `RESULT_UPCOMING` badge.
- Buyback above CMP shown with ₹target and % premium.
- Missing events = empty field, not error.

---

## 7. TECHNICAL DEBT & CLEANUP

| Item | File(s) | Action |
|---|---|---|
| 10 empty R stub files | `config.R`, `main.R`, `*demo.R` etc | Delete |
| `_sector_rotation_fund_tmp.csv` left after cache merge | `data/` | Delete in `_load_fundamental_details()` after successful cache update |
| Duplicate report output files (645+) | `reports/` | Archive anything older than 30 days to `reports/archive/` |
| `nse_analysis.db` schema undocumented | `nse_analysis.db` | Add schema doc to `docs/` |
| Portfolio analyzer phase 1 missing | `portfolio-analyzer/` | `phase1_pnl.py` not in pipeline |
| `.env` has both Anthropic and OpenAI keys; Anthropic unused | `.env` | Remove `ANTHROPIC_API_KEY` from active code |
| `README.md` is empty | `README.md` | Write 2-page project README |

---

## 8. IMPLEMENTATION ROADMAP

```
SPRINT 1 (DONE — 2026-05-02): Foundations
  ✅ P0-1  Signal Performance Logger
  ✅ P0-2  A+ Setup Classification
  ✅ P0-3  Formal Entry/Stop/Target Levels
  ✅ P0-4  Consolidate Data Sources
  ✅ P1-1  Market Regime Detector
  ✅ P1-2  F&O OI + PCR Signals
  ✅ P1-3  FII/DII Flow Signals

SPRINT 2 (READY): Signal Enrichment
  P1-4  Promoter/Insider Alerts           [M] — fetch_insider_alerts.py
  P1-5  Enhanced HTML Dashboard           [M] — sortable cols, heatmap
  P2-4  Portfolio-Aware Narratives        [L] — personalized entry/trim guidance

SPRINT 3: Market Intelligence Layer
  B1    Cross-Index Breadth Dashboard     [M] — index_intelligence.py
  B2    Global Correlation Monitor        [M] — yfinance integration
  B3    Sectoral Heat Calendar            [M] — seasonal alpha identification
  C1    McClellan Oscillator              [M] — market_breadth.py
  C2    TRIN / Arms Index                 [S]
  C3    Sector Breadth Divergence         [M]
  E4    Event-Driven Alert Engine         [M] — highest ROI in Branch E

SPRINT 4: Advanced Screeners
  A1    Stage Analysis Screener           [M] — screeners.py
  A2    Darvas Box Breakout               [M]
  A3    52W High Momentum                 [S]
  A6    Turnaround Detector               [S]
  P2-2  Counterfactual Scenarios          [L]

SPRINT 5: Deep Fundamentals (requires Screener.in 5yr scrape prerequisite)
  Prereq: extend fetch_screener_fundamental_details.R for 5-yr P&L + CFO + ROCE
  D5    Forensic Accounting Suite         [L] — deep_fundamentals.py (Beneish + Piotroski + Altman)
  D2    Earnings Quality Score            [M] — CCR, accruals, FCF yield
  D1    DuPont Decomposition              [M] — ROE driver analysis
  A4    Earnings Acceleration             [M] — quarterly EPS series required
  A7    Quality Compounder                [M] — 5yr CAGR screening
  P1-6  Macro-Economic Proxy Signals      [L] — GST, PMI, IIP, power data

SPRINT 6: Deep Fundamentals (cont) + Company Intelligence
  D6    Competitive Moat Score            [L] — pricing power, switching costs
  E2    Peer Comparison Engine            [M] — screener.in peers scrape
  E3    Management Quality Score          [M] — promoter + insider + concall
  P2-5  Concall Sentiment NLP (= D4)      [L] — BSE filings + LLM extraction
  A5    Institutional Accumulation        [M] — up/down volume ratio
  A8    Hidden Champions                  [M] — niche leaders, low coverage

SPRINT 7: Synthesis + Flow Intelligence
  E1    360° Company Dashboard            [XL] — ties together all of D + E
  B4    FII/DII Flow Battle Tracker       [M] — needs P1-3 data
  B5    Economic Cycle Tracker            [L] — needs P1-6 macro data
  D3    Business Cycle Positioning        [S] — extends B5 to stock level
  C4    Smart Money Flow Index            [M]
  P2-1  NSE Knowledge Graph              [XL]

SPRINT 8: Learning + Futuristic
  P2-3  Learning Loop                    [L] — 90 days signal data accumulated by now
  P3-2  Voice Briefing                   [M] — OpenAI TTS
  P3-1  Causal Inference Model           [XL] — 6+ months signal data required
  P3-3  Real-Time Mode                   [XL]
```

---

## 9. KEY DESIGN PRINCIPLES FOR CODING ASSISTANTS

1. **Never break existing pipelines.** `sector_rotation_report.py` runs end-to-end today — all additions are additive (new columns, new files, new functions). The existing flow must still work if a new module fails.

2. **All new data files go into `data/` folder.** Prefix with underscore if intermediate: `data/_fno_signals.csv`. Final outputs in `reports/`.

3. **NSE data access pattern:**  
   - Historical OHLCV: read from `data/nse_sec_full_data.csv` (already local)
   - External APIs (NSE, BSE): always use `curl` subprocess or `requests` with NSE headers; do NOT use `requests` directly on macOS without timeout + retry (known hang issue)
   - Rate limiting: 2-second sleep between NSE API calls

4. **All new external fetches must have a local cache with TTL.**  
   Pattern: check cache file age → if older than 24h, re-fetch → save → use.

5. **F&O and FII data is date-specific.** When data for today is not yet available (pre-market), use the previous trading day's data.

6. **LLM calls use `_llm_call()` in `sector_rotation_report.py`.** Do not add new `requests.post()` calls. Use the existing curl-subprocess helper.

7. **Python environment:** `.venv/` at project root. Activate with `source .venv/bin/activate`. R uses system R (Rscript must be in PATH).

8. **Regime detector is a gate, not a filter.** It never blocks signals; it re-weights them. A BEAR regime does not produce zero candidates — it produces candidates with lower scores and narrower setup classes.
