"""Council intelligence routing and objective expansion."""

from __future__ import annotations

import re
from dataclasses import replace


SECTOR_ALIASES = {
    "nifty auto": "NIFTY AUTO",
    "auto sector": "NIFTY AUTO",
    "auto": "NIFTY AUTO",
    "nifty pharma": "NIFTY PHARMA",
    "pharma sector": "NIFTY PHARMA",
    "nifty it": "NIFTY IT",
    "it sector": "NIFTY IT",
    "nifty bank": "NIFTY BANK",
    "bank sector": "NIFTY BANK",
    "nifty metal": "NIFTY METAL",
    "metal sector": "NIFTY METAL",
}


def run(state):
    return replace(
        state,
        route_decision=expand_route_decision(
            state.objective,
            state.mode,
            explicit_sector=(state.flags or {}).get("sector"),
        ),
    )


def expand_route_decision(objective: str, mode: str, *, explicit_sector: str | None = None) -> dict:
    if mode == "sector_opportunity":
        sector = str(explicit_sector).upper() if explicit_sector else _extract_sector(objective)
        return {
            "workflow": "sector_opportunity",
            "sector": sector,
            "expanded_objective": f"Find the best research candidates in {sector} for swing or positional trades.",
            "sub_questions": [
                f"Is {sector} worth allocating attention to now?",
                "Which stocks in the sector show leadership characteristics?",
                "Which shortlisted stocks are technically actionable?",
                "Which stocks have supportive fundamentals, filings, results, or catalysts?",
                "Which route is testable by Coder Quant after shortlist creation?",
                "Which candidates survive hedge-fund risk review?",
            ],
            "selected_agents": [
                "data_steward",
                "macro_regime",
                "sector_rotation",
                "technical",
                "minervini",
                "fundamental",
                "catalyst",
                "coder_quant",
                "hedge_fund_owner",
            ],
            "coder_quant_policy": "shortlist_only",
            "execution_order": [
                "sector_evidence",
                "shortlist",
                "specialist_review",
                "coder_quant_route_sweep",
                "risk_review",
                "chair_synthesis",
            ],
        }
    if mode == "strategy_build":
        return {
            "workflow": "strategy_build",
            "expanded_objective": objective,
            "sub_questions": [
                "What strategy family and rules should be tested?",
                "Does train/validation evidence support the thesis?",
                "What leakage, overfit, and risk objections remain?",
            ],
            "selected_agents": ["technical", "minervini", "fundamental", "fno_risk", "coder_quant", "hedge_fund_owner"],
            "coder_quant_policy": "primary",
        }
    return {
        "workflow": mode,
        "expanded_objective": objective,
        "sub_questions": [],
        "selected_agents": [],
        "coder_quant_policy": "mode_default",
    }


def _extract_sector(objective: str) -> str:
    text = objective.lower()
    for alias, sector in SECTOR_ALIASES.items():
        if alias in text:
            return sector
    match = re.search(r"nifty\s+([a-z]+)", text)
    if match:
        return f"NIFTY {match.group(1).upper()}"
    return "SECTOR"
