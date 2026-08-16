#!/usr/bin/env python3
"""Build a combined fund/technical/RS/Stage 2 portfolio concentration report."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("reports/portfolio_assessments/equity_portfolio_assessment_20260815.csv")
DEFAULT_OUT_DIR = Path("reports/portfolio_assessments")

PROTECTED_SYMBOLS = {"ICICIBANK", "HDFCBANK"}
CORPORATE_ACTION_RECONCILE = {"UJJFIN", "IDFC", "TMLDVR", "TATSPO", "TATCO"}
ALIAS_VERIFY_FIRST = {"PONOXI", "DECBEA"}
EQUITY_ETF_OVERRIDES = {"SKYGOL", "SKYGOLD"}


def to_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def fmt_inr(value: Any) -> str:
    number = to_float(value, 0.0) or 0.0
    return f"Rs. {number:,.0f}"


def fmt_pct(value: Any) -> str:
    number = to_float(value)
    return "-" if number is None else f"{number:.2f}%"


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def stage_component(stage: str | None) -> tuple[float, bool]:
    stage_text = (stage or "").upper()
    if "STAGE_2" in stage_text or stage_text == "2":
        return 100.0, True
    if "STAGE_1" in stage_text or stage_text == "1":
        return 55.0, False
    if "STAGE_3" in stage_text or stage_text == "3":
        return 25.0, False
    if "STAGE_4" in stage_text or stage_text == "4":
        return 0.0, False
    return 30.0, False


def score_bucket(score: float) -> str:
    if score >= 75:
        return "A - ADD/HOLD QUALITY"
    if score >= 65:
        return "B - HOLD QUALITY"
    if score >= 55:
        return "C - REVIEW"
    return "D - SELL/REDUCE"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def row_symbol(row: dict[str, str]) -> str:
    return (row.get("nse_symbol") or row.get("broker_symbol") or "").strip().upper()


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def score_row(row: dict[str, str]) -> dict[str, Any]:
    fund_missing = not (row.get("enhanced_fund_score") or row.get("fundamental_score"))
    tech_missing = not row.get("technical_score")
    rs_missing = not row.get("relative_strength")
    fund = to_float(row.get("enhanced_fund_score"), to_float(row.get("fundamental_score"), 45.0)) or 45.0
    tech = to_float(row.get("technical_score"), 40.0) or 40.0
    rs_raw = to_float(row.get("relative_strength"))
    rs_component = 35.0 if rs_raw is None else clamp(50.0 + rs_raw)
    stage_points, is_stage2 = stage_component(row.get("stage"))
    combined = (fund * 0.35) + (tech * 0.30) + (rs_component * 0.20) + (stage_points * 0.15)

    flags: list[str] = []
    if fund_missing:
        flags.append("missing fund score")
    if tech_missing:
        flags.append("missing tech score")
    if rs_missing:
        flags.append("missing RS")
    if not row.get("stage"):
        flags.append("missing stage")

    return {
        "fund_component": round(fund, 2),
        "tech_component": round(tech, 2),
        "rs_raw": "" if rs_raw is None else round(rs_raw, 2),
        "rs_component": round(rs_component, 2),
        "stage_component": round(stage_points, 2),
        "is_stage2": "Y" if is_stage2 else "N",
        "combined_score": round(combined, 2),
        "score_bucket": score_bucket(combined),
        "score_data_flags": "; ".join(flags),
    }


def assessment_group(row: dict[str, str]) -> str:
    broker = (row.get("broker_symbol") or "").strip().upper()
    symbol = (row.get("nse_symbol") or "").strip().upper()
    if is_true(row.get("is_etf_like")) and broker not in EQUITY_ETF_OVERRIDES and symbol not in EQUITY_ETF_OVERRIDES:
        return "ETF_SEPARATE"
    if broker in CORPORATE_ACTION_RECONCILE:
        return "RECONCILE_FIRST"
    if broker in ALIAS_VERIFY_FIRST:
        return "VERIFY_ALIAS_FIRST"
    if not row.get("nse_symbol"):
        return "UNRESOLVED_MANUAL"
    return "SCORE_ELIGIBLE"


def action_for(row: dict[str, Any], selected: bool, raw_top: bool) -> tuple[str, str]:
    symbol = row_symbol(row)
    score = to_float(row.get("combined_score"), 0.0) or 0.0
    value = to_float(row.get("value_at_market"), 0.0) or 0.0
    weight = to_float(row.get("portfolio_weight_pct"), 0.0) or 0.0
    stage = str(row.get("stage") or "").upper()
    is_stage2 = row.get("is_stage2") == "Y"
    fund = to_float(row.get("fund_component"), 0.0) or 0.0

    if row.get("assessment_group") == "ETF_SEPARATE":
        return "ETF - SIZE BY ASSET ALLOCATION", "ETF exposure kept outside the 40-stock equity core."
    if row.get("assessment_group") == "RECONCILE_FIRST":
        return "RECONCILE FIRST", "Old/corporate-action style row; verify demat/broker mapping before any order."
    if row.get("assessment_group") == "VERIFY_ALIAS_FIRST":
        return "VERIFY ALIAS FIRST", "Broker symbol needs current listing/alias confirmation before any order."
    if row.get("assessment_group") == "UNRESOLVED_MANUAL":
        return "MANUAL REVIEW", "No current NSE symbol in local assessment."

    if selected and symbol in PROTECTED_SYMBOLS:
        if "STAGE_4" in stage:
            return "PROTECTED HOLD - SCORE SAYS REDUCE", "Kept only because of the earlier bank exclusion; combined score is weak."
        return "PROTECTED HOLD", "Kept because of the earlier bank exclusion."
    if selected and score >= 75 and is_stage2 and value < 50_000:
        return "ADD / SCALE ON PULLBACK", "High combined score and Stage 2, but the current line is too small to matter."
    if selected and score >= 75 and is_stage2:
        return "HOLD / ADD ON PULLBACK", "High combined score with Stage 2 support."
    if selected and is_stage2:
        return "HOLD CORE", "Stage 2 supported core holding under the combined model."
    if selected:
        return "HOLD CORE - NON STAGE 2", "Kept by fund/tech/RS score despite not being Stage 2."
    if raw_top:
        return "SCORE TOP 40 - DISPLACED BY PROTECTED BANK", "Would be in raw score top 40 without the protected-bank constraint."
    if is_stage2 and score >= 65:
        return "WATCH / STRICT-40 SELL", "Stage 2 is acceptable, but it falls outside the protected 40-stock core."
    if fund >= 70 and score >= 55:
        return "MANUAL CHALLENGE BEFORE SELL", "Fund score is strong enough to review before clearing."
    if score < 55:
        return "SELL / REDUCE", "Combined fund/tech/RS/Stage score is weak."
    if weight < 0.25:
        return "TAIL CLEANUP", "Low portfolio weight and not in the 40-stock core."
    return "SELL / REDUCE FOR STRICT 40", "Outside the 40-stock core under the combined model."


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int | None = None) -> str:
    selected = rows if limit is None else rows[:limit]
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        values = []
        for _, key in columns:
            value = row.get(key, "")
            if key in {"value_at_market"}:
                value = fmt_inr(value)
            elif key in {"unrealized_pl_pct"}:
                value = fmt_pct(value)
            elif key in {"combined_score", "fund_component", "tech_component", "rs_raw", "stage_component"}:
                number = to_float(value)
                value = "-" if number is None else f"{number:.1f}"
            values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    if limit is not None and len(rows) > limit:
        lines.append(f"| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |")
    return "\n".join(lines)


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    core = payload["core"]
    sells = payload["sells"]
    full_rows = payload["rows"]
    score_top_displaced = payload["score_top_displaced"]
    stage2_outside = payload["stage2_outside"]
    challenge = payload["challenge"]
    reconcile = payload["reconcile"]
    etfs = payload["etfs"]
    summary = payload["summary"]

    core_cols = [
        ("Rank", "core_rank"),
        ("Broker", "broker_symbol"),
        ("NSE", "nse_symbol"),
        ("Company", "company_name"),
        ("Value", "value_at_market"),
        ("Score", "combined_score"),
        ("Fund", "fund_component"),
        ("Tech", "tech_component"),
        ("RS", "rs_raw"),
        ("Stage", "stage"),
        ("Action", "combined_action"),
    ]
    sell_cols = [
        ("Broker", "broker_symbol"),
        ("NSE", "nse_symbol"),
        ("Company", "company_name"),
        ("Value", "value_at_market"),
        ("P/L", "unrealized_pl_pct"),
        ("Score", "combined_score"),
        ("Fund", "fund_component"),
        ("Tech", "tech_component"),
        ("RS", "rs_raw"),
        ("Stage", "stage"),
        ("Action", "combined_action"),
    ]

    parts = [
        "# Portfolio Combined Score Assessment - Fund + Tech + RS + Stage 2",
        "",
        f"Generated from `{summary['input_file']}` on {summary['generated_at']}. Local score/EOD boundary: stage snapshot/EOD fields embedded in the source assessment, mainly through {summary['max_eod_date']}.",
        "",
        "Research-only. Verify live prices, liquidity, tax impact, corporate actions, and broker symbol mapping before placing any order.",
        "",
        "## Scoring Method",
        "",
        "Combined score = 35% fund score + 30% technical score + 20% RS component + 15% stage component.",
        "",
        "- Fund score: `enhanced_fund_score`, falling back to `fundamental_score`; missing score uses neutral 45 and is flagged.",
        "- Technical score: local `technical_score`; missing score uses neutral 40 and is flagged.",
        "- RS component: `50 + relative_strength`, clamped to 0-100; negative RS hurts the score.",
        "- Stage component: Stage 2 = 100, Stage 1 = 55, Stage 3 = 25, Stage 4 = 0, unknown/missing = 30.",
        "",
        "## Summary",
        "",
        f"- Total portfolio rows: **{summary['total_rows']}** / market value **{fmt_inr(summary['total_market_value'])}**",
        f"- Score-eligible equity rows: **{summary['score_eligible_rows']}**",
        f"- Protected-bank core view: **{len(core)} stocks**",
        f"- Strict-40 sell/reduce equity rows: **{len(sells)}** / estimated value **{fmt_inr(summary['sell_value'])}**",
        f"- Stage 2 names inside protected core: **{summary['stage2_core_count']}**",
        f"- Stage 2 names outside protected core: **{len(stage2_outside)}** / estimated value **{fmt_inr(summary['stage2_outside_value'])}**",
        f"- ETFs handled separately: **{len(etfs)}** / **{fmt_inr(summary['etf_value'])}**",
        f"- Reconcile/alias/manual rows: **{len(reconcile)}** / **{fmt_inr(summary['reconcile_value'])}**",
        "",
        "Assumption retained from the prior cash-raise instruction: `ICICIBANK` and `HDFCBANK` are protected from direct sell. `HDFCBANK` remains a protected hold only; the combined score itself says reduce because it is Stage 4 with weak technical/RS support.",
        "",
        "## Core 40 - Protected Bank View",
        "",
        md_table(core, core_cols),
    ]

    if score_top_displaced:
        parts.extend(
            [
                "",
                "## Raw Score Top 40 Displaced By Protected Banks",
                "",
                "These would be in the raw score-led top 40 if ICICI Bank/HDFC Bank were not forced into the core.",
                "",
                md_table(score_top_displaced, sell_cols),
            ]
        )

    add_scale = [
        row
        for row in core
        if row.get("combined_action") in {"ADD / SCALE ON PULLBACK", "HOLD / ADD ON PULLBACK"}
    ]
    if add_scale:
        parts.extend(
            [
                "",
                "## Add / Scale Candidates",
                "",
                "These are score-led Stage 2 names. For very small current lines, the practical choice is either scale deliberately on a valid pullback or clear the tail; keeping a tiny token line does not help concentration.",
                "",
                md_table(add_scale, sell_cols),
            ]
        )

    parts.extend(
        [
            "",
            "## Sell / Reduce For Strict 40",
            "",
            "Full list is in the CSV. The table below is sorted by value so the capital impact is visible first.",
            "",
            md_table(sells, sell_cols, limit=80),
        ]
    )

    if challenge:
        parts.extend(
            [
                "",
                "## Manual Challenge Before Sell",
                "",
                "These fall outside the protected 40-stock core, but the fund score is strong enough that they should get a final thesis check before clearing.",
                "",
                md_table(challenge, sell_cols, limit=40),
            ]
        )

    if stage2_outside:
        parts.extend(
            [
                "",
                "## Stage 2 Outside Core",
                "",
                "These have Stage 2 support but did not survive the protected 40-stock concentration cut. Treat them as watch/scale-or-clear, not as weak technical exits.",
                "",
                md_table(stage2_outside, sell_cols, limit=40),
            ]
        )

    if reconcile:
        parts.extend(
            [
                "",
                "## Reconcile / Verify First",
                "",
                "Do not direct-sell these from the model output. Reconcile corporate-action, alias, BSE-only, or unresolved mappings first.",
                "",
                md_table(reconcile, sell_cols, limit=80),
            ]
        )

    if etfs:
        parts.extend(
            [
                "",
                "## ETFs Separate",
                "",
                "ETF rows are outside the stock-count target. Keep or trim them by asset-allocation policy rather than the equity-stock score.",
                "",
                md_table(etfs, sell_cols, limit=80),
            ]
        )

    parts.extend(
        [
            "",
            "## Output Files",
            "",
            f"- Full scored table: `{summary['full_csv']}`",
            f"- Core 40 table: `{summary['core_csv']}`",
            f"- Sell/reduce table: `{summary['sell_csv']}`",
        ]
    )
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def build(args: argparse.Namespace) -> dict[str, Any]:
    rows = load_rows(args.input)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        scored = {**row, **score_row(row)}
        scored["assessment_group"] = assessment_group(row)
        enriched.append(scored)

    score_eligible = [row for row in enriched if row["assessment_group"] == "SCORE_ELIGIBLE"]
    score_eligible.sort(
        key=lambda row: (
            to_float(row.get("combined_score"), 0.0) or 0.0,
            to_float(row.get("value_at_market"), 0.0) or 0.0,
        ),
        reverse=True,
    )

    for idx, row in enumerate(score_eligible, start=1):
        row["combined_rank"] = idx

    raw_top = score_eligible[: args.core_size]
    raw_top_keys = {row.get("broker_symbol") for row in raw_top}
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    for row in score_eligible:
        if row_symbol(row) in PROTECTED_SYMBOLS:
            selected.append(row)
            selected_keys.add(row.get("broker_symbol", ""))
    for row in score_eligible:
        if len(selected) >= args.core_size:
            break
        key = row.get("broker_symbol", "")
        if key in selected_keys:
            continue
        selected.append(row)
        selected_keys.add(key)
    selected.sort(
        key=lambda row: (
            to_float(row.get("combined_score"), 0.0) or 0.0,
            to_float(row.get("value_at_market"), 0.0) or 0.0,
        ),
        reverse=True,
    )
    selected_keys = {row.get("broker_symbol") for row in selected}

    for idx, row in enumerate(selected, start=1):
        row["core_rank"] = idx

    for row in enriched:
        selected_flag = row.get("broker_symbol") in selected_keys
        raw_top_flag = row.get("broker_symbol") in raw_top_keys
        action, note = action_for(row, selected_flag, raw_top_flag)
        row["combined_action"] = action
        row["combined_action_reason"] = note
        if selected_flag:
            row["core_rank"] = next((r["core_rank"] for r in selected if r.get("broker_symbol") == row.get("broker_symbol")), "")
        else:
            row["core_rank"] = ""

    sells = [
        row
        for row in score_eligible
        if row.get("broker_symbol") not in selected_keys
    ]
    sells.sort(key=lambda row: to_float(row.get("value_at_market"), 0.0) or 0.0, reverse=True)
    score_top_displaced = [row for row in sells if row.get("broker_symbol") in raw_top_keys]
    stage2_outside = [
        row
        for row in sells
        if row.get("is_stage2") == "Y" and (to_float(row.get("combined_score"), 0.0) or 0.0) >= 60.0
    ]
    stage2_outside.sort(key=lambda row: to_float(row.get("combined_score"), 0.0) or 0.0, reverse=True)
    challenge = [
        row
        for row in sells
        if (to_float(row.get("fund_component"), 0.0) or 0.0) >= 70.0
        and (to_float(row.get("combined_score"), 0.0) or 0.0) >= 55.0
    ]
    challenge.sort(key=lambda row: to_float(row.get("combined_score"), 0.0) or 0.0, reverse=True)
    reconcile = [row for row in enriched if row["assessment_group"] in {"RECONCILE_FIRST", "VERIFY_ALIAS_FIRST", "UNRESOLVED_MANUAL"}]
    reconcile.sort(key=lambda row: to_float(row.get("value_at_market"), 0.0) or 0.0, reverse=True)
    etfs = [row for row in enriched if row["assessment_group"] == "ETF_SEPARATE"]
    etfs.sort(key=lambda row: to_float(row.get("value_at_market"), 0.0) or 0.0, reverse=True)

    return {
        "rows": enriched,
        "core": selected,
        "sells": sells,
        "score_top_displaced": score_top_displaced,
        "stage2_outside": stage2_outside,
        "challenge": challenge,
        "reconcile": reconcile,
        "etfs": etfs,
        "summary": {
            "input_file": str(args.input),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_rows": len(enriched),
            "score_eligible_rows": len(score_eligible),
            "total_market_value": sum(to_float(row.get("value_at_market"), 0.0) or 0.0 for row in enriched),
            "sell_value": sum(to_float(row.get("value_at_market"), 0.0) or 0.0 for row in sells),
            "stage2_core_count": sum(1 for row in selected if row.get("is_stage2") == "Y"),
            "stage2_outside_value": sum(to_float(row.get("value_at_market"), 0.0) or 0.0 for row in stage2_outside),
            "reconcile_value": sum(to_float(row.get("value_at_market"), 0.0) or 0.0 for row in reconcile),
            "etf_value": sum(to_float(row.get("value_at_market"), 0.0) or 0.0 for row in etfs),
            "max_eod_date": max((row.get("eod_trade_date") or "" for row in enriched), default=""),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--core-size", type=int, default=40)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    payload = build(args)

    stem = f"portfolio_combined_score_stage2_{args.as_of}"
    full_csv = args.out_dir / f"{stem}.csv"
    core_csv = args.out_dir / f"{stem}_core40.csv"
    sell_csv = args.out_dir / f"{stem}_sell_reduce.csv"
    md_path = args.out_dir / f"{stem}.md"

    base_columns = list(payload["rows"][0].keys()) if payload["rows"] else []
    preferred = [
        "combined_rank",
        "core_rank",
        "assessment_group",
        "combined_action",
        "combined_action_reason",
        "combined_score",
        "score_bucket",
        "fund_component",
        "tech_component",
        "rs_raw",
        "rs_component",
        "stage_component",
        "is_stage2",
        "score_data_flags",
    ]
    columns = preferred + [col for col in base_columns if col not in preferred]
    write_csv(full_csv, payload["rows"], columns)
    write_csv(core_csv, payload["core"], columns)
    write_csv(sell_csv, payload["sells"], columns)

    payload["summary"].update(
        {
            "full_csv": str(full_csv),
            "core_csv": str(core_csv),
            "sell_csv": str(sell_csv),
        }
    )
    write_markdown(md_path, payload)
    print(
        f"wrote {md_path}\n"
        f"wrote {full_csv}\n"
        f"wrote {core_csv}\n"
        f"wrote {sell_csv}"
    )


if __name__ == "__main__":
    main()
