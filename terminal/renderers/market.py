"""Renderers for market_dashboard, market_situation_assessment, and startup_morning_briefing intents."""

from terminal.renderers._base import _get, _source_trail_lines, FOOTER


def _fmt_pct(value) -> str:
    return f"{value:+.2f}%" if isinstance(value, (int, float)) else "n/a"


def _fmt_num(value) -> str:
    return f"{value:,.2f}" if isinstance(value, (int, float)) else "n/a"


def render_dashboard(tool_results: list[dict]) -> str:
    """Render the market_dashboard intent."""
    live = _get(tool_results, "get_live_market_overview")
    brd = _get(tool_results, "get_market_breadth")
    glob = _get(tool_results, "get_global_market_assessment")
    movers = _get(tool_results, "get_top_gainers_losers")
    cat = _get(tool_results, "search_latest_catalysts")

    lines: list[str] = []

    indices = (live or {}).get("indices") or {}
    n50 = indices.get("NIFTY 50") or {}
    bank = indices.get("NIFTY BANK") or {}
    vix = indices.get("INDIA VIX") or {}
    mid = (
        indices.get("NIFTY MIDCAP SELECT")
        or indices.get("NIFTY MIDCAP 50")
        or indices.get("NIFTY MIDCAP 100")
        or {}
    )
    small = indices.get("NIFTY SMALLCAP 100") or indices.get("NIFTY SMALLCAP 250") or {}
    live_adv_dec = (live or {}).get("adv_dec") or {}

    index_rows = []
    for name, row in indices.items():
        if name.upper() == "INDIA VIX":
            continue
        pct = row.get("pct_change", row.get("chg_pct"))
        last = row.get("last", row.get("close"))
        if isinstance(pct, (int, float)):
            index_rows.append((name, pct, last))
    leaders = sorted(index_rows, key=lambda x: x[1], reverse=True)[:5]
    laggards = sorted(index_rows, key=lambda x: x[1])[:5]

    n50_pct = n50.get("pct_change", n50.get("chg_pct"))
    adv = live_adv_dec.get("advances")
    dec = live_adv_dec.get("declines")
    breadth_bias = "mixed"
    if isinstance(adv, (int, float)) and isinstance(dec, (int, float)):
        breadth_bias = "positive" if adv > dec else ("negative" if dec > adv else "flat")
    price_bias = "bullish" if isinstance(n50_pct, (int, float)) and n50_pct > 0.25 else (
        "bearish" if isinstance(n50_pct, (int, float)) and n50_pct < -0.25 else "range-bound"
    )
    global_regime = (glob or {}).get("risk_regime", "mixed")
    narrative_bias = (
        "constructive but selective"
        if price_bias == "bullish" and breadth_bias != "negative"
        else "defensive / risk-off"
        if price_bias == "bearish" and breadth_bias == "negative"
        else "mixed and breadth-sensitive"
    )

    lines.append("## Current Market Dashboard")
    if live and not live.get("error"):
        lines.append(f"Source: {live.get('source', 'NSE live API')} | As of: {live.get('as_of', '—')}")
    lines.append("")

    lines.append("### 1. Market Tape")
    for label, row in (
        ("NIFTY 50", n50),
        ("NIFTY BANK", bank),
        ("MIDCAP", mid),
        ("SMALLCAP", small),
        ("INDIA VIX", vix),
    ):
        last = row.get("last", row.get("close"))
        pct = row.get("pct_change", row.get("chg_pct"))
        if isinstance(last, (int, float)):
            lines.append(f"- {label}: {_fmt_num(last)} ({_fmt_pct(pct)})")
    if live_adv_dec:
        lines.append(
            f"- Live breadth: {live_adv_dec.get('advances', '—')} advances / "
            f"{live_adv_dec.get('declines', '—')} declines ({breadth_bias})."
        )

    if leaders or laggards:
        lines.append("\n### 2. Index Leadership")
        if leaders:
            lines.append("- Leaders: " + " | ".join(f"{name} {_fmt_pct(pct)}" for name, pct, _ in leaders))
        if laggards:
            lines.append("- Laggards: " + " | ".join(f"{name} {_fmt_pct(pct)}" for name, pct, _ in laggards))

    if brd and not brd.get("error"):
        lines.append("\n### 3. Breadth & Internal Health")
        lines.append(
            f"- DB universe: {brd.get('advances', '—')} advances / {brd.get('declines', '—')} declines; "
            f"A/D ratio {brd.get('ad_ratio', '—')}."
        )
        if brd.get("avg_rs_pct") is not None:
            lines.append(f"- Average RS: {brd.get('avg_rs_pct'):+.1f}%.")
        sd = brd.get("stage_distribution") or {}
        if sd:
            stage_bits = []
            for key, label in (
                ("STAGE_1", "Stage 1"),
                ("STAGE_2", "Stage 2"),
                ("STAGE_3", "Stage 3"),
                ("STAGE_4", "Stage 4"),
            ):
                value = sd.get(key, sd.get(key.lower()))
                if value is not None:
                    stage_bits.append(f"{label}: {int(value or 0)}")
            if stage_bits:
                lines.append("- Stage mix: " + " | ".join(stage_bits))

    if movers and not movers.get("error"):
        gainers = movers.get("gainers") or []
        losers = movers.get("losers") or []
        lines.append("\n### 4. Stock Movers")
        if gainers:
            lines.append(
                "- Top gainers: "
                + " | ".join(
                    f"{r.get('symbol', '—')} {_fmt_pct(r.get('pct_change'))}" for r in gainers[:5]
                )
            )
        if losers:
            lines.append(
                "- Top losers: "
                + " | ".join(
                    f"{r.get('symbol', '—')} {_fmt_pct(r.get('pct_change'))}" for r in losers[:5]
                )
            )

    fii = _get(tool_results, "get_fii_dii_activity") or {}
    if fii and not fii.get("error"):
        lines.append("\n### 5. Flows")
        flow_parts = []
        for row in (fii.get("data") or [])[:4]:
            net = row.get("net_crore")
            net_txt = f"{net:+,.0f} Cr" if isinstance(net, (int, float)) else "n/a"
            flow_parts.append(f"{row.get('category', 'Flow')} {net_txt} ({row.get('sentiment', '—')})")
        if flow_parts:
            lines.append("- " + " | ".join(flow_parts))

    if glob and not glob.get("error"):
        lines.append("\n### 6. Global Read-through")
        lines.append(f"- Global risk regime: {global_regime}; as of {glob.get('as_of', '—')}.")
        readthrough = glob.get("india_readthrough") or []
        for item in readthrough[:4]:
            lines.append(f"- {item}")
        watch = glob.get("watch_items") or []
        if watch:
            lines.append("- Watch: " + " | ".join(watch[:3]))

    if cat and cat.get("results"):
        lines.append("\n### 7. Catalyst Tape")
        for r in cat.get("results", [])[:3]:
            title = (r.get("title") or "")[:110]
            url = r.get("url") or ""
            lines.append(f"- {title}" + (f" — {url}" if url else ""))

    lines.append("\n### 8. Narrative")
    lines.append(
        f"- Dashboard bias: {narrative_bias}. NIFTY tape is {price_bias}, breadth is {breadth_bias}, "
        f"and global regime is {global_regime}. Treat this as a situational map, not a trade signal."
    )
    if leaders:
        lines.append(
            f"- Leadership clue: strongest index bucket is {leaders[0][0]} ({_fmt_pct(leaders[0][1])})."
        )
    if laggards:
        lines.append(
            f"- Risk clue: weakest index bucket is {laggards[0][0]} ({_fmt_pct(laggards[0][1])})."
        )
    lines.append(
        "- Operating plan: confirm with breadth expansion, sector leadership, and invalidation levels "
        "before acting."
    )

    lines.append("\n▶ SOURCE TRAIL")
    for tr in tool_results:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
        lines.append(f"  {tr['tool']}: {status}")
    lines.append(f"\n{FOOTER}")
    return "\n".join(l for l in lines if str(l).strip() != "")


def render_situation_assessment(
    tool_results: list[dict], assessment_plan: dict | None = None
) -> str:
    """Render the market_situation_assessment intent.

    This intent optionally shows an assessment plan if assessment_plan has
    show_plan=True, then emits a clarification when confidence is low.
    The bulk of the rendering falls through to the stock_brief fallback renderer,
    so this function only handles the plan/clarification header and returns an
    empty string — the caller is responsible for chaining with render_stock_brief.
    """
    from terminal.renderers.stock_brief import _render_assessment_plan_block

    lines: list[str] = []

    if (assessment_plan or {}).get("show_plan"):
        _render_assessment_plan_block(assessment_plan, tool_results, lines)

    _plan_conf_dict = (assessment_plan or {}).get("confidence")
    if isinstance(_plan_conf_dict, dict) and _plan_conf_dict.get("score", 1.0) < 0.65:
        try:
            from terminal.confidence import ConfidenceScore, render_clarification
            from rich.console import Console as _RConsole

            _restored = ConfidenceScore(
                score=float(_plan_conf_dict.get("score", 0.0)),
                stage=str(_plan_conf_dict.get("stage", "plan")),
                decision=str(_plan_conf_dict.get("decision", "")),
                reasons=list(_plan_conf_dict.get("reasons") or []),
                signals=dict(_plan_conf_dict.get("signals") or {}),
                alternatives=list(_plan_conf_dict.get("alternatives") or []),
            )
            render_clarification(_restored, _RConsole())
        except Exception:
            pass

    return "\n".join(lines)


def render_morning_briefing(tool_results: list[dict]) -> str:
    """Render the startup_morning_briefing intent."""
    live = _get(tool_results, "get_live_market_overview")
    brd = _get(tool_results, "get_market_breadth")
    glob = _get(tool_results, "get_global_market_assessment")
    cat = _get(tool_results, "search_latest_catalysts")

    def _fmt_index_from_live(name: str) -> str:
        row = (live or {}).get("indices", {}).get(name) or {}
        last = row.get("last", row.get("close"))
        pct = row.get("pct_change", row.get("chg_pct"))
        if isinstance(last, (int, float)):
            return f"{name}: {last:,.2f} ({_fmt_pct(pct)})"
        return f"{name}: live level unavailable"

    index_snaps = [
        tr["result"] for tr in tool_results
        if tr["tool"] == "get_index_snapshot" and isinstance(tr.get("result"), dict)
    ]
    movers = _get(tool_results, "get_top_gainers_losers") or {}
    fii = _get(tool_results, "get_fii_dii_activity") or {}

    lines: list[str] = []
    lines.append("## Good Morning — Market Intelligence Briefing")

    lines.append("\n### 🌍 Global Overnight Context")
    if glob and not glob.get("error"):
        lines.append(f"- Risk regime: {glob.get('risk_regime', '—')} as of {glob.get('as_of', '—')}.")
        regions = glob.get("regions") or {}
        if regions:
            lines.append(
                "- Regional bias: "
                + " | ".join(
                    f"{name} {data.get('bias', '—')} ({_fmt_pct(data.get('avg_pct_change'))})"
                    for name, data in regions.items()
                )
            )
        moves = glob.get("moves") or {}
        key_assets = [
            "S&P 500", "Nasdaq", "Dow Jones", "Hang Seng", "Nikkei 225",
            "Shanghai Composite", "Crude Oil", "DXY", "USDINR",
        ]
        key_moves = [
            f"{asset} {_fmt_pct(moves[asset].get('pct_change'))}"
            for asset in key_assets
            if asset in moves
        ]
        if key_moves:
            lines.append("- Key global moves: " + " | ".join(key_moves))
        for item in (glob.get("india_readthrough") or [])[:4]:
            lines.append(f"- India read-through: {item}")
    else:
        lines.append("- Global cached assessment unavailable; no unsupported inference added.")

    lines.append("\n### 📅 Previous Trading Day Recap (NSE)")
    if index_snaps:
        for row in index_snaps:
            if row.get("error"):
                continue
            close = row.get("close")
            chg = row.get("chg_pct")
            if isinstance(close, (int, float)):
                lines.append(f"- {row.get('index', 'Index')}: closed at {close:,.2f} ({_fmt_pct(chg)}).")
    if brd and not brd.get("error"):
        lines.append(
            f"- EOD universe breadth: {brd.get('advances', '—')} advances / "
            f"{brd.get('declines', '—')} declines; A/D ratio {brd.get('ad_ratio', '—')}."
        )

    lines.append("\n### 📊 Current Market Status")
    if live and not live.get("error"):
        lines.append(f"- {_fmt_index_from_live('NIFTY 50')}")
        lines.append(f"- {_fmt_index_from_live('NIFTY BANK')}")
        adv_dec = live.get("adv_dec") or {}
        if adv_dec:
            lines.append(
                f"- Live breadth: {adv_dec.get('advances', '—')} advances / "
                f"{adv_dec.get('declines', '—')} declines."
            )
        lines.append(f"- Source: {live.get('source', 'NSE live API')} | As of: {live.get('as_of', '—')}.")
    else:
        lines.append("- Live NSE overview unavailable; using cached/EOD context only.")
    if fii and not fii.get("error"):
        flow_parts = []
        for row in fii.get("data", [])[:4]:
            net = row.get("net_crore")
            net_txt = f"{net:+,.2f} Cr" if isinstance(net, (int, float)) else "n/a"
            flow_parts.append(f"{row.get('category', 'Flow')} {net_txt} ({row.get('sentiment', '—')})")
        if flow_parts:
            lines.append("- FII/DII: " + " | ".join(flow_parts))

    if movers and not movers.get("error"):
        gainers = movers.get("gainers") or []
        losers = movers.get("losers") or []
        if gainers:
            lines.append(
                "- Top NIFTY 50 gainers: "
                + ", ".join(
                    f"{r.get('symbol')} {_fmt_pct(r.get('pct_change'))}" for r in gainers[:3]
                )
            )
        if losers:
            lines.append(
                "- Top NIFTY 50 losers: "
                + ", ".join(
                    f"{r.get('symbol')} {_fmt_pct(r.get('pct_change'))}" for r in losers[:3]
                )
            )

    lines.append("\n### 🎯 Today's Watchlist & Themes")
    watch_items = (glob or {}).get("watch_items") or []
    if watch_items:
        for item in watch_items[:4]:
            lines.append(f"- {item}")
    elif movers and not movers.get("error") and (movers.get("gainers") or movers.get("losers")):
        symbols = [
            r.get("symbol")
            for r in (movers.get("gainers") or [])[:2] + (movers.get("losers") or [])[:2]
            if r.get("symbol")
        ]
        lines.append("- Monitor live movers for continuation/fade research: " + ", ".join(symbols))
    else:
        lines.append(
            "- Monitor index breadth, FII/DII flows, USD/INR, crude, and high-volume NIFTY 50 movers."
        )

    if cat and cat.get("results"):
        lines.append("\n### 📰 Latest Source Trail")
        for r in cat["results"][:3]:
            title = (r.get("title") or "")[:110]
            url = r.get("url") or ""
            lines.append(f"- {title} — {url}" if url else f"- {title}")

    lines.append("\n### 🔬 Analyst's Take")
    regime = (glob or {}).get("risk_regime", "mixed")
    live_breadth = (live or {}).get("adv_dec") or {}
    breadth_text = (
        f"live breadth at {live_breadth.get('advances', '—')} advances "
        f"vs {live_breadth.get('declines', '—')} declines"
        if live_breadth else "live breadth unavailable"
    )
    lines.append(
        f"- Bias is {regime}: combine the global cue with {breadth_text}, institutional flow, "
        "and NIFTY/BANKNIFTY levels before forming any intraday view. "
        "Keep position sizing and invalidation discipline explicit."
    )

    lines.append("\n### Follow-up questions")
    lines.append("1. `/global` — refresh the full global risk regime and India read-through.")
    lines.append("2. `/heat` — inspect live sector and breadth heatmap for leadership confirmation.")
    lines.append("3. `/scan NIFTY 50 vwap` — find intraday research setups with clear invalidation.")

    lines.append("\n▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))
    lines.append(f"\n{FOOTER}")
    return "\n".join(l for l in lines if str(l).strip() != "")
