from __future__ import annotations

import csv
import html
import math
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal.financials_cache import read_financials
from terminal.tools import get_symbol_snapshot

INPUT = ROOT / "Mutual Funds" / "extracted" / "smallcap_common_holdings_including_agent_adda_20260806.csv"
SETUPS = ROOT / "reports" / "signal_effectiveness" / "stock_best_setups_20260621_215334.csv"
OUT_CSV = ROOT / "Mutual Funds" / "extracted" / "agent_adda_smallcap_preselection_scores_20260806.csv"
OUT_HTML = ROOT / "Mutual Funds" / "reports" / "agent_adda_smallcap_preselection_scored_report_20260806.html"


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
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


def fmt_num(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}"


def fmt_pct(value: Any, digits: int = 1) -> str:
    number = fnum(value)
    if number is None:
        return ""
    return f"{number:+.{digits}f}%"


def pct_change(new: Any, old: Any) -> float | None:
    n = fnum(new)
    o = fnum(old)
    if n is None or o in (None, 0):
        return None
    return (n / o - 1) * 100


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def normalize_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def latest_by_period(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows or [], key=lambda r: normalize_date(r.get("period_end")), reverse=True)


def find_year_ago(rows: list[dict[str, Any]], latest: dict[str, Any]) -> dict[str, Any] | None:
    latest_end = latest.get("period_end")
    if not hasattr(latest_end, "year"):
        return None
    target_year = latest_end.year - 1
    target_month = latest_end.month
    for row in rows:
        period_end = row.get("period_end")
        if hasattr(period_end, "year") and period_end.year == target_year and period_end.month == target_month:
            return row
    return None


def stage_points(stage: str) -> float:
    return {
        "STAGE_2": 6.0,
        "STAGE_1": 2.0,
        "STAGE_3": 1.0,
        "STAGE_4": 0.0,
    }.get(str(stage or "").upper(), 1.0)


def rsi_points(rsi: Any) -> float:
    r = fnum(rsi)
    if r is None:
        return 1.0
    if 50 <= r <= 70:
        return 4.0
    if 40 <= r < 50 or 70 < r <= 75:
        return 3.0
    if 35 <= r < 40 or 75 < r <= 80:
        return 1.5
    return 0.5


def rs_points(rs: Any) -> float:
    v = fnum(rs)
    if v is None:
        return 1.0
    if v >= 40:
        return 4.0
    if v >= 25:
        return 3.5
    if v >= 15:
        return 2.5
    if v >= 5:
        return 1.5
    if v >= 0:
        return 0.8
    return 0.0


def signal_points(signal: str, supertrend: str) -> float:
    sig = str(signal or "").upper()
    st = str(supertrend or "").upper()
    score = 0.0
    if sig == "BUY":
        score += 3.0
    elif sig == "HOLD":
        score += 1.8
    if st == "BULLISH":
        score += 1.0
    elif st == "BEARISH":
        score -= 0.7
    return clamp(score, 0.0, 4.0)


def technical_score(snapshot: dict[str, Any]) -> float:
    raw = fnum(snapshot.get("technical_score"))
    return round(
        clamp((raw or 0) * 0.12, 0, 12)
        + stage_points(str(snapshot.get("stage") or ""))
        + signal_points(str(snapshot.get("trading_signal") or ""), str(snapshot.get("supertrend_state") or ""))
        + rsi_points(snapshot.get("rsi"))
        + rs_points(snapshot.get("relative_strength")),
        1,
    )


def growth_points(*values: float | None) -> float:
    points = 0.0
    for value in values:
        if value is None:
            continue
        if value >= 50:
            points += 2.0
        elif value >= 25:
            points += 1.6
        elif value >= 12:
            points += 1.1
        elif value >= 0:
            points += 0.5
        else:
            points -= 0.5
    return clamp(points, 0, 8)


def margin_points(opm: Any, opm_yoy_delta: float | None) -> float:
    opm_v = fnum(opm)
    points = 0.0
    if opm_v is None:
        points = 1.0
    elif opm_v >= 18:
        points = 4.0
    elif opm_v >= 12:
        points = 3.0
    elif opm_v >= 8:
        points = 2.0
    elif opm_v >= 4:
        points = 1.0
    if opm_yoy_delta is not None:
        if opm_yoy_delta >= 2:
            points += 1.0
        elif opm_yoy_delta < -2:
            points -= 1.0
    return clamp(points, 0, 5)


def debt_points(debt_to_equity: float | None, sector: str) -> float:
    if str(sector or "").lower() in {"banks", "finance"}:
        return 2.0
    if debt_to_equity is None:
        return 1.0
    if debt_to_equity <= 0.25:
        return 3.0
    if debt_to_equity <= 0.75:
        return 2.2
    if debt_to_equity <= 1.5:
        return 1.0
    return 0.0


def cashflow_points(operating_cf: Any, annual_pat: Any, sector: str) -> float:
    if str(sector or "").lower() in {"banks", "finance"}:
        return 1.5
    ocf = fnum(operating_cf)
    pat = fnum(annual_pat)
    if ocf is None:
        return 0.8
    if ocf <= 0:
        return 0.0
    if pat not in (None, 0) and ocf >= pat:
        return 2.0
    return 1.0


def freshness_points(latest_q: dict[str, Any] | None, newest_fetched_at: Any) -> tuple[float, str]:
    label = str((latest_q or {}).get("period_label") or "")
    fetched = normalize_date(newest_fetched_at)
    if "Jun 2026" in label:
        return 2.0, f"fresh result: {label}; fetched {fetched}"
    if "Mar 2026" in label:
        return 1.0, f"needs Q1 FY27 refresh: latest cached quarter {label}; fetched {fetched}"
    if label:
        return 0.3, f"stale financial cache: latest cached quarter {label}; fetched {fetched}"
    return 0.0, "no financial cache"


def compute_financial_metrics(symbol: str, sector: str) -> dict[str, Any]:
    fin = read_financials(symbol)
    quarters = latest_by_period(fin.get("quarterly") or [])
    annual = latest_by_period(fin.get("annual") or [])
    balance = latest_by_period(fin.get("balance_sheet") or [])
    cashflow = latest_by_period(fin.get("cash_flow") or [])

    latest_q = quarters[0] if quarters else None
    prev_q = quarters[1] if len(quarters) > 1 else None
    yoy_q = find_year_ago(quarters, latest_q) if latest_q else None
    latest_a = annual[0] if annual else None
    prev_a = annual[1] if len(annual) > 1 else None
    latest_bs = balance[0] if balance else None
    latest_cf = cashflow[0] if cashflow else None

    q_revenue_yoy = pct_change((latest_q or {}).get("revenue"), (yoy_q or {}).get("revenue"))
    q_pat_yoy = pct_change((latest_q or {}).get("pat"), (yoy_q or {}).get("pat"))
    q_eps_yoy = pct_change((latest_q or {}).get("eps"), (yoy_q or {}).get("eps"))
    q_revenue_qoq = pct_change((latest_q or {}).get("revenue"), (prev_q or {}).get("revenue"))
    q_pat_qoq = pct_change((latest_q or {}).get("pat"), (prev_q or {}).get("pat"))
    q_eps_qoq = pct_change((latest_q or {}).get("eps"), (prev_q or {}).get("eps"))
    annual_revenue_yoy = pct_change((latest_a or {}).get("revenue"), (prev_a or {}).get("revenue"))
    annual_pat_yoy = pct_change((latest_a or {}).get("pat"), (prev_a or {}).get("pat"))
    annual_eps_yoy = pct_change((latest_a or {}).get("eps"), (prev_a or {}).get("eps"))
    opm_delta = None
    if latest_q and yoy_q:
        latest_opm = fnum(latest_q.get("opm_pct"))
        yoy_opm = fnum(yoy_q.get("opm_pct"))
        if latest_opm is not None and yoy_opm is not None:
            opm_delta = latest_opm - yoy_opm

    debt_to_equity = None
    if latest_bs:
        borrowings = fnum(latest_bs.get("borrowings"))
        equity = fnum(latest_bs.get("equity_capital"))
        reserves = fnum(latest_bs.get("reserves"))
        denominator = (equity or 0) + (reserves or 0)
        if borrowings is not None and denominator:
            debt_to_equity = borrowings / denominator

    newest_fetched_at = None
    for section in fin.values():
        for row in section or []:
            fetched_at = row.get("fetched_at")
            if fetched_at and (newest_fetched_at is None or fetched_at > newest_fetched_at):
                newest_fetched_at = fetched_at

    fresh_points, freshness = freshness_points(latest_q, newest_fetched_at)
    return {
        "financial_rows": sum(len(fin.get(k) or []) for k in ("quarterly", "annual", "balance_sheet", "cash_flow")),
        "latest_quarter": (latest_q or {}).get("period_label", ""),
        "latest_quarter_revenue_cr": fnum((latest_q or {}).get("revenue")),
        "latest_quarter_pat_cr": fnum((latest_q or {}).get("pat")),
        "latest_quarter_eps": fnum((latest_q or {}).get("eps")),
        "latest_quarter_opm_pct": fnum((latest_q or {}).get("opm_pct")),
        "quarter_revenue_yoy_pct": q_revenue_yoy,
        "quarter_pat_yoy_pct": q_pat_yoy,
        "quarter_eps_yoy_pct": q_eps_yoy,
        "quarter_revenue_qoq_pct": q_revenue_qoq,
        "quarter_pat_qoq_pct": q_pat_qoq,
        "quarter_eps_qoq_pct": q_eps_qoq,
        "latest_annual": (latest_a or {}).get("period_label", ""),
        "annual_revenue_cr": fnum((latest_a or {}).get("revenue")),
        "annual_pat_cr": fnum((latest_a or {}).get("pat")),
        "annual_eps": fnum((latest_a or {}).get("eps")),
        "annual_opm_pct": fnum((latest_a or {}).get("opm_pct")),
        "annual_revenue_yoy_pct": annual_revenue_yoy,
        "annual_pat_yoy_pct": annual_pat_yoy,
        "annual_eps_yoy_pct": annual_eps_yoy,
        "opm_yoy_delta_pct": opm_delta,
        "debt_to_equity": debt_to_equity,
        "operating_cash_flow_cr": fnum((latest_cf or {}).get("operating_cf")),
        "financial_source_url": (latest_q or latest_a or {}).get("source_url", ""),
        "financial_cache_fetched_at": normalize_date(newest_fetched_at),
        "financial_freshness": freshness,
        "_freshness_points": fresh_points,
        "_growth_points": growth_points(q_revenue_yoy, q_pat_yoy, annual_revenue_yoy, annual_pat_yoy),
        "_margin_points": margin_points((latest_q or {}).get("opm_pct"), opm_delta),
        "_debt_points": debt_points(debt_to_equity, sector),
        "_cashflow_points": cashflow_points((latest_cf or {}).get("operating_cf"), (latest_a or {}).get("pat"), sector),
    }


def fundamental_score(row: pd.Series, snapshot: dict[str, Any], metrics: dict[str, Any]) -> float:
    base = fnum(snapshot.get("enhanced_fund_score")) or fnum(row.get("agent_adda_fund_score")) or 0
    score = clamp(base * 0.10, 0, 10)
    score += metrics["_growth_points"]
    score += metrics["_margin_points"]
    score += metrics["_debt_points"]
    score += metrics["_cashflow_points"]
    score += metrics["_freshness_points"]
    return round(clamp(score, 0, 30), 1)


def institutional_score(row: pd.Series) -> float:
    count = int(fnum(row.get("mutual_fund_count")) or 0)
    total_weight = fnum(row.get("total_reported_mf_weight_pct")) or fnum(row.get("avg_mf_weight_pct")) or 0
    if count >= 3:
        score = 20.0
    elif count == 2:
        score = 17.0
    elif count == 1:
        score = 9.0
    else:
        score = 0.0
    if total_weight >= 5:
        score += 5.0
    elif total_weight >= 3:
        score += 4.0
    elif total_weight >= 1.5:
        score += 3.0
    elif total_weight > 0:
        score += 1.5
    return round(clamp(score, 0, 25), 1)


def setup_map() -> dict[str, dict[str, Any]]:
    if not SETUPS.exists():
        return {}
    df = pd.read_csv(SETUPS)
    if df.empty:
        return {}
    df["rank_key"] = df["net_expectancy_r"].fillna(-99) + (df["trades"].fillna(0) / 100)
    out: dict[str, dict[str, Any]] = {}
    for symbol, part in df.groupby("symbol"):
        best = part.sort_values("rank_key", ascending=False).iloc[0]
        out[str(symbol).upper()] = best.to_dict()
    return out


def entry_score(row: pd.Series, snapshot: dict[str, Any], setup: dict[str, Any] | None) -> float:
    label = str(row.get("agent_adda_label") or "").upper()
    score = 0.0
    if "CORE" in label:
        score += 4.0
    elif "GROWTH" in label:
        score += 3.0
    elif "VERIFY" in label:
        score += 2.5
    elif "WATCH ONLY" in label:
        score += 2.0
    elif "EXTENDED" in label:
        score += 1.0
    else:
        score += 1.5

    stage = str(snapshot.get("stage") or "").upper()
    sig = str(snapshot.get("trading_signal") or "").upper()
    if stage == "STAGE_2" and sig == "BUY":
        score += 4.0
    elif stage == "STAGE_2" and sig == "HOLD":
        score += 2.5
    elif stage == "STAGE_1":
        score += 0.5

    r = fnum(snapshot.get("rsi"))
    if r is None:
        score += 1.0
    elif 50 <= r <= 70:
        score += 3.0
    elif 40 <= r < 50 or 70 < r <= 75:
        score += 2.0
    elif 35 <= r < 40 or 75 < r <= 80:
        score += 1.0

    one_day = fnum(snapshot.get("change_1d_pct"))
    if one_day is None or one_day > -3:
        score += 2.0
    elif one_day > -7:
        score += 1.0

    if setup:
        expectancy = fnum(setup.get("net_expectancy_r"))
        quality = str(setup.get("sample_quality") or "").lower()
        if expectancy is not None and expectancy >= 0.5:
            score += 2.0
        elif expectancy is not None and expectancy > 0:
            score += 1.0
        if quality == "medium":
            score += 0.5
    else:
        score += 0.8

    return round(clamp(score, 0, 15), 1)


def decision(row: dict[str, Any]) -> tuple[str, str]:
    stage = str(row["current_stage"] or "").upper()
    rsi = fnum(row["current_rsi"])
    one_day = fnum(row["change_1d_pct"])
    label = str(row["agent_adda_label"] or "").upper()
    score = fnum(row["selection_score_100"]) or 0
    tech = fnum(row["technical_score_30"]) or 0
    fund = fnum(row["fundamental_score_30"]) or 0
    entry = fnum(row["entry_risk_score_15"]) or 0
    freshness = str(row.get("financial_freshness") or "").lower()
    fresh_result = freshness.startswith("fresh result")

    if stage != "STAGE_2" or (one_day is not None and one_day <= -7) or (rsi is not None and rsi < 35):
        return "Reject / No Fresh Buy", "Trend/base failed current gate; revisit only after Stage 2 rebuild and support confirmation."
    if score >= 75 and tech >= 20 and fund >= 20 and entry >= 10 and "EXTENDED" not in label and fresh_result:
        return "Selection Review - Core Candidate", "Eligible for investment-committee review after final filing/news and liquidity checks."
    if score >= 68 and tech >= 19 and fund >= 18 and entry >= 8 and not (rsi is not None and rsi > 80) and fresh_result:
        return "Selection Review - Phased Candidate", "Use staggered entry only after final filing/news check and a fresh technical trigger."
    if score >= 68 and tech >= 19 and fund >= 18:
        return "Shortlist - Refresh Results", "Promising setup, but do not select until latest quarterly result and filing/news evidence are refreshed."
    if score >= 60 or "EXTENDED" in label:
        return "Watch - Retest / Verify", "Strong enough for watchlist, but wait for cleaner entry, updated filing evidence, or valuation reset."
    return "Hold / Reject", "Evidence is not strong enough for inclusion before fresher confirmation."


def strengths_and_risks(row: dict[str, Any]) -> tuple[str, str]:
    strengths: list[str] = []
    risks: list[str] = []
    if int(fnum(row["mutual_fund_count"]) or 0) >= 2:
        strengths.append("owned by two sampled small-cap funds")
    elif int(fnum(row["mutual_fund_count"]) or 0) == 1:
        strengths.append("overlaps one sampled small-cap fund")
    if (fnum(row["current_relative_strength"]) or 0) >= 25:
        strengths.append("high relative strength")
    if str(row["current_stage"]) == "STAGE_2":
        strengths.append("current Stage 2 trend")
    if (fnum(row["quarter_pat_yoy_pct"]) or 0) >= 25 or (fnum(row["annual_pat_yoy_pct"]) or 0) >= 25:
        strengths.append("profit growth evidence")
    if (fnum(row["latest_quarter_opm_pct"]) or 0) >= 15:
        strengths.append("healthy operating margin")

    rsi = fnum(row["current_rsi"])
    if rsi is not None and rsi >= 75:
        risks.append("extended RSI")
    if str(row["current_stage"]) != "STAGE_2":
        risks.append("not in current Stage 2")
    if (fnum(row["change_1d_pct"]) or 0) <= -3:
        risks.append("fresh price shock")
    if "needs Q1" in str(row["financial_freshness"]) or "stale" in str(row["financial_freshness"]):
        risks.append("fundamental refresh pending")
    if (fnum(row["fundamental_score_30"]) or 0) < 16:
        risks.append("fundamental score weak")
    if str(row.get("setup_sample_quality") or "") == "provisional":
        risks.append("setup backtest sample provisional")

    return "; ".join(strengths[:4]), "; ".join(risks[:4])


def build_rows() -> list[dict[str, Any]]:
    df = pd.read_csv(INPUT)
    candidates = df[df["agent_adda_match"].eq("Y")].copy()
    setup_by_symbol = setup_map()
    rows: list[dict[str, Any]] = []
    for _, record in candidates.iterrows():
        symbol = str(record["agent_adda_symbol"]).strip().upper()
        snapshot = get_symbol_snapshot(symbol)
        metrics = compute_financial_metrics(symbol, str(record.get("sector") or ""))
        setup = setup_by_symbol.get(symbol, {})
        tech_score = technical_score(snapshot)
        fund_score = fundamental_score(record, snapshot, metrics)
        inst_score = institutional_score(record)
        risk_score = entry_score(record, snapshot, setup)
        total_score = round(inst_score + tech_score + fund_score + risk_score, 1)
        out = {
            "symbol": symbol,
            "company": record.get("company", ""),
            "sector": record.get("sector", ""),
            "mutual_fund_count": int(fnum(record.get("mutual_fund_count")) or 0),
            "avg_mf_weight_pct": fnum(record.get("avg_mf_weight_pct")),
            "total_reported_mf_weight_pct": fnum(record.get("total_reported_mf_weight_pct")),
            "sources": record.get("sources", ""),
            "agent_adda_3m": record.get("agent_adda_3m", ""),
            "agent_adda_6m": record.get("agent_adda_6m", ""),
            "agent_adda_signal": record.get("agent_adda_signal", ""),
            "agent_adda_label": record.get("agent_adda_label", ""),
            "agent_adda_prior_tech_score": fnum(record.get("agent_adda_tech")),
            "agent_adda_prior_fund_score": fnum(record.get("agent_adda_fund_score")),
            "snapshot_date": snapshot.get("snapshot_date", ""),
            "current_price": fnum(snapshot.get("price")),
            "current_stage": snapshot.get("stage", ""),
            "current_stage_score": fnum(snapshot.get("stage_score")),
            "current_signal": snapshot.get("trading_signal", ""),
            "trend_signal": snapshot.get("trend_signal", ""),
            "supertrend_state": snapshot.get("supertrend_state", ""),
            "current_technical_score_raw": fnum(snapshot.get("technical_score")),
            "current_rsi": fnum(snapshot.get("rsi")),
            "current_relative_strength": fnum(snapshot.get("relative_strength")),
            "change_1d_pct": fnum(snapshot.get("change_1d_pct")),
            "change_1w_pct": fnum(snapshot.get("change_1w_pct")),
            "change_1m_pct": fnum(snapshot.get("change_1m_pct")),
            "snapshot_sector": snapshot.get("sector", ""),
            "snapshot_evidence_coverage": snapshot.get("evidence_coverage", ""),
            "snapshot_missing_evidence": "; ".join(snapshot.get("missing_evidence") or []),
            "institutional_score_25": inst_score,
            "technical_score_30": tech_score,
            "fundamental_score_30": fund_score,
            "entry_risk_score_15": risk_score,
            "selection_score_100": total_score,
            "best_setup": setup.get("setup", ""),
            "setup_trades": fnum(setup.get("trades")),
            "setup_win_rate_pct": fnum(setup.get("win_rate_pct")),
            "setup_net_expectancy_r": fnum(setup.get("net_expectancy_r")),
            "setup_sample_quality": setup.get("sample_quality", ""),
            **{k: v for k, v in metrics.items() if not k.startswith("_")},
        }
        bucket, stance = decision(out)
        out["decision_bucket"] = bucket
        out["preselection_stance"] = stance
        strengths, risks = strengths_and_risks(out)
        out["key_strengths"] = strengths
        out["key_risks"] = risks
        rows.append(out)
    return sorted(rows, key=lambda r: fnum(r["selection_score_100"]) or 0, reverse=True)


def write_csv(rows: list[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def css_class(bucket: str) -> str:
    b = bucket.lower()
    if b.startswith("selection review - core"):
        return "core"
    if b.startswith("selection review") or b.startswith("shortlist"):
        return "select"
    if b.startswith("watch"):
        return "watch"
    return "reject"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def score_bar(value: Any, total: float) -> str:
    v = fnum(value) or 0
    pct = clamp(v / total * 100, 0, 100)
    return f"<span class='bar'><span style='width:{pct:.0f}%'></span></span><b>{v:.1f}</b>"


def write_html(rows: list[dict[str, Any]]) -> None:
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    buckets = pd.Series([r["decision_bucket"] for r in rows]).value_counts().to_dict()
    top = rows[:10]
    cards = "\n".join(
        f"""
        <article class="candidate {css_class(r['decision_bucket'])}">
          <div class="candidate-head">
            <div>
              <h3>{esc(r['symbol'])}</h3>
              <p>{esc(r['company'])}</p>
            </div>
            <strong>{fmt_num(r['selection_score_100'])}</strong>
          </div>
          <dl>
            <div><dt>Decision</dt><dd>{esc(r['decision_bucket'])}</dd></div>
            <div><dt>Sector</dt><dd>{esc(r['sector'])}</dd></div>
            <div><dt>MF Backing</dt><dd>{esc(r['mutual_fund_count'])} funds / {fmt_num(r['total_reported_mf_weight_pct'])}%</dd></div>
            <div><dt>Current Setup</dt><dd>{esc(r['current_stage'])}, {esc(r['current_signal'])}, RSI {fmt_num(r['current_rsi'])}</dd></div>
            <div><dt>Freshness</dt><dd>{esc(r['financial_freshness'])}</dd></div>
          </dl>
          <p class="stance">{esc(r['preselection_stance'])}</p>
        </article>
        """
        for r in top
    )
    table_rows = "\n".join(
        f"""
        <tr>
          <td><b>{esc(r['symbol'])}</b><span>{esc(r['company'])}</span></td>
          <td>{esc(r['sector'])}</td>
          <td class="{css_class(r['decision_bucket'])}">{esc(r['decision_bucket'])}</td>
          <td>{score_bar(r['selection_score_100'], 100)}</td>
          <td>{score_bar(r['institutional_score_25'], 25)}</td>
          <td>{score_bar(r['technical_score_30'], 30)}</td>
          <td>{score_bar(r['fundamental_score_30'], 30)}</td>
          <td>{score_bar(r['entry_risk_score_15'], 15)}</td>
          <td>{esc(r['current_stage'])}<br><small>{esc(r['current_signal'])} / {esc(r['supertrend_state'])}</small></td>
          <td>{fmt_num(r['current_rsi'])}<br><small>RS {fmt_num(r['current_relative_strength'])}</small></td>
          <td>{fmt_pct(r['change_1d_pct'])}<br><small>1M {fmt_pct(r['change_1m_pct'])}</small></td>
          <td>{esc(r['latest_quarter'])}<br><small>Rev {fmt_num(r['latest_quarter_revenue_cr'])} cr / PAT {fmt_num(r['latest_quarter_pat_cr'])} cr</small></td>
          <td>{fmt_pct(r['quarter_revenue_yoy_pct'])}<br><small>PAT {fmt_pct(r['quarter_pat_yoy_pct'])}</small></td>
          <td>{fmt_num(r['latest_quarter_opm_pct'])}%<br><small>D/E {fmt_num(r['debt_to_equity'], 2)}</small></td>
          <td>{esc(r['key_strengths'])}</td>
          <td>{esc(r['key_risks'])}</td>
          <td>{esc(r['preselection_stance'])}</td>
        </tr>
        """
        for r in rows
    )
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Adda Small Cap Fund - Pre-Selection Scores</title>
  <style>
    :root {{
      --ink:#182026; --muted:#60707c; --line:#d8e0e5; --soft:#f5f7f8;
      --core:#0d6b52; --select:#28708a; --watch:#9a6a00; --reject:#9a332b;
      --band:#eef4f2; --paper:#ffffff;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; background:#fbfcfc; }}
    header {{ padding:28px 32px 18px; border-bottom:1px solid var(--line); background:var(--paper); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0; font-size:18px; letter-spacing:0; }}
    p {{ margin:0; color:var(--muted); }}
    main {{ padding:22px 32px 44px; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }}
    .pill {{ border:1px solid var(--line); background:var(--soft); border-radius:8px; padding:7px 10px; color:#34434c; }}
    .summary {{ display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:12px; margin:18px 0 8px; }}
    .metric {{ background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .metric b {{ display:block; font-size:24px; }}
    .metric span {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(260px,1fr)); gap:12px; }}
    .candidate {{ background:var(--paper); border:1px solid var(--line); border-left:5px solid var(--watch); border-radius:8px; padding:14px; }}
    .candidate.core {{ border-left-color:var(--core); }}
    .candidate.select {{ border-left-color:var(--select); }}
    .candidate.reject {{ border-left-color:var(--reject); }}
    .candidate-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }}
    .candidate-head strong {{ font-size:28px; }}
    dl {{ display:grid; grid-template-columns:repeat(2,minmax(120px,1fr)); gap:8px 12px; margin:12px 0; }}
    dt {{ color:var(--muted); font-size:12px; }}
    dd {{ margin:2px 0 0; }}
    .stance {{ color:#24323a; }}
    .method {{ display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:12px; }}
    .method div {{ background:var(--band); border:1px solid var(--line); border-radius:8px; padding:12px; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--paper); }}
    table {{ width:100%; border-collapse:collapse; min-width:1680px; }}
    th,td {{ padding:10px 9px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }}
    th {{ background:#eef2f4; position:sticky; top:0; z-index:1; font-size:12px; color:#30414b; }}
    td span, small {{ display:block; color:var(--muted); }}
    td.core {{ color:var(--core); font-weight:700; }}
    td.select {{ color:var(--select); font-weight:700; }}
    td.watch {{ color:var(--watch); font-weight:700; }}
    td.reject {{ color:var(--reject); font-weight:700; }}
    .bar {{ display:inline-block; width:62px; height:7px; background:#e1e7eb; border-radius:5px; overflow:hidden; margin-right:6px; vertical-align:middle; }}
    .bar span {{ display:block; height:100%; background:#2f7f72; }}
    footer {{ padding:18px 32px 30px; color:var(--muted); border-top:1px solid var(--line); background:var(--paper); }}
    @media (max-width: 900px) {{
      header, main, footer {{ padding-left:16px; padding-right:16px; }}
      .summary, .grid, .method {{ grid-template-columns:1fr; }}
      h1 {{ font-size:23px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Agent Adda Small Cap Fund - Pre-Selection Scores</h1>
    <p>Scored overlap universe across Agent Adda candidates and sampled small-cap mutual fund holdings before final portfolio selection.</p>
    <div class="meta">
      <span class="pill">Generated: {esc(generated)}</span>
      <span class="pill">Universe: {len(rows)} Agent Adda + mutual fund overlap stocks</span>
      <span class="pill">Technical snapshot: local Agent Adda stage snapshot dated 2026-08-06</span>
      <span class="pill">Research only; not investment advice</span>
    </div>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><b>{len(rows)}</b><span>Scored stocks</span></div>
      <div class="metric"><b>{buckets.get('Selection Review - Core Candidate', 0)}</b><span>Core review</span></div>
      <div class="metric"><b>{buckets.get('Selection Review - Phased Candidate', 0)}</b><span>Phased review</span></div>
      <div class="metric"><b>{buckets.get('Watch - Retest / Verify', 0)}</b><span>Watch / verify</span></div>
    </section>

    <h2>Top Ranked Candidates</h2>
    <section class="grid">{cards}</section>

    <h2>Scoring Method</h2>
    <section class="method">
      <div><b>Institutional 25</b><p>Mutual fund overlap count and reported combined fund weight.</p></div>
      <div><b>Technical 30</b><p>Current stage, raw technical score, signal, RSI, supertrend, and relative strength.</p></div>
      <div><b>Fundamental 30</b><p>Agent Adda/Screener cache score, sales/PAT growth, margin, leverage, cash flow, and result freshness.</p></div>
      <div><b>Entry Risk 15</b><p>Agent Adda watch label, current entry quality, RSI extension, price shock, and setup backtest quality.</p></div>
    </section>

    <h2>Full Scored Table</h2>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Stock</th><th>Sector</th><th>Decision</th><th>Total</th><th>Inst</th><th>Tech</th><th>Fund</th><th>Entry</th>
            <th>Stage</th><th>RSI / RS</th><th>Price Move</th><th>Latest Quarter</th><th>Q YoY</th><th>Margin / Debt</th>
            <th>Strengths</th><th>Risks</th><th>Pre-selection Stance</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </section>
  </main>
  <footer>
    Inputs: {esc(str(INPUT.relative_to(ROOT)))}, local stage snapshots, PostgreSQL financial cache, and setup-effectiveness file where available.
    Selection still requires final official filing/news verification, liquidity check, portfolio concentration limit, and entry trigger.
  </footer>
</body>
</html>
"""
    OUT_HTML.write_text(html_text, encoding="utf-8")


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_html(rows)
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_HTML}")
    print(pd.DataFrame(rows)[["symbol", "selection_score_100", "decision_bucket", "technical_score_30", "fundamental_score_30", "entry_risk_score_15"]].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
