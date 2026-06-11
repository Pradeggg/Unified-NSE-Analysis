"""Renderer for bare-symbol quick stock analysis."""

from __future__ import annotations

from terminal.renderers._base import FOOTER, _get


def _fmt_money(value) -> str:
    if value is None:
        return "n/a"
    try:
        return f"Rs {float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value, *, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.2f}%"


def _fmt_num(value) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _yes_no(value) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"


def render(tool_results: list[dict]) -> str:
    data = _get(tool_results, "get_symbol_quick_analysis") or {}
    symbol = data.get("symbol") or "SYMBOL"
    company = data.get("company_name") or symbol

    lines: list[str] = [f"━━━ {symbol} - QUICK STOCK ANALYSIS ━━━"]
    if data.get("error"):
        lines.append("")
        lines.append("▶ ERROR")
        lines.append(f"  {data.get('error')}")
        lines.append("")
        lines.append("▶ SOURCE TRAIL")
        lines.append("  get_symbol_quick_analysis: ERROR")
        lines.append("")
        lines.append(FOOTER)
        return "\n".join(lines)

    lines.append(f"Company: {company}")
    if data.get("as_of"):
        lines.append(f"As of: {data.get('as_of')}")

    lines.append("")
    lines.append("▶ CURRENT READ")
    lines.append(
        "  "
        + " | ".join(
            [
                f"Price {_fmt_money(data.get('price'))}",
                f"1D {_fmt_pct(data.get('chg_pct'))}",
                f"Stage {data.get('stage') or 'n/a'}",
                f"Signal {data.get('trading_signal') or 'n/a'}",
            ]
        )
    )
    lines.append(
        "  "
        + " | ".join(
            [
                f"Technical score {_fmt_num(data.get('technical_score'))}",
                f"RSI {_fmt_num(data.get('rsi'))}",
                f"RS {_fmt_pct(data.get('relative_strength'))}",
                f"Sector {data.get('sector') or 'n/a'}",
            ]
        )
    )

    lines.append("")
    lines.append("▶ INTERPRETATION")
    ma_bits = [
        f"above 20DMA: {_yes_no(data.get('above_sma20'))}",
        f"above 50DMA: {_yes_no(data.get('above_sma50'))}",
        f"above 200DMA: {_yes_no(data.get('above_sma200'))}",
    ]
    lines.append("  " + " | ".join(ma_bits))
    breakout = data.get("breakout_pct_vs_prior_20d_high")
    if breakout is not None:
        lines.append(f"  Distance vs prior 20D high: {_fmt_pct(breakout)}")
    if data.get("adx") is not None:
        lines.append(f"  ADX: {_fmt_num(data.get('adx'))}")

    lines.append("")
    lines.append("▶ LEVELS")
    lines.append(
        "  "
        + " | ".join(
            [
                f"Support {_fmt_money(data.get('support'))}",
                f"Resistance {_fmt_money(data.get('resistance'))}",
                f"Risk stop {_fmt_money(data.get('stop_loss'))}",
            ]
        )
    )
    lines.append(
        "  "
        + " | ".join(
            [
                f"SMA20 {_fmt_money(data.get('sma20'))}",
                f"SMA50 {_fmt_money(data.get('sma50'))}",
                f"SMA200 {_fmt_money(data.get('sma200'))}",
            ]
        )
    )

    lines.append("")
    lines.append("▶ VOLUME")
    lines.append(
        "  "
        + " | ".join(
            [
                f"Last {_fmt_num(data.get('volume_last'))}",
                f"20D avg {_fmt_num(data.get('volume_avg_20d'))}",
                f"Ratio {_fmt_num(data.get('volume_ratio'))}x",
            ]
        )
    )

    lines.append("")
    lines.append("▶ FUNDAMENTALS")
    lines.append(
        "  "
        + " | ".join(
            [
                f"Fund score {_fmt_num(data.get('fundamental_score'))}",
                f"Investment score {_fmt_num(data.get('investment_score'))}",
                f"Financial strength {data.get('financial_strength') or 'n/a'}",
            ]
        )
    )

    fno = data.get("fno") or {}
    lines.append("")
    lines.append("▶ F&O")
    if fno.get("available"):
        parts = [
            f"Signal {fno.get('fno_signal') or 'n/a'}",
            f"Buildup {fno.get('buildup') or 'n/a'}",
            f"PCR {_fmt_num(fno.get('pcr'))}",
            f"OI 5D {_fmt_pct(fno.get('oi_change_5d'))}",
        ]
        if fno.get("snapshot_date"):
            parts.append(f"As of {fno.get('snapshot_date')}")
        lines.append("  " + " | ".join(parts))
    else:
        lines.append("  No F&O signal available for this symbol.")

    lines.append("")
    lines.append("▶ VERDICT")
    lines.append(f"  {data.get('verdict') or 'Insufficient evidence for a clean quick verdict.'}")
    missing = data.get("missing_evidence") or []
    if missing:
        lines.append("  Missing evidence: " + ", ".join(str(item) for item in missing))

    source_trail = data.get("source_trail") or {}
    lines.append("")
    lines.append("▶ SOURCE TRAIL")
    if source_trail:
        for source, status in source_trail.items():
            lines.append(f"  {source}: {status}")
    else:
        lines.append("  get_symbol_quick_analysis: ok")
    lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines)
