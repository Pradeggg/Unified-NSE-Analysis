import importlib


MODULES = [
    "terminal.research_council",
    "terminal.research_council.engine",
    "terminal.research_council.schemas",
    "terminal.research_council.mode_profiles",
    "terminal.research_council.tool_registry",
    "terminal.research_council.plan_compiler",
    "terminal.research_council.plan_executor",
    "terminal.research_council.decision_math",
    "terminal.research_council.evidence_pack_builder",
    "terminal.research_council.coder_sandbox",
    "terminal.research_council.features",
    "terminal.research_council.strategies",
    "terminal.research_council.report_review",
    "terminal.research_council.persistence",
    "terminal.research_council.llm_client",
    "terminal.research_council.states.intake",
    "terminal.research_council.states.route",
    "terminal.research_council.states.data_steward",
    "terminal.research_council.states.market_state",
    "terminal.research_council.states.specialist_pass",
    "terminal.research_council.states.branch_deliberation",
    "terminal.research_council.states.plan_build",
    "terminal.research_council.states.plan_execute",
    "terminal.research_council.states.plan_review",
    "terminal.research_council.states.critic_review",
    "terminal.research_council.states.revision",
    "terminal.research_council.states.synthesis",
    "terminal.research_council.states.render_html",
    "terminal.research_council.states.persistence",
    "terminal.research_council.agents.base",
    "terminal.research_council.agents.prompts",
    "terminal.research_council.agents.coder_quant",
    "terminal.research_council.critics.base",
    "terminal.research_council.critics.prompts",
    "terminal.research_council.critics.data_quality",
    "terminal.research_council.critics.leakage",
    "terminal.research_council.critics.overfit",
    "terminal.research_council.critics.risk",
    "terminal.research_council.critics.evidence",
    "terminal.research_council.reports.markdown_renderer",
    "terminal.research_council.reports.html_renderer",
]


def test_research_council_modules_import_without_provider_side_effects(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    for module_name in MODULES:
        importlib.import_module(module_name)


def test_research_council_package_exposes_run_council():
    package = importlib.import_module("terminal.research_council")

    assert callable(package.run_council)
