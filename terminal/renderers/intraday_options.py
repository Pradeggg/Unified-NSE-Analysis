"""Renderer for intraday options trade-plan synthesis."""

from __future__ import annotations

from terminal.renderers._base import FOOTER, _get, _source_trail_lines


def _fmt_price(value) -> str:
    if isinstance(value, (int, float)):
        return f"₹{value:,.2f}"
    return "—"


def _fmt_value(value) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:.1f}"
        return f"{value:g}"
    if isinstance(value, int):
        return str(value)
    return "—" if value is None else str(value)


def _first_num(values: list | tuple, default=None):
    for value in values or []:
        if isinstance(value, (int, float)):
            return value
    return default


def _last_num(values: list | tuple, default=None):
    for value in reversed(values or []):
        if isinstance(value, (int, float)):
            return value
    return default


def _nums(values: list | tuple) -> list[float]:
    return [value for value in values or [] if isinstance(value, (int, float))]


def render(tool_results: list[dict]) -> str:
    """Render an actionable, evidence-gated intraday options trade plan."""
    resolved = _get(tool_results, "resolve_symbol") or {}
    snapshot = _get(tool_results, "get_nse_intraday_snapshot") or {}
    levels = _get(tool_results, "get_intraday_levels") or {}
    fno = _get(tool_results, "get_fno_overview") or {}
    chain = _get(tool_results, "get_options_chain") or {}
    setup = _get(tool_results, "explain_intraday_setup") or {}

    symbol = (
        resolved.get("symbol")
        or snapshot.get("symbol")
        or levels.get("symbol")
        or fno.get("symbol")
        or chain.get("symbol")
        or "SYMBOL"
    )
    price = (
        snapshot.get("last_price")
        or snapshot.get("price")
        or levels.get("price")
        or setup.get("price")
    )
    supports = levels.get("supports") or []
    resistances = levels.get("resistances") or []
    pivot = levels.get("pivot")
    pcr = chain.get("pcr", fno.get("pcr"))
    max_pain = chain.get("max_pain", fno.get("max_pain"))
    basis = fno.get("basis")
    carry = fno.get("cost_of_carry")

    raw_supports = _nums(supports)
    raw_resistances = _nums(resistances)
    if isinstance(price, (int, float)):
        all_levels = sorted(set(raw_supports + raw_resistances))
        display_supports = [v for v in reversed(all_levels) if v <= price]
        display_resistances = [v for v in all_levels if v >= price]
    else:
        display_supports = raw_supports
        display_resistances = raw_resistances

    nearest_resistance = _first_num(display_resistances)
    breakout = _first_num(
        [
            r for r in display_resistances
            if isinstance(r, (int, float)) and (not isinstance(price, (int, float)) or r >= price)
        ]
    )
    next_resistance = None
    if breakout is not None:
        for r in display_resistances:
            if isinstance(r, (int, float)) and r > breakout:
                next_resistance = r
                break
    nearest_support = _first_num(display_supports)
    deeper_support = _last_num(display_supports, nearest_support)

    bias = "Neutral"
    pivot_bias = ""
    if isinstance(price, (int, float)) and isinstance(pivot, (int, float)):
        pivot_bias = "Bullish" if price >= pivot else "Bearish"
        bias = pivot_bias
    setup_label = str(setup.get("setup_label") or setup.get("setup") or "")
    setup_bias = ""
    if "LONG" in setup_label.upper():
        setup_bias = "Bullish"
    elif "SHORT" in setup_label.upper():
        setup_bias = "Bearish"
    conflict_note = ""
    if setup_bias and pivot_bias and setup_bias != pivot_bias:
        bias = "Mixed/conditional"
        conflict_note = f"setup label {setup_label} conflicts with spot {'below' if pivot_bias == 'Bearish' else 'above'} pivot"
    elif setup_bias:
        bias = setup_bias

    missing: list[str] = []
    if not chain or chain.get("error"):
        missing.append("usable option-chain strikes")
    if not fno or fno.get("error"):
        missing.append("futures/buildup detail")
    if not supports or not resistances:
        missing.append("intraday support/resistance levels")

    lines = [f"━━━ {symbol} — Intraday Options Trade Plan ━━━"]
    lines.append("\n▶ BIAS")
    lines.append(f"  {bias}: spot {_fmt_price(price)} vs pivot {_fmt_price(pivot)}.")
    if conflict_note:
        lines.append(f"  Evidence flag: {conflict_note}; wait for confirmation at trigger levels.")
    if setup_label:
        lines.append(f"  Intraday setup: {setup_label}.")

    lines.append("\n▶ KEY LEVELS")
    lines.append(f"  Spot: {_fmt_price(price)}")
    lines.append(f"  Pivot: {_fmt_price(pivot)}")
    lines.append("  Supports: " + (" | ".join(_fmt_price(v) for v in display_supports[:4]) if display_supports else "—"))
    lines.append("  Resistances: " + (" | ".join(_fmt_price(v) for v in display_resistances[:4]) if display_resistances else "—"))

    lines.append("\n▶ OPTIONS")
    lines.append(f"  PCR: {_fmt_value(pcr)} | Max pain: {_fmt_value(max_pain)}")
    if basis is not None or carry is not None:
        lines.append(f"  Futures basis: {_fmt_value(basis)} | Cost of carry: {_fmt_value(carry)}")

    lines.append("\n▶ CE SETUP")
    if breakout is not None:
        lines.append(f"  Trigger: sustained move above {_fmt_price(breakout)}.")
    else:
        lines.append("  No fresh CE trigger from current evidence; price is already above listed resistance levels.")
        lines.append("  Wait for a fresh high, pullback-retest, or updated intraday resistance.")
    lines.append("  Structure: prefer ATM/near-ATM CE only after trigger, or a defined-risk bull call spread.")
    if nearest_support is not None:
        lines.append(f"  Stop: spot below {_fmt_price(nearest_support)}.")
    else:
        lines.append("  Stop: below the trigger candle low once a valid trigger forms.")
    if next_resistance is not None or breakout is not None:
        lines.append(f"  Targets: {_fmt_price(next_resistance or breakout)} then trail if price holds above breakout.")
    else:
        lines.append("  Targets: use the next intraday high/round-number resistance after confirmation.")

    lines.append("\n▶ PE SETUP")
    if nearest_support is not None:
        lines.append(f"  Trigger: breakdown below {_fmt_price(nearest_support)} with bearish confirmation.")
    else:
        lines.append("  No fresh PE trigger from current evidence; no below-spot support is available.")
        lines.append("  Wait for updated support or a clean failed-breakout reversal.")
    lines.append("  Structure: ATM/near-ATM PE for scalp, or a defined-risk bear put spread.")
    if breakout is not None:
        lines.append(f"  Stop: spot back above {_fmt_price(breakout)}.")
    else:
        lines.append("  Stop: above the breakdown/reversal candle high after confirmation.")
    if deeper_support is not None:
        lines.append(f"  Targets: {_fmt_price(deeper_support)} first; avoid overstaying near max-pain pinning.")
    else:
        lines.append("  Targets: use the next lower intraday support after confirmation; avoid overstaying near max-pain pinning.")

    lines.append("\n▶ NO-TRADE ZONE")
    if nearest_support is not None and breakout is not None and nearest_support < breakout:
        lines.append(
            f"  Avoid fresh option entries while spot chops between {_fmt_price(nearest_support)} and {_fmt_price(breakout)}."
        )
    else:
        lines.append("  No clean two-sided chop band is available from current levels; wait for cleaner support/resistance.")
    if max_pain is not None:
        lines.append(f"  Max-pain pin risk around {_fmt_value(max_pain)} can mute option follow-through.")

    lines.append("\n▶ RISK")
    lines.append("  Use premium-defined risk; options can decay quickly if price stalls.")
    if missing:
        lines.append("  Missing evidence: " + ", ".join(missing) + ".")
        lines.append("  No unsupported buildup, IV, or strike-selection claim was inferred from missing data.")

    lines.append("\n▶ SOURCE TRAIL")
    lines.extend(_source_trail_lines(tool_results))
    lines.append(FOOTER)
    return "\n".join(line for line in lines if str(line).strip() != "")
