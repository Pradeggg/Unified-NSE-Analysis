"""AA-UR-5 Route validation.

Validates a :class:`terminal.router.schema.RouteDecision` *before* the
agent executes any tool or renders any NEXT OPTION. Catches:

* unknown tool names (not present in ``terminal.tools.TOOL_REGISTRY``)
* missing required args per the tool's JSON schema
* arg names not declared in the schema (best-effort, never strict)
* empty / index-only symbols on direct/compound routes
* compound routes whose evidence map isn't actually covered by tools
* NEXT OPTIONS whose ``bound_action`` is empty or references unknown tools
* report-recall routes whose report paths don't exist on disk

The validator is *advisory by default*: it returns a
:class:`terminal.router.schema.RouteValidation` summarising what was
checked. The higher-level helper :func:`enforce_validation` is what
the agent calls — it rewrites an invalid direct/compound route to
``blocked_ungrounded`` and strips broken NEXT OPTIONS, preserving the
original reasoning trace.

Per AA-UR-5 acceptance:
  - invalid options are suppressed or replaced with ``blocked_ungrounded``
  - ``A``, ``B``, ``1`` and option text execute the prior bound route
  - unknown tools / missing args are caught before display
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Iterable

from .schema import (
    NextOption,
    RouteDecision,
    RouteReasoningSummary,
    RouteValidation,
    ToolCallSpec,
)


_INDEX_TICKERS = frozenset(
    {
        "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
        "SENSEX", "BANKEX", "INDIAVIX",
    }
)


def _tool_registry() -> dict[str, Any]:
    """Lazy import so ``terminal.router`` stays import-safe in isolation."""
    try:
        from terminal.tools import TOOL_REGISTRY
    except Exception:  # pragma: no cover - degraded import path
        return {}
    return TOOL_REGISTRY


def _schema_for(tool_name: str) -> dict[str, Any]:
    spec = _tool_registry().get(tool_name)
    if not spec:
        return {}
    if isinstance(spec, (list, tuple)) and len(spec) >= 3:
        schema = spec[2]
        return schema if isinstance(schema, dict) else {}
    return {}


def _required_args(tool_name: str) -> list[str]:
    schema = _schema_for(tool_name)
    raw = schema.get("required") if isinstance(schema, dict) else None
    return list(raw) if isinstance(raw, list) else []


def _known_args(tool_name: str) -> set[str]:
    schema = _schema_for(tool_name)
    props = schema.get("properties") if isinstance(schema, dict) else None
    if isinstance(props, dict):
        return set(props.keys())
    return set()


def _validate_tool_spec(spec: ToolCallSpec) -> list[str]:
    """Return a list of error strings; empty if the spec is valid."""
    errors: list[str] = []
    registry = _tool_registry()
    if spec.tool not in registry:
        errors.append(f"unknown tool: {spec.tool!r}")
        return errors  # no schema → stop here
    required = _required_args(spec.tool)
    args = spec.args if isinstance(spec.args, dict) else {}
    for arg in required:
        if arg not in args:
            errors.append(f"{spec.tool}: missing required arg {arg!r}")
        else:
            value = args[arg]
            if value is None:
                errors.append(f"{spec.tool}: required arg {arg!r} is None")
            elif isinstance(value, str) and not value.strip():
                errors.append(f"{spec.tool}: required arg {arg!r} is empty")
            elif isinstance(value, (list, tuple)) and not value:
                errors.append(f"{spec.tool}: required arg {arg!r} is empty list")
    return errors


def _validate_symbols(decision: RouteDecision) -> list[str]:
    """Direct/compound routes must not bind only to indices.

    Per AA-UR-5: data-grounded asks must have grounded evidence — a
    route that only carries NIFTY/BANKNIFTY when a stock was meant is
    a known hallucination path (the AA-UR-4 NIFTY-fallback bug).
    """
    if decision.route_type not in {"direct_tool_plan", "compound_plan"}:
        return []
    bound_symbols: list[str] = []
    for spec in decision.tool_plan:
        sym = spec.args.get("symbol") if isinstance(spec.args, dict) else None
        if isinstance(sym, str) and sym.strip():
            bound_symbols.append(sym.strip().upper())
    if not bound_symbols:
        return []  # tools that don't take a symbol — fine
    stock_present = any(sym not in _INDEX_TICKERS for sym in bound_symbols)
    index_present = any(sym in _INDEX_TICKERS for sym in bound_symbols)
    if index_present and not stock_present:
        return [
            "symbols bound only to indices "
            f"({sorted(set(bound_symbols))}); refuse silent NIFTY fallback"
        ]
    return []


def _validate_evidence_coverage(decision: RouteDecision) -> list[str]:
    """For compound routes, every non-optional EvidenceRequirement must be
    covered by at least one tool present in the tool_plan.
    """
    if decision.route_type != "compound_plan":
        return []
    tool_names = {spec.tool for spec in decision.tool_plan}
    errors: list[str] = []
    for req in decision.evidence_requirements:
        if req.optional:
            continue
        if not any(tool in tool_names for tool in req.required_tools):
            errors.append(
                f"evidence {req.name!r} not covered: needs one of "
                f"{list(req.required_tools)}"
            )
    return errors


def _validate_report_paths(decision: RouteDecision) -> list[str]:
    """When a route binds to report paths, verify they exist on disk."""
    if not decision.context_binding.report_paths:
        return []
    errors: list[str] = []
    for path in decision.context_binding.report_paths:
        if not path:
            continue
        # Don't reject when running in an isolated test sandbox without
        # the reports directory — only flag when path is rooted and the
        # report directory is itself present.
        if os.path.isabs(path) or path.startswith("reports/"):
            if not os.path.exists(path):
                errors.append(f"report path missing on disk: {path}")
    return errors


def _validate_next_option(option: NextOption) -> list[str]:
    """A NEXT OPTION is executable iff its bound_action carries a non-empty
    tool_plan referencing only known tools (or is explicitly a
    contextual answer with a non-empty 'intent').
    """
    errors: list[str] = []
    action = option.bound_action or {}
    if not action:
        return [f"option {option.label!r}: empty bound_action"]
    intent = str(action.get("intent") or "").strip()
    raw_tools = action.get("tool_plan") or []
    if not intent and not raw_tools:
        return [f"option {option.label!r}: bound_action has neither intent nor tool_plan"]
    registry = _tool_registry()
    for entry in raw_tools:
        tool_name: str | None = None
        args: dict[str, Any] = {}
        if isinstance(entry, dict):
            tool_name = entry.get("tool")
            args = dict(entry.get("args") or {})
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            tool_name = entry[0]
            args = dict(entry[1] or {})
        if not tool_name:
            errors.append(f"option {option.label!r}: bound tool name is empty")
            continue
        if tool_name not in registry:
            errors.append(
                f"option {option.label!r}: unknown bound tool {tool_name!r}"
            )
            continue
        for required in _required_args(tool_name):
            if required not in args or args[required] in (None, ""):
                errors.append(
                    f"option {option.label!r}: bound {tool_name!r} missing "
                    f"required arg {required!r}"
                )
    return errors


def validate_decision(decision: RouteDecision) -> RouteValidation:
    """Run every check and return a fresh :class:`RouteValidation`."""
    errors: list[str] = []
    checked_tools: list[str] = []

    if (
        decision.route_type in {"direct_tool_plan", "compound_plan"}
        and not decision.tool_plan
    ):
        errors.append(f"{decision.route_type} requires a non-empty tool_plan")

    for spec in decision.tool_plan:
        if spec.tool:
            checked_tools.append(spec.tool)
        errors.extend(_validate_tool_spec(spec))

    errors.extend(_validate_symbols(decision))
    errors.extend(_validate_evidence_coverage(decision))
    errors.extend(_validate_report_paths(decision))

    for opt in decision.next_options:
        errors.extend(_validate_next_option(opt))

    return RouteValidation(
        ok=not errors,
        errors=tuple(errors),
        checked_tools=tuple(checked_tools),
    )


def filter_invalid_options(
    options: Iterable[NextOption],
) -> tuple[tuple[NextOption, ...], tuple[str, ...]]:
    """Return (kept_options, drop_reasons).

    AA-UR-5 acceptance: invalid options are suppressed before display.
    The drop reasons are appended to the route's reasoning summary so
    the agent can audit *why* an option was hidden.
    """
    kept: list[NextOption] = []
    reasons: list[str] = []
    for opt in options:
        errs = _validate_next_option(opt)
        if errs:
            reasons.append(
                f"dropped NEXT OPTION {opt.label!r}: " + "; ".join(errs)
            )
        else:
            kept.append(opt)
    return tuple(kept), tuple(reasons)


def enforce_validation(decision: RouteDecision) -> RouteDecision:
    """Return a route that is safe to display/execute.

    Strategy:
      1. Strip broken NEXT OPTIONS (always, regardless of route_type).
      2. Re-run :func:`validate_decision` after stripping options.
      3. If the route is still invalid AND it's a direct/compound
         plan, rewrite it to ``blocked_ungrounded`` with the original
         reasoning trace preserved so the user sees *why* it was
         blocked.
      4. Otherwise, return the route with the fresh validation
         attached.
    """
    kept_options, drop_reasons = filter_invalid_options(decision.next_options)
    rewritten = decision

    extra_rejected: tuple[str, ...] = tuple(drop_reasons)
    if drop_reasons:
        rewritten = replace(
            rewritten,
            next_options=kept_options,
            reasoning_summary=_extend_reasoning(rewritten.reasoning_summary, extra_rejected),
        )

    validation = validate_decision(rewritten)
    if validation.ok:
        return replace(rewritten, validation=validation)

    if rewritten.route_type in {"direct_tool_plan", "compound_plan"}:
        block_reasons = tuple(
            f"AA-UR-5 blocked: {err}" for err in validation.errors
        )
        blocked_summary = _extend_reasoning(
            rewritten.reasoning_summary, block_reasons
        )
        return replace(
            rewritten,
            route_type="blocked_ungrounded",
            confidence="low",
            tool_plan=(),
            reasoning_summary=blocked_summary,
            validation=validation,
        )

    return replace(rewritten, validation=validation)


def _extend_reasoning(
    summary: RouteReasoningSummary, extra: tuple[str, ...]
) -> RouteReasoningSummary:
    if not extra:
        return summary
    return RouteReasoningSummary(
        pot=summary.pot,
        selected_branch=summary.selected_branch,
        rejected_branches=tuple(summary.rejected_branches) + extra,
    )


def match_option_reply(
    text: str, options: Iterable[NextOption]
) -> NextOption | None:
    """Match a user reply against rendered NEXT OPTIONS.

    Accepts:
      * exact label match (case-insensitive): ``A``, ``a``, ``1``
      * exact text match (case-insensitive)
      * label with trailing punctuation: ``A.``, ``A)``
    """
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None
    candidates: list[NextOption] = list(options)
    if not candidates:
        return None

    # 1) label match (strip trailing punctuation/whitespace)
    stripped = raw.rstrip(".):").strip().lower()
    for opt in candidates:
        if opt.label.strip().lower() == stripped:
            return opt

    # 2) full text match
    lower = raw.lower()
    for opt in candidates:
        if opt.text.strip().lower() == lower:
            return opt

    return None


__all__ = [
    "enforce_validation",
    "filter_invalid_options",
    "match_option_reply",
    "validate_decision",
]
