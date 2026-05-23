#!/usr/bin/env python3
"""
End-to-end test harness for the `<cmd> | /email ...` pipe feature.

Runs 25 diverse scenarios. For each scenario:
  1. Creates a fresh rich.Console with record=True (mimics the REPL's pipe path).
  2. Renders representative content into that console (tables, panels, markdown,
     or real data from CSVs/Postgres).
  3. Captures the recorded text → writes `reports/generated/piped_<slug>_<ts>.md`.
  4. Dispatches `/email <path> --to pgorai@deloitte.com --send` via the existing
     email_dispatcher (LLM subject + body, sent immediately via Outlook).

Usage:
  python scripts/test_email_pipe.py                 # send all 25
  python scripts/test_email_pipe.py --dry-run       # write HTML previews only
  python scripts/test_email_pipe.py --limit 3       # only first N scenarios
  python scripts/test_email_pipe.py --to a@x.com    # override recipient
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from terminal.email_dispatcher import run_email_command


GENERATED = ROOT / "reports" / "generated"
GENERATED.mkdir(parents=True, exist_ok=True)
DATA = ROOT / "data"


# ─────────────────────────────────────────────────────────────────────────────
# Lazy agent — only needed for the LLM-drafted email subject/body.
# ─────────────────────────────────────────────────────────────────────────────

_agent_singleton = None


def _get_agent():
    global _agent_singleton
    if _agent_singleton is None:
        try:
            from terminal.agent import Agent  # type: ignore
            _agent_singleton = Agent()
        except Exception:
            class _Stub:
                backend = None
            _agent_singleton = _Stub()
    return _agent_singleton


# ─────────────────────────────────────────────────────────────────────────────
# Scenario builders — each returns (label, render_fn(console))
# ─────────────────────────────────────────────────────────────────────────────


def _csv_head(name: str, cols: list[str] | None = None, n: int = 12) -> pd.DataFrame:
    path = DATA / name
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if cols:
        df = df[[c for c in cols if c in df.columns]]
    return df.head(n)


def _render_table(console: Console, title: str, df: pd.DataFrame) -> None:
    if df.empty:
        console.print(f"[yellow]{title}: no rows available[/yellow]")
        return
    tbl = Table(title=title, header_style="bold cyan")
    for col in df.columns:
        tbl.add_column(str(col))
    for _, row in df.iterrows():
        tbl.add_row(*[str(v) for v in row.values])
    console.print(tbl)


def scenario_fii_dii(console: Console) -> None:
    df = _csv_head("fii_dii_flows.csv", n=10)
    _render_table(console, "FII / DII flows — last 10 days", df)


def scenario_insider_alerts(console: Console) -> None:
    df = _csv_head("insider_alerts_agg.csv", n=15)
    _render_table(console, "Insider alerts (aggregated, top 15)", df)


def scenario_corporate_events(console: Console) -> None:
    df = _csv_head("corporate_events.csv", n=20)
    _render_table(console, "Upcoming corporate events (next 20)", df)


def scenario_sector_breadth(console: Console) -> None:
    df = _csv_head("sector_breadth.csv", n=12)
    _render_table(console, "Sector breadth snapshot", df)


def scenario_macro_proxy(console: Console) -> None:
    df = _csv_head("macro_proxy_signals.csv", n=12)
    _render_table(console, "Macro proxy signals", df)


def scenario_seasonal(console: Console) -> None:
    df = _csv_head("seasonal_monthly_returns.csv", n=12)
    _render_table(console, "Seasonal monthly returns", df)


def scenario_global_indices(console: Console) -> None:
    df = _csv_head("global_indices.csv", n=15)
    _render_table(console, "Global indices snapshot", df)


def scenario_signal_log(console: Console) -> None:
    df = _csv_head("signal_log.csv", n=15)
    _render_table(console, "Signal log — most recent 15", df)


def scenario_voice_briefing(console: Console) -> None:
    p = ROOT / "reports" / "voice_briefings" / "briefing_2026-05-19.txt"
    if p.exists():
        console.print(Markdown(f"## Voice briefing — 2026-05-19\n\n```\n{p.read_text()[:3000]}\n```"))
    else:
        console.print("[yellow]voice briefing not found[/yellow]")


def scenario_sector_rotation_md(console: Console) -> None:
    p = ROOT / "reports" / "latest" / "sector_rotation.md"
    if p.exists():
        console.print(Markdown(p.read_text()[:4000]))
    else:
        console.print("[yellow]sector rotation markdown not found[/yellow]")


def scenario_ric_sherlock_dmart(console: Console) -> None:
    console.print(Panel.fit(
        "[bold cyan]/ric sherlock DMART[/bold cyan]\n"
        "Step 1 — Quote: DMART @ ₹3,940.50  (+1.42% · vol 1.2× avg)\n"
        "Step 2 — Technicals: RSI 58, MACD bullish, above 50/200 DMA\n"
        "Step 3 — Fundamentals: P/E 92, ROE 14.8%, debt-free\n"
        "Step 4 — News: Q4 results due 25-May, broker upgrades 3\n"
        "Step 5 — Trade: BUY zone ₹3,880–3,920, target ₹4,180, SL ₹3,820",
        title="RIC: Sherlock Investigation",
        border_style="cyan",
    ))


def scenario_strategy_council(console: Console) -> None:
    console.print(Markdown(
        "## Strategy Council Verdict — RELIANCE\n\n"
        "**Verdict:** ACCUMULATE on dips · Confidence: 0.71\n\n"
        "- ✅ Bullish: trend score 78, RS vs Nifty +4.2%\n"
        "- ⚠️ Caution: F&O OI buildup short, FII selling 5D\n"
        "- 📊 Fundamentals: Q4 PAT +12% YoY, beat consensus\n"
        "- 🎯 Entry: ₹1,420–1,440 · Target: ₹1,580 · SL: ₹1,380\n"
    ))


def scenario_top_movers(console: Console) -> None:
    rows = [
        ("CHEMCON",   "STRONG_BUY", "+10.68%", "81.3"),
        ("GRANULES",  "STRONG_BUY", "+4.79%",  "80.0"),
        ("MANINDS",   "BUY",        "+2.09%",  "78.0"),
        ("APOLLO",    "BUY",        "+9.55%",  "76.0"),
        ("DEEPINDS",  "BUY",        "+6.05%",  "76.0"),
    ]
    tbl = Table(title="Top movers today — STRONG_BUY / BUY", header_style="bold green")
    for c in ["Symbol", "Signal", "Change 1D", "Tech Score"]:
        tbl.add_column(c)
    for r in rows:
        tbl.add_row(*r)
    console.print(tbl)


def scenario_nifty_pulse(console: Console) -> None:
    rows = [
        ("Nifty 50",     "23,618",  "SELL",        "39.7", "-5.02%"),
        ("Nifty Bank",   "53,409",  "SELL",        "30.3", "-10.75%"),
        ("Nifty IT",     "29,308",  "SELL",        "51.4", "-3.19%"),
        ("Nifty Pharma", "24,867",  "BUY",         "85.6", "+8.32%"),
        ("Nifty Metal",  "13,164",  "STRONG_BUY",  "54.3", "+7.29%"),
        ("Nifty Auto",   "25,699",  "SELL",        "45.9", "-6.69%"),
    ]
    tbl = Table(title="Index pulse — 2026-05-19", header_style="bold magenta")
    for c in ["Index", "Level", "Signal", "RSI", "50D Momentum"]:
        tbl.add_column(c)
    for r in rows:
        tbl.add_row(*r)
    console.print(tbl)


def scenario_stage2_summary(console: Console) -> None:
    console.print(Markdown(
        "## Stage 2 Tracker — 2026-05-19\n\n"
        "- **Total Stage 2 stocks:** 187 (down 3 from yesterday)\n"
        "- **New entrants today:** 21\n"
        "- **Exits today:** 17\n"
        "- **After hard-gate filter:** 29 candidates remain\n\n"
        "**Top hard-gate survivors:** CHEMCON, GRANULES, MANINDS, APOLLO, DEEPINDS, "
        "TALBROAUTO, COSMOFIRST, STAR, GLENMARK, AUROPHARMA"
    ))


def scenario_fno_signals(console: Console) -> None:
    df = _csv_head("fno_signals.csv", n=12)
    _render_table(console, "F&O signals — top 12", df)


def scenario_results_feed(console: Console) -> None:
    rows = [
        ("BOSCHLTD", "2026-05-20", "Q4 Results + Dividend"),
        ("APOLLOHOSP","2026-05-20", "Q4 Results + Dividend + Buyback"),
        ("ABCAPITAL","2026-05-20", "Board meeting — fund raise"),
        ("GRASIM",   "2026-05-20", "Q4 Results + Dividend"),
        ("MOTHERSON","2026-05-20", "Fund raising board meet"),
    ]
    tbl = Table(title="Results / Events — next 24h", header_style="bold yellow")
    for c in ["Symbol", "Date", "Event"]:
        tbl.add_column(c)
    for r in rows:
        tbl.add_row(*r)
    console.print(tbl)


def scenario_market_dashboard(console: Console) -> None:
    console.print(Markdown(
        "## Market Dashboard — 2026-05-19\n\n"
        "| Metric | Value | Trend |\n"
        "|---|---|---|\n"
        "| Nifty 50 | 23,618 (-0.42%) | 🔻 |\n"
        "| Advances/Declines | 781/1,532 | 🔻 |\n"
        "| FII Net (₹Cr) | -2,457 | 🔻 |\n"
        "| DII Net (₹Cr) | +3,802 | 🔺 |\n"
        "| Flow Signal | NEUTRAL | ➡️ |\n"
        "| Stage 2 stocks | 187 | 🔻 |\n"
        "| Regime | ROTATION | 🔄 |\n"
    ))


def scenario_data_coverage(console: Console) -> None:
    console.print(Markdown(
        "## /data-coverage report\n\n"
        "- **market.equity_eod**: 348,863 rows · 2025-10-13 → 2026-05-19 ✅\n"
        "- **market.index_eod**: 973 rows · 2026-05-11 → 2026-05-19 ✅\n"
        "- **scores.daily_scores**: 906 rows for 2026-05-19 ✅\n"
        "- **fundamentals.screener**: 700 records ✅\n"
        "- **insider_alerts**: 42 symbols ✅\n"
    ))


def scenario_morning_intel(console: Console) -> None:
    console.print(Markdown(
        "## Morning Intelligence — 20 May 2026\n\n"
        "### Global cues\n- S&P 500 -0.4% · Dow -0.3% · Nasdaq -0.5%\n- Brent $84.21 (+0.6%) · USD/INR 83.42\n\n"
        "### India setup\n- Nifty 50 -0.42% yesterday · close 23,618\n- FII -₹2,457Cr · DII +₹3,802Cr\n- Stage 2: 187 stocks · 21 new entrants\n\n"
        "### Watchlist (today)\nCHEMCON · GRANULES · APOLLO · NAVINFLUOR · STAR\n"
    ))


def scenario_breadth(console: Console) -> None:
    df = _csv_head("breadth_history.csv", n=10)
    _render_table(console, "Market breadth — last 10 sessions", df)


def scenario_portfolio_pnl(console: Console) -> None:
    rows = [
        ("RELIANCE",  "100", "1,420", "1,445", "+2,500", "+1.76%"),
        ("HDFCBANK",  "50",  "1,580", "1,612", "+1,600", "+2.03%"),
        ("INFY",      "75",  "1,420", "1,398", "-1,650", "-1.55%"),
        ("DMART",     "30",  "3,880", "3,940", "+1,800", "+1.55%"),
    ]
    tbl = Table(title="Portfolio P&L snapshot", header_style="bold blue")
    for c in ["Symbol", "Qty", "Avg Cost", "LTP", "P&L (₹)", "Return"]:
        tbl.add_column(c)
    for r in rows:
        tbl.add_row(*r)
    console.print(tbl)


def scenario_regime_detect(console: Console) -> None:
    console.print(Panel.fit(
        "[bold yellow]Market Regime[/bold yellow]: ROTATION\n\n"
        "- Trend score: 38/100 (mid-bear)\n"
        "- Breadth thrust: -22 (advance-decline negative 3D)\n"
        "- Volatility: VIX-equiv 14.2 (rising)\n"
        "- Sector dispersion: HIGH (Pharma/Metal up · Bank/Auto down)\n"
        "- Recommendation: TIGHT stops, sector-rotation trades only",
        title="Regime Detector",
        border_style="yellow",
    ))


def scenario_pullback_recovery(console: Console) -> None:
    rows = [
        ("MARUTI",     "12,420", "-8.2%", "STAGE_2", "BUY"),
        ("ASIANPAINT", "2,840",  "-6.5%", "STAGE_2", "BUY"),
        ("TITAN",      "3,250",  "-7.1%", "STAGE_2", "ACCUMULATE"),
    ]
    tbl = Table(title="Pullback recovery candidates", header_style="bold green")
    for c in ["Symbol", "LTP", "Drawdown", "Stage", "Action"]:
        tbl.add_column(c)
    for r in rows:
        tbl.add_row(*r)
    console.print(tbl)


def scenario_company_xray_dmart(console: Console) -> None:
    console.print(Markdown(
        "## DMART — 9-step Company Xray\n\n"
        "1. **Identity** — Avenue Supermarts, FMCG retail, ₹2.56L Cr m-cap\n"
        "2. **Financials** — Sales ₹50,789 Cr (+17% YoY) · NP ₹2,536 Cr\n"
        "3. **Ratios** — ROE 14.8% · ROCE 18.6% · D/E 0.04\n"
        "4. **Technicals** — Above 50/200 DMA · RSI 58 · MACD bullish\n"
        "5. **Sector** — FMCG +1.6% MTD · #3 in retail leader index\n"
        "6. **Catalysts** — Q4 due 25-May · 50 new stores FY27 guidance\n"
        "7. **Forensics** — Beneish -2.4 ✓ · Piotroski 7 ✓ · Altman 7.2 ✓\n"
        "8. **Insider** — No promoter activity (last 90d)\n"
        "9. **Verdict** — ACCUMULATE · Target ₹4,180 (12m)\n"
    ))


def scenario_backtest(console: Console) -> None:
    console.print(Markdown(
        "## /backtest VCP RELIANCE 90d\n\n"
        "- Trades: 4 · Winners: 3 · Win rate: 75%\n"
        "- Total return: +14.2% · vs Nifty: +9.8% · Alpha: +4.4%\n"
        "- Max drawdown: -3.1% · Sharpe: 1.62\n"
        "- Avg holding: 8 days · Avg gain/trade: +3.55%\n"
    ))


def scenario_news_brief(console: Console) -> None:
    console.print(Markdown(
        "## News Brief — Top 5 (19 May 2026)\n\n"
        "1. **RBI** — Repo unchanged at 6.50%; CRR cut by 25 bps · Bank-positive\n"
        "2. **Pharma** — USFDA approval for Cipla generic Advair · CIPLA +4%\n"
        "3. **IT** — TCS wins $1.2B BFSI deal · positive read-through to peers\n"
        "4. **Metals** — China stimulus ↑ steel; JSW Steel + Tata Steel rallying\n"
        "5. **Macro** — FII outflows 5D ₹-2,830 Cr · DII inflows ₹+11,078 Cr\n"
    ))


def scenario_volatility_alert(console: Console) -> None:
    console.print(Panel.fit(
        "[bold red]VOLATILITY ALERT[/bold red] — 2026-05-19 19:30 IST\n\n"
        "ATR-expansion in: ADANIENT, ADANIPORTS, INDIGO\n"
        "F&O OI build-up: ADANIENT short, INDIGO long\n"
        "Action: avoid fresh longs in ADANIENT until volatility settles",
        title="Alerts",
        border_style="red",
    ))


# Registry: (id, title-for-subject, render_fn)
SCENARIOS = [
    ("01-fii-dii",            "FII/DII flows",              scenario_fii_dii),
    ("02-insider",            "Insider alerts",             scenario_insider_alerts),
    ("03-corp-events",        "Upcoming corporate events",  scenario_corporate_events),
    ("04-sector-breadth",     "Sector breadth",             scenario_sector_breadth),
    ("05-macro-proxy",        "Macro proxy signals",        scenario_macro_proxy),
    ("06-seasonal",           "Seasonal returns",           scenario_seasonal),
    ("07-global",             "Global indices",             scenario_global_indices),
    ("08-signal-log",         "Signal log",                 scenario_signal_log),
    ("09-voice-briefing",     "Voice briefing",             scenario_voice_briefing),
    ("10-sector-rotation",    "Sector rotation report",     scenario_sector_rotation_md),
    ("11-ric-sherlock-dmart", "RIC Sherlock DMART",         scenario_ric_sherlock_dmart),
    ("12-strategy-council",   "Strategy council RELIANCE",  scenario_strategy_council),
    ("13-top-movers",         "Top movers",                 scenario_top_movers),
    ("14-nifty-pulse",        "Nifty index pulse",          scenario_nifty_pulse),
    ("15-stage2-summary",     "Stage 2 tracker summary",    scenario_stage2_summary),
    ("16-fno-signals",        "F&O signals",                scenario_fno_signals),
    ("17-results-feed",       "Results feed",               scenario_results_feed),
    ("18-market-dashboard",   "Market dashboard",           scenario_market_dashboard),
    ("19-data-coverage",      "Data coverage",              scenario_data_coverage),
    ("20-morning-intel",      "Morning intel",              scenario_morning_intel),
    ("21-breadth",            "Market breadth history",     scenario_breadth),
    ("22-portfolio-pnl",      "Portfolio P&L",              scenario_portfolio_pnl),
    ("23-regime",             "Regime detector",            scenario_regime_detect),
    ("24-pullback",           "Pullback recovery picks",    scenario_pullback_recovery),
    ("25-company-xray-dmart", "Company Xray DMART",         scenario_company_xray_dmart),
]


# ─────────────────────────────────────────────────────────────────────────────

def run_scenario(idx: int, sid: str, title: str, fn, *,
                 to: str, send: bool, dry_run: bool) -> dict:
    console = Console(highlight=False, record=True, file=open("/dev/null", "w"))
    try:
        fn(console)
    except Exception as exc:
        console.print(f"[red]scenario render error: {exc}[/red]")
    captured = console.export_text(clear=True).strip()
    console.file.close()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = GENERATED / f"piped_{sid}_{ts}.md"
    outfile.write_text(
        f"# {title}\n\n"
        f"**Source:** test scenario `{sid}`  ·  **Captured:** {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
        f"---\n\n"
        f"```\n{captured}\n```\n",
        encoding="utf-8",
    )

    flags = ["--to", to]
    if send and not dry_run:
        flags.append("--send")
    if dry_run:
        flags.append("--dry-run")
    note = f"Test pipe scenario {idx:02d}/25: {title}"
    cmd = f'/email {outfile} {" ".join(flags)} --note "{note}"'

    agent = _get_agent()
    result = run_email_command(cmd, agent)
    return {"id": sid, "title": title, "outfile": str(outfile), "result": result}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default="pgorai@deloitte.com")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=len(SCENARIOS))
    ap.add_argument("--delay", type=float, default=1.5,
                    help="Seconds between emails (avoid overwhelming Outlook).")
    args = ap.parse_args()

    log = Console()
    log.print(f"[bold]Test pipe → /email[/bold] · target: {args.to} · "
              f"mode: {'DRY-RUN' if args.dry_run else 'SEND'} · "
              f"scenarios: {min(args.limit, len(SCENARIOS))}/{len(SCENARIOS)}")

    ok = 0
    failed = 0
    for i, (sid, title, fn) in enumerate(SCENARIOS[:args.limit], start=1):
        log.print(f"\n[cyan]▶ [{i:02d}/{args.limit}] {sid} — {title}[/cyan]")
        try:
            r = run_scenario(i, sid, title, fn, to=args.to,
                             send=not args.dry_run, dry_run=args.dry_run)
        except Exception as exc:
            failed += 1
            log.print(f"[red]  ✗ crashed: {exc}[/red]")
            continue
        res = r["result"]
        if res.get("ok"):
            ok += 1
            subj = res.get("subject", "")
            log.print(f"[green]  ✓ {res.get('message', '')}[/green]")
            log.print(f"[dim]    subject: {subj}[/dim]")
            log.print(f"[dim]    md:      {r['outfile']}[/dim]")
        else:
            failed += 1
            log.print(f"[red]  ✗ {res.get('message', 'unknown')}[/red]")
        if i < args.limit and args.delay > 0:
            time.sleep(args.delay)

    log.print(f"\n[bold]Done.[/bold] OK={ok}  Failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
