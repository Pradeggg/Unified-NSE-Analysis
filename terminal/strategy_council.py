"""Terminal command handler for Strategy Council simulations."""

from __future__ import annotations

import shlex
from dataclasses import replace
from pathlib import Path

import pandas as pd

from backtesting.strategy_council.council import run_strategy_council
from backtesting.strategy_council.evidence import build_evidence_pack, load_symbol_eod_history
from backtesting.strategy_council.llm import build_default_agents
from backtesting.strategy_council.postgres_storage import persist_council_result
from backtesting.strategy_council.report import write_council_report
from backtesting.strategy_council.types import CouncilConfig, EvidencePack


DEFAULT_HORIZONS = (5, 10, 20)
HORIZON_ALIASES = {"1w": 5, "2w": 10, "4w": 20}


def _parse_horizons(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return DEFAULT_HORIZONS
    values: list[int] = []
    for part in raw.split(","):
        item = part.strip().lower()
        if not item:
            continue
        if item in HORIZON_ALIASES:
            values.append(HORIZON_ALIASES[item])
        elif item.isdigit():
            value = int(item)
            if value <= 0:
                raise ValueError(f"Invalid horizon '{item}'; use positive days or aliases 1w,2w,4w")
            values.append(value)
        else:
            raise ValueError(f"Invalid horizon '{item}'; use positive days or aliases 1w,2w,4w")
    cleaned = tuple(v for v in values if v > 0)
    if not cleaned:
        raise ValueError("At least one valid horizon is required")
    return cleaned


def _arg(parts: list[str], name: str, default: str | None = None) -> str | None:
    if name not in parts:
        return default
    idx = parts.index(name)
    if idx + 1 >= len(parts):
        raise ValueError(f"Missing value for {name}")
    return parts[idx + 1]


def _positive_int(raw: str | None, *, name: str, default: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _parse_strategies(raw: str | None, default: CouncilConfig) -> tuple[str, ...]:
    if not raw:
        return default.allowed_strategies
    requested = tuple(s.strip().lower().replace("-", "_") for s in raw.split(",") if s.strip())
    if not requested:
        raise ValueError("At least one strategy is required")
    unknown = tuple(s for s in requested if s not in default.allowed_strategies)
    if unknown:
        allowed = ", ".join(default.allowed_strategies)
        raise ValueError(f"Unknown strategy {', '.join(unknown)}; allowed strategies: {allowed}")
    return requested


def parse_strategy_council_command(text: str) -> CouncilConfig:
    parts = shlex.split(text)
    if len(parts) < 2:
        raise ValueError("Usage: /strategy-council SYMBOL [--horizon 1w,2w,4w] [--iterations 3]")
    symbol = parts[1].upper()
    strategies = _arg(parts, "--strategies")
    default = CouncilConfig(symbol=symbol)
    return CouncilConfig(
        symbol=symbol,
        horizons=_parse_horizons(_arg(parts, "--horizon")),
        iterations=_positive_int(_arg(parts, "--iterations"), name="--iterations", default=3),
        max_candidates=_positive_int(_arg(parts, "--max-candidates"), name="--max-candidates", default=5),
        from_date=_arg(parts, "--from"),
        validation_from=_arg(parts, "--validation-from"),
        test_from=_arg(parts, "--test-from"),
        allowed_strategies=_parse_strategies(strategies, default),
    )


def _flag_enabled(parts: list[str], *names: str) -> bool:
    return any(name in parts for name in names)


def _strategy_council_data_mode(parts: list[str], ambient_mode: str | None = None) -> str:
    if _flag_enabled(parts, "--eod", "--historical"):
        return "eod"
    raw_mode = _arg(parts, "--mode")
    if raw_mode:
        mode = raw_mode.strip().lower()
        if mode in {"intraday", "live"}:
            return "intraday"
        if mode in {"eod", "historical"}:
            return "eod"
        raise ValueError("--mode must be intraday or eod")
    if _flag_enabled(parts, "--intraday", "--live"):
        return "intraday"
    if (ambient_mode or "").strip().lower() in {"intraday", "live"}:
        return "intraday"
    return "eod"


def resolve_strategy_council_agents(parts: list[str]):
    """Resolve strategist/critic adapters and return a human-readable mode label."""
    force_no_llm = "--no-llm" in parts
    use_llm = not force_no_llm
    strategist, critics = build_default_agents(use_llm=use_llm)
    mode = "LLM strategist + critics" if use_llm and "--no-llm" not in parts else "deterministic fallback"
    if "RuleBased" in strategist.__class__.__name__:
        mode = "deterministic fallback"
    return strategist, critics, mode


def _load_symbol_eod(symbol: str, root: Path, from_date: str | None) -> pd.DataFrame:
    df, _trail = load_symbol_eod_history(symbol, project_root=root, from_date=from_date)
    return df


def _clean_mode_args(parts: list[str]) -> list[str]:
    cleaned: list[str] = []
    skip_next = False
    for part in parts:
        if skip_next:
            skip_next = False
            continue
        if part == "--mode":
            skip_next = True
            continue
        if part in {"--intraday", "--live", "--eod", "--historical"}:
            continue
        cleaned.append(part)
    return cleaned


def _build_intraday_evidence(symbol: str, evidence: EvidencePack, *, timeframe: str = "15m") -> tuple[EvidencePack, dict]:
    from terminal import tools

    snapshot = tools.get_nse_intraday_snapshot(symbol)
    setup = tools.explain_intraday_setup(symbol, timeframe=timeframe)
    fallback = None
    if setup.get("error"):
        fallback = tools.get_intraday_analysis(symbol, interval=timeframe)

    evidence.market["intraday_snapshot"] = snapshot
    evidence.technical["intraday_setup"] = setup
    evidence.freshness["intraday_snapshot"] = "available" if not snapshot.get("error") else "unavailable"

    if fallback is not None:
        evidence.technical["intraday_fallback_analysis"] = fallback
        evidence.freshness["intraday_candles"] = "yfinance_fallback" if not fallback.get("error") else "unavailable"
    else:
        evidence.freshness["intraday_candles"] = "available" if not setup.get("error") else "unavailable"

    if snapshot.get("error"):
        evidence.missing.append("intraday_snapshot")
    if setup.get("error") and (not fallback or fallback.get("error")):
        evidence.missing.append("intraday_candles")

    source_parts = []
    if snapshot.get("source"):
        source_parts.append(str(snapshot["source"]))
    elif not snapshot.get("error"):
        source_parts.append("NSE live API snapshot")
    if setup.get("source"):
        source_parts.append(str(setup["source"]))
    if fallback and fallback.get("source"):
        source_parts.append(str(fallback["source"]))

    summary = {
        "snapshot": snapshot,
        "setup": setup,
        "fallback": fallback,
        "sources": " + ".join(dict.fromkeys(source_parts)) or "intraday sources unavailable",
        "label": setup.get("setup_label") or fallback.get("bias") if fallback else setup.get("setup_label"),
        "score": setup.get("score"),
        "latest": snapshot.get("last_price") or setup.get("latest_close") or (fallback or {}).get("close"),
    }
    return evidence, summary


def _format_intraday_lines(summary: dict) -> list[str]:
    lines = [f"Sources: {summary.get('sources')}"]
    if summary.get("latest") is not None:
        lines.append(f"Live/Latest price: {summary['latest']}")
    if summary.get("label"):
        lines.append(f"Intraday setup: {summary['label']}")
    if summary.get("score") is not None:
        lines.append(f"Intraday score: {summary['score']}")
    return lines


def handle_strategy_council_command(
    text: str,
    *,
    project_root: Path | None = None,
    data_mode: str | None = None,
) -> str:
    root = Path(project_root or Path.cwd())
    try:
        parts = shlex.split(text)
        mode = _strategy_council_data_mode(parts, data_mode)
        config = parse_strategy_council_command(" ".join(shlex.quote(p) for p in _clean_mode_args(parts)))
        strategist, critics, agent_mode = resolve_strategy_council_agents(parts)
        evidence = build_evidence_pack(config.symbol, project_root=root)
        intraday_summary = None
        if mode == "intraday":
            evidence, intraday_summary = _build_intraday_evidence(config.symbol, evidence)
        eod = _load_symbol_eod(config.symbol, root, config.from_date)
        result = run_strategy_council(eod, evidence=evidence, config=config, strategist=strategist, critics=critics)
        report = write_council_report(result, output_dir=root / "reports" / "strategy_council")
        result = replace(result, report_path=str(report))
        persisted = None
        if _flag_enabled(parts, "--persist", "--postgres"):
            persisted = persist_council_result(result)
    except Exception as exc:
        return f"Strategy Council failed: {exc}"

    lines = [
        f"Strategy Council — {config.symbol}",
        f"Recommendation: {result.recommendation}",
        f"Locked strategy: {result.locked_strategy.strategy_id if result.locked_strategy else 'none'}",
        f"Iterations: {len(result.iterations)}",
        f"Report: {report}",
    ]
    if persisted:
        lines.append(f"PostgreSQL council run: {persisted['run_id']}")
        lines.append(f"Persisted split results: {persisted['split_results_inserted']}")
    if intraday_summary:
        lines.extend(_format_intraday_lines(intraday_summary))
        lines.append(f"Mode: Intraday Strategy Council ({agent_mode}); research-only, not investment advice.")
    else:
        lines.append(f"Mode: EOD Strategy Council simulation ({agent_mode}); research-only, not investment advice.")
    return "\n".join(lines)
