#!/usr/bin/env python3
"""Build the Agent Adda Morning Market HTML dashboard."""
from __future__ import annotations

import html
import argparse
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OLLAMA_GRANITE_MODEL = "granite4:latest"

REPORT_VARIANTS: dict[str, dict[str, str]] = {
    "morning": {
        "latest_name": "morning_market.html",
        "dated_dir": "morning_market",
        "archive_prefix": "morning_market",
        "page_title": "Agent Adda Morning Market",
        "kicker": "Agent Adda Morning Market",
        "status_label": "Opening stance",
        "audience_title": "Built for informed retail investors",
        "audience_intro": (
            "This morning dashboard is designed for retail investors and swing traders who actively "
            "follow Indian equities and want a structured opening read before updating their watchlist, "
            "risk exposure, or market view."
        ),
        "hero_confirm": "Use the first 15-30 minutes to confirm whether this is real breadth or just a gap-and-rotate tape.",
        "commentary_context": "opening report",
        "confirmation_window": "first 15-30 minutes",
        "confirm_1": "NIFTY holds above opening range high after the first 15-30 minutes.",
        "fno_confirm": "VWAP/opening-range confirmation",
        "slug_context": "morning",
    },
    "midday": {
        "latest_name": "midday_market.html",
        "dated_dir": "midday_market",
        "archive_prefix": "midday_market",
        "page_title": "Agent Adda Midday Market",
        "kicker": "Agent Adda Midday Market",
        "status_label": "Midday stance",
        "audience_title": "Built for informed retail investors",
        "audience_intro": (
            "This midday dashboard is designed for retail investors and swing traders who want a "
            "second-half market read after the opening noise has settled, with focus on sector leadership, "
            "breadth, movers, momentum, F&O context, and risk control."
        ),
        "hero_confirm": "Use the next 60-90 minutes to confirm whether leadership is broadening, fading, or rotating into the close.",
        "commentary_context": "midday report",
        "confirmation_window": "next 60-90 minutes",
        "confirm_1": "NIFTY holds the key intraday range and avoids a failed second-half breakout.",
        "fno_confirm": "VWAP/intraday-range confirmation",
        "slug_context": "midday",
    },
}


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def safe_call(label: str, fn: Any, *args: Any, **kwargs: Any) -> tuple[Any, str | None]:
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 - report generation should degrade, not crash.
        return {}, f"{label}: {type(exc).__name__}: {exc}"


def num(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        out = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def fmt_num(value: Any, digits: int = 2) -> str:
    value_f = num(value)
    if value_f is None:
        return "n/a"
    if abs(value_f) >= 100:
        return f"{value_f:,.0f}"
    return f"{value_f:,.{digits}f}".rstrip("0").rstrip(".")


def fmt_pct(value: Any) -> str:
    value_f = num(value)
    if value_f is None:
        return "n/a"
    return f"{value_f:+.2f}%"


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def symbol_link(symbol: Any) -> str:
    value = str(symbol or "").strip().upper()
    if not value:
        return "n/a"
    href = f"https://www.nseindia.com/get-quotes/equity?symbol={quote(value, safe='')}"
    return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{esc(value)}</a>'


def load_llm_env_if_needed() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key in {"OPENAI_API_KEY", "OPENAI_MODEL"} and not os.environ.get(key):
                os.environ[key] = value.strip().strip('"').strip("'")
    except OSError:
        return


def configure_retail_commentary_llm() -> tuple[str, str | None]:
    """Prefer OpenAI when configured; otherwise use the local Ollama Granite model."""

    load_llm_env_if_needed()
    if os.environ.get("OPENAI_API_KEY"):
        return "OpenAI", os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"

    model = (
        os.environ.get("AGENT_ADDA_MORNING_MARKET_OLLAMA_MODEL")
        or os.environ.get("RESEARCH_COUNCIL_OLLAMA_MODEL")
        or DEFAULT_OLLAMA_GRANITE_MODEL
    )
    os.environ["RESEARCH_COUNCIL_OLLAMA_MODEL"] = model
    return "Ollama", model


def report_variant_config(variant: str) -> dict[str, str]:
    key = variant.lower().strip()
    if key not in REPORT_VARIANTS:
        raise ValueError(f"Unknown report variant: {variant}. Expected one of {', '.join(REPORT_VARIANTS)}")
    return REPORT_VARIANTS[key]


AI_GROUNDING_NOTE = (
    "AI assistants may help draft and organize this market dashboard. Tables, levels, breadth, F&O, "
    "momentum, global cues, and source freshness are grounded in Agent Adda evidence shown in the report. "
    "AI synthesis does not replace independent verification, suitability assessment, or risk management."
)

SEBI_CAUTION = (
    "This is for education and general market research only. It is not personalised advice, not a "
    "SEBI-registered research report, and not a recommendation or solicitation to buy, sell, hold, trade, "
    "or subscribe. Markets carry risk, including capital loss. No assured, fixed, or guaranteed returns are "
    "expressed or implied. Verify independently and consult a SEBI-registered investment adviser / qualified "
    "professional before acting."
)


def css_class(value: Any) -> str:
    value_f = num(value, 0.0) or 0.0
    if value_f > 0.15:
        return "pos"
    if value_f < -0.15:
        return "neg"
    return "flat"


def read_for_index(name: str, pct: Any, *, vix: bool = False) -> str:
    pct_f = num(pct, 0.0) or 0.0
    if vix:
        if pct_f < -0.05:
            return "Vol easing"
        if pct_f > 0.05:
            return "Vol rising"
        return "Calm"
    if pct_f >= 0.5:
        return "Leading"
    if pct_f >= 0.15:
        return "Supportive"
    if pct_f > -0.15:
        return "Flat"
    return "Weak"


def market_stance(indices: dict[str, Any], sectors: list[dict[str, Any]]) -> tuple[str, str, str]:
    nifty = num((indices.get("NIFTY 50") or {}).get("pct_change"), 0.0) or 0.0
    bank = num((indices.get("NIFTY BANK") or {}).get("pct_change"), 0.0) or 0.0
    small = num((indices.get("NIFTY SMALLCAP 250") or {}).get("pct_change"), 0.0) or 0.0
    micro = num((indices.get("NIFTY MICROCAP 250") or {}).get("pct_change"), 0.0) or 0.0
    vix = num((indices.get("INDIA VIX") or {}).get("pct_change"), 0.0) or 0.0
    positives = sum(1 for row in sectors if (num(row.get("pct_change"), 0.0) or 0.0) > 0)
    total = max(len(sectors), 1)
    breadth = positives / total

    if nifty > 0 and small > nifty and micro > nifty and vix <= 0:
        title = "Selective risk-on"
        subtitle = "Broader market is leading while volatility is calm."
    elif nifty < 0 and breadth < 0.45:
        title = "Risk-off open"
        subtitle = "Headline and sector participation are weak."
    else:
        title = "Rotational open"
        subtitle = "Leadership is selective; confirm with first-hour breadth."

    caution = "Bank Nifty is not confirming yet." if bank < 0.05 else "Banking is at least supportive."
    return title, subtitle, caution


EXCLUDE_INDEX_TERMS = (
    "G-SEC",
    "BHARAT BOND",
    "BENCHMARK",
    "CLEAN PRICE",
    "8-13 YR",
    "4-8 YR",
    "11-15 YR",
    "15 YR",
    "COMPOSITE G-SEC",
)

EXCLUDE_INDEX_NAMES = {
    "NIFTY 50",
    "NIFTY NEXT 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    "NIFTY TOTAL MARKET",
    "INDIA VIX",
}


def sector_rows(indices: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, row in indices.items():
        if name in EXCLUDE_INDEX_NAMES:
            continue
        if any(term in name for term in EXCLUDE_INDEX_TERMS):
            continue
        if row.get("pct_change") is None:
            continue
        rows.append(
            {
                "name": name,
                "last": row.get("last"),
                "pct_change": row.get("pct_change"),
                "day_high": row.get("day_high"),
                "day_low": row.get("day_low"),
            }
        )
    rows.sort(key=lambda item: num(item.get("pct_change"), 0.0) or 0.0, reverse=True)
    return rows


def row_cells(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def table(headers: list[str], rows: list[list[str]], class_name: str = "") -> str:
    if not rows:
        rows = [["n/a" for _ in headers]]
    thead = "<tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr>"
    body = "".join(row_cells(row) for row in rows)
    cls = f' class="{class_name}"' if class_name else ""
    return f'<div class="table-wrap"><table{cls}><thead>{thead}</thead><tbody>{body}</tbody></table></div>'


def bar_rows(rows: list[dict[str, Any]], *, positive: bool) -> str:
    if not rows:
        return '<div class="empty">No rows available.</div>'
    max_abs = max(abs(num(row.get("pct_change"), 0.0) or 0.0) for row in rows) or 1.0
    parts = []
    for row in rows:
        pct = num(row.get("pct_change"), 0.0) or 0.0
        width = max(4, min(100, abs(pct) / max_abs * 100))
        tone = "goodbar" if positive else "badbar"
        parts.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{esc(row.get('name'))}</div>
              <div class="bar-track"><span class="{tone}" style="width:{width:.1f}%"></span></div>
              <div class="bar-value {css_class(pct)}">{fmt_pct(pct)}</div>
            </div>
            """
        )
    return "\n".join(parts)


def extract_fno_row(fno_result: dict[str, Any]) -> dict[str, Any]:
    rows = fno_result.get("rows") if isinstance(fno_result, dict) else []
    return rows[0] if rows else {}

def _parse_ymd(value: Any) -> date | None:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        for pattern in ("%Y-%m-%d", "%d-%b-%Y"):
            try:
                return datetime.strptime(raw[:10] if pattern == "%Y-%m-%d" else raw, pattern).date()
            except ValueError:
                continue
        return None
    except Exception:
        return None


def _is_last_weekday_of_month(d: date) -> bool:
    # Same weekday one week later would fall in a new month => this is the last one in month.
    return (d + timedelta(days=7)).month != d.month


def expiry_awareness(now_ist: datetime, instrument: str, fno_row: dict[str, Any]) -> str:
    """Return a short expiry-awareness note based on the instrument's next expiry."""

    expiry = _parse_ymd(fno_row.get("options_expiry") or fno_row.get("futures_expiry"))
    if expiry is None:
        return f"{instrument}: expiry n/a"
    today = now_ist.date()
    delta = (expiry - today).days
    kind = "Monthly" if _is_last_weekday_of_month(expiry) else "Weekly"
    if delta == 0:
        return f"{instrument}: expiry today ({expiry.isoformat()}, {kind})"
    if delta == 1:
        return f"{instrument}: expiry tomorrow ({expiry.isoformat()}, {kind})"
    if 1 < delta <= 7:
        return f"{instrument}: next expiry {expiry.isoformat()} ({kind})"
    return f"{instrument}: expiry {expiry.isoformat()}"


def fno_read(row: dict[str, Any]) -> str:
    pcr = num(row.get("pcr_oi"))
    buildup = str(row.get("buildup") or "").upper()
    if pcr is None:
        return "Data gap"
    if pcr >= 1.1 and "LONG" in buildup and "UNWIND" not in buildup:
        return "Bullish, needs price confirmation"
    if pcr <= 0.8 and "SHORT" in buildup and "COVER" not in buildup:
        return "Bearish, needs price confirmation"
    if pcr >= 1.0:
        return "Constructive PCR; price confirmation needed"
    if pcr <= 0.8:
        return "Bearish-leaning PCR; price confirmation needed"
    return "Neutral"


def fno_stock_read(row: dict[str, Any]) -> str:
    """Summarize stock-level F&O evidence without turning it into a trade call."""
    move = num(row.get("futures_price_change_pct"))
    pcr = num(row.get("pcr_oi"))
    direction = "up" if move is not None and move > 0 else "down" if move is not None and move < 0 else "flat"
    if pcr is None:
        return f"Price {direction}, PCR unavailable — wait for confirmation"
    if pcr >= 1.0:
        if direction == "up":
            return "Price up, PCR constructive — better alignment"
        if direction == "down":
            return "Price down, PCR constructive — possible support"
    if pcr <= 0.8:
        if direction == "up":
            return "Price up, PCR bearish — weak confirmation"
        if direction == "down":
            return "Price down, PCR bearish — aligned pressure"
    return "Mixed PCR — wait for price confirmation"


def symbol_list(rows: list[dict[str, Any]], *, limit: int = 4) -> str:
    symbols = [str(row.get("symbol") or row.get("name") or "").strip() for row in rows if row.get("symbol") or row.get("name")]
    return ", ".join(symbols[:limit]) or "n/a"


def commentary_has_trade_call_language(text: str) -> bool:
    """Reject model prose that turns evidence labels into actionable calls."""

    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    blocked_phrases = (
        "bullish signal",
        "bullish signals",
        "bearish signal",
        "bearish signals",
        "strong bullish signal",
        "strong bullish signals",
        "strong bearish signal",
        "strong bearish signals",
        "signals for",
        "strong buy signal",
        "strong buy signals",
        "buy signal",
        "buy signals",
        "sell signal",
        "sell signals",
        "strong buy recommendation",
        "strong buy recommendations",
        "buy recommendation",
        "buy recommendations",
        "sell recommendation",
        "sell recommendations",
        "must buy",
        "should buy",
        "buy now",
        "sell now",
        "recommended to buy",
        "recommended buy",
        "entry price",
        "entry zone",
        "target price",
        "stop loss",
        "stop-loss",
        "sl ",
    )
    return any(phrase in normalized for phrase in blocked_phrases)


def commentary_conflicts_with_evidence(
    text: str,
    *,
    global_view: dict[str, Any],
    indices: dict[str, Any],
    momentum_rows: list[dict[str, Any]],
) -> bool:
    """Reject broad claims that contradict supplied market moves."""

    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    moves = global_view.get("moves") if isinstance(global_view, dict) else {}
    major_assets = ("S&P 500", "Nasdaq", "Hang Seng", "Nikkei 225")
    has_negative_major_asset = any(
        num((moves.get(asset) or {}).get("pct_change")) is not None
        and (num((moves.get(asset) or {}).get("pct_change")) or 0.0) < 0
        for asset in major_assets
    )
    if has_negative_major_asset and any(
        phrase in normalized
        for phrase in (
            "all major indices are positive",
            "all global indices are positive",
            "positive trends observed across major indices",
            "positive across major indices",
            "positive sentiment across major indices",
            "positive market sentiment across major indices",
            "positive returns across major indices",
            "positive returns across major markets",
            "positive bias in us, asia",
            "positive bias in us and asia",
            "positive bias in us & asia",
            "positive bias in asia",
            "positive in asia",
            "all major global indices",
        )
    ):
        return True
    if has_negative_major_asset and re.search(r"positive\\s+returns?.{0,40}major\\s+indices", normalized):
        return True
    if has_negative_major_asset and re.search(r"positive\\s+bias\\s+in\\s+u\\.?s\\.?\\s*(and|&)\\s+asia", normalized):
        return True

    def _pct(asset: str) -> float | None:
        try:
            value = (moves.get(asset) or {}).get("pct_change")
            return float(value) if value is not None else None
        except Exception:
            return None

    def _direction_conflict(asset_alias: str, pct: float) -> bool:
        for match in re.finditer(re.escape(asset_alias), normalized):
            window = normalized[max(0, match.start() - 48): match.end() + 48]
            if pct < -0.05 and re.search(r"\b(up|positive|green|gained|rose|rising|strong)\b", window):
                return True
            if pct > 0.05 and re.search(r"\b(down|negative|red|fell|falling|weak)\b", window):
                return True
        return False

    # If the narrative calls an explicitly named asset up/down, ensure it matches the supplied move.
    asset_aliases = {
        "S&P 500": ["s&p 500", "sp 500"],
        "Nasdaq": ["nasdaq"],
        "Hang Seng": ["hang seng"],
        "Nikkei 225": ["nikkei 225", "nikkei"],
        "Gold": ["gold"],
        "Crude Oil": ["crude", "crude oil", "oil"],
        "Copper": ["copper"],
        "DXY": ["dxy"],
        "USDINR": ["usdinr", "usd inr"],
    }
    for asset, aliases in asset_aliases.items():
        pct = _pct(asset)
        if pct is None:
            continue
        for alias in aliases:
            if _direction_conflict(alias, pct):
                return True

    nifty_move = num((indices.get("NIFTY 50") or {}).get("pct_change"), 0.0) or 0.0
    bank_move = num((indices.get("NIFTY BANK") or {}).get("pct_change"), 0.0) or 0.0
    domestic_not_confirmed = nifty_move <= 0 or bank_move <= 0
    if domestic_not_confirmed and any(
        phrase in normalized
        for phrase in (
            "indian market is broadly bullish",
            "indian market is bullish",
            "domestic market is broadly bullish",
            "domestic market is bullish",
            "broadly risk-on",
            "strong bullish market sentiment",
        )
    ):
        return True

    extended_symbols = [
        str(row.get("symbol") or "").lower()
        for row in momentum_rows
        if (num(row.get("rsi")) or 0.0) > 80
    ]
    if extended_symbols and "strong buy" in normalized:
        mentioned_extended_name = any(symbol and symbol in normalized for symbol in extended_symbols)
        has_caution = any(
            phrase in normalized
            for phrase in ("extended", "overbought", "do not chase", "avoid chasing", "requires confirmation")
        )
        if mentioned_extended_name and not has_caution:
            return True
    return False


def generate_retail_investor_commentary(
    *,
    report_label: str,
    commentary_context: str,
    confirmation_window: str,
    stance: str,
    stance_detail: str,
    stance_caution: str,
    indices: dict[str, Any],
    leaders: list[dict[str, Any]],
    laggards: list[dict[str, Any]],
    gainers: list[dict[str, Any]],
    losers: list[dict[str, Any]],
    momentum_rows: list[dict[str, Any]],
    nifty_fno: dict[str, Any],
    bank_fno: dict[str, Any],
    global_view: dict[str, Any],
    as_of: str,
) -> dict[str, Any]:
    """Return a retail-friendly commentary, with LLM overlay and deterministic fallback."""

    nifty = indices.get("NIFTY 50") or {}
    bank = indices.get("NIFTY BANK") or {}
    small = indices.get("NIFTY SMALLCAP 250") or {}
    vix = indices.get("INDIA VIX") or {}
    global_regime = (global_view.get("risk_regime") if isinstance(global_view, dict) else None) or "mixed"
    global_as_of = (global_view.get("as_of") if isinstance(global_view, dict) else None) or "n/a"
    domestic_weak = (
        (num(nifty.get("pct_change"), 0.0) or 0.0) < -0.15
        and (num(bank.get("pct_change"), 0.0) or 0.0) < -0.15
        and (num(vix.get("pct_change"), 0.0) or 0.0) > 0.15
    )

    fallback = {
        "headline": f"{stance}: read the market as evidence, not as a trade call",
        "commentary": (
            f"As of {as_of}, the {report_label.lower()} is best read as {stance.lower()}. {stance_detail} "
            f"{stance_caution} For retail investors, the practical message is to observe whether the "
            f"{confirmation_window} confirm participation across NIFTY, Bank Nifty, broader indices, and sector leaders. "
            f"NIFTY 50 is at {fmt_num(nifty.get('last'))} ({fmt_pct(nifty.get('pct_change'))}), Bank Nifty is at "
            f"{fmt_num(bank.get('last'))} ({fmt_pct(bank.get('pct_change'))}), and Smallcap 250 is at "
            f"{fmt_num(small.get('last'))} ({fmt_pct(small.get('pct_change'))}). India VIX is "
            f"{fmt_pct(vix.get('pct_change'))}, so risk appetite should be judged with volatility in mind.\n\n"
            f"Sector leadership is concentrated around {symbol_list(leaders, limit=4)}, while weaker pockets include "
            f"{symbol_list(laggards, limit=4)}. The top mover list highlights {symbol_list(gainers, limit=4)} on the "
            f"positive side and {symbol_list(losers, limit=4)} on the weak side. Momentum screens are useful for "
            f"building a watchlist, especially names such as {symbol_list(momentum_rows, limit=5)}, but the report "
            f"should not be treated as a trade list. Look for price holding above the opening range, improving "
            f"breadth, and volume confirmation before drawing conclusions.\n\n"
            f"F&O evidence is a context layer, not a standalone signal. NIFTY reads as {fno_read(nifty_fno).lower()} "
            f"with PCR OI {fmt_num(nifty_fno.get('pcr_oi'), 2)} (expiry {nifty_fno.get('options_expiry') or 'n/a'}), "
            f"while BANKNIFTY reads as {fno_read(bank_fno).lower()} with PCR OI {fmt_num(bank_fno.get('pcr_oi'), 2)} "
            f"(expiry {bank_fno.get('options_expiry') or 'n/a'}). "
            f"The global backdrop (as of {global_as_of}) is marked as {global_regime}. "
            f"Retail investors should use this dashboard to decide what deserves attention, what requires patience, "
            f"and where risk control matters most."
        ),
        "takeaways": [
            "Use the report as a market map: index direction, breadth, sectors, movers, momentum, F&O, and global cues.",
            f"Treat strength as provisional until the {confirmation_window} confirm breadth and price acceptance.",
            "Avoid chasing sharp movers without checking RSI, volume, support distance, and position size.",
            "Prioritize watchlist refinement and risk control over instant action.",
        ],
        "source": "deterministic evidence synthesis",
    }
    if domestic_weak:
        return {**fallback, "source": "AI-assisted evidence synthesis fallback"}

    schema = {
        "type": "object",
        "required": ["headline", "commentary", "takeaways"],
        "properties": {
            "headline": {"type": "string"},
            "commentary": {"type": "string"},
            "takeaways": {"type": "array", "items": {"type": "string"}},
        },
    }
    payload = {
        "as_of": as_of,
        "report_label": report_label,
        "commentary_context": commentary_context,
        "confirmation_window": confirmation_window,
        "stance": stance,
        "stance_detail": stance_detail,
        "stance_caution": stance_caution,
        "indices": {
            "NIFTY 50": nifty,
            "NIFTY BANK": bank,
            "NIFTY SMALLCAP 250": small,
            "INDIA VIX": vix,
        },
        "sector_leaders": leaders[:6],
        "weak_pockets": laggards[:6],
        "top_gainers": gainers[:6],
        "top_losers": losers[:6],
        "momentum": momentum_rows[:8],
        "fno": {"NIFTY": nifty_fno, "BANKNIFTY": bank_fno},
        "global": global_view,
    }

    try:
        from terminal.research_council.llm_client import call_llm_json  # noqa: PLC0415

        provider, provider_model = configure_retail_commentary_llm()
        result = call_llm_json(
            system=(
                "You are Agent Adda's market-intelligence narrator. Write for informed Indian retail "
                "investors in plain language. Use only the supplied evidence. Do not make buy/sell/hold "
                "recommendations, targets, assured-return claims, or personalised advice. Explain what the "
                f"{commentary_context} means, how to read confirmation, and where risk control matters. Keep the "
                "commentary as 3 compact paragraphs, around 230-320 words. Domestic live evidence takes priority "
                "over cached global cues. Explicitly separate the global regime from the domestic market read. "
                "Do not call the Indian session broadly bullish or risk-on unless NIFTY, Bank Nifty, breadth, and "
                "sector participation support that conclusion; otherwise use flat, mixed, cautious, selective, or "
                "rotational language. Never say all global indices are positive: describe each supplied asset move "
                "and call the region mixed when any major index is negative. Treat cached or prior-day global, "
                "momentum, and F&O data as dated context, not live confirmation. "
                "If you reference screener signals, do not output tokens like STRONG_BUY/BUY/HOLD/SELL/WEAK_HOLD; "
                "use neutral wording like Strong Bullish/Bullish/Neutral/Cautious/Bearish instead, and keep it as a "
                "watchlist-style label (not advice). "
                "For momentum names, inspect RSI and explicitly flag RSI above 80 as extended and unsuitable for "
                "chasing. Say 'momentum watchlist' or 'requires confirmation' instead of 'buy recommendation', "
                "'must buy', or 'buy now'. Copper strength is only a potential cyclical tailwind; do not claim "
                "that Indian metals are strong unless the supplied domestic metal index confirms it. Mention FII/DII "
                "only as a confirmation item unless actual flow values are present. If NIFTY and Bank Nifty are weak "
                "while India VIX is rising, do not call the session broadly risk-on; describe it as cautious, "
                "selective, or rotational."
            ),
            user=json.dumps(payload, default=str),
            schema=schema,
            model=provider_model or "gpt-4o-mini",
        )
        takeaways = result.get("takeaways") if isinstance(result.get("takeaways"), list) else fallback["takeaways"]
        headline = str(result.get("headline") or fallback["headline"]).strip()
        commentary = str(result.get("commentary") or fallback["commentary"]).strip()
        headline = soften_signal_words(headline)
        commentary = soften_signal_words(commentary)
        takeaways = [soften_signal_words(str(item)) for item in takeaways]
        combined = f"{headline}\n{commentary}".lower()
        if commentary_has_trade_call_language(combined) or commentary_conflicts_with_evidence(
            combined,
            global_view=global_view,
            indices=indices,
            momentum_rows=momentum_rows,
        ):
            return {**fallback, "source": "AI-assisted evidence synthesis fallback"}
        if domestic_weak and ("risk-on" in combined or "risk on" in combined):
            return {**fallback, "source": "AI-assisted evidence synthesis fallback"}
        return {
            "headline": headline,
            "commentary": commentary,
            "takeaways": [str(item).strip() for item in takeaways if str(item).strip()][:5] or fallback["takeaways"],
            "source": f"{provider} {provider_model} evidence synthesis".strip(),
        }
    except Exception:  # noqa: BLE001 - scheduled report should still complete.
        return {**fallback, "source": "AI-assisted evidence synthesis fallback"}


def paragraphs(text: str) -> str:
    parts = [part.strip() for part in str(text or "").split("\n") if part.strip()]
    return "".join(f"<p>{esc(part)}</p>" for part in parts)


def bullet_items(items: list[Any]) -> str:
    return "".join(f"<li>{esc(item)}</li>" for item in items if str(item).strip())

def soften_signal_words(text: str) -> str:
    """Normalize model-style signal tokens to neutral market language in narrative text.

    This is intentionally applied only to narrative outputs, not to raw signal fields.
    """
    text = str(text or "")
    if not text.strip():
        return text
    replacements = [
        (r"\bSTRONG[_ ]?BUY\b", "Strong Bullish"),
        (r"\bSTRONG[_ ]?SELL\b", "Strong Bearish"),
        (r"\bWEAK[_ ]?HOLD\b", "Cautious"),
        (r"\bSTRONG\s+BUY\b", "Strong Bullish"),
        (r"\bSTRONG\s+SELL\b", "Strong Bearish"),
        (r"\bBUY\s+SIGNALS?\b", "Bullish signals"),
        (r"\bSELL\s+SIGNALS?\b", "Bearish signals"),
        (r"\bBUY\b", "Bullish"),
        (r"\bSELL\b", "Bearish"),
        (r"\bHOLD\b", "Neutral"),
    ]
    out = text
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def stock_signal_label(signal: Any) -> str:
    """Render stock screener signals as neutral research descriptors."""
    labels = {
        "STRONG_BUY": "Strong bullish",
        "BUY": "Bullish",
        "STRONG_SELL": "Strong bearish",
        "SELL": "Bearish",
        "HOLD": "Watch",
        "WEAK_HOLD": "Cautious",
    }
    key = str(signal or "").strip().upper()
    return labels.get(key, "No signal" if not key or key == "N/A" else key.replace("_", " ").title())


def stock_row(row: dict[str, Any]) -> list[str]:
    move = row.get("pct_change", row.get("change_1d_pct"))
    rs = row.get("relative_strength", row.get("rs_pct", row.get("rsi")))
    return [
        f"<strong>{symbol_link(row.get('symbol'))}</strong><br><span>{esc(row.get('sector') or row.get('company_name') or '')}</span>",
        f'<span class="{css_class(move)}">{fmt_pct(move)}</span>',
        esc(row.get("stage") or "n/a"),
        esc(stock_signal_label(row.get("trading_signal"))),
        fmt_num(rs, 1),
    ]


def merge_stock_movers(rows: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        move = num(row.get("pct_change", row.get("change_1d_pct")))
        if move is None:
            continue
        current = by_symbol.get(symbol)
        if current is None:
            by_symbol[symbol] = row
            continue
        current_move = num(current.get("pct_change", current.get("change_1d_pct")), 0.0) or 0.0
        if (reverse and move > current_move) or (not reverse and move < current_move):
            by_symbol[symbol] = row
    return sorted(
        by_symbol.values(),
        key=lambda item: num(item.get("pct_change", item.get("change_1d_pct")), 0.0) or 0.0,
        reverse=reverse,
    )


def build_report(variant: str = "morning") -> tuple[str, Path, Path]:
    cfg = report_variant_config(variant)
    latest_out = ROOT / "reports" / "latest" / cfg["latest_name"]
    dated_dir = ROOT / "reports" / cfg["dated_dir"]

    from terminal.tools import (  # noqa: PLC0415
        get_fno_analytics,
        get_fno_data_status,
        get_global_market_assessment,
        get_live_market_overview,
        get_top_gainers_losers,
        run_screener_query,
    )

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    as_of = now.strftime("%Y-%m-%d %H:%M IST")
    stamp = now.strftime("%Y%m%d_%H%M")

    errors: list[str] = []
    overview, err = safe_call("get_live_market_overview", get_live_market_overview)
    if err:
        errors.append(err)
    movers, err = safe_call("get_top_gainers_losers", get_top_gainers_losers, index="NIFTY 500", top_n=10, direction="both")
    if err:
        errors.append(err)
    mover_fallbacks: list[tuple[str, dict[str, Any]]] = []
    for fallback_index in ("NIFTY 50", "NIFTY SMALLCAP 250", "NIFTY MIDCAP 100"):
        fallback_movers, err = safe_call(
            f"get_top_gainers_losers {fallback_index}",
            get_top_gainers_losers,
            index=fallback_index,
            top_n=10,
            direction="both",
        )
        if err:
            errors.append(err)
        if isinstance(fallback_movers, dict):
            mover_fallbacks.append((fallback_index, fallback_movers))
    momentum, err = safe_call("run_screener_query", run_screener_query, screen_type="momentum_52w", top_n=12)
    if err:
        errors.append(err)
    fno_status, err = safe_call("get_fno_data_status", get_fno_data_status)
    if err:
        errors.append(err)
    fno_top, err = safe_call("get_fno_analytics top", get_fno_analytics, top_n=12)
    if err:
        errors.append(err)
    nifty_fno, err = safe_call("get_fno_analytics NIFTY", get_fno_analytics, symbol="NIFTY")
    if err:
        errors.append(err)
    bank_fno, err = safe_call("get_fno_analytics BANKNIFTY", get_fno_analytics, symbol="BANKNIFTY")
    if err:
        errors.append(err)
    global_view, err = safe_call("get_global_market_assessment", get_global_market_assessment)
    if err:
        errors.append(err)

    indices = overview.get("indices") if isinstance(overview, dict) else {}
    indices = indices or {}
    sectors = sector_rows(indices)
    leaders = sectors[:12]
    laggards = sorted(sectors, key=lambda item: num(item.get("pct_change"), 0.0) or 0.0)[:12]
    stance, stance_detail, stance_caution = market_stance(indices, sectors)
    if cfg["slug_context"] == "midday":
        stance = stance.replace(" open", " session")
    bank_move = num((indices.get("NIFTY BANK") or {}).get("pct_change"), 0.0) or 0.0
    mobile_stance = "Bank Nifty lagging. Confirm breadth in 15-30 min." if bank_move < 0.05 else "Confirm breadth in 15-30 min."

    broad_keys = [
        "NIFTY 50",
        "NIFTY BANK",
        "NIFTY FINANCIAL SERVICES",
        "NIFTY MIDCAP 100",
        "NIFTY SMALLCAP 100",
        "NIFTY SMALLCAP 250",
        "NIFTY MICROCAP 250",
        "INDIA VIX",
    ]
    broad_rows = []
    for key in broad_keys:
        row = indices.get(key) or {}
        broad_rows.append(
            [
                esc(key),
                fmt_num(row.get("last")),
                f'<span class="{css_class(row.get("pct_change"))}">{fmt_pct(row.get("pct_change"))}</span>',
                f"{fmt_num(row.get('day_low'))} - {fmt_num(row.get('day_high'))}",
                esc(read_for_index(key, row.get("pct_change"), vix=key == "INDIA VIX")),
            ]
        )

    mover_source = movers.get("source", "n/a") if isinstance(movers, dict) else "n/a"
    mover_as_of = movers.get("as_of", "n/a") if isinstance(movers, dict) else "n/a"
    gainers = (movers.get("gainers") if isinstance(movers, dict) else []) or []
    losers = (movers.get("losers") if isinstance(movers, dict) else []) or []
    fallback_labels: list[str] = []
    if len(gainers) < 5:
        fallback_labels = [label for label, _ in mover_fallbacks]
        gainers = merge_stock_movers(
            gainers + [row for _, data in mover_fallbacks for row in (data.get("gainers") or [])],
            reverse=True,
        )
    if len(losers) < 5:
        losers = merge_stock_movers(
            losers + [row for _, data in mover_fallbacks for row in (data.get("losers") or [])],
            reverse=False,
        )
    if fallback_labels:
        mover_source = f"{mover_source} + fallback merge: {', '.join(fallback_labels)}"

    momentum_rows_raw = (momentum.get("results") if isinstance(momentum, dict) else []) or []
    momentum_date = momentum.get("snapshot_date", "n/a") if isinstance(momentum, dict) else "n/a"

    nifty = extract_fno_row(nifty_fno if isinstance(nifty_fno, dict) else {})
    bank = extract_fno_row(bank_fno if isinstance(bank_fno, dict) else {})
    live_fno = all(
        isinstance(row, dict) and str(row.get("source") or "").lower() == "live-nse-api"
        for row in (nifty_fno, bank_fno)
    )
    fno_date = (
        nifty_fno.get("as_of") if live_fno and isinstance(nifty_fno, dict)
        else fno_status.get("latest_date", "n/a") if isinstance(fno_status, dict) else "n/a"
    )
    expiry_notes = " · ".join(
        [
            expiry_awareness(now, "NIFTY", nifty),
            expiry_awareness(now, "BANKNIFTY", bank),
        ]
    )
    expiry_caution = (
        "On expiry sessions, open interest and PCR can change quickly due to rolls/unwinds; "
        "treat max pain and call/put walls as context and re-check after the first 30–60 minutes."
    )
    fno_rows = []
    for label, row in (("NIFTY", nifty), ("BANKNIFTY", bank)):
        fno_rows.append(
            [
                esc(label),
                fmt_num(row.get("pcr_oi"), 2),
                fmt_num(row.get("max_pain")),
                fmt_num(row.get("max_call_oi_strike")),
                fmt_num(row.get("max_put_oi_strike")),
                "Buildup unavailable" if str(row.get("buildup") or "").upper() == "LIVE_CHAIN" else esc(row.get("buildup") or "n/a"),
                esc(fno_read(row)),
            ]
        )

    fno_stock_rows = []
    for row in (fno_top.get("rows") if isinstance(fno_top, dict) else []) or []:
        fno_stock_rows.append(
            [
                f"<strong>{symbol_link(row.get('symbol'))}</strong>",
                fmt_num(row.get("futures_price_change_pct"), 2) + "%",
                fmt_num(row.get("futures_oi"), 0),
                f"{fmt_num(row.get('pcr_oi'), 2)} / {fmt_num(row.get('pcr_volume'), 2)}",
                f"{fmt_num(row.get('max_call_oi_strike'))} / {fmt_num(row.get('max_put_oi_strike'))}",
                f"{fmt_num(row.get('max_pain'))} ({fmt_num(row.get('distance_from_max_pain_pct'), 2)}% vs spot)",
                esc(fno_stock_read(row)),
            ]
        )

    moves = global_view.get("moves") if isinstance(global_view, dict) else {}
    regions = global_view.get("regions") if isinstance(global_view, dict) else {}
    global_as_of = global_view.get("as_of", "n/a") if isinstance(global_view, dict) else "n/a"
    global_rows = []
    for asset in ["S&P 500", "Nasdaq", "Hang Seng", "Nikkei 225", "Gold", "Crude Oil", "Copper", "DXY", "USDINR"]:
        row = moves.get(asset) or {}
        global_rows.append(
            [
                esc(asset),
                fmt_num(row.get("price")),
                f'<span class="{css_class(row.get("pct_change"))}">{fmt_pct(row.get("pct_change"))}</span>',
                esc(row.get("as_of") or "n/a"),
            ]
        )

    source_items = [
        ("Domestic indices", "terminal.tools.get_live_market_overview", as_of),
        ("Top movers", mover_source, mover_as_of),
        ("Momentum", str(momentum.get("data_source", "n/a") if isinstance(momentum, dict) else "n/a"), str(momentum_date)),
        ("F&O", str(nifty_fno.get("source", "n/a")) if isinstance(nifty_fno, dict) else "n/a", str(fno_date)),
        ("Global", str(global_view.get("source", "n/a") if isinstance(global_view, dict) else "n/a"), str(global_as_of)),
    ]

    leader_html = bar_rows(leaders[:10], positive=True)
    laggard_html = bar_rows(laggards[:10], positive=False)
    gainers_table = table(["Symbol", "Move", "Stage", "Signal", "RS/RSI"], [stock_row(row) for row in gainers[:10]])
    losers_table = table(["Symbol", "Move", "Stage", "Signal", "RS/RSI"], [stock_row(row) for row in losers[:8]])
    momentum_table = table(
        ["Symbol", "1M Move", "RS", "RSI", "Signal"],
        [
            [
                f"<strong>{symbol_link(row.get('symbol'))}</strong><br><span>{esc(row.get('sector') or row.get('company_name') or '')}</span>",
                f'<span class="{css_class(row.get("change"))}">{fmt_pct(row.get("change"))}</span>',
                fmt_num(row.get("rs_pct", row.get("relative_strength")), 1),
                fmt_num(row.get("rsi"), 1),
                esc(stock_signal_label(row.get("trading_signal"))),
            ]
            for row in momentum_rows_raw[:10]
        ],
    )
    global_table = table(["Asset", "Price", "Move", "As of"], global_rows)
    fno_table = table(["Instrument", "PCR OI", "Max Pain", "Call Wall", "Put Wall", "Buildup", "Read"], fno_rows)
    fno_stock_table = table(
        ["Symbol", "Fut Px Δ", "Fut OI", "PCR OI / Vol", "CE / PE Wall", "Max Pain", "Evidence read"],
        fno_stock_rows[:10],
    )
    broad_table = table(["Area", "Level", "Move", "Day Range", "Read"], broad_rows)

    source_rows = table(["Evidence", "Source", "As of"], [[esc(a), esc(b), esc(c)] for a, b, c in source_items])
    warning_html = ""
    if errors:
        warning_html = "<div class=\"warning\"><strong>Data warnings</strong><ul>" + "".join(f"<li>{esc(e)}</li>" for e in errors) + "</ul></div>"

    region_badges = ""
    for name, row in regions.items():
        region_badges += f'<span class="pill">{esc(name)} {fmt_pct(row.get("avg_pct_change"))} - {esc(row.get("bias"))}</span>'
    top_gainer = gainers[0] if gainers else {}
    top_loser = losers[0] if losers else {}
    movers_note = (
        f"Top gainers are supplemented from {', '.join(fallback_labels)} because the NIFTY 500 mover feed returned only "
        f"{len((movers.get('gainers') if isinstance(movers, dict) else []) or [])} positive row(s)."
        if fallback_labels
        else f"Top movers are sourced from {mover_source} as of {mover_as_of}."
    )
    retail_commentary = generate_retail_investor_commentary(
        report_label=cfg["page_title"],
        commentary_context=cfg["commentary_context"],
        confirmation_window=cfg["confirmation_window"],
        stance=stance,
        stance_detail=stance_detail,
        stance_caution=stance_caution,
        indices=indices,
        leaders=leaders,
        laggards=laggards,
        gainers=gainers,
        losers=losers,
        momentum_rows=momentum_rows_raw,
        nifty_fno=nifty,
        bank_fno=bank,
        global_view=global_view if isinstance(global_view, dict) else {},
        as_of=as_of,
    )
    retail_takeaways_html = bullet_items(list(retail_commentary.get("takeaways") or []))

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(cfg["page_title"])} - {esc(as_of)}</title>
  <style>
    :root {{
      --bg:#0d1117; --panel:#161b22; --panel2:#1c2128; --line:#30363d;
      --ink:#e6edf3; --muted:#8b949e; --good:#3fb950; --bad:#f85149;
      --amber:#d29922; --blue:#58a6ff; --teal:#2dd4bf; --soft:#111820;
      --shadow:0 18px 50px rgba(0,0,0,.24);
    }}
    * {{ box-sizing:border-box; }}
    html, body {{ max-width:100%; overflow-x:hidden; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:linear-gradient(180deg,#0d1117,#111820 42%,#0d1117); font-size:13px; }}
    a {{ color:var(--blue); text-decoration-color:rgba(88,166,255,.55); }}
    a:visited {{ color:var(--teal); }}
    a:hover, a:focus-visible {{ color:#9ecbff; }}
    .page {{ width:min(1220px, calc(100% - 32px)); margin:0 auto; padding:28px 0 44px; }}
    .brandbar {{ display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:14px; }}
    .brand {{ display:flex; align-items:center; gap:10px; min-width:0; }}
    .logo {{ width:38px; height:38px; border-radius:10px; display:grid; place-items:center; background:linear-gradient(135deg,#1f6feb,#2dd4bf); color:#fff; font-weight:900; letter-spacing:0; box-shadow:0 8px 22px rgba(31,111,235,.28); }}
    .brand-title {{ font-weight:850; letter-spacing:.08em; text-transform:uppercase; font-size:12px; color:var(--blue); }}
    .brand-sub {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; margin-top:2px; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1.4fr) minmax(300px,.6fr); gap:18px; align-items:stretch; padding:26px; background:linear-gradient(135deg,rgba(88,166,255,.12),rgba(45,212,191,.07)), var(--panel); border:1px solid var(--line); box-shadow:var(--shadow); overflow:hidden; }}
    h1 {{ margin:0; font-size:clamp(32px,5vw,58px); line-height:.95; letter-spacing:0; overflow-wrap:break-word; }}
    h2 {{ margin:0 0 12px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0 0 10px; font-size:14px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
    p {{ color:var(--muted); line-height:1.55; overflow-wrap:anywhere; }}
    .kicker {{ color:var(--blue); font-weight:800; text-transform:uppercase; letter-spacing:.12em; font-size:12px; margin-bottom:8px; }}
    .hero-main {{ min-width:0; }}
    .hero-main p {{ max-width:760px; font-size:17px; }}
    .mobile-brief {{ display:none; }}
    .status-card {{ background:#0d1117; color:#fff; padding:20px; display:flex; flex-direction:column; justify-content:space-between; min-height:210px; min-width:0; border:1px solid rgba(88,166,255,.24); }}
    .status-card strong {{ font-size:28px; line-height:1.05; }}
    .status-card span {{ color:#c9d1d9; display:block; min-width:0; max-width:100%; white-space:normal; overflow-wrap:anywhere; }}
    .status-short {{ display:none !important; }}
    .audience {{ margin-top:16px; display:grid; grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr); gap:16px; }}
    .audience-panel {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:18px; box-shadow:0 10px 28px rgba(0,0,0,.16); min-width:0; }}
    .audience-panel strong {{ color:var(--ink); }}
    .audience-list {{ margin:0; padding-left:18px; color:var(--muted); line-height:1.65; }}
    .commentary {{ background:linear-gradient(180deg,rgba(45,212,191,.08),rgba(22,27,34,.98)); border-color:rgba(45,212,191,.34); }}
    .commentary h2 {{ margin-bottom:4px; }}
    .commentary-title {{ color:var(--teal); font-size:12px; font-weight:850; text-transform:uppercase; letter-spacing:.1em; margin-bottom:8px; }}
    .commentary-body p {{ margin:10px 0 0; color:#c9d1d9; font-size:14px; line-height:1.65; }}
    .commentary-meta {{ margin-top:12px; color:var(--muted); font-size:11px; }}
    .pill-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
    .pill {{ display:inline-flex; gap:6px; align-items:center; padding:7px 10px; border:1px solid var(--line); background:var(--panel2); color:var(--ink); font-size:12px; font-weight:700; max-width:100%; overflow-wrap:anywhere; }}
    .grid {{ display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; margin-top:16px; }}
    .panel {{ grid-column:span 6; background:var(--panel); border:1px solid var(--line); box-shadow:0 10px 28px rgba(0,0,0,.16); padding:18px; min-width:0; border-radius:10px; }}
    .panel.wide {{ grid-column:span 12; }}
    .panel.third {{ grid-column:span 4; }}
    .panel.movers {{ border-color:rgba(88,166,255,.36); background:linear-gradient(180deg,rgba(88,166,255,.08),rgba(22,27,34,.98)); }}
    .section-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap; margin-bottom:12px; }}
    .section-head p {{ margin:0; font-size:12px; max-width:560px; }}
    .mover-spotlight {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-bottom:12px; }}
    .spot {{ border:1px solid var(--line); background:var(--panel2); padding:12px; border-radius:8px; }}
    .spot label {{ display:block; color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.08em; margin-bottom:4px; }}
    .spot strong {{ display:block; font-size:18px; }}
    .spot span {{ display:block; margin-top:4px; }}
    .metric-strip {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:16px; }}
    .metric {{ border:1px solid var(--line); background:var(--panel); padding:12px; min-height:88px; border-radius:8px; }}
    .metric label {{ display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }}
    .metric strong {{ display:block; font-size:22px; margin-top:6px; }}
    .metric span {{ font-size:13px; }}
    .table-wrap {{ overflow:auto; max-width:100%; border:1px solid var(--line); background:var(--panel); border-radius:8px; }}
    table {{ width:100%; border-collapse:collapse; min-width:620px; }}
    th {{ background:var(--panel2); color:var(--muted); text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.08em; padding:10px; white-space:nowrap; }}
    td {{ border-top:1px solid #21262d; padding:10px; vertical-align:top; font-size:13px; }}
    td span {{ color:var(--muted); font-size:12px; }}
    .pos {{ color:var(--good); font-weight:800; }}
    .neg {{ color:var(--bad); font-weight:800; }}
    .flat {{ color:var(--amber); font-weight:800; }}
    .bar-row {{ display:grid; grid-template-columns:minmax(130px,1fr) 1.8fr 72px; gap:10px; align-items:center; padding:9px 0; border-top:1px solid #21262d; }}
    .bar-row:first-child {{ border-top:0; }}
    .bar-label {{ font-weight:750; font-size:13px; }}
    .bar-track {{ height:10px; background:#26303b; overflow:hidden; border-radius:999px; }}
    .bar-track span {{ display:block; height:100%; }}
    .goodbar {{ background:linear-gradient(90deg,var(--teal),#40c057); }}
    .badbar {{ background:linear-gradient(90deg,#e8590c,var(--bad)); }}
    .bar-value {{ text-align:right; font-size:13px; }}
    .callout {{ border-left:4px solid var(--blue); background:rgba(88,166,255,.10); padding:14px; color:var(--ink); }}
    .checklist {{ margin:0; padding-left:18px; color:var(--muted); line-height:1.65; }}
    .warning {{ margin-top:16px; border:1px solid rgba(210,153,34,.45); background:rgba(210,153,34,.10); padding:14px; color:#f2cc8f; }}
    .notice-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:16px; }}
    .notice {{ padding:14px; border:1px solid rgba(88,166,255,.32); background:rgba(88,166,255,.08); color:#c9d1d9; line-height:1.55; border-radius:8px; }}
    .notice strong {{ color:var(--ink); }}
    .notice.caution {{ border-color:rgba(210,153,34,.45); background:rgba(210,153,34,.09); color:#f2cc8f; }}
    .footer {{ margin-top:18px; color:var(--muted); font-size:12px; }}
    @media (max-width: 900px) {{
      .page {{ width:calc(100% - 20px); padding:14px 0 44px; }}
      .hero {{ grid-template-columns:1fr; padding:18px; }}
      .panel, .panel.third {{ grid-column:span 12; }}
      .metric-strip {{ grid-template-columns:1fr 1fr; }}
      .mover-spotlight {{ grid-template-columns:1fr; }}
      .notice-grid {{ grid-template-columns:1fr; }}
      .audience {{ grid-template-columns:1fr; }}
      table {{ min-width:560px; }}
    }}
    @media (max-width: 560px) {{
      .brandbar {{ align-items:stretch; flex-direction:column; }}
      .brandbar > .pill {{ align-self:flex-start; }}
      .hero-main p.hero-copy {{ display:none; }}
      .mobile-brief {{ display:block; color:var(--muted); font-size:15px; line-height:1.45; margin-top:12px; }}
      .status-card {{ min-height:170px; }}
      .status-long {{ display:none !important; }}
      .status-short {{ display:block !important; }}
      .metric-strip {{ grid-template-columns:1fr; }}
      .bar-row {{ grid-template-columns:1fr 76px; }}
      .bar-track {{ grid-column:1 / -1; grid-row:2; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <div class="brandbar">
      <div class="brand">
        <div class="logo">AA</div>
        <div>
          <div class="brand-title">Agent Adda</div>
          <div class="brand-sub">Market intelligence dashboard</div>
        </div>
      </div>
      <span class="pill">Educational market intelligence - not advice</span>
    </div>
    <section class="hero">
      <div class="hero-main">
        <div class="kicker">{esc(cfg["kicker"])}</div>
        <h1>{esc(stance)}</h1>
        <p class="hero-copy">{esc(stance_detail)} {esc(stance_caution)} {esc(cfg["hero_confirm"])}</p>
        <div class="mobile-brief">{esc(mobile_stance)}</div>
        <div class="pill-row">
          <span class="pill">As of {esc(as_of)}</span>
          <span class="pill">Domestic live runtime</span>
          <span class="pill">F&O date {esc(fno_date)}</span>
          <span class="pill">Momentum date {esc(momentum_date)}</span>
        </div>
      </div>
      <aside class="status-card">
        <span>{esc(cfg["status_label"])}</span>
        <strong>{esc(stance)}</strong>
        <span class="status-long">{esc((global_view.get('risk_regime') if isinstance(global_view, dict) else 'n/a') or 'n/a')} global backdrop - educational market intelligence only.</span>
        <span class="status-short">Research only.</span>
      </aside>
    </section>

    <section class="audience" aria-label="Audience and retail investor summary">
      <div class="audience-panel">
        <div class="commentary-title">Who this report is for</div>
        <h2>{esc(cfg["audience_title"])}</h2>
        <p>{esc(cfg["audience_intro"])}</p>
        <ul class="audience-list">
          <li>Best suited for investors who already track indices, sectors, watchlists, and basic technical context.</li>
          <li>Useful for spotting leadership, weak pockets, momentum names, F&O context, and confirmation levels.</li>
          <li>Not a trade-call sheet, portfolio recommendation, or substitute for suitability-based advice.</li>
        </ul>
      </div>
      <div class="audience-panel commentary">
        <div class="commentary-title">Retail investor commentary</div>
        <h2>{esc(retail_commentary.get('headline'))}</h2>
        <div class="commentary-body">
          {paragraphs(str(retail_commentary.get('commentary') or ''))}
        </div>
        <ul class="audience-list">
          {retail_takeaways_html}
        </ul>
        <div class="commentary-meta">Summary source: {esc(retail_commentary.get('source'))}. Grounded only in report evidence.</div>
      </div>
    </section>

    <section class="metric-strip">
      <div class="metric"><label>NIFTY 50</label><strong>{fmt_num((indices.get('NIFTY 50') or {}).get('last'))}</strong><span class="{css_class((indices.get('NIFTY 50') or {}).get('pct_change'))}">{fmt_pct((indices.get('NIFTY 50') or {}).get('pct_change'))}</span></div>
      <div class="metric"><label>Bank Nifty</label><strong>{fmt_num((indices.get('NIFTY BANK') or {}).get('last'))}</strong><span class="{css_class((indices.get('NIFTY BANK') or {}).get('pct_change'))}">{fmt_pct((indices.get('NIFTY BANK') or {}).get('pct_change'))}</span></div>
      <div class="metric"><label>Smallcap 250</label><strong>{fmt_num((indices.get('NIFTY SMALLCAP 250') or {}).get('last'))}</strong><span class="{css_class((indices.get('NIFTY SMALLCAP 250') or {}).get('pct_change'))}">{fmt_pct((indices.get('NIFTY SMALLCAP 250') or {}).get('pct_change'))}</span></div>
      <div class="metric"><label>India VIX</label><strong>{fmt_num((indices.get('INDIA VIX') or {}).get('last'))}</strong><span class="{css_class(-1 * (num((indices.get('INDIA VIX') or {}).get('pct_change'), 0.0) or 0.0))}">{fmt_pct((indices.get('INDIA VIX') or {}).get('pct_change'))}</span></div>
    </section>

    <section class="grid">
      <div class="panel wide">
        <h2>Domestic Index Pulse</h2>
        {broad_table}
      </div>
      <div class="panel wide movers">
        <div class="section-head">
          <div>
            <h2>Market Movers: Top Gainers And Losers</h2>
            <p>{esc(movers_note)}</p>
          </div>
          <span class="pill">Mover source as of {esc(mover_as_of)}</span>
        </div>
        <div class="mover-spotlight">
          <div class="spot">
            <label>Top gainer</label>
            <strong>{symbol_link(top_gainer.get('symbol'))}</strong>
            <span class="{css_class(top_gainer.get('pct_change', top_gainer.get('change_1d_pct')))}">{fmt_pct(top_gainer.get('pct_change', top_gainer.get('change_1d_pct')))}</span>
          </div>
          <div class="spot">
            <label>Top loser</label>
            <strong>{symbol_link(top_loser.get('symbol'))}</strong>
            <span class="{css_class(top_loser.get('pct_change', top_loser.get('change_1d_pct')))}">{fmt_pct(top_loser.get('pct_change', top_loser.get('change_1d_pct')))}</span>
          </div>
        </div>
        <h3>Top Gainers</h3>
        {gainers_table}
        <h3 style="margin-top:16px">Top Losers</h3>
        {losers_table}
      </div>
      <div class="panel">
        <h2>Sector And Index Leaders</h2>
        {leader_html}
      </div>
      <div class="panel">
        <h2>Weak Pockets</h2>
        {laggard_html}
      </div>
      <div class="panel wide">
        <h2>Momentum Leaders</h2>
        <p>Latest momentum screen snapshot: {esc(momentum_date)}. Treat stale rows as watchlist context until current-day price action confirms.</p>
        {momentum_table}
      </div>
      <div class="panel">
        <h2>F&O Index Setup</h2>
        <p>Latest F&O evidence date: {esc(fno_date)}. <strong>Expiry awareness:</strong> {esc(expiry_notes)}. {esc(expiry_caution)} Directional conviction needs price, PCR, OI buildup, and {esc(cfg["fno_confirm"])} to align.</p>
        {fno_table}
      </div>
      <div class="panel">
        <h2>F&O Stock Watch</h2>
        {fno_stock_table}
      </div>
      <div class="panel wide">
        <h2>Global And Commodity Cues</h2>
        <div class="pill-row">{region_badges}</div>
        {global_table}
      </div>
      <div class="panel third">
        <h3>Confirm</h3>
        <ul class="checklist">
          <li>{esc(cfg["confirm_1"])}</li>
          <li>Bank Nifty stops lagging or financial services keeps absorbing weakness.</li>
          <li>Small/microcap strength holds without VIX rising.</li>
        </ul>
      </div>
      <div class="panel third">
        <h3>Respect</h3>
        <ul class="checklist">
          <li>Avoid chasing leaders with RSI above 80 or large one-day gaps.</li>
          <li>Treat F&O as neutral unless PCR and buildup confirm with price.</li>
          <li>Prefer sectors with both index strength and stock-level breadth.</li>
        </ul>
      </div>
      <div class="panel third">
        <h3>Watch</h3>
        <ul class="checklist">
          <li>Capital markets, IT, metals, realty, and broad-market quality momentum.</li>
          <li>Consumer durables, PSU banks, pharma, defence, and auto if weakness persists.</li>
          <li>Crude, USDINR, DXY, and FII/DII flow confirmation.</li>
        </ul>
      </div>
      <div class="panel wide">
        <h2>Evidence And Freshness</h2>
        {source_rows}
        {warning_html}
        <div class="notice-grid">
          <div class="notice"><strong>AI and data-grounding note:</strong> {esc(AI_GROUNDING_NOTE)}</div>
          <div class="notice caution"><strong>Disclaimer / SEBI-aligned investor caution:</strong> {esc(SEBI_CAUTION)}</div>
        </div>
        <div class="footer">Generated by scripts/build_morning_market_report.py. Educational market intelligence only; not investment advice.</div>
      </div>
    </section>
  </main>
</body>
</html>
"""

    dated_dir.mkdir(parents=True, exist_ok=True)
    latest_out.parent.mkdir(parents=True, exist_ok=True)
    dated_out = dated_dir / f"{cfg['archive_prefix']}_{stamp}.html"
    latest_out.write_text(html_doc, encoding="utf-8")
    dated_out.write_text(html_doc, encoding="utf-8")
    return html_doc, latest_out, dated_out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Agent Adda market status HTML dashboard.")
    parser.add_argument("--variant", choices=sorted(REPORT_VARIANTS), default="morning")
    args = parser.parse_args()

    html_doc, latest, dated = build_report(variant=args.variant)
    print(json.dumps({"variant": args.variant, "latest": str(latest), "dated": str(dated), "bytes": len(html_doc)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
