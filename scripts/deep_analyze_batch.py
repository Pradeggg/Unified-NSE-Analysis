"""One-off batch deep-analysis driver.

Calls the underlying tool functions directly (bypassing the agent renderer that
currently collapses /analyze output into a meta block) and emits a Markdown
report per symbol under reports/analysis_runs/<date>/<SYMBOL>.md.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terminal.tools import (  # noqa: E402
    resolve_symbol,
    get_symbol_snapshot,
    get_technical_setup,
    get_sector_context,
    search_latest_catalysts,
)
from terminal.forensics import run_forensic_analysis  # noqa: E402
from terminal.web_research import comprehensive_stock_research  # noqa: E402


def _fmt(v, prec=2):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.{prec}f}"
    return str(v)


def analyze(symbol: str) -> str:
    out = [f"# {symbol} — Deep Analysis", ""]
    try:
        rs = resolve_symbol(symbol)
        canon = rs.get("symbol") or symbol
        out.append(f"_Resolved symbol_: **{canon}** — {rs.get('company_name') or rs.get('name') or ''}")
    except Exception as e:
        out.append(f"resolve_symbol error: {e}")
        canon = symbol

    # Snapshot
    out += ["", "## Snapshot"]
    try:
        snap = get_symbol_snapshot(canon)
        for k in (
            "price", "change_1d", "change_1w", "change_1m", "change_3m",
            "change_6m", "change_1y", "stage", "trading_signal",
            "market_cap_category", "sector", "rsi", "technical_score",
            "relative_strength", "minervini_score", "can_slim_score",
            "fundamental_score", "trading_value",
        ):
            if k in snap:
                out.append(f"- {k}: {_fmt(snap.get(k))}")
        if snap.get("error"):
            out.append(f"- error: {snap['error']}")
    except Exception as e:
        out.append(f"snapshot error: {e}\n```\n{traceback.format_exc()}\n```")

    # Technical
    out += ["", "## Technical setup"]
    try:
        tech = get_technical_setup(canon)
        keys = [
            "stage", "trend_signal", "ema20", "ema50", "ema200",
            "sma50", "sma200", "rsi", "adx", "macd_signal", "supertrend",
            "atr", "atr_pct", "volume_zscore", "high_52w", "low_52w",
            "pct_from_52w_high", "pct_from_52w_low", "relative_strength",
            "minervini_score", "can_slim_score", "technical_score",
            "breakout_state", "vol_state", "support", "resistance",
        ]
        for k in keys:
            if k in tech:
                out.append(f"- {k}: {_fmt(tech[k])}")
        if tech.get("error"):
            out.append(f"- error: {tech['error']}")
    except Exception as e:
        out.append(f"technical error: {e}")

    # Sector
    out += ["", "## Sector context"]
    try:
        sec = get_sector_context(canon)
        for k in (
            "sector", "index", "sector_change_1d", "sector_change_1w",
            "sector_change_1m", "rank_in_sector", "breadth", "leaders",
            "laggards", "rotation_signal",
        ):
            if k in sec:
                val = sec[k]
                if isinstance(val, (list, dict)):
                    val = json.dumps(val, default=str)[:400]
                out.append(f"- {k}: {val}")
        if sec.get("error"):
            out.append(f"- error: {sec['error']}")
    except Exception as e:
        out.append(f"sector error: {e}")

    # Fundamentals (forensic engine scrapes screener)
    out += ["", "## Forensic / fundamental ratios"]
    try:
        fo = run_forensic_analysis(canon)
        if fo.get("error"):
            out.append(f"- error: {fo['error']}")
        else:
            out.append(f"- Overall forensic risk: **{fo.get('overall_risk', 'unknown')}**")
            out.append(f"- Source: {fo.get('source_url', '')}")
            for engine in ("beneish", "piotroski", "altman"):
                blk = fo.get(engine) or {}
                if blk:
                    score = blk.get("score") or blk.get("m_score") or blk.get("z_score")
                    out.append(f"- {engine}: score={_fmt(score)} verdict={blk.get('verdict') or blk.get('classification')}")
            # Pull the raw screener numbers if available
            pl = fo.get("pl") or {}
            bs = fo.get("bs") or {}
            if pl or bs:
                out.append("")
                out.append("### Screener pulls (key rows)")
                for label, src in (("P&L", pl), ("Balance sheet", bs)):
                    if src:
                        out.append(f"**{label}**")
                        for k, v in list(src.items())[:14]:
                            if isinstance(v, list):
                                v = v[-5:]
                            out.append(f"  - {k}: {v}")
    except Exception as e:
        out.append(f"forensic error: {e}")

    # Comprehensive research (LLM-assisted multi-vertical research)
    out += ["", "## Comprehensive research"]
    try:
        cr = comprehensive_stock_research(canon, aspects=["business", "growth", "risks", "catalysts", "valuation"])
        if cr.get("error"):
            out.append(f"- error: {cr['error']}")
        else:
            for aspect in ("business", "growth", "risks", "catalysts", "valuation",
                            "summary", "narrative", "thesis"):
                txt = cr.get(aspect)
                if txt:
                    if isinstance(txt, (list, dict)):
                        txt = json.dumps(txt, default=str, indent=2)[:1500]
                    out.append(f"### {aspect}")
                    out.append(str(txt)[:1500])
    except Exception as e:
        out.append(f"comprehensive_research error: {e}")

    # Catalysts
    out += ["", "## Latest catalysts"]
    try:
        cat = search_latest_catalysts(canon, max_results=8)
        if cat.get("error"):
            out.append(f"- error: {cat['error']}")
        else:
            items = cat.get("items") or cat.get("results") or []
            for it in items[:8]:
                if isinstance(it, dict):
                    title = it.get("title") or it.get("headline") or ""
                    date_ = it.get("date") or it.get("published") or ""
                    url = it.get("url") or it.get("link") or ""
                    out.append(f"- [{date_}] {title} — {url}")
                else:
                    out.append(f"- {it}")
    except Exception as e:
        out.append(f"catalysts error: {e}")

    out.append("")
    out.append("---")
    out.append("_Not investment advice. Research and learning only._")
    return "\n".join(str(x) for x in out)


def main():
    syms = [
        "INSPIRISYS", "SCHNEIDER", "GVPIL", "DREDGECORP",
        "STALLION", "RISHABH", "KIRLOSIND", "SOMANYCERA",
    ]
    out_dir = ROOT / "reports" / "analysis_runs" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in syms:
        print(f"=== {s} ===", flush=True)
        try:
            md = analyze(s)
        except Exception as e:
            md = f"# {s}\n\nFatal error: {e}\n```\n{traceback.format_exc()}\n```"
        (out_dir / f"{s}.md").write_text(md)
        print(f"  wrote {out_dir / (s + '.md')} ({len(md)} bytes)")


if __name__ == "__main__":
    main()
