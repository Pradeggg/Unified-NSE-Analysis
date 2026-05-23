"""Terminal command handler for Strategy Council simulations."""

from __future__ import annotations

import shlex
from dataclasses import replace
from pathlib import Path

import pandas as pd

from backtesting.strategy_council.council import run_strategy_council
from backtesting.strategy_council.evidence import (
    build_strategy_council_evidence_pack,
    load_symbol_eod_history,
)
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
    enrichment = not _flag_enabled(parts, "--no-enrichment")
    advanced_critics = not _flag_enabled(parts, "--no-advanced-critics")
    dashboard_dir = _arg(parts, "--dashboard-dir")
    dashboard_enabled = not _flag_enabled(parts, "--no-dashboard")
    if dashboard_enabled and dashboard_dir is None:
        dashboard_dir = "reports/dashboards"
    elif not dashboard_enabled:
        dashboard_dir = None
    return CouncilConfig(
        symbol=symbol,
        horizons=_parse_horizons(_arg(parts, "--horizon")),
        iterations=_positive_int(_arg(parts, "--iterations"), name="--iterations", default=3),
        max_candidates=_positive_int(_arg(parts, "--max-candidates"), name="--max-candidates", default=5),
        from_date=_arg(parts, "--from"),
        validation_from=_arg(parts, "--validation-from"),
        test_from=_arg(parts, "--test-from"),
        allowed_strategies=_parse_strategies(strategies, default),
        include_enrichment=enrichment,
        use_advanced_critics=advanced_critics,
        dashboard_output_dir=dashboard_dir,
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
        evidence = build_strategy_council_evidence_pack(config.symbol, project_root=root)
        intraday_summary = None
        if mode == "intraday":
            evidence, intraday_summary = _build_intraday_evidence(config.symbol, evidence)
        eod = _load_symbol_eod(config.symbol, root, config.from_date)
        if config.use_advanced_critics:
            try:
                from backtesting.strategy_council.critics_advanced import build_advanced_critics
                critics = tuple(critics) + build_advanced_critics(
                    evidence=evidence,
                    max_drawdown_pct=config.max_drawdown_threshold_pct,
                    correlation_threshold=config.train_val_corr_threshold,
                    beta_threshold=config.beta_threshold,
                )
            except Exception:
                pass
        result = run_strategy_council(eod, evidence=evidence, config=config, strategist=strategist, critics=critics)
        report = write_council_report(result, output_dir=root / "reports" / "strategy_council")
        result = replace(result, report_path=str(report))
        persisted = None
        if _flag_enabled(parts, "--persist", "--postgres"):
            persisted = persist_council_result(result)
    except Exception as exc:
        return f"Strategy Council failed: {exc}"

    header = f"### Strategy Council — {config.symbol}"
    summary = _render_council_summary(
        result=result,
        evidence=evidence,
        agent_mode=agent_mode,
        config=config,
        report_path=report,
        intraday_summary=intraday_summary,
        persisted=persisted,
    )
    return "\n".join([header, "", *summary])


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_num(value) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{f:.2f}"


def _render_council_summary(
    *,
    result,
    evidence: EvidencePack,
    agent_mode: str,
    config: CouncilConfig,
    report_path: Path,
    intraday_summary: dict | None,
    persisted: dict | None,
) -> list[str]:
    """Produce a multi-section terminal-friendly summary of a council run.

    Mirrors the structure of the markdown report so the agent answer is
    self-contained without requiring the user to open the file.
    """
    lines: list[str] = []
    fundamental = evidence.fundamental or {}
    readiness = fundamental.get("readiness") or {}
    tech = evidence.technical or {}
    snapshot = fundamental.get("snapshot") or {}
    filing = fundamental.get("filing") or {}
    latest_results = fundamental.get("latest_results") or {}
    breadth = (evidence.market or {}).get("breadth") or {}
    factor_exposure = (evidence.market or {}).get("factor_exposure") or {}
    regime = (evidence.market or {}).get("regime") or {}
    microstructure = (evidence.market or {}).get("microstructure") or {}

    lines.append(f"- **Recommendation:** {result.recommendation}")
    locked = result.locked_strategy.strategy_id if result.locked_strategy else "none"
    lines.append(f"- **Locked strategy:** {locked}")
    lines.append(f"- **Iterations:** {len(result.iterations)}")
    lines.append(
        f"- **Readiness:** {readiness.get('score', 'n/a')} / "
        f"{readiness.get('status', 'n/a')}"
        + (
            f" (missing: {', '.join(readiness.get('missing') or [])})"
            if readiness.get("missing")
            else ""
        )
    )
    lines.append(
        "- **Enhancements:** "
        f"enrichment={'on' if config.include_enrichment else 'off'}, "
        f"advanced_critics={'on' if config.use_advanced_critics else 'off'}, "
        f"dashboard={'on' if config.dashboard_output_dir else 'off'}"
    )

    lines.append("")
    lines.append("#### Evidence Snapshot")
    if tech:
        lines.append(
            f"- Close ₹{_fmt_num(tech.get('close'))} "
            f"| O ₹{_fmt_num(tech.get('open'))} "
            f"H ₹{_fmt_num(tech.get('high'))} "
            f"L ₹{_fmt_num(tech.get('low'))} "
            f"| Vol {_fmt_num(tech.get('volume'))} "
            f"| Bars {tech.get('bars', 'n/a')}"
        )
    regime_label = regime.get("label") if isinstance(regime, dict) else None
    if regime_label or regime:
        bias = regime.get("bias_pct") if isinstance(regime, dict) else None
        lines.append(
            f"- Regime: **{regime_label or evidence.freshness.get('regime', 'n/a')}**"
            + (f" (bias {_fmt_pct(bias)})" if bias is not None else "")
        )
    beta = factor_exposure.get("beta") if isinstance(factor_exposure, dict) else None
    if beta is not None:
        lines.append(f"- Factor β vs Nifty 50: {float(beta):+.2f}")
    atr = microstructure.get("atr_pct") if isinstance(microstructure, dict) else None
    if atr is not None:
        lines.append(f"- Microstructure: ATR {_fmt_pct(atr)}")
    if snapshot:
        bits = []
        if snapshot.get("stage"):
            bits.append(str(snapshot["stage"]))
        if snapshot.get("trading_signal"):
            bits.append(f"signal {snapshot['trading_signal']}")
        if snapshot.get("rsi") is not None:
            bits.append(f"RSI {_fmt_num(snapshot['rsi'])}")
        if snapshot.get("relative_strength") is not None:
            bits.append(f"RS {_fmt_num(snapshot['relative_strength'])}")
        if snapshot.get("sector"):
            bits.append(str(snapshot["sector"]))
        if bits:
            lines.append("- Snapshot: " + " · ".join(bits))

    facts = latest_results.get("facts") if isinstance(latest_results, dict) else None
    if facts:
        fact_bits = []
        for key in ("revenue", "ebitda", "pat", "eps", "net_debt"):
            if key in facts:
                item = facts[key]
                fact_bits.append(
                    f"{key.upper()} {item.get('value')} ({item.get('period')})"
                )
        if fact_bits:
            lines.append("- Latest results: " + " · ".join(fact_bits))

    if filing.get("period"):
        head = filing.get("headline_numbers") or {}
        pages = filing.get("page_count") or len(filing.get("page_excerpts") or [])
        tables = filing.get("table_count") or len(filing.get("tables") or [])
        head_keys = ", ".join(head.keys()) if head else "no headline tables"
        lines.append(
            f"- Filing: {filing.get('period')} · {pages} pages · {tables} tables · {head_keys}"
        )

    if breadth:
        lines.append(
            f"- Market breadth: A/D {breadth.get('ad_ratio', 'n/a')} "
            f"({breadth.get('advances', '?')}↑ / {breadth.get('declines', '?')}↓), "
            f"avg RS {breadth.get('avg_rs_pct', 'n/a')}"
        )

    if evidence.news:
        lines.append("")
        lines.append("#### Top Catalysts")
        for n in evidence.news[:5]:
            title = n.get("title") if isinstance(n, dict) else str(n)
            if title:
                lines.append(f"- {title}")

    if evidence.source_trail:
        lines.append("")
        lines.append("#### Source Trail")
        for entry in evidence.source_trail:
            lines.append(f"- {entry}")
    if evidence.missing:
        lines.append(f"- _Missing axes:_ {', '.join(evidence.missing)}")

    if result.iterations:
        lines.append("")
        lines.append("#### Iteration Critique Highlights")
        for it in result.iterations:
            concerns = []
            for crit in it.critiques or ():
                if crit.issues:
                    concerns.append(f"{crit.critic}: {crit.issues[0]}")
            concern_str = "; ".join(concerns[:3]) if concerns else "no blocking concerns"
            lines.append(
                f"- Iter {it.index}: {len(it.candidates)} candidates → {concern_str}"
            )
            if it.strategist_revision:
                lines.append(f"  - revision: {it.strategist_revision}")

    if result.test_results:
        lines.append("")
        lines.append("#### Final One-Shot Test")
        for slice_ in result.test_results:
            metrics = slice_.metrics or {}
            ret = metrics.get("return_pct") or metrics.get("return")
            pnl = metrics.get("pnl") or metrics.get("p&l")
            lines.append(
                f"- {slice_.strategy_id} / {slice_.horizon_days}d / "
                f"{slice_.trade_count} trades / return {_fmt_pct(ret) if ret is not None else 'n/a'}"
                + (f" / P&L {_fmt_num(pnl)}" if pnl is not None else "")
            )

    if result.rationale:
        lines.append("")
        lines.append(f"_Rationale:_ {result.rationale}")

    lines.append("")
    lines.append(f"- **Report:** `{report_path}`")
    if result.dashboard_path:
        lines.append(f"- **Dashboard:** `{result.dashboard_path}`")
    if persisted:
        lines.append(f"- **PostgreSQL council run:** {persisted['run_id']}")
        lines.append(f"- **Persisted split results:** {persisted['split_results_inserted']}")

    if intraday_summary:
        for line in _format_intraday_lines(intraday_summary):
            lines.append(f"- {line}")
        lines.append(
            f"- _Mode: Intraday Strategy Council ({agent_mode}); research-only, not investment advice._"
        )
    else:
        lines.append(
            f"- _Mode: EOD Strategy Council simulation ({agent_mode}); research-only, not investment advice._"
        )
    return lines
