"""Markdown reporting for Strategy Council results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backtesting.strategy_council.types import CouncilResult


def _metrics_table(results) -> list[str]:
    lines = ["| Split | Strategy | Horizon | Trades | Return % | P&L |", "|---|---|---:|---:|---:|---:|"]
    for result in results:
        lines.append(
            "| {split} | {strategy} | {horizon} | {trades} | {ret} | {pnl} |".format(
                split=result.split,
                strategy=result.strategy_id,
                horizon=result.horizon_days,
                trades=result.trade_count,
                ret=result.metrics.get("total_return_pct"),
                pnl=result.metrics.get("total_pnl"),
            )
        )
    return lines


def _intraday_evidence_lines(result: CouncilResult) -> list[str]:
    snapshot = result.evidence.market.get("intraday_snapshot") or {}
    setup = result.evidence.technical.get("intraday_setup") or {}
    fallback = result.evidence.technical.get("intraday_fallback_analysis") or {}
    if not (snapshot or setup or fallback):
        return []

    lines = ["", "## Intraday Evidence"]
    if snapshot:
        lines.append(f"- Live source: `{snapshot.get('source') or 'NSE live API snapshot'}`")
        if snapshot.get("as_of"):
            lines.append(f"- Live as of: `{snapshot.get('as_of')}`")
        if snapshot.get("last_price") is not None:
            lines.append(f"- Live price: `{snapshot.get('last_price')}`")
        if snapshot.get("pct_change") is not None:
            lines.append(f"- Live change %: `{snapshot.get('pct_change')}`")
    if setup:
        lines.append(f"- Candle/setup source: `{setup.get('source') or 'intraday candles'}`")
        if setup.get("setup_label"):
            lines.append(f"- Setup label: `{setup.get('setup_label')}`")
        if setup.get("score") is not None:
            lines.append(f"- Setup score: `{setup.get('score')}`")
        if setup.get("error"):
            lines.append(f"- Primary candle issue: `{setup.get('error')}`")
    if fallback:
        lines.append(f"- Fallback source: `{fallback.get('source') or fallback.get('data_source') or 'fallback candles'}`")
        if fallback.get("bias"):
            lines.append(f"- Fallback bias: `{fallback.get('bias')}`")
        if fallback.get("close") is not None:
            lines.append(f"- Fallback close: `{fallback.get('close')}`")
    lines.append("- Framing: intraday evidence is context for research, not an execution recommendation.")
    return lines


def render_council_markdown(result: CouncilResult) -> str:
    lines = [
        f"# Strategy Council — {result.config.symbol}",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Evidence as of: {result.evidence.as_of}",
        f"Recommendation: **{result.recommendation}**",
        "",
        "## Evidence Pack",
        f"- Symbol: `{result.evidence.symbol}`",
        f"- Technical: `{result.evidence.technical}`",
        f"- Freshness: `{result.evidence.freshness}`",
        "",
        "## Missing Data",
    ]
    if result.evidence.missing:
        lines.extend(f"- {item}" for item in result.evidence.missing)
    else:
        lines.append("- None reported")

    if result.evidence.source_trail:
        lines.extend(["", "## Source Trail"])
        lines.extend(f"- {item}" for item in result.evidence.source_trail)

    lines.extend(_intraday_evidence_lines(result))

    lines.extend(["", "## Iterations"])
    if not result.iterations:
        lines.append("- No iterations captured.")
    for iteration in result.iterations:
        lines.append(f"### Iteration {iteration.index}")
        lines.append(f"- Candidates: {len(iteration.candidates)}")
        lines.append(f"- Strategist revision: {iteration.strategist_revision}")
        lines.extend(_metrics_table(iteration.train_results + iteration.validation_results))
        lines.append("")
        for critique in iteration.critiques:
            lines.append(f"- Critic `{critique.critic}`: {critique.verdict}; issues={list(critique.issues)}")

    lines.extend(["", "## Locked Strategy"])
    if result.locked_strategy:
        lines.append(f"- Strategy: `{result.locked_strategy.strategy_id}`")
        lines.append(f"- Strategy Origin: `{result.locked_strategy.origin}`")
        lines.append(f"- Horizon: {result.locked_strategy.horizon_days} trading days")
        lines.append(f"- Thesis: {result.locked_strategy.thesis}")
    else:
        lines.append("- No strategy locked.")

    lines.extend(["", "## Final One-Shot Test"])
    lines.extend(_metrics_table(result.test_results) if result.test_results else ["- No test result."])
    lines.extend(
        [
            "",
            "## Rationale",
            result.rationale,
            "",
            "## Disclaimer",
            "This is AI-assisted research and deterministic backtesting output, not investment advice.",
        ]
    )
    return "\n".join(lines)


def write_council_report(result: CouncilResult, *, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or Path("reports") / "strategy_council"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"strategy_council_{result.config.symbol}_{suffix}.md"
    path.write_text(render_council_markdown(result), encoding="utf-8")
    return path
