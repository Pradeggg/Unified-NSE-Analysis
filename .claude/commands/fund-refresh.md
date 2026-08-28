# /fund-refresh — Daily Fund Dashboard Refresh

Refresh the Agent Adda fund dashboard. Regenerate the P&L report, rebuild the
combined dashboard, and print a concise terminal summary of what changed.

## Steps

Run each step in order. Stop and report clearly if any step fails.

### 1 — Regenerate the P&L report

```bash
python tools/fund_lab_pnl.py --report
```

Generates `reports/latest/fund_lab.html` with live prices from yfinance and
DB-backed signals (HOLD / STRONG HOLD / WEAKENING / EXIT / NEW ENTRY).

### 2 — Rebuild the combined dashboard

```bash
python tools/fund_dashboard_build.py
```

Combines `fund_lab.html` + the latest `fund_inception_*.html` into
`reports/latest/fund_dashboard.html` with properly scoped CSS.

### 3 — Print a terminal summary

After both scripts finish, read their stdout output and print a concise summary:

```
═══════════════════════════════════════════════
  FUND DASHBOARD REFRESH — <today's date>
═══════════════════════════════════════════════
  SC Portfolio:  ₹<invested>  →  ₹<current>  (<pnl%>)
  MC Portfolio:  ₹<invested>  →  ₹<current>  (<pnl%>)
  Combined:      ₹<invested>  →  ₹<current>  (<pnl%>)

  Signals:
    🟢 STRONG HOLD  <symbols>
    🔵 HOLD         <symbols>
    🟡 WEAKENING    <symbols>
    🔴 EXIT         <symbols>
    🆕 NEW ENTRY    <symbols>

  Dashboard → reports/latest/fund_dashboard.html
═══════════════════════════════════════════════
```

Only show signal categories that have at least one symbol.

### 4 — Flag anything actionable

The generated dashboard must also place these items in the first **Action Items** tab,
with severity, symbol, evidence, and a suggested next review step. This is a review
queue only and must remain aligned with the Alerts tab.

If any position has signal EXIT or WEAKENING, print a clear warning:

```
⚠  ACTION REQUIRED: <SYMBOL> → <signal> (<reason>)
```

If no positions need action, print:
```
✓  All positions holding. No action required.
```

### 5 — Prompt about new fills

Ask: "Any new order fills to record in data/fund_holdings.json?"
If yes, collect symbol, entry price, qty, and fund (SC/MC), then write them
into `data/fund_holdings.json` under the correct key and confirm.

## Notes

- `data/fund_holdings.json` is the single source of truth for all active
  holdings. Never modify it unless the user confirms a fill.
- The Order Sheet tab (`fund_inception_*.html`) is regenerated separately with
  `python tools/fund_daily.py --fresh --tranche 25 --html` — only do this if
  the user explicitly asks for a new order sheet (Mondays).
- Run on market days only. If today is Saturday/Sunday, note it and skip unless
  the user overrides.
