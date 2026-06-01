"""Leakage critic for strategy and historical tests."""

from __future__ import annotations

from terminal.research_council.critics.base import Critic, finding


class LeakageCritic(Critic):
    name = "leakage"

    def run_deterministic(self, state):
        flags = getattr(state, "flags", {}) or {}
        findings = []
        if flags.get("latest_fundamentals_used_in_history"):
            findings.append(
                finding(
                    finding_id="leakage_latest_fundamentals",
                    severity="block",
                    target={"kind": "backtest", "id": "fundamentals"},
                    description="Historical test uses latest fundamentals.",
                    recommendation="Use point-in-time fundamentals only.",
                )
            )
        split_policy = flags.get("split_policy")
        if split_policy and split_policy not in {"train_validation_test_time_ordered", "time_ordered"}:
            findings.append(
                finding(
                    finding_id="leakage_split_policy",
                    severity="block",
                    target={"kind": "backtest", "id": "split_policy"},
                    description=f"Split policy is not time ordered: {split_policy}.",
                    recommendation="Use a time ordered train/validation/test split.",
                )
            )
        return self.make_review(state, findings, summary=f"{len(findings)} leakage findings.")
