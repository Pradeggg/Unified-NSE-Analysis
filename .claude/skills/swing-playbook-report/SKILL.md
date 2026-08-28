# Swing Playbook Report

Generates the **Agent Adda dark-terminal themed Swing Playbook HTML report**.

Runs the full pipeline:
1. Pulls swing candidates from PostgreSQL (`scores.daily_scores`)
2. Checks overextension signals (RSI14 > 72 or price > 7% above SMA20)
3. Fetches live market context (NIFTY, BANKNIFTY, VIX, breadth, Stage 2 %)
4. Renders themed HTML with sparklines, TradingView + Screener.in links, R:R
5. Overwrites `reports/latest/swing_playbook.html` and archives dated copy

## Quickstart

```bash
cd /Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis
source .venv/bin/activate
python scripts/generate_swing_playbook_report.py
```

## Key flags

```bash
# Re-pull candidates from PostgreSQL (use after daily data load)
python scripts/generate_swing_playbook_report.py --fresh

# Re-render from existing CSV without re-running data pipeline
python scripts/generate_swing_playbook_report.py --from-csv

# More candidates per sleeve (default 10)
python scripts/generate_swing_playbook_report.py --top-n 15

# Skip opening in browser (for cron / pipeline use)
python scripts/generate_swing_playbook_report.py --no-open

# Full pipeline with refresh + 15 candidates, no browser
python scripts/generate_swing_playbook_report.py --fresh --top-n 15 --no-open
```

## Prerequisites

- PostgreSQL running: `./postgres/start_pg.sh start`
- Daily pipeline completed: `python daily_refresh.py` (or `--skip-analysis` at minimum)
- Venv active with `terminal.swing_playbook` importable

## Output files

| File | Purpose |
|------|---------|
| `reports/latest/swing_playbook.html` | Main dark-themed report (overwritten each run) |
| `reports/latest/swing_playbook_candidates.csv` | Raw candidate data |
| `reports/latest/swing_playbook.md` | Markdown version |
| `reports/swing_playbook/{YEAR}/Swing_Playbook_{YYYYMMDD}_themed.html` | Daily archive |

## What the report shows

- **Narrative header** — two-column: methodology explainer + today's market summary (auto-generated from live data)
- **Market context strip** — NIFTY, BANKNIFTY, VIX, breadth, Stage 2%, stance pill
- **Summary cards** — tactical count, position count, top score, regime
- **Two tabs** — Tactical Swings (shorter stops) and Position Swings (wider stops)
- **Per-row** — sparkline chart, composite score + bar, entry/stop/T1/T2 prices, R:R badge, RSI tag, TEC/RS/FND mini-bars, TradingView + Screener.in links
- **Overextension flags** — RSI > 72 or price > 7% above SMA20 → amber `⚠ EXTENDED` badge, yellow sparkline, muted score, amber row highlight, disclaimer block at bottom
- **SEBI disclaimer** — full text matching agentadda.in standard

## Overextension logic

```
overextended = (rsi_14 > 72) OR (pct_above_sma20 > 7.0)
```

Sourced from `scores.daily_scores` (latest date per symbol). Overextended setups:
- Show amber `⚠ EXTENDED` badge next to stage pill
- Score bar switches to yellow→red gradient
- Row background is amber-tinted
- RSI column shows red tag `RSI 74` etc.
- Disclaimer block renders with exact overextended symbol names

## Integration with daily pipeline

Add to `daily_refresh.py` after Step 5 (picks), before Step 7 (distribution):

```python
# Step 5B.5 — themed swing playbook report
subprocess.run([
    sys.executable, "scripts/generate_swing_playbook_report.py",
    "--no-open", "--fresh"
], check=True)
```

Or add as a REPL `/swing-playbook-report` alias in `nse_agent.py`:

```python
"/swing-playbook-report": "python scripts/generate_swing_playbook_report.py",
```

## After running

Report back:
- Number of tactical + position candidates found
- Top candidate name and score
- Number of overextended setups flagged (and their symbols)
- Market context: NIFTY level + change, regime, breadth
- Path to generated report
- Any errors (DB connection, missing CSV, import errors)
