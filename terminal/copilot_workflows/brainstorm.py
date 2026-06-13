"""Deterministic /brainstorm workflow — market-context-aware."""

from __future__ import annotations

from .common import command_arg

# Market topics that trigger trading-specific approaches instead of the
# generic software-engineering template.
_MARKET_KEYWORDS = frozenset({
    "strategy", "trade", "trading", "entry", "exit", "stop", "target",
    "intraday", "swing", "positional", "hedge", "options", "option",
    "call", "put", "straddle", "strangle", "spread", "futures", "future",
    "buy", "sell", "long", "short", "risk", "reward", "breakout", "reversal",
    "momentum", "trend", "support", "resistance", "backtest", "screener",
    "watchlist", "portfolio", "position", "sizing", "oi", "pcr", "vwap",
    "ema", "pivot", "nifty", "banknifty", "finnifty", "midcpnifty",
})


def _is_market_topic(topic: str) -> bool:
    return bool(_MARKET_KEYWORDS & set(topic.lower().split()))


def render_brainstorm(topic: str, context_symbols: list[str] | None = None) -> str:
    topic = (topic or "").strip() or "unspecified topic"
    symbols = context_symbols or []
    market_mode = _is_market_topic(topic) or bool(symbols)

    lines = ["# Brainstorm", "", f"**Topic:** {topic}"]

    if symbols:
        lines += ["", f"**Market Context:** {', '.join(symbols)} (from current session)"]

    lines += [""]

    if market_mode:
        lines += [
            "**Known Context**",
            "- This is a market/trading discussion — no orders or portfolio mutations happen here.",
            "- All strategy ideas are for research only; execution requires explicit approval.",
            "- Use live NSE data tools (F&O, intraday, breadth) for evidence before recommending.",
            "",
            "**Assumptions**",
            "- Risk management (stop-loss, position size) must be defined before any setup is actionable.",
            "- Broader market trend and F&O OI context should inform the directional bias.",
            "- Backtest data or historical win-rate should support the approach if available.",
            "",
            "**Approaches**",
            "1. **Intraday**: pivot-based levels, VWAP, ORB, CE/PE OI walls as S/R.",
            "2. **Swing**: EMA50/200 trend, breakout from consolidation, volume confirmation.",
            "3. **Options play**: defined-risk spread (bull call / bear put) aligned with PCR + max pain.",
            "",
            "**Recommendation**",
            "Start with F&O context (PCR, max pain, OI build) to set directional bias,"
            " then overlay intraday levels for entry/exit precision.",
        ]
    else:
        lines += [
            "**Known Context**",
            "- Treat this as a design discussion, not implementation.",
            "- Preserve existing Agent Adda behavior unless the change is explicitly approved.",
            "- Prefer deterministic workflows first; use an LLM only for synthesis or wording.",
            "",
            "**Assumptions**",
            "- The goal is to clarify intent, risks, and tradeoffs before any code or data changes.",
            "- Any action that mutates files, reports, data, or portfolio state needs a later approval step.",
            "",
            "**Approaches**",
            "1. **Minimal**: add a narrow command or behavior only for the named workflow.",
            "2. **Structured**: add a reusable workflow primitive with tests and help entries.",
            "3. **Full copilot**: add state, execution trace, verification, and resumable task memory.",
            "",
            "**Recommendation**",
            "Use the structured approach first, then promote it to the full copilot path once it proves useful.",
        ]

    lines += [
        "",
        "**Approval Gate**",
        "Reply with `approved` to proceed, or describe changes to the approach first.",
    ]
    return "\n".join(lines)


def handle_brainstorm_command(command: str, context_symbols: list[str] | None = None) -> str:
    return render_brainstorm(command_arg(command, "brainstorm"), context_symbols)
