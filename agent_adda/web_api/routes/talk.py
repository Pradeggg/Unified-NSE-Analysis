"""Talk 2 Stocks MVP routes.

This route is intentionally deterministic-first. It resolves symbols, gathers
Agent Adda evidence, then optionally uses the configured OpenAI synthesis model
when an API key is available. Missing evidence is returned explicitly so the
10-user MVP can run in permissive mode without pretending completeness.
"""
from __future__ import annotations

import csv
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from ..schemas import (
    TalkAction,
    TalkChatRequest,
    TalkChatResponse,
    TalkCompareRequest,
    TalkEvidenceItem,
    TalkScreenerRequest,
)

router = APIRouter()

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
_DEFAULT_WATCHLIST = ["NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "SBIN"]

_STOPWORDS = {
    "A", "ABOUT", "ADD", "AN", "AND", "ARE", "AS", "AT", "BUY", "CAN", "COMPARE", "DO",
    "FOR", "FROM", "GOOD", "HOW", "IN", "INDEX", "IS", "IT", "LOOKING", "ME", "MY",
    "OF", "ON", "OR", "SECTOR", "SELL", "SHOW", "STOCK", "STOCKS", "THE", "THIS",
    "TODAY", "TRACK", "VS", "WATCH", "WATCHLIST", "WHAT", "WITH",
}
_TASK_WORDS = {
    "CURRENT",
    "ANALYSE", "ANALYZE", "ANALYSIS", "BRIEF", "BRIEFLY", "DEEP", "DIVE",
    "FINANCIAL", "FINANCIALS", "FUNDAMENTAL", "FUNDAMENTALS", "LATEST",
    "QUICK", "QUICKLY", "RECENT", "RESEARCH", "RESULT", "RESULTS",
    "TECHNICAL", "TECHNICALS",
}
_AMBIGUOUS_SINGLE_TOKEN_PREFIXES = {
    "ADANI", "ASIAN", "AXIS", "BAJAJ", "BHARAT", "HDFC", "HINDUSTAN", "KOTAK",
    "LARSEN", "MAHINDRA", "PREMIER", "STATE", "SUN", "TATA",
}

_PRICE_FIELDS = ("price", "live_price", "db_price", "current_price", "latest_close")
_INDEX_ALIASES = {
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
    "NIFTY 50": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "BANK NIFTY": "NIFTY BANK",
    "NIFTY BANK": "NIFTY BANK",
    "FINNIFTY": "NIFTY FIN SERVICE",
    "NIFTY FIN": "NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NIFTY MID SELECT",
    "MIDCAP NIFTY": "NIFTY MID SELECT",
}
_LOCAL_SYMBOLS: set[str] | None = None
_LOCAL_NAME_ALIASES: dict[str, str] | None = None
_SESSION_MEMORY: dict[str, dict[str, Any]] = {}
_CONTEXT_RE = re.compile(r"\b(it|its|this|that|these|those|them|same|above|previous|earlier)\b", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"\b(gaps?|evidence|sources?|freshness|stale|missing|used)\b", re.IGNORECASE)
_ADVICE_RE = re.compile(r"\b(should\s+i\s+(buy|sell)|can\s+i\s+(buy|sell)|buy\s+it|sell\s+it|recommend|advice)\b", re.IGNORECASE)
_FINANCIAL_RE = re.compile(
    r"\b("
    r"fundamentals?|financials?|revenue|sales|profit|pat|eps|quarterly|results?|"
    r"margin|opm|earnings|balance\s+sheet|cash\s*flow|borrowings?|debt|"
    r"dividend|valuation|roe|roce"
    r")\b",
    re.IGNORECASE,
)
_INTRADAY_RE = re.compile(r"\b(intraday|live\s+quote|live\s+price|quote|snapshot|5m|15m|30m|1h|orb|vwap)\b", re.IGNORECASE)

_SCREENERS: dict[str, dict[str, Any]] = {
    "stage2": {"label": "Stage 2 stocks", "tool": "run_screener_query", "screen_type": "stage2"},
    "new_highs": {"label": "New highs", "tool": "run_screener_query", "screen_type": "new_highs"},
    "high_rs": {"label": "High RS leaders", "tool": "run_screener_query", "screen_type": "high_rs"},
    "momentum_52w": {"label": "Momentum 52-week leaders", "tool": "run_screener_query", "screen_type": "momentum_52w"},
    "turnaround": {"label": "Turnaround setups", "tool": "run_screener_query", "screen_type": "turnaround"},
    "stage1_base": {"label": "Stage 1 bases", "tool": "run_screener_query", "screen_type": "stage1_base"},
    "tight_range": {"label": "Tight range / VCP-like setups", "tool": "run_screener_query", "screen_type": "tight_range"},
    "oversold_bounce": {"label": "Oversold bounce", "tool": "run_screener_query", "screen_type": "oversold_bounce"},
    "supertrend_buy": {"label": "Supertrend buy", "tool": "run_screener_query", "screen_type": "supertrend_buy"},
    "strong_buy": {"label": "Strong buy signals", "tool": "run_screener_query", "screen_type": "strong_buy"},
    "new_entrants": {"label": "New Stage 2 entrants", "tool": "run_screener_query", "screen_type": "new_entrants"},
    "quality_breakouts": {"label": "Quality breakout screener", "tool": "run_quality_breakout_screener", "mode": "balanced"},
    "long_term_growth": {"label": "Long-term growth candidates", "tool": "get_long_term_growth_candidates", "index_scope": "MIDCAP"},
    "watchlist_strength": {"label": "Strength watchlist validation", "tool": "validate_strength_watchlist"},
}

_SCREENER_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("watchlist_strength", ("watchlist strength", "validate watchlist", "strength validation", "validate my watchlist")),
    ("quality_breakouts", ("quality breakout", "quality breakouts", "quality screener")),
    ("long_term_growth", ("long term growth", "long-term growth", "growth candidates", "compounder candidates")),
    ("new_entrants", ("new stage 2", "new stage2", "stage 2 entrants", "stage2 entrants", "new entrants")),
    ("stage1_base", ("stage 1 base", "stage1 base", "stage 1 bases", "stage1 bases", "basing stocks")),
    ("tight_range", ("tight range", "vcp-like", "vcp like", "vcp setup", "vcp setups", "consolidation setup")),
    ("momentum_52w", ("momentum 52", "52-week momentum", "52 week momentum", "momentum leaders")),
    ("new_highs", ("new highs", "52-week high", "52 week high", "near 52w high")),
    ("high_rs", ("high rs", "relative strength leaders", "rs leaders", "strong rs")),
    ("oversold_bounce", ("oversold bounce", "oversold stage 2", "rsi below 40")),
    ("supertrend_buy", ("supertrend buy", "supertrend bullish")),
    ("strong_buy", ("strong buy", "strong_buy")),
    ("turnaround", ("turnaround", "recovery setup", "recovery setups")),
    ("stage2", ("stage 2", "stage2")),
)

_MANUAL_COMPANY_ALIASES = {
    "AXIS BANK": "AXISBANK",
    "KOTAK MAHINDRA BANK": "KOTAKBANK",
}


def _tools():
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    os.environ.setdefault("AGENT_ADDA_SKIP_VENV_CHECK", "1")
    import terminal.tools as t
    return t


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _fmt(value: Any, suffix: str = "") -> str:
    num = _coerce_float(value)
    if num is None:
        return "n/a"
    if abs(num) >= 100:
        out = f"{num:,.0f}"
    else:
        out = f"{num:.1f}"
    return f"{out}{suffix}"


def _md_cell(value: Any) -> str:
    return str(value if value not in (None, "") else "n/a").replace("|", "\\|")


def _md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return []
    lines = [
        "| " + " | ".join(_md_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _header in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_md_cell(cell) for cell in row) + " |" for row in rows)
    return lines


def _fmt_crore(value: Any) -> str:
    num = _coerce_float(value)
    if num is None:
        return "n/a"
    return f"{num:,.0f}"


def _fmt_eps(value: Any) -> str:
    num = _coerce_float(value)
    if num is None:
        return "n/a"
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _score_label(value: Any) -> str:
    num = _coerce_float(value)
    if num is None:
        return "n/a"
    if num >= 75:
        return "strong"
    if num >= 60:
        return "constructive"
    if num >= 45:
        return "mixed"
    return "weak"


def _technical_assessment(snapshot: dict[str, Any], technicals: dict[str, Any]) -> str:
    stage = str(snapshot.get("stage") or "").upper()
    trend = str(snapshot.get("trend_signal") or "").upper()
    score = _coerce_float(snapshot.get("technical_score") or technicals.get("technical_score"))
    if "STAGE_2" in stage and score is not None and score >= 60:
        return "constructive uptrend setup"
    if "BEARISH" in trend or (score is not None and score < 45):
        return "weak or cautious technical setup"
    if score is not None:
        return f"{_score_label(score)} technical setup"
    return "technical setup unavailable"


def _fundamental_assessment(snapshot: dict[str, Any]) -> str:
    score = (
        snapshot.get("enhanced_fund_score")
        or snapshot.get("fundamental_score")
        or snapshot.get("investment_score")
    )
    label = _score_label(score)
    if label == "n/a":
        return "fundamental score unavailable"
    return f"{label} fundamental profile"


def _snapshot_price(snapshot: dict[str, Any], technicals: dict[str, Any]) -> Any:
    for field in _PRICE_FIELDS:
        if snapshot.get(field) not in (None, ""):
            return snapshot[field]
        if technicals.get(field) not in (None, ""):
            return technicals[field]
    return None


def _canonical_index(value: str) -> str | None:
    raw = re.sub(r"\s+", " ", (value or "").strip().upper())
    if not raw:
        return None
    if raw in _INDEX_ALIASES:
        return _INDEX_ALIASES[raw]
    match = re.match(r"^NIFTY(\d{2,4})$", raw)
    if match:
        return f"NIFTY {match.group(1)}"
    if raw.startswith("NIFTY ") and any(token in raw for token in ("BANK", "IT", "AUTO", "PHARMA", "FMCG", "METAL", "ENERGY", "FIN")):
        return raw
    return None


def _trusted_symbol_resolution(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict) or not result.get("symbol"):
        return False
    band = str(result.get("confidence_band") or "").lower()
    if band in {"exact", "high"}:
        return True
    try:
        return float(result.get("score") or 0.0) >= 0.85
    except Exception:
        return False


def _resolution_gap(candidate: str, result: dict[str, Any] | None) -> str:
    if isinstance(result, dict):
        sym = str(result.get("symbol") or "").strip().upper()
        candidates = [str(c).strip().upper() for c in (result.get("candidates") or []) if str(c).strip()]
        band = str(result.get("confidence_band") or result.get("confidence") or "none")
        if sym:
            candidates = list(dict.fromkeys([sym, *candidates]))[:5]
            return f"{candidate}: unresolved; weak/ambiguous match ({band}) candidates: {', '.join(candidates)}"
        if candidates:
            return f"{candidate}: unresolved; candidates: {', '.join(list(dict.fromkeys(candidates))[:5])}"
        error = str(result.get("error") or "").strip()
        if error:
            return f"{candidate}: {error}"
    return f"{candidate}: unresolved symbol"


def _resolve_stock_candidate(candidate: str) -> tuple[str | None, str]:
    text = (candidate or "").strip()
    if not text or _canonical_index(text):
        return None, ""
    alias_symbol = _local_company_alias(text)
    if alias_symbol:
        return alias_symbol, ""
    weak_suffix_symbol = _weak_company_suffix_symbol(text)
    if weak_suffix_symbol:
        return None, f"{text}: unresolved; weak/ambiguous match (local_suffix) candidates: {weak_suffix_symbol}"
    if (
        text.upper() in _AMBIGUOUS_SINGLE_TOKEN_PREFIXES
        and not _is_local_symbol(text)
    ):
        return None, f"{text}: ambiguous company prefix; use the full company name"
    t = _tools()
    resolvers = []
    if hasattr(t, "_resolve_local_symbol"):
        resolvers.append(t._resolve_local_symbol)
    resolvers.append(t.resolve_symbol)
    last_result: dict[str, Any] | None = None
    for resolver in resolvers:
        try:
            result = resolver(text)
        except Exception:
            continue
        last_result = result
        sym = str(result.get("symbol") or "").strip().upper()
        if sym and _trusted_symbol_resolution(result):
            return sym, ""
    if re.fullmatch(r"[A-Z0-9&-]{2,16}", text.upper()) and _is_local_symbol(text):
        return text.upper(), ""
    return None, _resolution_gap(text, last_result)


def _question_tokens(question: str) -> list[tuple[str, str]]:
    return [(match.group(0), match.group(0).upper()) for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9&-]{1,20}\b", question)]


def _resolve_query_symbols_with_gaps(question: str, watchlist: list[str]) -> tuple[list[str], list[str]]:
    symbols: list[str] = []
    gaps: list[str] = []
    token_pairs = _question_tokens(question)
    raw_tokens = [upper for _raw, upper in token_pairs]
    consumed: set[int] = set()

    max_window = min(5, len(raw_tokens))
    for size in range(max_window, 1, -1):
        for start in range(0, len(raw_tokens) - size + 1):
            positions = set(range(start, start + size))
            if consumed & positions:
                continue
            phrase_tokens = raw_tokens[start:start + size]
            if all(token in _STOPWORDS for token in phrase_tokens):
                continue
            if any(token in _TASK_WORDS for token in phrase_tokens):
                continue
            phrase = " ".join(phrase_tokens)
            sym, gap = _resolve_stock_candidate(phrase)
            if sym and sym not in symbols:
                symbols.append(sym)
                consumed.update(positions)
            elif gap and not any(token in _STOPWORDS for token in phrase_tokens):
                gaps.append(gap)
                if "ambiguous company prefix" in gap or "weak/ambiguous" in gap:
                    consumed.update(positions)

    watch = {s.strip().upper() for s in watchlist if s.strip()}
    candidates = []
    for idx, token in enumerate(raw_tokens):
        if idx in consumed:
            continue
        if token in _STOPWORDS or token in _TASK_WORDS:
            continue
        if token in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"} or token in watch:
            candidates.append(token)
        elif token.isupper() and len(token) >= 3:
            candidates.append(token)

    for token in candidates:
        sym, gap = _resolve_stock_candidate(token)
        if sym and sym not in symbols:
            symbols.append(sym)
        elif gap:
            gaps.append(gap)
    return symbols[:10], list(dict.fromkeys(gaps))


def _resolve_query_symbols(question: str, watchlist: list[str]) -> list[str]:
    symbols, _gaps = _resolve_query_symbols_with_gaps(question, watchlist)
    return symbols


def _resolve_query_indices(question: str, watchlist: list[str]) -> list[str]:
    found: list[str] = []
    # Only the active question should trigger index routing. The watchlist often
    # contains default indices such as NIFTY/BANKNIFTY, and those must not
    # override a stock-specific compare prompt.
    del watchlist
    haystack = question.upper()
    ordered_aliases = sorted(_INDEX_ALIASES, key=len, reverse=True)
    for alias in ordered_aliases:
        if re.search(rf"\b{re.escape(alias)}\b", haystack):
            canonical = _INDEX_ALIASES[alias]
            if canonical not in found:
                found.append(canonical)
    for match in re.findall(r"\bNIFTY\s*\d{2,4}\b", haystack):
        canonical = _canonical_index(match)
        if canonical and canonical not in found:
            found.append(canonical)
    return found[:5]


def _strip_index_symbols(symbols: list[str], indices: list[str]) -> list[str]:
    if not indices:
        return symbols
    index_tokens = set(_INDEX_ALIASES.keys()) | {value.replace(" ", "") for value in _INDEX_ALIASES.values()}
    return [symbol for symbol in symbols if symbol.upper() not in index_tokens]


def _is_local_symbol(symbol: str) -> bool:
    global _LOCAL_SYMBOLS
    sym = symbol.strip().upper()
    if not sym:
        return False
    if _LOCAL_SYMBOLS is None:
        loaded: set[str] = set()
        csv_paths = [
            _REPO_ROOT / "data" / "nse_sec_full_data.csv",
            _REPO_ROOT / "data" / "signal_log.csv",
            _REPO_ROOT / "data" / "fno_signals.csv",
        ]
        for path in csv_paths:
            if not path.exists():
                continue
            try:
                with path.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        raw = row.get("SYMBOL") or row.get("symbol")
                        if raw:
                            loaded.add(str(raw).strip().strip('"').upper())
            except Exception:
                continue
        _LOCAL_SYMBOLS = loaded
    return sym in _LOCAL_SYMBOLS


def _normalise_company_key(value: str) -> str:
    raw = re.sub(r"[^A-Z0-9& ]+", " ", (value or "").upper())
    raw = re.sub(r"\b(LIMITED|LTD|PVT|PRIVATE)\b", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _local_company_alias(query: str) -> str | None:
    global _LOCAL_NAME_ALIASES
    key = _normalise_company_key(query)
    if not key:
        return None
    if _LOCAL_NAME_ALIASES is None:
        aliases: dict[str, str] = dict(_MANUAL_COMPANY_ALIASES)
        csv_paths = [
            _REPO_ROOT / "data" / "signal_log.csv",
        ]
        for path in csv_paths:
            if not path.exists():
                continue
            try:
                with path.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        symbol = str(row.get("symbol") or row.get("SYMBOL") or "").strip().upper()
                        company = str(row.get("company") or row.get("company_name") or "").strip()
                        if symbol and company:
                            aliases.setdefault(_normalise_company_key(company), symbol)
            except Exception:
                continue
        _LOCAL_NAME_ALIASES = aliases
    return _LOCAL_NAME_ALIASES.get(key)


def _weak_company_suffix_symbol(query: str) -> str | None:
    key = _normalise_company_key(query)
    if not key.endswith(" COMPANY"):
        return None
    base = key.removesuffix(" COMPANY").strip()
    if base and _is_local_symbol(base):
        return base
    return None


def _session_context(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    return _SESSION_MEMORY.get(session_id)


def _bind_context_symbols(question: str, symbols: list[str], context: dict[str, Any] | None) -> list[str]:
    if not context or not _CONTEXT_RE.search(question):
        return symbols
    prior_symbols = [str(s).strip().upper() for s in (context.get("symbols") or []) if str(s).strip()]
    if not prior_symbols:
        return symbols
    merged = prior_symbols + [s for s in symbols if s not in prior_symbols]
    return merged[:10]


def _bind_context_indices(question: str, indices: list[str], context: dict[str, Any] | None) -> list[str]:
    if not context or not _CONTEXT_RE.search(question):
        return indices
    prior_indices = [str(s).strip().upper() for s in (context.get("indices") or []) if str(s).strip()]
    if not prior_indices:
        return indices
    merged = prior_indices + [s for s in indices if s not in prior_indices]
    return merged[:5]


def _infer_intent(
    question: str,
    symbols: list[str],
    context: dict[str, Any] | None = None,
    indices: list[str] | None = None,
) -> str:
    q = question.lower()
    indices = indices or []
    if _detect_screener_key(question):
        return "screener"
    if _INTRADAY_RE.search(question):
        return "intraday_health"
    if context and _EVIDENCE_RE.search(q) and not symbols:
        return "evidence_review"
    if indices:
        return "index_context"
    if symbols and _ADVICE_RE.search(question):
        return "advice_boundary"
    if symbols and _FINANCIAL_RE.search(question):
        return "financials_review"
    if "watchlist" in q or "track" in q:
        return "watchlist"
    if "compare" in q or " vs " in q or len(symbols) >= 2:
        return "compare"
    if "sector" in q or "breadth" in q or "market" in q or "index" in q:
        return "market_context"
    if symbols:
        return "stock_deep_dive"
    return "general_research"


def _context_evidence(context: dict[str, Any]) -> list[TalkEvidenceItem]:
    evidence: list[TalkEvidenceItem] = []
    for item in context.get("evidence") or []:
        if isinstance(item, TalkEvidenceItem):
            evidence.append(item)
        elif isinstance(item, dict):
            try:
                evidence.append(TalkEvidenceItem(**item))
            except Exception:
                continue
    return evidence


def _symbol_evidence(symbol: str) -> tuple[dict[str, Any], list[TalkEvidenceItem], list[str]]:
    t = _tools()
    gaps: list[str] = []
    evidence: list[TalkEvidenceItem] = []

    snapshot = {}
    technicals = {}

    try:
        snapshot = t.get_symbol_snapshot(symbol)
        if snapshot.get("error"):
            gaps.append(f"{symbol}: {snapshot['error']}")
        gaps.extend(f"{symbol}: missing {x}" for x in (snapshot.get("missing_evidence") or []))
    except Exception as exc:
        gaps.append(f"{symbol}: snapshot unavailable ({exc})")

    try:
        technicals = t.get_technical_setup(symbol)
        if technicals.get("error"):
            gaps.append(f"{symbol}: {technicals['error']}")
        gaps.extend(f"{symbol}: missing {x}" for x in (technicals.get("missing_evidence") or []))
    except Exception as exc:
        gaps.append(f"{symbol}: technicals unavailable ({exc})")

    price = _snapshot_price(snapshot, technicals)
    as_of = str(snapshot.get("snapshot_date") or snapshot.get("price_date") or date.today().isoformat())
    row = {
        "symbol": symbol,
        "company": snapshot.get("company_name") or snapshot.get("name") or symbol,
        "price": price,
        "stage": snapshot.get("stage"),
        "sector": snapshot.get("sector"),
        "rsi": snapshot.get("rsi") or technicals.get("rsi"),
        "technical_score": snapshot.get("technical_score"),
        "technical_assessment": _technical_assessment(snapshot, technicals),
        "investment_score": snapshot.get("investment_score"),
        "fundamental_score": snapshot.get("fundamental_score"),
        "enhanced_fund_score": snapshot.get("enhanced_fund_score"),
        "fundamental_assessment": _fundamental_assessment(snapshot),
        "can_slim_score": snapshot.get("can_slim_score"),
        "minervini_score": snapshot.get("minervini_score"),
        "earnings_quality": snapshot.get("earnings_quality"),
        "sales_growth": snapshot.get("sales_growth"),
        "financial_strength": snapshot.get("financial_strength"),
        "institutional_backing": snapshot.get("institutional_backing"),
        "trend_signal": snapshot.get("trend_signal"),
        "trading_signal": snapshot.get("trading_signal"),
        "supertrend": snapshot.get("supertrend_state") or technicals.get("supertrend_signal"),
        "change_1d_pct": snapshot.get("change_1d_pct"),
        "change_1w_pct": snapshot.get("change_1w_pct"),
        "change_1m_pct": snapshot.get("change_1m_pct"),
        "support": technicals.get("support"),
        "resistance": technicals.get("resistance"),
        "as_of": as_of,
    }

    evidence.extend(
        [
            TalkEvidenceItem(label=f"{symbol} snapshot", value=row, source="get_symbol_snapshot", as_of=as_of),
            TalkEvidenceItem(label=f"{symbol} technicals", value=technicals, source="get_technical_setup", as_of=as_of),
        ]
    )
    return row, evidence, list(dict.fromkeys(gaps))


def _compact_financial_row(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row.get(field) for field in fields if field in row}


def _financial_evidence(symbol: str) -> tuple[dict[str, Any], list[TalkEvidenceItem], list[str]]:
    t = _tools()
    gaps: list[str] = []
    evidence: list[TalkEvidenceItem] = []
    compact: dict[str, Any] = {"symbol": symbol}
    try:
        financials = t.get_cached_financials(symbol)
    except Exception as exc:
        return compact, [], [f"{symbol}: cached financials unavailable ({exc})"]

    if financials.get("error"):
        gaps.append(f"{symbol}: {financials['error']}")
    quarterly = financials.get("quarterly") if isinstance(financials.get("quarterly"), list) else []
    annual = financials.get("annual") if isinstance(financials.get("annual"), list) else []
    balance_sheet = financials.get("balance_sheet") if isinstance(financials.get("balance_sheet"), list) else []
    cash_flow = financials.get("cash_flow") if isinstance(financials.get("cash_flow"), list) else []
    latest_q = quarterly[0] if quarterly and isinstance(quarterly[0], dict) else {}
    latest_annual = annual[0] if annual and isinstance(annual[0], dict) else {}
    latest_bs = balance_sheet[0] if balance_sheet and isinstance(balance_sheet[0], dict) else {}
    latest_cf = cash_flow[0] if cash_flow and isinstance(cash_flow[0], dict) else {}
    if latest_q:
        compact.update(
            {
                "latest_quarter": latest_q.get("period_label"),
                "latest_quarter_end": latest_q.get("period_end"),
                "revenue": latest_q.get("revenue"),
                "pat": latest_q.get("pat"),
                "eps": latest_q.get("eps"),
                "opm_pct": latest_q.get("opm_pct"),
                "financial_source": latest_q.get("source"),
                "financial_source_url": latest_q.get("source_url"),
                "financial_fetched_at": latest_q.get("fetched_at"),
                "financial_unit": "INR crore",
            }
        )
    else:
        gaps.append(f"{symbol}: missing quarterly financials")
    if latest_annual:
        compact["latest_annual"] = _compact_financial_row(
            latest_annual,
            (
                "period_label", "period_end", "revenue", "operating_profit", "opm_pct",
                "pat", "eps", "dividend_payout_pct", "source", "source_url", "fetched_at",
            ),
        )
    else:
        gaps.append(f"{symbol}: missing annual financials")
    if latest_bs:
        compact["latest_balance_sheet"] = _compact_financial_row(
            latest_bs,
            (
                "period_label", "period_end", "reserves", "borrowings", "total_liabilities",
                "fixed_assets", "investments", "total_assets", "net_debt", "source",
                "source_url", "fetched_at",
            ),
        )
    else:
        gaps.append(f"{symbol}: missing balance sheet")
    if latest_cf:
        compact["latest_cash_flow"] = _compact_financial_row(
            latest_cf,
            (
                "period_label", "period_end", "operating_cf", "investing_cf",
                "financing_cf", "net_cf", "source", "source_url", "fetched_at",
            ),
        )
    else:
        gaps.append(f"{symbol}: missing cash flow")

    recent_quarters = [
        _compact_financial_row(
            row,
            ("period_label", "period_end", "revenue", "operating_profit", "opm_pct", "pat", "eps"),
        )
        for row in quarterly[:4]
        if isinstance(row, dict)
    ]
    annual_history = [
        _compact_financial_row(
            row,
            ("period_label", "period_end", "revenue", "operating_profit", "opm_pct", "pat", "eps", "dividend_payout_pct"),
        )
        for row in annual[:4]
        if isinstance(row, dict)
    ]

    evidence.append(
        TalkEvidenceItem(
            label=f"{symbol} cached financials",
            value={
                "unit": "INR crore except EPS and percentages",
                "latest_quarter": compact,
                "recent_quarters": recent_quarters,
                "annual_history": annual_history,
                "latest_balance_sheet": compact.get("latest_balance_sheet"),
                "latest_cash_flow": compact.get("latest_cash_flow"),
                "section_counts": financials.get("section_counts"),
                "data_source": financials.get("data_source"),
            },
            source="get_cached_financials",
            as_of=str(compact.get("financial_fetched_at") or compact.get("latest_quarter_end") or date.today().isoformat()),
        )
    )
    return compact, evidence, list(dict.fromkeys(gaps))


def _extract_top_n(question: str, default: int = 10) -> int:
    match = re.search(r"\b(?:top|show|give)\s+(\d{1,2})\b", question or "", re.IGNORECASE)
    if not match:
        return default
    try:
        return max(1, min(int(match.group(1)), 30))
    except Exception:
        return default


def _detect_screener_key(question: str) -> str | None:
    q = " ".join((question or "").lower().replace("_", " ").split())
    for key, aliases in _SCREENER_ALIASES:
        if any(alias in q for alias in aliases):
            return key
    if "screener" in q or "screen " in q or q.startswith("screen"):
        return "stage2"
    return None


def _safe_screener_row(row: dict[str, Any], *, screen_key: str) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").strip().upper()
    return {
        "symbol": symbol,
        "company": row.get("company_name") or row.get("company") or symbol,
        "sector": row.get("sector"),
        "price": row.get("price") or row.get("latest_close"),
        "stage": row.get("stage"),
        "rsi": row.get("rsi"),
        "relative_strength": row.get("relative_strength") or row.get("rs"),
        "rs_pct": row.get("rs_pct"),
        "change_1d_pct": row.get("change_1d_pct"),
        "change_1m_pct": row.get("change_1m_pct") or row.get("change"),
        "technical_score": row.get("technical_score"),
        "investment_score": row.get("investment_score"),
        "enhanced_fund_score": row.get("enhanced_fund_score"),
        "financial_strength": row.get("financial_strength"),
        "can_slim_score": row.get("can_slim_score"),
        "piotroski_score": row.get("piotroski_score"),
        "strength_score": row.get("strength_score"),
        "composite_score": row.get("composite_score"),
        "trading_signal": row.get("trading_signal"),
        "setup_tags": row.get("setup_tags") or row.get("reason_tags") or [],
        "risk_flags": row.get("risk_flags") or [],
        "verdict": row.get("verdict"),
        "missing_evidence": row.get("missing_evidence") or [],
        "screen_type": screen_key,
    }


def _screener_context(
    screen_key: str,
    *,
    top_n: int = 10,
    watchlist: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[TalkEvidenceItem], list[str], dict[str, Any]]:
    t = _tools()
    spec = _SCREENERS.get(screen_key)
    if not spec:
        available = ", ".join(sorted(_SCREENERS))
        return [], [], [f"Unknown screener '{screen_key}'. Available: {available}"], {"screen_type": screen_key}

    limit = max(1, min(int(top_n or 10), 30))
    tool_name = str(spec["tool"])
    payload: dict[str, Any]
    gaps: list[str] = []
    try:
        if tool_name == "run_screener_query":
            payload = t.run_screener_query(str(spec["screen_type"]), top_n=limit)
        elif tool_name == "run_quality_breakout_screener":
            runner = t.TOOL_REGISTRY["run_quality_breakout_screener"][0]
            payload = runner(top_n=limit, mode=str(spec.get("mode") or "balanced"))
        elif tool_name == "get_long_term_growth_candidates":
            payload = t.get_long_term_growth_candidates(
                index_scope=str(spec.get("index_scope") or "MIDCAP"),
                top_n=limit,
                include_research=False,
            )
        elif tool_name == "validate_strength_watchlist":
            symbols = [s.strip().upper() for s in (watchlist or []) if s.strip()]
            symbols = _strip_index_symbols(symbols, list(_INDEX_ALIASES.values()))
            payload = t.validate_strength_watchlist(symbols, top_n=limit)
        else:
            return [], [], [f"Screener tool '{tool_name}' is not wired in T2S"], {"screen_type": screen_key}
    except Exception as exc:
        return [], [], [f"{screen_key}: screener unavailable ({exc})"], {"screen_type": screen_key, "tool": tool_name}

    if payload.get("error"):
        gaps.append(f"{screen_key}: {payload['error']}")
    gaps.extend(str(x) for x in (payload.get("missing_evidence") or []))
    rows_source = payload.get("results") or payload.get("candidates") or []
    rows = [_safe_screener_row(row, screen_key=screen_key) for row in rows_source if isinstance(row, dict)]
    snapshot_date = (
        payload.get("snapshot_date")
        or payload.get("as_of")
        or (rows[0].get("snapshot_date") if rows else None)
        or date.today().isoformat()
    )
    meta = {
        "screen_type": screen_key,
        "label": spec["label"],
        "tool": tool_name,
        "description": payload.get("description") or spec["label"],
        "snapshot_date": str(snapshot_date),
        "count": payload.get("count", len(rows)),
        "source_counts": payload.get("source_counts"),
        "merged_count": payload.get("merged_count"),
        "passed_count": payload.get("passed_count"),
        "input_symbols": payload.get("input_symbols"),
        "validation_rule": payload.get("validation_rule"),
        "warnings": payload.get("warnings") or [],
    }
    evidence = [
        TalkEvidenceItem(
            label=str(spec["label"]),
            value={**meta, "results": rows[:limit]},
            source=tool_name,
            as_of=str(snapshot_date),
        )
    ]
    return rows[:limit], evidence, list(dict.fromkeys(gaps)), meta


def _intraday_health_context(max_age_minutes: int = 30) -> tuple[dict[str, Any], list[TalkEvidenceItem], list[str]]:
    t = _tools()
    try:
        health = t.get_intraday_source_health(max_age_minutes=max_age_minutes)
    except Exception as exc:
        health = {
            "data_mode": "intraday",
            "overall_status": "MISSING",
            "error": f"intraday health unavailable ({exc})",
            "tables": {},
        }
    gaps: list[str] = []
    status = str(health.get("overall_status") or "UNKNOWN").upper()
    if status not in {"FRESH", "PRESENT"}:
        gaps.append(f"Intraday source health is {status}; live/intraday setup output is gated.")
    if health.get("error"):
        gaps.append(str(health["error"]))
    evidence = [
        TalkEvidenceItem(
            label="Intraday source health",
            value=health,
            source="get_intraday_source_health",
            as_of=date.today().isoformat(),
            freshness="fresh" if status == "FRESH" else "unknown",
        )
    ]
    return health, evidence, list(dict.fromkeys(gaps))


def _market_context() -> tuple[list[dict[str, Any]], list[TalkEvidenceItem], list[str]]:
    path = _REPO_ROOT / "data" / "sector_breadth.csv"
    gaps: list[str] = []
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows, [], ["sector_breadth.csv missing"]

    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                breadth = _coerce_float(row.get("pct_above_50dma"))
                change = _coerce_float(row.get("change_5d"))
                rows.append(
                    {
                        "sector": row.get("sector"),
                        "index_name": row.get("index_name"),
                        "pct_above_50dma": breadth,
                        "change_5d": change,
                        "breadth_signal": row.get("breadth_signal"),
                        "divergence_alert": row.get("divergence_alert"),
                        "as_of": row.get("as_of_date"),
                    }
                )
    except Exception as exc:
        return [], [], [f"sector breadth unavailable ({exc})"]

    rows.sort(key=lambda r: (_coerce_float(r.get("pct_above_50dma")) or -1), reverse=True)
    top = rows[:5]
    as_of = str(top[0].get("as_of") if top else date.today().isoformat())
    evidence = [TalkEvidenceItem(label="Sector breadth leaders", value=top, source="data/sector_breadth.csv", as_of=as_of)]
    return top, evidence, gaps


def _index_context(indices: list[str]) -> tuple[list[dict[str, Any]], list[TalkEvidenceItem], list[str]]:
    t = _tools()
    rows: list[dict[str, Any]] = []
    evidence: list[TalkEvidenceItem] = []
    gaps: list[str] = []

    for index in indices[:5]:
        snapshot: dict[str, Any] = {}
        breadth: dict[str, Any] = {}
        try:
            snapshot = t.get_index_snapshot(index)
            if snapshot.get("error"):
                gaps.append(f"{index}: {snapshot['error']}")
        except Exception as exc:
            gaps.append(f"{index}: index snapshot unavailable ({exc})")

        try:
            breadth = t.get_market_breadth(index)
            if breadth.get("error"):
                gaps.append(f"{index}: {breadth['error']}")
            for missing in breadth.get("missing_evidence") or []:
                if missing == "complete_index_score_coverage" and breadth.get("matched_count"):
                    continue
                gaps.append(f"{index}: missing {missing}")
        except Exception as exc:
            gaps.append(f"{index}: market breadth unavailable ({exc})")

        as_of = str(snapshot.get("as_of") or breadth.get("snapshot_date") or date.today().isoformat())
        row = {
            "index": snapshot.get("index") or index,
            "index_name": index,
            "close": snapshot.get("close"),
            "open": snapshot.get("open"),
            "high": snapshot.get("high"),
            "low": snapshot.get("low"),
            "chg_pct": snapshot.get("chg_pct"),
            "52w_high": snapshot.get("52w_high"),
            "52w_low": snapshot.get("52w_low"),
            "trend_10d": snapshot.get("trend_10d"),
            "total_stocks": breadth.get("total_stocks"),
            "advances": breadth.get("advances"),
            "declines": breadth.get("declines"),
            "ad_ratio": breadth.get("ad_ratio"),
            "avg_rs_pct": breadth.get("avg_rs_pct"),
            "stage_distribution": breadth.get("stage_distribution"),
            "composition_count": breadth.get("composition_count"),
            "matched_count": breadth.get("matched_count"),
            "coverage_pct": breadth.get("coverage_pct"),
            "warnings": breadth.get("warnings") or [],
            "data_source": breadth.get("data_source") or "index snapshot + market breadth",
            "as_of": as_of,
        }
        rows.append(row)
        evidence.append(TalkEvidenceItem(label=f"{index} index snapshot", value=snapshot, source="get_index_snapshot", as_of=as_of))
        evidence.append(TalkEvidenceItem(label=f"{index} market breadth", value=breadth, source="get_market_breadth", as_of=str(breadth.get("snapshot_date") or as_of)))

    return rows, evidence, list(dict.fromkeys(gaps))


def _fallback_answer(
    intent: str,
    question: str,
    symbols: list[str],
    comparison: list[dict[str, Any]],
    market: list[dict[str, Any]],
    gaps: list[str],
    *,
    screener_results: list[dict[str, Any]] | None = None,
    intraday_context: dict[str, Any] | None = None,
) -> str:
    screener_results = screener_results or []
    intraday_context = intraday_context or {}

    if intent == "screener":
        if screener_results:
            lines = ["Screener shortlist from available Agent Adda evidence:", ""]
            for row in screener_results[:10]:
                score = (
                    row.get("composite_score")
                    or row.get("strength_score")
                    or row.get("investment_score")
                    or row.get("technical_score")
                )
                tags = row.get("setup_tags") or []
                tag_text = f", tags {', '.join(str(t) for t in tags[:3])}" if tags else ""
                lines.append(
                    f"- {row.get('symbol')}: {row.get('company') or row.get('symbol')}; "
                    f"price {_fmt(row.get('price'))}, stage {row.get('stage') or 'n/a'}, "
                    f"RSI {_fmt(row.get('rsi'))}, RS {_fmt(row.get('rs_pct') or row.get('relative_strength'), '%')}, "
                    f"score {_fmt(score)}, signal {row.get('trading_signal') or row.get('verdict') or 'n/a'}{tag_text}."
                )
            lines.append("")
            lines.append("Use this as a research shortlist, not a buy/sell recommendation.")
            if gaps:
                lines.append("Gaps: " + "; ".join(gaps[:5]))
            return "\n".join(lines)
        gap_text = "; ".join(gaps[:5]) if gaps else "No rows matched the screener."
        return f"The screener did not return usable rows. Gap: {gap_text}"

    if intent == "intraday_health":
        status = str(intraday_context.get("overall_status") or "UNKNOWN").upper()
        mode = intraday_context.get("data_mode") or "intraday"
        lines = [
            f"Intraday source health is {status} for {mode} data.",
            "",
            "T2S is gating live quote, intraday bars, ORB, VWAP, MACD, RSI divergence, Bollinger squeeze, VCP, and momentum scanner output until the source health is fresh enough.",
        ]
        tables = intraday_context.get("tables") if isinstance(intraday_context.get("tables"), dict) else {}
        for name, table in list(tables.items())[:5]:
            if isinstance(table, dict):
                lines.append(
                    f"- {name}: rows {table.get('rows') or 'n/a'}, latest {table.get('latest_ts') or table.get('latest_date') or 'n/a'}, status {table.get('status') or 'n/a'}."
                )
        if gaps:
            lines.append("")
            lines.append("Gaps: " + "; ".join(gaps[:5]))
        return "\n".join(lines)

    if intent == "advice_boundary" and comparison:
        row = comparison[0]
        return "\n".join(
            [
                f"I cannot tell you whether to buy or sell {row['symbol']}. This is research only, not investment advice.",
                "",
                f"Current evidence view: price {_fmt(row.get('price'))}, stage {row.get('stage') or 'n/a'}, "
                f"RSI {_fmt(row.get('rsi'))}, technical score {_fmt(row.get('technical_score'))}, "
                f"trend {row.get('trend_signal') or 'n/a'}, trading signal {row.get('trading_signal') or 'n/a'}.",
                "",
                "Useful next checks: your time horizon, risk limit, position size, support/resistance, and whether fresh fundamentals or results change the setup.",
            ]
        )

    if intent == "evidence_review":
        if gaps:
            lines = ["Evidence gaps from the active context:", ""]
            lines.extend(f"- {gap}" for gap in gaps[:10])
            return "\n".join(lines)
        return "The active context has no blocking evidence gaps recorded. Continue to treat the answer as research-only, using the cited evidence and freshness labels."

    if intent == "financials_review" and comparison:
        lines = ["Financial evidence from cached fundamentals:", ""]
        for row in comparison:
            if row.get("latest_quarter"):
                unit = row.get("financial_unit") or "INR crore"
                lines.append(f"**{row['symbol']} Latest Financial Results**")
                lines.append("")
                lines.append("**Quarterly Results**")
                lines.extend(
                    _md_table(
                        ["Period", f"Revenue ({unit})", f"PAT ({unit})", "EPS", "OPM"],
                        [[row.get("latest_quarter"), _fmt_crore(row.get("revenue")), _fmt_crore(row.get("pat")), _fmt_eps(row.get("eps")), _fmt(row.get("opm_pct"), "%")]],
                    )
                )
                annual_row = row.get("latest_annual") or {}
                if annual_row:
                    lines.append("")
                    lines.append("**Annual Results**")
                    lines.extend(
                        _md_table(
                            ["Period", "Revenue (INR crore)", "PAT (INR crore)", "EPS", "OPM"],
                            [[
                                annual_row.get("period_label"),
                                _fmt_crore(annual_row.get("revenue")),
                                _fmt_crore(annual_row.get("pat")),
                                _fmt_eps(annual_row.get("eps")),
                                _fmt(annual_row.get("opm_pct"), "%"),
                            ]],
                        )
                    )
                bs = row.get("latest_balance_sheet") or {}
                if bs:
                    lines.append("")
                    lines.append(f"**Balance Sheet ({_md_cell(bs.get('period_label'))})**")
                    lines.extend(
                        _md_table(
                            ["Metric", "Value (INR crore)"],
                            [
                                ["Net debt", _fmt_crore(bs.get("net_debt"))],
                                ["Borrowings", _fmt_crore(bs.get("borrowings"))],
                                ["Reserves", _fmt_crore(bs.get("reserves"))],
                            ],
                        )
                    )
                cf = row.get("latest_cash_flow") or {}
                if cf:
                    lines.append("")
                    lines.append(f"**Cash Flow ({_md_cell(cf.get('period_label'))})**")
                    lines.extend(
                        _md_table(
                            ["Metric", "Value (INR crore)"],
                            [
                                ["Operating cash flow", _fmt_crore(cf.get("operating_cf"))],
                                ["Net cash flow", _fmt_crore(cf.get("net_cf"))],
                            ],
                        )
                    )
                if row.get("financial_source_url"):
                    lines.append("")
                    lines.append(f"Source: [{row.get('financial_source') or 'financial source'}]({row['financial_source_url']}).")
                lines.append("")
            else:
                lines.append(f"- {row['symbol']}: quarterly financials were not available in cached evidence.")
        if gaps:
            lines.append("")
            lines.append("Gaps: " + "; ".join(gaps[:5]))
        return "\n".join(lines)


    if intent == "compare" and comparison:
        leader = max(
            comparison,
            key=lambda r: (_coerce_float(r.get("technical_score")) or -1, _coerce_float(r.get("investment_score")) or -1),
        )
        lines = [
            f"Direct view: {leader['symbol']} currently has the strongest deterministic score among this basket.",
            "",
            "Comparison snapshot:",
        ]
        for row in comparison:
            lines.append(
                f"- {row['symbol']}: price {_fmt(row.get('price'))}, stage {row.get('stage') or 'n/a'}, "
                f"RSI {_fmt(row.get('rsi'))}, technical {_fmt(row.get('technical_score'))}, "
                f"investment {_fmt(row.get('investment_score'))}, trend {row.get('trend_signal') or 'n/a'}."
            )
        lines.append("")
        lines.append("Use this as a shortlist view, not a buy/sell recommendation.")
        return "\n".join(lines)

    if intent == "index_context" and market:
        lines = ["Direct view: index evidence is available without treating the index as a stock:", ""]
        for row in market[:5]:
            lines.append(
                f"- {row.get('index_name') or row.get('index')}: close {_fmt(row.get('close'))}, "
                f"change {_fmt(row.get('chg_pct'), '%')}, A/D {row.get('advances') or 'n/a'}/{row.get('declines') or 'n/a'}, "
                f"AD ratio {_fmt(row.get('ad_ratio'))}, avg RS {_fmt(row.get('avg_rs_pct'), '%')}."
            )
        if gaps:
            lines.append("")
            lines.append("Gaps: " + "; ".join(gaps[:5]))
        return "\n".join(lines)

    if intent == "market_context" and market:
        lines = ["Direct view: current sector breadth leaders are concentrated in these groups:", ""]
        for row in market[:5]:
            lines.append(
                f"- {row.get('sector')}: {_fmt(row.get('pct_above_50dma'), '%')} above 50DMA, "
                f"5D change {_fmt(row.get('change_5d'), '%')}, signal {row.get('breadth_signal') or 'n/a'}."
            )
        lines.append("")
        lines.append("This is breadth context only; individual stock validation still needs price, volume, and fundamentals.")
        return "\n".join(lines)

    if comparison:
        row = comparison[0]
        return "\n".join(
            [
                f"Direct view: {row['symbol']} is available for a permissive MVP read, with explicit gaps.",
                "",
                f"- Price: {_fmt(row.get('price'))}",
                f"- Stage: {row.get('stage') or 'n/a'}",
                f"- Sector: {row.get('sector') or 'n/a'}",
                f"- RSI: {_fmt(row.get('rsi'))}",
                f"- Technical score: {_fmt(row.get('technical_score'))}",
                f"- Investment score: {_fmt(row.get('investment_score'))}",
                f"- Trend signal: {row.get('trend_signal') or 'n/a'}",
                f"- Support / resistance: {_fmt(row.get('support'))} / {_fmt(row.get('resistance'))}",
                "",
                "Research only. This is not investment advice.",
            ]
        )

    gap_text = "; ".join(gaps[:3]) if gaps else "No symbol or market object was resolved from the question."
    return (
        "I could not build a full evidence-backed answer yet. "
        f"Gap: {gap_text}. Try a direct prompt such as 'analyze HDFCBANK' or 'compare TCS vs INFY'."
    )


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = {
        "gpt-5-nano": (0.05, 0.40),
        "gpt-4o-mini": (0.15, 0.60),
    }
    in_rate, out_rate = rates.get(model, (0.0, 0.0))
    return round((input_tokens / 1_000_000 * in_rate) + (output_tokens / 1_000_000 * out_rate), 6)


def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", "off"}


def _llm_synthesis(
    question: str,
    fallback: str,
    evidence: list[TalkEvidenceItem],
    gaps: list[str],
    context: dict[str, Any] | None = None,
    intent: str = "",
) -> tuple[str, str, int, int, float, str, str]:
    if not _env_flag("TALK2STOCKS_LLM_SYNTHESIS", "1"):
        return fallback, "fallback_template", 0, 0, 0.0, "disabled", "TALK2STOCKS_LLM_SYNTHESIS disabled"

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")
    if not api_key:
        return fallback, "fallback_template", 0, 0, 0.0, "missing_api_key", "OPENAI_API_KEY not configured"

    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key)
        evidence_block = "\n".join(f"- {item.label}: {item.value}"[:1800] for item in evidence[:8])
        has_structured_gaps = bool(gaps)
        gap_block = "\n".join(f"- {gap}" for gap in gaps[:8]) or "- none"
        context_block = ""
        if context:
            context_symbols = ", ".join(str(s) for s in (context.get("symbols") or [])[:8]) or "none"
            context_block = (
                f"\nConversation context:\n"
                f"- Previous intent: {context.get('intent') or 'unknown'}\n"
                f"- Previous symbols: {context_symbols}\n"
                f"- Previous gaps: {len(context.get('gaps') or [])}\n"
            )
        task_instruction = ""
        if intent == "evidence_review":
            labels = ", ".join(item.label for item in evidence[:8]) or "none"
            task_instruction = (
                "\nCurrent task: evidence review. Answer only the user's evidence/gap/source question. "
                "Do not add a fresh stock analysis, do not introduce new metrics, and do not infer gaps "
                "that are not present in the Gaps block. Mention the evidence labels used: "
                f"{labels}.\n"
            )
        elif intent == "advice_boundary":
            task_instruction = (
                "\nCurrent task: advice boundary. Start by saying you cannot provide a buy/sell recommendation. "
                "Then give a research-only evidence summary and next checks. Do not say 'buy', 'sell', or 'hold' as a recommendation.\n"
            )
        elif intent == "financials_review":
            task_instruction = (
                "\nCurrent task: financial evidence answer. Use cached financials evidence when present. "
                "Format quarter, annual, balance sheet, and cash-flow figures as compact Markdown tables. "
                "Financial revenue/PAT amounts from cached Screener financials are in INR crore unless the evidence says otherwise. "
                "Never call these amounts millions. If revenue/PAT/EPS is missing from evidence, say it is missing; "
                "do not infer it from price or technical data.\n"
            )
        elif intent == "index_context":
            task_instruction = (
                "\nCurrent task: index context. Treat NIFTY/BANKNIFTY/FINNIFTY-style inputs as indices, not stocks. "
                "Use index snapshot and market breadth evidence. Do not claim stock-specific fields such as company fundamentals, "
                "stage snapshot, or stock price-history gaps for an index.\n"
            )
        elif intent == "screener":
            task_instruction = (
                "\nCurrent task: screener shortlist. Use only the screener evidence rows. "
                "Call them research candidates or shortlist entries, not recommendations. "
                "Mention the screener source and any explicit gaps; do not invent rank reasons not in evidence.\n"
            )
        elif intent == "intraday_health":
            task_instruction = (
                "\nCurrent task: intraday source health. Report only health/freshness/readiness from the evidence. "
                "Do not produce live levels, setups, ORB, VWAP, scanner output, or trade guidance when the health gate is not fresh.\n"
            )
        prompt = (
            "You are Talk 2 Stocks by Agent Adda. Write a concise Indian stock research answer.\n"
            "Rules: research only; no buy/sell advice; cite evidence labels; include gaps if present; "
            "do not invent missing numbers; when the user uses pronouns, rely only on the conversation context provided. "
            "Only call something an evidence gap if it appears in the Gaps block. "
            "Null optional fields in Evidence are unavailable fields, not gaps.\n"
            f"Structured gaps present: {'yes' if has_structured_gaps else 'no'}. "
            "If structured gaps present is no, do not include a gaps/note/missing-evidence sentence.\n\n"
            f"Question: {question}{context_block}{task_instruction}\n\nEvidence:\n{evidence_block}\n\nGaps:\n{gap_block}\n\n"
            f"Deterministic draft:\n{fallback}"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
        )
        answer = resp.choices[0].message.content or fallback
        in_tok = resp.usage.prompt_tokens if resp.usage else 0
        out_tok = resp.usage.completion_tokens if resp.usage else 0
        return answer, model, in_tok, out_tok, _estimate_cost(model, in_tok, out_tok), "succeeded", ""
    except Exception as exc:
        return f"{fallback}\n\nLLM synthesis unavailable: {exc}", "fallback_template", 0, 0, 0.0, "failed", str(exc)


def _next_actions(
    intent: str,
    symbols: list[str],
    *,
    screener_results: list[dict[str, Any]] | None = None,
) -> list[TalkAction]:
    screener_results = screener_results or []
    if intent == "screener":
        top_symbols = [str(row.get("symbol")).strip().upper() for row in screener_results if row.get("symbol")]
        top_symbols = list(dict.fromkeys(top_symbols))[:5]
        return [
            TalkAction(label="Compare top names", action="compare", payload={"symbols": top_symbols[:3]}),
            TalkAction(label="Save shortlist", action="save_watchlist", payload={"symbols": top_symbols}),
            TalkAction(label="Validate watchlist", action="screener", payload={"screen_type": "watchlist_strength"}),
        ][:3]
    if intent == "intraday_health":
        return [
            TalkAction(label="Check health again", action="intraday_health", payload={}),
            TalkAction(label="Show Stage 2 stocks", action="screener", payload={"screen_type": "stage2"}),
            TalkAction(label="Show market breadth", action="market_context", payload={}),
        ]
    actions = [
        TalkAction(label="Compare", action="compare", payload={"symbols": symbols[:3]}),
        TalkAction(label="Save watchlist", action="save_watchlist", payload={"symbols": symbols}),
    ]
    if symbols:
        actions.insert(0, TalkAction(label="Deep dive", action="deep_dive", payload={"symbol": symbols[0]}))
    if intent == "market_context":
        actions.insert(0, TalkAction(label="Show sector leaders", action="market_context", payload={}))
    return actions[:3]


def _remember_turn(
    session_id: str,
    intent: str,
    question: str,
    symbols: list[str],
    indices: list[str],
    evidence: list[TalkEvidenceItem],
    gaps: list[str],
    comparison: list[dict[str, Any]],
    market: list[dict[str, Any]],
    answer: str,
    screener_results: list[dict[str, Any]] | None = None,
    intraday_context: dict[str, Any] | None = None,
) -> None:
    _SESSION_MEMORY[session_id] = {
        "intent": intent,
        "question": question,
        "symbols": symbols,
        "indices": indices,
        "evidence": [item.model_dump() for item in evidence],
        "gaps": gaps,
        "comparison": comparison,
        "screener_results": screener_results or [],
        "market_context": market,
        "intraday_context": intraday_context or {},
        "answer": answer[:4000],
    }


@router.get("/defaults")
async def defaults():
    return {
        "brand": "Agent Adda",
        "product": "Talk 2 Stocks",
        "watchlist": _DEFAULT_WATCHLIST,
        "router_model": os.getenv("LLM_ROUTER_MODEL", "gpt-5-nano"),
        "default_model": os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini"),
        "synthesis_policy": "llm_preferred" if _env_flag("TALK2STOCKS_LLM_SYNTHESIS", "1") else "local_only",
        "mode": "permissive",
    }


def _env_use_agent_bridge() -> bool:
    """Feature flag — set T2S_USE_AGENT_BRIDGE=0 to fall back to the legacy pipeline."""
    return os.getenv("T2S_USE_AGENT_BRIDGE", "1").strip().lower() not in {"0", "false", "no", "off"}


async def _chat_via_bridge(req: TalkChatRequest, session_id: str) -> TalkChatResponse:
    """Route through the CLI Agent pipeline (UnifiedRouter + full 7-stage waterfall).

    Falls back to the legacy deterministic pipeline on any import/runtime error
    so T2S stays operational even when the Agent cannot be instantiated.
    """
    from ..bridge import agent_query
    from ..trace_extract import (
        extract_comparison,
        extract_evidence,
        extract_intent,
        extract_market_context,
        extract_screener_results,
        extract_symbols,
        extract_usage,
    )

    result = await agent_query(session_id, req.question.strip())

    trace      = result.get("trace") or []
    answer     = result.get("answer") or ""
    backend    = result.get("backend") or "unknown"
    intent     = extract_intent(result)

    comparison      = extract_comparison(trace)
    market          = extract_market_context(trace)
    screener_results = extract_screener_results(trace)
    evidence        = extract_evidence(trace)
    symbols         = extract_symbols(trace, comparison)
    in_tok, out_tok, cost = extract_usage(result)

    # Collect gaps from the trace (any tool result with an "error" field)
    gaps: list[str] = []
    for item in trace:
        if isinstance(item, dict):
            res = item.get("result") or {}
            if isinstance(res, dict) and res.get("error"):
                tool = item.get("tool") or "tool"
                sym = res.get("symbol") or ""
                prefix = f"{sym}: " if sym else ""
                gaps.append(f"{prefix}{tool}: {res['error']}")

    # Persist a lightweight session snapshot so /compare and /screener
    # endpoints can still read context if needed.
    _remember_turn(
        session_id, intent, req.question.strip(),
        symbols, [], evidence, gaps,
        comparison, market, answer,
        screener_results, {},
    )

    return TalkChatResponse(
        session_id=session_id,
        intent=intent,
        answer=answer,
        symbols=symbols,
        comparison=comparison,
        screener_results=screener_results,
        market_context=market,
        intraday_context={},
        evidence=evidence,
        gaps=gaps,
        next_actions=_next_actions(intent, symbols, screener_results=screener_results),
        model_route={
            "router": "UnifiedRouter",
            "synthesis": backend,
            "synthesis_policy": "agent_pipeline",
            "synthesis_status": "succeeded" if answer and result.get("intent") != "error" else "failed",
            "synthesis_error": "" if result.get("intent") != "error" else answer,
            "mode": req.mode,
            "provider": backend,
        },
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
    )


async def _chat_legacy(req: TalkChatRequest, session_id: str) -> TalkChatResponse:
    """Original deterministic-first pipeline (regex intent → tool calls → gpt-4o-mini)."""
    question = req.question.strip()
    watchlist = [s.strip().upper() for s in (req.watchlist or []) if s.strip()]
    context = _session_context(session_id)
    screener_key = _detect_screener_key(question)
    intraday_requested = bool(_INTRADAY_RE.search(question))
    if screener_key:
        indices: list[str] = []
        symbols: list[str] = []
        resolution_gaps: list[str] = []
        intent = "screener"
    elif intraday_requested:
        indices = []
        symbols = []
        resolution_gaps = []
        intent = "intraday_health"
    else:
        indices = _resolve_query_indices(question, watchlist)
        indices = _bind_context_indices(question, indices, context)
        symbols, resolution_gaps = _resolve_query_symbols_with_gaps(question, watchlist)
        symbols = _strip_index_symbols(symbols, indices)
        symbols = _bind_context_symbols(question, symbols, context)
        intent = _infer_intent(question, symbols, context, indices)

    comparison: list[dict[str, Any]] = []
    evidence: list[TalkEvidenceItem] = []
    gaps: list[str] = []
    market: list[dict[str, Any]] = []
    screener_results: list[dict[str, Any]] = []
    intraday_context: dict[str, Any] = {}
    gaps.extend(resolution_gaps)

    if intent == "evidence_review" and context:
        evidence.extend(_context_evidence(context))
        gaps.extend(str(gap) for gap in (context.get("gaps") or []))
        comparison.extend(dict(row) for row in (context.get("comparison") or []) if isinstance(row, dict))
        screener_results.extend(dict(row) for row in (context.get("screener_results") or []) if isinstance(row, dict))
        market.extend(dict(row) for row in (context.get("market_context") or []) if isinstance(row, dict))
        intraday_context.update(dict(context.get("intraday_context") or {}))
        symbols = [str(s) for s in (context.get("symbols") or symbols)]
        indices = [str(s) for s in (context.get("indices") or indices)]
    elif intent == "screener" and screener_key:
        screener_results, screener_evidence, screener_gaps, _screener_meta = _screener_context(
            screener_key,
            top_n=_extract_top_n(question),
            watchlist=watchlist,
        )
        evidence.extend(screener_evidence)
        gaps.extend(screener_gaps)
        symbols = [str(row.get("symbol")).strip().upper() for row in screener_results if row.get("symbol")][:10]
    elif intent == "intraday_health":
        intraday_context, intraday_evidence, intraday_gaps = _intraday_health_context()
        evidence.extend(intraday_evidence)
        gaps.extend(intraday_gaps)
    elif intent == "index_context":
        market, index_evidence, index_gaps = _index_context(indices)
        evidence.extend(index_evidence)
        gaps.extend(index_gaps)
    elif intent == "market_context" and not symbols:
        market, market_evidence, market_gaps = _market_context()
        evidence.extend(market_evidence)
        gaps.extend(market_gaps)
    else:
        for symbol in symbols[:10]:
            row, symbol_evidence, symbol_gaps = _symbol_evidence(symbol)
            if intent == "financials_review":
                financial_row, financial_evidence, financial_gaps = _financial_evidence(symbol)
                row.update(financial_row)
                symbol_evidence.extend(financial_evidence)
                symbol_gaps.extend(financial_gaps)
            comparison.append(row)
            evidence.extend(symbol_evidence)
            gaps.extend(symbol_gaps)
        if intent in {"market_context", "stock_deep_dive", "compare"}:
            market, market_evidence, market_gaps = _market_context()
            evidence.extend(market_evidence)
            gaps.extend(market_gaps)

    gaps = list(dict.fromkeys(gaps))
    if req.mode == "strict" and gaps:
        fallback = "Strict evidence mode blocked the answer because required evidence is missing."
    else:
        fallback = _fallback_answer(
            intent, question, symbols, comparison, market, gaps,
            screener_results=screener_results,
            intraday_context=intraday_context,
        )

    answer, model, in_tok, out_tok, cost, synthesis_status, synthesis_error = _llm_synthesis(
        question, fallback, evidence, gaps, context, intent,
    )
    _remember_turn(
        session_id, intent, question, symbols, indices,
        evidence, gaps, comparison, market, answer,
        screener_results, intraday_context,
    )

    return TalkChatResponse(
        session_id=session_id,
        intent=intent,
        answer=answer,
        symbols=symbols,
        comparison=comparison,
        screener_results=screener_results,
        market_context=market,
        intraday_context=intraday_context,
        evidence=evidence,
        gaps=gaps,
        next_actions=_next_actions(intent, symbols, screener_results=screener_results),
        model_route={
            "router": os.getenv("LLM_ROUTER_MODEL", "gpt-5-nano"),
            "synthesis": model,
            "synthesis_policy": "llm_preferred" if _env_flag("TALK2STOCKS_LLM_SYNTHESIS", "1") else "local_only",
            "synthesis_status": synthesis_status,
            "synthesis_error": synthesis_error,
            "mode": req.mode,
            "provider": "openai" if model != "fallback_template" else "local",
        },
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
    )


@router.post("/chat", response_model=TalkChatResponse)
async def chat(req: TalkChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    if _env_use_agent_bridge():
        try:
            return await _chat_via_bridge(req, session_id)
        except Exception:
            # Bridge unavailable (Agent import failed, DB offline, etc.) —
            # transparently fall through to the legacy pipeline.
            pass
    return await _chat_legacy(req, session_id)


@router.post("/compare", response_model=TalkChatResponse)
async def compare(req: TalkCompareRequest):
    question = req.question or "Compare " + " vs ".join(req.symbols)
    chat_req = TalkChatRequest(question=question, watchlist=req.symbols, mode=req.mode)
    if "compare" not in chat_req.question.lower():
        chat_req.question = "Compare " + " vs ".join(req.symbols) + ". " + chat_req.question
    return await chat(chat_req)


@router.post("/screener", response_model=TalkChatResponse)
async def screener(req: TalkScreenerRequest):
    screen_key = _detect_screener_key(req.screen_type) or req.screen_type.strip().lower().replace("-", "_").replace(" ", "_")
    question = req.question or f"Show top {req.top_n} {screen_key.replace('_', ' ')} screener results"
    session_id = str(uuid.uuid4())
    watchlist = [s.strip().upper() for s in (req.symbols or []) if s.strip()]
    screener_results, evidence, gaps, _meta = _screener_context(screen_key, top_n=req.top_n, watchlist=watchlist)
    symbols = [str(row.get("symbol")).strip().upper() for row in screener_results if row.get("symbol")][:10]

    if req.mode == "strict" and gaps:
        fallback = "Strict evidence mode blocked the screener answer because required evidence is missing."
    else:
        fallback = _fallback_answer(
            "screener",
            question,
            symbols,
            [],
            [],
            gaps,
            screener_results=screener_results,
        )
    answer, model, in_tok, out_tok, cost, synthesis_status, synthesis_error = _llm_synthesis(
        question,
        fallback,
        evidence,
        gaps,
        None,
        "screener",
    )
    _remember_turn(session_id, "screener", question, symbols, [], evidence, gaps, [], [], answer, screener_results, {})
    return TalkChatResponse(
        session_id=session_id,
        intent="screener",
        answer=answer,
        symbols=symbols,
        screener_results=screener_results,
        evidence=evidence,
        gaps=gaps,
        next_actions=_next_actions("screener", symbols, screener_results=screener_results),
        model_route={
            "router": os.getenv("LLM_ROUTER_MODEL", "gpt-5-nano"),
            "synthesis": model,
            "synthesis_policy": "llm_preferred" if _env_flag("TALK2STOCKS_LLM_SYNTHESIS", "1") else "local_only",
            "synthesis_status": synthesis_status,
            "synthesis_error": synthesis_error,
            "mode": req.mode,
            "provider": "openai" if model != "fallback_template" else "local",
        },
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
    )
