from __future__ import annotations

import argparse
import csv
import html
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.tools import get_index_snapshot, get_live_quote


DEFAULT_RUN_DATE = datetime.now().strftime("%Y%m%d")
NAV = 500_000.0

POLICY_GATE = ROOT / "Mutual Funds" / "extracted" / "agent_adda_smallcap_policy_gate_20260806.csv"
PRESELECTION = ROOT / "Mutual Funds" / "extracted" / "agent_adda_smallcap_preselection_scores_20260806.csv"
REFRESH_AUDIT = ROOT / "Mutual Funds" / "extracted" / "smallcap_fundamental_refresh_audit_20260806.csv"

RUN_DATE = DEFAULT_RUN_DATE
RUN_DATE_DISPLAY = ""
OUT_CSV = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_research_update_{RUN_DATE}.csv"
OUT_MD = ROOT / "docs" / "fund_policies" / "research_updates" / "smallcap-portfolio-research-update.md"
OUT_HTML = ROOT / "Mutual Funds" / "reports" / f"agent_adda_smallcap_research_update_{RUN_DATE}.html"

SYMBOLS = [
    "SYRMA",
    "GLAND",
    "RUBICON",
    "SKYGOLD",
    "CPPLUS",
    "RRKABEL",
    "KARURVYSYA",
    "RAINBOW",
    "SANSERA",
]

INDEXES = [
    "NIFTY SMALLCAP 100",
    "NIFTY SMALLCAP 250",
    "NIFTY SMALLCAP 50",
    "NIFTY 50",
    "NIFTY AUTO",
    "NIFTY PHARMA",
    "NIFTY IT",
    "NIFTY CONSUMER DURABLES",
]

EXTERNAL_EVIDENCE: dict[str, dict[str, str]] = {
    "GLAND": {
        "result_status": "Board meeting scheduled before Q1 FY27 result extraction",
        "external_note": (
            "Official Gland page lists Q1 FY27 result, press release, transcript, and audio links, "
            "but result/transcript/audio URLs returned 404 in the web check. The board-meeting "
            "intimation confirms the meeting is on 2026-08-10 and the call is at 18:30 IST."
        ),
        "source_trail": (
            "https://glandpharma.com/investors/financials | "
            "https://glandpharma.com/images/BM_Intimation_Q1_FY27.pdf"
        ),
        "research_action": "Wait for 2026-08-10 result/call, then extract official numbers.",
    },
    "RUBICON": {
        "result_status": "Q1 FY27 result not visible in fetched official investor page",
        "external_note": (
            "Official investor page shows July 2026 corporate events including KIA Rubicon merger, "
            "Invatech acquisition, ESOP allotment, board outcome, FDA inspection, and shareholding. "
            "The result itself still needs direct exchange confirmation."
        ),
        "source_trail": "https://www.rubicon.co.in/investors",
        "research_action": "Direct NSE/BSE result search plus corporate-action and FDA-event review.",
    },
    "SKYGOLD": {
        "result_status": "Q1 FY27 result event pending / not in fetched official extract",
        "external_note": (
            "Official IR extract still surfaced older June 2025 quarter result/presentation rows. "
            "Secondary market-news sources indicated an August 2026 Q1 event window; treat this as "
            "pending until official result is extracted."
        ),
        "source_trail": "https://skygold.co.in/investor-relations-2/",
        "research_action": "Wait for official Q1 FY27 result, then reconcile cash conversion and gold working capital.",
    },
    "CPPLUS": {
        "result_status": "Q1 FY27 result pending",
        "external_note": (
            "Official Aditya Infotech stock-exchange page showed AGM/trading-window and March 2026 "
            "material in the fetched extract. Secondary portals indicated a board meeting on "
            "2026-08-12 for June 2026 quarterly results."
        ),
        "source_trail": "https://www.adityagroup.com/stock-exchange-submissions",
        "research_action": "No selection until the 2026-08-12 quarterly result and Supertrend conflict clear.",
    },
    "SANSERA": {
        "result_status": "Fresh result still required in local cache",
        "external_note": "Auto-components theme has sector tailwind, but the local financial cache remains Mar 2026.",
        "source_trail": "Local Agent Adda financial refresh audit",
        "research_action": "Result refresh plus pullback/retest only because price is extended.",
    },
    "RRKABEL": {
        "result_status": "Fresh Jun 2026 result in local cache",
        "external_note": "Result freshness is better, but RSI extension blocks chase entry.",
        "source_trail": "Local Agent Adda policy gate and preselection CSVs",
        "research_action": "Retest-only watch after RSI cools.",
    },
    "SYRMA": {
        "result_status": "Fresh Jun 2026 result in local cache",
        "external_note": "Best clean trigger-map score, but governance and valuation review remain open.",
        "source_trail": "Local Agent Adda policy gate and preselection CSVs",
        "research_action": "Build/update focused evidence pack before any paper trigger.",
    },
    "KARURVYSYA": {
        "result_status": "Fresh Jun 2026 result in local cache",
        "external_note": "Bank candidate needs asset-quality, NIM, CASA, credit-cost, and liquidity review.",
        "source_trail": "Local Agent Adda policy gate and preselection CSVs",
        "research_action": "Bank-specific evidence pack, then wait for volume-backed trigger.",
    },
    "RAINBOW": {
        "result_status": "Fresh Jun 2026 result in local cache",
        "external_note": "Existing evidence pack is usable, but current state remains retest-only after extension.",
        "source_trail": "docs/fund_policies/evidence_packs/2026-08-06-rainbow-evidence-pack.md",
        "research_action": "Keep prepared; do not chase before governance review and retest confirmation.",
    },
}


def display_date(run_date: str) -> str:
    return f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}"


def configure_run_date(run_date: str) -> None:
    global RUN_DATE, RUN_DATE_DISPLAY, OUT_CSV, OUT_MD, OUT_HTML
    if not re.fullmatch(r"\d{8}", run_date):
        raise ValueError("run_date must use YYYYMMDD format")
    RUN_DATE = run_date
    RUN_DATE_DISPLAY = display_date(run_date)
    OUT_CSV = ROOT / "Mutual Funds" / "extracted" / f"agent_adda_smallcap_research_update_{RUN_DATE}.csv"
    OUT_MD = ROOT / "docs" / "fund_policies" / "research_updates" / f"{RUN_DATE_DISPLAY}-smallcap-portfolio-research-update.md"
    OUT_HTML = ROOT / "Mutual Funds" / "reports" / f"agent_adda_smallcap_research_update_{RUN_DATE}.html"


configure_run_date(DEFAULT_RUN_DATE)


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    text = text.replace(",", "").replace("%", "").replace("Rs.", "").replace("₹", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def fmt(value: Any, digits: int = 2) -> str:
    number = fnum(value)
    if number is None:
        return "NA"
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def fmt_pct(value: Any, digits: int = 2) -> str:
    number = fnum(value)
    return "NA" if number is None else f"{number:,.{digits}f}%"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def clean_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def read_csv_by_symbol(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {row["symbol"]: row for row in rows if row.get("symbol")}


def parse_levels(trigger: str) -> tuple[float | None, float | None]:
    breakout = None
    retest = None
    m = re.search(r"Break above\s+([0-9,.]+)", trigger or "", flags=re.I)
    if m:
        breakout = fnum(m.group(1))
    m = re.search(r"retest-hold near\s+([0-9,.]+)", trigger or "", flags=re.I)
    if m:
        retest = fnum(m.group(1))
    return breakout, retest


def quote(symbol: str) -> dict[str, Any]:
    try:
        return get_live_quote(symbol) or {"symbol": symbol, "error": "empty quote"}
    except Exception as exc:
        return {"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}


def index_snapshot(index: str) -> dict[str, Any]:
    try:
        return get_index_snapshot(index) or {"index": index, "error": "empty snapshot"}
    except Exception as exc:
        return {"index": index, "error": f"{type(exc).__name__}: {exc}"}


def trigger_state(policy: dict[str, Any], latest_price: float | None, day_high: float | None, day_low: float | None) -> str:
    breakout, retest = parse_levels(policy.get("entry_trigger", ""))
    blockers = " ".join(
        str(policy.get(key, ""))
        for key in ["financial_gate", "governance_gate", "evidence_blockers", "phase1_status"]
    )
    blocked = any(token in blockers for token in ["REFRESH_REQUIRED", "PENDING", "NO_CHASE", "WATCH_AGENT", "FAIL_"])
    if latest_price is None:
        return "NO_QUOTE"
    if breakout is not None and day_high is not None and latest_price >= breakout and day_high >= breakout:
        return "TRIGGER_TOUCHED_BUT_BLOCKED" if blocked else "TRIGGER_READY_REVIEW"
    if retest is not None and day_low is not None and day_low <= retest <= latest_price:
        return "RETEST_HELD_BUT_BLOCKED" if blocked else "RETEST_READY_REVIEW"
    if breakout is not None and breakout > latest_price:
        gap = (breakout / latest_price - 1) * 100
        if gap <= 3:
            return "NEAR_BREAKOUT_BUT_WAIT"
    return "WAIT"


def readiness_overlay(policy: dict[str, Any], pre: dict[str, Any]) -> tuple[float, str]:
    score = fnum(policy.get("policy_score_100")) or fnum(pre.get("selection_score_100")) or 0.0
    reasons: list[str] = []

    if policy.get("current_stage") == "STAGE_2":
        score += 2
        reasons.append("+stage2")
    if policy.get("current_signal") == "BUY":
        score += 2
        reasons.append("+buy_signal")

    rs = fnum(policy.get("current_relative_strength"))
    if rs is not None:
        if rs >= 50:
            score += 4
            reasons.append("+rs_leader")
        elif rs >= 35:
            score += 3
            reasons.append("+rs_good")
        elif rs >= 25:
            score += 2
            reasons.append("+rs_ok")
        elif rs < 15:
            score -= 2
            reasons.append("-rs_low")

    rsi = fnum(policy.get("current_rsi"))
    if rsi is not None:
        if rsi > 75:
            score -= 5
            reasons.append("-rsi_extended")
        elif 50 <= rsi <= 65:
            score += 1
            reasons.append("+rsi_constructive")

    if policy.get("financial_gate") == "REFRESH_REQUIRED":
        score -= 8
        reasons.append("-stale_result")
    if "PENDING" in str(policy.get("governance_gate", "")):
        score -= 5
        reasons.append("-governance_pending")
    blockers = str(policy.get("evidence_blockers", ""))
    if any(token in blockers for token in ["WATCH_AGENT_ADDA_EXTENDED", "FAIL_RSI_EXTENDED", "FAIL_TOO_FAR_FROM_20DMA"]):
        score -= 5
        reasons.append("-no_chase")

    if str(pre.get("supertrend_state", "")).upper() == "BEARISH":
        score -= 3
        reasons.append("-supertrend_conflict")
    ocf = fnum(pre.get("operating_cash_flow_cr"))
    if ocf is not None and ocf < 0:
        score -= 3
        reasons.append("-negative_ocf")
    debt = fnum(pre.get("debt_to_equity"))
    if debt is not None and debt > 0.6:
        score -= 2
        reasons.append("-working_capital_leverage")

    score = max(0.0, min(100.0, round(score, 1)))
    return score, "; ".join(reasons)


def action_bucket(row: dict[str, Any]) -> str:
    state = row["trigger_state"]
    blockers = row["blockers"]
    if "TRIGGER_TOUCHED" in state:
        return "No order: trigger touched before evidence cleared" if blockers else "Trigger review"
    if "REFRESH_REQUIRED" in blockers:
        return "Refresh first"
    if "FAIL_RSI_EXTENDED" in blockers or "FAIL_TOO_FAR_FROM_20DMA" in blockers or "WATCH_AGENT" in blockers:
        return "Retest only"
    if "GOVERNANCE_REVIEW_PENDING" in blockers:
        return "Evidence pack / governance review"
    return "Watch trigger"


def build_rows() -> list[dict[str, Any]]:
    policy_rows = read_csv_by_symbol(POLICY_GATE)
    pre_rows = read_csv_by_symbol(PRESELECTION)
    audit_rows = read_csv_by_symbol(REFRESH_AUDIT)
    rows: list[dict[str, Any]] = []

    for symbol in SYMBOLS:
        policy = policy_rows[symbol]
        pre = pre_rows.get(symbol, {})
        audit = audit_rows.get(symbol, {})
        q = quote(symbol)
        latest_price = fnum(q.get("last_price")) or fnum(policy.get("current_price"))
        day_high = fnum(q.get("day_high"))
        day_low = fnum(q.get("day_low"))
        breakout, retest = parse_levels(policy.get("entry_trigger", ""))
        stop = fnum(policy.get("initial_stop_price"))
        readiness, readiness_notes = readiness_overlay(policy, pre)
        source_note = EXTERNAL_EVIDENCE.get(symbol, {})
        blockers = "; ".join(
            x for x in [
                str(policy.get("evidence_blockers", "") or ""),
                str(policy.get("financial_gate", "") or ""),
                str(policy.get("governance_gate", "") or ""),
            ]
            if x and x.lower() != "nan"
        )
        trigger = trigger_state(policy, latest_price, day_high, day_low)
        row = {
            "symbol": symbol,
            "company": policy.get("company", ""),
            "sector": policy.get("sector", ""),
            "policy_score_100": policy.get("policy_score_100", ""),
            "readiness_overlay_100": readiness,
            "readiness_notes": readiness_notes,
            "policy_rating": policy.get("policy_rating", ""),
            "phase1_status": policy.get("phase1_status", ""),
            "local_stage_signal": f"{policy.get('current_stage', '')} / {policy.get('current_signal', '')}",
            "rsi": policy.get("current_rsi", ""),
            "relative_strength": policy.get("current_relative_strength", ""),
            "latest_price": latest_price,
            "latest_pct_change": q.get("pct_change"),
            "quote_as_of": q.get("as_of") or q.get("error", ""),
            "quote_source": q.get("source", ""),
            "breakout_level": breakout,
            "retest_level": retest,
            "initial_stop": stop,
            "target_2r": policy.get("target_2r_price", ""),
            "paper_quantity": policy.get("paper_quantity_by_policy", ""),
            "paper_position_value": policy.get("paper_position_value", ""),
            "paper_risk_to_stop": policy.get("paper_risk_to_stop", ""),
            "trigger_state": trigger,
            "action_bucket": "",
            "latest_quarter": policy.get("latest_quarter", ""),
            "financial_freshness": policy.get("financial_freshness", ""),
            "audit_outcome": audit.get("refresh_outcome", ""),
            "annual_revenue_cr": pre.get("annual_revenue_cr", ""),
            "annual_pat_cr": pre.get("annual_pat_cr", ""),
            "latest_quarter_revenue_cr": pre.get("latest_quarter_revenue_cr", ""),
            "latest_quarter_pat_cr": pre.get("latest_quarter_pat_cr", ""),
            "annual_revenue_yoy_pct": pre.get("annual_revenue_yoy_pct", ""),
            "annual_pat_yoy_pct": pre.get("annual_pat_yoy_pct", ""),
            "operating_cash_flow_cr": pre.get("operating_cash_flow_cr", ""),
            "debt_to_equity": pre.get("debt_to_equity", ""),
            "supertrend_state": pre.get("supertrend_state", ""),
            "result_status": source_note.get("result_status", ""),
            "external_note": source_note.get("external_note", ""),
            "source_trail": source_note.get("source_trail", ""),
            "research_action": source_note.get("research_action", policy.get("next_action", "")),
            "blockers": blockers,
        }
        row["action_bucket"] = action_bucket(row)
        rows.append(row)

    rows.sort(key=lambda r: (float(r["readiness_overlay_100"]), float(fnum(r["policy_score_100"]) or 0)), reverse=True)
    return rows


def write_csv(rows: list[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_market_rows() -> list[dict[str, Any]]:
    return [index_snapshot(name) for name in INDEXES]


def md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for title, _ in columns) + " |"]
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows:
        values = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                value = fmt(value, 2)
            values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_markdown(rows: list[dict[str, Any]], market_rows: list[dict[str, Any]]) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    market_table = []
    for m in market_rows:
        market_table.append(
            {
                "index": m.get("index") or m.get("label", ""),
                "as_of": m.get("as_of", ""),
                "close": fmt(m.get("close")),
                "chg_pct": fmt_pct(m.get("chg_pct")),
                "trend_10d": fmt_pct((m.get("trend_10d") or {}).get("chg_pct")),
                "52w_high": fmt(m.get("52w_high")),
            }
        )
    rank_rows = []
    for row in rows:
        rank_rows.append(
            {
                "symbol": row["symbol"],
                "company": row["company"],
                "policy": fmt(row["policy_score_100"], 1),
                "readiness": fmt(row["readiness_overlay_100"], 1),
                "setup": row["local_stage_signal"],
                "rsi": fmt(row["rsi"], 1),
                "rs": fmt(row["relative_strength"], 2),
                "latest": fmt(row["latest_price"], 2),
                "trigger": row["trigger_state"],
                "action": row["action_bucket"],
            }
        )

    lines = [
        f"# Smallcap Portfolio Research Update - {RUN_DATE_DISPLAY}",
        "",
        "Portfolio: Agent Adda Small Cap Portfolio",
        "Status: Research continuation, no paper order",
        f"Generated: {generated}",
        "",
        "## Executive View",
        "",
        "The research should continue, but the portfolio should not create a paper order from this update.",
        "Smallcap indices are still near their 52-week highs, so the opportunity set is active but entry risk is elevated.",
        "The best next work is evidence extraction and trigger discipline, not forced deployment.",
        "",
        "Immediate priority:",
        "",
        "1. Build the GLAND Q1 FY27 evidence pack only after the 2026-08-10 board/result event is published and downloadable.",
        "2. Run direct exchange searches for RUBICON and review its July corporate actions before any score upgrade.",
        "3. Treat SKYGOLD's breakout as blocked because Q1 result and cash-conversion review are still pending.",
        "4. Keep CPPLUS on watch until the June-quarter result event and the local Supertrend conflict clear.",
        "5. Keep SANSERA and RRKABEL retest-only because the setup is extended.",
        "",
        "## Market Regime",
        "",
        md_table(market_table, [("Index", "index"), ("As Of", "as_of"), ("Close", "close"), ("Day Chg", "chg_pct"), ("10D Chg", "trend_10d"), ("52W High", "52w_high")]),
        "",
        "Interpretation: smallcap breadth is constructive but mature. Smallcap 50 and Smallcap 250 are near 52-week highs, while NIFTY AUTO and NIFTY IT are current leadership pockets. This supports watchlist preparation, but not chasing extended smallcap moves.",
        "",
        "## Ranked Research Sheet",
        "",
        "The readiness overlay starts with the policy score and applies penalties for stale results, pending governance, no-chase flags, bearish Supertrend, negative operating cash flow, and working-capital leverage. It is a research-priority score, not a buy signal.",
        "",
        md_table(rank_rows, [("Symbol", "symbol"), ("Company", "company"), ("Policy", "policy"), ("Readiness", "readiness"), ("Setup", "setup"), ("RSI", "rsi"), ("RS", "rs"), ("Latest", "latest"), ("Trigger", "trigger"), ("Action", "action")]),
        "",
        "## Stock Notes",
        "",
    ]

    for row in rows:
        lines.extend(
            [
                f"### {row['symbol']} - {row['company']}",
                "",
                f"- Current action: {row['action_bucket']}",
                f"- Policy score / readiness overlay: {fmt(row['policy_score_100'], 1)} / {fmt(row['readiness_overlay_100'], 1)}",
                f"- Technical: {row['local_stage_signal']}; RSI {fmt(row['rsi'], 1)}; relative strength {fmt(row['relative_strength'], 2)}; Supertrend {row['supertrend_state'] or 'NA'}",
                f"- Latest quote: Rs. {fmt(row['latest_price'], 2)} ({fmt_pct(row['latest_pct_change'])}); quote as of {row['quote_as_of']}",
                f"- Trigger map: breakout Rs. {fmt(row['breakout_level'])}; retest Rs. {fmt(row['retest_level'])}; stop Rs. {fmt(row['initial_stop'])}; 2R target Rs. {fmt(row['target_2r'])}",
                f"- Financial cache: {row['latest_quarter']}; {row['financial_freshness']}; audit {row['audit_outcome'] or 'NA'}",
                f"- Fundamentals snapshot: annual revenue Rs. {fmt(row['annual_revenue_cr'])} crore; annual PAT Rs. {fmt(row['annual_pat_cr'])} crore; OCF Rs. {fmt(row['operating_cash_flow_cr'])} crore; D/E {fmt(row['debt_to_equity'], 2)}",
                f"- External status: {row['result_status']}",
                f"- Research note: {row['external_note']}",
                f"- Next work: {row['research_action']}",
                f"- Source trail: {row['source_trail']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Portfolio Strategy Implication",
            "",
            "The portfolio remains a paper/model portfolio with a Rs. 5,00,000 reference corpus. Phase 1 should stay below the policy exposure cap and use small initial slots only after evidence, governance, trigger, and stop-risk gates clear.",
            "",
            "Selection priority is now split into two lanes:",
            "",
            "1. Evidence-pack lane: SYRMA, GLAND, RUBICON, SKYGOLD, CPPLUS.",
            "2. Retest-only lane: RRKABEL, RAINBOW, SANSERA, plus any name where RSI/20DMA distance says no chase.",
            "",
            "No paper order is authorized by this report. A future order needs a fresh official filing check, a trigger close or retest hold, volume confirmation, and portfolio-risk approval.",
            "",
            "Research-only. Not investment advice.",
        ]
    )
    return "\n".join(lines) + "\n"


def html_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    head = "".join(f"<th>{esc(title)}</th>" for title, _ in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{esc(row.get(key, ''))}</td>" for _, key in columns)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_html(rows: list[dict[str, Any]], market_rows: list[dict[str, Any]], md_text: str) -> str:
    market_render = [
        {
            "index": m.get("index") or m.get("label", ""),
            "as_of": m.get("as_of", ""),
            "close": fmt(m.get("close")),
            "chg_pct": fmt_pct(m.get("chg_pct")),
            "trend_10d": fmt_pct((m.get("trend_10d") or {}).get("chg_pct")),
            "52w_high": fmt(m.get("52w_high")),
        }
        for m in market_rows
    ]
    row_render = [
        {
            "symbol": r["symbol"],
            "company": r["company"],
            "policy": fmt(r["policy_score_100"], 1),
            "readiness": fmt(r["readiness_overlay_100"], 1),
            "setup": r["local_stage_signal"],
            "rsi": fmt(r["rsi"], 1),
            "rs": fmt(r["relative_strength"], 2),
            "latest": fmt(r["latest_price"], 2),
            "trigger": r["trigger_state"],
            "action": r["action_bucket"],
            "status": r["result_status"],
        }
        for r in rows
    ]
    cards = []
    for r in rows:
        cards.append(
            f"""
            <section class="stock">
              <div class="stock-head">
                <div><h3>{esc(r['symbol'])}</h3><p>{esc(r['company'])}</p></div>
                <span>{esc(r['action_bucket'])}</span>
              </div>
              <div class="metrics">
                <div><b>{fmt(r['policy_score_100'], 1)}</b><small>Policy</small></div>
                <div><b>{fmt(r['readiness_overlay_100'], 1)}</b><small>Readiness</small></div>
                <div><b>{fmt(r['rsi'], 1)}</b><small>RSI</small></div>
                <div><b>{fmt(r['relative_strength'], 2)}</b><small>Relative Strength</small></div>
              </div>
              <p><b>Technical:</b> {esc(r['local_stage_signal'])}; Supertrend {esc(r['supertrend_state'] or 'NA')}; trigger state {esc(r['trigger_state'])}.</p>
              <p><b>Levels:</b> breakout Rs. {fmt(r['breakout_level'])}; retest Rs. {fmt(r['retest_level'])}; stop Rs. {fmt(r['initial_stop'])}; 2R target Rs. {fmt(r['target_2r'])}.</p>
              <p><b>Financial cache:</b> {esc(r['latest_quarter'])}; {esc(r['financial_freshness'])}; audit {esc(r['audit_outcome'] or 'NA')}.</p>
              <p><b>External status:</b> {esc(r['result_status'])}</p>
              <p>{esc(r['external_note'])}</p>
              <p><b>Next work:</b> {esc(r['research_action'])}</p>
              <p class="source"><b>Source trail:</b> {esc(r['source_trail'])}</p>
            </section>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Adda Smallcap Portfolio Research Update - {esc(RUN_DATE_DISPLAY)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #172026; background: #f6f7f8; }}
    header {{ background: #17324d; color: #fff; padding: 28px 36px; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    header p {{ margin: 4px 0; color: #d7e1ea; }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 28px 20px 42px; }}
    section {{ margin: 22px 0; }}
    .notice {{ background: #fff7dd; border-left: 5px solid #c68600; padding: 14px 16px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; }}
    th, td {{ border: 1px solid #d9dee3; padding: 9px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #edf2f6; color: #25313b; }}
    .stock {{ background: #fff; border: 1px solid #d9dee3; border-radius: 8px; padding: 18px; }}
    .stock-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: start; border-bottom: 1px solid #e6eaee; padding-bottom: 10px; margin-bottom: 12px; }}
    .stock-head h3 {{ margin: 0; font-size: 20px; }}
    .stock-head p {{ margin: 3px 0 0; color: #52606d; }}
    .stock-head span {{ background: #eaf4ef; color: #14633d; border-radius: 999px; padding: 6px 10px; font-size: 12px; white-space: nowrap; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin: 10px 0 14px; }}
    .metrics div {{ background: #f5f7f9; padding: 10px; border-radius: 6px; }}
    .metrics b {{ display: block; font-size: 18px; }}
    .metrics small {{ color: #5a6875; }}
    .source {{ color: #52606d; font-size: 12px; }}
    pre {{ background: #fff; border: 1px solid #d9dee3; padding: 16px; overflow: auto; }}
    @media (max-width: 760px) {{ .metrics {{ grid-template-columns: repeat(2, 1fr); }} .stock-head {{ display: block; }} .stock-head span {{ display: inline-block; margin-top: 10px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Agent Adda Smallcap Portfolio Research Update</h1>
    <p>Run date: {esc(RUN_DATE_DISPLAY)} | Status: research continuation, no paper order</p>
    <p>Portfolio-first operating model using the existing smallcap policy gates.</p>
  </header>
  <main>
    <section class="notice">
      <b>Decision:</b> Continue research, but do not deploy. Several stocks are near or through mapped triggers while Q1 FY27 evidence and governance gates remain unresolved.
    </section>
    <section>
      <h2>Market Regime</h2>
      {html_table(market_render, [("Index", "index"), ("As Of", "as_of"), ("Close", "close"), ("Day Chg", "chg_pct"), ("10D Chg", "trend_10d"), ("52W High", "52w_high")])}
    </section>
    <section>
      <h2>Ranked Research Sheet</h2>
      {html_table(row_render, [("Symbol", "symbol"), ("Company", "company"), ("Policy", "policy"), ("Readiness", "readiness"), ("Setup", "setup"), ("RSI", "rsi"), ("RS", "rs"), ("Latest", "latest"), ("Trigger", "trigger"), ("Action", "action"), ("Result Status", "status")])}
    </section>
    <section>
      <h2>Stock Notes</h2>
      {''.join(cards)}
    </section>
    <section>
      <h2>Portfolio Strategy Implication</h2>
      <p>The portfolio remains a paper/model portfolio with a Rs. 5,00,000 reference corpus. Phase 1 should stay below the policy exposure cap and use small initial slots only after evidence, governance, trigger, and stop-risk gates clear.</p>
      <p>No paper order is authorized by this report. A future order needs a fresh official filing check, a trigger close or retest hold, volume confirmation, and portfolio-risk approval.</p>
    </section>
    <section>
      <h2>Markdown Source</h2>
      <pre>{esc(md_text)}</pre>
    </section>
  </main>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Agent Adda smallcap portfolio research update.")
    parser.add_argument("--run-date", default=DEFAULT_RUN_DATE, help="Run date in YYYYMMDD format. Defaults to today.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    configure_run_date(args.run_date)
    rows = build_rows()
    market_rows = build_market_rows()
    write_csv(rows)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md_text = clean_text(build_markdown(rows, market_rows))
    OUT_MD.write_text(md_text, encoding="utf-8")
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(clean_text(build_html(rows, market_rows, md_text)), encoding="utf-8")
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote {OUT_HTML.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
