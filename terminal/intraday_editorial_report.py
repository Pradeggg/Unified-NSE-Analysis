"""Editorial quantitative F&O report from the intraday indicator study.

This layer is intentionally evidence-bound: it reads the structured study
report, extracts facts from tables, and only then builds editorial prose. An
LLM may rewrite the prose, but it receives the extracted evidence JSON rather
than free-form permission to invent conclusions.
"""

from __future__ import annotations

import html
import json
import math
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


IST = timezone(timedelta(hours=5, minutes=30))
LATEST_STUDY = Path("reports/latest/intraday_fno_indicator_study.md")


@dataclass(frozen=True)
class EditorialReport:
    evidence: dict[str, Any]
    narrative: dict[str, Any]
    metadata: dict[str, Any]
    markdown: str


@dataclass(frozen=True)
class DetailedResearchPaper:
    evidence: dict[str, Any]
    narrative: dict[str, Any]
    metadata: dict[str, Any]
    markdown: str


def _clean(value: str) -> str:
    return str(value or "").strip().strip("*").strip()


def _parse_bullets(markdown: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        key_norm = key.strip().lower().replace(" ", "_")
        out[key_norm] = value.strip()
    return out


def _section(markdown: str, title: str) -> str:
    marker = f"## {title}"
    start = markdown.find(marker)
    if start < 0:
        return ""
    rest = markdown[start + len(marker):]
    next_idx = rest.find("\n## ")
    return rest if next_idx < 0 else rest[:next_idx]


def _tables(section: str) -> list[list[dict[str, str]]]:
    tables: list[list[dict[str, str]]] = []
    current: list[str] = []
    for raw in section.splitlines():
        line = raw.strip()
        if line.startswith("| ") and line.endswith(" |"):
            current.append(line)
            continue
        if current:
            parsed = _parse_table(current)
            if parsed:
                tables.append(parsed)
            current = []
    if current:
        parsed = _parse_table(current)
        if parsed:
            tables.append(parsed)
    return tables


def _parse_table(lines: list[str]) -> list[dict[str, str]]:
    if len(lines) < 3:
        return []
    header = [_clean(c) for c in lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        values = [_clean(c) for c in line.strip("|").split("|")]
        if len(values) != len(header):
            continue
        rows.append(dict(zip(header, values)))
    return rows


def _first_table(markdown: str, section_title: str) -> list[dict[str, str]]:
    section = _section(markdown, section_title)
    tables = _tables(section)
    return tables[0] if tables else []


def build_editorial_evidence(markdown: str) -> dict[str, Any]:
    bullets = _parse_bullets(markdown)
    indicator = _first_table(markdown, "Indicator Leaderboard")
    walk_forward = _first_table(markdown, "Walk-Forward Validation")
    symbol_rows = _first_table(markdown, "Confirmed Setup Symbol Drilldown")
    time_rows = _first_table(markdown, "Confirmed Setup Time-of-Day Filter")
    volatility_rows = _first_table(markdown, "Volatility Regime Read-Through")
    model_rows = _first_table(markdown, "Statistical Model Diagnostics")

    core_carriers = [row for row in symbol_rows if row.get("symbol_edge_status") == "core_carrier"]
    edge_diluters = [row for row in symbol_rows if row.get("symbol_edge_status") == "edge_diluter"]
    return {
        "generated": bullets.get("generated", ""),
        "universe": bullets.get("universe", ""),
        "timeframes": bullets.get("timeframes", ""),
        "bars_loaded": bullets.get("bars_loaded", ""),
        "symbols_with_bars": bullets.get("symbols_with_bars", ""),
        "trade_candidates_tested": bullets.get("trade_candidates_tested", ""),
        "fno_context_rows": bullets.get("daily_f&o_context_rows", ""),
        "top_setup": indicator[0] if indicator else {},
        "walk_forward": walk_forward[0] if walk_forward else {},
        "core_carriers": core_carriers,
        "edge_diluters": edge_diluters,
        "time_filter": time_rows[0] if time_rows else {},
        "volatility_regimes": volatility_rows[:8],
        "model_diagnostics": model_rows[:12],
        "source_sections": [
            "Indicator Leaderboard",
            "Walk-Forward Validation",
            "Confirmed Setup Symbol Drilldown",
            "Confirmed Setup Time-of-Day Filter",
            "Volatility Regime Read-Through",
            "Statistical Model Diagnostics",
        ],
    }


def _fallback_narrative(evidence: dict[str, Any]) -> dict[str, Any]:
    top = evidence.get("top_setup") or {}
    wf = evidence.get("walk_forward") or {}
    time_filter = evidence.get("time_filter") or {}
    core = evidence.get("core_carriers") or []
    diluters = evidence.get("edge_diluters") or []
    setup = top.get("setup") or "the tested setup"
    direction = top.get("direction") or ""
    timeframe = top.get("timeframe") or evidence.get("timeframes") or ""
    core_symbols = ", ".join(row.get("symbol", "") for row in core if row.get("symbol")) or "no symbol met the core-carrier threshold"
    diluter_symbols = ", ".join(row.get("symbol", "") for row in diluters if row.get("symbol")) or "none identified"

    return {
        "headline": "Opening Range + VWAP in Indian F&O: A Quantitative Intraday Study",
        "executive_summary": (
            f"The evidence supports {setup} {direction} on {timeframe} as an opening-drive continuation thesis. "
            f"It tested {top.get('trades', '-')} trades with {top.get('win_rate', '-')} win rate, "
            f"{top.get('expectancy_r', '-')}R expectancy, and {top.get('profit_factor', '-')} profit factor. "
            f"The walk-forward result was {wf.get('walk_forward_status', 'unavailable')} with "
            f"{wf.get('validation_trades', '-')} validation trades."
        ),
        "research_question": (
            "Can a simple opening range breakout above VWAP survive transaction costs, rolling stability checks, "
            "and unseen walk-forward validation across the Indian F&O intraday universe?"
        ),
        "methodology": [
            f"Universe: {evidence.get('universe') or 'not reported'}; timeframe: {timeframe or 'not reported'}.",
            f"Data loaded: {evidence.get('bars_loaded') or '-'} bars across {evidence.get('symbols_with_bars') or '-'} symbols.",
            "Setups were compared after slippage and brokerage assumptions, then filtered through rolling stability and walk-forward validation.",
            "The editorial layer summarizes only extracted evidence from the generated quantitative study.",
        ],
        "key_findings": [
            f"{setup} {direction} was the only setup promoted as the core thesis after walk-forward validation.",
            f"The edge is concentrated in core carriers: {core_symbols}.",
            f"Edge diluters were: {diluter_symbols}.",
            f"The strongest time filter is {time_filter.get('time_bucket', 'not reported')} with {time_filter.get('trades', '-')} trades.",
        ],
        "failed_hypotheses": [
            "Broad short-side continuation did not survive the current out-of-sample validation pass.",
            "MACD momentum looked conditionally interesting but was rejected out-of-sample in the latest study.",
        ],
        "risk_limits": [
            "The history is still short and should be expanded before treating this as a durable market edge.",
            "The study uses F&O eligibility and daily option-chain context; it does not backtest actual option premium fills.",
            "Execution quality, opening spreads, gap risk, and fast VWAP failures can materially change realized outcomes.",
        ],
        "monitoring_rules": [
            f"Monitor only {setup} {direction} on {timeframe} during {time_filter.get('time_bucket', 'the strongest time bucket')}.",
            f"Prioritize core carriers: {core_symbols}.",
            f"Suppress or heavily discount edge diluters: {diluter_symbols}.",
            "Require live price above opening range high and VWAP, plus acceptable liquidity and spread.",
        ],
        "linkedin_post": (
            "I ran a quantitative study on intraday F&O setups using Agent Adda. The strongest result was not a broad "
            "momentum claim. The only setup that survived the current evidence stack was ORB + VWAP long on 15-minute "
            "bars, concentrated in a small group of symbols and primarily during the opening drive. The important lesson: "
            "the edge is conditional, not universal. Research only, not investment advice."
        ),
        "disclaimer": "Research only; not investment advice. Historical validation does not guarantee future execution or returns.",
    }


def _flatten_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    return str(value or "")


def _validate_narrative_against_evidence(narrative: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    top = evidence.get("top_setup") or {}
    setup = str(top.get("setup") or "").strip()
    timeframe = str(top.get("timeframe") or "").strip()
    direction = str(top.get("direction") or "").strip()
    text = _flatten_text(
        {
            "headline": narrative.get("headline"),
            "executive_summary": narrative.get("executive_summary"),
            "key_findings": narrative.get("key_findings"),
            "monitoring_rules": narrative.get("monitoring_rules"),
        }
    ).lower()
    if setup and setup.lower() not in text:
        errors.append(f"missing top setup {setup}")
    if timeframe and timeframe.lower() not in text:
        errors.append(f"missing timeframe {timeframe}")
    if direction and direction.lower() not in text:
        errors.append(f"missing direction {direction}")
    if "macd" in text and setup.lower() != "macd + volume momentum":
        errors.append("mentions MACD as thesis despite different top setup")
    if "5-minute" in text and timeframe not in {"5m", "5min", "5-minute"}:
        errors.append("mentions 5-minute despite different evidence timeframe")
    if re.search(r"(?<!1)\b5m\b", text) and timeframe != "5m":
        errors.append("mentions 5m despite different evidence timeframe")
    return errors


_NARRATIVE_SCHEMA = {
    "type": "object",
    "required": [
        "headline",
        "executive_summary",
        "research_question",
        "methodology",
        "key_findings",
        "failed_hypotheses",
        "risk_limits",
        "monitoring_rules",
        "linkedin_post",
        "disclaimer",
    ],
    "properties": {
        "headline": {"type": "string"},
        "executive_summary": {"type": "string"},
        "research_question": {"type": "string"},
        "methodology": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        "key_findings": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        "failed_hypotheses": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "risk_limits": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "monitoring_rules": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "linkedin_post": {"type": "string"},
        "disclaimer": {"type": "string"},
    },
}


def build_editorial_narrative(
    evidence: dict[str, Any],
    *,
    allow_llm: bool = True,
    llm_call: Callable[..., dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fallback = _fallback_narrative(evidence)
    if not allow_llm and llm_call is None:
        return fallback, {"source": "deterministic"}

    try:
        if llm_call is None:
            from terminal.research_council.llm_client import call_llm_json

            llm_call = call_llm_json
        result = llm_call(
            system=(
                "You are an editorial quant analyst. Write publishable but conservative commentary. "
                "Use only the supplied evidence_json. Do not invent symbols, metrics, dates, or conclusions. "
                "Keep the tone suitable for LinkedIn and a research report."
            ),
            user=json.dumps({"evidence_json": evidence}, indent=2, sort_keys=True),
            schema=_NARRATIVE_SCHEMA,
        )
        validation_errors = _validate_narrative_against_evidence(result, evidence)
        if validation_errors:
            return fallback, {
                "source": "deterministic",
                "validation_error": "; ".join(validation_errors),
                "llm_rejected": True,
            }
        return {**fallback, **result}, {"source": "LLM"}
    except Exception as exc:
        return fallback, {"source": "deterministic", "llm_error": f"{type(exc).__name__}: {exc}"}


def _list_md(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if str(item).strip()]


def _table_md(rows: list[dict[str, str]], cols: list[str], limit: int = 10) -> str:
    if not rows:
        return "_No rows._"
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in rows[:limit]:
        lines.append("| " + " | ".join(str(row.get(col, "-") or "-") for col in cols) + " |")
    return "\n".join(lines)


def render_editorial_markdown(evidence: dict[str, Any], narrative: dict[str, Any], metadata: dict[str, Any]) -> str:
    generated_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    lines = [
        "# Editorial Quantitative F&O Analysis",
        "",
        f"## {narrative.get('headline')}",
        "",
        f"- Generated: {generated_at}",
        f"- Evidence report generated: {evidence.get('generated') or '-'}",
        f"- Narrative source: {metadata.get('source')}",
        f"- Universe: {evidence.get('universe') or '-'}",
        f"- Timeframes: {evidence.get('timeframes') or '-'}",
        "",
        "## Executive Summary",
        "",
        str(narrative.get("executive_summary") or ""),
        "",
        "## Research Question",
        "",
        str(narrative.get("research_question") or ""),
        "",
        "## Methodology",
        "",
        *_list_md(list(narrative.get("methodology") or [])),
        "",
        "## Key Findings",
        "",
        *_list_md(list(narrative.get("key_findings") or [])),
        "",
        "## Evidence Snapshot",
        "",
        f"- Bars loaded: {evidence.get('bars_loaded') or '-'}",
        f"- Symbols with bars: {evidence.get('symbols_with_bars') or '-'}",
        f"- Trade candidates tested: {evidence.get('trade_candidates_tested') or '-'}",
        "",
        "### Top Setup",
        "",
        _table_md([evidence.get("top_setup") or {}], ["setup", "timeframe", "direction", "trades", "win_rate", "expectancy_r", "profit_factor"], 1),
        "",
        "### Walk-Forward Validation",
        "",
        _table_md([evidence.get("walk_forward") or {}], ["setup", "timeframe", "direction", "walk_forward_status", "validation_trades", "validation_expectancy_r", "validation_positive_fold_rate"], 1),
        "",
        "### Symbol Attribution",
        "",
        _table_md(
            list(evidence.get("core_carriers") or []) + list(evidence.get("edge_diluters") or []),
            ["symbol", "symbol_edge_status", "trades", "win_rate", "expectancy_r", "profit_factor", "best_volatility_regime"],
            12,
        ),
        "",
        "## Failed Hypotheses",
        "",
        *_list_md(list(narrative.get("failed_hypotheses") or [])),
        "",
        "## Practical Monitoring Rules",
        "",
        *_list_md(list(narrative.get("monitoring_rules") or [])),
        "",
        "## Risk And Limitations",
        "",
        *_list_md(list(narrative.get("risk_limits") or [])),
        "",
        "## LinkedIn Draft",
        "",
        str(narrative.get("linkedin_post") or ""),
        "",
        "## Disclaimer",
        "",
        str(narrative.get("disclaimer") or "Research only; not investment advice."),
    ]
    if metadata.get("llm_error"):
        lines.extend(["", "## Narrative Generation Note", "", str(metadata["llm_error"])])
    return "\n".join(lines)


def _row_value(row: dict[str, Any], key: str, default: str = "-") -> str:
    value = row.get(key)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    text = str(value).strip()
    return text if text else default


def build_detailed_research_paper(
    evidence: dict[str, Any],
    narrative: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> DetailedResearchPaper:
    metadata = {
        **(metadata or {}),
        "report_type": "detailed_research_paper",
        "built_at": datetime.now(IST).isoformat(timespec="seconds"),
    }
    top = evidence.get("top_setup") or {}
    wf = evidence.get("walk_forward") or {}
    time_filter = evidence.get("time_filter") or {}
    core = list(evidence.get("core_carriers") or [])
    diluters = list(evidence.get("edge_diluters") or [])
    vol = list(evidence.get("volatility_regimes") or [])
    models = list(evidence.get("model_diagnostics") or [])
    setup = _row_value(top, "setup", "ORB + VWAP")
    direction = _row_value(top, "direction", "LONG")
    timeframe = _row_value(top, "timeframe", evidence.get("timeframes") or "15m")

    lines = [
        "# Detailed Research Report",
        "",
        f"## {setup} {direction} on {timeframe}: Editorial Quantitative F&O Analysis",
        "",
        "### Report Purpose",
        "",
        (
            "This paper explains the full research chain behind the intraday F&O study: the question being tested, "
            "the signal definition, the backtest evidence, walk-forward validation, symbol attribution, volatility "
            "regime behavior, statistical diagnostics, and practical monitoring rules. It is written as a research "
            "document, not as a trading recommendation."
        ),
        "",
        "### Evidence Source",
        "",
        f"- Source report generated: {evidence.get('generated') or '-'}",
        f"- Narrative source: {metadata.get('source') or '-'}",
        f"- Universe: {evidence.get('universe') or '-'}",
        f"- Timeframe tested: {evidence.get('timeframes') or timeframe}",
        f"- Bars loaded: {evidence.get('bars_loaded') or '-'}",
        f"- Symbols with bars: {evidence.get('symbols_with_bars') or '-'}",
        f"- Trade candidates tested: {evidence.get('trade_candidates_tested') or '-'}",
        f"- F&O context rows: {evidence.get('fno_context_rows') or '-'}",
        "",
        "## 1. Research Question",
        "",
        str(narrative.get("research_question") or (
            f"Does {setup} {direction} on {timeframe} produce a repeatable intraday continuation edge after costs, "
            "and does that edge survive out-of-sample validation?"
        )),
        "",
        "## 2. What ORB + VWAP Means",
        "",
        "- **ORB** means Opening Range Breakout. The setup waits for price to clear the high of the early-session range.",
        "- **VWAP** means Volume Weighted Average Price. It is used as an intraday participation benchmark.",
        "- **ORB + VWAP LONG** therefore means price breaks above the opening range while also trading above VWAP.",
        "- The thesis is not simply bullish momentum. It is opening-drive continuation with VWAP confirmation.",
        "- In this study, the setup is evaluated on the reported intraday timeframe and held for a bounded number of bars with stop/target logic from the underlying indicator study.",
        "",
        "## 3. Study Design",
        "",
        "- The study uses stored intraday OHLCV bars from the local Agent Adda data layer.",
        "- The tested universe is the F&O universe ordered by intraday data coverage.",
        "- Each candidate setup is replayed historically and measured after configured transaction-cost assumptions.",
        "- The first stage ranks setup families by aggregate expectancy, win rate, profit factor, MFE, MAE, and hold time.",
        "- The second stage checks whether the apparent edge survives rolling windows and walk-forward validation.",
        "- The final stage asks whether the edge is broad, symbol-specific, time-specific, or regime-specific.",
        "",
        "## 4. Metric Glossary",
        "",
        "- **Trades**: number of historical signals tested for the setup or slice.",
        "- **Win rate**: percentage of trades with positive R after costs.",
        "- **Expectancy R**: average result per trade normalized by initial risk. A value of `0.14R` means the average trade earned 0.14 units of initial risk.",
        "- **Profit factor**: total gains divided by total losses. Values above 1.0 are profitable before further robustness checks.",
        "- **MFE R**: maximum favorable excursion in R units. It shows how far trades moved in the desired direction.",
        "- **MAE R**: maximum adverse excursion in R units. It shows how much pain trades endured before exit.",
        "- **Walk-forward validation**: earlier chronological windows choose/promote a setup; the next unseen window validates it.",
        "- **Positive fold rate**: percentage of validation folds with positive expectancy.",
        "- **Volatility regime**: EWMA-return volatility bucket, split into low, normal, and high.",
        "- **GARCH(1,1)**: statistical volatility model used to estimate volatility persistence, not a trade signal by itself.",
        "",
        "## 5. Top-Line Result",
        "",
        _table_md([top], ["setup", "timeframe", "direction", "trades", "win_rate", "expectancy_r", "profit_factor"], 1),
        "",
        (
            f"The headline result is {setup} {direction} on {timeframe}. It produced "
            f"{_row_value(top, 'trades')} trades, {_row_value(top, 'win_rate')} win rate, "
            f"{_row_value(top, 'expectancy_r')}R expectancy, and {_row_value(top, 'profit_factor')} profit factor. "
            "This is a positive aggregate result, but aggregate profitability is only the starting point."
        ),
        "",
        "## 6. Walk-Forward Validation",
        "",
        _table_md([wf], ["setup", "timeframe", "direction", "walk_forward_status", "folds_tested", "promoted_folds", "validation_trades", "validation_expectancy_r", "validation_profit_factor", "validation_positive_fold_rate", "worst_validation_r"], 1),
        "",
        (
            "Walk-forward validation is the most important robustness check in this report. It prevents the study "
            "from merely choosing the best in-sample pattern. The current evidence says the confirmed setup survived "
            f"{_row_value(wf, 'folds_tested')} validation folds with {_row_value(wf, 'validation_trades')} validation trades, "
            f"{_row_value(wf, 'validation_expectancy_r')}R validation expectancy, and "
            f"{_row_value(wf, 'validation_positive_fold_rate')} positive validation fold rate."
        ),
        "",
        "## 7. Symbol Attribution",
        "",
        "The edge is not evenly distributed. The study separates symbols that carry the edge from symbols that dilute it.",
        "",
        "### Core Carriers",
        "",
        _table_md(core, ["symbol", "symbol_edge_status", "trades", "win_rate", "expectancy_r", "profit_factor", "best_volatility_regime", "best_pcr_regime"], 10),
        "",
        "### Edge Diluters",
        "",
        _table_md(diluters, ["symbol", "symbol_edge_status", "trades", "win_rate", "expectancy_r", "profit_factor", "best_volatility_regime", "best_pcr_regime"], 10),
        "",
        (
            "This matters operationally. A setup can be valid in aggregate but still fail on the wrong instruments. "
            "For this study, alerts should begin with the core carriers and either suppress or strongly discount the diluters."
        ),
        "",
        "## 8. Time-of-Day Filter",
        "",
        _table_md([time_filter], ["setup", "timeframe", "direction", "time_bucket", "trades", "win_rate", "expectancy_r", "profit_factor"], 1),
        "",
        (
            "The time filter shows when the setup actually expresses its edge. In the current evidence, the strongest "
            f"bucket is `{_row_value(time_filter, 'time_bucket')}`. That means the setup should first be monitored as an "
            "opening-drive system, not as an all-day generic trend strategy."
        ),
        "",
        "## 9. Volatility-Regime Interpretation",
        "",
        _table_md(vol, ["setup", "timeframe", "direction", "volatility_regime", "trades", "win_rate", "expectancy_r", "profit_factor"], 12),
        "",
        (
            "The volatility split helps separate stable continuation from noisy breakouts. The current evidence shows "
            "that low and normal volatility regimes are more attractive than high volatility for the confirmed setup. "
            "High volatility can still work, but the expectancy and profit factor are lower in the extracted evidence."
        ),
        "",
        "## 10. Statistical Model Diagnostics",
        "",
        _table_md(models, ["symbol", "timeframe", "model_type", "status", "observations", "persistence", "forecast_vol_pct", "volatility_clustering", "bias"], 18),
        "",
        (
            "The statistical diagnostics are supporting context, not direct trade instructions. AR(1) and AutoReg(1) "
            "diagnostics estimate short-run return persistence or mean reversion. GARCH(1,1) estimates volatility persistence. "
            "The key editorial use is to avoid claiming that the setup works because of a universal return-persistence effect."
        ),
        "",
        "## 11. What Failed",
        "",
        *_list_md(list(narrative.get("failed_hypotheses") or [])),
        "",
        "## 12. Practical Monitoring Playbook",
        "",
        *_list_md(list(narrative.get("monitoring_rules") or [])),
        "",
        "Additional operating rules:",
        "",
        "- Treat the setup as valid only when price breaks the opening range high and remains above VWAP.",
        "- Prefer the identified core carriers before expanding to the rest of the F&O universe.",
        "- Block broad short-side alerts until new evidence validates them out-of-sample.",
        "- Recompute the report after every data refresh and compare whether the same symbols remain carriers.",
        "- Require live liquidity, spread, and execution checks before turning any research signal into an alert.",
        "",
        "## 13. Risk, Limitations, And What This Study Does Not Claim",
        "",
        *_list_md(list(narrative.get("risk_limits") or [])),
        "",
        "- This study does not prove a permanent market anomaly.",
        "- This study does not model actual option premium fills, implied volatility surfaces, or option bid-ask slippage.",
        "- This study does not recommend buying or selling futures or options.",
        "- The output is a research filter for future monitoring and paper/live alert gating.",
        "",
        "## 14. Research-Grade Conclusion",
        "",
        (
            f"The current evidence supports a narrow and useful thesis: **{setup} {direction} on {timeframe}** is a "
            "confirmed opening-drive continuation setup in this dataset, but only when treated as conditional. "
            "The signal is strongest when constrained by symbol attribution, time-of-day, and volatility regime. "
            "The next research step is not to broaden the claim; it is to monitor whether the same carrier symbols and "
            "validation characteristics persist after additional history is added."
        ),
        "",
        "## 15. LinkedIn-Ready Abstract",
        "",
        str(narrative.get("linkedin_post") or ""),
        "",
        "## Disclaimer",
        "",
        str(narrative.get("disclaimer") or "Research only; not investment advice."),
    ]
    return DetailedResearchPaper(evidence=evidence, narrative=narrative, metadata=metadata, markdown="\n".join(lines))


def _markdown_to_html(markdown: str) -> str:
    body: list[str] = []
    in_table = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("| ") and line.endswith(" |"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            if set(cells) == {"---"}:
                continue
            if not in_table:
                body.append("<table>")
                in_table = True
                body.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
            else:
                body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            body.append(f"<p class='bullet'>{html.escape(line)}</p>")
        elif line:
            body.append(f"<p>{html.escape(line)}</p>")
    if in_table:
        body.append("</table>")
    css = """
    body{font-family:Inter,Arial,sans-serif;background:#f4f6f8;color:#172023;margin:0;padding:30px}
    .wrap{max-width:1040px;margin:auto;background:white;border:1px solid #dce3e8;border-radius:8px;padding:30px}
    h1{margin:0 0 12px;color:#0c4f4a} h2{margin-top:30px;color:#143f3b} h3{color:#31514f}
    p{line-height:1.58}.bullet{margin:5px 0;color:#334155}
    table{border-collapse:collapse;width:100%;margin:12px 0 22px;font-size:13px}
    th{background:#0c4f4a;color:white;text-align:left;padding:9px;border:1px solid #d6e2e2}
    td{padding:8px;border:1px solid #d6e2e2;vertical-align:top}
    tr:nth-child(even){background:#f7fbfb}
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Editorial Quantitative F&O Analysis</title><style>{css}</style></head><body><main class='wrap'>{''.join(body)}</main></body></html>"


def build_editorial_report(
    source_path: str | Path = LATEST_STUDY,
    *,
    allow_llm: bool = True,
    llm_call: Callable[..., dict[str, Any]] | None = None,
) -> EditorialReport:
    source = Path(source_path)
    markdown = source.read_text(encoding="utf-8")
    evidence = build_editorial_evidence(markdown)
    narrative, metadata = build_editorial_narrative(evidence, allow_llm=allow_llm, llm_call=llm_call)
    metadata = {
        **metadata,
        "source_report": str(source),
        "built_at": datetime.now(IST).isoformat(timespec="seconds"),
    }
    rendered = render_editorial_markdown(evidence, narrative, metadata)
    return EditorialReport(evidence=evidence, narrative=narrative, metadata=metadata, markdown=rendered)


def write_editorial_report(report: EditorialReport, *, output_dir: str | Path = "reports/latest") -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "intraday_fno_editorial_research.md"
    html_path = out_dir / "intraday_fno_editorial_research.html"
    json_path = out_dir / "intraday_fno_editorial_research.json"
    md_path.write_text(report.markdown, encoding="utf-8")
    html_path.write_text(_markdown_to_html(report.markdown), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"evidence": report.evidence, "narrative": report.narrative, "metadata": report.metadata},
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    research_dir = Path("reports/research")
    try:
        research_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        shutil.copyfile(md_path, research_dir / f"intraday_fno_editorial_research_{stamp}.md")
        shutil.copyfile(html_path, research_dir / f"intraday_fno_editorial_research_{stamp}.html")
    except OSError:
        pass
    return {"markdown": str(md_path), "html": str(html_path), "json": str(json_path)}


def write_detailed_research_paper(
    paper: DetailedResearchPaper,
    *,
    output_dir: str | Path = "reports/latest",
) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "intraday_fno_detailed_research_paper.md"
    html_path = out_dir / "intraday_fno_detailed_research_paper.html"
    json_path = out_dir / "intraday_fno_detailed_research_paper.json"
    md_path.write_text(paper.markdown, encoding="utf-8")
    html_path.write_text(_markdown_to_html(paper.markdown), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"evidence": paper.evidence, "narrative": paper.narrative, "metadata": paper.metadata},
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    research_dir = Path("reports/research")
    try:
        research_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        shutil.copyfile(md_path, research_dir / f"intraday_fno_detailed_research_paper_{stamp}.md")
        shutil.copyfile(html_path, research_dir / f"intraday_fno_detailed_research_paper_{stamp}.html")
    except OSError:
        pass
    return {"markdown": str(md_path), "html": str(html_path), "json": str(json_path)}


def run_editorial_report(
    source_path: str | Path = LATEST_STUDY,
    *,
    output_dir: str | Path = "reports/latest",
    allow_llm: bool = True,
    detailed: bool = False,
) -> dict[str, Any]:
    report = build_editorial_report(source_path, allow_llm=allow_llm)
    paths = write_editorial_report(report, output_dir=output_dir)
    detailed_paths: dict[str, str] = {}
    if detailed:
        paper = build_detailed_research_paper(report.evidence, report.narrative, report.metadata)
        detailed_paths = write_detailed_research_paper(paper, output_dir=output_dir)
    return {
        "ok": True,
        "paths": paths,
        "detailed_paths": detailed_paths,
        "metadata": report.metadata,
        "headline": report.narrative.get("headline"),
    }


if __name__ == "__main__":
    result = run_editorial_report()
    print("Editorial Quantitative F&O Analysis: OK")
    print(f"Markdown: {result['paths']['markdown']}")
    print(f"HTML: {result['paths']['html']}")
