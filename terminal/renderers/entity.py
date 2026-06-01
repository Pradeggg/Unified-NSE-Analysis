"""Renderer for the entity_topic_command intent."""

from terminal.renderers._base import _get, _source_trail_lines, FOOTER


def render(tool_results: list[dict]) -> str:
    """Render the entity_topic_command intent."""
    from terminal.renderers.stock_results import _render_stock_results_block

    deep = _get(tool_results, "deep_search")
    fno_chain = _get(tool_results, "get_options_chain") or _get(tool_results, "get_option_chain")
    latest_results = _get(tool_results, "get_latest_results")
    scr_fund = _get(tool_results, "scrape_screener_in")
    nse_ann = _get(tool_results, "search_nse_announcements")
    bse_filings = _get(tool_results, "search_bse_filings")
    concalls = _get(tool_results, "search_concall_transcripts")

    symbol = ""
    for tr in tool_results:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        args = tr.get("args") if isinstance(tr.get("args"), dict) else {}
        symbol = str(result.get("symbol") or args.get("symbol") or symbol or "").upper()

    lines: list[str] = []
    lines.append(f"━━━ {symbol or 'Entity'} — Command Assessment Result ━━━")

    if deep is not None:
        lines.append("")
        lines.append("▶ DEEP SEARCH")
        if deep.get("error"):
            lines.append(f"  Error: {deep.get('error')}")
        else:
            count = len(deep.get("results") or deep.get("items") or [])
            lines.append(f"  Symbol: {symbol}")
            lines.append(f"  Results: {count}")
            lines.append("  Framing: Entity and topic were resolved before routing.")

    if fno_chain is not None:
        lines.append("")
        lines.append("▶ OPTIONS")
        if fno_chain.get("error"):
            lines.append(f"  Error: {fno_chain.get('error')}")
        else:
            lines.append(f"  Symbol: {fno_chain.get('symbol', symbol)}")
            lines.append(f"  PCR: {fno_chain.get('pcr', 'n/a')}")
            lines.append(f"  Max pain: {fno_chain.get('max_pain', 'n/a')}")

    if latest_results is not None:
        lines.append("")
        lines.append("▶ Latest Results Evidence")
        lines.append(f"  Status: {latest_results.get('status', 'unknown')}")
        lines.append(f"  Period: {latest_results.get('period', 'latest')}")
        selected = latest_results.get("selected_filing") or {}
        if selected:
            lines.append(
                f"  Selected filing: {selected.get('title') or selected.get('url') or 'N/A'}"
            )
        facts = latest_results.get("facts") or {}
        for label, key in (("Revenue", "revenue"), ("PAT", "pat"), ("EPS", "eps")):
            item = facts.get(key)
            if item:
                lines.append(f"  {label}: {item.get('value')} ({item.get('period', 'latest')})")
        missing = latest_results.get("missing_facts") or []
        if missing:
            lines.append(f"  Missing facts: {', '.join(missing)}")
        if latest_results.get("summary"):
            lines.append("  Summary:")
            for line in str(latest_results.get("summary")).splitlines()[:6]:
                lines.append(f"    {line}")

    if scr_fund is not None and (nse_ann is not None or bse_filings is not None or concalls is not None):
        lines.append("")
        _render_stock_results_block(symbol, lines, tool_results)

    lines.append("")
    lines.append("▶ SOURCE TRAIL")
    for tr in tool_results:
        result = tr.get("result") if isinstance(tr.get("result"), dict) else {}
        status = f"ERROR: {result.get('error')}" if result.get("error") else "ok"
        lines.append(f"  {tr.get('tool')}: {status}")
        if tr.get("tool") == "get_latest_results" and isinstance(result.get("source_trail"), dict):
            for sub_tool, sub_status in result["source_trail"].items():
                lines.append(f"  {sub_tool}: {sub_status}")

    lines.append(f"\n{FOOTER}")
    return "\n".join(lines)
