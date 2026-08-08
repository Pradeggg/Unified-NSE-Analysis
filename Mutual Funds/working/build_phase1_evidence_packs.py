from __future__ import annotations

import csv
import html
import json
import math
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.financials_cache import read_financials
from terminal.tools import get_technical_setup
from terminal.web_research import scrape_screener_in


RUN_DATE = "20260806"
NAV = 500_000.0
PHASE1_EXPOSURE_CAP = NAV * 0.40
OPEN_RISK_CAP = NAV * 0.06
POLICY = ROOT / "docs" / "fund_policies" / "2026-08-06-smallcap-super-performers-fund-policy.md"
POLICY_GATE = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_policy_gate_{RUN_DATE}.csv"
OUT_CSV = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_phase1_evidence_packs_{RUN_DATE}.csv"
OUT_JSON = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_phase1_evidence_packs_{RUN_DATE}.json"
OUT_HTML = ROOT / "Mutual Funds" / "reports" / f"agent_adda_smallcap_phase1_evidence_packs_{RUN_DATE}.html"


CLEAN_STATUS = "PHASE1_TRIGGER_MAP_GOVERNANCE_PENDING"
RETEST_STATUS = "PHASE1_RETEST_TRIGGER_MAP_GOVERNANCE_PENDING"
WATCH_STATUSES = {CLEAN_STATUS, RETEST_STATUS}


BUSINESS_CASE = {
    "objective": (
        "Build an internal, paper-only smallcap portfolio process that can identify asymmetric "
        "opportunities while proving that selection, sizing, risk control, and review discipline "
        "work before any live-capital discussion."
    ),
    "why_now": (
        "The current smallcap research stack has three useful inputs at the same time: local Agent Adda "
        "stage/technical evidence, refreshed company fundamentals, and mutual-fund holding overlap. "
        "The business case is to convert that research into a repeatable portfolio operating system."
    ),
    "edge_hypothesis": (
        "The edge is not one model. It is the combination of theme confirmation, fundamental "
        "acceleration, relative-strength momentum, liquidity discipline, and stop-risk sizing."
    ),
    "constraints": (
        "This is an internal paper/model portfolio only. It is long-only, no leverage, no derivatives, no forced "
        "deployment, and no automatic order from narrative research or LLM output."
    ),
    "success_definition": (
        "Success means a controlled process: documented evidence packs, pre-defined triggers, realistic "
        "paper execution, measurable expectancy, drawdown control, and benchmark-relative review."
    ),
}


OPERATING_APPROACH = [
    {
        "title": "1. Source The Universe",
        "detail": (
            "Start from Agent Adda smallcap screens, stage snapshots, index/sector evidence, mutual-fund "
            "overlap files, and current company fundamentals."
        ),
    },
    {
        "title": "2. Score And Gate",
        "detail": (
            "Apply the 100-point scorecard across theme, fundamentals, technicals, liquidity, governance, "
            "and valuation/reward-risk. Scores create research priority, not orders."
        ),
    },
    {
        "title": "3. Build Evidence Packs",
        "detail": (
            "For each active candidate, attach financials, ratios, shareholding, source links, technical "
            "levels, theme thesis, risks, and invalidation rules."
        ),
    },
    {
        "title": "4. Map Triggers",
        "detail": (
            "Convert eligible names into pre-defined breakout, retest, or pullback triggers with stop, "
            "2R target, no-chase rule, and paper quantity."
        ),
    },
    {
        "title": "5. Portfolio-Risk Check",
        "detail": (
            "Before a paper order, check NAV, available cash, sector cap, single-stock cap, liquidity cap, "
            "risk to stop, total open risk, and event gap risk."
        ),
    },
    {
        "title": "6. Journal And Review",
        "detail": (
            "Every paper order, skip, add, trim, and exit must create a journal entry with thesis, result, "
            "R multiple, postmortem, and policy lesson."
        ),
    },
]


GOVERNANCE_MODEL = [
    {
        "role": "Research engine",
        "responsibility": "Finds themes, screens stocks, gathers company/technical/source evidence, and drafts scorecards.",
    },
    {
        "role": "Strategy engine",
        "responsibility": "Turns approved candidates into deterministic entry, stop, sizing, exit, and backtest rules.",
    },
    {
        "role": "Portfolio manager",
        "responsibility": "Allocates paper capital, enforces caps, approves skips/orders, and manages adds/trims/exits.",
    },
    {
        "role": "Reviewer",
        "responsibility": "Challenges assumptions, reviews postmortems, and approves policy changes only with evidence.",
    },
]


ROADMAP = [
    ("Phase A", "Policy and business case", "Complete"),
    ("Phase B", "Candidate evidence packs and trigger map", "Current artifact"),
    ("Phase C", "Portfolio Lab integration with managed paper orders", "Next"),
    ("Phase D", "Backtest, liquidity stress, gap/slippage sensitivity", "Pending"),
    ("Phase E", "Daily paper operations, journal, weekly/monthly review", "Pending"),
]


OPERATING_METRICS = [
    "NAV, cash, gross exposure, and benchmark-relative return.",
    "Open positions, stock weights, sector exposure, and cash drag.",
    "Stop level, rupee risk to stop, total open risk, and gap-risk flags.",
    "Closed trade count, hit rate, average win/loss, expectancy, profit factor, and max drawdown.",
    "Rule adherence: entries skipped for no-chase, liquidity, stale data, governance, or event risk.",
]


MANUAL_ASSESSMENTS: dict[str, dict[str, Any]] = {
    "SYRMA": {
        "stance": "Best clean candidate, but valuation/governance must clear before order.",
        "fundamental_view": (
            "EMS growth is strong and fresh Q1 data is available. The main offset is valuation, "
            "promoter reduction, and working-capital stretch."
        ),
        "technical_view": (
            "Stage 2 with good relative strength and a non-extended RSI. Breakout or 20DMA retest "
            "can be mapped, but the order is not executable until volume confirms."
        ),
        "sector_view": "Industrial manufacturing/EMS remains a high-growth manufacturing theme.",
        "kill_switches": [
            "Failure below the structure stop.",
            "Official Q1 filing or transcript contradicts cached growth numbers.",
            "Receivable or working-capital deterioration accelerates.",
        ],
    },
    "AEGISVOPAK": {
        "stance": "Theme and relative strength are attractive; valuation/leverage history makes this active watch.",
        "fundamental_view": (
            "Terminal infrastructure has high operating margin, but the stock screens expensive and carries "
            "leverage/interest-capitalization concerns."
        ),
        "technical_view": (
            "Stage 2 and high relative strength, with strong traded value. It needs the mapped trigger rather "
            "than a chase after the result move."
        ),
        "sector_view": "Liquid/gas logistics and storage is infrastructure-linked with long-duration assets.",
        "kill_switches": [
            "Debt, security-cover, or interest capitalization review weakens.",
            "Q1 FY27 official result does not support current margin profile.",
            "Breakout fails back below 20DMA with volume.",
        ],
    },
    "KARURVYSYA": {
        "stance": "Best valuation/liquidity balance among the clean five, but technical leadership is lower.",
        "fundamental_view": (
            "Fresh bank result evidence and institutional ownership are positives. The analysis needs NPA, "
            "CASA, NIM, credit-cost, and capital adequacy checks before capital deployment."
        ),
        "technical_view": (
            "Stage 2 with high RSI but weaker relative strength than the leaders. Current volume ratio is thin, "
            "so the trigger needs stronger participation."
        ),
        "sector_view": "Private bank exposure is cyclical and rate/credit-cost sensitive.",
        "kill_switches": [
            "Asset-quality or credit-cost trend worsens.",
            "Relative strength fails versus Bank/Nifty benchmarks.",
            "Price closes below mapped stop or 50DMA structure.",
        ],
    },
    "VMART": {
        "stance": "Consumer recovery watch; still needs valuation and execution comfort.",
        "fundamental_view": (
            "Fresh Q1 data supports recovery, but operating margin remains modest and valuation is not cheap."
        ),
        "technical_view": (
            "Stage 2 and improving momentum, but liquidity is weaker than the other clean candidates. "
            "Retest quality matters."
        ),
        "sector_view": "Value retail is discretionary-consumption sensitive and execution-heavy.",
        "kill_switches": [
            "Same-store growth or margin recovery stalls.",
            "Management/finance leadership changes create disclosure risk.",
            "Low-volume breakout fails near the 52-week high zone.",
        ],
    },
    "FIVESTAR": {
        "stance": "NBFC watch only until asset-quality and governance checks are complete.",
        "fundamental_view": (
            "Business scale and profitability are visible, but PAT growth is modest, valuation is high, and "
            "promoter holding has reduced materially."
        ),
        "technical_view": (
            "Stage 2 but not near 52-week leadership. Trigger is dominated by retest discipline and gap-risk control."
        ),
        "sector_view": "Secured small-business lending is credit-cycle and funding-cost sensitive.",
        "kill_switches": [
            "Collection efficiency, GNPA/NNPA, or credit-cost trends deteriorate.",
            "Borrowing cost or liquidity disclosures weaken.",
            "Price loses the 20DMA/50DMA support zone before trigger.",
        ],
    },
}


THEME_DETAILS: dict[str, dict[str, str]] = {
    "SYRMA": {
        "theme_lens": "India EMS and manufacturing scale-up",
        "theme_thesis": (
            "The theme is domestic electronics manufacturing, outsourcing, and import substitution. "
            "It stays attractive only if revenue growth converts into cash and margins without excess "
            "inventory or receivable stretch."
        ),
        "stock_expression": (
            "Syrma is the EMS expression in the basket: high growth, Stage 2 price behavior, and "
            "mutual-fund overlap, but not a valuation bargain."
        ),
        "theme_confirmation": (
            "Fresh Jun 2026 result in local cache, high relative strength, Stage 2 trend, and policy "
            "theme fit through industrial manufacturing."
        ),
        "theme_risk": (
            "Expensive EMS expectations, working-capital deterioration, customer/product execution risk, "
            "and promoter holding reduction."
        ),
        "theme_invalidation": (
            "Growth quality weakens, cash conversion deteriorates, or the stock fails the mapped retest/"
            "breakout with volume."
        ),
        "priority_implication": (
            "Highest clean-candidate priority, but only after governance review and trigger confirmation."
        ),
    },
    "AEGISVOPAK": {
        "theme_lens": "Energy storage, terminals, and logistics infrastructure",
        "theme_thesis": (
            "The theme is long-duration liquid/gas storage infrastructure with operating leverage. "
            "It works when utilization, pricing, and debt-service comfort support the asset base."
        ),
        "stock_expression": (
            "Aegis Vopak represents terminal infrastructure rather than commodity-price exposure. "
            "The market is rewarding the asset theme, visible in relative strength."
        ),
        "theme_confirmation": (
            "Stage 2 trend, strong relative strength, fresh Jun 2026 result cache, and adequate traded "
            "value for a small-cap paper slot."
        ),
        "theme_risk": (
            "High P/E and P/B, leverage, interest capitalization concerns, short listed history, and "
            "asset-heavy capex execution."
        ),
        "theme_invalidation": (
            "Security-cover/debt review weakens, Q1 margins do not support the thesis, or price loses "
            "20DMA support after a failed breakout."
        ),
        "priority_implication": (
            "Good theme watch, but valuation and balance-sheet review must be stricter than for SYRMA."
        ),
    },
    "KARURVYSYA": {
        "theme_lens": "Private-bank credit cycle and regional lending franchise",
        "theme_thesis": (
            "The theme is mid-sized private bank credit growth with profitability, asset-quality, and "
            "deposit-franchise discipline."
        ),
        "stock_expression": (
            "Karur Vysya is the valuation-and-liquidity counterweight in the clean list. It is less "
            "thematic momentum and more compounding-through-credit-cycle evidence."
        ),
        "theme_confirmation": (
            "Fresh Jun 2026 result cache, strong institutional holding, Stage 2 price trend, and very "
            "high traded value."
        ),
        "theme_risk": (
            "Lower relative strength than the leaders, thin current volume ratio in the policy scan, "
            "and bank-specific NPA/NIM/CASA/credit-cost evidence still needing review."
        ),
        "theme_invalidation": (
            "Asset quality, NIM, or credit-cost commentary deteriorates, or relative strength fails "
            "against bank benchmarks."
        ),
        "priority_implication": (
            "Useful diversifier if the trigger arrives with participation, not the first momentum buy."
        ),
    },
    "VMART": {
        "theme_lens": "Value retail and discretionary consumption recovery",
        "theme_thesis": (
            "The theme is small-town/value retail recovery: revenue growth, store economics, margin "
            "normalization, and inventory discipline."
        ),
        "stock_expression": (
            "V-Mart is the consumer recovery expression. The stock has Stage 2 behavior, but the "
            "fundamental thesis depends on execution and margin recovery."
        ),
        "theme_confirmation": (
            "Fresh Jun 2026 result cache, Stage 2 trend, improving momentum score, and sampled fund "
            "ownership overlap."
        ),
        "theme_risk": (
            "Modest operating margin, not-cheap valuation, weaker liquidity versus the top candidates, "
            "and execution/management-transition risk."
        ),
        "theme_invalidation": (
            "Same-store growth or margin recovery stalls, inventory pressure rises, or breakout near "
            "the 52-week zone fails on weak volume."
        ),
        "priority_implication": (
            "Keep as active watch; require a clean retest or high-quality breakout before slotting."
        ),
    },
    "FIVESTAR": {
        "theme_lens": "Secured MSME and small-business NBFC lending",
        "theme_thesis": (
            "The theme is formalized secured lending to small business customers. It works when loan "
            "growth, collections, credit cost, and funding access remain controlled."
        ),
        "stock_expression": (
            "Five Star gives NBFC exposure with visible profitability, but the score is constrained by "
            "valuation, modest growth, and shareholding/governance questions."
        ),
        "theme_confirmation": (
            "Fresh Jun 2026 result cache, Stage 2 trend, acceptable liquidity, and healthy operating "
            "profitability in cached financials."
        ),
        "theme_risk": (
            "NBFC asset quality, borrowing cost, high valuation, low promoter holding, and promoter "
            "holding decline."
        ),
        "theme_invalidation": (
            "GNPA/NNPA, collection efficiency, or credit-cost trends weaken, or price fails the 20DMA/"
            "50DMA support zone."
        ),
        "priority_implication": (
            "Watch-only until asset-quality and governance review is complete; do not lead Phase 1."
        ),
    },
    "SONACOMS": {
        "theme_lens": "EV and premium auto-component content",
        "theme_thesis": (
            "The theme is rising EV and drivetrain content per vehicle. It needs durable order visibility "
            "and margin protection."
        ),
        "stock_expression": "Sona BLW is the EV/auto-component quality proxy, but the policy scan flags no-chase behavior.",
        "theme_confirmation": "Fresh result cache, Stage 2 trend, and auto-component policy theme fit.",
        "theme_risk": "Extended setup, valuation risk, export/customer-cycle sensitivity, and EV demand volatility.",
        "theme_invalidation": "Retest fails or management commentary weakens on order conversion/margins.",
        "priority_implication": "Retest-only; no fresh allocation at current extension.",
    },
    "NETWEB": {
        "theme_lens": "AI, HPC, and data-center infrastructure",
        "theme_thesis": "The theme is domestic compute infrastructure, AI servers, and high-performance computing demand.",
        "stock_expression": "Netweb is a direct digital-infrastructure momentum proxy.",
        "theme_confirmation": "Fresh result cache, Stage 2 trend, and very high traded value.",
        "theme_risk": "Valuation, order concentration, capacity execution, and extended price behavior.",
        "theme_invalidation": "Order pipeline or margin commentary disappoints, or the retest fails with volume.",
        "priority_implication": "Attractive theme, but retest-only under no-chase discipline.",
    },
    "WELCORP": {
        "theme_lens": "Industrial pipes and energy infrastructure capex",
        "theme_thesis": "The theme is energy, water, and infrastructure pipe demand with operating leverage.",
        "stock_expression": "Welspun Corp gives cyclical industrial capex exposure.",
        "theme_confirmation": "Fresh result cache, high relative strength, Stage 2 trend, and strong liquidity.",
        "theme_risk": "Cyclical order timing, commodity/input-cost swings, and extended RSI.",
        "theme_invalidation": "Order book/margin read-through weakens or RSI extension resolves through price damage.",
        "priority_implication": "Retest-only because the technical gate is extended.",
    },
    "RAINBOW": {
        "theme_lens": "Specialty healthcare services and hospital capacity",
        "theme_thesis": "The theme is pediatric and maternity specialty healthcare with capacity-led growth.",
        "stock_expression": "Rainbow is the healthcare-services quality and expansion proxy.",
        "theme_confirmation": "Fresh result cache, Stage 2 trend, operating-margin evidence, and sampled fund overlap.",
        "theme_risk": "Capex ramp-up, occupancy, doctor availability, and valuation risk.",
        "theme_invalidation": "Occupancy/margin trend weakens or retest fails after extension.",
        "priority_implication": "Retest-only; useful defensive-growth watch if price resets.",
    },
    "WEWORK": {
        "theme_lens": "Flexible workspace and managed office demand",
        "theme_thesis": "The theme is enterprise adoption of flexible workspaces and managed office capacity.",
        "stock_expression": "WeWork India represents office-services growth rather than pure real-estate ownership.",
        "theme_confirmation": "Fresh result cache, Stage 2 trend, healthy operating-margin evidence, and adequate liquidity.",
        "theme_risk": "Lease liabilities, occupancy execution, cyclicality in office demand, and short market history.",
        "theme_invalidation": "Occupancy, margin, or cash-flow evidence weakens, or retest fails.",
        "priority_implication": "Retest-only; needs more listing-history and governance comfort.",
    },
}


OFFICIAL_SOURCES: dict[str, list[dict[str, str]]] = {
    "SYRMA": [
        {"label": "Company IR: Q1 FY2027 results and earnings materials", "url": "https://www.syrmasgs.com/investor-relations/"},
    ],
    "AEGISVOPAK": [
        {"label": "Company IR: investor presentations and exchange communications", "url": "https://www.aegisvopak.com/investors"},
    ],
    "KARURVYSYA": [
        {"label": "Company financial report: quarter ended June 30, 2026", "url": "https://www.kvb.bank.in/about-us/financial-performance/financial-reports-recent-quarter/"},
    ],
    "VMART": [
        {"label": "Company IR: earnings-call invitations and presentations", "url": "https://www.vmart.co.in/investor-call-invitation-investor-presentation/"},
        {"label": "Company IR sections: results, transcripts, governance, annual reports", "url": "https://www.vmart.co.in/press-and-releases/"},
    ],
    "FIVESTAR": [
        {"label": "Company site: financials, credit rating, governance sections", "url": "https://fivestargroup.in/"},
        {"label": "Company governance page", "url": "https://fivestargroup.in/corporate-governance/"},
    ],
}


CSV_FIELDS = [
    "rank",
    "bucket",
    "symbol",
    "company",
    "sector",
    "policy_score_100",
    "policy_rating",
    "phase1_status",
    "stance",
    "current_price",
    "current_stage",
    "current_rsi",
    "current_relative_strength",
    "relative_strength_score_10",
    "momentum_score_10",
    "setup_quality_score_10",
    "technical_25",
    "fundamental_25",
    "liquidity_tradeability_15",
    "governance_management_10",
    "valuation_reward_risk_10",
    "entry_trigger",
    "initial_stop_price",
    "target_2r_price",
    "paper_quantity_by_policy",
    "paper_position_value",
    "paper_risk_to_stop",
    "latest_quarter",
    "latest_revenue_cr",
    "latest_pat_cr",
    "latest_opm_pct",
    "revenue_yoy_pct",
    "pat_yoy_pct",
    "annual_revenue_cr",
    "annual_pat_cr",
    "market_cap",
    "stock_pe",
    "price_to_book",
    "roe",
    "roce",
    "promoters",
    "fiis",
    "diis",
    "public",
    "key_strengths",
    "key_risks",
    "evidence_blockers",
    "next_action",
    "source_domains",
    "theme_lens",
    "theme_thesis",
    "stock_expression",
    "theme_confirmation",
    "theme_risk",
    "theme_invalidation",
    "priority_implication",
]


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na"}:
        return None
    text = (
        text.replace(",", "")
        .replace("%", "")
        .replace("+", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .replace("INR", "")
        .replace("Cr", "")
        .replace("cr", "")
        .replace("x", "")
        .replace("₹", "")
        .strip()
    )
    try:
        return float(text)
    except ValueError:
        return None


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def normalize_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def sort_period_desc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows or [], key=lambda r: normalize_date(r.get("period_end")), reverse=True)


def find_same_quarter_prior_year(rows: list[dict[str, Any]], latest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not latest:
        return None
    period_end = latest.get("period_end")
    if not hasattr(period_end, "year"):
        return None
    target_year = period_end.year - 1
    target_month = period_end.month
    for row in rows:
        other = row.get("period_end")
        if hasattr(other, "year") and other.year == target_year and other.month == target_month:
            return row
    return None


def pct_change(new: Any, old: Any) -> float | None:
    n = fnum(new)
    o = fnum(old)
    if n is None or o in (None, 0):
        return None
    return (n / o - 1) * 100


def fmt_num(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"{number:,.{digits}f}"


def fmt_pct(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"{number:,.{digits}f}%"


def fmt_money(value: Any) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    return f"Rs. {number:,.0f}"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def read_policy_rows() -> list[dict[str, Any]]:
    with POLICY_GATE.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    selected = [r for r in rows if r.get("phase1_status") in WATCH_STATUSES]
    return sorted(
        selected,
        key=lambda r: (
            r.get("phase1_status") != CLEAN_STATUS,
            -(fnum(r.get("policy_score_100")) or 0),
        ),
    )


def safe_call(label: str, symbol: str, fn) -> dict[str, Any]:
    try:
        out = fn(symbol) or {}
        if isinstance(out, dict):
            return out
        return {"error": f"{label} returned {type(out).__name__}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def ratio_value(ratios: dict[str, Any], *names: str) -> str:
    for name in names:
        value = ratios.get(name)
        if clean_text(value):
            return clean_text(value)
    return ""


def latest_financial_summary(symbol: str) -> dict[str, Any]:
    fin = read_financials(symbol)
    quarters = sort_period_desc(fin.get("quarterly") or [])
    annual = sort_period_desc(fin.get("annual") or [])
    balance = sort_period_desc(fin.get("balance_sheet") or [])
    cash_flow = sort_period_desc(fin.get("cash_flow") or [])

    latest_q = quarters[0] if quarters else {}
    prev_q = quarters[1] if len(quarters) > 1 else {}
    yoy_q = find_same_quarter_prior_year(quarters, latest_q)
    latest_a = annual[0] if annual else {}
    prev_a = annual[1] if len(annual) > 1 else {}
    latest_bs = balance[0] if balance else {}
    latest_cf = cash_flow[0] if cash_flow else {}

    revenue_yoy = pct_change(latest_q.get("revenue"), (yoy_q or {}).get("revenue"))
    pat_yoy = pct_change(latest_q.get("pat"), (yoy_q or {}).get("pat"))
    eps_yoy = pct_change(latest_q.get("eps"), (yoy_q or {}).get("eps"))
    revenue_qoq = pct_change(latest_q.get("revenue"), prev_q.get("revenue"))
    pat_qoq = pct_change(latest_q.get("pat"), prev_q.get("pat"))
    annual_revenue_yoy = pct_change(latest_a.get("revenue"), prev_a.get("revenue"))
    annual_pat_yoy = pct_change(latest_a.get("pat"), prev_a.get("pat"))

    return {
        "latest_quarter": latest_q,
        "previous_quarter": prev_q,
        "year_ago_quarter": yoy_q or {},
        "latest_annual": latest_a,
        "previous_annual": prev_a,
        "latest_balance_sheet": latest_bs,
        "latest_cash_flow": latest_cf,
        "revenue_yoy_pct": revenue_yoy,
        "pat_yoy_pct": pat_yoy,
        "eps_yoy_pct": eps_yoy,
        "revenue_qoq_pct": revenue_qoq,
        "pat_qoq_pct": pat_qoq,
        "annual_revenue_yoy_pct": annual_revenue_yoy,
        "annual_pat_yoy_pct": annual_pat_yoy,
        "financial_source": latest_q.get("source") or latest_a.get("source") or "",
        "financial_source_url": latest_q.get("source_url") or latest_a.get("source_url") or "",
        "financial_fetched_at": latest_q.get("fetched_at") or latest_a.get("fetched_at") or "",
    }


def source_items(symbol: str, screener: dict[str, Any], financials: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in OFFICIAL_SOURCES.get(symbol, []):
        items.append(dict(item))
    for label, key in [
        ("Screener structured fundamentals", "source_url"),
        ("NSE quote page", "nse_url"),
        ("BSE company page", "bse_url"),
    ]:
        url = clean_text(screener.get(key))
        if url:
            items.append({"label": label, "url": url})
    url = clean_text(financials.get("financial_source_url"))
    if url:
        items.append({"label": "Local financial cache source URL", "url": url})
    for ann in (screener.get("announcements") or [])[:3]:
        if ann.get("url"):
            items.append({"label": f"BSE announcement: {ann.get('title', '')[:90]}", "url": ann["url"]})
    for concall in (screener.get("concalls") or [])[:2]:
        for key, label in [
            ("transcript_url", "Concall transcript"),
            ("ppt_url", "Concall presentation"),
            ("recording_url", "Concall recording"),
        ]:
            url = clean_text(concall.get(key))
            if url:
                period = clean_text(concall.get("period"))
                items.append({"label": f"{label}: {period}", "url": url})
                break

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(item)
    return deduped[:10]


def build_pack(row: dict[str, Any], rank: int) -> dict[str, Any]:
    symbol = row["symbol"].strip().upper()
    financials = latest_financial_summary(symbol)
    screener = safe_call("scrape_screener_in", symbol, scrape_screener_in)
    technical = safe_call("get_technical_setup", symbol, get_technical_setup)
    ratios = screener.get("ratios") or {}
    shareholding = screener.get("shareholding") or {}
    assessment = MANUAL_ASSESSMENTS.get(symbol, {})
    theme = THEME_DETAILS.get(symbol, {})
    latest_q = financials.get("latest_quarter") or {}
    latest_a = financials.get("latest_annual") or {}
    sources = source_items(symbol, screener, financials)
    source_domains = sorted({domain(item["url"]) for item in sources if domain(item["url"])})
    bucket = "Clean trigger map" if row.get("phase1_status") == CLEAN_STATUS else "Retest trigger map"

    pack = {
        "rank": rank,
        "bucket": bucket,
        "symbol": symbol,
        "company": row.get("company", ""),
        "sector": row.get("sector", ""),
        "policy": row,
        "assessment": assessment,
        "theme": theme,
        "financials": financials,
        "screener": {
            "source_url": screener.get("source_url", ""),
            "ratios": ratios,
            "pros": screener.get("pros") or [],
            "cons": screener.get("cons") or [],
            "shareholding": shareholding,
            "announcements": screener.get("announcements") or [],
            "annual_reports": screener.get("annual_reports") or [],
            "concalls": screener.get("concalls") or [],
            "error": screener.get("error", ""),
        },
        "technical": technical,
        "sources": sources,
        "source_domains": source_domains,
        "csv": {
            "rank": rank,
            "bucket": bucket,
            "symbol": symbol,
            "company": row.get("company", ""),
            "sector": row.get("sector", ""),
            "policy_score_100": row.get("policy_score_100", ""),
            "policy_rating": row.get("policy_rating", ""),
            "phase1_status": row.get("phase1_status", ""),
            "stance": assessment.get("stance", "Trigger-map candidate; execution gates pending."),
            "current_price": row.get("current_price", ""),
            "current_stage": row.get("current_stage", ""),
            "current_rsi": row.get("current_rsi", ""),
            "current_relative_strength": row.get("current_relative_strength", ""),
            "relative_strength_score_10": row.get("relative_strength_score_10", ""),
            "momentum_score_10": row.get("momentum_score_10", ""),
            "setup_quality_score_10": row.get("setup_quality_score_10", ""),
            "technical_25": row.get("technical_25", ""),
            "fundamental_25": row.get("fundamental_25", ""),
            "liquidity_tradeability_15": row.get("liquidity_tradeability_15", ""),
            "governance_management_10": row.get("governance_management_10", ""),
            "valuation_reward_risk_10": row.get("valuation_reward_risk_10", ""),
            "entry_trigger": row.get("entry_trigger", ""),
            "initial_stop_price": row.get("initial_stop_price", ""),
            "target_2r_price": row.get("target_2r_price", ""),
            "paper_quantity_by_policy": row.get("paper_quantity_by_policy", ""),
            "paper_position_value": row.get("paper_position_value", ""),
            "paper_risk_to_stop": row.get("paper_risk_to_stop", ""),
            "latest_quarter": latest_q.get("period_label", ""),
            "latest_revenue_cr": latest_q.get("revenue", ""),
            "latest_pat_cr": latest_q.get("pat", ""),
            "latest_opm_pct": latest_q.get("opm_pct", ""),
            "revenue_yoy_pct": financials.get("revenue_yoy_pct"),
            "pat_yoy_pct": financials.get("pat_yoy_pct"),
            "annual_revenue_cr": latest_a.get("revenue", ""),
            "annual_pat_cr": latest_a.get("pat", ""),
            "market_cap": ratio_value(ratios, "Market Cap"),
            "stock_pe": ratio_value(ratios, "Stock P/E"),
            "price_to_book": ratio_value(ratios, "Price to Book", "Book Value"),
            "roe": ratio_value(ratios, "ROE"),
            "roce": ratio_value(ratios, "ROCE"),
            "promoters": shareholding.get("Promoters", ""),
            "fiis": shareholding.get("FIIs", ""),
            "diis": shareholding.get("DIIs", ""),
            "public": shareholding.get("Public", ""),
            "key_strengths": clean_text(row.get("key_strengths")),
            "key_risks": clean_text(row.get("key_risks")),
            "evidence_blockers": clean_text(row.get("evidence_blockers")),
            "next_action": clean_text(row.get("next_action")),
            "source_domains": "; ".join(source_domains),
            "theme_lens": theme.get("theme_lens", ""),
            "theme_thesis": theme.get("theme_thesis", ""),
            "stock_expression": theme.get("stock_expression", ""),
            "theme_confirmation": theme.get("theme_confirmation", ""),
            "theme_risk": theme.get("theme_risk", ""),
            "theme_invalidation": theme.get("theme_invalidation", ""),
            "priority_implication": theme.get("priority_implication", ""),
        },
    }
    return pack


def write_csv(packs: list[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for pack in packs:
            row = dict(pack["csv"])
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})


def write_json(packs: list[dict[str, Any]]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_date": RUN_DATE,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "policy": str(POLICY.relative_to(ROOT)),
        "policy_gate_input": str(POLICY_GATE.relative_to(ROOT)),
        "nav": NAV,
        "phase1_exposure_cap": PHASE1_EXPOSURE_CAP,
        "open_risk_cap": OPEN_RISK_CAP,
        "business_case": BUSINESS_CASE,
        "operating_approach": OPERATING_APPROACH,
        "governance_model": GOVERNANCE_MODEL,
        "roadmap": ROADMAP,
        "operating_metrics": OPERATING_METRICS,
        "packs": packs,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")


def score_bar(label: str, value: Any, max_value: float) -> str:
    val = fnum(value) or 0.0
    pct = max(0.0, min(100.0, val / max_value * 100 if max_value else 0.0))
    return f"""
      <div class="scorebar">
        <div class="scorebar-head"><span>{esc(label)}</span><b>{fmt_num(val, 1)} / {fmt_num(max_value, 0)}</b></div>
        <div class="bar"><span style="width:{pct:.1f}%"></span></div>
      </div>
    """


def metric(label: str, value: Any, detail: str = "") -> str:
    return f"""
      <div class="metric">
        <span>{esc(label)}</span>
        <b>{esc(value)}</b>
        <small>{esc(detail)}</small>
      </div>
    """


def link_list(items: list[dict[str, str]]) -> str:
    if not items:
        return "<p class=\"muted\">No source links captured.</p>"
    links = []
    for item in items:
        label = item.get("label", "Source")
        url = item.get("url", "")
        links.append(f"<li><a href=\"{esc(url)}\">{esc(label)}</a><span>{esc(domain(url))}</span></li>")
    return "<ul class=\"source-list\">" + "\n".join(links) + "</ul>"


def list_items(items: list[Any], empty: str) -> str:
    texts = [clean_text(item) for item in items if clean_text(item)]
    if not texts:
        return f"<li>{esc(empty)}</li>"
    return "\n".join(f"<li>{esc(item)}</li>" for item in texts[:5])


def financial_table(pack: dict[str, Any]) -> str:
    financials = pack["financials"]
    latest_q = financials.get("latest_quarter") or {}
    prev_q = financials.get("previous_quarter") or {}
    yoy_q = financials.get("year_ago_quarter") or {}
    latest_a = financials.get("latest_annual") or {}
    latest_bs = financials.get("latest_balance_sheet") or {}
    latest_cf = financials.get("latest_cash_flow") or {}
    rows = [
        ("Latest quarter", latest_q.get("period_label", "NA"), fmt_num(latest_q.get("revenue")), fmt_num(latest_q.get("pat")), fmt_pct(latest_q.get("opm_pct")), fmt_pct(financials.get("revenue_yoy_pct")), fmt_pct(financials.get("pat_yoy_pct"))),
        ("Previous quarter", prev_q.get("period_label", "NA"), fmt_num(prev_q.get("revenue")), fmt_num(prev_q.get("pat")), fmt_pct(prev_q.get("opm_pct")), fmt_pct(financials.get("revenue_qoq_pct")), fmt_pct(financials.get("pat_qoq_pct"))),
        ("Year-ago quarter", yoy_q.get("period_label", "NA"), fmt_num(yoy_q.get("revenue")), fmt_num(yoy_q.get("pat")), fmt_pct(yoy_q.get("opm_pct")), "", ""),
        ("Latest annual", latest_a.get("period_label", "NA"), fmt_num(latest_a.get("revenue")), fmt_num(latest_a.get("pat")), fmt_pct(latest_a.get("opm_pct")), fmt_pct(financials.get("annual_revenue_yoy_pct")), fmt_pct(financials.get("annual_pat_yoy_pct"))),
    ]
    body = "\n".join(
        f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td><td>{esc(d)}</td><td>{esc(e)}</td><td>{esc(f)}</td><td>{esc(g)}</td></tr>"
        for a, b, c, d, e, f, g in rows
    )
    balance_detail = []
    if latest_bs:
        balance_detail.append(f"Borrowings {fmt_num(latest_bs.get('borrowings'))}")
        balance_detail.append(f"Net debt {fmt_num(latest_bs.get('net_debt'))}")
        balance_detail.append(f"Assets {fmt_num(latest_bs.get('total_assets'))}")
    if latest_cf:
        balance_detail.append(f"Operating CF {fmt_num(latest_cf.get('operating_cf'))}")
        balance_detail.append(f"Net CF {fmt_num(latest_cf.get('net_cf'))}")
    foot = "; ".join(balance_detail) if balance_detail else "Balance sheet/cash-flow cache is not complete for this symbol."
    return f"""
      <div class="mini-table">
        <table>
          <thead><tr><th>Period</th><th>Label</th><th>Revenue Cr</th><th>PAT Cr</th><th>OPM</th><th>Revenue Chg</th><th>PAT Chg</th></tr></thead>
          <tbody>{body}</tbody>
        </table>
      </div>
      <p class="muted">{esc(foot)}</p>
    """


def ratio_grid(pack: dict[str, Any]) -> str:
    ratios = pack["screener"].get("ratios") or {}
    share = pack["screener"].get("shareholding") or {}
    cells = [
        ("Market cap", ratio_value(ratios, "Market Cap")),
        ("P/E", ratio_value(ratios, "Stock P/E")),
        ("P/B or book", ratio_value(ratios, "Price to Book", "Book Value")),
        ("ROE", ratio_value(ratios, "ROE")),
        ("ROCE", ratio_value(ratios, "ROCE")),
        ("Dividend yield", ratio_value(ratios, "Dividend Yield")),
        ("Promoters", share.get("Promoters", "")),
        ("FII/DII", f"{share.get('FIIs', '')} / {share.get('DIIs', '')}".strip(" /")),
    ]
    return "<div class=\"ratio-grid\">" + "\n".join(
        f"<div><span>{esc(label)}</span><b>{esc(value or 'NA')}</b></div>" for label, value in cells
    ) + "</div>"


def candidate_card(pack: dict[str, Any]) -> str:
    row = pack["policy"]
    assessment = pack["assessment"]
    theme = pack["theme"]
    screener = pack["screener"]
    tech = pack["technical"]
    clean = pack["bucket"] == "Clean trigger map"
    source_domains = ", ".join(pack["source_domains"]) or "local cache"
    kill_switches = assessment.get("kill_switches") or []
    return f"""
    <article id="{esc(pack['symbol'])}" class="candidate {'clean' if clean else 'retest'}">
      <div class="candidate-head">
        <div>
          <span class="eyebrow">{esc(pack['bucket'])} / Rank {esc(pack['rank'])}</span>
          <h3>{esc(pack['symbol'])} <small>{esc(pack['company'])}</small></h3>
          <p>{esc(assessment.get('stance', 'Trigger-map candidate; execution gates pending.'))}</p>
        </div>
        <div class="score-chip">{fmt_num(row.get('policy_score_100'))}<span>/100</span></div>
      </div>

      <div class="metrics">
        {metric("Policy rating", row.get("policy_rating", "NA"), row.get("phase1_status", ""))}
        {metric("Price / stage", fmt_num(row.get("current_price")), f"{row.get('current_stage', '')} / RSI {fmt_num(row.get('current_rsi'))}")}
        {metric("RS", fmt_num(row.get("current_relative_strength")), f"RS score {fmt_num(row.get('relative_strength_score_10'))}/10")}
        {metric("Paper slot", fmt_money(row.get("paper_position_value")), f"{row.get('paper_quantity_by_policy', '')} sh / risk {fmt_money(row.get('paper_risk_to_stop'))}")}
      </div>

      <section class="theme-box">
        <h4>Theme Detail</h4>
        <div class="theme-grid">
          <div>
            <span>Lens</span>
            <b>{esc(theme.get("theme_lens", row.get("policy_theme_bucket", "Theme not mapped")))}</b>
          </div>
          <div>
            <span>Policy Status</span>
            <b>{esc(row.get("policy_theme_bucket", ""))}</b>
            <small>{esc(row.get("theme_status", ""))} / theme score {fmt_num(row.get("theme_fit_15"))}/15</small>
          </div>
          <div>
            <span>Stock Expression</span>
            <b>{esc(theme.get("stock_expression", "Theme expression needs manual review."))}</b>
          </div>
          <div>
            <span>Priority Impact</span>
            <b>{esc(theme.get("priority_implication", "Theme impact not assigned."))}</b>
          </div>
        </div>
        <p>{esc(theme.get("theme_thesis", ""))}</p>
        <div class="columns compact">
          <section>
            <h4>Theme Confirmation</h4>
            <p>{esc(theme.get("theme_confirmation", "Confirmation evidence pending."))}</p>
          </section>
          <section>
            <h4>Theme Risk / Invalidation</h4>
            <p>{esc(theme.get("theme_risk", "Risk evidence pending."))}</p>
            <p class="muted">{esc(theme.get("theme_invalidation", ""))}</p>
          </section>
        </div>
      </section>

      <div class="columns">
        <section>
          <h4>Score Components</h4>
          {score_bar("Theme", row.get("theme_fit_15"), 15)}
          {score_bar("Fundamental", row.get("fundamental_25"), 25)}
          {score_bar("Technical", row.get("technical_25"), 25)}
          {score_bar("Liquidity", row.get("liquidity_tradeability_15"), 15)}
          {score_bar("Governance", row.get("governance_management_10"), 10)}
          {score_bar("Valuation/RR", row.get("valuation_reward_risk_10"), 10)}
        </section>
        <section>
          <h4>Trigger Plan</h4>
          <p class="strong">{esc(row.get("entry_trigger", ""))}</p>
          <div class="trade-grid">
            <div><span>Stop</span><b>{fmt_num(row.get("initial_stop_price"))}</b></div>
            <div><span>2R target</span><b>{fmt_num(row.get("target_2r_price"))}</b></div>
            <div><span>Turnover</span><b>{fmt_num(row.get("avg_turnover_20d_cr"))} cr</b></div>
            <div><span>Volume ratio</span><b>{fmt_num(row.get("vol_ratio"))}</b></div>
          </div>
          <p class="warning">Not an order. Governance/filing review and live trigger confirmation remain mandatory.</p>
        </section>
      </div>

      <div class="columns">
        <section>
          <h4>Fundamental View</h4>
          <p>{esc(assessment.get("fundamental_view", ""))}</p>
          {financial_table(pack)}
          {ratio_grid(pack)}
        </section>
        <section>
          <h4>Technical And Sector View</h4>
          <p>{esc(assessment.get("technical_view", ""))}</p>
          <p>{esc(assessment.get("sector_view", ""))}</p>
          <div class="trade-grid">
            <div><span>Tech price</span><b>{fmt_num(tech.get("price"))}</b></div>
            <div><span>20DMA / 50DMA</span><b>{fmt_num(tech.get("sma20"))} / {fmt_num(tech.get("sma50"))}</b></div>
            <div><span>ADX</span><b>{fmt_num(tech.get("adx"))}</b></div>
            <div><span>52W gap</span><b>{fmt_pct(tech.get("pct_from_52h"))}</b></div>
          </div>
        </section>
      </div>

      <div class="columns">
        <section>
          <h4>Strengths</h4>
          <ul>
            {list_items([row.get("key_strengths")] + (screener.get("pros") or []), "No explicit strength list captured.")}
          </ul>
        </section>
        <section>
          <h4>Risks And Kill Switches</h4>
          <ul>
            {list_items([row.get("key_risks"), row.get("evidence_blockers")] + (screener.get("cons") or []) + kill_switches, "No explicit risk list captured.")}
          </ul>
        </section>
      </div>

      <section>
        <h4>Source Trail</h4>
        <p class="muted">Domains captured: {esc(source_domains)}</p>
        {link_list(pack["sources"])}
      </section>
    </article>
    """


def retest_table(packs: list[dict[str, Any]]) -> str:
    rows = []
    for pack in packs:
        row = pack["policy"]
        rows.append(
            f"""
            <tr>
              <td><a href="#{esc(pack['symbol'])}"><b>{esc(pack['symbol'])}</b></a><span>{esc(pack['company'])}</span></td>
              <td>{fmt_num(row.get('policy_score_100'))}</td>
              <td>{esc(row.get('no_chase_gate', ''))}</td>
              <td>{fmt_num(row.get('current_rsi'))}</td>
              <td>{fmt_num(row.get('current_relative_strength'))}</td>
              <td>{esc(row.get('entry_trigger', ''))}</td>
              <td>{fmt_money(row.get('paper_position_value'))}<span>risk {fmt_money(row.get('paper_risk_to_stop'))}</span></td>
              <td>{esc(row.get('evidence_blockers', ''))}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def theme_board(packs: list[dict[str, Any]]) -> str:
    rows = []
    for pack in packs:
        row = pack["policy"]
        theme = pack["theme"]
        rows.append(
            f"""
            <tr>
              <td><a href="#{esc(pack['symbol'])}"><b>{esc(pack['symbol'])}</b></a><span>{esc(pack['bucket'])}</span></td>
              <td>{esc(theme.get('theme_lens', row.get('policy_theme_bucket', '')))}</td>
              <td>{esc(theme.get('stock_expression', 'Theme expression pending.'))}</td>
              <td>{esc(theme.get('theme_confirmation', 'Confirmation pending.'))}</td>
              <td>{esc(theme.get('theme_risk', 'Risk pending.'))}</td>
              <td>{esc(theme.get('priority_implication', 'Priority impact pending.'))}</td>
              <td>{fmt_num(row.get('theme_fit_15'))}<span>{esc(row.get('theme_status', ''))}</span></td>
            </tr>
            """
        )
    return "\n".join(rows)


def business_case_section(clean_count: int, retest_count: int, clean_value: float, clean_risk: float) -> str:
    case_items = [
        ("Objective", BUSINESS_CASE["objective"]),
        ("Why Now", BUSINESS_CASE["why_now"]),
        ("Edge Hypothesis", BUSINESS_CASE["edge_hypothesis"]),
        ("Constraints", BUSINESS_CASE["constraints"]),
        ("Success Definition", BUSINESS_CASE["success_definition"]),
    ]
    case_html = "\n".join(
        f"""
        <section class="case-card">
          <h3>{esc(title)}</h3>
          <p>{esc(detail)}</p>
        </section>
        """
        for title, detail in case_items
    )
    approach_html = "\n".join(
        f"""
        <section class="case-card step-card">
          <h3>{esc(item['title'])}</h3>
          <p>{esc(item['detail'])}</p>
        </section>
        """
        for item in OPERATING_APPROACH
    )
    governance_html = "\n".join(
        f"""
        <tr>
          <td><b>{esc(item['role'])}</b></td>
          <td>{esc(item['responsibility'])}</td>
        </tr>
        """
        for item in GOVERNANCE_MODEL
    )
    roadmap_html = "\n".join(
        f"""
        <tr>
          <td><b>{esc(phase)}</b></td>
          <td>{esc(name)}</td>
          <td>{esc(status)}</td>
        </tr>
        """
        for phase, name, status in ROADMAP
    )
    metrics_html = "\n".join(f"<li>{esc(item)}</li>" for item in OPERATING_METRICS)
    return f"""
    <section class="business-case">
      <h2>Business Case And Operating Approach</h2>
      <p class="lead">This section explains how the report becomes a portfolio process. The current artifact is not a buy list; it is the bridge from research to controlled paper-portfolio operation.</p>

      <div class="case-grid">{case_html}</div>

      <h2>Current Strategy Read</h2>
      <div class="case-grid strategy-read">
        {metric("Deployment phase", "Phase 1 pilot", "evidence packs and trigger map")}
        {metric("Eligible clean names", clean_count, "governance and live trigger still pending")}
        {metric("Retest reserve", retest_count, "no-chase watchlist")}
        {metric("Modelled clean exposure", fmt_money(clean_value), f"Phase 1 cap {fmt_money(PHASE1_EXPOSURE_CAP)}")}
        {metric("Modelled clean risk", fmt_money(clean_risk), f"open-risk cap {fmt_money(OPEN_RISK_CAP)}")}
        {metric("Order status", "None", "no automatic paper buy")}
      </div>

      <h2>Approach</h2>
      <div class="case-grid steps">{approach_html}</div>

      <div class="columns">
        <section>
          <h2>Governance Model</h2>
          <div class="table-wrap compact-table">
            <table>
              <thead><tr><th>Role</th><th>Responsibility</th></tr></thead>
              <tbody>{governance_html}</tbody>
            </table>
          </div>
        </section>
        <section>
          <h2>Implementation Roadmap</h2>
          <div class="table-wrap compact-table">
            <table>
              <thead><tr><th>Phase</th><th>Deliverable</th><th>Status</th></tr></thead>
              <tbody>{roadmap_html}</tbody>
            </table>
          </div>
        </section>
      </div>

      <h2>Operating Metrics</h2>
      <ul class="metrics-list">{metrics_html}</ul>
    </section>
    """


def write_html(packs: list[dict[str, Any]]) -> None:
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    clean = [p for p in packs if p["bucket"] == "Clean trigger map"]
    retest = [p for p in packs if p["bucket"] == "Retest trigger map"]
    clean_value = sum(fnum(p["policy"].get("paper_position_value")) or 0 for p in clean)
    clean_risk = sum(fnum(p["policy"].get("paper_risk_to_stop")) or 0 for p in clean)
    total_value = sum(fnum(p["policy"].get("paper_position_value")) or 0 for p in packs)
    total_risk = sum(fnum(p["policy"].get("paper_risk_to_stop")) or 0 for p in packs)
    best = clean[0] if clean else packs[0]

    clean_cards = "\n".join(candidate_card(pack) for pack in clean)
    retest_cards = "\n".join(candidate_card(pack) for pack in retest)
    nav_links = "\n".join(f"<a href=\"#{esc(p['symbol'])}\">{esc(p['symbol'])}</a>" for p in packs)
    theme_rows = theme_board(packs)
    business_case = business_case_section(len(clean), len(retest), clean_value, clean_risk)
    retest_rows = retest_table(retest)

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Adda Smallcap Portfolio - Phase 1 Evidence Packs</title>
  <style>
    :root {{
      --ink:#17222b;
      --muted:#63717c;
      --line:#dbe3e8;
      --paper:#ffffff;
      --soft:#f4f7f8;
      --soft2:#eef5f1;
      --green:#0e6b52;
      --blue:#1f5d8f;
      --amber:#9a6a00;
      --red:#9a332b;
    }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{
      margin:0;
      color:var(--ink);
      background:#fbfcfd;
      font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
    }}
    header, main, footer {{ padding:24px 32px; }}
    header {{
      background:var(--paper);
      border-bottom:1px solid var(--line);
      position:sticky;
      top:0;
      z-index:3;
    }}
    h1 {{ margin:0 0 6px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:20px; letter-spacing:0; }}
    h3 {{ margin:0; font-size:21px; letter-spacing:0; }}
    h3 small {{ display:block; color:var(--muted); font-weight:500; font-size:13px; }}
    h4 {{ margin:0 0 10px; font-size:14px; text-transform:uppercase; letter-spacing:.04em; color:#3e505c; }}
    p {{ margin:0 0 10px; }}
    a {{ color:var(--blue); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    nav {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }}
    nav a {{ border:1px solid var(--line); border-radius:8px; padding:6px 9px; background:var(--soft); }}
    .meta {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; color:var(--muted); }}
    .pill {{ border:1px solid var(--line); border-radius:8px; padding:7px 9px; background:var(--soft); }}
    .summary {{
      display:grid;
      grid-template-columns:repeat(6,minmax(150px,1fr));
      gap:10px;
      margin-top:8px;
    }}
    .metric {{
      background:var(--paper);
      border:1px solid var(--line);
      border-radius:8px;
      padding:11px;
      min-height:82px;
    }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; }}
    .metric b {{ display:block; margin-top:3px; font-size:21px; }}
    .metric small {{ display:block; margin-top:4px; color:var(--muted); }}
    .business-case {{
      margin-top:18px;
      padding-top:4px;
    }}
    .lead {{
      max-width:980px;
      color:#33454f;
      font-size:15px;
    }}
    .case-grid {{
      display:grid;
      grid-template-columns:repeat(3,minmax(0,1fr));
      gap:10px;
      margin:12px 0;
    }}
    .case-card {{
      background:var(--paper);
      border:1px solid var(--line);
      border-radius:8px;
      padding:13px;
      min-height:126px;
    }}
    .case-card h3 {{
      margin:0 0 7px;
      font-size:16px;
    }}
    .case-card p {{
      color:var(--muted);
    }}
    .steps {{
      grid-template-columns:repeat(2,minmax(0,1fr));
    }}
    .step-card {{
      min-height:118px;
    }}
    .strategy-read {{
      grid-template-columns:repeat(6,minmax(130px,1fr));
    }}
    .compact-table table {{
      min-width:560px;
    }}
    .metrics-list {{
      display:grid;
      grid-template-columns:repeat(2,minmax(0,1fr));
      gap:8px 18px;
      background:var(--paper);
      border:1px solid var(--line);
      border-radius:8px;
      padding:14px 14px 14px 32px;
    }}
    .decision {{
      border-left:5px solid var(--green);
      background:var(--soft2);
      border-radius:8px;
      padding:14px;
      margin-top:18px;
    }}
    .candidate {{
      background:var(--paper);
      border:1px solid var(--line);
      border-left:5px solid var(--green);
      border-radius:8px;
      margin:14px 0;
      padding:16px;
    }}
    .candidate.retest {{ border-left-color:var(--amber); }}
    .candidate-head {{
      display:flex;
      justify-content:space-between;
      align-items:flex-start;
      gap:16px;
    }}
    .eyebrow {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
    .score-chip {{
      min-width:78px;
      text-align:center;
      color:var(--green);
      border:1px solid #bad8cd;
      background:#f2faf6;
      border-radius:8px;
      padding:9px;
      font-size:25px;
      font-weight:800;
    }}
    .score-chip span {{ font-size:12px; color:var(--muted); }}
    .metrics, .columns {{
      display:grid;
      grid-template-columns:repeat(4,minmax(0,1fr));
      gap:10px;
      margin-top:12px;
    }}
    .columns {{ grid-template-columns:1fr 1fr; gap:14px; }}
    .columns section, .mini-table, .ratio-grid, .trade-grid {{
      min-width:0;
    }}
    .scorebar {{ margin:9px 0; }}
    .scorebar-head {{ display:flex; justify-content:space-between; gap:10px; font-size:12px; color:var(--muted); }}
    .scorebar-head b {{ color:var(--ink); }}
    .bar {{ height:8px; background:#e7ecef; border-radius:999px; overflow:hidden; margin-top:4px; }}
    .bar span {{ display:block; height:100%; background:linear-gradient(90deg,var(--blue),var(--green)); }}
    .trade-grid, .ratio-grid {{
      display:grid;
      grid-template-columns:repeat(2,minmax(0,1fr));
      gap:8px;
      margin:10px 0;
    }}
    .theme-box {{
      margin-top:12px;
      border:1px solid var(--line);
      border-radius:8px;
      padding:12px;
      background:#fbfdfb;
    }}
    .theme-grid {{
      display:grid;
      grid-template-columns:repeat(4,minmax(0,1fr));
      gap:8px;
      margin:10px 0;
    }}
    .trade-grid div, .ratio-grid div, .theme-grid div {{
      border:1px solid var(--line);
      border-radius:8px;
      padding:8px;
      background:var(--soft);
    }}
    .trade-grid span, .ratio-grid span, .theme-grid span {{ display:block; color:var(--muted); font-size:12px; }}
    .trade-grid b, .ratio-grid b, .theme-grid b {{ display:block; margin-top:2px; overflow-wrap:anywhere; }}
    .theme-grid small {{ display:block; color:var(--muted); margin-top:2px; }}
    .compact {{ margin-top:10px; }}
    .strong {{ font-weight:700; color:var(--ink); }}
    .warning {{ color:#5c4100; background:#fff8e5; border-left:4px solid var(--amber); padding:9px; border-radius:8px; }}
    .muted {{ color:var(--muted); }}
    ul {{ margin:0; padding-left:19px; }}
    li {{ margin:5px 0; }}
    .source-list {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px 14px; padding-left:0; list-style:none; }}
    .source-list span {{ display:block; color:var(--muted); font-size:12px; }}
    .mini-table {{ overflow:auto; border:1px solid var(--line); border-radius:8px; margin:10px 0; }}
    table {{ width:100%; border-collapse:collapse; min-width:760px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }}
    th {{ background:#eef3f5; color:#31434f; font-size:12px; }}
    td span {{ display:block; color:var(--muted); }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--paper); }}
    .table-wrap table {{ min-width:1200px; }}
    footer {{ color:var(--muted); border-top:1px solid var(--line); background:var(--paper); }}
    @media (max-width: 1100px) {{
      .summary {{ grid-template-columns:repeat(3,minmax(150px,1fr)); }}
      .case-grid, .steps, .strategy-read {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .metrics {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .columns {{ grid-template-columns:1fr; }}
      .theme-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .metrics-list {{ grid-template-columns:1fr; }}
      .source-list {{ grid-template-columns:1fr; }}
    }}
    @media (max-width: 720px) {{
      header, main, footer {{ padding:16px; }}
      header {{ position:static; }}
      h1 {{ font-size:23px; }}
      .summary, .metrics {{ grid-template-columns:1fr; }}
      .case-grid, .steps, .strategy-read {{ grid-template-columns:1fr; }}
      .theme-grid {{ grid-template-columns:1fr; }}
      .candidate-head {{ flex-direction:column; }}
      .score-chip {{ width:100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Agent Adda Smallcap Portfolio - Phase 1 Evidence Packs</h1>
    <p>Clean trigger-map names and retest-only names from the 2026-08-06 smallcap portfolio policy gate.</p>
    <div class="meta">
      <span class="pill">Generated: {esc(generated)}</span>
      <span class="pill">Policy: {esc(str(POLICY.relative_to(ROOT)))}</span>
      <span class="pill">Input: {esc(str(POLICY_GATE.relative_to(ROOT)))}</span>
      <span class="pill">Research only</span>
    </div>
    <nav>{nav_links}</nav>
  </header>
  <main>
    <section class="summary">
      {metric("Clean candidates", len(clean), "trigger-map only")}
      {metric("Retest candidates", len(retest), "no-chase watch")}
      {metric("Best score", fmt_num(best["policy"].get("policy_score_100")), best["symbol"])}
      {metric("Clean exposure", fmt_money(clean_value), f"cap {fmt_money(PHASE1_EXPOSURE_CAP)}")}
      {metric("Clean risk", fmt_money(clean_risk), f"cap {fmt_money(OPEN_RISK_CAP)}")}
      {metric("All trigger-map exposure", fmt_money(total_value), f"risk {fmt_money(total_risk)}")}
    </section>

    {business_case}

    <section class="decision">
      <h2>Execution Decision</h2>
      <p><b>No paper order is created yet.</b> The policy output is a trigger map. Every candidate still requires governance/filing review, current-source reconciliation, and a live trigger with volume confirmation before any Agent Adda Smallcap Portfolio paper slot can be booked.</p>
      <p>The clean Phase 1 list is {esc(", ".join(p["symbol"] for p in clean))}. The retest-only list is {esc(", ".join(p["symbol"] for p in retest))}. SYRMA ranks highest, but the report keeps its valuation and working-capital risks visible instead of treating the score as automatic approval.</p>
    </section>

    <h2>Theme Board</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Stock</th><th>Theme Lens</th><th>Stock Expression</th><th>Confirmation</th><th>Theme Risk</th><th>Priority Impact</th><th>Theme Score</th></tr>
        </thead>
        <tbody>{theme_rows}</tbody>
      </table>
    </div>

    <h2>Clean Phase 1 Evidence Packs</h2>
    {clean_cards}

    <h2>Retest-Only Appendix</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Stock</th><th>Score</th><th>No-Chase Gate</th><th>RSI</th><th>RS</th><th>Mapped Trigger</th><th>Slot</th><th>Blockers</th></tr>
        </thead>
        <tbody>{retest_rows}</tbody>
      </table>
    </div>
    {retest_cards}
  </main>
  <footer>
    Inputs are local Agent Adda policy-gate scores, local financial-cache rows, local technical setup snapshots, and Screener/company/exchange source links captured at generation time. This is a research artifact, not investment advice or an executable trading instruction.
  </footer>
</body>
</html>
"""
    OUT_HTML.write_text(html_text, encoding="utf-8")


def main() -> None:
    rows = read_policy_rows()
    packs = [build_pack(row, index + 1) for index, row in enumerate(rows)]
    write_csv(packs)
    write_json(packs)
    write_html(packs)

    clean = [p for p in packs if p["bucket"] == "Clean trigger map"]
    retest = [p for p in packs if p["bucket"] == "Retest trigger map"]
    clean_value = sum(fnum(p["policy"].get("paper_position_value")) or 0 for p in clean)
    clean_risk = sum(fnum(p["policy"].get("paper_risk_to_stop")) or 0 for p in clean)
    print(f"Wrote {OUT_HTML}")
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")
    print(f"Clean candidates: {', '.join(p['symbol'] for p in clean)}")
    print(f"Retest candidates: {', '.join(p['symbol'] for p in retest)}")
    print(f"Clean trigger-map exposure: {clean_value:.0f}; risk: {clean_risk:.0f}")


if __name__ == "__main__":
    main()
