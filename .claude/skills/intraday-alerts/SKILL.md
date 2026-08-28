# Intraday Alerts

Live F&O intraday scan with trigger-based email alerts. Scans the F&O universe every N minutes, detects active/near setups, and emails candidates to the `intraday_alerts` distribution list.

## Quickstart — one scan cycle + send email

```bash
cd /Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis
source .venv/bin/activate
OPENAI_API_KEY=$(grep OPENAI_API_KEY /Users/pradeepgorai/Documents/Projects/finance/.env | cut -d= -f2-) \
  python -m terminal.live_intraday_alerts --cycles 1 --send
```

## Continuous mode (runs until market close)

```bash
OPENAI_API_KEY=$(grep OPENAI_API_KEY /Users/pradeepgorai/Documents/Projects/finance/.env | cut -d= -f2-) \
  python -m terminal.live_intraday_alerts --cycles 0 --interval 60 --send
```

## Key flags

```bash
# Single scan, dry-run preview only (no email)
python -m terminal.live_intraday_alerts --cycles 1 --dry-run

# Custom symbols
python -m terminal.live_intraday_alerts --symbols NIFTY,BANKNIFTY,RELIANCE,HDFCBANK --cycles 1 --send

# Change candle interval (default 15m)
python -m terminal.live_intraday_alerts --candle-interval 5m --cycles 1 --send

# No LLM commentary (faster, deterministic)
python -m terminal.live_intraday_alerts --cycles 1 --no-llm --send

# Trigger filter
python -m terminal.live_intraday_alerts --trigger active    # only active setups
python -m terminal.live_intraday_alerts --trigger near      # only near setups
python -m terminal.live_intraday_alerts --trigger active_or_near  # both (default)

# Email cadence (default: every 15 min in continuous mode)
python -m terminal.live_intraday_alerts --cycles 0 --email-every-mins 30 --send

# Minimum R:R threshold for email alert (default 2.0)
python -m terminal.live_intraday_alerts --min-rr 1.5 --cycles 1 --send
```

## Default F&O universe

NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY + top liquid F&O names (BEL, TRENT, DIXON, SCHNEIDER, INDUSINDBK, NESTLEIND, ICICIBANK, MCX, RELIANCE, HDFCBANK, SBIN, ADANIENT, TCS, AXISBANK, KOTAKBANK, LT, …)

## Recipients

Configured in `config/report_recipients.yml` under `intraday_alerts`:
- **To:** pgorai@icloud.com
- **BCC:** hitesh86, hinamanit, gorai.sandeep, mbinjola, avirup.sen, vitangirala, kapilsingh143, aumahale, pikcool, tvphani, mdbhatia52

## Logs

Each run appends to `logs/intraday_alerts_<YYYYMMDD>_<HHMMSS>.jsonl`.
Latest alert markdown: `logs/intraday_alerts_latest.md`
Preview HTML: `logs/_intraday_alert_preview_<timestamp>.html`

## Market hours check

The script auto-detects session status. Outside 09:15–15:30 IST it will warn but still run (useful for testing with EOD data).

## After running

Report back:
- Number of candidates found and their symbols
- Trigger type (active / near)
- R:R of top candidates
- Whether email was sent or draft opened
- Any errors (ModuleNotFoundError → activate venv; no data → check market hours)
