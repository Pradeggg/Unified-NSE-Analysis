"""AA-UR-3 :class:`UnifiedRouter` — the additive routing shim.

The router accepts ``(user_input, ContextPack)`` and returns a
:class:`RouteDecision`. It runs every registered provider, sorts the
resulting candidates by score (ties broken by registration order),
projects the winner into a ``RouteDecision`` whose
``reasoning_summary`` carries the selected branch + rejected branches,
and attaches a :class:`ContextBinding` derived from the pack.

This wrapper is intentionally side-effect free; it does not call into
``terminal.situation_assessment`` or ``terminal.agent``. Those modules
will be wired through the wrapper in later tickets (AA-UR-4..7). For
AA-UR-3, the wrapper is exercised exclusively by tests.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from .context import ContextPack
from .providers import DEFAULT_PROVIDERS, RouteProvider
from .schema import (
    ContextBinding,
    RouteCandidate,
    RouteDecision,
    RouteValidation,
)


def _default_providers() -> list[RouteProvider]:
    return [cls() for cls in DEFAULT_PROVIDERS]


def _binding_from_pack(pack: ContextPack, winner: RouteCandidate) -> ContextBinding:
    """Project the ContextPack into a ContextBinding for the winning route."""
    workflow_id = pack.active_workflow.workflow_id if pack.active_workflow else ""
    report_paths = tuple(report.path for report in pack.active_reports)
    binding_type = _binding_type_for(winner)

    # Merge pack symbols with any symbol arg the winning candidate's
    # tool_plan resolved to, so the binding reflects the route's actual
    # subject (e.g. AA-UR-4 compound prompts whose pack started empty).
    merged_symbols: list[str] = []
    for sym in pack.active_symbols:
        if sym and sym not in merged_symbols:
            merged_symbols.append(sym)
    for spec in winner.tool_plan:
        sym = spec.args.get("symbol") if isinstance(spec.args, dict) else None
        if isinstance(sym, str):
            value = sym.strip().upper()
            if value and value not in merged_symbols:
                merged_symbols.append(value)

    return ContextBinding(
        binding_type=binding_type,
        symbols=tuple(merged_symbols),
        indices=pack.active_indices,
        sectors=pack.active_sectors,
        report_paths=report_paths,
        workflow_id=workflow_id,
        freshness=pack.freshness,
    )


def _binding_type_for(candidate: RouteCandidate) -> str:
    if candidate.provider == "PendingOptionProvider":
        return "pending_option"
    if candidate.provider == "ContextualFollowupProvider":
        return "followup"
    if candidate.provider == "EntityTopicProvider":
        return "entity_topic"
    if candidate.provider == "ReportProvider":
        return "report_recall"
    if candidate.provider == "VisualScanProvider":
        return "visual_scan"
    if candidate.provider == "MarketSituationProvider":
        return "market_situation"
    if candidate.provider == "CompoundStockProvider":
        return "compound_stock"
    if candidate.provider == "DirectIntentProvider":
        return "direct_intent"
    return "none"


def _validate_candidate(candidate: RouteCandidate) -> RouteValidation:
    errors: list[str] = []
    checked_tools: list[str] = []
    if candidate.route_type in {"direct_tool_plan", "compound_plan"}:
        if not candidate.tool_plan:
            errors.append(
                f"{candidate.route_type} requires a non-empty tool_plan"
            )
        for spec in candidate.tool_plan:
            if not spec.tool:
                errors.append("tool_plan entry has empty tool name")
            else:
                checked_tools.append(spec.tool)
    return RouteValidation(ok=not errors, errors=tuple(errors), checked_tools=tuple(checked_tools))


def _no_candidate_decision(
    *,
    user_input: str,
    pack: ContextPack,
    rejected: tuple[str, ...],
) -> RouteDecision:
    """Fallback ``fallback_llm`` decision when no provider proposes anything."""
    binding = ContextBinding(
        binding_type="none",
        symbols=pack.active_symbols,
        indices=pack.active_indices,
        sectors=pack.active_sectors,
        report_paths=tuple(report.path for report in pack.active_reports),
        workflow_id=(pack.active_workflow.workflow_id if pack.active_workflow else ""),
        freshness=pack.freshness,
    )
    from .schema import RouteReasoningSummary  # local import to avoid cycles

    return RouteDecision(
        decision_id=str(uuid.uuid4()),
        intent="fallback",
        route_type="fallback_llm",
        confidence="low",
        user_is_asking=user_input.strip() or "(empty input)",
        context_binding=binding,
        reasoning_summary=RouteReasoningSummary(
            pot=("No provider proposed a candidate; deferring to fallback_llm.",),
            selected_branch="<none>",
            rejected_branches=rejected,
        ),
        validation=RouteValidation(ok=True, errors=(), checked_tools=()),
    )


class UnifiedRouter:
    """Provider-chain router that emits :class:`RouteDecision` objects."""

    def __init__(self, providers: Iterable[RouteProvider] | None = None) -> None:
        self.providers: list[RouteProvider] = (
            list(providers) if providers is not None else _default_providers()
        )

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self.providers]

    def route(
        self,
        user_input: str,
        context_pack: ContextPack,
    ) -> RouteDecision:
        """Return the winning :class:`RouteDecision` for ``user_input``."""
        if user_input is None:
            user_input = ""

        all_candidates: list[tuple[int, RouteCandidate]] = []
        for idx, provider in enumerate(self.providers):
            try:
                proposed = provider.propose(user_input, context_pack) or []
            except Exception as exc:  # noqa: BLE001
                # A misbehaving provider must never crash the router.
                from .schema import RouteCandidate as _RC

                proposed = []
                # Record an explicit rejection reason via a zero-score candidate
                # so the trace surfaces the error.
                all_candidates.append(
                    (
                        idx,
                        _RC(
                            provider=getattr(provider, "name", type(provider).__name__),
                            intent="provider_error",
                            route_type="fallback_llm",
                            confidence="low",
                            score=0.0,
                            reasons=(f"provider raised: {exc!r}",),
                        ),
                    )
                )
                continue
            for cand in proposed:
                all_candidates.append((idx, cand))

        if not all_candidates:
            return _no_candidate_decision(
                user_input=user_input,
                pack=context_pack,
                rejected=tuple(p.name for p in self.providers),
            )

        # Sort by (score DESC, registration_index ASC) — first-registered wins ties.
        all_candidates.sort(key=lambda pair: (-pair[1].score, pair[0]))
        _, winner = all_candidates[0]
        rejected = tuple(
            f"{cand.provider}:{cand.score:.2f}:{cand.intent}"
            for _, cand in all_candidates[1:]
        )

        binding = _binding_from_pack(context_pack, winner)
        validation = _validate_candidate(winner)
        decision = winner.to_decision(
            decision_id=str(uuid.uuid4()),
            user_is_asking=user_input.strip(),
            context_binding=binding,
            validation=validation,
            rejected_branches=rejected,
        )
        return decision


__all__ = ["UnifiedRouter"]
