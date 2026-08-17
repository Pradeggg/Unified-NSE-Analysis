# /eod-refresh — NSE EOD Data Refresh & Report Pipeline

Refresh all underlying NSE data (Equity, F&O, Indices) into PostgreSQL and
regenerate the full suite of EOD reports.

## Pre-flight checks

```bash
source .venv/bin/activate
pg_isready -h /tmp -U nse_admin -d nse_market
```

If PostgreSQL is not ready: `bash postgres/start_pg.sh start`

---

## Mode 1 — Full pipeline (standard daily EOD run)

Run after market close (~3:30 PM IST).

```bash
source .venv/bin/activate && python daily_refresh.py --skip-email
```

**Known quirks / fixed issues:**

| Issue | Status | Notes |
|-------|--------|-------|
| `stage_snapshots` empty at VCP materialize | ✅ Fixed | Stage backfill now runs before materialize (Step 3A → 2C order) |
| Exit 144 (SIGURG) during snapshot enrichment | ✅ Fixed | `--enrich-missing` default reduced 60 → 10 |
| EOD market report crashes without intraday | ✅ Fixed | Falls back to latest equity EOD date automatically |
| Stage tracker HTML crashes with NULL conn | ✅ Fixed | SQLite always opened as fallback in `build_change_report` |
| Top picks empty when supertrend is NULL | ✅ Fixed | Both pick-list queries allow `supertrend_state IS NULL` |
| Reports can show `UNKNOWN` stages after tracker snapshot | ✅ Fixed | Pipeline now repairs the latest PG snapshot after PostgreSQL load and before reports |

If you run `sector_rotation_tracker.py --snapshot` manually, it can still write
`STAGE_UNKNOWN` for all stocks when the comprehensive CSV has no STAGE column.
Repair that manual snapshot before generating reports:
```bash
python scripts/backfill_historical_stage_snapshots.py \
    --start $(date +%Y-%m-%d) --end $(date +%Y-%m-%d) --replace-existing
```
This is safe to run after a manual snapshot — it overwrites only stage/stage_score.

---

## Mode 2 — Data refresh only (no reports)

### A — Fetch fresh bhavcopy (equity + indices via R)
```bash
Rscript load_latest_nse_data_comprehensive.R
```

### B — Backfill F&O bhavcopy
```bash
source .venv/bin/activate
python fetch_fno_data.py --backfill 7      # last 7 trading days
python fetch_fno_data.py --backfill 70     # after a long gap
```

### C — Load everything into PostgreSQL
```bash
source .venv/bin/activate && python postgres/loader.py
```

---

## Mode 3 — Targeted segment loads

```bash
source .venv/bin/activate

# Equity + Indices EOD only
python postgres/loader.py --eod-only

# F&O only (bhavcopy → derivatives.fno_eod + analytics)
python postgres/loader.py --fno-only

# Fundamentals only (fast pre-snapshot refresh)
python postgres/loader.py --fundamentals-only
```

---

## Mode 4 — Recompute Minervini stages (required after --snapshot)

The tracker snapshot (`--snapshot`) writes STAGE_UNKNOWN for all stocks
because the comprehensive CSV has no STAGE column. Always fix this with:

```bash
source .venv/bin/activate
python scripts/backfill_historical_stage_snapshots.py \
    --start 2026-08-14 --end 2026-08-14 --replace-existing
```

This computes real STAGE_1/2/3/4 from SMA50/150/200 relationships and
writes them into `scores.stage_snapshots`.

---

## Mode 5 — Individual reports (run after data + stages are loaded)

| Report | Command |
|--------|---------|
| Sector Rotation | `python sector_rotation_report.py` |
| Stage 2 Tracker snapshot | `python sector_rotation_tracker.py --snapshot` |
| Stage 2 Tracker HTML | `python sector_rotation_tracker.py --report --html` |
| Market Breadth + RRG | `python rrg_report.py` |
| Top Investment Picks | `python top_picks_report.py --no-llm` |
| EOD Market Report | `python scripts/build_eod_market_report.py --no-open --date YYYY-MM-DD` |
| Portfolio EOD | `python -c "from terminal.portfolio_monitor import run_eod_report; run_eod_report()"` |
| Swing Playbook | `python -c "from terminal.reports import generate_preset_report; r=generate_preset_report('swing-playbook','html'); print(r.html_path)"` |
| Portfolio Strategy Lab | `python -c "from terminal.reports import generate_preset_report; r=generate_preset_report('strategy-lab','html'); print(r.html_path)"` |

**Note on EOD Market Report**: pass `--date` explicitly (e.g. `--date 2026-08-14`)
because auto-detection requires an `intraday.ohlcv_bars` table with data.
If no intraday bars exist the script raises RuntimeError without `--date`.

---

## Mode 6 — Live prices only (fast, ~1 min)

```bash
source .venv/bin/activate && python daily_refresh.py --live-only
```

---

## What's in PostgreSQL

| Table | Rows (Aug 2026) | Description |
|-------|-----------------|-------------|
| `market.equity_eod` | 228,677 | Daily OHLCV — 2,721 symbols, Mar–Aug 2026 |
| `market.index_eod` | 12,962 | 139 NSE indices, Mar–Aug 2026 |
| `market.global_index_levels` | 996 | SPX, FTSE, Nikkei, etc. |
| `ref.instruments` | 2,406 | NSE master list, sectors, ISIN |
| `ref.indices` | 15 | Nifty 50/100/200/500 etc. |
| `ref.index_compositions` | 3,250 | Index memberships |
| `derivatives.fno_eod` | 3,210,002 | F&O bhavcopy — Apr–Aug 2026 |
| `derivatives.fno_signals` | 214 | PCR, OI change, max pain, buildup |
| `scores.stage_snapshots` | 227K+ | Daily Minervini stage per symbol |
| `scores.fundamental_scores` | 425 | Composite fundamental scores |
| `breadth.market_daily` | 287 | Market-wide breadth indicators |
| `signals.fii_dii_flows` | — | FII/DII flows |
| `signals.bulk_block_deals` | 521 | Bulk & block deals |

---

## Reports generated (`reports/latest/`)

| File | Description |
|------|-------------|
| `stage2_tracker.html` | Stage 2 VCP tracker — ranked candidates |
| `sector_rotation.html` + `.pdf` | Full sector rotation report |
| `market_breadth_rrg.html` | Market breadth + RRG chart |
| `top_picks.html` | Top 10 investment picks with charts |
| `eod_market_report.html` | EOD market tape — breadth, movers |
| `portfolio_strategy_lab.html` | Strategy lab backtest comparison |
| `portfolio_eod.html` | Personal portfolio EOD P&L |
| `swing_playbook.html` | Swing trading ideas |

Open all key reports:
```bash
open reports/latest/stage2_tracker.html \
     reports/latest/top_picks.html \
     reports/latest/eod_market_report.html \
     reports/latest/market_breadth_rrg.html \
     reports/latest/sector_rotation.html
```

---

## Verify DB state

```bash
psql "dbname=nse_market user=nse_admin host=/tmp" -c "
SELECT tbl, cnt, latest FROM (
  SELECT 'equity_eod'      AS tbl, count(*)::int AS cnt, max(trade_date)::text AS latest FROM market.equity_eod
  UNION ALL SELECT 'index_eod',    count(*)::int, max(trade_date)::text FROM market.index_eod
  UNION ALL SELECT 'fno_eod',      count(*)::int, max(trade_date)::text FROM derivatives.fno_eod
  UNION ALL SELECT 'fno_signals',  count(*)::int, NULL                  FROM derivatives.fno_signals
  UNION ALL SELECT 'instruments',  count(*)::int, NULL                  FROM ref.instruments
  UNION ALL SELECT 'stage_snapshots', count(*)::int, max(snapshot_date)::text FROM scores.stage_snapshots
) t ORDER BY tbl;"
```

---

## First-time / empty database setup

```bash
# 1. Apply schemas
psql "dbname=nse_market user=nse_admin host=/tmp" -f postgres/schema.sql
psql "dbname=nse_market user=nse_admin host=/tmp" -f postgres/screener_schema.sql
psql "dbname=nse_market user=nse_admin host=/tmp" -f postgres/fno_analytics.sql

# Create intraday schema (needed by EOD market report)
psql "dbname=nse_market user=nse_admin host=/tmp" -c "
  CREATE SCHEMA IF NOT EXISTS intraday;
  CREATE TABLE IF NOT EXISTS intraday.ohlcv_bars (
    id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL, timeframe TEXT NOT NULL DEFAULT '15m',
    open NUMERIC(14,4), high NUMERIC(14,4), low NUMERIC(14,4),
    close NUMERIC(14,4), volume BIGINT,
    UNIQUE (symbol, timestamp, timeframe)
  );"

# 2. Seed ref.instruments + ref.indices
source .venv/bin/activate
python scripts/load_nse_instrument_sectors.py --skip-meta

# 3. Backfill F&O
python fetch_fno_data.py --backfill 70

# 4. Full loader
python postgres/loader.py

# 5. Compute Minervini stages for all history
python scripts/backfill_historical_stage_snapshots.py

# 6. Run reports
python sector_rotation_report.py
python sector_rotation_tracker.py --report --html
python rrg_report.py
python top_picks_report.py --no-llm
python scripts/build_eod_market_report.py --no-open --date $(date +%Y-%m-%d)
```

---

## Scheduling (launchd — macOS)

```bash
launchctl list | grep agentadda                         # check status
launchctl load   com.agentadda.daily_refresh.plist      # enable
launchctl unload com.agentadda.daily_refresh.plist      # disable
```
