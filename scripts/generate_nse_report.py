"""
Generate reports/NSE_Market_Report_YYYYMMDD.html from pipeline CSV outputs.
Reads working-sector/output/ CSVs and produces a self-contained shareable HTML.
"""
import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "working-sector" / "output"
REPORTS_DIR = ROOT / "reports"


def load_data():
    metrics = pd.read_csv(OUTPUT_DIR / "phase2_universe_metrics.csv")
    shortlist = pd.read_csv(OUTPUT_DIR / "phase3_shortlist.csv")
    backtest = pd.read_csv(OUTPUT_DIR / "phase4_backtest_results.csv")
    return metrics, shortlist, backtest


def pct(val, decimals=1):
    try:
        v = float(val)
        sign = "+" if v >= 0 else ""
        color = "#16a34a" if v >= 0 else "#dc2626"
        return f'<span style="color:{color};font-weight:600">{sign}{v*100:.{decimals}f}%</span>'
    except Exception:
        return "—"


def score_bar(val, max_val=100):
    try:
        v = float(val)
        pct_w = min(v / max_val * 100, 100)
        color = "#16a34a" if v >= 60 else "#ca8a04" if v >= 45 else "#dc2626"
        return (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="background:#e2e8f0;border-radius:4px;width:80px;height:8px">'
            f'<div style="background:{color};width:{pct_w:.0f}%;height:8px;border-radius:4px"></div></div>'
            f'<span style="font-weight:600">{v:.1f}</span></div>'
        )
    except Exception:
        return "—"


def backtest_summary(backtest: pd.DataFrame):
    valid = backtest.dropna(subset=["EXCESS_RET"])
    if valid.empty:
        return 0, "—", "—", "—"
    n = len(valid)
    mean_excess = valid["EXCESS_RET"].mean()
    hit_rate = (valid["EXCESS_RET"] > 0).mean()
    best = valid["EXCESS_RET"].max()
    return n, mean_excess, hit_rate, best


def render_shortlist_rows(shortlist: pd.DataFrame) -> str:
    rows = []
    for i, r in shortlist.iterrows():
        sym = r.get("SYMBOL", "")
        subsector = r.get("SUBSECTOR", "")
        price = r.get("CURRENT_PRICE", "")
        ret1m = pct(r.get("RET_1M"))
        ret6m = pct(r.get("RET_6M"))
        rs = pct(r.get("RS_VS_NIFTY_500_6M"))
        composite = r.get("COMPOSITE_SCORE", "")
        fund = score_bar(r.get("FUND_SCORE"))
        tech = score_bar(r.get("TECHNICAL_SCORE"))
        rsi = r.get("RSI", "")
        try:
            rsi_str = f"{float(rsi):.1f}"
        except Exception:
            rsi_str = "—"
        try:
            price_str = f"₹{float(price):,.1f}"
        except Exception:
            price_str = "—"
        try:
            comp_str = f"<strong>{float(composite):.1f}</strong>"
        except Exception:
            comp_str = "—"

        rows.append(f"""<tr>
      <td class="rank">{len(rows)+1}</td>
      <td class="symbol">{sym}</td>
      <td>{subsector}</td>
      <td>{price_str}</td>
      <td>{ret1m}</td>
      <td>{ret6m}</td>
      <td>{rs}</td>
      <td>{fund}</td>
      <td>{tech}</td>
      <td>{rsi_str}</td>
      <td>{comp_str}</td>
    </tr>""")
    return "\n".join(rows)


def render_metrics_rows(metrics: pd.DataFrame, top_n=20) -> str:
    sort_col = "COMPOSITE_SCORE" if "COMPOSITE_SCORE" in metrics.columns else "TECHNICAL_SCORE"
    df = metrics.sort_values(sort_col, ascending=False).head(top_n)
    rows = []
    for i, r in df.iterrows():
        sym = r.get("SYMBOL", "")
        subsector = r.get("SUBSECTOR", "")
        price = r.get("CURRENT_PRICE", "")
        ret1m = pct(r.get("RET_1M"))
        ret6m = pct(r.get("RET_6M"))
        rs = pct(r.get("RS_VS_NIFTY_500_6M"))
        fund = score_bar(r.get("FUND_SCORE"))
        tech = score_bar(r.get("TECHNICAL_SCORE"))
        try:
            price_str = f"₹{float(price):,.1f}"
        except Exception:
            price_str = "—"
        rows.append(f"""<tr>
      <td class="rank">{len(rows)+1}</td>
      <td class="symbol">{sym}</td>
      <td>{subsector}</td>
      <td>{price_str}</td>
      <td>{ret1m}</td>
      <td>{ret6m}</td>
      <td>{rs}</td>
      <td>{fund}</td>
      <td>{tech}</td>
    </tr>""")
    return "\n".join(rows)


def generate_html(metrics: pd.DataFrame, shortlist: pd.DataFrame, backtest: pd.DataFrame) -> str:
    as_of = metrics["AS_OF_DATE"].iloc[0] if "AS_OF_DATE" in metrics.columns else str(date.today())
    try:
        as_of_fmt = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        as_of_fmt = str(as_of)

    n_stocks = len(metrics)
    rs_positive = int((metrics["RS_VS_NIFTY_500_6M"] > 0).sum())
    pass_screen = int((shortlist.get("PASS_SCREEN", pd.Series([False]*len(shortlist)))).sum()) if "PASS_SCREEN" in shortlist.columns else 0

    n_bt, mean_excess, hit_rate, best_excess = backtest_summary(backtest)
    try:
        mean_excess_str = f"{mean_excess*100:+.1f}%"
        hit_rate_str = f"{hit_rate*100:.0f}%"
        best_str = f"{best_excess*100:+.1f}%"
    except Exception:
        mean_excess_str = hit_rate_str = best_str = "—"

    shortlist_rows = render_shortlist_rows(shortlist.head(15))
    metrics_rows = render_metrics_rows(metrics)

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NSE Auto Components Report — {as_of_fmt}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #1e293b; }}
  .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%); color: white; padding: 32px 40px; }}
  .header h1 {{ font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }}
  .header .sub {{ font-size: 14px; opacity: 0.85; margin-top: 6px; }}
  .header .meta {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; font-size: 13px; opacity: 0.9; }}
  .header .meta span {{ background: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 20px; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 20px; }}
  .section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .section-title {{ font-size: 18px; font-weight: 700; color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 18px; display: flex; align-items: center; gap: 8px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
  .kpi {{ background: #f1f5f9; border-radius: 8px; padding: 14px 16px; }}
  .kpi .label {{ font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
  .kpi .value {{ font-size: 26px; font-weight: 700; color: #1e293b; margin-top: 2px; }}
  .kpi .value.green {{ color: #16a34a; }}
  .kpi .value.red {{ color: #dc2626; }}
  .kpi .value.amber {{ color: #ca8a04; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f1f5f9; color: #475569; font-weight: 600; text-align: left; padding: 10px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.3px; border-bottom: 1px solid #e2e8f0; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f8fafc; }}
  .rank {{ font-weight: 700; color: #64748b; width: 32px; }}
  .symbol {{ font-weight: 700; color: #1e3a5f; }}
  .note {{ font-size: 12px; color: #64748b; margin-top: 12px; font-style: italic; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .disclaimer {{ background: #fef3c7; border: 1px solid #fde68a; border-radius: 8px; padding: 12px 16px; font-size: 12px; color: #92400e; margin-bottom: 20px; }}
  .footer {{ text-align: center; color: #94a3b8; font-size: 12px; padding: 20px; }}
  @media(max-width:700px){{ .two-col{{ grid-template-columns:1fr; }} .kpi .value{{ font-size:20px; }} }}
</style>
</head>
<body>

<div class="header">
  <h1>🇮🇳 NSE Auto Components Intelligence Report</h1>
  <div class="sub">Quantitative sector analysis — Auto Components universe with composite scoring</div>
  <div class="meta">
    <span>📅 Data as of: {as_of_fmt}</span>
    <span>🔩 Sector: Auto Components</span>
    <span>📊 Universe: {n_stocks} stocks</span>
    <span>⏱ Generated: {generated_at}</span>
  </div>
</div>

<div class="container">

<div class="disclaimer">
  ⚠️ <strong>For informational purposes only.</strong> Generated from quantitative models. Not investment advice. Past performance does not guarantee future results. All data sourced from NSE public feeds.
</div>

<!-- SECTOR KPIs -->
<div class="section">
  <div class="section-title"><span>📈</span> Sector Overview — Auto Components ({as_of_fmt})</div>
  <div class="kpi-grid">
    <div class="kpi"><div class="label">Universe</div><div class="value">{n_stocks}</div></div>
    <div class="kpi"><div class="label">RS &gt; 0 vs N500</div><div class="value green">{rs_positive}</div></div>
    <div class="kpi"><div class="label">Pass Screen</div><div class="value {'green' if pass_screen > 0 else 'red'}">{pass_screen}</div></div>
    <div class="kpi"><div class="label">Backtest Periods</div><div class="value">{n_bt}</div></div>
    <div class="kpi"><div class="label">Mean Excess Ret</div><div class="value {'green' if mean_excess > 0 else 'red'}">{mean_excess_str}</div></div>
    <div class="kpi"><div class="label">Hit Rate</div><div class="value amber">{hit_rate_str}</div></div>
    <div class="kpi"><div class="label">Best Period</div><div class="value green">{best_str}</div></div>
  </div>
</div>

<!-- TOP 15 SHORTLIST -->
<div class="section">
  <div class="section-title"><span>🏆</span> Top 15 — Composite Ranked Shortlist</div>
  <table>
    <thead><tr>
      <th>#</th><th>Symbol</th><th>Subsector</th><th>Price</th>
      <th>1M</th><th>6M</th><th>RS vs N500</th>
      <th>Fundamental</th><th>Technical</th><th>RSI</th><th>Composite</th>
    </tr></thead>
    <tbody>
{shortlist_rows}
    </tbody>
  </table>
  <p class="note">Composite = 40% Fundamental + 40% Technical + 20% RS Rank. Screens: FUND ≥ 70 AND RS_6M &gt; 0.</p>
</div>

<!-- FULL UNIVERSE TOP 20 -->
<div class="section">
  <div class="section-title"><span>📋</span> Full Universe — Top 20 by Composite Score</div>
  <table>
    <thead><tr>
      <th>#</th><th>Symbol</th><th>Subsector</th><th>Price</th>
      <th>1M</th><th>6M</th><th>RS vs N500</th>
      <th>Fundamental</th><th>Technical</th>
    </tr></thead>
    <tbody>
{metrics_rows}
    </tbody>
  </table>
</div>

<!-- SECTOR CONTEXT -->
<div class="section">
  <div class="section-title"><span>🏭</span> Sector Context — Auto Components India</div>
  <div class="two-col">
    <div>
      <p style="font-size:13px;line-height:1.8;color:#374151">
        <strong>Industry size:</strong> ₹6.73 lakh crore (USD 80.2B) FY2024–25, +9.6% YoY, ~14% CAGR over 5 years.<br><br>
        <strong>Policy:</strong> Auto PLI ₹5,939 Cr; PM E-Drive ₹1,500 Cr for EV trucks/charging; ADAS mandatory for CVs from Apr 2026.<br><br>
        <strong>EV transition:</strong> Battery/semiconductor content 40–50% of EV value. EV component share ~4.6% of OEM shipments (early 2026).
      </p>
    </div>
    <div>
      <p style="font-size:13px;line-height:1.8;color:#374151">
        <strong>Revenue outlook:</strong> CRISIL projects 7–9% growth FY26 on 2W and PV demand strength.<br><br>
        <strong>Key themes:</strong> ADAS penetration (8.4% → 62% by 2035), thermal management, sunroof/glazing, localisation of EV supply chain.<br><br>
        <strong>Risks:</strong> ~10% cost disability vs China, electronics import surge, shift to pull-supply chains.
      </p>
    </div>
  </div>
</div>

<div class="footer">
  Generated {generated_at} by Unified NSE Analysis Pipeline &nbsp;|&nbsp; Data as of {as_of_fmt}<br>
  For internal research use only. Not for distribution to retail investors.
</div>

</div>
</body>
</html>"""


def main():
    REPORTS_DIR.mkdir(exist_ok=True)
    metrics, shortlist, backtest = load_data()

    as_of = str(metrics["AS_OF_DATE"].iloc[0])[:10].replace("-", "") if "AS_OF_DATE" in metrics.columns else datetime.utcnow().strftime("%Y%m%d")
    out_path = REPORTS_DIR / f"NSE_Market_Report_{as_of}.html"

    html = generate_html(metrics, shortlist, backtest)
    out_path.write_text(html, encoding="utf-8")
    print(f"Report generated: {out_path}")


if __name__ == "__main__":
    main()
