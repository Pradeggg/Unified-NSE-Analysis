---
name: daily-pipeline
description: Run the full Agent Adda 7-phase daily pipeline after NSE market close (~16:00 IST). Downloads bhavcopy, scores 965 stocks, generates all 8 HTML reports (EOD, Stage2, Sector Rotation, Top Picks, RRG, Portfolio, Swing Playbook, Fund Dashboard), validates them, and emails top picks. Use when the user says "run daily pipeline", "run EOD reports", "refresh all reports", or "run daily refresh".
---

# Daily Pipeline

Full 7-phase pipeline. Run after NSE market close (~16:00 IST). ~25–35 min wall-clock.

## Quickstart — one command

```bash
cd /Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis
source .venv/bin/activate
OPENAI_API_KEY=$(grep OPENAI_API_KEY /Users/pradeepgorai/Documents/Projects/finance/.env | cut -d= -f2-) \
  python daily_refresh.py
```

That runs all 7 phases in sequence. Report back with a summary when done (see **Report back** section).

## Flags

```bash
python daily_refresh.py --dry-run              # preview all steps, no execution
python daily_refresh.py --live-only            # fast price update only (~1 min)
python daily_refresh.py --skip-analysis        # skip heavy scoring, just tracker
python daily_refresh.py --fundamentals-backfill  # force full Nifty 500 screener backfill
python daily_refresh.py --skip-news            # skip yfinance news in fund dashboard
python daily_refresh.py --email-send           # actually send email (default is draft)
```

## Manual phase-by-phase (if pipeline fails mid-run)

Run these in exact order. Each step is a prerequisite for the ones below it.

### Phase 1 — Data Ingestion

```bash
# Step 0: bhavcopy from NSE archives
Rscript load_latest_nse_data_comprehensive.R

# Step 0B: load equity + index EOD into PostgreSQL
python postgres/loader.py --eod-only

# Step 1: auxiliary feeds
python fetch_fii_dii_flows.py
python fetch_fno_data.py --backfill 7
python fetch_corporate_events.py
python fetch_insider_alerts.py
python fetch_macro_proxies.py

# Step 1B: F&O into PostgreSQL
python postgres/loader.py --fno-only
```

### Phase 2 — Scoring  ⚠️ Order matters

```bash
# Step 2: universe scoring
python fixed_nse_universe_analysis.py --export-csv

# Step 2B: fundamentals ← MUST be before step 4B (PG-FUND-ORDER)
python postgres/loader.py --fundamentals-only

# Step 3A: historical stage backfill
python -m scripts.backfill_historical_stage_snapshots --start 2025-01-01 --lookback 2024-01-01

# Step 2C: VCP materialization ← MUST be before top_picks_report.py (VCP-PICKS-ORDER)
python scripts/materialize_stage2_vcp_picks.py --lookback-days 365
```

### Phase 3 — Strategy Lab

```bash
# Step 3B: paper-trading replay + HTML report
python -m portfolio.cli strategy-lab --start 2025-01-01 --top-n 200 --slippage-bps 5 --brokerage-bps 3
python report_validation.py --checkpoint portfolio_strategy_lab
```

### Phase 4 — Stage & Sector Reports  ⚠️ Order matters

```bash
# Step 4B: today's Weinstein stage snapshot ← runs AFTER 2B; uses DB history (500+ days)
python sector_rotation_tracker.py --snapshot --enrich-missing 10 --enrich-delay 2.5 --enrich-yfinance-fallback

# Step 7: full PG load + all 40 screeners
python postgres/loader.py

# Step 4B.5: repair any UNKNOWN stage rows
python -m scripts.backfill_historical_stage_snapshots --start $(date +%Y-%m-%d) --end $(date +%Y-%m-%d) --replace-existing

# Step 4A: sector rotation report
python sector_rotation_report.py
python report_validation.py --checkpoint sector_rotation

# Step 4C: Stage 2 tracker HTML
python sector_rotation_tracker.py --report --html
python report_validation.py --checkpoint stage2_tracker

# Step 4E: RRG + market breadth
python rrg_report.py
```

### Phase 5 — Picks & Market Reports

```bash
# Step 5A: warm fundamentals for today's picks
python top_picks_report.py --print-picks  # prints candidate list

# Step 5A.5: refresh corporate events & insider alerts
python fetch_corporate_events.py --force
python fetch_insider_alerts.py --force

# Step 5C: top picks (needs 2C VCP done first)
OPENAI_API_KEY=$(grep OPENAI_API_KEY /Users/pradeepgorai/Documents/Projects/finance/.env | cut -d= -f2-) \
  python top_picks_report.py
cp reports/top_picks/Top_Investment_Picks_Analysis_$(date +%Y%m%d)*.html reports/latest/top_picks.html
cp reports/top_picks/Top_Investment_Picks_Analysis_$(date +%Y%m%d)*.md   reports/latest/top_picks.md
python report_validation.py --checkpoint top_picks

# Step 5D: EOD market report
python scripts/build_eod_market_report.py --no-open
python report_validation.py --checkpoint eod_market
```

### Phase 6 — Portfolio & Fund

```bash
# Step 6: personal portfolio EOD
python -c "from terminal.portfolio_monitor import run_eod_report; run_eod_report()"
python report_validation.py --checkpoint portfolio_eod

# Step 6B: swing playbook
python -c "from terminal.swing_playbook import generate_swing_playbook, parse_swing_playbook_args; o=parse_swing_playbook_args('/swing-playbook --fresh'); generate_swing_playbook(options=o)"

# Step 6C: Aug Fund dashboard ← NEW
python tools/fund_refresh.py --no-open
```

### Phase 7 — Distribution & Maintenance

```bash
# Email top picks (draft by default; add --email-send to send)
python -m terminal.email_dispatcher top_picks --mode both

# Voice briefing script
python generate_voice_briefing.py --no-tts

# Results feed refresh
python -m scripts.refresh_results_feed --days-back 14 --limit 200 --delay 2.5

# Daily results analysis (LLM)
python -m scripts.analyze_daily_results --days-back 1 --limit 10

# Sundays only — or use --fundamentals-backfill flag:
# python scripts/backfill_screener_fundamentals.py

# Final validation: all reports clean
python report_validation.py
```

## Critical ordering rules

| Rule | What | Consequence if violated |
|---|---|---|
| **PG-FUND-ORDER** | Step 2B before Step 4B | Stage-2 HTML detail cards render NULL sub-scores |
| **VCP-PICKS-ORDER** | Step 2C before Step 5C | All picks get `sector+s2` source; no `vcp+sector` tag → validator HIGH |
| **CSV-200-ORDER** | Stage tracker needs 200+ day history | CSV has ~95 days → all stages UNKNOWN. Falls back to PG automatically. |

## If stage snapshot returns all-UNKNOWN

The tracker normally auto-falls-back to `market.equity_eod` (500+ days). If it doesn't:

```bash
mv data/nse_sec_full_data.csv data/nse_sec_full_data.csv.bak
python sector_rotation_tracker.py --snapshot --force
mv data/nse_sec_full_data.csv.bak data/nse_sec_full_data.csv
```

## Reports generated

| Report | Path | Validator checkpoint |
|---|---|---|
| EOD Market Report | `reports/latest/eod_market_report.html` | `eod_market` |
| Stage 2 Tracker | `reports/latest/stage2_tracker.html` | `stage2_tracker` |
| Sector Rotation | `reports/latest/sector_rotation.html` | `sector_rotation` |
| Top Investment Picks | `reports/latest/top_picks.html` | `top_picks` |
| RRG + Breadth | `reports/latest/market_breadth_rrg.html` | — |
| Portfolio EOD | `reports/latest/portfolio_analysis.html` | `portfolio_eod` |
| Swing Playbook | `reports/latest/swing_playbook.html` | — |
| **Aug Fund Dashboard** | `reports/latest/fund_dashboard.html` | — |
| Portfolio Strategy Lab | `reports/latest/portfolio_strategy_lab.html` | `portfolio_strategy_lab` |

## Report back

After the pipeline completes, summarise:

- ✅/❌ per phase
- Validation result: `findings=N high=N`
- Today's top picks (symbol list)
- Fund dashboard: SC P&L%, MC P&L%, combined P&L%
- Any SL breach alerts from the fund dashboard
- Any non-fatal failures or warnings
