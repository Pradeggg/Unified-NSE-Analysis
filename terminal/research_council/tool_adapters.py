"""Lazy adapters from Research Council logical tools to existing Agent Adda tools."""

from __future__ import annotations

from importlib import import_module
from typing import Any

import pandas as pd

from terminal.research_council.agents.coder_quant import CoderQuantAgent


def regime_detect(**kwargs: Any) -> dict:
    breadth = _safe_call("get_market_breadth")
    cycle = _safe_call("get_economic_cycle_assessment")
    return {"ok": True, "tool": "regime.detect", "breadth": breadth, "cycle": cycle, "args": kwargs}


def breadth_summarize(**kwargs: Any) -> dict:
    return _call_terminal_tool("get_market_breadth", **kwargs)


def flows_fii_dii_5d(**kwargs: Any) -> dict:
    return _call_terminal_tool("get_fii_dii_activity", **kwargs)


def macro_proxy_signals(**kwargs: Any) -> dict:
    module = import_module("fetch_macro_proxies")
    if hasattr(module, "generate_macro_signals"):
        signals, tailwinds = module.generate_macro_signals(**_filtered_kwargs(kwargs, {"force"}))
        return {"ok": True, "signals": _frame_to_records(signals), "tailwinds": _frame_to_records(tailwinds)}
    return {"ok": False, "error": "macro_adapter_unavailable"}


def sector_rs_ranking(**kwargs: Any) -> dict:
    return {"ok": True, "tool": "sector.rs_ranking", "status": "adapter_pending", "args": kwargs}


def sector_breadth_health(**kwargs: Any) -> dict:
    return {"ok": True, "tool": "sector.breadth_health", "status": "adapter_pending", "args": kwargs}


def sector_top_stocks(**kwargs: Any) -> dict:
    sector = kwargs.get("sector") or kwargs.get("symbol") or ""
    return _call_terminal_tool("get_sector_context", sector_or_symbol=sector) if sector else {
        "ok": True,
        "tool": "sector.top_stocks",
        "status": "requires_sector",
    }


def screen_stage2(**kwargs: Any) -> dict:
    return _call_terminal_tool("run_screener_query", screen_type="stage2", top_n=int(kwargs.get("top_n", 10)))


def screen_high_rs(**kwargs: Any) -> dict:
    return _call_terminal_tool("run_screener_query", screen_type="high_rs", top_n=int(kwargs.get("top_n", 10)))


def screen_momentum_52w(**kwargs: Any) -> dict:
    return _call_terminal_tool("run_screener_query", screen_type="52w_high", top_n=int(kwargs.get("top_n", 10)))


def fund_results_trend(**kwargs: Any) -> dict:
    return _call_terminal_tool("get_latest_results_feed", **kwargs)


def fund_balance_sheet_health(**kwargs: Any) -> dict:
    return {"ok": True, "tool": "fund.balance_sheet_health", "status": "adapter_pending", "args": kwargs}


def events_upcoming(**kwargs: Any) -> dict:
    return _call_terminal_tool("get_upcoming_events", **kwargs)


def fno_buildup(**kwargs: Any) -> dict:
    return _call_terminal_tool("get_fno_analytics", **kwargs)


def strategy_build(**kwargs: Any) -> dict:
    if kwargs.get("include_test"):
        return {
            "ok": False,
            "error": "test_split_locked",
            "message": "test split is locked until strategy commit",
        }

    eod_data = kwargs.get("eod_data")
    eod_source_trail: list[str] = []
    symbols = _normalize_symbols(kwargs.get("symbols") or kwargs.get("shortlist_symbols") or [])
    if eod_data is None and symbols:
        eod_data, eod_source_trail = _load_shortlist_eod_data(symbols)
    if kwargs.get("sweep"):
        if eod_data is None:
            return {"ok": False, "error": "requires_eod_data_for_sweep"}
        use_ai_design = bool(kwargs.get("ai_design"))
        agent = CoderQuantAgent(
            llm_call=_default_llm_call() if use_ai_design else None,
            require_ai=use_ai_design,
            model=kwargs.get("model"),
        )
        output = _serialize_sweep_output(
            agent.sweep_train_validation(
                source_branch=str(kwargs.get("source_branch") or "research_council"),
                hypothesis=str(kwargs.get("hypothesis") or kwargs.get("objective") or ""),
                eod_data=eod_data,
                strategy_families=list(kwargs.get("strategy_families") or []),
                horizons=list(kwargs.get("allowed_horizons") or kwargs.get("horizons") or [5, 10, 20]),
                initial_capital=float(kwargs.get("initial_capital") or 100000.0),
            )
        )
        if symbols:
            output["symbols"] = symbols
        if eod_source_trail:
            output["eod_source_trail"] = eod_source_trail
        return output

    agent = CoderQuantAgent(llm_call=_default_llm_call(), require_ai=True, model=kwargs.get("model"))
    request = agent.build_request(
        source_branch=str(kwargs.get("source_branch") or "research_council"),
        hypothesis=str(kwargs.get("hypothesis") or kwargs.get("objective") or ""),
        strategy_family=str(kwargs.get("strategy_family") or kwargs.get("family") or "stage2_breakout"),
        required_features=list(kwargs.get("required_features") or []),
        allowed_horizons=list(kwargs.get("allowed_horizons") or [5, 10, 20]),
    )
    if eod_data is None:
        proposed = agent.try_propose_strategy_spec(request)
        if not proposed.get("ok"):
            return proposed
        spec = proposed["spec"]
        result = agent.evaluate_request(request)
        return {
            "ok": True,
            "request": request.to_dict(),
            "spec": _dataclass_to_dict(spec),
            "result": result.to_dict(),
            "status": "requires_eod_data_for_backtest",
        }
    output = agent.run_train_validation(
        request,
        eod_data,
        initial_capital=float(kwargs.get("initial_capital") or 100000.0),
        validation_from=kwargs.get("validation_from"),
        test_from=kwargs.get("test_from"),
    )
    if not output.get("ok"):
        return output
    return {
        "ok": True,
        "request": output["request"].to_dict(),
        "spec": _dataclass_to_dict(output["spec"]),
        "result": output["result"].to_dict(),
        "backtest_results": {
            split: _dataclass_to_dict(row)
            for split, row in output["backtest_results"].items()
            if split in {"train", "validation"}
        },
    }


def _serialize_sweep_output(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": output.get("ok", True),
        "best": _serialize_sweep_item(output.get("best")),
        "ranked_options": [_serialize_sweep_item(item) for item in output.get("ranked_options", [])],
        "untestable": [_serialize_sweep_item(item) for item in output.get("untestable", [])],
        "routes_tested": output.get("routes_tested", 0),
        "routes_untestable": output.get("routes_untestable", 0),
    }


def _serialize_sweep_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    return {key: _dataclass_to_dict(value) for key, value in item.items()}


def _load_shortlist_eod_data(symbols: list[str]) -> tuple[pd.DataFrame | None, list[str]]:
    frames = []
    trail = []
    for symbol in symbols:
        frame, symbol_trail = _load_symbol_eod_history(symbol)
        trail.extend(f"{symbol}: {item}" for item in symbol_trail)
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return None, trail
    return pd.concat(frames, ignore_index=True).sort_values(["date", "symbol"]).reset_index(drop=True), trail


def _load_symbol_eod_history(symbol: str):
    from backtesting.strategy_council.evidence import load_symbol_eod_history

    return load_symbol_eod_history(symbol)


def _normalize_symbols(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",")]
    out = []
    seen = set()
    for item in raw or []:
        symbol = str(item).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _default_llm_call():
    from terminal.research_council.llm_client import call_llm_json

    return call_llm_json


def _call_terminal_tool(name: str, **kwargs: Any) -> Any:
    return _normalize_tool_output(_terminal_tool(name)(**kwargs))


def _terminal_tool(name: str):
    module = import_module("terminal.tools")
    return getattr(module, name)


def _safe_call(name: str, **kwargs: Any) -> Any:
    try:
        return _call_terminal_tool(name, **kwargs)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tool": name}


def _normalize_tool_output(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if "ok" in value:
            return value
        return {"ok": True, **value}
    return {"ok": True, "value": value}


def _frame_to_records(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict(orient="records")
    return value


def _filtered_kwargs(kwargs: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if key in allowed}


def _dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(value)
    return value
