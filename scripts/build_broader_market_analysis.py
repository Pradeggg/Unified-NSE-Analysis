#!/usr/bin/env python3
"""Build a comprehensive broader market HTML report.

The report combines:
  - Domestic index performance
  - Sector breadth / rotation
  - Global asset backdrop
  - Institutional flows
  - Latest NSE corporate filings / results / events
  - Short commentary sourced from current market headlines

Output:
  - reports/latest/broader_market_analysis_YYYYMMDD.html
  - reports/market_overview/broader_market_analysis_YYYYMMDD.html
"""
from __future__ import annotations

import html as _h
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.now().strftime("%Y-%m-%d")
STAMP = datetime.now().strftime("%Y%m%d")
IS_WEEKEND = datetime.now().weekday() >= 5

OUT_LATEST = ROOT / "reports" / "latest" / f"broader_market_analysis_{STAMP}.html"
OUT_DATED = ROOT / "reports" / "market_overview" / f"broader_market_analysis_{STAMP}.html"

SOURCE_LINKS = {
    "nse_index_performance": "https://www.nseindia.com/market-data/index-performances",
    "nse_corporate_filings": "https://www.nseindia.com/companies-listing/corporate-filings-application",
    "nse_event_calendar": "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar",
    "nse_sectoral": "https://www.nseindia.com/static/products-services/indices-sectoral",
    "nse_market_snapshot": "https://www.nseindia.com/market-data/analysis-and-tools-capital-market-snapshot",
    "et_market_wrap": "https://economictimes.indiatimes.com/markets/stocks/news/market-wrap-eternal-kotak-bank-hcl-tech-interglobe-top-gainers-and-losers-on-nifty-and-sensex-on-thursday/articleshow/133375367.cms?from=mdr",
    "et_opening": "https://economictimes.indiatimes.com/markets/stocks/news/sensex-and-nifty-off-to-a-choppy-start-amid-middle-east-uncertaint-what-lies-ahead/articleshow/133392272.cms?from=mdr",
    "et_fii_flows": "https://economictimes.indiatimes.com/markets/stocks/news/fiis-pour-rs-6535-crore-into-indian-financial-stocks-what-else-are-they-buying-this-month/articleshow/133392007.cms?from=mdr",
    "ap_us_wrap": "https://apnews.com/article/b595de56eb56950bf87e77e1f812cfba",
    "mint_results_calendar": "https://www.livemint.com/market/quarterly-results-calendar",
}


def pct(v: float, digits: int = 2) -> str:
    return f"{v:+.{digits}f}%"


def money(v: float, digits: int = 1) -> str:
    return f"₹{v:,.{digits}f} cr"


def num(v: float, digits: int = 2) -> str:
    return f"{v:,.{digits}f}"


def color(v: float) -> str:
    return "#16a34a" if v > 0 else "#dc2626" if v < 0 else "#64748b"


def safe_float(v) -> float:
    try:
        if pd.isna(v):
            return float("nan")
        return float(v)
    except Exception:
        return float("nan")


def sparkline(series: list[float], *, stroke: str = "#2563eb", fill: str = "rgba(37,99,235,.12)") -> str:
    values = [safe_float(v) for v in series if pd.notna(v)]
    if len(values) < 2:
        return '<div class="spark spark-empty">n/a</div>'
    w, h, pad = 220, 70, 8
    lo, hi = min(values), max(values)
    spread = hi - lo or 1.0
    pts = []
    for i, val in enumerate(values):
        x = pad + i * (w - 2 * pad) / max(1, len(values) - 1)
        y = pad + (hi - val) * (h - 2 * pad) / spread
        pts.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M {pts[0][0]:.1f},{h-pad:.1f} " + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts) + f" L {pts[-1][0]:.1f},{h-pad:.1f} Z"
    return f"""
    <svg viewBox="0 0 {w} {h}" class="spark" role="img" aria-label="trend chart">
      <defs>
        <linearGradient id="g{abs(hash(tuple(round(v, 2) for v in values))) % 99999}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="{stroke}" stop-opacity=".22"/>
          <stop offset="1" stop-color="{stroke}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path d="{area}" fill="{fill}"></path>
      <polyline points="{line}" fill="none" stroke="{stroke}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
    """


def simple_table(df: pd.DataFrame, columns: list[tuple[str, ...]]) -> str:
    resolved: list[tuple[str, str, str]] = []
    for item in columns:
        if len(item) == 3:
            col, label, kind = item
        elif len(item) == 2:
            col, kind = item
            label = col
        else:
            raise ValueError(f"Unsupported column tuple: {item!r}")
        resolved.append((col, label, kind))
    head = "".join(f'<th data-sort="{"num" if kind == "num" or kind.startswith("pct") else "str"}">{_h.escape(label)}</th>' for col, label, kind in resolved)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col, label, kind in resolved:
            val = row[col]
            if kind == "num":
                sval = num(safe_float(val), 2)
                cls = "num"
            elif kind == "pct":
                sval = pct(safe_float(val), 2)
                cls = f"num {'pos' if safe_float(val) > 0 else 'neg' if safe_float(val) < 0 else 'muted'}"
            elif kind == "pct1":
                sval = pct(safe_float(val), 1)
                cls = f"num {'pos' if safe_float(val) > 0 else 'neg' if safe_float(val) < 0 else 'muted'}"
            else:
                sval = _h.escape("" if pd.isna(val) else str(val))
                cls = ""
            cells.append(f'<td class="{cls}">{sval}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tbl-wrap"><table class="sortable"><thead><tr>{head}</tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"


def bar_list(items: list[dict], *, value_key: str, label_key: str, subtitle_key: str | None = None, kind: str = "pct") -> str:
    vals = [safe_float(item[value_key]) for item in items if pd.notna(item.get(value_key))]
    scale = max([abs(v) for v in vals], default=1.0) or 1.0
    out = []
    for item in items:
        v = safe_float(item[value_key])
        width = max(6.0, abs(v) / scale * 100)
        c = color(v)
        subtitle = f'<div class="bar-sub">{_h.escape(str(item[subtitle_key]))}</div>' if subtitle_key else ""
        value_txt = pct(v, 2) if kind.startswith("pct") else num(v, 2)
        out.append(
            f'<div class="bar-row"><div><div class="bar-label">{_h.escape(str(item[label_key]))}</div>{subtitle}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%;background:{c}"></div></div>'
            f'<div class="bar-value" style="color:{c}">{value_txt}</div></div>'
        )
    return "".join(out)


def build_domestic_indices(indices: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    indices = indices.copy()
    indices["TIMESTAMP"] = pd.to_datetime(indices["TIMESTAMP"])
    indices = indices.sort_values(["SYMBOL", "TIMESTAMP"])
    selected = [
        ("Nifty 50", "Nifty 50"),
        ("Nifty 500", "Nifty 500"),
        ("NIFTY MIDCAP 100", "Midcap 100"),
        ("NIFTY MIDCAP 150", "Midcap 150"),
        ("NIFTY SMLCAP 250", "Smallcap 250"),
        ("Nifty Bank", "Bank"),
        ("Nifty IT", "IT"),
        ("Nifty Auto", "Auto"),
        ("Nifty Metal", "Metal"),
        ("Nifty Realty", "Realty"),
        ("Nifty Pharma", "Pharma"),
        ("Nifty FMCG", "FMCG"),
        ("Nifty Energy", "Energy"),
        ("Nifty PSU Bank", "PSU Bank"),
        ("Nifty Infra", "Infra"),
        ("Nifty PSE", "CPSE"),
    ]
    rows: list[dict] = []
    for symbol, label in selected:
        frame = indices[indices["SYMBOL"].astype(str).str.casefold() == symbol.casefold()].copy()
        if frame.empty:
            continue
        closes = frame["CLOSE"].astype(float).reset_index(drop=True)
        if len(closes) < 21:
            continue
        rows.append({
            "name": label,
            "symbol": symbol,
            "close": closes.iloc[-1],
            "d1": (closes.iloc[-1] / closes.iloc[-2] - 1) * 100,
            "d5": (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) >= 6 else float("nan"),
            "m1": (closes.iloc[-1] / closes.iloc[-22] - 1) * 100 if len(closes) >= 22 else float("nan"),
            "m3": (closes.iloc[-1] / closes.iloc[-64] - 1) * 100 if len(closes) >= 64 else float("nan"),
            "spark_20": closes.tail(20).tolist(),
            "spark_60": closes.tail(60).tolist(),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("m1", ascending=False)
    return df, rows


def load_global_context(global_path: Path) -> pd.DataFrame:
    df = pd.read_csv(global_path)
    df["Date"] = pd.to_datetime(df["Date"])
    cols = [c for c in df.columns if c != "Date"]
    out = []
    for col in cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 2:
            continue
        latest = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        c5 = float(series.iloc[-6]) if len(series) >= 6 else float("nan")
        c20 = float(series.iloc[-21]) if len(series) >= 21 else float("nan")
        out.append({
            "asset": col,
            "latest": latest,
            "d1": (latest / prev - 1) * 100 if prev else float("nan"),
            "d5": (latest / c5 - 1) * 100 if pd.notna(c5) and c5 else float("nan"),
            "d20": (latest / c20 - 1) * 100 if pd.notna(c20) and c20 else float("nan"),
            "spark_20": series.tail(20).tolist(),
        })
    return pd.DataFrame(out)


def build_breadth_chart(history: pd.DataFrame) -> str:
    tail = history.tail(30).copy()
    xs = list(range(len(tail)))
    vals = tail["summation"].astype(float).tolist()
    adv = tail["net_ad"].astype(float).tolist()
    width, height, pad = 860, 280, 28
    lo, hi = min(vals + adv), max(vals + adv)
    spread = hi - lo or 1.0
    def xy(value: float, idx: int) -> tuple[float, float]:
        x = pad + idx * (width - 2 * pad) / max(1, len(xs) - 1)
        y = pad + (hi - value) * (height - 2 * pad) / spread
        return x, y
    poly = " ".join(f"{xy(v, i)[0]:.1f},{xy(v, i)[1]:.1f}" for i, v in enumerate(vals))
    area = "M " + f"{xy(vals[0], 0)[0]:.1f},{height-pad:.1f} " + " ".join(
        f"L {xy(v, i)[0]:.1f},{xy(v, i)[1]:.1f}" for i, v in enumerate(vals)
    ) + f" L {xy(vals[-1], len(vals)-1)[0]:.1f},{height-pad:.1f} Z"
    zero_y = pad + (hi - 0) * (height - 2 * pad) / spread
    bars = []
    for i, v in enumerate(adv):
        x, y = xy(v, i)
        y0 = zero_y
        h = abs(y0 - y)
        top = min(y0, y)
        bars.append(f'<rect x="{x-4:.1f}" y="{top:.1f}" width="8" height="{h:.1f}" fill="{"#16a34a" if v>=0 else "#dc2626"}" opacity=".35"></rect>')
    return f"""
    <section class="panel span-2">
      <h2>Breadth trend</h2>
      <p class="sub">McClellan-style summation proxy and daily net advances. A falling summation with occasional positive breadth spikes is a narrow-rally pattern.</p>
      <svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="breadth trend">
        <defs>
          <linearGradient id="breadthFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#ef4444" stop-opacity=".28"/>
            <stop offset="1" stop-color="#ef4444" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <line x1="{pad}" y1="{zero_y:.1f}" x2="{width-pad}" y2="{zero_y:.1f}" stroke="#94a3b8" stroke-dasharray="5 5"/>
        {''.join(bars)}
        <path d="{area}" fill="url(#breadthFill)"></path>
        <polyline points="{poly}" fill="none" stroke="#dc2626" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"></polyline>
        <text x="{pad}" y="{height-8}" class="svg-label">{tail.iloc[0]['date']}</text>
        <text x="{width-pad}" y="{height-8}" text-anchor="end" class="svg-label">{tail.iloc[-1]['date']}</text>
        <text x="{width-pad}" y="{pad}" text-anchor="end" class="svg-value">Summation {vals[-1]:,.0f}</text>
      </svg>
    </section>
    """


def build_section_title(title: str, subtitle: str) -> str:
    return f'<div class="section-head"><h2>{_h.escape(title)}</h2><p>{_h.escape(subtitle)}</p></div>'


def top_cards(cards: list[tuple[str, str, str, str]]) -> str:
    html_parts = []
    for label, value, sub, cls in cards:
        html_parts.append(
            f'<div class="metric-card {cls}"><div class="metric-label">{_h.escape(label)}</div>'
            f'<div class="metric-value">{_h.escape(value)}</div><div class="metric-sub">{_h.escape(sub)}</div></div>'
        )
    return '<div class="metrics-grid">' + "".join(html_parts) + "</div>"


def read_latest_rows(df: pd.DataFrame, date_col: str, *, days: int | None = None, future: bool = False) -> pd.DataFrame:
    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col])
    ref = pd.to_datetime(TODAY)
    if future:
        data = data[data[date_col] >= ref]
        if days is not None:
            data = data[data[date_col] <= ref + timedelta(days=days)]
        return data.sort_values(date_col)
    data = data[data[date_col] <= ref]
    if days is not None:
        data = data[data[date_col] >= ref - timedelta(days=days)]
    return data.sort_values(date_col, ascending=False)


def build_html() -> str:
    summary = json.loads((ROOT / "data" / "data_summary.json").read_text())
    data_as_of = pd.to_datetime(summary["timestamp"][0]).strftime("%d %b %Y %H:%M")
    stock_start, stock_end = summary["stock_date_range"]
    index_end = summary["index_date_range"][1]

    indices = pd.read_csv(ROOT / "data" / "nse_index_data.csv")
    domestic_df, domestic_rows = build_domestic_indices(indices)

    global_df = load_global_context(ROOT / "data" / "global_indices.csv")
    global_df = global_df.sort_values("d1", ascending=False)

    sector = pd.read_csv(ROOT / "data" / "sector_breadth.csv")
    sector = sector.sort_values(["pct_above_50dma", "change_5d"], ascending=[False, False]).reset_index(drop=True)
    global_corr = pd.read_csv(ROOT / "data" / "global_correlations.csv")
    global_corr = global_corr.sort_values(["alert", "corr_30d"], ascending=[True, False]).reset_index(drop=True)

    breadth = pd.read_csv(ROOT / "data" / "breadth_history.csv")
    flows = pd.read_csv(ROOT / "data" / "fii_dii_flows.csv")
    flow_latest = flows.iloc[-1]

    macro = pd.read_csv(ROOT / "data" / "macro_proxy_signals.csv")
    macro = macro.sort_values("signal_score", ascending=False)

    events = pd.read_csv(ROOT / "data" / "corporate_events.csv")
    events = events.rename(columns=str.upper)
    events["EVENT_DATE"] = pd.to_datetime(events["EVENT_DATE"], errors="coerce")
    recent_events = read_latest_rows(events, "EVENT_DATE", days=21)
    upcoming_events = read_latest_rows(events, "EVENT_DATE", days=30, future=True)
    results_events = recent_events[recent_events["EVENT_TYPE"].astype(str).str.contains("RESULT", case=False, na=False)]
    board_events = upcoming_events[upcoming_events["EVENT_TYPE"].astype(str).str.contains("BOARD", case=False, na=False)]
    action_events = recent_events[recent_events["EVENT_TYPE"].astype(str).str.contains("ACTION", case=False, na=False)]

    vix_row = macro[macro["indicator"].astype(str).str.contains("VIX", case=False, na=False)].head(1)
    nifty_row = macro[macro["indicator"].astype(str).str.contains("Nifty 50", case=False, na=False)].head(1)
    nifty_vix = float(vix_row.iloc[0]["latest_value"]) if not vix_row.empty else float("nan")
    nifty_now = float(nifty_row.iloc[0]["latest_value"]) if not nifty_row.empty else float("nan")

    global_table = global_df[["asset", "latest", "d1", "d5", "d20"]].copy()
    global_table.columns = ["Asset", "Latest", "1D", "5D", "20D"]
    global_table["Latest"] = global_table["Latest"].map(lambda x: f"{x:,.2f}")

    sector_top = sector.head(10).copy()
    sector_bottom = sector.tail(6).copy()

    flow_signal = "DII support offsets FII selling" if safe_float(flow_latest["dii_net_today"]) > 0 and safe_float(flow_latest["fii_net_today"]) < 0 else "Flows mixed"
    if safe_float(flow_latest["dii_net_5d"]) > 0:
        flow_signal = "DII buying remains a stabilizer"

    stance = (
        "Selective risk-on, not broad-based. The tape improved after the Aug 20 rebound, "
        "but breadth remains narrow enough that chasing weak sectors is not justified. "
        "Leadership is still concentrated in IT, banks, auto ancillaries, metal, and real-estate pockets; "
        "energy, infra, CPSE and commodities remain on the weak side."
    )
    weekend_frame = (
        "Weekend review: the market closed the week with a rebound, but not a clean breadth repair. "
        "Treat this as a hold-your-best-ideas environment, not a blanket buy-the-dip setup."
        if IS_WEEKEND
        else ""
    )

    domestic_cards = [
        ("Nifty 50", f"{nifty_now:,.2f}" if pd.notna(nifty_now) else "n/a", "Latest Nifty signal proxy", "green"),
        ("Nifty VIX", f"{nifty_vix:,.2f}" if pd.notna(nifty_vix) else "n/a", "Volatility remains subdued", "blue"),
        ("FII 5D", money(safe_float(flow_latest["fii_net_5d"])), f"Today {money(safe_float(flow_latest['fii_net_today']))}", "amber" if safe_float(flow_latest["fii_net_today"]) < 0 else "green"),
        ("DII 5D", money(safe_float(flow_latest["dii_net_5d"])), f"Today {money(safe_float(flow_latest['dii_net_today']))}", "green"),
        ("Breadth", f"{breadth.iloc[-1]['summation']:,.0f}", f"{int(breadth.iloc[-1]['advances'])} adv / {int(breadth.iloc[-1]['declines'])} dec", "red" if breadth.iloc[-1]["summation"] < 0 else "green"),
        ("Coverage", f"{int(summary['unique_stocks'][0]):,}", f"{summary['stock_records'][0]:,} stock rows across {stock_start} → {stock_end}", "blue"),
    ]

    global_cards = [
        ("S&P 500", f"{global_df.loc[global_df['asset']=='S&P 500','latest'].iloc[0]:,.2f}" if not global_df[global_df["asset"] == "S&P 500"].empty else "n/a", "US growth cue", "amber"),
        ("Nasdaq", f"{global_df.loc[global_df['asset']=='Nasdaq','latest'].iloc[0]:,.2f}" if not global_df[global_df["asset"] == "Nasdaq"].empty else "n/a", "Tech sentiment", "amber"),
        ("Brent", f"{global_df.loc[global_df['asset']=='Crude Oil','latest'].iloc[0]:,.2f}" if not global_df[global_df["asset"] == "Crude Oil"].empty else "n/a", "Crude pressure on risk appetite", "amber"),
        ("Gold", f"{global_df.loc[global_df['asset']=='Gold','latest'].iloc[0]:,.2f}" if not global_df[global_df["asset"] == "Gold"].empty else "n/a", "Defensive bid", "green"),
        ("USDINR", f"{global_df.loc[global_df['asset']=='USDINR','latest'].iloc[0]:,.2f}" if not global_df[global_df["asset"] == "USDINR"].empty else "n/a", "Currency drift remains tight", "amber"),
        ("Copper", f"{global_df.loc[global_df['asset']=='Copper','latest'].iloc[0]:,.2f}" if not global_df[global_df["asset"] == "Copper"].empty else "n/a", "Growth proxy", "green"),
    ]

    top_sector_bars = [
        {"name": r["sector"], "value": r["pct_above_50dma"], "sub": f"{r['index_name']} · 5D {r['change_5d']:+.1f} pts"} for _, r in sector_top.iterrows()
    ]
    bottom_sector_bars = [
        {"name": r["sector"], "value": r["pct_above_50dma"], "sub": f"{r['index_name']} · 5D {r['change_5d']:+.1f} pts"} for _, r in sector_bottom.iterrows()
    ]
    global_bars = [
        {"name": r["asset"], "value": r["d1"], "sub": f"5D {r['d5']:+.2f}% · 20D {r['d20']:+.2f}%"} for _, r in global_df.head(9).iterrows()
    ]

    source_list = [
        ("NSE index performance", SOURCE_LINKS["nse_index_performance"]),
        ("NSE corporate filings", SOURCE_LINKS["nse_corporate_filings"]),
        ("NSE event calendar", SOURCE_LINKS["nse_event_calendar"]),
        ("NSE sectoral indices", SOURCE_LINKS["nse_sectoral"]),
        ("NSE market snapshot", SOURCE_LINKS["nse_market_snapshot"]),
        ("Economic Times market wrap", SOURCE_LINKS["et_market_wrap"]),
        ("Economic Times opening note", SOURCE_LINKS["et_opening"]),
        ("Economic Times FII flows", SOURCE_LINKS["et_fii_flows"]),
        ("AP global market wrap", SOURCE_LINKS["ap_us_wrap"]),
        ("Mint results calendar", SOURCE_LINKS["mint_results_calendar"]),
    ]

    latest_result_rows = []
    for _, r in results_events.head(6).iterrows():
        latest_result_rows.append(
            f"<tr><td>{_h.escape(str(r['SYMBOL']))}</td><td>{_h.escape(str(r['EVENT_DATE'].date()))}</td><td>{_h.escape(str(r.get('PURPOSE_RAW', '')))}</td><td>{_h.escape(str(r.get('DETAIL', '')))}</td></tr>"
        )

    upcoming_result_rows = []
    for _, r in upcoming_events[upcoming_events["EVENT_TYPE"].astype(str).str.contains("RESULT", case=False, na=False)].head(8).iterrows():
        upcoming_result_rows.append(
            f"<tr><td>{_h.escape(str(r['SYMBOL']))}</td><td>{_h.escape(str(r['EVENT_DATE'].date()))}</td><td>{_h.escape(str(r.get('PURPOSE_RAW', '')))}</td><td>{_h.escape(str(r.get('SOURCE', '')))}</td></tr>"
        )

    board_rows = []
    for _, r in board_events.head(6).iterrows():
        board_rows.append(
            f"<tr><td>{_h.escape(str(r['SYMBOL']))}</td><td>{_h.escape(str(r['EVENT_DATE'].date()))}</td><td>{_h.escape(str(r.get('PURPOSE_RAW', '')))}</td><td>{_h.escape(str(r.get('SOURCE', '')))}</td></tr>"
        )

    action_rows = []
    for _, r in action_events.head(6).iterrows():
        action_rows.append(
            f"<tr><td>{_h.escape(str(r['SYMBOL']))}</td><td>{_h.escape(str(r['EVENT_DATE'].date()))}</td><td>{_h.escape(str(r.get('EVENT_TYPE', '')))}</td><td>{_h.escape(str(r.get('SOURCE', '')))}</td></tr>"
        )

    result_count = int(len(results_events))
    upcoming_result_count = int(
        len(upcoming_events[upcoming_events["EVENT_TYPE"].astype(str).str.contains("RESULT", case=False, na=False)])
    )
    board_count = int(len(board_events))
    action_count = int(len(action_events))
    breadth_latest = breadth.iloc[-1]
    breadth_state = "repairing" if safe_float(breadth_latest["summation"]) > -2500 else "fragile"
    if safe_float(breadth_latest["summation"]) < -3500:
        breadth_state = "stressed"
    regime_bits = [
        "Breadth improving" if breadth_state == "repairing" else f"Breadth {breadth_state}",
        "DII support intact" if safe_float(flow_latest["dii_net_5d"]) > 0 else "DII support mixed",
        "VIX low" if pd.notna(nifty_vix) and nifty_vix < 12 else "VIX elevated",
        "Crude firm" if safe_float(global_df.loc[global_df["asset"] == "Crude Oil", "d1"].iloc[0]) > -1 else "Crude cooling",
    ]
    bullish_sectors = ["IT", "Banking", "Auto", "Realty", "Metal"]
    weak_sectors = ["Energy", "CPSE", "Infra", "Commodities", "FMCG"]
    watch_rows = []
    caution_rows = []
    for _, row in sector.head(5)[["sector", "pct_above_50dma"]].iterrows():
        tone = "good" if str(row["sector"]) in bullish_sectors else "watch"
        watch_rows.append(f'<span class="chip {tone}">{_h.escape(str(row["sector"]))} · {row["pct_above_50dma"]:.1f}%</span>')
    for name in weak_sectors:
        match = sector[sector["sector"].astype(str).str.casefold() == name.casefold()]
        if match.empty:
            continue
        row = match.iloc[0]
        caution_rows.append(f'<span class="chip bad">{_h.escape(str(row["sector"]))} · {row["pct_above_50dma"]:.1f}%</span>')
    correlation_rows = []
    for _, r in global_corr.iterrows():
        alert = str(r["alert"]).upper()
        alert_cls = "bad" if alert == "DECOUPLING" else "watch" if alert == "RISK" else "good"
        correlation_rows.append(
            "<tr>"
            f"<td>{_h.escape(str(r['asset']))}</td>"
            f"<td class='num'>{safe_float(r['price']):,.2f}</td>"
            f"<td class='num'>{safe_float(r['corr_30d']):+.3f}</td>"
            f"<td class='num'>{safe_float(r['corr_60d']):+.3f}</td>"
            f"<td class='num'>{safe_float(r['change']):+.3f}</td>"
            f"<td><span class='chip {alert_cls}'>{_h.escape(str(r['alert']))}</span></td>"
            "</tr>"
        )

    latest_news_cards = f"""
      <div class="news-card"><span class="news-pill domestic">Domestic</span><h3>Aug 20 rebound snapped a seven-session losing streak</h3><p>Nifty rose 0.64% and Sensex 0.82%; breadth turned positive, but midcaps and smallcaps were still weaker on the day. Realty led while PSU Bank lagged.</p><a href="{SOURCE_LINKS['et_market_wrap']}" target="_blank" rel="noreferrer">Source</a></div>
      <div class="news-card"><span class="news-pill live">Live</span><h3>Aug 21 open turned choppy as crude and geopolitics stayed in focus</h3><p>Nifty slipped back below 24,250 after a green open; broad markets held up better, and VIX stayed below 11 in the ET morning note.</p><a href="{SOURCE_LINKS['et_opening']}" target="_blank" rel="noreferrer">Source</a></div>
      <div class="news-card"><span class="news-pill global">Global</span><h3>US equities were weak overnight</h3><p>AP reported a down session for the S&amp;P 500 and Nasdaq on Aug 20, with global risk sentiment pressured by yields and oil.</p><a href="{SOURCE_LINKS['ap_us_wrap']}" target="_blank" rel="noreferrer">Source</a></div>
      <div class="news-card"><span class="news-pill flows">Flows</span><h3>FIIs rotated into financials and select cyclicals</h3><p>ET’s August flow note highlighted buying in financials, automobiles, and consumer services, with selling in telecom, capital goods, power, and real estate.</p><a href="{SOURCE_LINKS['et_fii_flows']}" target="_blank" rel="noreferrer">Source</a></div>
    """

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{'Weekend Market Review' if IS_WEEKEND else 'Broader Market Analysis'} — India &amp; Global — {datetime.now().strftime('%d %b %Y')}</title>
<style>
:root {{
  --bg:#eef3f8; --card:#ffffff; --text:#0f172a; --muted:#64748b; --border:#dbe4ee;
  --brand:#123b68; --brand-2:#2563eb; --green:#16a34a; --red:#dc2626; --amber:#d97706; --blue:#2563eb;
  --radius:16px; --shadow:0 10px 30px rgba(16,35,63,.08);
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:linear-gradient(180deg,#eaf1f8 0%,#f6f8fb 40%,#eef3f8 100%); color:var(--text); font:14px/1.5 Inter,Segoe UI,Arial,sans-serif; }}
a {{ color:var(--brand-2); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.hero {{ background:linear-gradient(135deg,#071b35,#113967 55%,#0e7490); color:#fff; padding:34px 28px 42px; }}
.hero-inner {{ max-width:1400px; margin:0 auto; }}
.eyebrow {{ display:inline-flex; gap:8px; align-items:center; padding:5px 10px; border-radius:999px; background:rgba(255,255,255,.12); color:#dbeafe; font-size:11px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }}
.hero h1 {{ margin:12px 0 8px; font-size:38px; line-height:1.05; letter-spacing:-.04em; }}
.hero p {{ margin:0; max-width:1040px; color:#dbeafe; font-size:15px; }}
.subrow {{ margin-top:12px; display:flex; flex-wrap:wrap; gap:10px; }}
.pill {{ padding:6px 10px; border-radius:999px; background:rgba(255,255,255,.12); color:#fff; font-size:12px; font-weight:700; }}
.wrap {{ max-width:1400px; margin:-26px auto 40px; padding:0 18px; }}
.metrics-grid {{ display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:12px; margin-bottom:18px; }}
.metric-card {{ background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; box-shadow:var(--shadow); min-height:108px; }}
.metric-card.green {{ border-top:4px solid var(--green); }} .metric-card.red {{ border-top:4px solid var(--red); }}
.metric-card.amber {{ border-top:4px solid var(--amber); }} .metric-card.blue {{ border-top:4px solid var(--blue); }}
.metric-label {{ font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin-bottom:8px; }}
.metric-value {{ font-size:24px; font-weight:900; letter-spacing:-.03em; }}
.metric-sub {{ font-size:12px; color:var(--muted); margin-top:4px; }}
.layout {{ display:grid; grid-template-columns:2fr 1fr; gap:16px; }}
.panel {{ background:var(--card); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); padding:20px; margin-bottom:16px; }}
.span-2 {{ grid-column:span 2; }}
.section-head h2 {{ margin:0; font-size:20px; letter-spacing:-.02em; }}
.section-head p {{ margin:4px 0 0; color:var(--muted); font-size:12px; }}
.callout {{ background:linear-gradient(135deg,#eff6ff,#f8fafc); border:1px solid #d6e4ff; border-left:6px solid var(--brand-2); border-radius:14px; padding:16px 18px; font-size:15px; line-height:1.6; }}
.grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.grid-3 {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }}
.chart {{ width:100%; height:auto; border-radius:12px; background:#fbfdff; border:1px solid #eef2f7; }}
.svg-label {{ font-size:11px; fill:#64748b; }} .svg-value {{ font-size:14px; fill:#991b1b; font-weight:800; }}
.spark {{ width:100%; height:70px; display:block; border-radius:10px; background:#f8fbff; border:1px solid #edf2f7; }}
.spark-empty {{ display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:12px; }}
.trend-card {{ display:flex; flex-direction:column; gap:8px; }}
.trend-card h3 {{ margin:0; font-size:15px; }}
.trend-card .small {{ color:var(--muted); font-size:12px; }}
.bar-row {{ display:grid; grid-template-columns: 260px 1fr 90px; gap:12px; align-items:center; margin:10px 0; }}
.bar-label {{ font-weight:800; }}
.bar-sub {{ color:var(--muted); font-size:12px; margin-top:2px; }}
.bar-track {{ height:10px; background:#e8eef5; border-radius:999px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:999px; }}
.bar-value {{ text-align:right; font-weight:900; font-variant-numeric:tabular-nums; }}
.tbl-wrap {{ overflow:auto; border:1px solid var(--border); border-radius:14px; box-shadow:var(--shadow); background:#fff; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ position:sticky; top:0; background:#f8fafc; z-index:1; text-align:left; color:#334155; padding:10px 12px; text-transform:uppercase; font-size:11px; letter-spacing:.04em; border-bottom:1px solid var(--border); user-select:none; cursor:pointer; white-space:nowrap; }}
th.sortable::after {{ content:" ↕"; color:#cbd5e1; }}
th.sort-asc::after {{ content:" ▲"; color:var(--brand-2); }}
th.sort-desc::after {{ content:" ▼"; color:var(--brand-2); }}
td {{ padding:10px 12px; border-top:1px solid #eef2f7; white-space:nowrap; }}
tbody tr:hover td {{ background:#fbfdff; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.pos {{ color:var(--green); font-weight:700; }} .neg {{ color:var(--red); font-weight:700; }} .muted {{ color:var(--muted); }}
.tag {{ display:inline-block; padding:4px 8px; border-radius:999px; font-size:10px; font-weight:900; text-transform:uppercase; letter-spacing:.04em; }}
.tag.good {{ background:#dcfce7; color:#166534; }} .tag.watch {{ background:#fef3c7; color:#92400e; }} .tag.bad {{ background:#fee2e2; color:#991b1b; }}
.cards {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
.news-card {{ border:1px solid var(--border); border-radius:14px; padding:16px; background:linear-gradient(180deg,#fff,#fbfdff); box-shadow:var(--shadow); }}
.news-card h3 {{ margin:10px 0 8px; font-size:16px; line-height:1.35; }}
.news-card p {{ margin:0 0 10px; color:#475569; }}
.news-pill {{ display:inline-block; padding:5px 10px; border-radius:999px; color:#fff; font-size:10px; font-weight:900; text-transform:uppercase; letter-spacing:.06em; }}
.news-pill.domestic {{ background:#2563eb; }} .news-pill.live {{ background:#0f766e; }} .news-pill.global {{ background:#8b5cf6; }} .news-pill.flows {{ background:#d97706; }}
.risk-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
.risk-card {{ border-radius:14px; padding:15px 16px; border-left:5px solid; background:#fff; box-shadow:var(--shadow); }}
.risk-card strong {{ display:block; margin-bottom:5px; }} .risk-card span {{ color:#475569; font-size:12px; }}
.risk-green {{ background:#f0fdf4; border-color:#16a34a; }} .risk-amber {{ background:#fffbeb; border-color:#d97706; }} .risk-red {{ background:#fef2f2; border-color:#dc2626; }} .risk-blue {{ background:#eff6ff; border-color:#2563eb; }}
.source-list {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }}
.source-list a {{ display:block; padding:10px 12px; border:1px solid var(--border); border-radius:10px; background:#fff; }}
.chip-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
.chip {{ display:inline-flex; align-items:center; gap:6px; padding:6px 10px; border-radius:999px; font-size:11px; font-weight:800; border:1px solid transparent; }}
.chip.good {{ background:#dcfce7; color:#166534; border-color:#bbf7d0; }}
.chip.watch {{ background:#fef3c7; color:#92400e; border-color:#fde68a; }}
.chip.bad {{ background:#fee2e2; color:#991b1b; border-color:#fecaca; }}
.chip.blue {{ background:#dbeafe; color:#1d4ed8; border-color:#bfdbfe; }}
.summary-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-top:12px; }}
.summary-box {{ border:1px solid var(--border); border-radius:14px; padding:14px 16px; background:#fff; box-shadow:var(--shadow); }}
.summary-box h3 {{ margin:0 0 6px; font-size:15px; }}
.summary-box p {{ margin:0; color:#475569; font-size:12px; line-height:1.6; }}
.kpi-text {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }}
.kpi-text span {{ padding:4px 8px; border-radius:999px; background:#f8fafc; border:1px solid var(--border); font-size:11px; font-weight:700; color:#334155; }}
.footer {{ max-width:1400px; margin:0 auto 30px; padding:0 18px; color:var(--muted); font-size:12px; line-height:1.7; }}
@media (max-width: 1100px) {{ .metrics-grid, .grid-3 {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .layout, .grid-2, .cards, .risk-grid, .source-list {{ grid-template-columns:1fr; }} .span-2 {{ grid-column:span 1; }} .bar-row {{ grid-template-columns:1fr; }} .bar-value {{ text-align:left; }} }}
</style>
</head>
<body>
<header class="hero">
  <div class="hero-inner">
    <div class="eyebrow">Agent Adda · {'Weekend Market Review' if IS_WEEKEND else 'Broader Market Analysis'}</div>
    <h1>{'Weekend Market Review' if IS_WEEKEND else 'India and Global Market Dashboard'}</h1>
    <p>Comprehensive read on domestic breadth, global cues, results season, latest events, and sector leadership. Built from the latest local market snapshot in this workspace plus current NSE / market-news references checked on 22 Aug 2026.</p>
    <div class="subrow">
      <span class="pill">Data snapshot: {data_as_of}</span>
      <span class="pill">Index coverage: through {index_end}</span>
      <span class="pill">Stock coverage: {stock_start} → {stock_end}</span>
      {f'<span class="pill">Weekend format: weekly recap + next-week watchlist</span>' if IS_WEEKEND else ''}
    </div>
  </div>
</header>

<main class="wrap">
  {top_cards(domestic_cards)}
  <div class="panel">
    <div class="callout"><strong>{'Weekend view:' if IS_WEEKEND else 'View:'}</strong> {weekend_frame or stance}</div>
    <div class="summary-grid">
      <div class="summary-box">
        <h3>Regime snapshot</h3>
        <p>The market is improving, but not broad. Leadership exists, yet breadth still needs repair before this becomes a clean risk-on phase.</p>
        <div class="kpi-text">{''.join(f'<span>{_h.escape(bit)}</span>' for bit in regime_bits)}</div>
      </div>
      <div class="summary-box">
        <h3>What to own</h3>
        <p>Stay with areas where participation is still visible and momentum has not broken.</p>
        <div class="chip-row">{''.join(watch_rows)}</div>
      </div>
      <div class="summary-box">
        <h3>What to avoid</h3>
        <p>Weak breadth and poor follow-through are still the main reason to stay selective.</p>
        <div class="chip-row">{''.join(caution_rows)}</div>
      </div>
    </div>
  </div>

  <section class="panel">
    {build_section_title("Week in review", "The few facts that matter most heading into next week")}
    <div class="grid-2">
      <div class="risk-grid">
        <div class="risk-card risk-blue"><strong>What worked</strong><span>IT, banks, auto ancillaries and real-estate pockets remained the best-supported areas by breadth and momentum.</span></div>
        <div class="risk-card risk-amber"><strong>What failed to confirm</strong><span>Energy, infra, CPSE and commodities stayed below the breadth threshold that would justify broader risk-taking.</span></div>
        <div class="risk-card risk-green"><strong>Liquidity</strong><span>DII buying continued to stabilize the tape even as FII flows remained mixed to negative on the latest print.</span></div>
        <div class="risk-card risk-red"><strong>Macro pressure</strong><span>Crude and a firm USDINR remain the most obvious external variables to watch.</span></div>
      </div>
      <div>
        <h3 style="margin:0 0 10px;">Weekly sector rotation</h3>
        {simple_table(sector.head(8)[["sector","index_name","pct_above_50dma","change_5d","breadth_signal"]], [("sector","Sector","str"),("index_name","Index","str"),("pct_above_50dma","% > 50DMA","pct"),("change_5d","5D Δ","pct1"),("breadth_signal","Breadth","str")])}
      </div>
    </div>
  </section>

  <div class="layout">
    <section class="panel">
      {build_section_title("Domestic market", "Broad index leadership, short-term trend, and what the tape is actually doing")}
      {simple_table(domestic_df[["name","close","d1","d5","m1","m3"]].head(10), [("name","Index","str"),("close","Close","num"),("d1","1D","pct"),("d5","5D","pct"),("m1","1M","pct"),("m3","3M","pct")])}
      <div class="grid-3" style="margin-top:14px;">
        <div class="trend-card"><h3>Nifty 50</h3><div class="small">Latest trend over the last 20 sessions</div>{sparkline(domestic_df.loc[domestic_df["name"]=="Nifty 50","spark_20"].iloc[0] if not domestic_df[domestic_df["name"]=="Nifty 50"].empty else [], stroke="#2563eb")}</div>
        <div class="trend-card"><h3>Nifty Bank</h3><div class="small">Financials are still a key stabilizer</div>{sparkline(domestic_df.loc[domestic_df["name"]=="Bank","spark_20"].iloc[0] if not domestic_df[domestic_df["name"]=="Bank"].empty else [], stroke="#0f766e")}</div>
        <div class="trend-card"><h3>Nifty IT</h3><div class="small">The clearest multi-week leadership pocket</div>{sparkline(domestic_df.loc[domestic_df["name"]=="IT","spark_20"].iloc[0] if not domestic_df[domestic_df["name"]=="IT"].empty else [], stroke="#7c3aed")}</div>
      </div>
    </section>

    <aside class="panel">
      {build_section_title("Quick read", "Short bullets that explain the current market regime")}
      <ul style="margin:0; padding-left:18px; color:#334155;">
        <li>Broad market breadth improved on Aug 20, but the summation line is still weak.</li>
        <li>Leadership is concentrated in IT, banks, auto ancillaries, select metals and real estate.</li>
        <li>Energy, CPSE, infra and commodities remain structurally weak on breadth.</li>
        <li>VIX is low, but crude remains the most obvious macro pressure point.</li>
      </ul>
      <div style="margin-top:14px;" class="trend-card">
        <h3>Breadth summation</h3>
        <div class="small">Negative bias remains even after a positive rebound session</div>
      </div>
      {build_breadth_chart(breadth)}
    </aside>
  </div>

  <section class="panel">
    {build_section_title("Sector leadership and breadth", "Where the market has participation, and where it does not")}
    <div class="grid-2">
      <div>
        <h3 style="margin:0 0 10px;">Strongest sectors</h3>
        {bar_list(top_sector_bars, value_key="value", label_key="name", subtitle_key="sub", kind="pct")}
      </div>
      <div>
        <h3 style="margin:0 0 10px;">Weakest sectors</h3>
        {bar_list(bottom_sector_bars, value_key="value", label_key="name", subtitle_key="sub", kind="pct")}
      </div>
    </div>
    <div style="margin-top:16px;">
      {simple_table(sector.head(12)[["sector","index_name","pct_above_50dma","change_5d","breadth_signal","divergence_alert"]], [("sector","Sector","str"),("index_name","Index","str"),("pct_above_50dma","% > 50DMA","pct"),("change_5d","5D Δ","pct1"),("breadth_signal","Breadth","str"),("divergence_alert","Alert","str")])}
    </div>
  </section>

  <section class="panel">
    {build_section_title("Global context", "Global risk, dollar, crude, gold and currencies")}
    <div class="metrics-grid" style="grid-template-columns:repeat(6,minmax(0,1fr));">
      {"".join(f'<div class="metric-card {"green" if safe_float(r["d1"])>0 and r["asset"] in {"Gold","Copper","Hang Seng"} else "red" if safe_float(r["d1"])<0 and r["asset"] in {"S&P 500","Nasdaq","Crude Oil"} else "blue"}"><div class="metric-label">{_h.escape(str(r["asset"]))}</div><div class="metric-value">{r["latest"]:,.2f}</div><div class="metric-sub">1D {pct(safe_float(r["d1"]))} · 5D {pct(safe_float(r["d5"]))} · 20D {pct(safe_float(r["d20"]))}</div></div>' for _, r in global_df.head(6).iterrows())}
    </div>
    <div style="margin-top:14px;">
      {bar_list(global_bars, value_key="value", label_key="name", subtitle_key="sub", kind="pct")}
    </div>
    <div style="margin-top:16px;">
      {simple_table(global_table, [("Asset","Asset","str"),("Latest","Latest","str"),("1D","1D","pct"),("5D","5D","pct"),("20D","20D","pct")])}
    </div>
    <div style="margin-top:14px;" class="cards">
      <div class="news-card">
        <span class="news-pill global">Global read-through</span>
        <h3>US tech and risk assets are softer; oil remains the main variable</h3>
        <p>AP’s latest market wrap showed the S&amp;P 500 and Nasdaq losing ground on Aug 20. That matters for India because it keeps pressure on high-multiple cyclicals and supports a selective rather than indiscriminate risk-on stance.</p>
        <a href="{SOURCE_LINKS['ap_us_wrap']}" target="_blank" rel="noreferrer">AP market wrap</a>
      </div>
      <div class="news-card">
        <span class="news-pill global">FX / commodities</span>
        <h3>USDINR is firm and Brent is elevated</h3>
        <p>That combination is usually uncomfortable for import-heavy sectors and rate-sensitive names, while it can support selected exporters and commodity-linked trades only if price action confirms.</p>
        <a href="{SOURCE_LINKS['nse_market_snapshot']}" target="_blank" rel="noreferrer">NSE market snapshot</a>
      </div>
    </div>
  </section>

  <section class="panel">
    {build_section_title("Flows, liquidity and market regime", "Who is buying, who is selling, and what that means for the next few sessions")}
    <div class="grid-2">
      <div>
        <div class="metric-card green" style="margin-bottom:12px;">
          <div class="metric-label">FII / DII flow</div>
          <div class="metric-value">{money(safe_float(flow_latest['fii_net_today']))} / {money(safe_float(flow_latest['dii_net_today']))}</div>
          <div class="metric-sub">5D: {money(safe_float(flow_latest['fii_net_5d']))} / {money(safe_float(flow_latest['dii_net_5d']))}</div>
        </div>
        <div class="risk-grid">
          <div class="risk-card risk-blue"><strong>Interpretation</strong><span>{flow_signal}</span></div>
          <div class="risk-card risk-amber"><strong>Macro watch</strong><span>High crude plus fragile global tech can cap a broad market melt-up even if DIIs continue to absorb supply.</span></div>
        </div>
      </div>
      <div>
        <div class="bar-row" style="grid-template-columns: 180px 1fr 110px;"><div><div class="bar-label">FII today</div><div class="bar-sub">Cash market</div></div><div class="bar-track"><div class="bar-fill" style="width:38%;background:{color(safe_float(flow_latest['fii_net_today']))}"></div></div><div class="bar-value" style="color:{color(safe_float(flow_latest['fii_net_today']))}">{money(safe_float(flow_latest['fii_net_today']))}</div></div>
        <div class="bar-row" style="grid-template-columns: 180px 1fr 110px;"><div><div class="bar-label">DII today</div><div class="bar-sub">Cash market</div></div><div class="bar-track"><div class="bar-fill" style="width:78%;background:{color(safe_float(flow_latest['dii_net_today']))}"></div></div><div class="bar-value" style="color:{color(safe_float(flow_latest['dii_net_today']))}">{money(safe_float(flow_latest['dii_net_today']))}</div></div>
        <div class="bar-row" style="grid-template-columns: 180px 1fr 110px;"><div><div class="bar-label">FII 5D</div><div class="bar-sub">Window</div></div><div class="bar-track"><div class="bar-fill" style="width:32%;background:{color(safe_float(flow_latest['fii_net_5d']))}"></div></div><div class="bar-value" style="color:{color(safe_float(flow_latest['fii_net_5d']))}">{money(safe_float(flow_latest['fii_net_5d']))}</div></div>
        <div class="bar-row" style="grid-template-columns: 180px 1fr 110px;"><div><div class="bar-label">DII 5D</div><div class="bar-sub">Window</div></div><div class="bar-track"><div class="bar-fill" style="width:82%;background:{color(safe_float(flow_latest['dii_net_5d']))}"></div></div><div class="bar-value" style="color:{color(safe_float(flow_latest['dii_net_5d']))}">{money(safe_float(flow_latest['dii_net_5d']))}</div></div>
      </div>
    </div>
  </section>

  <section class="panel">
    {build_section_title("Event radar", "How much fresh event risk is in the system")}
    <div class="metrics-grid" style="grid-template-columns:repeat(4,minmax(0,1fr));">
      <div class="metric-card blue"><div class="metric-label">Recent results</div><div class="metric-value">{result_count}</div><div class="metric-sub">in the last 21 days</div></div>
      <div class="metric-card green"><div class="metric-label">Upcoming results</div><div class="metric-value">{upcoming_result_count}</div><div class="metric-sub">next 30 days in event cache</div></div>
      <div class="metric-card amber"><div class="metric-label">Board meetings</div><div class="metric-value">{board_count}</div><div class="metric-sub">scheduled in next 30 days</div></div>
      <div class="metric-card red"><div class="metric-label">Corporate actions</div><div class="metric-value">{action_count}</div><div class="metric-sub">recent event activity</div></div>
    </div>
  </section>

  <section class="panel">
    {build_section_title("Latest results and event calendar", "What has just hit the tape, what is upcoming, and what should be watched")}
    <div class="grid-2">
      <div>
        <h3 style="margin:0 0 10px;">Latest financial results on NSE</h3>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Symbol</th><th>Period / Date</th><th>Purpose</th><th>Detail</th></tr></thead>
            <tbody>{''.join(latest_result_rows) if latest_result_rows else '<tr><td colspan="4">No recent result rows in local event cache.</td></tr>'}</tbody>
          </table>
        </div>
        <p style="color:var(--muted);font-size:12px;margin-top:8px;">Source cross-check: NSE corporate filings page currently lists KANANIIND, VSTTILLERS, IL&amp;FSTRANS and VIDEOIND among the latest financial results.</p>
      </div>
      <div>
        <h3 style="margin:0 0 10px;">Upcoming results / board events</h3>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Symbol</th><th>Date</th><th>Purpose</th><th>Source</th></tr></thead>
            <tbody>{''.join(upcoming_result_rows) if upcoming_result_rows else '<tr><td colspan="4">No upcoming result rows in local event cache.</td></tr>'}</tbody>
          </table>
        </div>
        <div style="margin-top:12px;" class="tbl-wrap">
          <table>
            <thead><tr><th>Symbol</th><th>Date</th><th>Purpose</th><th>Source</th></tr></thead>
            <tbody>{''.join(board_rows) if board_rows else '<tr><td colspan="4">No upcoming board meetings in local event cache.</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    </div>
    <div style="margin-top:16px;">
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Symbol</th><th>Date</th><th>Event type</th><th>Source</th></tr></thead>
          <tbody>{''.join(action_rows) if action_rows else '<tr><td colspan="4">No recent corporate actions in local event cache.</td></tr>'}</tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="panel">
    {build_section_title("Latest headlines that explain the tape", "Short, current market notes that connect the data to the price action")}
    <div class="cards">{latest_news_cards}</div>
  </section>

  <section class="panel">
    {build_section_title("Global correlation watch", "Which outside moves currently matter most for Indian risk appetite")}
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Asset</th><th>Price</th><th>30D Corr</th><th>60D Corr</th><th>Change</th><th>Signal</th></tr></thead>
        <tbody>{''.join(correlation_rows)}</tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    {build_section_title("Current signals to watch", "What would change the base case next week")}
    <div class="risk-grid">
      <div class="risk-card risk-green"><strong>Breadth repair</strong><span>Need multiple sessions of improving advance/decline and a rising summation line to call this a broader risk-on phase.</span></div>
      <div class="risk-card risk-amber"><strong>Crude shock</strong><span>Brent staying elevated or moving higher would keep pressure on cyclicals, rates and the currency.</span></div>
      <div class="risk-card risk-red"><strong>Leadership failure</strong><span>If IT, banks and auto ancillaries roll over together, the market likely loses its current support pillars.</span></div>
      <div class="risk-card risk-blue"><strong>DII absorption</strong><span>Persistent domestic buying can keep the market constructive even if FIIs remain mixed or sellers on a day-to-day basis.</span></div>
    </div>
  </section>

  <section class="panel">
    {build_section_title("Source trail", "Direct links used to anchor the report")}
    <div class="source-list">
      {"".join(f'<a href="{url}" target="_blank" rel="noreferrer">{_h.escape(label)}</a>' for label, url in source_list)}
    </div>
  </section>
</main>

<footer class="footer">
  Generated on {datetime.now().strftime("%d %b %Y %H:%M %Z")} from Agent Adda market datasets and current public market sources. Coverage: local data snapshot through {index_end}, plus current market-news references reviewed on 22 Aug 2026. Educational use only. Not investment advice.
</footer>

<script>
(function() {{
  document.querySelectorAll('table.sortable').forEach(function(tbl) {{
    var ths = tbl.querySelectorAll('thead th');
    ths.forEach(function(th, idx) {{
      th.classList.add('sortable');
      th.addEventListener('click', function() {{
        var asc = !th.classList.contains('sort-asc');
        ths.forEach(function(t) {{ t.classList.remove('sort-asc', 'sort-desc'); }});
        th.classList.add(asc ? 'sort-asc' : 'sort-desc');
        var rows = Array.from(tbl.tBodies[0].rows);
        var kind = th.dataset.sort || 'str';
        rows.sort(function(a, b) {{
          var av = a.cells[idx].innerText.trim();
          var bv = b.cells[idx].innerText.trim();
          if (kind.indexOf('num') === 0) {{
            av = parseFloat(av.replace(/[^0-9.-]/g, '')) || 0;
            bv = parseFloat(bv.replace(/[^0-9.-]/g, '')) || 0;
          }} else {{
            av = av.toLowerCase(); bv = bv.toLowerCase();
          }}
          return asc ? (av > bv ? 1 : av < bv ? -1 : 0) : (av < bv ? 1 : av > bv ? -1 : 0);
        }});
        rows.forEach(function(r) {{ tbl.tBodies[0].appendChild(r); }});
      }});
    }});
  }});
}})();
</script>
</body>
</html>
"""
    return html_doc


def main() -> None:
    html_doc = build_html()
    OUT_LATEST.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATED.parent.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(html_doc, encoding="utf-8")
    OUT_DATED.write_text(html_doc, encoding="utf-8")
    print(OUT_LATEST)
    print(OUT_DATED)


if __name__ == "__main__":
    main()
