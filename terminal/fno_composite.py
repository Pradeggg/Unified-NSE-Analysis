"""Composite F&O overview tools."""

from __future__ import annotations

from typing import Any


_OPTION_TYPE_TOKENS = {"CE", "PE", "FUT", "CALL", "PUT"}


def _get_options_chain(symbol: str, expiry_index: int = 0) -> dict:
    from terminal.tools import get_options_chain

    return get_options_chain(symbol, expiry_index=expiry_index)


def _get_futures_analysis(symbol: str) -> dict:
    from terminal.tools import get_futures_analysis

    return get_futures_analysis(symbol)


def _get_strategy_recommendations(symbol: str) -> dict:
    from terminal.tools import get_strategy_recommendations

    return get_strategy_recommendations(symbol)


def _status(result: dict | None) -> str:
    if not result:
        return "missing"
    return f"ERROR: {result.get('error')}" if result.get("error") else "ok"


def _pcr_value(chain: dict) -> float | int | None:
    pcr = chain.get("pcr")
    if isinstance(pcr, dict):
        return _first_present(pcr.get("oi"), pcr.get("pcr_oi"))
    return pcr


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _top_oi(rows: list[dict] | None, oi_keys: tuple[str, ...], limit: int = 5) -> list[dict]:
    def oi_value(row: dict) -> float:
        for key in oi_keys:
            value = row.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    return sorted(rows or [], key=oi_value, reverse=True)[:limit]


def get_option_chain_summary(symbol: str, expiry_index: int = 0) -> dict:
    chain = _get_options_chain(symbol, expiry_index=expiry_index)
    if chain.get("error"):
        return {"status": "missing", "symbol": symbol.upper(), "error": chain.get("error")}
    top_calls = (
        chain.get("top_call_oi")
        or chain.get("top_calls")
        or chain.get("top_ce_oi_strikes")
        or _top_oi(chain.get("calls"), ("oi", "ce_oi", "open_interest"))
    )
    top_puts = (
        chain.get("top_put_oi")
        or chain.get("top_puts")
        or chain.get("top_pe_oi_strikes")
        or _top_oi(chain.get("puts"), ("oi", "pe_oi", "open_interest"))
    )
    return {
        "status": "ok",
        "symbol": chain.get("symbol", symbol.upper()),
        "expiry": chain.get("expiry"),
        "pcr": _pcr_value(chain),
        "max_pain": chain.get("max_pain"),
        "top_call_oi": top_calls or [],
        "top_put_oi": top_puts or [],
        "raw": chain,
    }


def get_max_pain(symbol: str, expiry_index: int = 0) -> dict:
    summary = get_option_chain_summary(symbol, expiry_index=expiry_index)
    return {"symbol": symbol.upper(), "status": summary.get("status"), "max_pain": summary.get("max_pain"), "error": summary.get("error")}


def get_pcr_summary(symbol: str, expiry_index: int = 0) -> dict:
    summary = get_option_chain_summary(symbol, expiry_index=expiry_index)
    pcr = summary.get("pcr")
    if pcr is None:
        regime = "unknown"
    else:
        regime = "put-heavy" if float(pcr) > 1.1 else ("call-heavy" if float(pcr) < 0.8 else "balanced")
    return {"symbol": symbol.upper(), "status": summary.get("status"), "pcr": pcr, "regime": regime, "error": summary.get("error")}


def get_top_oi_strikes(symbol: str, expiry_index: int = 0) -> dict:
    summary = get_option_chain_summary(symbol, expiry_index=expiry_index)
    return {
        "symbol": symbol.upper(),
        "status": summary.get("status"),
        "top_call_oi": summary.get("top_call_oi") or [],
        "top_put_oi": summary.get("top_put_oi") or [],
        "error": summary.get("error"),
    }


def get_futures_basis(symbol: str) -> dict:
    futures = _get_futures_analysis(symbol)
    if futures.get("error"):
        return {"status": "missing", "symbol": symbol.upper(), "error": futures.get("error")}
    normalized = _normalize_futures(futures, symbol.upper())
    return {"status": "ok", "symbol": futures.get("symbol", symbol.upper()), "basis": normalized.get("basis"), "raw": futures}


def get_cost_of_carry(symbol: str) -> dict:
    futures = _get_futures_analysis(symbol)
    if futures.get("error"):
        return {"status": "missing", "symbol": symbol.upper(), "error": futures.get("error")}
    normalized = _normalize_futures(futures, symbol.upper())
    return {
        "status": "ok",
        "symbol": futures.get("symbol", symbol.upper()),
        "cost_of_carry": normalized.get("cost_of_carry"),
        "raw": futures,
    }


def _normalize_futures(futures_raw: dict, symbol: str) -> dict:
    """Expose near-contract basis/carry at the root of the composite result."""
    if futures_raw.get("error"):
        return {"status": "missing", "symbol": symbol, "error": futures_raw.get("error")}

    contracts = futures_raw.get("futures") or []
    near = contracts[0] if contracts else {}
    spot = _first_present(futures_raw.get("spot"), futures_raw.get("underlying"), near.get("underlying"))
    future = _first_present(futures_raw.get("future"), near.get("last_price"), near.get("settle_price"))
    basis = _first_present(futures_raw.get("basis"), near.get("basis"))
    if basis is None and future is not None and spot is not None:
        try:
            basis = round(float(future) - float(spot), 2)
        except (TypeError, ValueError):
            basis = None
    cost_of_carry = _first_present(
        futures_raw.get("cost_of_carry"),
        futures_raw.get("annualized_cost_of_carry"),
        futures_raw.get("annualised_cost_of_carry"),
        near.get("cost_of_carry"),
        near.get("annualized_cost_of_carry"),
        near.get("cost_of_carry_annualised_pct"),
    )
    return {
        "status": "ok",
        **futures_raw,
        "symbol": futures_raw.get("symbol", symbol),
        "spot": spot,
        "future": future,
        "near_contract": near,
        "basis": basis,
        "cost_of_carry": cost_of_carry,
        "annualized_cost_of_carry": cost_of_carry,
    }


def recommend_options_strategy(
    symbol: str,
    option_chain: dict | None = None,
    futures: dict | None = None,
    raw_strategy: dict | None = None,
) -> dict:
    if not option_chain or option_chain.get("status") == "missing" or option_chain.get("error"):
        return {
            "status": "blocked",
            "strategy": None,
            "reason": "Option-chain evidence is missing, so no options strategy was recommended.",
            "framing": "Research-only; not investment advice.",
        }
    if not futures or futures.get("status") == "missing" or futures.get("error"):
        return {
            "status": "blocked",
            "strategy": None,
            "reason": "Futures basis/cost-of-carry evidence is missing, so no options strategy was recommended.",
            "framing": "Research-only; not investment advice.",
        }
    raw_strategy = raw_strategy or {}
    strategy = raw_strategy.get("recommended") or raw_strategy.get("strategy") or raw_strategy.get("best_strategy") or "defined_risk_spread"
    max_pain = option_chain.get("max_pain")
    basis = futures.get("basis")
    return {
        "status": "ok",
        "strategy": strategy,
        "conditions": [
            f"Option chain remains supportive around max pain {max_pain}" if max_pain is not None else "Option-chain PCR/OI remains supportive.",
            f"Futures basis remains near {basis}" if basis is not None else "Futures basis does not materially deteriorate.",
        ],
        "invalidation": "Avoid/exit the thesis if spot breaks key support or OI shifts against the setup.",
        "max_loss": "Defined by debit/credit spread width and net premium; calculate from selected strikes before execution.",
        "max_profit": "Defined by selected strikes and net premium; calculate from the exact option legs before execution.",
        "framing": "Research-only options strategy framing; not a buy/sell recommendation.",
        "raw": raw_strategy,
    }


def get_fno_overview(symbol: str = "NIFTY", expiry_index: int = 0) -> dict:
    sym = symbol.strip().upper()
    if sym in _OPTION_TYPE_TOKENS:
        message = (
            f"{sym} is an option type, not an F&O underlying symbol. "
            "Use an underlying such as NIFTY, BANKNIFTY, FINNIFTY, or a stock F&O symbol."
        )
        return {
            "status": "invalid_input",
            "symbol": sym,
            "error": message,
            "option_chain": {"status": "missing", "symbol": sym, "error": message},
            "pcr": None,
            "max_pain": None,
            "top_oi_strikes": {"calls": [], "puts": []},
            "futures": {"status": "missing", "symbol": sym, "error": message},
            "basis": None,
            "cost_of_carry": None,
            "recommendation": {
                "status": "blocked",
                "strategy": None,
                "reason": "A valid F&O underlying symbol is required before recommending an options strategy.",
                "framing": "Research-only; not investment advice.",
            },
            "missing_evidence": ["valid_underlying_symbol"],
            "source_trail": {
                "get_options_chain": "skipped",
                "get_futures_analysis": "skipped",
                "get_strategy_recommendations": "skipped",
            },
            "framing": "Research-only F&O overview; not investment advice.",
        }
    chain = get_option_chain_summary(sym, expiry_index=expiry_index)
    futures_raw = _get_futures_analysis(sym)
    futures = _normalize_futures(futures_raw, sym)
    missing: list[str] = []
    if chain.get("status") != "ok":
        missing.append("option_chain")
    if futures.get("status") != "ok":
        missing.append("futures")
    raw_strategy: dict[str, Any] = {}
    if not missing:
        raw_strategy = _get_strategy_recommendations(sym)
        strategy_status = _status(raw_strategy)
    else:
        strategy_status = "skipped"
    recommendation = recommend_options_strategy(
        sym,
        option_chain=chain,
        futures=futures,
        raw_strategy=raw_strategy,
    )
    return {
        "status": "ok" if not missing else "missing_evidence",
        "symbol": sym,
        "option_chain": chain,
        "pcr": chain.get("pcr"),
        "max_pain": chain.get("max_pain"),
        "top_oi_strikes": {
            "calls": chain.get("top_call_oi") or [],
            "puts": chain.get("top_put_oi") or [],
        },
        "futures": futures,
        "basis": futures.get("basis"),
        "cost_of_carry": futures.get("cost_of_carry") or futures.get("annualized_cost_of_carry"),
        "recommendation": recommendation,
        "missing_evidence": missing,
        "source_trail": {
            "get_options_chain": _status(chain),
            "get_futures_analysis": _status(futures_raw),
            "get_strategy_recommendations": strategy_status,
        },
        "framing": "Research-only F&O overview; not investment advice.",
    }
