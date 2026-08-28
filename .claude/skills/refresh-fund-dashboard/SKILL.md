---
name: refresh-fund-dashboard
description: End-to-end refresh of the Aug Fund dashboard. Reads fund_holdings.json, fetches live prices via yfinance, queries DB for snapshots/fundamentals/quarterly results, applies fund rules compliance gate, computes P&L for each position, and generates reports/latest/fund_dashboard.html with clickable stock detail modals. Use when the user asks to refresh, update, rebuild, or open the fund dashboard.
---

# Refresh Fund Dashboard

End-to-end pipeline: `data/fund_holdings.json` → prices → DB → HTML dashboard.

## Single command (recommended)

```bash
cd /Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis
source .venv/bin/activate 2>/dev/null || true
python tools/fund_refresh.py
```

This runs all 6 steps automatically:
1. **Load holdings** from `data/fund_holdings.json`
2. **Fetch live prices** via yfinance (`.NS` suffix)
3. **Query DB** — `scores.stage_snapshots`, `scores.fundamentals`, `scores.quarterly_results`
4. **Build stock detail data** — tech scores, fund scores, fundamentals, quarterly results
5. **Compute P&L and action queue** — per position + fund totals + stop-loss alerts; converts current critical/warning alerts into prioritised review actions
6. **Render HTML** — writes `reports/latest/fund_dashboard.html` and opens browser, with the **Action Items** tab first at the top

## Flags

```bash
# Refresh without opening browser
python tools/fund_refresh.py --no-open

# Use cached prices (skip yfinance call)
python tools/fund_refresh.py --skip-prices

# Only refresh prices then regenerate (skip DB)
python tools/fund_refresh.py --prices-only
```

## Adding / removing a position

Edit `data/fund_holdings.json` — it is the **single source of truth**.
Schema per position:
```json
{
  "NSE_SYMBOL": {
    "entry":      1234.50,
    "entry_date": "2026-08-17",
    "qty":        10,
    "fund":       "Aug SC",
    "note":       "ICICI Direct — market order 17-Aug-2026, filled"
  }
}
```
Then run `python tools/fund_refresh.py` to regenerate.

## Dashboard features

| Feature | Detail |
|---|---|
| **Fund P&L tab** | SC + MC tables with Entry, CMP, Qty, Invested, Current, P&L %, Stop ₹, Buy Date, Days |
| **Clickable symbols** | Opens side panel with full stock detail |
| **Fund Rules Gate** | ✅/❌ checklist per stock (Stage/RS/Tech/Fund/Supertrend/Signal) |
| **Technical** | TechScore, Stage, RS, RSI, Supertrend, Signal, Trend, Stance |
| **Fund Scores** | EnhFundScore, Earnings Quality, Sales Growth, Fin Strength, Inst Backing, Inv Score |
| **Fundamentals** | Piotroski F, ROE, ROCE, D/E, Promoter % |
| **Quarterly Results** | Last 5 quarters: Revenue, PAT, OPM% |
| **Stop-loss alerts** | Printed to console if any position hits SL threshold |
| **Action Items tab** | First tab; prioritised CRITICAL/WARNING alerts with evidence and suggested next review step. Rebuilt on every refresh. Review queue only — never auto-trades. |
| **Fund Rules tab** | Full rules & governance reference |

## Fund rules applied

**SC fund**: Stage=S2, RS≥65, TechScore≥65, FundScore≥65, Supertrend=BULLISH, Signal=BUY/HOLD, Stop=−8%
**MC fund**: Stage=S1/S2, RS≥65, TechScore≥65, FundScore≥65, Supertrend=BULLISH, Signal=BUY/HOLD, Stop=−7%

## Error handling

| Error | Fix |
|---|---|
| `ModuleNotFoundError` | `source .venv/bin/activate` |
| `yfinance` price missing | Fallback to cached price in `data/fund_prices_cache.json`; use `--skip-prices` |
| DB connection error | Check `postgres/loader.py` config; verify PostgreSQL is running |
| `KeyError: symbol` | Add DB alias to `NSE_TO_DB` dict in `tools/fund_refresh.py` |

## After running

Report back:
- ✅ Dashboard written — quote SC P&L, MC P&L, combined P&L %
- 🌐 Opened `file:///Users/pradeepgorai/Documents/Projects/finance/Unified-NSE-Analysis/reports/latest/fund_dashboard.html`
- ⚠️ Any stop-loss breach alerts
- If failed, show full error + fix

## Action Items tab contract

- The Action Items tab is generated from `generate_technical_alerts()` on every refresh.
- It includes every CRITICAL and WARNING alert, sorted by severity, with trigger evidence and a suggested next review step.
- It remains the first tab and the default active tab, aligned with the Alerts tab count.
- It is a review queue only; it must never place or imply automatic trades.
