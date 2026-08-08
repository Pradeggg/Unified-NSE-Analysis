from __future__ import annotations

import csv
import html
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.tools import get_technical_setup


NAV = 500_000.0
PHASE1_EXPOSURE_CAP = NAV * 0.40
RISK_PER_TRADE = NAV * 0.0075
TOTAL_OPEN_RISK_CAP = NAV * 0.06
INITIAL_POSITION_CORE = NAV * 0.04
INITIAL_POSITION_WATCH = NAV * 0.03

POLICY = ROOT / "docs" / "fund_policies" / "2026-08-06-smallcap-super-performers-fund-policy.md"
INPUT = ROOT / "Mutual Funds" / "extracted" / "agent_adda_smallcap_preselection_scores_20260806.csv"
OUT_CSV = ROOT / "Mutual Funds" / "extracted" / "agent_adda_smallcap_policy_gate_20260806.csv"
OUT_HTML = ROOT / "Mutual Funds" / "reports" / "agent_adda_smallcap_policy_gate_report_20260806.html"


POLICY_THEME_SECTORS = {
    "Auto Components": "Auto components / EV ancillaries",
    "Industrial Products": "Capital goods / industrial suppliers",
    "Industrial Manufacturing": "Capital goods / industrial manufacturing",
    "Healthcare Services": "Healthcare / specialty services",
    "Pharmaceuticals & Biotechnology": "Healthcare / pharma",
    "Banks": "Financial services",
    "Finance": "Financial services",
    "Retailing": "Consumer / retail",
    "Consumer Durables": "Consumer / premiumization",
    "Chemicals & Petrochemicals": "Chemicals / specialty materials",
    "Other Utilities": "Infrastructure / utilities",
    "Commercial Services & Supplies": "Business services",
    "IT - Software": "Technology / digital infrastructure",
    "IT - Services": "Technology / digital infrastructure",
    "Oil": "Infrastructure / terminals",
    "Textiles & Apparels": "Export / branded manufacturing",
    "Agricultural Food and other Product": "Agri / commodity processing",
}


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    text = text.replace(",", "").replace("%", "").replace("+", "")
    try:
        return float(text)
    except ValueError:
        return None


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def fmt_num(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}"


def fmt_money(value: Any) -> str:
    number = fnum(value)
    if number is None:
        return ""
    return f"Rs. {number:,.0f}"


def fmt_pct(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}%"


def safe_setup(symbol: str) -> dict[str, Any]:
    try:
        out = get_technical_setup(symbol)
        if out.get("error"):
            return {"error": out.get("error")}
        return out
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def dist_pct(price: Any, ref: Any) -> float | None:
    p = fnum(price)
    r = fnum(ref)
    if p is None or r in (None, 0):
        return None
    return (p / r - 1) * 100


def turnover_cr(price: Any, volume: Any) -> float | None:
    p = fnum(price)
    v = fnum(volume)
    if p is None or v is None:
        return None
    return p * v / 10_000_000


def latest_financial_state(row: pd.Series) -> str:
    freshness = str(row.get("financial_freshness") or "").lower()
    if freshness.startswith("fresh result"):
        return "PASS"
    if "needs q1" in freshness or "mar 2026" in freshness:
        return "REFRESH_REQUIRED"
    if "no financial cache" in freshness:
        return "FAIL_NO_CACHE"
    return "PENDING"


def liquidity_gate(avg_turnover_cr: float | None, vol_ratio: float | None) -> str:
    if avg_turnover_cr is None:
        return "PENDING_NO_TURNOVER"
    if avg_turnover_cr < 5:
        return "FAIL_LT_5CR"
    if vol_ratio is not None and vol_ratio < 0.35:
        return "WATCH_THIN_CURRENT_VOLUME"
    return "PASS"


def no_chase_gate(row: pd.Series, setup: dict[str, Any], distance_sma20: float | None) -> str:
    rsi = fnum(row.get("current_rsi"))
    if rsi is not None and rsi > 80:
        return "FAIL_RSI_EXTENDED"
    if distance_sma20 is not None and distance_sma20 > 12:
        return "FAIL_TOO_FAR_FROM_20DMA"
    if rsi is not None and rsi > 75:
        return "WATCH_RSI_EXTENDED"
    if distance_sma20 is not None and distance_sma20 > 8:
        return "WATCH_EXTENDED_FROM_20DMA"
    label = str(row.get("agent_adda_label") or "").upper()
    if "EXTENDED" in label:
        return "WATCH_AGENT_ADDA_EXTENDED"
    return "PASS"


def theme_status(row: pd.Series, chase_gate: str) -> str:
    stage = str(row.get("current_stage") or "")
    rs = fnum(row.get("current_relative_strength")) or 0
    sector = str(row.get("sector") or "")
    has_theme = sector in POLICY_THEME_SECTORS
    if chase_gate.startswith("FAIL") or "EXTENDED" in chase_gate:
        return "CROWDED"
    if stage == "STAGE_2" and rs >= 25 and has_theme:
        return "CONFIRMED"
    if stage == "STAGE_2" and has_theme:
        return "BUILDING"
    if has_theme:
        return "IDEA"
    return "PENDING"


def theme_score(row: pd.Series, theme: str) -> float:
    score = 0.0
    if str(row.get("sector") or "") in POLICY_THEME_SECTORS:
        score += 5.0
    mf_count = fnum(row.get("mutual_fund_count")) or 0
    if mf_count >= 2:
        score += 3.0
    elif mf_count >= 1:
        score += 2.0
    rs = fnum(row.get("current_relative_strength")) or 0
    if rs >= 35:
        score += 3.0
    elif rs >= 20:
        score += 2.0
    elif rs >= 10:
        score += 1.0
    if str(row.get("current_stage") or "") == "STAGE_2":
        score += 2.0
    if theme == "CONFIRMED":
        score += 2.0
    elif theme == "BUILDING":
        score += 1.0
    return round(clamp(score, 0, 15), 1)


def fundamental_policy_score(row: pd.Series, financial_gate: str) -> float:
    base = (fnum(row.get("fundamental_score_30")) or 0) / 30 * 17
    score = base
    if financial_gate == "PASS":
        score += 4
    elif financial_gate == "REFRESH_REQUIRED":
        score += 1.5
    else:
        score -= 2
    q_pat = fnum(row.get("quarter_pat_yoy_pct"))
    a_pat = fnum(row.get("annual_pat_yoy_pct"))
    opm = fnum(row.get("latest_quarter_opm_pct"))
    if q_pat is not None and q_pat >= 25:
        score += 1.5
    if a_pat is not None and a_pat >= 20:
        score += 1.5
    if opm is not None and opm >= 12:
        score += 1.0
    if financial_gate == "FAIL_NO_CACHE":
        score = min(score, 9)
    return round(clamp(score, 0, 25), 1)


def technical_policy_score(row: pd.Series, chase_gate: str) -> float:
    rs_score = relative_strength_score(row)
    momentum = momentum_score(row)
    setup = setup_quality_score(row, chase_gate)
    score = rs_score * 0.8 + momentum * 0.8 + setup * 0.9
    return round(clamp(score, 0, 25), 1)


def relative_strength_score(row: pd.Series) -> float:
    rs = fnum(row.get("current_relative_strength"))
    score = 0.0
    if rs is None:
        score = 1.0
    elif rs >= 40:
        score = 7.0
    elif rs >= 30:
        score = 6.0
    elif rs >= 20:
        score = 5.0
    elif rs >= 10:
        score = 3.5
    elif rs >= 0:
        score = 2.0

    six_month = fnum(row.get("agent_adda_6m"))
    three_month = fnum(row.get("agent_adda_3m"))
    if six_month is not None and six_month >= 50:
        score += 1.5
    elif six_month is not None and six_month >= 25:
        score += 1.0
    if three_month is not None and three_month >= 25:
        score += 1.0
    if three_month is not None and six_month is not None and three_month > six_month:
        score += 0.5
    return round(clamp(score, 0, 10), 1)


def momentum_score(row: pd.Series) -> float:
    setup_score = fnum(row.get("_setup_technical_score")) or 0
    distance_sma20 = fnum(row.get("_distance_sma20"))
    vol_ratio = fnum(row.get("_vol_ratio"))
    rsi = fnum(row.get("current_rsi"))
    score = clamp(setup_score / 100 * 4, 0, 4)
    if distance_sma20 is not None:
        if 0 <= distance_sma20 <= 8:
            score += 2.0
        elif 8 < distance_sma20 <= 12:
            score += 0.8
        elif distance_sma20 < 0:
            score += 0.5
    if rsi is not None:
        if 50 <= rsi <= 70:
            score += 2.0
        elif 40 <= rsi < 50 or 70 < rsi <= 75:
            score += 1.2
        elif 75 < rsi <= 80:
            score += 0.4
    if vol_ratio is not None:
        if vol_ratio >= 1.5:
            score += 2.0
        elif vol_ratio >= 1.0:
            score += 1.2
        elif vol_ratio >= 0.7:
            score += 0.5
    return round(clamp(score, 0, 10), 1)


def setup_quality_score(row: pd.Series, chase_gate: str) -> float:
    score = 0.0
    if str(row.get("current_stage") or "") == "STAGE_2":
        score += 3.0
    if str(row.get("current_signal") or "") == "BUY":
        score += 2.0
    elif str(row.get("current_signal") or "") == "HOLD":
        score += 1.0
    if chase_gate == "PASS":
        score += 2.0
    elif chase_gate.startswith("WATCH"):
        score += 0.8

    expectancy = fnum(row.get("setup_net_expectancy_r"))
    trades = fnum(row.get("setup_trades"))
    quality = str(row.get("setup_sample_quality") or "").lower()
    if expectancy is not None and expectancy >= 0.5:
        score += 1.5
    elif expectancy is not None and expectancy > 0:
        score += 0.8
    if trades is not None and trades >= 10:
        score += 1.0
    elif quality == "medium":
        score += 0.6
    elif quality == "provisional":
        score += 0.2
    return round(clamp(score, 0, 10), 1)


def liquidity_score(avg_turnover_cr: float | None, vol_ratio: float | None) -> float:
    if avg_turnover_cr is None:
        return 0.0
    if avg_turnover_cr >= 50:
        score = 15
    elif avg_turnover_cr >= 20:
        score = 13
    elif avg_turnover_cr >= 10:
        score = 11
    elif avg_turnover_cr >= 5:
        score = 8
    elif avg_turnover_cr >= 2:
        score = 5
    else:
        score = 2
    if vol_ratio is not None and vol_ratio < 0.5:
        score -= 2
    return round(clamp(score, 0, 15), 1)


def governance_score(row: pd.Series, financial_gate: str) -> float:
    # This is intentionally conservative. The policy requires separate
    # governance evidence before a paper order can be created.
    if financial_gate == "PASS" and (fnum(row.get("fundamental_score_30")) or 0) >= 18:
        return 6.0
    if financial_gate == "REFRESH_REQUIRED":
        return 4.5
    if financial_gate == "FAIL_NO_CACHE":
        return 2.5
    return 3.5


def valuation_rr_score(row: pd.Series, chase_gate: str, stop_distance_pct: float) -> float:
    score = 5.0
    if stop_distance_pct <= 10:
        score += 1.5
    if chase_gate == "PASS":
        score += 1.5
    elif chase_gate.startswith("FAIL"):
        score -= 1.5
    if (fnum(row.get("selection_score_100")) or 0) >= 70:
        score += 1.0
    # Full valuation evidence is not yet available for every name.
    return round(clamp(score, 0, 8), 1)


def choose_stop(price: float, setup: dict[str, Any]) -> tuple[float, float, str]:
    sma50 = fnum(setup.get("sma50"))
    if sma50:
        structure_stop = sma50 * 0.99
        structure_pct = (price - structure_stop) / price * 100
        if 6 <= structure_pct <= 12:
            return round(structure_stop, 2), round(structure_pct, 1), "50DMA structure stop"
    return round(price * 0.90, 2), 10.0, "10% policy default stop"


def candidate_rating(score: float) -> str:
    if score >= 75:
        return "Core Candidate"
    if score >= 65:
        return "Active Watch"
    if score >= 55:
        return "Research Watch"
    return "Reject or Monitor"


def phase_status(
    rating: str,
    stage: str,
    liquidity: str,
    financial: str,
    chase: str,
    stop_distance_pct: float,
) -> str:
    if rating == "Reject or Monitor":
        return "REJECT_OR_MONITOR"
    if stage != "STAGE_2":
        return "NO_TRADE_STAGE_FAIL"
    if liquidity.startswith("FAIL"):
        return "NO_TRADE_LIQUIDITY_FAIL"
    if financial == "FAIL_NO_CACHE":
        return "NO_TRADE_FINANCIAL_CACHE_MISSING"
    if stop_distance_pct > 12:
        return "NO_TRADE_STOP_TOO_WIDE"
    if chase.startswith("FAIL") and financial == "REFRESH_REQUIRED":
        return "RETEST_AND_REFRESH_BEFORE_PHASE1"
    if chase.startswith("FAIL"):
        return "RETEST_ONLY_NO_CHASE"
    if chase.startswith("WATCH") and financial == "PASS" and rating in {"Core Candidate", "Active Watch"}:
        return "PHASE1_RETEST_TRIGGER_MAP_GOVERNANCE_PENDING"
    if chase.startswith("WATCH") and financial == "REFRESH_REQUIRED" and rating in {"Core Candidate", "Active Watch"}:
        return "RETEST_AND_REFRESH_BEFORE_PHASE1"
    if financial == "PASS" and rating in {"Core Candidate", "Active Watch"}:
        return "PHASE1_TRIGGER_MAP_GOVERNANCE_PENDING"
    if financial == "REFRESH_REQUIRED" and rating in {"Core Candidate", "Active Watch"}:
        return "REFRESH_RESULTS_BEFORE_PHASE1"
    if rating == "Research Watch":
        return "RESEARCH_WATCH_NO_CAPITAL"
    return "HOLD_FOR_EVIDENCE"


def build_row(row: pd.Series) -> dict[str, Any]:
    symbol = str(row["symbol"]).strip().upper()
    setup = safe_setup(symbol)
    price = fnum(setup.get("price")) or fnum(row.get("current_price")) or 0.0
    avg_turnover = turnover_cr(price, setup.get("vol_avg_20d"))
    vol_ratio = fnum(setup.get("vol_ratio"))
    distance_sma20 = dist_pct(price, setup.get("sma20"))
    distance_sma50 = dist_pct(price, setup.get("sma50"))
    stop_price, stop_distance, stop_method = choose_stop(price, setup) if price else (None, 10.0, "pending price")
    financial = latest_financial_state(row)
    liquidity = liquidity_gate(avg_turnover, vol_ratio)
    chase = no_chase_gate(row, setup, distance_sma20)
    theme = theme_status(row, chase)

    tech_row = row.copy()
    tech_row["_setup_technical_score"] = fnum(setup.get("technical_score"))
    tech_row["_distance_sma20"] = distance_sma20
    tech_row["_vol_ratio"] = vol_ratio
    rs_subscore = relative_strength_score(tech_row)
    momentum_subscore = momentum_score(tech_row)
    setup_subscore = setup_quality_score(tech_row, chase)
    theme_pts = theme_score(row, theme)
    fund_pts = fundamental_policy_score(row, financial)
    tech_pts = technical_policy_score(tech_row, chase)
    liq_pts = liquidity_score(avg_turnover, vol_ratio)
    gov_pts = governance_score(row, financial)
    rr_pts = valuation_rr_score(row, chase, stop_distance)
    policy_score = round(theme_pts + fund_pts + tech_pts + liq_pts + gov_pts + rr_pts, 1)
    rating = candidate_rating(policy_score)
    status = phase_status(rating, str(row.get("current_stage") or ""), liquidity, financial, chase, stop_distance)

    initial_value = 0.0
    if rating == "Core Candidate":
        initial_value = INITIAL_POSITION_CORE
    elif rating == "Active Watch":
        initial_value = INITIAL_POSITION_WATCH
    max_qty_by_position = math.floor(initial_value / price) if price and initial_value else 0
    risk_per_share = abs(price - (stop_price or 0)) if price and stop_price else 0
    max_qty_by_risk = math.floor(RISK_PER_TRADE / risk_per_share) if risk_per_share else 0
    liquidity_value_cap = (avg_turnover or 0) * 10_000_000 * 0.02
    max_qty_by_liquidity = math.floor(liquidity_value_cap / price) if price and liquidity_value_cap else 0
    qty = min(max_qty_by_position, max_qty_by_risk, max_qty_by_liquidity) if price else 0
    proposed_value = round(qty * price, 2)
    proposed_risk = round(qty * risk_per_share, 2)
    target_2r = round(price + 2 * risk_per_share, 2) if price and risk_per_share else None

    evidence_blockers: list[str] = []
    if financial != "PASS":
        evidence_blockers.append(financial)
    evidence_blockers.append("GOVERNANCE_REVIEW_PENDING")
    if liquidity != "PASS":
        evidence_blockers.append(liquidity)
    if chase != "PASS":
        evidence_blockers.append(chase)

    if status == "PHASE1_TRIGGER_MAP_GOVERNANCE_PENDING":
        next_action = "Complete governance/filing review, then wait for breakout-retest or pullback trigger."
    elif status == "PHASE1_RETEST_TRIGGER_MAP_GOVERNANCE_PENDING":
        next_action = "Complete governance/filing review; retest-only because current setup is extended or flagged no-chase."
    elif status == "REFRESH_RESULTS_BEFORE_PHASE1":
        next_action = "Refresh latest quarterly result and source trail before any Phase 1 paper slot."
    elif status == "RETEST_AND_REFRESH_BEFORE_PHASE1":
        next_action = "Refresh latest result and wait for retest/reset; no chase."
    elif status == "RETEST_ONLY_NO_CHASE":
        next_action = "No chase; wait for RSI/distance reset and retest hold."
    elif "NO_TRADE" in status:
        next_action = "No capital until failed gate is fixed."
    elif status == "RESEARCH_WATCH_NO_CAPITAL":
        next_action = "Track only; score is below active-capital threshold."
    else:
        next_action = "Hold for more evidence."

    entry_trigger = "Pending trigger map"
    if price:
        high_52w = fnum(setup.get("52w_high"))
        sma20 = fnum(setup.get("sma20"))
        if high_52w and sma20:
            entry_trigger = (
                f"Break above {high_52w * 1.01:.2f} with volume, or retest-hold near "
                f"{sma20:.2f}; skip if >5% above planned trigger."
            )
        elif sma20:
            entry_trigger = f"Retest-hold near 20DMA {sma20:.2f}; skip if >5% above trigger."

    return {
        "symbol": symbol,
        "company": row.get("company", ""),
        "sector": row.get("sector", ""),
        "policy_theme_bucket": POLICY_THEME_SECTORS.get(str(row.get("sector") or ""), "Unmapped"),
        "theme_status": theme,
        "policy_score_100": policy_score,
        "policy_rating": rating,
        "phase1_status": status,
        "preselection_score_100": fnum(row.get("selection_score_100")),
        "preselection_decision": row.get("decision_bucket", ""),
        "theme_fit_15": theme_pts,
        "fundamental_25": fund_pts,
        "technical_25": tech_pts,
        "relative_strength_score_10": rs_subscore,
        "momentum_score_10": momentum_subscore,
        "setup_quality_score_10": setup_subscore,
        "liquidity_tradeability_15": liq_pts,
        "governance_management_10": gov_pts,
        "valuation_reward_risk_10": rr_pts,
        "current_price": price,
        "current_stage": row.get("current_stage", ""),
        "current_signal": row.get("current_signal", ""),
        "current_rsi": fnum(row.get("current_rsi")),
        "current_relative_strength": fnum(row.get("current_relative_strength")),
        "technical_setup_score": fnum(setup.get("technical_score")),
        "sma20": fnum(setup.get("sma20")),
        "sma50": fnum(setup.get("sma50")),
        "distance_from_sma20_pct": distance_sma20,
        "distance_from_sma50_pct": distance_sma50,
        "pct_from_52w_high": fnum(setup.get("pct_from_52h")),
        "vol_avg_20d": fnum(setup.get("vol_avg_20d")),
        "avg_turnover_20d_cr": avg_turnover,
        "vol_ratio": vol_ratio,
        "liquidity_gate": liquidity,
        "financial_gate": financial,
        "governance_gate": "PENDING_OFFICIAL_REVIEW",
        "stop_distance_gate": "PASS" if stop_distance <= 12 else "FAIL_STOP_GT_12",
        "reward_risk_gate": "PASS_2R_MODELLED" if stop_distance <= 12 else "PENDING",
        "no_chase_gate": chase,
        "entry_trigger": entry_trigger,
        "reference_entry_price": price,
        "initial_stop_price": stop_price,
        "initial_stop_distance_pct": stop_distance,
        "stop_method": stop_method,
        "target_2r_price": target_2r,
        "policy_initial_slot_value": initial_value,
        "paper_quantity_by_policy": qty,
        "paper_position_value": proposed_value,
        "paper_risk_to_stop": proposed_risk,
        "max_position_qty_by_value": max_qty_by_position,
        "max_position_qty_by_risk": max_qty_by_risk,
        "max_position_qty_by_liquidity": max_qty_by_liquidity,
        "latest_quarter": row.get("latest_quarter", ""),
        "financial_freshness": row.get("financial_freshness", ""),
        "key_strengths": row.get("key_strengths", ""),
        "key_risks": row.get("key_risks", ""),
        "evidence_blockers": "; ".join(dict.fromkeys(evidence_blockers)),
        "next_action": next_action,
    }


def build_rows() -> list[dict[str, Any]]:
    df = pd.read_csv(INPUT)
    rows = [build_row(row) for _, row in df.iterrows()]
    return sorted(
        rows,
        key=lambda r: (
            r["phase1_status"] != "PHASE1_TRIGGER_MAP_GOVERNANCE_PENDING",
            r["phase1_status"] != "REFRESH_RESULTS_BEFORE_PHASE1",
            -(fnum(r["policy_score_100"]) or 0),
        ),
    )


def write_csv(rows: list[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def status_class(status: str) -> str:
    s = status.lower()
    if "retest" in s:
        return "retest"
    if "trigger_map" in s:
        return "ready"
    if "refresh" in s:
        return "refresh"
    if "research" in s:
        return "research"
    if "reject" in s or "no_trade" in s:
        return "reject"
    return "hold"


def make_row_html(row: dict[str, Any]) -> str:
    return f"""
      <tr>
        <td><b>{esc(row['symbol'])}</b><span>{esc(row['company'])}</span></td>
        <td>{esc(row['policy_rating'])}<br><small>{fmt_num(row['policy_score_100'])}/100</small></td>
        <td class="{status_class(row['phase1_status'])}">{esc(row['phase1_status'])}</td>
        <td>{esc(row['policy_theme_bucket'])}<br><small>{esc(row['theme_status'])}</small></td>
        <td>{fmt_num(row['theme_fit_15'])}<br><small>Theme</small></td>
        <td>{fmt_num(row['fundamental_25'])}<br><small>Fundamental</small></td>
        <td>{fmt_num(row['technical_25'])}<br><small>Tech</small></td>
        <td>{fmt_num(row['relative_strength_score_10'])}<br><small>RS</small></td>
        <td>{fmt_num(row['momentum_score_10'])}<br><small>Momentum</small></td>
        <td>{fmt_num(row['setup_quality_score_10'])}<br><small>Setup</small></td>
        <td>{fmt_num(row['liquidity_tradeability_15'])}<br><small>{fmt_num(row['avg_turnover_20d_cr'])} cr</small></td>
        <td>{fmt_num(row['governance_management_10'])}<br><small>{esc(row['governance_gate'])}</small></td>
        <td>{fmt_num(row['valuation_reward_risk_10'])}<br><small>{esc(row['reward_risk_gate'])}</small></td>
        <td>{fmt_num(row['current_price'])}<br><small>{esc(row['current_stage'])} / RSI {fmt_num(row['current_rsi'])}</small></td>
        <td>{esc(row['entry_trigger'])}</td>
        <td>{fmt_num(row['initial_stop_price'])}<br><small>{fmt_pct(row['initial_stop_distance_pct'])}</small></td>
        <td>{fmt_money(row['paper_position_value'])}<br><small>{esc(row['paper_quantity_by_policy'])} sh / risk {fmt_money(row['paper_risk_to_stop'])}</small></td>
        <td>{esc(row['evidence_blockers'])}</td>
        <td>{esc(row['next_action'])}</td>
      </tr>
    """


def write_html(rows: list[dict[str, Any]]) -> None:
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    counts = pd.Series([r["phase1_status"] for r in rows]).value_counts().to_dict()
    ready = [r for r in rows if r["phase1_status"] == "PHASE1_TRIGGER_MAP_GOVERNANCE_PENDING"]
    retest_ready = [r for r in rows if r["phase1_status"] == "PHASE1_RETEST_TRIGGER_MAP_GOVERNANCE_PENDING"]
    refresh = [
        r
        for r in rows
        if r["phase1_status"] in {"REFRESH_RESULTS_BEFORE_PHASE1", "RETEST_AND_REFRESH_BEFORE_PHASE1"}
    ]
    modelled_value = sum(fnum(r["paper_position_value"]) or 0 for r in ready)
    modelled_risk = sum(fnum(r["paper_risk_to_stop"]) or 0 for r in ready)
    table = "\n".join(make_row_html(row) for row in rows)
    ready_cards = "\n".join(
        f"""
        <article>
          <h3>{esc(r['symbol'])}</h3>
          <p>{esc(r['company'])}</p>
          <dl>
            <div><dt>Policy Score</dt><dd>{fmt_num(r['policy_score_100'])}</dd></div>
            <div><dt>Slot</dt><dd>{fmt_money(r['paper_position_value'])}</dd></div>
            <div><dt>Risk</dt><dd>{fmt_money(r['paper_risk_to_stop'])}</dd></div>
            <div><dt>Gate</dt><dd>{esc(r['governance_gate'])}</dd></div>
          </dl>
          <p>{esc(r['entry_trigger'])}</p>
        </article>
        """
        for r in ready
    ) or "<p>No symbol can become an order yet without at least governance/filing completion and a live trigger.</p>"
    retest_cards = "\n".join(
        f"""
        <article class="retest-card">
          <h3>{esc(r['symbol'])}</h3>
          <p>{esc(r['company'])}</p>
          <dl>
            <div><dt>Policy Score</dt><dd>{fmt_num(r['policy_score_100'])}</dd></div>
            <div><dt>No-Chase Gate</dt><dd>{esc(r['no_chase_gate'])}</dd></div>
            <div><dt>RS / Momentum / Setup</dt><dd>{fmt_num(r['relative_strength_score_10'])} / {fmt_num(r['momentum_score_10'])} / {fmt_num(r['setup_quality_score_10'])}</dd></div>
            <div><dt>Risk</dt><dd>{fmt_money(r['paper_risk_to_stop'])}</dd></div>
          </dl>
          <p>{esc(r['entry_trigger'])}</p>
        </article>
        """
        for r in retest_ready
    ) or "<p>No fresh-result retest-trigger names are available.</p>"
    refresh_list = "\n".join(f"<li><b>{esc(r['symbol'])}</b> - {esc(r['next_action'])}</li>" for r in refresh[:10])
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Smallcap Super Performers Portfolio - Policy Gate</title>
  <style>
    :root {{
      --ink:#172129; --muted:#5e6d78; --line:#d7e0e6; --paper:#fff;
      --soft:#f5f8f9; --ready:#0d6b52; --refresh:#2d6f8c; --retest:#9a6a00; --reject:#9a332b;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; color:var(--ink); background:#fbfcfc; }}
    header, main, footer {{ padding:24px 32px; }}
    header, footer {{ background:var(--paper); border-bottom:1px solid var(--line); }}
    footer {{ border-top:1px solid var(--line); border-bottom:0; color:var(--muted); }}
    h1 {{ margin:0 0 8px; font-size:27px; letter-spacing:0; }}
    h2 {{ margin:26px 0 12px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0 0 4px; font-size:18px; letter-spacing:0; }}
    p {{ margin:0; color:var(--muted); }}
    .meta, .summary {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }}
    .pill, .metric {{ border:1px solid var(--line); background:var(--soft); border-radius:8px; padding:9px 11px; }}
    .metric b {{ display:block; font-size:24px; color:var(--ink); }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(260px,1fr)); gap:12px; }}
    article {{ background:var(--paper); border:1px solid var(--line); border-left:5px solid var(--ready); border-radius:8px; padding:14px; }}
    article.retest-card {{ border-left-color:var(--retest); }}
    dl {{ display:grid; grid-template-columns:repeat(4,minmax(90px,1fr)); gap:8px; margin:12px 0; }}
    dt {{ font-size:12px; color:var(--muted); }}
    dd {{ margin:0; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--paper); }}
    table {{ border-collapse:collapse; width:100%; min-width:2100px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:9px 8px; vertical-align:top; text-align:left; }}
    th {{ background:#eef3f5; color:#30404a; position:sticky; top:0; z-index:1; font-size:12px; }}
    td span, small {{ display:block; color:var(--muted); }}
    .ready {{ color:var(--ready); font-weight:700; }}
    .refresh {{ color:var(--refresh); font-weight:700; }}
    .retest {{ color:var(--retest); font-weight:700; }}
    .research {{ color:#52606a; font-weight:700; }}
    .reject {{ color:var(--reject); font-weight:700; }}
    .hold {{ color:#52606a; font-weight:700; }}
    .note {{ border-left:4px solid var(--retest); background:#fff8e8; padding:12px; border-radius:8px; color:#463604; }}
    @media (max-width: 900px) {{
      header, main, footer {{ padding-left:16px; padding-right:16px; }}
      .grid {{ grid-template-columns:1fr; }}
      h1 {{ font-size:23px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Smallcap Super Performers Portfolio - Policy Gate</h1>
    <p>Application of the 2026-08-06 portfolio policy to the Agent Adda small-cap preselection scores.</p>
    <div class="meta">
      <span class="pill">Generated: {esc(generated)}</span>
      <span class="pill">Corpus: Rs. 5,00,000 paper capital</span>
      <span class="pill">Phase 1 exposure cap: Rs. 2,00,000</span>
      <span class="pill">Risk per trade: Rs. 3,750</span>
      <span class="pill">Research only; no live recommendation</span>
    </div>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><b>{len(rows)}</b><span>Policy-scored names</span></div>
      <div class="metric"><b>{counts.get('PHASE1_TRIGGER_MAP_GOVERNANCE_PENDING', 0)}</b><span>Clean trigger-map names</span></div>
      <div class="metric"><b>{counts.get('PHASE1_RETEST_TRIGGER_MAP_GOVERNANCE_PENDING', 0)}</b><span>Retest trigger-map names</span></div>
      <div class="metric"><b>{counts.get('REFRESH_RESULTS_BEFORE_PHASE1', 0)}</b><span>Refresh before Phase 1</span></div>
      <div class="metric"><b>{fmt_money(modelled_value)}</b><span>Modelled trigger-map exposure</span></div>
      <div class="metric"><b>{fmt_money(modelled_risk)}</b><span>Modelled risk to stop</span></div>
    </section>

    <h2>Policy Decision</h2>
    <p class="note">No automatic paper buy is created. The policy requires governance/filing review, a defined entry trigger, liquidity pass, and stop-risk sizing before any order. Current output is a Phase 1 trigger map and evidence backlog.</p>

    <h2>Phase 1 Trigger Map</h2>
    <section class="grid">{ready_cards}</section>

    <h2>Retest Trigger Map</h2>
    <section class="grid">{retest_cards}</section>

    <h2>Refresh Backlog</h2>
    <ul>{refresh_list}</ul>

    <h2>Full Policy Gate Table</h2>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Stock</th><th>Rating</th><th>Phase Status</th><th>Theme</th><th>Theme</th><th>Fundamental</th><th>Tech</th><th>RS</th><th>Momentum</th><th>Setup</th><th>Liquidity</th><th>Governance</th><th>RR</th>
            <th>Setup</th><th>Entry Trigger</th><th>Stop</th><th>Policy Slot</th><th>Blockers</th><th>Next Action</th>
          </tr>
        </thead>
        <tbody>{table}</tbody>
      </table>
    </section>
  </main>
  <footer>
    Inputs: {esc(str(POLICY.relative_to(ROOT)))}, {esc(str(INPUT.relative_to(ROOT)))}, local technical setup snapshots.
    Governance review remains pending for all names; policy scores are pre-order research gates, not executable orders.
  </footer>
</body>
</html>
"""
    OUT_HTML.write_text(html_text, encoding="utf-8")


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_html(rows)
    df = pd.DataFrame(rows)
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_HTML}")
    print(df[["symbol", "policy_score_100", "policy_rating", "phase1_status", "paper_position_value", "paper_risk_to_stop"]].head(15).to_string(index=False))
    print("\nPhase status counts:")
    print(df["phase1_status"].value_counts().to_string())
    ready = df[df["phase1_status"].eq("PHASE1_TRIGGER_MAP_GOVERNANCE_PENDING")]
    print(f"\nReady trigger-map exposure: {ready['paper_position_value'].sum():.0f}; risk: {ready['paper_risk_to_stop'].sum():.0f}")
    print(f"Phase 1 exposure cap: {PHASE1_EXPOSURE_CAP:.0f}; open-risk cap: {TOTAL_OPEN_RISK_CAP:.0f}")


if __name__ == "__main__":
    main()
