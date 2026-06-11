from __future__ import annotations

from .schema import SkillDefinition


_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        id="market_readiness",
        name="Market Readiness",
        description="Check market state, data freshness, PostgreSQL readiness, and source health.",
        triggers=("market today", "live market", "data readiness", "freshness"),
        evidence_required=("market_state", "data_readiness"),
        output_contract=("freshness", "source_health", "warnings"),
    ),
    SkillDefinition(
        id="entity_resolution",
        name="Entity Resolution",
        description="Resolve company, index, and sector names before evidence collection.",
        triggers=("company name", "symbol", "index", "sector"),
        output_contract=("canonical_symbol", "entity_type", "confidence"),
    ),
    SkillDefinition(
        id="evidence_grounding",
        name="Evidence Grounding",
        description="Require source-backed answers or an explicit insufficient-evidence result.",
        triggers=("recommend", "why", "explain", "deep dive"),
        evidence_required=("source_trail",),
        output_contract=("answer", "evidence_used", "missing_evidence"),
    ),
    SkillDefinition(
        id="fundamental_driver_diagnosis",
        name="Fundamental Driver Diagnosis",
        description="Explain why EPS, ROCE, margins, debt, or cash-flow metrics changed.",
        triggers=(
            "why is eps going down",
            "why eps fell",
            "why is roce high",
            "why did margins fall",
            "why is debt rising",
            "cash flow weak",
        ),
        entities_required=("symbol",),
        evidence_required=("financial_statements", "quarterly_results", "annual_results"),
        output_contract=(
            "short_answer",
            "metric_bridge",
            "evidence",
            "interpretation",
            "what_to_watch",
        ),
    ),
    SkillDefinition(
        id="financial_statement_analysis",
        name="Financial Statement Analysis",
        description="Analyze P&L, balance sheet, and cash-flow statements across periods.",
        triggers=("balance sheet", "cash flow", "profit and loss", "financial statement"),
        entities_required=("symbol",),
        evidence_required=("financial_statements",),
        output_contract=("summary", "period_comparison", "drivers", "risks"),
    ),
    SkillDefinition(
        id="valuation_analysis",
        name="Valuation Analysis",
        description="Build valuation ranges from multiples, peer bands, and scenarios.",
        triggers=("valuation", "fair value", "target price", "dcf", "expensive"),
        entities_required=("symbol",),
        evidence_required=("financial_statements", "market_price"),
        output_contract=("valuation_range", "assumptions", "sensitivity", "risks"),
    ),
    SkillDefinition(
        id="forensic_accounting",
        name="Forensic Accounting",
        description="Identify accounting and financial-health red flags.",
        triggers=("forensic", "red flags", "earnings quality", "fraud risk"),
        entities_required=("symbol",),
        evidence_required=("financial_statements",),
        output_contract=("risk_level", "flags", "evidence", "watch_items"),
    ),
    SkillDefinition(
        id="capital_allocation",
        name="Capital Allocation",
        description="Assess capex productivity, reinvestment, buybacks, dividends, and acquisitions.",
        triggers=("capital allocation", "capex", "buyback", "dividend", "acquisition"),
        entities_required=("symbol",),
        evidence_required=("financial_statements", "corporate_actions"),
        output_contract=("assessment", "capital_uses", "returns", "risks"),
    ),
    SkillDefinition(
        id="corporate_event_analysis",
        name="Corporate Event Analysis",
        description="Interpret results, demergers, mergers, orders, pledges, and other events.",
        triggers=("results impact", "demerger", "merger", "order win", "pledge"),
        entities_required=("symbol",),
        evidence_required=("corporate_events",),
        output_contract=("event_summary", "materiality", "impact", "watch_items"),
    ),
    SkillDefinition(
        id="portfolio_risk_review",
        name="Portfolio Risk Review",
        description="Review holdings, concentration, stops, weak positions, and add/trim decisions.",
        triggers=("portfolio", "holdings", "add", "trim", "exit"),
        evidence_required=("portfolio_holdings", "market_data"),
        output_contract=("actions", "exposure", "risk_flags", "watch_items"),
    ),
    SkillDefinition(
        id="swing_trade_playbook",
        name="Swing Trade Playbook",
        description="Rank swing candidates and produce entry, stop, target, and portfolio action plans.",
        triggers=("swing", "entry", "stop", "target", "setup"),
        evidence_required=("technical_scores", "stage", "portfolio_holdings"),
        output_contract=("candidates", "risk_plan", "portfolio_actions", "disclaimer"),
    ),
    SkillDefinition(
        id="report_qa",
        name="Report QA",
        description="Validate generated reports for required sections, freshness, and source trail.",
        triggers=("validate report", "report qa", "open report", "email report"),
        evidence_required=("report_path",),
        output_contract=("status", "findings", "warnings"),
    ),
    SkillDefinition(
        id="systematic_debugging",
        name="Systematic Debugging",
        description="Diagnose broken commands, data pipelines, reports, and terminal behavior.",
        triggers=("not showing", "broken", "failed", "error", "why is this wrong"),
        output_contract=("root_cause", "fix", "verification"),
    ),
    SkillDefinition(
        id="trading_discipline",
        name="Trading Discipline",
        description="Require timeframe, risk, invalidation, and research-only framing for trade ideas.",
        triggers=("buy", "sell", "enter", "trade", "position size"),
        evidence_required=("risk_plan",),
        output_contract=("timeframe", "entry", "stop", "invalidation", "disclaimer"),
    ),
)

_BY_ID = {skill.id: skill for skill in _SKILLS}


def list_skills() -> tuple[SkillDefinition, ...]:
    return _SKILLS


def get_skill(skill_id: str) -> SkillDefinition:
    return _BY_ID[skill_id]
