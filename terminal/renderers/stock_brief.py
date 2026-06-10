"""Big fallback renderer: covers forensic + sym fallback block (agent.py lines 4995–6217).

Also provides _render_assessment_plan_block and _first_nonempty_row helpers.
"""

from terminal.renderers._base import _get, _source_trail_lines, FOOTER


# ─── Shared helpers ────────────────────────────────────────────────────────────

def _render_assessment_plan_block(plan: dict | None, tool_results: list[dict], lines: list[str]) -> None:
    """Render the SITUATION ASSESSMENT PLAN block into *lines* in place."""
    if not plan:
        return
    tool_status: dict[str, str] = {}
    for tr in tool_results:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        tool_status[tr["tool"]] = (
            f"ERROR: {result.get('error')}" if result.get("error") else "ok"
        )

    lines.append("▶ SITUATION ASSESSMENT PLAN")
    for i, task in enumerate(plan.get("tasks") or [], start=1):
        tool = task.get("tool")
        derived_from = task.get("derived_from")
        if tool:
            status = tool_status.get(tool, "not executed")
            source = f"tool={tool}"
        elif derived_from:
            status = (
                "derived"
                if tool_status.get(derived_from) == "ok"
                else f"blocked by {derived_from}"
            )
            source = f"derived_from={derived_from}"
        else:
            status = "missing tool"
            source = "tool=missing"
        lines.append(f"  {i}. {task.get('question')} [{source}; status={status}]")
        if status != "ok" and status != "derived" and task.get("fallback"):
            lines.append(f"     fallback: {task.get('fallback')}")
        if (
            (not tool or status.startswith("ERROR") or status == "not executed")
            and task.get("recovery_plan")
        ):
            lines.append(f"     recovery/code plan: {task.get('recovery_plan')}")
    lines.append("")


def _first_nonempty_row(table: dict, labels: tuple) -> tuple | None:
    """Match each label loosely: ignores trailing '+' / '%' and is case-insensitive."""
    def _norm(s: str) -> str:
        return (s or "").replace("+", "").replace("%", "").strip().lower()
    wanted = {_norm(label) for label in labels}
    for key, values in (table or {}).items():
        if key.startswith("_"):
            continue
        if _norm(key) in wanted and isinstance(values, list) and any(str(v).strip() for v in values):
            return key, values
    return None


def _num(value) -> float | None:
    text = str(value or "").strip()
    if not text or text in {"—", "-", "N/A", "NA", "None"}:
        return None
    text = text.replace(",", "").replace("%", "").replace("₹", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _pct_change(current, previous) -> float | None:
    curr = _num(current)
    prev = _num(previous)
    if curr is None or prev in (None, 0):
        return None
    return round((curr - prev) / abs(prev) * 100, 1)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _growth_metric_line(label: str, values: list, *, qoq: bool = False) -> str | None:
    clean = [v for v in values if str(v or "").strip()]
    if qoq:
        if len(clean) < 2:
            return None
        change = _pct_change(clean[-1], clean[-2])
    else:
        # Quarterly YoY uses same quarter last year when six rolling quarters
        # are available: latest index -1 vs latest -5. Annual YoY uses -1 vs -2.
        lag = 4 if len(clean) >= 5 else 1
        if len(clean) <= lag:
            return None
        change = _pct_change(clean[-1], clean[-1 - lag])
    if change is None:
        return None
    return f"  {label}: {_fmt_pct(change)}"


def _sales_eps_growth_lines(q_rows: dict, a_rows: dict) -> list[str]:
    sales_q = _first_nonempty_row(q_rows, ("Sales", "Revenue", "Operating Revenue"))
    eps_q = _first_nonempty_row(q_rows, ("EPS in Rs", "EPS"))
    sales_a = _first_nonempty_row(a_rows, ("Sales", "Revenue"))
    eps_a = _first_nonempty_row(a_rows, ("EPS in Rs", "EPS"))

    lines: list[str] = []
    for item in (
        _growth_metric_line("Quarterly Sales YoY", sales_q[1]) if sales_q else None,
        _growth_metric_line("Quarterly EPS YoY", eps_q[1]) if eps_q else None,
        _growth_metric_line("Quarterly Sales QoQ", sales_q[1], qoq=True) if sales_q else None,
        _growth_metric_line("Quarterly EPS QoQ", eps_q[1], qoq=True) if eps_q else None,
        _growth_metric_line("Annual Sales YoY", sales_a[1], qoq=True) if sales_a else None,
        _growth_metric_line("Annual EPS YoY", eps_a[1], qoq=True) if eps_a else None,
    ):
        if item:
            lines.append(item)
    if not lines:
        return []
    return ["\n▶ SALES & EPS GROWTH", *lines]


def _market_breadth_verdict(live: dict | None, brd: dict | None) -> list[str]:
    if not brd or brd.get("error"):
        return []
    advances = brd.get("advances")
    declines = brd.get("declines")
    if not isinstance(advances, (int, float)) or not isinstance(declines, (int, float)):
        return []
    total = advances + declines
    advancing_pct = round(advances / total * 100) if total else None
    try:
        ratio = float(brd.get("ad_ratio"))
    except Exception:
        ratio = advances / declines if declines else 0.0
    sd = brd.get("stage_distribution") or {}
    total_stocks = brd.get("total_stocks") or sum(int(value or 0) for value in sd.values())

    def _stage_pct(key: str) -> int | None:
        if not total_stocks:
            return None
        value = sd.get(key, sd.get(key.lower()))
        if value is None:
            return None
        return round(float(value or 0) / float(total_stocks) * 100)

    stage2_pct = _stage_pct("STAGE_2")
    stage4_pct = _stage_pct("STAGE_4")
    if ratio >= 1.25 and (stage2_pct is None or stage2_pct >= 25):
        bias = "healthy/positive"
    elif ratio >= 1.0:
        bias = "mixed but improving"
    elif ratio >= 0.8:
        bias = "weak/negative"
    else:
        bias = "broadly weak"

    scope_name = brd.get("index") or brd.get("requested_index") or "Market"
    scope_label = f"{scope_name} breadth" if scope_name != "Market" else "Market breadth"
    pieces = [
        f"{scope_label} is {bias}.",
        f"Advances are {int(advances)} advances vs {int(declines)} declines",
        f"so about {advancing_pct}% of stocks are advancing" if advancing_pct is not None else "",
        f"and the A/D ratio is {ratio:.2f}.",
    ]
    stage_bits = []
    if stage2_pct is not None:
        stage_bits.append(f"Stage 2 uptrends are {stage2_pct}%")
    if stage4_pct is not None:
        stage_bits.append(f"Stage 4 downtrends are {stage4_pct}%")
    if stage_bits:
        pieces.append("Stage mix is also not strong: " + ", while ".join(stage_bits) + ".")
    sectors = []
    if live and not live.get("error"):
        sectors = [
            str(row.get("name") or "").strip()
            for row in (live.get("top_sectors") or [])
            if row.get("name")
        ]
    if sectors:
        pieces.append("Relative pockets: " + " and ".join(sectors[:3]) + ".")
    return ["\n▶ BREADTH VERDICT", "  " + " ".join(piece for piece in pieces if piece)]


def _market_rs_distribution_lines(brd: dict | None) -> list[str]:
    if not brd or brd.get("error"):
        return []
    percentiles = brd.get("rs_percentiles") or {}
    distribution = brd.get("rs_distribution") or {}
    if not percentiles and not distribution:
        return []

    lines = ["\n▶ RS DISTRIBUTION"]
    if percentiles:
        pieces = []
        for key in ("p10", "p25", "p50", "p75", "p90"):
            value = percentiles.get(key)
            if isinstance(value, (int, float)):
                pieces.append(f"{key} {value:.1f}%")
        if pieces:
            lines.append("  Percentiles: " + " | ".join(pieces))
    for key in ("negative", "neutral_0_25", "positive_25_50", "strong_50_plus"):
        row = distribution.get(key) if isinstance(distribution, dict) else None
        if not isinstance(row, dict):
            continue
        label = row.get("label") or key
        count = row.get("count")
        pct = row.get("pct")
        pct_txt = f" ({pct:.1f}%)" if isinstance(pct, (int, float)) else ""
        lines.append(f"  {label}: {count}{pct_txt}")
    return lines


# ─── Main fallback renderer ────────────────────────────────────────────────────

def render(
    intent: str,
    tool_results: list[dict],
    assessment_plan: dict | None = None,
) -> str:
    """Big fallback renderer — covers forensic + sym fallback (agent.py lines 4995–6217).

    Called when no named intent branch matched in the dispatcher.
    """
    snap = _get(tool_results, "get_symbol_snapshot")
    tech = _get(tool_results, "get_technical_setup")
    sec = _get(tool_results, "get_sector_context")
    idx = _get(tool_results, "get_index_snapshot")
    live = _get(tool_results, "get_live_market_overview")
    brd = _get(tool_results, "get_market_breadth")
    scr = _get(tool_results, "run_screener_query")
    growth_research = _get(tool_results, "get_long_term_growth_candidates")
    strength = _get(tool_results, "validate_strength_watchlist")
    knowledge = _get(tool_results, "search_market_knowledge")
    cat = _get(tool_results, "search_latest_catalysts")
    glob = _get(tool_results, "get_global_market_assessment")
    movers = _get(tool_results, "get_top_gainers_losers")
    comparison = _get(tool_results, "compare_stocks")
    insider_alerts = _get(tool_results, "get_insider_alerts")
    portfolio_exposure = _get(tool_results, "get_portfolio_exposure")
    portfolio_narratives = _get(tool_results, "generate_portfolio_narratives")
    portfolio_forensic = _get(tool_results, "screen_portfolio_forensic_watchlist") or _get(tool_results, "screen_forensic_watchlist")
    event_calendar = _get(tool_results, "get_event_calendar_summary")
    market_recap = _get(tool_results, "get_intraday_market_recap")
    fno_overview = _get(tool_results, "get_fno_overview")
    forensic = _get(tool_results, "run_forensic_analysis")
    deep = _get(tool_results, "deep_search")
    intra_setup = _get(tool_results, "explain_intraday_setup")
    intra_screen = _get(tool_results, "run_intraday_screener")
    intra_index_scan = _get(tool_results, "scan_intraday_market")
    intra_symbol_scan = _get(tool_results, "scan_symbols_intraday")
    intra_levels = _get(tool_results, "get_intraday_levels")
    intra_ind = _get(tool_results, "compute_intraday_indicators")
    nse_intraday = _get(tool_results, "get_nse_intraday_snapshot")
    intra_legacy = _get(tool_results, "get_intraday_analysis")
    scr_fund = _get(tool_results, "scrape_screener_in")
    research = _get(tool_results, "comprehensive_stock_research") or {}
    # /analyze pipes through comprehensive_stock_research, which wraps
    # scrape_screener_in under result["screener"]. Backfill scr_fund.
    if not scr_fund and isinstance(research, dict):
        emb = research.get("screener")
        if isinstance(emb, dict):
            scr_fund = emb
    nse_ann = _get(tool_results, "search_nse_announcements")
    bse_filings = _get(tool_results, "search_bse_filings")
    concalls = _get(tool_results, "search_concall_transcripts")
    cached_financials = _get(tool_results, "get_cached_financials")
    latest_results = _get(tool_results, "get_latest_results")

    sym = (snap or {}).get("symbol") or (tech or {}).get("symbol") or ""
    if not sym and forensic:
        sym = forensic.get("symbol") or ""
    cname = (snap or {}).get("company_name") or sym

    lines: list[str] = []

    # ── FORENSIC block (when run_forensic_analysis was called) ────────────────
    if forensic:
        fsym = forensic.get("symbol") or sym or "SYMBOL"
        lines.append(f"━━━ {fsym} — FORENSIC ACCOUNTING ANALYSIS ━━━")
        if forensic.get("error"):
            lines.append(f"\n▶ ERROR\n  {forensic.get('error')}")
        else:
            beneish = forensic.get("beneish") or {}
            piotroski = forensic.get("piotroski") or {}
            altman = forensic.get("altman") or {}
            lines.append(
                f"Overall forensic risk: {str(forensic.get('overall_risk', 'unknown')).upper()}"
            )
            if forensic.get("source_url"):
                lines.append(f"Source: {forensic.get('source_url')}")

            lines.append("\n▶ Beneish M-score")
            lines.append(
                f"  Score: {beneish.get('score', '—')} | "
                f"Interpretation: {beneish.get('interpretation', '—')}"
            )
            risk_flags = beneish.get("risk_flags") or []
            lines.append(
                "  Flagged variables: "
                + (", ".join(map(str, risk_flags)) if risk_flags else "None reported")
            )
            variables = beneish.get("variables") or beneish.get("components") or {}
            for name, value in list(variables.items())[:10]:
                lines.append(f"    - {name}: {value}")

            lines.append("\n▶ Piotroski F-score")
            max_possible = piotroski.get("max_possible", 9)
            lines.append(
                f"  Score: {piotroski.get('score', '—')}/{max_possible} | "
                f"Financial health: {piotroski.get('strength') or piotroski.get('interpretation', '—')}"
            )
            signals = piotroski.get("signals") or piotroski.get("components") or {}
            for name, value in list(signals.items())[:12]:
                verdict = (
                    "pass" if value in {1, True, "pass", "PASS"}
                    else "fail" if value in {0, False, "fail", "FAIL"}
                    else value
                )
                lines.append(f"    - {name}: {verdict}")

            lines.append("\n▶ Altman Z'-score")
            lines.append(
                f"  Score: {altman.get('score', '—')} | "
                f"Zone: {altman.get('zone') or altman.get('interpretation', '—')}"
            )
            components = altman.get("components") or {}
            for name, value in list(components.items())[:8]:
                lines.append(f"    - {name}: {value}")

            if forensic.get("summary"):
                lines.append("\n▶ SUMMARY")
                for line in str(forensic["summary"]).splitlines():
                    lines.append(f"  {line}")

        # ── TECHNICAL SETUP (for /analyze 360°) ─────────────────────────────
        if tech and isinstance(tech, dict) and not tech.get("error"):
            lines.append("\n━━━ TECHNICAL SETUP ━━━")
            if tech.get("technical_score") is not None:
                lines.append(
                    f"  Derived score: {tech.get('technical_score')} "
                    f"({tech.get('score_method', 'derived')})"
                )
            lines.append(f"  RSI:        {tech.get('rsi', '—')}")
            lines.append(f"  ADX:        {tech.get('adx', '—')}  (>25 = trending)")
            lines.append(f"  MACD:       {tech.get('macd', '—')}")
            lines.append(f"  Supertrend: {tech.get('supertrend', '—')}")
            ma_flags = []
            if tech.get("above_sma20"):
                ma_flags.append("▲ SMA20")
            if tech.get("above_sma50"):
                ma_flags.append("▲ SMA50")
            if tech.get("above_sma200"):
                ma_flags.append("▲ SMA200")
            lines.append(f"  MAs:        {' | '.join(ma_flags) or '— below key MAs'}")
            h52, l52, pct = tech.get("52w_high"), tech.get("52w_low"), tech.get("pct_from_52h")
            if h52 and l52:
                pct_txt = (
                    f"  ({pct:+.1f}% from high)" if isinstance(pct, (int, float)) else ""
                )
                lines.append(f"  52W Range:  ₹{l52:,.0f} – ₹{h52:,.0f}{pct_txt}")
            vr = tech.get("vol_ratio")
            if isinstance(vr, (int, float)):
                lines.append(f"  Volume:     {vr:.1f}x avg")
            if tech.get("stage"):
                lines.append(f"  Stage:      {tech.get('stage')}")
            if tech.get("trend_signal"):
                lines.append(f"  Trend:      {tech.get('trend_signal')}")

        # ── SECTOR CONTEXT (for /analyze 360°) ──────────────────────────────
        if sec and isinstance(sec, dict) and not sec.get("error"):
            lines.append("\n━━━ SECTOR CONTEXT ━━━")
            lines.append(f"  Sector:         {sec.get('sector', '—')}")
            lines.append(f"  Stocks in DB:   {sec.get('total_stocks', '—')}")
            lines.append(f"  Stage 2 count:  {sec.get('stage2_count', '—')}")
            lines.append(f"  Buy signals:    {sec.get('buy_signals', '—')}")
            avg_rs = sec.get("avg_rs_pct")
            if isinstance(avg_rs, (int, float)):
                lines.append(f"  Avg RS:         {avg_rs:+.1f}%")
            avg_1m = sec.get("avg_1m_pct")
            if isinstance(avg_1m, (int, float)):
                lines.append(f"  Avg 1M chg:     {avg_1m:+.2f}%")
            top5 = sec.get("top5_by_score") or []
            if top5:
                lines.append(
                    "  Top peers:      "
                    + ", ".join(str(s.get("symbol", "?")) for s in top5[:5])
                )

        # ── LATEST CATALYSTS (for /analyze 360°) ────────────────────────────
        if cat and isinstance(cat, dict) and (cat.get("results") or []):
            lines.append("\n━━━ LATEST CATALYSTS ━━━")
            for r in (cat.get("results") or [])[:5]:
                if not isinstance(r, dict):
                    continue
                title = str(r.get("title") or "")[:100]
                url = str(r.get("url") or "")
                snippet = str(r.get("snippet") or "")[:140]
                lines.append(f"  • {title}")
                if url:
                    lines.append(f"    {url}")
                if snippet:
                    lines.append(f"    {snippet}")
            sentiment = cat.get("sentiment") or cat.get("overall_sentiment")
            if sentiment:
                lines.append(f"  Sentiment: {sentiment}")

        # ── INSTITUTIONAL & INSIDER (screener shareholding + deep_search) ───
        section_lines: list[str] = []
        shp_src = (scr_fund or {}).get("shareholding") if isinstance(scr_fund, dict) else None
        if isinstance(shp_src, dict) and shp_src:
            for label, keys in (
                ("Promoters", ("Promoters", "Promoter")),
                ("FII",       ("FIIs", "FII")),
                ("DII",       ("DIIs", "DII")),
                ("Government", ("Government",)),
                ("Public",    ("Public",)),
            ):
                v = None
                for k in keys:
                    if shp_src.get(k) not in (None, ""):
                        v = shp_src.get(k)
                        break
                if v is not None:
                    trend = shp_src.get(f"{keys[0]}_trend") or shp_src.get(f"{label}_trend")
                    extra = ""
                    if isinstance(trend, list) and len(trend) >= 2:
                        extra = f"  (trend: {' → '.join(str(t) for t in trend[-4:])})"
                    section_lines.append(f"  {label:<11} {v}{extra}")
            quarters = shp_src.get("_quarters")
            if isinstance(quarters, list) and quarters:
                section_lines.append(f"  Quarters covered: {quarters[0]} → {quarters[-1]}")
        if deep and isinstance(deep, dict) and not deep.get("error"):
            verticals = deep.get("verticals") or deep.get("data") or {}
            if isinstance(verticals, dict):
                insider = verticals.get("insider_trades") or verticals.get("insiders") or []
                if isinstance(insider, list) and insider:
                    section_lines.append("  Recent insider activity:")
                    for entry in insider[:3]:
                        if isinstance(entry, dict):
                            txt = entry.get("summary") or entry.get("description") or str(entry)
                            section_lines.append(f"    • {str(txt)[:140]}")
                targets = verticals.get("analyst_targets") or verticals.get("targets") or []
                if isinstance(targets, list) and targets:
                    section_lines.append("  Analyst targets:")
                    for entry in targets[:3]:
                        if isinstance(entry, dict):
                            txt = entry.get("summary") or entry.get("target") or str(entry)
                            section_lines.append(f"    • {str(txt)[:140]}")
            if section_lines:
                lines.append("\n━━━ INSTITUTIONAL & INSIDER ACTIVITY ━━━")
                lines.extend(section_lines)

        # ── FUNDAMENTAL ANALYSIS (for /analyze 360°) ────────────────────────
        if scr_fund and isinstance(scr_fund, dict) and not scr_fund.get("error"):
            ratios_f = scr_fund.get("ratios") or {}
            q_f = scr_fund.get("quarterly") or {}
            annual_f = scr_fund.get("annual_pl") or {}
            pros_f = scr_fund.get("pros") or []
            cons_f = scr_fund.get("cons") or []

            fund_lines: list[str] = []

            if isinstance(ratios_f, dict) and ratios_f:
                def _norm_key(k: str) -> str:
                    return str(k).strip().rstrip("+").strip().lower()
                key_ratios = [
                    ("Market Cap", ("Market Cap",)),
                    ("Current Price", ("Current Price",)),
                    ("Stock P/E", ("Stock P/E", "P/E")),
                    ("Industry P/E", ("Industry PE", "Industry P/E")),
                    ("Book Value", ("Book Value",)),
                    ("Price to Book", ("Price to book value", "P/B")),
                    ("Dividend Yield", ("Dividend Yield",)),
                    ("ROCE", ("ROCE", "Return on capital employed")),
                    ("ROE", ("ROE", "Return on equity")),
                    ("Debt to Equity", ("Debt to equity",)),
                    ("Sales Growth 3Y", ("Sales growth 3Years", "Compounded Sales Growth 3Years")),
                    ("Profit Growth 3Y", ("Profit growth 3Years", "Compounded Profit Growth 3Years")),
                    ("Promoter Holding", ("Promoter holding",)),
                    ("FII Holding", ("FII holding",)),
                ]
                rendered_ratio_rows: list[tuple[str, str]] = []
                norm_ratios = {_norm_key(k): v for k, v in ratios_f.items()}
                for label, keys in key_ratios:
                    val = None
                    for k in keys:
                        v = norm_ratios.get(_norm_key(k))
                        if v not in (None, "", "—"):
                            val = v
                            break
                    if val not in (None, "", "—"):
                        rendered_ratio_rows.append((label, str(val)))
                if rendered_ratio_rows:
                    fund_lines.append("\n▶ KEY RATIOS")
                    for label, val in rendered_ratio_rows:
                        fund_lines.append(f"  - {label}: {val}")

            q_headers_f = q_f.get("_headers") if isinstance(q_f, dict) else []
            if q_headers_f:
                qmetrics = []
                for labels in (
                    ("Sales", "Revenue", "Operating Revenue"),
                    ("Operating Profit",),
                    ("OPM %",),
                    ("Net Profit", "Profit after tax", "PAT"),
                    ("EPS in Rs", "EPS"),
                ):
                    wanted = {l.strip().lower() for l in labels}
                    for key, values in q_f.items():
                        if str(key).startswith("_"):
                            continue
                        norm_k = str(key).strip().rstrip("+").strip().lower()
                        if norm_k in wanted and isinstance(values, list):
                            if any(str(v).strip() for v in values):
                                qmetrics.append((str(key).rstrip("+").strip(), values))
                                break
                if qmetrics:
                    fund_lines.append("\n▶ QUARTERLY P&L (₹ Cr — last 6 quarters)")
                    hdrs = [str(h) for h in q_headers_f[-6:]]
                    fund_lines.append(
                        "  | Metric              | "
                        + " | ".join(f"{h:>10}" for h in hdrs)
                        + " |"
                    )
                    fund_lines.append("  |---------------------|" + ("------------|" * len(hdrs)))
                    for label, values in qmetrics:
                        vals = list(values)
                        if (
                            vals
                            and isinstance(vals[0], str)
                            and vals[0].strip().rstrip("+").strip().lower() == label.strip().lower()
                        ):
                            vals = vals[1:]
                        tail = vals[-len(hdrs):] if len(vals) >= len(hdrs) else vals
                        padded = [""] * (len(hdrs) - len(tail)) + list(tail)
                        cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                        fund_lines.append(f"  | {str(label)[:19]:<19} | {cells} |")

            annual_headers_f = annual_f.get("_headers") if isinstance(annual_f, dict) else []
            if annual_headers_f:
                ametrics = []
                for labels in (
                    ("Sales", "Revenue"),
                    ("Net Profit", "Profit after tax", "PAT"),
                    ("EPS in Rs", "EPS"),
                ):
                    wanted = {l.strip().lower() for l in labels}
                    for key, values in annual_f.items():
                        if str(key).startswith("_"):
                            continue
                        norm_k = str(key).strip().rstrip("+").strip().lower()
                        if norm_k in wanted and isinstance(values, list):
                            if any(str(v).strip() for v in values):
                                ametrics.append((str(key).rstrip("+").strip(), values))
                                break
                if ametrics:
                    fund_lines.append("\n▶ ANNUAL P&L (₹ Cr — last 5 years)")
                    hdrs = [str(h) for h in annual_headers_f[-5:]]
                    fund_lines.append(
                        "  | Metric              | "
                        + " | ".join(f"{h:>10}" for h in hdrs)
                        + " |"
                    )
                    fund_lines.append("  |---------------------|" + ("------------|" * len(hdrs)))
                    for label, values in ametrics:
                        vals = list(values)
                        if (
                            vals
                            and isinstance(vals[0], str)
                            and vals[0].strip().rstrip("+").strip().lower() == label.strip().lower()
                        ):
                            vals = vals[1:]
                        tail = vals[-len(hdrs):] if len(vals) >= len(hdrs) else vals
                        padded = [""] * (len(hdrs) - len(tail)) + list(tail)
                        cells = " | ".join(f"{str(v or '—'):>10}" for v in padded)
                        fund_lines.append(f"  | {str(label)[:19]:<19} | {cells} |")

            if pros_f or cons_f:
                fund_lines.append("\n▶ SCREENER ANALYSIS")
                if pros_f:
                    fund_lines.append("  Pros:")
                    for p in pros_f[:5]:
                        fund_lines.append(f"    • {p}")
                if cons_f:
                    fund_lines.append("  Cons:")
                    for c in cons_f[:5]:
                        fund_lines.append(f"    • {c}")

            if fund_lines:
                lines.append("\n━━━ FUNDAMENTAL ANALYSIS ━━━")
                lines.extend(fund_lines)
                if scr_fund.get("source_url"):
                    lines.append(f"\nSource: {scr_fund.get('source_url')}")

        lines.append("\n▶ SOURCE TRAIL")
        for tr in tool_results:
            result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
            status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
            lines.append(f"  {tr['tool']}: {status}")
        lines.append(f"\n{FOOTER}")
        return "\n".join(l for l in lines if str(l).strip() != "")

    # ── sym fallback (Market Brief) ────────────────────────────────────────────
    if sym:
        lines.append(f"━━━ {cname} ({sym}) — Market Brief ━━━")
        snap_date = (snap or {}).get("snapshot_date", "N/A")
        lines.append(f"Data: EOD snapshot {snap_date}\n")

    if market_recap and not market_recap.get("error"):
        minutes = market_recap.get("minutes", 15)
        lines.append(f"━━━ Last {minutes} Minutes — Market Recap ━━━")
        lines.append(f"  {market_recap.get('narrative', 'Live market recap unavailable.')}")
        rows = market_recap.get("rows") or []
        if rows:
            lines.append("\n▶ INDEX TAPE")
            for row in rows:
                current = row.get("current")
                day_pct = row.get("current_pct_change")
                interval_pct = row.get("interval_pct_change")
                points = row.get("point_change")
                if current is None:
                    continue
                interval_text = (
                    f" | {points:+.2f} pts ({interval_pct:+.2f}%) vs stored {minutes}m tape"
                    if isinstance(points, (int, float)) and isinstance(interval_pct, (int, float))
                    else " | no earlier stored tape"
                )
                day_text = f" ({day_pct:+.2f}% day)" if isinstance(day_pct, (int, float)) else ""
                lines.append(
                    f"  {row.get('symbol')}: {float(current):,.2f}{day_text}{interval_text}"
                )
        adv_dec = market_recap.get("adv_dec") or {}
        if adv_dec:
            lines.append(
                f"\n▶ LIVE BREADTH\n  {adv_dec.get('advances', '—')} advances / "
                f"{adv_dec.get('declines', '—')} declines"
            )
        lines.append(
            f"\nSource: {market_recap.get('source', 'NSE live API')} | "
            f"As of: {market_recap.get('as_of', '—')}"
        )

    if strength and not strength.get("error"):
        lines.append("━━━ Validated Multi-Factor Strength ━━━")
        lines.append(f"Data: EOD snapshot {strength.get('snapshot_date') or 'N/A'}")
        lines.append(strength.get("validation_rule", "Missing evidence is not inferred."))
        for row in strength.get("results", [])[:10]:
            score = row.get("strength_score")
            score_txt = f"{score:.1f}" if isinstance(score, (int, float)) else "N/A"
            piot = row.get("piotroski_score")
            piot_txt = (
                f"{piot}/{row.get('piotroski_max')}" if piot is not None else "N/A"
            )
            missing = row.get("missing_evidence") or []
            lines.append(
                f"- {row.get('symbol')}: score {score_txt}; "
                f"CANSLIM {row.get('can_slim_score') or 'N/A'}; "
                f"RS {row.get('rs_pct') if row.get('rs_pct') is not None else 'N/A'}; "
                f"Fund {row.get('enhanced_fund_score') or 'N/A'}; "
                f"Piotroski {piot_txt}; "
                f"Risk {row.get('overall_forensic_risk') or 'unknown'}; "
                f"{row.get('verdict')}"
            )
            if missing:
                lines.append(f"  Missing evidence: {', '.join(missing)}")
        lines.append(f"\n{FOOTER}")
        return "\n".join([ln for ln in lines if ln is not None])

    if comparison and not comparison.get("error"):
        lines.append("▶ STOCK COMPARISON")
        lines.append(f"  Symbols: {', '.join(comparison.get('symbols') or [])}")
        lines.append(f"  Aspects: {', '.join(comparison.get('aspects') or [])}")
        for row in (comparison.get("stock_details") or [])[:6]:
            bits = [
                str(row.get("symbol", "—")),
                f"stage {row.get('stage', '—')}",
                f"tech {row.get('technical_score', '—')}",
                f"RS {row.get('rs_pct', '—')}",
                f"signal {row.get('trading_signal', '—')}",
                f"sector {row.get('sector', '—')}",
            ]
            if row.get("pe") is not None:
                bits.append(f"P/E {row.get('pe')}")
            if row.get("roe") is not None:
                bits.append(f"ROE {row.get('roe')}")
            lines.append("  - " + " | ".join(bits))

    if insider_alerts and not insider_alerts.get("error"):
        alerts = insider_alerts.get("alerts") or []
        lines.append(f"━━━ INSIDER & BULK DEAL ALERTS ━━━")
        lines.append(f"Total alerts: {insider_alerts.get('total', len(alerts))}")
        for a in alerts[:15]:
            val = a.get("value_cr", "")
            val_str = f"₹{val}Cr" if val else ""
            lines.append(
                f"  [{a.get('date','')}] {a.get('symbol','')}: {a.get('alert_type','')} "
                f"| {a.get('entity','')} | {val_str} {a.get('detail','')}"
            )
        lines.append("")

    if portfolio_exposure and not portfolio_exposure.get("error"):
        total = portfolio_exposure.get("total_stocks", 0)
        lines.append(f"━━━ PORTFOLIO OVERVIEW ━━━")
        lines.append(f"Holdings: {total} stocks")
        sector_counts = portfolio_exposure.get("sector_counts") or {}
        if sector_counts:
            top_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)[:6]
            lines.append("\n▶ SECTOR BREAKDOWN")
            for sec, cnt in top_sectors:
                pct = cnt / total * 100 if total else 0
                lines.append(f"  - {sec}: {cnt} stocks ({pct:.0f}%)")
        top_holdings = portfolio_exposure.get("top_holdings") or []
        if top_holdings:
            lines.append("\n▶ TOP HOLDINGS (by value)")
            for h in top_holdings[:10]:
                sym_h = h.get("symbol", "")
                val = h.get("value", 0)
                sec_h = h.get("sector", "")
                val_str = f"₹{val:,.0f}" if val else "—"
                lines.append(f"  - {sym_h}: {val_str}  [{sec_h}]")
        lines.append("")

    if portfolio_narratives and not portfolio_narratives.get("error"):
        lines.append("▶ PORTFOLIO REVIEW")
        for row in (portfolio_narratives.get("narratives") or [])[:10]:
            if row.get("error"):
                lines.append(f"  - {row.get('symbol')}: ERROR {row.get('error')}")
                continue
            lines.append(
                f"  - {row.get('symbol')}: stage {row.get('stage', '—')} | "
                f"RSI {row.get('rsi', '—')} | action {row.get('action_hint', '—')}"
            )
            if row.get("thesis"):
                lines.append(f"    thesis: {row.get('thesis')}")
            if row.get("bear_case"):
                lines.append(f"    risk: {row.get('bear_case')}")

    if portfolio_forensic:
        lines.append("━━━ PORTFOLIO FORENSIC ACCOUNTING SCREEN ━━━")
        if portfolio_forensic.get("error"):
            lines.append(f"\n▶ ERROR\n  {portfolio_forensic.get('error')}")
        else:
            screened = portfolio_forensic.get("screened_count") or portfolio_forensic.get("count") or len(portfolio_forensic.get("results") or [])
            total = portfolio_forensic.get("portfolio_total_stocks")
            total_txt = f" of {total}" if total else ""
            lines.append(f"Screened {screened}{total_txt} portfolio holdings for Beneish, Piotroski and Altman red flags.")
            high = portfolio_forensic.get("high_risk") or []
            moderate = portfolio_forensic.get("moderate_risk") or []
            low = portfolio_forensic.get("low_risk") or []
            lines.append(
                f"Risk buckets: high {len(high)} | moderate {len(moderate)} | low {len(low)}"
            )
            source = portfolio_forensic.get("portfolio_source")
            if source:
                lines.append(f"Portfolio source: {source}")
            rows = portfolio_forensic.get("results") or []
            if rows:
                lines.append("\n▶ HOLDING-LEVEL FLAGS")
                for row in rows[:10]:
                    if row.get("error"):
                        lines.append(f"  - {row.get('symbol', '—')}: ERROR {row.get('error')}")
                        continue
                    lines.append(
                        f"  - {row.get('symbol', '—')}: risk {str(row.get('overall_risk', 'unknown')).upper()} | "
                        f"Beneish {row.get('beneish_score', '—')} | "
                        f"Piotroski {row.get('piotroski_score', '—')} | "
                        f"Altman {row.get('altman_score', '—')}"
                    )

    if event_calendar and not event_calendar.get("error"):
        lines.append("▶ EVENT CALENDAR")
        lines.append(
            f"  Index: {event_calendar.get('index', '—')} | "
            f"Window: {event_calendar.get('days_ahead', '—')} days | "
            f"Total events: {event_calendar.get('total_events', '—')}"
        )
        counts = event_calendar.get("event_counts") or {}
        if counts:
            lines.append("  Event mix: " + " | ".join(f"{k}: {v}" for k, v in counts.items()))
        events = event_calendar.get("events") or []
        if events:
            lines.append("  Upcoming:")
            for ev in events[:10]:
                lines.append(
                    f"    - {ev.get('symbol', '—')} | {ev.get('type', '—')} | "
                    f"{ev.get('ex_date', '—')} | {ev.get('detail', '—')}"
                )

    if knowledge:
        answer = knowledge.get("answer_markdown")
        if answer:
            return str(answer)
        if knowledge.get("error"):
            return (
                f"No reliable Investopedia or Wikipedia source was found: {knowledge['error']}"
            )

    # 1. Snapshot
    if snap and not snap.get("error"):
        lines.append("▶ SNAPSHOT")
        price = snap.get("price") or (tech or {}).get("price")
        chg1d = snap.get("change_1d_pct")
        if price:
            chg_str = f"  ({chg1d:+.2f}%)" if chg1d else ""
            lines.append(f"  Price:  ₹{price:,.2f}{chg_str}")
        lines.append(f"  Stage:  {snap.get('stage', '—')}  (score: {snap.get('stage_score', '—')})")
        lines.append(f"  Signal: {snap.get('trading_signal', '—')}")
        rs = snap.get("rs_pct")
        lines.append(f"  RS:     {rs:+.0f}%" if rs is not None else "  RS:     —")
        lines.append(f"  Sector: {snap.get('sector', '—')}")
        lines.append(f"  MCap:   {snap.get('market_cap_cat', '—')}")
        if snap.get("narrative"):
            lines.append(f"  Note:   {snap['narrative'][:120]}")
        if snap.get("missing_evidence"):
            lines.append(f"  Missing evidence: {', '.join(snap.get('missing_evidence') or [])}")

    # 2. Technical Setup
    if tech and not tech.get("error"):
        lines.append("\n▶ TECHNICAL SETUP")
        if tech.get("technical_score") is not None:
            lines.append(
                f"  Derived score: {tech.get('technical_score')} "
                f"({tech.get('score_method', 'derived')})"
            )
        lines.append(f"  RSI:        {tech.get('rsi', '—')}")
        lines.append(f"  ADX:        {tech.get('adx', '—')}  (>25 = trending)")
        lines.append(f"  MACD:       {tech.get('macd', '—')}")
        lines.append(f"  Supertrend: {tech.get('supertrend', '—')}")
        ma_flags = []
        if tech.get("above_sma20"):
            ma_flags.append("▲ SMA20")
        if tech.get("above_sma50"):
            ma_flags.append("▲ SMA50")
        if tech.get("above_sma200"):
            ma_flags.append("▲ SMA200")
        lines.append(f"  MAs:        {' | '.join(ma_flags) or '— below key MAs'}")
        h52, l52, pct = tech.get("52w_high"), tech.get("52w_low"), tech.get("pct_from_52h")
        if h52:
            lines.append(
                f"  52W Range:  ₹{l52:,.0f} – ₹{h52:,.0f}  ({pct:+.1f}% from high)"
                if pct else ""
            )
        vr = tech.get("vol_ratio")
        lines.append(f"  Volume:     {vr:.1f}x avg" if vr else "")

    # 3. Sector Context
    if sec and not sec.get("error"):
        lines.append("\n▶ SECTOR CONTEXT")
        lines.append(f"  Sector:         {sec.get('sector', '—')}")
        lines.append(f"  Stocks in DB:   {sec.get('total_stocks', '—')}")
        lines.append(f"  Stage 2 count:  {sec.get('stage2_count', '—')}")
        lines.append(f"  Buy signals:    {sec.get('buy_signals', '—')}")
        lines.append(
            f"  Avg RS:         {sec.get('avg_rs_pct', '—'):+.1f}%"
            if sec.get("avg_rs_pct") is not None else ""
        )
        lines.append(
            f"  Avg 1M chg:     {sec.get('avg_1m_pct', '—'):+.2f}%"
            if sec.get("avg_1m_pct") is not None else ""
        )
        top5 = sec.get("top5_by_score", [])
        if top5:
            lines.append("  Top peers:      " + ", ".join(s["symbol"] for s in top5[:5]))

    # 3b. Fundamental evidence: PG cache -> Screener -> latest filing evidence
    if cached_financials and not cached_financials.get("error"):
        counts = cached_financials.get("section_counts") or {}
        lines.append("\n▶ FUNDAMENTAL EVIDENCE")
        lines.append(
            "  PG financial cache: "
            + " | ".join(
                f"{label} {counts.get(label, 0)}"
                for label in ("quarterly", "annual", "balance_sheet", "cash_flow")
            )
        )
        quarterly_rows = cached_financials.get("quarterly") or []
        if quarterly_rows:
            lines.append("  Latest quarterly rows:")
            for row in quarterly_rows[:2]:
                if not isinstance(row, dict):
                    continue
                period = row.get("period") or row.get("quarter") or row.get("date") or row.get("result_date") or "latest"
                metrics = []
                for label, keys in (
                    ("Revenue", ("revenue", "sales", "net_sales", "income")),
                    ("PAT", ("pat", "net_profit", "profit_after_tax")),
                    ("EPS", ("eps", "eps_basic", "basic_eps")),
                ):
                    value = next((row.get(key) for key in keys if row.get(key) is not None), None)
                    if value is not None:
                        metrics.append(f"{label}: {value}")
                lines.append(f"    - {period}" + (f" | {' | '.join(metrics)}" if metrics else ""))
        annual_rows = cached_financials.get("annual") or []
        if annual_rows:
            lines.append("  Latest annual rows:")
            for row in annual_rows[:2]:
                if not isinstance(row, dict):
                    continue
                period = row.get("period") or row.get("year") or row.get("financial_year") or "latest"
                metrics = []
                for label, keys in (
                    ("Sales", ("sales", "revenue", "net_sales")),
                    ("PAT", ("pat", "net_profit", "profit_after_tax")),
                    ("ROCE", ("roce", "roce_pct")),
                ):
                    value = next((row.get(key) for key in keys if row.get(key) is not None), None)
                    if value is not None:
                        metrics.append(f"{label}: {value}")
                lines.append(f"    - {period}" + (f" | {' | '.join(metrics)}" if metrics else ""))

    # 3c. Screener.in Fundamentals
    if scr_fund and not scr_fund.get("error"):
        ratios = scr_fund.get("ratios") or {}
        if ratios:
            lines.append("\n▶ FUNDAMENTAL RATIOS (screener.in)")
            key_order = [
                "Market Cap", "Current Price", "High / Low", "Stock P/E",
                "Book Value", "Dividend Yield", "ROCE", "ROE",
                "Face Value", "Industry PE", "Debt to equity",
                "PEG Ratio", "EPS", "Promoter holding",
            ]
            shown = 0
            for k in key_order:
                v = ratios.get(k)
                if v:
                    lines.append(f"  {k:<18} {v}")
                    shown += 1
            for k, v in ratios.items():
                if k in key_order or not v:
                    continue
                lines.append(f"  {k:<18} {v}")
                shown += 1
                if shown >= 18:
                    break

        quarterly = scr_fund.get("quarterly") or {}
        q_headers = quarterly.get("_headers") if isinstance(quarterly, dict) else None
        q_rows = (
            {k: v for k, v in (quarterly or {}).items() if k != "_headers"}
            if isinstance(quarterly, dict) else {}
        )
        if q_headers and q_rows:
            lines.append("\n▶ QUARTERLY RESULTS (₹ Cr — last 6 quarters)")
            lines.append(
                "  | Metric              | "
                + " | ".join(f"{h:>10}" for h in q_headers)
                + " |"
            )
            lines.append("  |" + "-" * 22 + "|" + ("-" * 12 + "|") * len(q_headers))
            priority = (
                "Sales", "Sales+", "Revenue", "Expenses", "Expenses+",
                "Operating Profit", "OPM %", "Net Profit", "Net Profit+", "EPS in Rs",
            )
            ordered = [k for k in priority if k in q_rows] + [k for k in q_rows if k not in priority]
            for metric in ordered[:10]:
                vals = q_rows.get(metric) or []
                cells = " | ".join(
                    f"{(v or '—'):>10}"
                    for v in (vals[:len(q_headers)] + [""] * (len(q_headers) - len(vals)))
                )
                lines.append(f"  | {metric[:18]:<18} | {cells} |")

        annual = scr_fund.get("annual_pl") or {}
        a_headers = annual.get("_headers") if isinstance(annual, dict) else None
        a_rows = (
            {k: v for k, v in (annual or {}).items() if k != "_headers"}
            if isinstance(annual, dict) else {}
        )
        if a_headers and a_rows:
            lines.append("\n▶ ANNUAL P&L (₹ Cr — last 5 years)")
            lines.append(
                "  | Metric              | "
                + " | ".join(f"{h:>10}" for h in a_headers)
                + " |"
            )
            lines.append("  |" + "-" * 22 + "|" + ("-" * 12 + "|") * len(a_headers))
            priority = (
                "Sales", "Sales+", "Revenue", "Expenses", "Expenses+",
                "Operating Profit", "OPM %", "Net Profit", "Net Profit+",
                "EPS in Rs", "Dividend Payout %",
            )
            ordered = [k for k in priority if k in a_rows] + [k for k in a_rows if k not in priority]
            for metric in ordered[:10]:
                vals = a_rows.get(metric) or []
                cells = " | ".join(
                    f"{(v or '—'):>10}"
                    for v in (vals[:len(a_headers)] + [""] * (len(a_headers) - len(vals)))
                )
                lines.append(f"  | {metric[:18]:<18} | {cells} |")

        lines.extend(_sales_eps_growth_lines(q_rows, a_rows))

        pros = scr_fund.get("pros") or []
        cons = scr_fund.get("cons") or []
        if pros or cons:
            lines.append("\n▶ SCREENER ANALYSIS")
            if pros:
                lines.append("  Pros:")
                for p in pros[:4]:
                    lines.append(f"    • {p}")
            if cons:
                lines.append("  Cons:")
                for c in cons[:4]:
                    lines.append(f"    • {c}")

        peers = scr_fund.get("peers") or []
        if peers:
            lines.append("\n▶ PEER COMPARISON")
            for p in peers[:5]:
                name = p.get("Name") or p.get("S.No.") or "—"
                pe = p.get("P/E") or p.get("PE") or "—"
                mcap = p.get("Mar Cap Rs.Cr.") or p.get("Mar Cap") or "—"
                roe = p.get("ROCE %") or p.get("ROE") or "—"
                lines.append(
                    f"  - {str(name)[:24]:<24} | P/E {pe:>8} | M-Cap {mcap:>10} | ROCE {roe:>6}"
                )

        shp = scr_fund.get("shareholding") or {}
        if shp:
            promo = shp.get("Promoters") or shp.get("Promoter")
            fii = shp.get("FIIs") or shp.get("FII")
            dii = shp.get("DIIs") or shp.get("DII")
            if any([promo, fii, dii]):
                lines.append("\n▶ SHAREHOLDING (latest)")
                if promo:
                    lines.append(f"  Promoters: {promo}")
                if fii:
                    lines.append(f"  FII:       {fii}")
                if dii:
                    lines.append(f"  DII:       {dii}")

        announcements = scr_fund.get("announcements") or []
        if announcements:
            lines.append("\n▶ RECENT FILINGS (BSE)")
            for a in announcements[:5]:
                title = (a.get("title") or "")[:80]
                url = a.get("url") or ""
                lines.append(f"  • {title}")
                if url:
                    lines.append(f"    {url}")

        src = scr_fund.get("source_url")
        if src:
            lines.append(f"\n  Source: {src}")

    if latest_results and not latest_results.get("error"):
        lines.append("\n▶ LATEST RESULTS EVIDENCE")
        lines.append(f"  Status: {latest_results.get('status', 'unknown')}")
        if latest_results.get("period"):
            lines.append(f"  Period: {latest_results.get('period')}")
        selected = latest_results.get("selected_filing") or {}
        if selected:
            lines.append(f"  Selected filing: {selected.get('title') or selected.get('url') or 'N/A'}")
            if selected.get("source"):
                lines.append(f"  Filing source: {selected.get('source')}")
        facts = latest_results.get("facts") or {}
        if facts:
            for label, key in (("Revenue", "revenue"), ("PAT", "pat"), ("EPS", "eps")):
                item = facts.get(key)
                if isinstance(item, dict):
                    lines.append(
                        f"  {label}: {item.get('value')} "
                        f"({item.get('period', 'latest')} · {item.get('source', 'source unavailable')})"
                    )
        missing = latest_results.get("missing_facts") or []
        if missing:
            lines.append("  Missing facts: " + ", ".join(str(item) for item in missing))
        summary = latest_results.get("summary")
        if summary:
            for line in str(summary).splitlines()[:4]:
                lines.append(f"  {line}")
        source_trail = latest_results.get("source_trail") or {}
        if source_trail:
            lines.append("  Filing source trail: " + " | ".join(f"{k}: {v}" for k, v in source_trail.items()))

    # 3d. Latest NSE / BSE corporate announcements
    if nse_ann and not nse_ann.get("error"):
        items = nse_ann.get("announcements") or nse_ann.get("results") or []
        if items:
            lines.append("\n▶ NSE/BSE ANNOUNCEMENTS")
            for a in items[:5]:
                title = (a.get("subject") or a.get("title") or "")[:90]
                date = a.get("date") or a.get("dt") or ""
                url = a.get("url") or a.get("link") or a.get("pdf") or ""
                lines.append(f"  • [{date}] {title}")
                if url:
                    lines.append(f"    {url}")

    # 4. Live market overview / Index / breadth
    if live and not live.get("error"):
        lines.append("\n▶ LIVE MARKET")
        indices = live.get("indices") or {}
        for index_name in (
            "NIFTY 50", "NIFTY BANK", "NIFTY MIDCAP SELECT",
            "NIFTY MIDCAP 50", "NIFTY MIDCAP 100",
        ):
            row = indices.get(index_name)
            if not row:
                continue
            last = row.get("last", row.get("close"))
            pct = row.get("pct_change", row.get("chg_pct"))
            if isinstance(last, (int, float)):
                pct_txt = f"  ({pct:+.2f}%)" if isinstance(pct, (int, float)) else ""
                lines.append(f"  {index_name}: {last:,.2f}{pct_txt}")
        adv_dec = live.get("adv_dec") or {}
        if adv_dec:
            lines.append(
                f"  Live breadth: {adv_dec.get('advances', '—')} advances / "
                f"{adv_dec.get('declines', '—')} declines"
            )
        if live.get("as_of") or live.get("source"):
            lines.append(
                f"  Source: {live.get('source', 'NSE live API')} | As of: {live.get('as_of', '—')}"
            )

        top_sectors = live.get("top_sectors") or []
        bottom_sectors = live.get("bottom_sectors") or []
        if (top_sectors or bottom_sectors) and intent in {"market_overview", "market_situation_assessment"}:
            lines.append("\n▶ SECTOR STRENGTH")
            if top_sectors:
                lines.append(
                    "  Leading sectors: "
                    + " | ".join(
                        f"{row.get('name', '—')} {float(row.get('pct_change') or 0):+.2f}%"
                        for row in top_sectors[:5]
                    )
                )
            if bottom_sectors:
                lines.append(
                    "  Weak sectors: "
                    + " | ".join(
                        f"{row.get('name', '—')} {float(row.get('pct_change') or 0):+.2f}%"
                        for row in bottom_sectors[:5]
                    )
                )

        index_rows = []
        for name, row in indices.items():
            pct = row.get("pct_change", row.get("chg_pct"))
            last = row.get("last", row.get("close"))
            if isinstance(pct, (int, float)):
                index_rows.append((name, pct, last))
        if index_rows and intent in {"market_overview", "market_situation_assessment"}:
            leaders = sorted(index_rows, key=lambda x: x[1], reverse=True)[:5]
            laggards = sorted(index_rows, key=lambda x: x[1])[:5]
            lines.append("\n▶ INDEX MOVERS")
            lines.append(
                "  Top indices: "
                + " | ".join(f"{name} {pct:+.2f}%" for name, pct, _ in leaders)
            )
            lines.append(
                "  Weak indices: "
                + " | ".join(f"{name} {pct:+.2f}%" for name, pct, _ in laggards)
            )

    if idx and not idx.get("error"):
        lines.append("\n▶ INDEX")
        lines.append(
            f"  {idx.get('index')}: {idx.get('close'):,.2f}  ({idx.get('chg_pct'):+.2f}%)"
        )
        t = idx.get("trend_10d", {})
        lines.append(
            f"  10d trend: {t.get('chg_pct', 0):+.2f}%  "
            f"({t.get('up_days', 0)}/{len(t.get('closes', [])) - 1} up-days)"
        )

    if brd and not brd.get("error"):
        if intent in {"market_overview", "market_situation_assessment", "market_situation"}:
            lines.extend(_market_breadth_verdict(live, brd))
        brd_index = brd.get("index") or brd.get("requested_index")
        if brd_index:
            lines.append(f"\n▶ {str(brd_index).upper()} BREADTH")
        elif live and not live.get("error"):
            lines.append("\n▶ DB UNIVERSE CONTEXT")
        else:
            lines.append("\n▶ MARKET BREADTH")
        lines.append(
            f"  Advances: {brd.get('advances')}  Declines: {brd.get('declines')}  "
            f"A/D ratio: {brd.get('ad_ratio')}"
        )
        rs_label = "Index avg RS" if brd_index else "Universe avg RS"
        lines.append(f"  {rs_label}: {brd.get('avg_rs_pct', 0):+.1f}%")
        if brd_index and brd.get("composition_count"):
            lines.append(
                f"  Coverage: {brd.get('matched_count', brd.get('total_stocks'))}/"
                f"{brd.get('composition_count')} constituents"
                + (
                    f" ({brd.get('coverage_pct'):.1f}%)"
                    if isinstance(brd.get("coverage_pct"), (int, float))
                    else ""
                )
            )
        for warning in brd.get("warnings") or []:
            lines.append(f"  Warning: {warning}")
        lines.extend(_market_rs_distribution_lines(brd))
        sd = brd.get("stage_distribution", {})
        if sd:
            stage_parts = [
                ("Stage 1", sd.get("STAGE_1", sd.get("stage_1", 0))),
                ("Stage 2", sd.get("STAGE_2", sd.get("stage_2", 0))),
                ("Stage 3", sd.get("STAGE_3", sd.get("stage_3", 0))),
                ("Stage 4", sd.get("STAGE_4", sd.get("stage_4", 0))),
            ]
            unknown = sd.get("UNKNOWN", sd.get("unknown"))
            if unknown:
                stage_parts.append(("Unknown", unknown))
            lines.append(
                "  Stage dist: "
                + " | ".join(f"{label}: {int(value or 0)}" for label, value in stage_parts)
            )
    elif brd and brd.get("error"):
        brd_index = brd.get("index") or brd.get("requested_index")
        label = f"{str(brd_index).upper()} BREADTH" if brd_index else "MARKET BREADTH"
        lines.append(f"\n▶ {label}")
        lines.append(f"  ERROR: {brd.get('error')}")

    if movers and not movers.get("error"):
        lines.append("\n▶ TOP STOCK MOVERS")
        gainers = movers.get("gainers") or []
        losers = movers.get("losers") or []
        if gainers:
            lines.append(
                "  Top gainers: "
                + " | ".join(
                    f"{row.get('symbol', '—')} {row.get('pct_change', 0):+.2f}%"
                    if isinstance(row.get("pct_change"), (int, float))
                    else f"{row.get('symbol', '—')} n/a"
                    for row in gainers[:5]
                )
            )
        if losers:
            lines.append(
                "  Top losers: "
                + " | ".join(
                    f"{row.get('symbol', '—')} {row.get('pct_change', 0):+.2f}%"
                    if isinstance(row.get("pct_change"), (int, float))
                    else f"{row.get('symbol', '—')} n/a"
                    for row in losers[:5]
                )
            )

    mtf_scan = _get(tool_results, "scan_mtf_aligned")
    if mtf_scan and not mtf_scan.get("error"):
        lines.append("\n▶ MULTI-TIMEFRAME CONFLUENCE")
        lines.append(
            f"  Direction: {mtf_scan.get('direction', '—')}  ·  "
            f"min_score: {mtf_scan.get('min_score', '—')}  ·  "
            f"timeframes: {','.join(mtf_scan.get('timeframes') or [])}  ·  "
            f"universe: {mtf_scan.get('universe_size', 0)}  ·  "
            f"matches: {mtf_scan.get('matches_total', 0)}"
        )
        top = mtf_scan.get("top") or []
        if top:
            lines.append("  Top aligned (score · verdict · aligned TFs):")
            for row in top[:10]:
                aligned = ",".join(row.get("aligned_tfs", []) or [])
                lines.append(
                    f"    {row.get('symbol', '—'):<14} "
                    f"{int(row.get('confluence_score', 0)):>3}  "
                    f"{row.get('verdict', '—'):<6}  "
                    f"[{aligned}]"
                )
        else:
            lines.append(
                "  No symbols met the confluence threshold; "
                "consider lowering min_score or widening universe."
            )

    # 4b. Global market assessment
    if glob and not glob.get("error"):
        lines.append("\n▶ GLOBAL MARKET ASSESSMENT")
        lines.append(f"  Risk regime: {glob.get('risk_regime', '—')}")
        lines.append(f"  As of:        {glob.get('as_of', '—')}")
        regions = glob.get("regions") or {}
        if regions:
            region_bits = []
            for name, data in regions.items():
                avg = data.get("avg_pct_change")
                avg_s = f"{avg:+.2f}%" if isinstance(avg, (int, float)) else "n/a"
                region_bits.append(f"{name}: {data.get('bias', '—')} ({avg_s})")
            lines.append("  Regions:      " + " | ".join(region_bits))
        moves = glob.get("moves") or {}
        if moves:
            key_moves = []
            for asset in [
                "S&P 500", "Nasdaq", "Hang Seng", "Nikkei 225",
                "Crude Oil", "DXY", "USDINR",
            ]:
                if asset in moves:
                    m = moves[asset]
                    key_moves.append(f"{asset} {m.get('pct_change', 0):+.2f}%")
            if key_moves:
                lines.append("  Key moves:    " + " | ".join(key_moves))
        readthrough = glob.get("india_readthrough") or []
        if readthrough:
            lines.append("  India read-through:")
            for item in readthrough[:5]:
                lines.append(f"    - {item}")
        watch = glob.get("watch_items") or []
        if watch:
            lines.append("  Watch:")
            for item in watch[:4]:
                lines.append(f"    - {item}")
        corrs = glob.get("correlations") or []
        if corrs:
            lines.append("  Correlation context:")
            for c in corrs[:5]:
                lines.append(
                    f"    - {c.get('asset')}: 30d {c.get('corr_30d')} | "
                    f"60d {c.get('corr_60d')} | {c.get('alert', '—')}"
                )

    # 5. Long-term growth research
    if growth_research:
        lines.append("\n▶ LONG-TERM GROWTH RESEARCH")
        if growth_research.get("error"):
            lines.append(f"  Error: {growth_research.get('error')}")
        else:
            indices_list = ", ".join(growth_research.get("indices") or [])
            lines.append(
                f"  Universe: {growth_research.get('index_scope', '—')}  |  "
                f"Indices: {indices_list or '—'}"
            )
            lines.append(
                f"  Constituents scanned: {growth_research.get('constituent_count', '—')}  |  "
                f"Snapshot: {growth_research.get('snapshot_date', '—')}"
            )
            lines.append(
                "  Candidate ranking uses enhanced fundamentals, financial strength, "
                "sales growth, investment score, and RS."
            )
            candidates = growth_research.get("candidates") or []
            if candidates:
                lines.append("\n  Top candidates:")
                for row in candidates[:10]:
                    rs = row.get("rs_pct")
                    rs_txt = f"{rs:+.0f}%" if isinstance(rs, (int, float)) else "—"
                    lines.append(
                        f"  {row.get('symbol', '—'):<12} "
                        f"{str(row.get('company_name') or '')[:24]:<24} "
                        f"Stage {row.get('stage', '—'):<8} Inv {row.get('investment_score', '—')} "
                        f"Fund {row.get('enhanced_fund_score', '—')} "
                        f"Growth {row.get('sales_growth', '—')} RS {rs_txt}"
                    )
            research_items = growth_research.get("research_items") or []
            if research_items:
                lines.append("\n  Fundamental evidence highlights:")
                for item in research_items[:5]:
                    if item.get("error"):
                        lines.append(
                            f"  - {item.get('symbol', '—')}: "
                            f"missing screener evidence ({item.get('error')})"
                        )
                        continue
                    ratios = []
                    for label, key in (("P/E", "stock_pe"), ("ROE", "roe"), ("ROCE", "roce")):
                        if item.get(key):
                            ratios.append(f"{label} {item.get(key)}")
                    lines.append(
                        f"  - {item.get('symbol', '—')}: "
                        + (" | ".join(ratios) if ratios else "ratios unavailable")
                    )
                    pros = item.get("pros") or []
                    cons = item.get("cons") or []
                    if pros:
                        lines.append("    Pros: " + " | ".join(str(p)[:80] for p in pros[:2]))
                    if cons:
                        lines.append("    Cons: " + " | ".join(str(c)[:80] for c in cons[:2]))
            warnings_list = growth_research.get("warnings") or []
            if warnings_list:
                lines.append("\n  Warnings:")
                for warning in warnings_list[:4]:
                    lines.append(f"  - {warning}")

    # 5b. Screener results
    if scr:
        lines.append(
            f"\n▶ SCREENER: {scr.get('screen_type', '').upper()}  ({scr.get('count', 0)} results)"
        )
        for s in (scr.get("results") or [])[:8]:
            rs_str = f"RS:{s['rs_pct']:+.0f}%" if s.get("rs_pct") is not None else ""
            lines.append(
                f"  {s['symbol']:<12}  ₹{s.get('price', 0):>8,.0f}  "
                f"{rs_str:<8}  {s.get('trading_signal', '—')}"
            )

    # 5c. PostgreSQL intraday setup and screeners
    if intra_setup and not intra_setup.get("error"):
        _sym = intra_setup.get("symbol", "—")
        _tf = intra_setup.get("timeframe", "—")
        _label = intra_setup.get("setup_label", "—")
        _score = intra_setup.get("score", "—")
        _price = intra_setup.get("latest_close")
        _ts = intra_setup.get("latest_timestamp", "—")
        _ind = intra_setup.get("indicators") or {}
        _levels = intra_setup.get("levels") or {}
        _pivots = _levels.get("pivot_levels") or {}
        _ema_lvl = _levels.get("ema_levels") or {}
        _sups = _levels.get("supports") or []
        _ress = _levels.get("resistances") or []
        _inv = intra_setup.get("invalidation_level")
        _targets = intra_setup.get("technical_target_zones") or []
        _signals = intra_setup.get("signals") or []
        _tp = intra_setup.get("trade_plan") or {}
        _ps = intra_setup.get("position_sizing") or {}
        _rr = intra_setup.get("risk_reward_frame") or {}

        def _pct_from(ref, val):
            if isinstance(ref, (int, float)) and isinstance(val, (int, float)) and ref > 0:
                return f"({(val - ref) / ref * 100:+.2f}%)"
            return ""

        lines.append("\n▶ INTRADAY SETUP")
        price_str = f"₹{_price:,.2f}" if isinstance(_price, (int, float)) else "—"
        lines.append(f"  Symbol:    {_sym}  |  Timeframe: {_tf}")
        lines.append(f"  Setup:     {_label}  |  Score: {_score}")
        lines.append(f"  Price:     {price_str}  |  As of: {_ts}")

        lines.append("  ── Key Levels ──")
        if _pivots.get("PP") is not None:
            lines.append(f"  Pivot (PP): ₹{_pivots['PP']:,.2f}")
        for lvl in ["R1", "R2", "R3"]:
            v = _pivots.get(lvl)
            if v is not None:
                lines.append(f"  {lvl}:        ₹{v:,.2f}  {_pct_from(_price, v)}")
        for lvl in ["S1", "S2", "S3"]:
            v = _pivots.get(lvl)
            if v is not None:
                lines.append(f"  {lvl}:        ₹{v:,.2f}  {_pct_from(_price, v)}")
        if _sups:
            lines.append(
                "  Supports:   "
                + " | ".join(
                    f"₹{s:,.2f}" if isinstance(s, (int, float)) else str(s)
                    for s in _sups[:4]
                )
            )
        if _ress:
            lines.append(
                "  Resistances:"
                + " | ".join(
                    f"₹{r:,.2f}" if isinstance(r, (int, float)) else str(r)
                    for r in _ress[:4]
                )
            )
        ema_parts = []
        for ek in ["ema9", "ema21", "ema50", "ema200"]:
            ev = _ema_lvl.get(ek) or _ind.get(ek)
            if isinstance(ev, (int, float)):
                ema_parts.append(f"{ek.upper()}: ₹{ev:,.2f}")
        if ema_parts:
            lines.append("  EMAs:       " + " | ".join(ema_parts))

        lines.append("  ── Targets & Invalidation ──")
        if len(_targets) > 0 and isinstance(_targets[0], (int, float)):
            lines.append(f"  T1:         ₹{_targets[0]:,.2f}  {_pct_from(_price, _targets[0])}")
        else:
            lines.append("  T1:         —")
        if len(_targets) > 1 and isinstance(_targets[1], (int, float)):
            lines.append(f"  T2:         ₹{_targets[1]:,.2f}  {_pct_from(_price, _targets[1])}")
        if isinstance(_inv, (int, float)):
            lines.append(f"  Invalidation (SL): ₹{_inv:,.2f}  {_pct_from(_price, _inv)}")
        else:
            lines.append("  Invalidation (SL): —")

        lines.append("  ── Indicators ──")
        rsi_str = f"{_ind['rsi']:.1f}" if isinstance(_ind.get("rsi"), (int, float)) else "—"
        macd_str = (
            f"{_ind['macd_hist']:.4f}" if isinstance(_ind.get("macd_hist"), (int, float)) else "—"
        )
        st_map = {1: "Bullish", -1: "Bearish"}
        st_str = st_map.get(_ind.get("supertrend_dir"), "—")
        lines.append(f"  RSI: {rsi_str} | MACD hist: {macd_str} | Supertrend: {st_str}")
        ind_extra = []
        if isinstance(_ind.get("volume_ratio"), (int, float)):
            ind_extra.append(f"Vol ratio: {_ind['volume_ratio']:.1f}x")
        if isinstance(_ind.get("atr"), (int, float)):
            ind_extra.append(f"ATR: ₹{_ind['atr']:,.2f}")
        if isinstance(_ind.get("bb_pct"), (int, float)):
            ind_extra.append(f"BB%: {_ind['bb_pct']:.0f}%")
        if ind_extra:
            lines.append("  " + " | ".join(ind_extra))

        active_sigs = [s for s in _signals if s.get("entry") is not None]
        if active_sigs:
            lines.append("  ── Strategy Signals ──")
            for sig in active_sigs[:5]:
                s_name = sig.get("strategy", "—")
                s_dir = sig.get("setup_label", sig.get("direction", "—"))
                s_entry = sig.get("entry")
                s_tgt = sig.get("target")
                s_sl = sig.get("stoploss")
                s_rr = sig.get("rr")
                s_str = sig.get("strength", "")
                parts = [f"{s_name} ({s_dir}):"]
                if isinstance(s_entry, (int, float)):
                    parts.append(f"entry ₹{s_entry:,.2f}")
                if isinstance(s_tgt, (int, float)):
                    parts.append(f"target ₹{s_tgt:,.2f}")
                if isinstance(s_sl, (int, float)):
                    parts.append(f"SL ₹{s_sl:,.2f}")
                if isinstance(s_rr, (int, float)):
                    parts.append(f"R:R {s_rr:.1f}")
                if s_str:
                    parts.append(f"[{s_str}]")
                lines.append("  " + " | ".join(parts))
                note = sig.get("note")
                if note:
                    lines.append(f"    {note}")

        if _tp and _tp.get("direction"):
            lines.append(f"  ── Trade Plan (Educational) — {_tp['direction']} ──")
            lines.append("  Entry confirmations:")
            for c in _tp.get("entry_confirmations", []):
                lines.append(f"    • {c}")
            so = _tp.get("scale_out", [])
            if so:
                lines.append("  Scale-out plan:")
                for s in so:
                    lines.append(f"    • {s}")
            inv_act = _tp.get("invalidation_action")
            if inv_act:
                lines.append(f"  Invalidation: {inv_act}")

        if _ps and not _ps.get("error"):
            budget = _ps.get("risk_per_trade", 5000)
            lines.append(
                f"  ── Position Sizing (Educational, ₹{budget:,.0f} risk budget) ──"
            )
            lines.append(f"  Risk/share:  ₹{_ps.get('risk_per_share', 0):,.2f}")
            cash = _ps.get("cash") or {}
            if cash.get("shares"):
                lines.append(
                    f"  Cash/Equity: {cash['shares']:,} shares "
                    f"(capital ~₹{cash.get('capital_required', 0):,.0f})"
                )
            fut = _ps.get("futures")
            if fut:
                lines.append(
                    f"  Futures:     {fut['lots']} lot(s) x {fut['lot_size']} = "
                    f"{fut['units']} units "
                    f"(risk ₹{fut['risk_per_lot']:,.0f}/lot, "
                    f"margin ~₹{fut['approx_margin_per_lot']:,.0f}/lot)"
                )
            opt_note = _ps.get("options_note")
            if opt_note:
                lines.append(f"  Options:     {opt_note}")

        if _rr and _rr.get("risk_per_share"):
            lines.append("  ── Risk-Reward Frame ──")
            lines.append(f"  Risk/share:  ₹{_rr['risk_per_share']:,.2f}")
            if _rr.get("t1_rr") is not None:
                lines.append(
                    f"  T1 R:R       1:{_rr['t1_rr']:.1f}  "
                    f"(₹{_rr.get('rupee_risk', 0):,.0f} risk → "
                    f"₹{_rr.get('t1_rupee_reward', 0):,.0f} reward)"
                )
            if _rr.get("t2_rr") is not None:
                lines.append(
                    f"  T2 R:R       1:{_rr['t2_rr']:.1f}  "
                    f"(₹{_rr.get('rupee_risk', 0):,.0f} risk → "
                    f"₹{_rr.get('t2_rupee_reward', 0):,.0f} reward)"
                )

        lines.append(
            "  ━━━ Research setup only; not a buy/sell recommendation. Not SEBI registered. ━━━"
        )

    if intra_levels and not intra_levels.get("error"):
        lines.append("\n▶ INTRADAY LEVELS")
        lines.append(f"  Symbol:      {intra_levels.get('symbol', '—')}")
        lines.append(f"  Timeframe:   {intra_levels.get('timeframe', '—')}")
        lines.append(f"  Price:       ₹{intra_levels.get('latest_close', '—')}")
        lines.append(f"  Supports:    {intra_levels.get('supports') or '—'}")
        lines.append(f"  Resistances: {intra_levels.get('resistances') or '—'}")
        lines.append(f"  Pivot:       {intra_levels.get('pivot', '—')}")

    if intra_ind and not intra_ind.get("error"):
        lines.append("\n▶ INTRADAY INDICATORS")
        ind = intra_ind.get("indicators") or {}
        lines.append(f"  Symbol:      {intra_ind.get('symbol', '—')}")
        lines.append(f"  Timeframe:   {intra_ind.get('timeframe', '—')}")
        lines.append(f"  Score:       {intra_ind.get('score', '—')}")
        lines.append(f"  RSI:         {ind.get('rsi', '—')}")
        lines.append(f"  MACD hist:   {ind.get('macd_hist', '—')}")
        lines.append(f"  Supertrend:  {ind.get('supertrend_dir', '—')}")

    if nse_intraday and not nse_intraday.get("error"):
        lines.append("\n▶ NSE LIVE SNAPSHOT")
        lines.append(f"  Symbol:      {nse_intraday.get('symbol', '—')}")
        lines.append(f"  Source:      {nse_intraday.get('source', 'NSE website')}")
        lines.append(f"  As of:       {nse_intraday.get('as_of', '—')}")
        lines.append(f"  Last price:  ₹{nse_intraday.get('last_price', '—')}")
        if nse_intraday.get("pct_change") is not None:
            lines.append(f"  Change:      {nse_intraday.get('pct_change')}%")
        lines.append(
            f"  Day range:   {nse_intraday.get('day_low', '—')} – "
            f"{nse_intraday.get('day_high', '—')}"
        )
        if nse_intraday.get("vwap") is not None:
            lines.append(f"  VWAP:        ₹{nse_intraday.get('vwap')}")
        lines.append("  Framing:     NSE website live snapshot; not a full intraday candle series.")

    if (
        intra_legacy
        and not intra_legacy.get("error")
        and (
            (intra_setup and intra_setup.get("error"))
            or (intra_levels and intra_levels.get("error"))
            or not (intra_setup or intra_levels or intra_ind)
        )
    ):
        bars_error = (
            (intra_setup or {}).get("error")
            or (intra_levels or {}).get("error")
            or "PostgreSQL intraday bars unavailable"
        )
        lines.append("\n▶ INTRADAY FALLBACK ANALYSIS")
        lines.append(f"  PostgreSQL intraday bars unavailable: {bars_error}")
        lines.append(
            f"  Fallback source: "
            f"{intra_legacy.get('source') or intra_legacy.get('data_source') or 'legacy intraday engine'}"
        )
        lines.append(f"  Symbol:      {intra_legacy.get('symbol', '—')}")
        lines.append(f"  Interval:    {intra_legacy.get('interval', '—')}")
        lines.append(f"  Session:     {intra_legacy.get('session', '—')}")
        lines.append(f"  Price:       ₹{intra_legacy.get('close', '—')}")
        lines.append(f"  Bias:        {intra_legacy.get('bias', '—')}")
        if intra_legacy.get("candles") is not None:
            lines.append(f"  Candles:     {intra_legacy.get('candles')}")
        reason = intra_legacy.get("reason") or intra_legacy.get("note")
        if reason:
            lines.append(f"  Note:        {reason}")
        key_levels = intra_legacy.get("key_levels") or intra_legacy.get("approx_levels") or {}
        if key_levels:
            supports = key_levels.get("supports") or [
                key_levels.get("support_20d_low"), key_levels.get("prev_day_low")
            ]
            resistances = key_levels.get("resistances") or [
                key_levels.get("resistance_20d_high"), key_levels.get("prev_day_high")
            ]
            supports = [v for v in supports if v is not None]
            resistances = [v for v in resistances if v is not None]
            lines.append(f"  Supports:    {supports or '—'}")
            lines.append(f"  Resistances: {resistances or '—'}")
            lines.append(
                f"  Pivot:       "
                f"{key_levels.get('pivot') or key_levels.get('prev_day_close') or '—'}"
            )
        ind = intra_legacy.get("indicators") or {}
        if ind:
            lines.append(
                f"  Indicators:  RSI {ind.get('rsi', '—')} | "
                f"MACD hist {ind.get('macd_hist', '—')} | "
                f"Supertrend dir {ind.get('supertrend_dir', '—')}"
            )
        buy_sigs = intra_legacy.get("buy_signals") or []
        sell_sigs = intra_legacy.get("sell_signals") or []
        watch = intra_legacy.get("watch_alerts") or []
        if buy_sigs or sell_sigs or watch:
            lines.append(
                f"  Signals:     {len(buy_sigs)} long research setups | "
                f"{len(sell_sigs)} short research setups | {len(watch)} watch alerts"
            )
            for sig in (buy_sigs + sell_sigs + watch)[:5]:
                bits = [str(sig.get("strategy", "setup"))]
                if sig.get("entry") is not None:
                    bits.append(f"entry {sig.get('entry')}")
                if sig.get("target") is not None:
                    bits.append(f"target {sig.get('target')}")
                if sig.get("stoploss") is not None:
                    bits.append(f"invalidation {sig.get('stoploss')}")
                lines.append("    - " + " | ".join(bits))
        lines.append(
            "  Framing:     Research-only fallback analysis; not a buy/sell recommendation."
        )

    if intra_screen and not intra_screen.get("error"):
        lines.append(
            f"\n▶ INTRADAY SCREENER: {intra_screen.get('screen_type', '').upper()} "
            f"({intra_screen.get('count', 0)} results)"
        )
        for row in (intra_screen.get("results") or [])[:10]:
            lines.append(
                f"  {row.get('symbol', '—'):<12} {row.get('setup_label', '—'):<12} "
                f"score {row.get('score', '—')} price ₹{row.get('price', '—')} "
                f"S {row.get('support', '—')} R {row.get('resistance', '—')}"
            )
        lines.append("  Framing: Research-only setup labels; not buy/sell recommendations.")

    if intra_index_scan and not intra_index_scan.get("error"):
        buy = intra_index_scan.get("top_buy") or intra_index_scan.get("buy_signals") or []
        sell = intra_index_scan.get("top_sell") or intra_index_scan.get("sell_signals") or []
        lines.append("\n▶ INTRADAY INDEX SCAN")
        lines.append(f"  Index:       {intra_index_scan.get('index', '—')}")
        lines.append(
            f"  Timeframe:   "
            f"{intra_index_scan.get('interval') or intra_index_scan.get('timeframe') or '—'}"
        )
        if intra_index_scan.get("data_source"):
            lines.append(f"  Source:      {intra_index_scan.get('data_source')}")
        lines.append(
            f"  Signals:     {len(buy)} long research setups | {len(sell)} short research setups"
        )
        for label, rows in (("Long", buy), ("Short", sell)):
            if not rows:
                continue
            lines.append(f"  {label} setups:")
            for sig in rows[:10]:
                bits = [str(sig.get("symbol", "—"))]
                if sig.get("strategy"):
                    bits.append(str(sig.get("strategy")))
                if sig.get("entry") is not None:
                    bits.append(f"entry {sig.get('entry')}")
                if sig.get("target") is not None:
                    bits.append(f"target {sig.get('target')}")
                invalidation = sig.get("stoploss", sig.get("invalidation_level"))
                if invalidation is not None:
                    bits.append(f"invalidation {invalidation}")
                if sig.get("rr") is not None:
                    bits.append(f"R:R {sig.get('rr')}")
                lines.append("    - " + " | ".join(bits))

    if intra_symbol_scan and not intra_symbol_scan.get("error"):
        buy = intra_symbol_scan.get("top_buy") or intra_symbol_scan.get("buy_signals") or []
        sell = intra_symbol_scan.get("top_sell") or intra_symbol_scan.get("sell_signals") or []
        symbols_scanned = intra_symbol_scan.get("symbols_scanned") or []
        lines.append("\n▶ INTRADAY SYMBOL SCAN")
        lines.append(
            f"  Symbols:     "
            f"{', '.join(symbols_scanned[:20]) if symbols_scanned else '—'}"
        )
        lines.append(
            f"  Timeframe:   "
            f"{intra_symbol_scan.get('interval') or intra_symbol_scan.get('timeframe') or '—'}"
        )
        if intra_symbol_scan.get("data_source"):
            lines.append(f"  Source:      {intra_symbol_scan.get('data_source')}")
        lines.append(
            f"  Signals:     {len(buy)} long research setups | {len(sell)} short research setups"
        )
        for label, rows in (("Long", buy), ("Short", sell)):
            if not rows:
                continue
            lines.append(f"  {label} setups:")
            for sig in rows[:10]:
                bits = [str(sig.get("symbol", "—"))]
                if sig.get("strategy"):
                    bits.append(str(sig.get("strategy")))
                if sig.get("entry") is not None:
                    bits.append(f"entry {sig.get('entry')}")
                if sig.get("target") is not None:
                    bits.append(f"target {sig.get('target')}")
                invalidation = sig.get("stoploss", sig.get("invalidation_level"))
                if invalidation is not None:
                    bits.append(f"invalidation {invalidation}")
                if sig.get("rr") is not None:
                    bits.append(f"R:R {sig.get('rr')}")
                lines.append("    - " + " | ".join(bits))
        lines.append("  Framing: Research-only intraday scan; not buy/sell recommendations.")

    # 6. Catalysts
    if cat and cat.get("results"):
        lines.append(
            "\n▶ LATEST CATALYSTS (web search results — use EXACT URLs below, never write 'Read more')"
        )
        for r in cat["results"][:5]:
            title = r.get("title", "")[:100]
            url = r.get("url", "")
            snippet = r.get("snippet", "")[:120]
            lines.append(f"  TITLE:   {title}")
            if url:
                lines.append(f"  URL:     {url}")
            if snippet:
                lines.append(f"  SNIPPET: {snippet}")
            lines.append("")

    # 7. Risks / Watch
    risks: list[str] = []
    if tech and not tech.get("error"):
        if tech.get("rsi", 50) > 75:
            risks.append("RSI overbought (>75)")
        if not tech.get("above_sma50"):
            risks.append("Price below SMA50")
        if tech.get("adx", 0) < 20:
            risks.append("ADX < 20 — weak trend")
    if snap and not snap.get("error"):
        if snap.get("stage") not in ("STAGE_2", None) and snap.get("stage"):
            risks.append(f"Not in Stage 2 ({snap.get('stage')})")
    if risks:
        lines.append("\n▶ RISKS / WATCH")
        for r in risks:
            lines.append(f"  ⚠ {r}")

    missing_tools = [
        tr["tool"]
        for tr in tool_results
        if isinstance(tr.get("result"), dict) and tr["result"].get("error")
    ]
    if missing_tools:
        lines.append("\n▶ MISSING EVIDENCE")
        lines.append("  Missing evidence: " + ", ".join(dict.fromkeys(missing_tools)))
        for tr in tool_results:
            if tr.get("tool") != "resolve_symbol" or not isinstance(tr.get("result"), dict):
                continue
            if tr["result"].get("symbol") and not tr["result"].get("error"):
                continue
            candidates = tr["result"].get("candidates") or []
            if candidates:
                bad_query = (
                    tr["result"].get("query")
                    or tr.get("args", {}).get("query")
                    or "requested symbol"
                )
                lines.append(
                    f"  Symbol not found: {bad_query}. "
                    f"Did you mean: {', '.join(str(c) for c in candidates[:5])}?"
                )
        lines.append(
            "  No unsupported technical, fundamental, catalyst, or sector conclusion was "
            "inferred from missing data."
        )

    # Intraday / data health
    intra_health = _get(tool_results, "get_intraday_source_health")
    data_health = _get(tool_results, "get_data_health")
    if intent in ("intraday_health", "data_health"):
        src = intra_health or data_health or {}
        if src and not src.get("error"):
            lines.append(f"## Intraday Data Health  —  {src.get('source', 'PostgreSQL')}")
            lines.append(f"Overall status: **{src.get('overall_status', '—')}**")
            lines.append(f"Database: `{src.get('db_path', '—')}`")
            tables = src.get("tables") or {}
            if tables:
                lines.append("\n| Table | Status | Rows | Latest | Age (min) |")
                lines.append("|-------|--------|------|--------|-----------|")
                for tname, tinfo in tables.items():
                    if isinstance(tinfo, dict):
                        lines.append(
                            f"| {tname} | {tinfo.get('status', '—')} "
                            f"| {tinfo.get('rows', '—'):,} "
                            f"| {tinfo.get('latest_timestamp', '—')} "
                            f"| {tinfo.get('age_minutes', '—')} |"
                        )
        elif src:
            lines.append(f"## Data Health\n- Error: {src.get('error', 'unknown')}")

    # ── F&O overlay (when fno tools ran alongside a non-fno primary intent) ──
    fno_chain    = _get(tool_results, "get_options_chain") or _get(tool_results, "get_option_chain")
    fno_futures  = _get(tool_results, "get_futures_analysis")
    fno_strategy = _get(tool_results, "get_strategy_recommendations")

    if fno_overview and intent != "fno_overview":
        _fsym = fno_overview.get("symbol") or "—"
        lines.append(f"\n━━━ {_fsym} — F&O Overview ━━━")
        lines.append("▶ OPTION CHAIN")
        _chain = fno_overview.get("option_chain") or {}
        if _chain.get("status") == "missing" or _chain.get("error"):
            lines.append(f"  ERROR: {_chain.get('error') or 'option-chain evidence missing'}")
        else:
            lines.append(f"  PCR: {fno_overview.get('pcr', '—')} | Max pain: {fno_overview.get('max_pain', '—')}")
        lines.append("▶ FUTURES BASIS & CARRY")
        _fut = fno_overview.get("futures") or {}
        if _fut.get("status") == "missing" or _fut.get("error"):
            lines.append(f"  ERROR: {_fut.get('error') or 'futures evidence missing'}")
        else:
            lines.append(f"  Basis: {fno_overview.get('basis', '—')} | Cost of carry: {fno_overview.get('cost_of_carry', '—')}")
        _rec = fno_overview.get("recommendation") or {}
        if _rec:
            lines.append("▶ STRATEGY CONTEXT")
            if _rec.get("status") == "blocked":
                lines.append(f"  Blocked: {_rec.get('reason')}")
            else:
                lines.append(f"  Strategy: {_rec.get('strategy', '—')}")

    if fno_chain or fno_futures or fno_strategy:
        _fsym = (
            (fno_chain or {}).get("symbol")
            or (fno_futures or {}).get("symbol")
            or (fno_strategy or {}).get("symbol")
            or "NIFTY"
        )
        lines.append(f"━━━ {_fsym} — F&O Overview ━━━")
        if fno_chain and not fno_chain.get("error"):
            _pcr = fno_chain.get("pcr")
            _pcr_text = (
                f"OI {_pcr.get('oi', '—')} | Volume {_pcr.get('volume', '—')} | {_pcr.get('signal', '—')}"
                if isinstance(_pcr, dict)
                else str(_pcr if _pcr is not None else "—")
            )
            lines.append(f"\n▶ OPTION CHAIN")
            lines.append(f"  PCR: {_pcr_text} | Max pain: {fno_chain.get('max_pain', '—')}")
        elif fno_chain:
            lines.append(f"\n▶ OPTION CHAIN\n  ERROR: {fno_chain.get('error')}")
        if fno_futures and not fno_futures.get("error"):
            lines.append(f"\n▶ FUTURES")
            lines.append(f"  Basis: {fno_futures.get('basis', '—')} | Cost of carry: {fno_futures.get('cost_of_carry', '—')}")

    # Source trail
    lines.append("\n▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))

    lines.append(f"\n{FOOTER}")
    return "\n".join(l for l in lines if l.strip() != "")
