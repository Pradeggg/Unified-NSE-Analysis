"""Governance evaluation engine for NSE-listed companies."""

from terminal.governance.models import GovernanceReport

__all__ = ["GovernanceReport", "evaluate_governance", "render_markdown"]


def __getattr__(name: str):
    if name == "evaluate_governance":
        from terminal.governance.engine import evaluate_governance

        return evaluate_governance
    if name == "render_markdown":
        from terminal.governance.markdown import render_markdown

        return render_markdown
    raise AttributeError(name)
