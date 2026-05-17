"""Composite F&O overview tools."""

from __future__ import annotations

from typing import Any


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


def get_option_chain_summary(symbol: str, expiry_index: int = 0) -> dict:
    chain = _get_options_chain(symbol, expiry_index=expiry_index)
    if chain.get("error"):
        return {"status": "missing", "symbol": symbol.upper(), "error": chain.get("error")}
    return {
        "status": "ok",
        "symbol": chain.get("symbol", symbol.upper()),
        "expiry": chain.get("expiry"),
        "pcr": chain.get("pcr"),
        "max_pain": chain.get("max_pain"),
        "top_call_oi": chain.get("top_call_oi") or chain.get("top_calls") or [],
        "top_put_oi": chain.get("top_put_oi") or chain.get("top_puts") or [],
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
    basis = futures.get("basis")
    if basis is None and futures.get("future") is not None and futures.get("spot") is not None:
        basis = float(futures["future"]) - float(futures["spot"])
    return {"status": "ok", "symbol": futures.get("symbol", symbol.upper()), "basis": basis, "raw": futures}


def get_cost_of_carry(symbol: str) -> dict:
    futures = _get_futures_analysis(symbol)
    if futures.get("error"):
        return {"status": "missing", "symbol": symbol.upper(), "error": futures.get("error")}
    return {
        "status": "ok",
        "symbol": futures.get("symbol", symbol.upper()),
        "cost_of_carry": futures.get("cost_of_carry") or futures.get("annualized_cost_of_carry"),
        "raw": futures,
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
    chain = get_option_chain_summary(sym, expiry_index=expiry_index)
    futures_raw = _get_futures_analysis(sym)
    futures = {"status": "missing", "symbol": sym, "error": futures_raw.get("error")} if futures_raw.get("error") else {
        "status": "ok",
        **futures_raw,
    }
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
