"""Agentic turn orchestration helpers for Agent Adda.

This module is intentionally deterministic. It binds only actions that can be
grounded in prior tool evidence or registered artifacts, and it stays disabled
unless ``AGENT_ADDA_AGENTIC_ORCHESTRATOR`` is truthy.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if re.fullmatch(r"[A-Z0-9&-]{2,20}", text):
        return text
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = _clean_symbol(value)
        if clean and _is_actionable_symbol(clean) and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _is_actionable_symbol(symbol: str) -> bool:
    """Filter exchange artifacts that should not become next-action stocks."""
    if "-RE" in symbol or symbol.endswith("RE1"):
        return False
    if symbol.endswith("ETF") or "ETF" in symbol:
        return False
    return True


def _jsonable_tool_plan(plan: list[tuple[str, dict[str, Any]]]) -> list[list[Any]]:
    return [[str(tool), dict(args or {})] for tool, args in plan or []]


def _tool_plan_from_snapshot(value: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for item in value or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        tool = str(item[0] or "")
        args = dict(item[1] or {}) if isinstance(item[1], dict) else {}
        if tool:
            out.append((tool, args))
    return out


@dataclass
class ArtifactRef:
    id: str
    kind: str
    title: str
    path: str
    symbols: list[str] = field(default_factory=list)
    created_by_workflow: str = ""
    created_at: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "path": self.path,
            "symbols": list(self.symbols),
            "created_by_workflow": self.created_by_workflow,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRef":
        return cls(
            id=str(data.get("id") or ""),
            kind=str(data.get("kind") or ""),
            title=str(data.get("title") or ""),
            path=str(data.get("path") or ""),
            symbols=_dedupe([str(v) for v in data.get("symbols") or []]),
            created_by_workflow=str(data.get("created_by_workflow") or ""),
            created_at=str(data.get("created_at") or _utcnow_iso()),
        )


@dataclass
class BoundNextAction:
    id: str
    label: str
    description: str
    action_type: str
    tool_plan: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    artifact_targets: list[str] = field(default_factory=list)
    requires_confirmation: bool = True
    created_at: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "action_type": self.action_type,
            "tool_plan": _jsonable_tool_plan(self.tool_plan),
            "entities": list(self.entities),
            "artifact_targets": list(self.artifact_targets),
            "requires_confirmation": self.requires_confirmation,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundNextAction":
        return cls(
            id=str(data.get("id") or ""),
            label=str(data.get("label") or ""),
            description=str(data.get("description") or ""),
            action_type=str(data.get("action_type") or ""),
            tool_plan=_tool_plan_from_snapshot(data.get("tool_plan") or []),
            entities=_dedupe([str(v) for v in data.get("entities") or []]),
            artifact_targets=[str(v) for v in data.get("artifact_targets") or []],
            requires_confirmation=bool(data.get("requires_confirmation", True)),
            created_at=str(data.get("created_at") or _utcnow_iso()),
        )


@dataclass
class AgenticTurnState:
    user_goal: str = ""
    workflow: str = "direct_answer"
    expanded_query: str = ""
    resolved_entities: list[str] = field(default_factory=list)
    artifacts: list[ArtifactRef | dict[str, Any]] = field(default_factory=list)
    final_takeaway: str = ""
    caveats: list[str] = field(default_factory=list)
    next_actions: list[BoundNextAction] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        self.resolved_entities = _dedupe(self.resolved_entities)
        self.artifacts = [
            ArtifactRef.from_dict(item) if isinstance(item, dict) else item
            for item in self.artifacts
        ]
        self.next_actions = [
            BoundNextAction.from_dict(item) if isinstance(item, dict) else item
            for item in self.next_actions
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "workflow": self.workflow,
            "expanded_query": self.expanded_query,
            "resolved_entities": list(self.resolved_entities),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts if isinstance(artifact, ArtifactRef)],
            "final_takeaway": self.final_takeaway,
            "caveats": list(self.caveats),
            "next_actions": [action.to_dict() for action in self.next_actions],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AgenticTurnState | None":
        if not isinstance(data, dict) or not data:
            return None
        return cls(
            user_goal=str(data.get("user_goal") or ""),
            workflow=str(data.get("workflow") or "direct_answer"),
            expanded_query=str(data.get("expanded_query") or ""),
            resolved_entities=[str(v) for v in data.get("resolved_entities") or []],
            artifacts=[item for item in data.get("artifacts") or [] if isinstance(item, dict)],
            final_takeaway=str(data.get("final_takeaway") or ""),
            caveats=[str(v) for v in data.get("caveats") or []],
            next_actions=[item for item in data.get("next_actions") or [] if isinstance(item, dict)],
            created_at=str(data.get("created_at") or _utcnow_iso()),
        )


def agentic_orchestrator_enabled() -> bool:
    return os.environ.get("AGENT_ADDA_AGENTIC_ORCHESTRATOR", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
    }


def is_confirmation(text: str) -> bool:
    clean = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not clean or clean.startswith("/"):
        return False
    return clean in {
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
        "sure go ahead",
        "go ahead",
        "do it",
        "please do",
        "yes please",
        "proceed",
        "continue",
        "lets do it",
        "let's do it",
    }


def action_from_confirmation(
    text: str,
    state: AgenticTurnState | None,
) -> BoundNextAction | None:
    if not is_confirmation(text) or state is None:
        return None
    for action in state.next_actions:
        if action.requires_confirmation and action.tool_plan:
            return action
    return None


def action_from_artifact_reference(
    text: str,
    state: AgenticTurnState | None,
) -> BoundNextAction | None:
    if state is None:
        return None
    clean = (text or "").strip().lower()
    if clean.startswith("/"):
        return None
    if not re.search(r"\b(it|this|that|report|latest report|file)\b", clean):
        return None
    report = _latest_report_artifact(state)
    if report is None:
        return None
    if re.search(r"\b(open|show|launch)\b", clean):
        return BoundNextAction(
            id="open_latest_artifact",
            label="Open latest report",
            description=f"Open {report.path}",
            action_type="tool_plan",
            tool_plan=[("open_report", {"path": report.path})],
            artifact_targets=[report.path],
            requires_confirmation=False,
        )
    if re.search(r"\b(read|summari[sz]e|summary)\b", clean):
        return BoundNextAction(
            id="read_latest_artifact",
            label="Read latest report",
            description=f"Read {report.path}",
            action_type="tool_plan",
            tool_plan=[("read_report", {"path": report.path, "max_chars": 12000})],
            artifact_targets=[report.path],
            requires_confirmation=False,
        )
    if re.search(r"\b(email|mail|send)\b", clean):
        return BoundNextAction(
            id="locate_latest_artifact_for_email",
            label="Locate latest report for email",
            description=f"Locate {report.path} for email dispatch",
            action_type="tool_plan",
            tool_plan=[("get_last_report", {"last_report_path": report.path})],
            artifact_targets=[report.path],
            requires_confirmation=False,
        )
    return None


def extract_artifacts(tool_results: list[dict[str, Any]]) -> list[ArtifactRef]:
    artifacts: list[ArtifactRef] = []
    seen: set[str] = set()
    for idx, item in enumerate(tool_results or []):
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        symbols = _symbols_from_payload(result) or _symbols_from_payload(item.get("args") or {})
        candidates: list[tuple[str, str]] = []
        for key in ("html_path", "report_path", "path"):
            path = str(result.get(key) or "")
            if path:
                candidates.append((path, _kind_from_path(path)))
        paths = result.get("report_paths")
        if isinstance(paths, dict):
            for kind_key, path_value in paths.items():
                path = str(path_value or "")
                if path:
                    candidates.append((path, _kind_from_path(path, str(kind_key))))
        for key in ("json_path", "evidence_path"):
            path = str(result.get(key) or "")
            if path:
                candidates.append((path, "json_evidence"))
        files = result.get("files")
        if isinstance(files, list):
            for file_item in files[:5]:
                if isinstance(file_item, dict):
                    path = str(file_item.get("path") or "")
                else:
                    path = str(file_item or "")
                if path:
                    candidates.append((path, _kind_from_path(path)))
        for path, kind in candidates:
            if path in seen or not _looks_like_artifact_path(path):
                continue
            seen.add(path)
            artifacts.append(
                ArtifactRef(
                    id=f"artifact_{idx + 1}_{len(artifacts) + 1}",
                    kind=kind,
                    title=path.rsplit("/", 1)[-1],
                    path=path,
                    symbols=symbols,
                    created_by_workflow=str(item.get("tool") or ""),
                )
            )
    return artifacts


def build_agentic_turn_state(
    *,
    user_input: str,
    intent: str,
    tool_results: list[dict[str, Any]],
    answer: str,
    previous_state: AgenticTurnState | None = None,
) -> AgenticTurnState | None:
    if not tool_results and previous_state is None:
        return None
    workflow = _workflow_for(intent, tool_results, user_input)
    artifacts = extract_artifacts(tool_results)
    symbols = _symbols_from_tool_results(tool_results)
    caveats = _extract_caveats(answer)
    next_actions = _build_next_actions(workflow, symbols, artifacts)
    if not next_actions and artifacts:
        report = _latest_report_artifact(AgenticTurnState(artifacts=artifacts))
        if report:
            next_actions.append(
                BoundNextAction(
                    id="open_latest_artifact",
                    label="Open latest report",
                    description=f"Open {report.path}",
                    action_type="tool_plan",
                    tool_plan=[("open_report", {"path": report.path})],
                    artifact_targets=[report.path],
                )
            )
    if not next_actions and not artifacts and not caveats:
        return None
    return AgenticTurnState(
        user_goal=(user_input or "").strip(),
        workflow=workflow,
        expanded_query=(user_input or "").strip(),
        resolved_entities=symbols,
        artifacts=artifacts,
        final_takeaway=_first_sentence(answer),
        caveats=caveats,
        next_actions=next_actions,
    )


def append_next_action_block(answer: str, state: AgenticTurnState | None) -> str:
    if state is None or not state.next_actions or "▶ NEXT ACTION" in (answer or ""):
        return answer
    action = state.next_actions[0]
    details = action.description or action.label
    if action.entities:
        details = f"{details} ({', '.join(action.entities)})"
    return (
        f"{answer.rstrip()}\n\n"
        "▶ NEXT ACTION\n"
        f"  {action.label}\n"
        f"  {details}\n"
        "  Reply `go ahead` to run this bound action."
    )


def render_bound_action_summary(
    action: BoundNextAction,
    tool_results: list[dict[str, Any]],
) -> str:
    """Render multi-symbol bound-action results without collapsing to stock 1."""
    symbols = action.entities or _symbols_from_tool_results(tool_results)
    if len(symbols) <= 1:
        return ""
    grouped = _group_tool_results_by_symbol(tool_results)
    lines: list[str] = [
        f"▶ BOUND ACTION — {action.label}",
        f"  Scope: {', '.join(symbols)}",
        "",
        "▶ SHORTLIST DEEP DIVE",
    ]
    for symbol in symbols:
        bucket = grouped.get(symbol, {})
        snapshot = bucket.get("get_symbol_snapshot") or {}
        technical = bucket.get("get_technical_setup") or {}
        screener = bucket.get("scrape_screener_in") or {}
        sector = bucket.get("get_sector_context") or {}
        announcements = bucket.get("search_nse_announcements") or {}
        name = (
            snapshot.get("company_name")
            or screener.get("company_name")
            or symbol
        )
        parts = [
            f"{symbol} — {name}",
            f"Price {_fmt_value(snapshot.get('price') or technical.get('price') or screener.get('current_price'))}",
            f"Stage {_fmt_value(snapshot.get('stage') or technical.get('stage'))}",
            f"Signal {_fmt_value(snapshot.get('signal') or technical.get('signal'))}",
            f"RS {_fmt_value(snapshot.get('rs') or snapshot.get('rs_pct') or technical.get('rs_pct'))}",
            f"RSI {_fmt_value(technical.get('rsi') or snapshot.get('rsi'))}",
        ]
        ratio_bits = _ratio_bits(screener)
        if ratio_bits:
            parts.extend(ratio_bits)
        if sector and not sector.get("error"):
            parts.append(f"Sector {_fmt_value(sector.get('sector'))}")
        if announcements and not announcements.get("error"):
            count = announcements.get("count")
            if count is not None:
                parts.append(f"Filings {count}")
        lines.append("  - " + " | ".join(parts))
        gaps = _missing_tools_for_symbol(bucket)
        if gaps:
            lines.append(f"    Missing/weak evidence: {', '.join(gaps)}")
    lines.extend(
        [
            "",
            "▶ HOW TO READ THIS",
            "  Treat this as a first-pass shortlist audit. Prefer names where price strength, Stage 2/BUY structure, fundamentals, and sector context agree.",
            "",
            "▶ SOURCE TRAIL",
        ]
    )
    for item in tool_results:
        tool = str(item.get("tool") or "tool")
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        status = "ERROR: " + str(result.get("error")) if result.get("error") else "ok"
        lines.append(f"  {tool}: {status}")
    lines.append("")
    lines.append("━━━ Not investment advice. For research and learning only. ━━━")
    return "\n".join(lines)


def _workflow_for(intent: str, tool_results: list[dict[str, Any]], user_input: str) -> str:
    names = {str(item.get("tool") or "") for item in tool_results or []}
    q = (user_input or "").lower()
    if "email" in q or "mail" in q:
        return "email_dispatch"
    if any(name in names for name in {"run_quality_breakout_screener", "get_live_market_overview", "get_market_breadth"}):
        return "market_scan"
    if "run_screener_query" in names:
        return "screener"
    if any("report" in name for name in names) or any("path" in (item.get("result") or {}) for item in tool_results or [] if isinstance(item.get("result"), dict)):
        return "report_generation"
    if any(name in names for name in {"get_symbol_snapshot", "get_technical_setup", "scrape_screener_in"}):
        return "stock_deep_dive"
    return intent or "direct_answer"


def _group_tool_results_by_symbol(tool_results: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    last_symbol = ""
    for item in tool_results or []:
        tool = str(item.get("tool") or "")
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        symbols = _symbols_from_payload(args) or _symbols_from_payload(result)
        symbol = symbols[0] if symbols else last_symbol
        if not symbol:
            continue
        last_symbol = symbol
        grouped.setdefault(symbol, {})[tool] = result
    return grouped


def _fmt_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _ratio_bits(screener: dict[str, Any]) -> list[str]:
    ratios = screener.get("ratios") if isinstance(screener.get("ratios"), dict) else screener
    bits: list[str] = []
    for label, keys in (
        ("P/E", ("Stock P/E", "stock_pe", "pe")),
        ("ROCE", ("ROCE", "roce")),
        ("ROE", ("ROE", "roe")),
    ):
        for key in keys:
            if isinstance(ratios, dict) and ratios.get(key) not in (None, ""):
                bits.append(f"{label} {_fmt_value(ratios.get(key))}")
                break
    return bits


def _missing_tools_for_symbol(bucket: dict[str, dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for tool in (
        "get_symbol_snapshot",
        "get_technical_setup",
        "get_sector_context",
        "scrape_screener_in",
        "search_nse_announcements",
    ):
        result = bucket.get(tool)
        if not result:
            missing.append(tool)
        elif result.get("error"):
            missing.append(f"{tool} error")
    return missing[:5]


def _build_next_actions(
    workflow: str,
    symbols: list[str],
    artifacts: list[ArtifactRef],
) -> list[BoundNextAction]:
    if workflow in {"market_scan", "screener"} and symbols:
        top_symbols = symbols[:4]
        plan: list[tuple[str, dict[str, Any]]] = []
        for symbol in top_symbols:
            plan.extend(
                [
                    ("resolve_symbol", {"query": symbol}),
                    ("get_symbol_snapshot", {"symbol": symbol}),
                    ("get_technical_setup", {"symbol": symbol}),
                    ("get_sector_context", {"sector_or_symbol": symbol}),
                    ("scrape_screener_in", {"symbol": symbol}),
                    ("search_nse_announcements", {"symbol": symbol, "days": 14}),
                ]
            )
        return [
            BoundNextAction(
                id="next_deep_dive_top_symbols",
                label=f"Deep dive top {len(top_symbols)} with RIC-style evidence",
                description="Run technical, sector, fundamentals, and announcements evidence for the shortlisted names",
                action_type="tool_plan",
                tool_plan=plan,
                entities=top_symbols,
                artifact_targets=["evidence_summary"],
            )
        ]
    if workflow == "report_generation" and artifacts:
        report = _latest_report_artifact(AgenticTurnState(artifacts=artifacts))
        if report:
            return [
                BoundNextAction(
                    id="open_latest_artifact",
                    label="Open latest report",
                    description=f"Open {report.path}",
                    action_type="tool_plan",
                    tool_plan=[("open_report", {"path": report.path})],
                    artifact_targets=[report.path],
                )
            ]
    return []


def _symbols_from_tool_results(tool_results: list[dict[str, Any]]) -> list[str]:
    symbols: list[str] = []
    for item in tool_results or []:
        tool = str(item.get("tool") or "")
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        if tool == "run_quality_breakout_screener":
            symbols.extend(_symbols_from_screen_result(result))
        if tool == "run_screener_query":
            symbols.extend(_symbols_from_screen_result(result))
        if tool == "get_top_gainers_losers":
            symbols.extend(_symbols_from_top_movers(result))
        symbols.extend(_symbols_from_payload(args))
        symbols.extend(_symbols_from_payload(result))
    return _dedupe(symbols)


def _symbols_from_screen_result(result: dict[str, Any]) -> list[str]:
    symbols: list[str] = []
    for key in ("items", "results", "candidates", "stocks", "rows"):
        rows = result.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                symbols.append(str(row.get("symbol") or row.get("ticker") or ""))
            else:
                symbols.append(str(row))
    return symbols


def _symbols_from_top_movers(result: dict[str, Any]) -> list[str]:
    symbols: list[str] = []
    for key in ("gainers", "top_gainers", "leaders"):
        rows = result.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    symbols.append(str(row.get("symbol") or row.get("ticker") or ""))
                else:
                    symbols.append(str(row))
    if symbols:
        return symbols
    for key in ("losers", "top_losers", "laggards"):
        rows = result.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    symbols.append(str(row.get("symbol") or row.get("ticker") or ""))
                else:
                    symbols.append(str(row))
    return symbols


def _symbols_from_payload(payload: Any) -> list[str]:
    symbols: list[str] = []
    if isinstance(payload, dict):
        for key in ("symbol", "ticker"):
            if payload.get(key):
                symbols.append(str(payload[key]))
        values = payload.get("symbols")
        if isinstance(values, list):
            symbols.extend(str(v) for v in values)
    return _dedupe(symbols)


def _looks_like_artifact_path(path: str) -> bool:
    return bool(re.search(r"\.(html|md|json|csv|pdf|png|jpg|jpeg)$", path, flags=re.I))


def _kind_from_path(path: str, hint: str = "") -> str:
    lower = f"{hint} {path}".lower()
    if lower.endswith(".html") or "html" in lower:
        return "html_report"
    if lower.endswith(".json") or "json" in lower or "evidence" in lower:
        return "json_evidence"
    if lower.endswith(".csv"):
        return "csv_artifact"
    if lower.endswith(".pdf"):
        return "pdf_report"
    if lower.endswith((".png", ".jpg", ".jpeg")):
        return "image"
    return "report"


def _latest_report_artifact(state: AgenticTurnState) -> ArtifactRef | None:
    reports = [
        item
        for item in state.artifacts
        if isinstance(item, ArtifactRef) and item.kind in {"html_report", "pdf_report", "report"}
    ]
    if not reports:
        return None
    return reports[-1]


def _extract_caveats(answer: str) -> list[str]:
    caveats: list[str] = []
    for line in (answer or "").splitlines():
        stripped = line.strip(" -•\t")
        lower = stripped.lower()
        if not stripped:
            continue
        if any(term in lower for term in ("missing evidence", "unavailable", "partial", "caveat", "failed")):
            caveats.append(stripped)
    return caveats[:5]


def _first_sentence(answer: str) -> str:
    clean = re.sub(r"\s+", " ", answer or "").strip()
    if not clean:
        return ""
    match = re.search(r"(.{20,240}?[.!?])\s", clean)
    if match:
        return match.group(1)
    return clean[:240]
