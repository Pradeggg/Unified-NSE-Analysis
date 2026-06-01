"""Overfit critic for generated strategies."""

from __future__ import annotations

from terminal.research_council.critics.base import Critic, finding


class OverfitCritic(Critic):
    name = "overfit"

    def run_deterministic(self, state):
        metrics = _strategy_metrics(state)
        findings = []
        if not metrics:
            return self.make_review(state, findings, summary="No strategy metrics supplied.")
        if metrics.get("trade_count") is not None and int(metrics.get("trade_count") or 0) < 30:
            findings.append(
                finding(
                    finding_id="overfit_trade_count",
                    severity="block",
                    target={"kind": "strategy", "id": "trade_count"},
                    description="Backtest trade count is too low for reliable inference.",
                    recommendation="Require at least 30 trades or mark strategy as untestable.",
                )
            )
        if int(metrics.get("parameter_count") or 0) > 8:
            findings.append(
                finding(
                    finding_id="overfit_parameter_count",
                    severity="warn",
                    target={"kind": "strategy", "id": "parameter_count"},
                    description="Strategy uses excessive parameters.",
                    recommendation="Reduce parameters or require stronger validation.",
                )
            )
        if metrics.get("validation_pass") is False:
            findings.append(
                finding(
                    finding_id="overfit_validation",
                    severity="block",
                    target={"kind": "strategy", "id": "validation"},
                    description="Strategy failed validation.",
                    recommendation="Do not advance until validation passes.",
                )
            )
        if float(metrics.get("regime_concentration_pct") or 0) > 70:
            findings.append(
                finding(
                    finding_id="overfit_regime_concentration",
                    severity="warn",
                    target={"kind": "strategy", "id": "regime_concentration"},
                    description="Returns are concentrated in one regime.",
                    recommendation="Validate across regimes or downgrade confidence.",
                )
            )
        return self.make_review(state, findings, summary=f"{len(findings)} overfit findings.")


def _strategy_metrics(state) -> dict:
    explicit = (getattr(state, "flags", {}) or {}).get("strategy_metrics") or {}
    if explicit:
        return explicit
    for plan_results in (getattr(state, "execution_results", {}) or {}).values():
        result = _mapping_get(plan_results, "coder_quant_shortlist_sweep")
        if not result or _mapping_get(result, "status") != "success":
            continue
        for output in _mapping_get(result, "outputs", []) or []:
            if not isinstance(output, dict) or output.get("ok") is False:
                continue
            best = output.get("best") or {}
            result_payload = best.get("result") or {}
            metrics = result_payload.get("metrics") or {}
            if metrics:
                return metrics
    return {}


def _mapping_get(payload, key, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)
