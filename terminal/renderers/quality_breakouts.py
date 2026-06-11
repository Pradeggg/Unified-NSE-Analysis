"""Renderer for the quality-breakouts composite screener."""
from __future__ import annotations


def _payload(tool_results: list[dict]) -> dict:
    for trace in tool_results or []:
        if trace.get("tool") == "run_quality_breakout_screener" and isinstance(trace.get("result"), dict):
            return trace["result"]
    return {}


def render(tool_results: list[dict]) -> str:
    data = _payload(tool_results)
    if not data:
        return "QUALITY BREAKOUTS\n\nNo quality-breakouts payload was returned."

    lines: list[str] = [
        "QUALITY BREAKOUTS",
        f"Snapshot: {data.get('snapshot_date') or 'unknown'}",
        f"Mode: {data.get('mode', 'balanced')}",
        "",
        "Execution Trail",
    ]
    counts = data.get("source_counts") or {}
    for key in ("new_highs", "momentum_52w", "tight_range", "breakouts"):
        lines.append(f"- {key}: {counts.get(key, 0)}")
    lines.append(f"- merged unique: {data.get('merged_count', 0)}")
    lines.append(f"- quality passed: {data.get('passed_count', 0)}")
    lines.append("")

    rows = data.get("results") or []
    if rows:
        lines.append("| Symbol | Setups | Stage | Signal | RS | RSI | Fund | Invest | Score | Sector |")
        lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|---|")
        for row in rows[:15]:
            lines.append(
                "| {symbol} | {setups} | {stage} | {signal} | {rs:.1f} | {rsi:.1f} | {fund:.0f} | {invest:.0f} | {score:.1f} | {sector} |".format(
                    symbol=row.get("symbol", ""),
                    setups=",".join(row.get("setup_tags") or []),
                    stage=row.get("stage", ""),
                    signal=row.get("trading_signal", ""),
                    rs=float(row.get("rs") or row.get("relative_strength") or 0),
                    rsi=float(row.get("rsi") or 0),
                    fund=float(row.get("enhanced_fund_score") or 0),
                    invest=float(row.get("investment_score") or 0),
                    score=float(row.get("composite_score") or 0),
                    sector=row.get("sector", ""),
                )
            )
        lines.append("")
        lines.append("Reasons")
        for row in rows[:15]:
            reason = ", ".join(row.get("reason_tags") or [])
            risks = ", ".join(row.get("risk_flags") or []) or "none"
            lines.append(f"- {row.get('symbol')}: {reason}; risk: {risks}")
    else:
        lines.append("No qualifying candidates.")

    tv = data.get("tradingview_symbols") or []
    if tv:
        lines.append("")
        lines.append("TradingView")
        lines.append("```text")
        lines.extend(tv)
        lines.append("```")

    lines.append("")
    lines.append("Research-only scan. Not investment advice.")
    return "\n".join(lines)

