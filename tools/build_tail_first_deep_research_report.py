#!/usr/bin/env python3
"""Build the tail-first / deep-research portfolio reduction report."""

from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "portfolio_assessments"
INPUT_CSV = REPORT_DIR / "equity_tail_first_and_remaining_deep_research_20260808.csv"
OUTPUT_MD = REPORT_DIR / "equity_tail_first_and_remaining_deep_research_20260808.md"
OUTPUT_HTML = REPORT_DIR / "equity_tail_first_and_remaining_deep_research_20260808.html"
OUTPUT_JSON = REPORT_DIR / "equity_tail_first_and_remaining_deep_research_20260808.json"
ASSESSMENT_CSV = REPORT_DIR / "equity_portfolio_assessment_20260808.csv"
ASSESSMENT_JSON = REPORT_DIR / "equity_portfolio_assessment_20260808.json"
PLAN_CSV = REPORT_DIR / "equity_portfolio_50_reduction_plan_20260808.csv"
PLAN_JSON = REPORT_DIR / "equity_portfolio_50_reduction_plan_20260808.json"


ACTION_ORDER = {
    "RESOLVE_OR_EXIT": 1,
    "CLEAN_EXIT": 2,
    "SELL_TO_RESEARCH_WATCHLIST": 3,
    "VERIFY_BEFORE_EXIT": 4,
}


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    text = text.replace("%", "")
    text = re.sub(r"^\-\s+", "-", text)
    accounting_negative = text.startswith("(") and text.endswith(")")
    if accounting_negative:
        text = text[1:-1].strip()
    try:
        number = float(text)
        return -number if accounting_negative else number
    except ValueError:
        return None


def fmt_pct(value: Any, digits: int = 2) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}%"


def fmt_inr(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"Rs. {number:,.0f}"


def fmt_num(value: Any, digits: int = 1) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}"


def fmt_weight_sum(rows: list[dict[str, str]]) -> str:
    total = sum(parse_number(row.get("current_weight_pct")) or 0.0 for row in rows)
    return f"{total:.2f}%"


def classify_research_decision(row: dict[str, str]) -> str:
    if row["research_stage"] == "TAIL_FIRST":
        action = row["recommended_action"]
        if action == "CLEAN_EXIT":
            return "Proceed after price/tax/liquidity check"
        if action == "RESOLVE_OR_EXIT":
            return "Resolve corporate action or exit"
        if action == "SELL_TO_RESEARCH_WATCHLIST":
            return "Exit small line, keep on watchlist"
        if action == "VERIFY_BEFORE_EXIT":
            return "Verify once before selling"
        return "Tail cleanup review"
    action = row["recommended_action"].upper()
    if "WAIT" in action or "WATCH" in action or "HOLD-REVIEW" in action:
        return "Research watch, not automatic sell"
    if "REDUCE" in action or "EXIT" in action:
        return "Reduce if enforcing 50-stock book"
    return "Deep research review"


def read_rows() -> list[dict[str, str]]:
    with INPUT_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return sorted(
        rows,
        key=lambda row: (
            0 if row["research_stage"] == "TAIL_FIRST" else 1,
            ACTION_ORDER.get(row["recommended_action"], 99),
            -(parse_number(row.get("current_weight_pct")) or 0.0),
        ),
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json_obj(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_portfolio_bundle() -> dict[str, Any]:
    assessment_payload = read_json_obj(ASSESSMENT_JSON)
    plan_payload = read_json_obj(PLAN_JSON)
    assessment_rows = read_csv_rows(ASSESSMENT_CSV)
    plan_rows = read_csv_rows(PLAN_CSV)
    return {
        "assessment_summary": assessment_payload.get("summary", {}),
        "assessment_rows": assessment_rows,
        "plan_summary": plan_payload.get("summary", {}),
        "plan_rows": plan_rows,
        "plan_by_symbol": {str(row.get("symbol") or "").upper(): row for row in plan_rows},
    }


def build_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    tail_rows = [row for row in rows if row["research_stage"] == "TAIL_FIRST"]
    deep_rows = [row for row in rows if row["research_stage"] == "DEEP_RESEARCH_REMAINING"]
    tail_actions = Counter(row["recommended_action"] for row in tail_rows)
    deep_decisions = Counter(classify_research_decision(row) for row in deep_rows)
    watchlist = [
        row["symbol"]
        for row in rows
        if row["recommended_action"] in {"SELL_TO_RESEARCH_WATCHLIST", "VERIFY_BEFORE_EXIT"}
        or classify_research_decision(row) == "Research watch, not automatic sell"
    ]
    return {
        "report_title": "Tail First And Remaining Deep Research",
        "data_through": "2026-08-07 local assessment; public checks summarized from 2026-08-08 research",
        "research_only": True,
        "tail_first_count": len(tail_rows),
        "tail_first_weight_pct": fmt_weight_sum(tail_rows),
        "remaining_deep_research_count": len(deep_rows),
        "remaining_deep_research_weight_pct": fmt_weight_sum(deep_rows),
        "tail_action_counts": dict(tail_actions),
        "deep_decision_counts": dict(deep_decisions),
        "watchlist_after_cleanup": watchlist,
        "source_assessment": "reports/portfolio_assessments/equity_portfolio_assessment_20260808.csv",
        "source_50_plan": "reports/portfolio_assessments/equity_portfolio_50_reduction_plan_20260808.csv",
        "source_staged_csv": str(INPUT_CSV.relative_to(ROOT)),
    }


def markdown_table(rows: list[dict[str, str]], deep: bool = False) -> list[str]:
    def clean_cell(value: Any) -> str:
        return str(value if value is not None else "-").replace("|", "/").replace("\n", " ")

    def md_row(cells: list[Any]) -> str:
        return "| " + " | ".join(clean_cell(cell) for cell in cells) + " |"

    if deep:
        lines = [
            "| Symbol | ICICIdirect | Weight | Local Tech/Fund | Public Evidence | Verdict | Action |",
            "|---|---|---:|---|---|---|---|",
        ]
        for row in rows:
            local = (
                f"{row.get('stage') or '-'} / {row.get('trading_signal') or '-'} / "
                f"tech {fmt_num(row.get('technical_score'))} / fund {fmt_num(row.get('fundamental_score'))}"
            )
            lines.append(
                md_row(
                    [
                        row["symbol"],
                        row["broker_symbol"],
                        fmt_pct(row["current_weight_pct"]),
                        local,
                        row["public_summary"],
                        row["deep_verdict"],
                        row["recommended_action"],
                    ]
                )
            )
        return lines

    lines = [
        "| Symbol | ICICIdirect | Weight | P/L | Stage | Tech | Fund | Decision | Rationale |",
        "|---|---|---:|---:|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            md_row(
                [
                    row["symbol"],
                    row["broker_symbol"],
                    fmt_pct(row["current_weight_pct"]),
                    fmt_pct(row["unrealized_pl_pct"]),
                    row.get("stage") or "-",
                    fmt_num(row.get("technical_score")),
                    fmt_num(row.get("fundamental_score")),
                    classify_research_decision(row),
                    row["deep_verdict"],
                ]
            )
        )
    return lines


def write_markdown(rows: list[dict[str, str]], summary: dict[str, Any]) -> None:
    tail_rows = [row for row in rows if row["research_stage"] == "TAIL_FIRST"]
    deep_rows = [row for row in rows if row["research_stage"] == "DEEP_RESEARCH_REMAINING"]
    by_tail_action: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in tail_rows:
        by_tail_action[row["recommended_action"]].append(row)

    lines: list[str] = [
        "# Tail First And Remaining Deep Research",
        "",
        "Research-only; not an order list. This report separates portfolio hygiene exits from company-quality exits.",
        "",
        "## Executive Narrative",
        "",
        f"- Start with the tail: {summary['tail_first_count']} holdings together represent a very small part of the book, but they create monitoring load.",
        "- Do not treat all exits as bad-business calls. Several names have acceptable fundamentals but weak technicals or no role in the 50-stock target book.",
        "- Tail cleanup can proceed first after price, tax, liquidity, and corporate-action checks.",
        f"- Remaining deep-research names ({summary['remaining_deep_research_count']}) should be reviewed one by one before irreversible selling.",
        "",
        "## Decision Legend",
        "",
        "- CLEAN_EXIT: small/no-gain position with weak technicals, weak latest financial evidence, or no portfolio role.",
        "- RESOLVE_OR_EXIT: identity or corporate-action gap; resolve tradability/current listing before deeper research.",
        "- SELL_TO_RESEARCH_WATCHLIST: sell/reduce the small line for simplification, but keep the company on a watchlist.",
        "- VERIFY_BEFORE_EXIT: not a poor business on local evidence; confirm once before selling.",
        "- Research watch, not automatic sell: public/current evidence is not weak enough for a blind exit.",
        "",
        "## Summary",
        "",
        f"- Tail-first names: {summary['tail_first_count']} ({summary['tail_first_weight_pct']} current portfolio weight)",
        f"- Remaining deep-research names: {summary['remaining_deep_research_count']} ({summary['remaining_deep_research_weight_pct']} current portfolio weight)",
        f"- Tail action counts: {summary['tail_action_counts']}",
        f"- Deep decision counts: {summary['deep_decision_counts']}",
        f"- Watchlist after cleanup: {', '.join(summary['watchlist_after_cleanup'])}",
        "",
        "## Tail Buckets",
        "",
    ]

    for action in ("RESOLVE_OR_EXIT", "CLEAN_EXIT", "SELL_TO_RESEARCH_WATCHLIST", "VERIFY_BEFORE_EXIT"):
        action_rows = by_tail_action.get(action, [])
        if not action_rows:
            continue
        lines.append(f"### {action}")
        lines.append("")
        lines.extend(markdown_table(action_rows))
        lines.append("")

    lines.extend(
        [
            "## Remaining Deep Research",
            "",
            "These are not automatic sells. Public/current evidence changed the interpretation for several names.",
            "",
        ]
    )
    lines.extend(markdown_table(deep_rows, deep=True))
    lines.extend(
        [
            "",
            "## Source Trail",
            "",
            f"- Local assessment: `{summary['source_assessment']}`",
            f"- 50-stock plan: `{summary['source_50_plan']}`",
            f"- Staged CSV: `{summary['source_staged_csv']}`",
            "- Public-source summaries are retained in the `source_trail` column of the CSV/JSON.",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def badge(text: str) -> str:
    upper = text.upper()
    css_class = "sig-sell" if "EXIT" in upper or "CLEAN" in upper else "sig-hold"
    if "PROCEED AFTER" in upper:
        css_class = "sig-sell"
    if "WATCH" in upper or "VERIFY" in upper or "WAIT" in upper or "HOLD-REVIEW" in upper:
        css_class = "sig-weak-hold"
    if "RESEARCH WATCH" in upper or "NOT AUTOMATIC" in upper:
        css_class = "sig-buy"
    return f'<span class="signal-chip {css_class}">{html.escape(text)}</span>'


def action_class(action: str) -> str:
    action = (action or "").upper()
    if "WATCH" in action or "VERIFY" in action or "WAIT" in action:
        return "row-weak-hold"
    if "CLEAN" in action or "EXIT" in action:
        return "row-sell"
    return "row-hold"


def pct_class(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return "ret-flat"
    if number > 0:
        return "ret-pos"
    if number < 0:
        return "ret-neg"
    return "ret-flat"


def score_class(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return "score-na"
    if number >= 70:
        return "score-high"
    if number >= 50:
        return "score-mid"
    return "score-low"


def weight_class(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return "wt-low"
    if number >= 5:
        return "wt-high"
    if number >= 1:
        return "wt-mid"
    return "wt-low"


def score_bar(value: Any, accent: str = "#059669") -> str:
    number = parse_number(value)
    if number is None:
        return '<span class="score-na">-</span>'
    width = max(0.0, min(100.0, number))
    return (
        '<span class="score-bar">'
        f'<span class="sb-num">{number:.0f}</span>'
        '<span class="sb-track">'
        f'<span class="sb-fill" style="width:{width:.1f}%;background:{accent}"></span>'
        "</span></span>"
    )


def stage_badge(stage: str) -> str:
    stage_text = stage or "-"
    stage_num = stage_text.split("_")[-1] if stage_text.startswith("STAGE_") else ""
    stage_classes = {"1": "s-1", "2": "s-2", "3": "s-3", "4": "s-4"}
    css_class = stage_classes.get(stage_num, "s-all")
    label = f"S{stage_num}" if stage_num else "-"
    return f'<span class="stage-chip {css_class}">{html.escape(label)}</span>'


def heat_cell(value: Any, kind: str, text: str) -> str:
    if kind == "return":
        css_class = pct_class(value)
    elif kind == "weight":
        css_class = weight_class(value)
    else:
        css_class = score_class(value)
    return f'<span class="heat {css_class}">{html.escape(text)}</span>'


def metric(label: str, value: Any, css_class: str = "") -> str:
    class_attr = f"sum-card {css_class}".strip()
    return (
        f'<div class="{html.escape(class_attr)}">'
        f'<div class="sc-val">{html.escape(str(value))}</div>'
        f'<div class="sc-lbl">{html.escape(label)}</div>'
        "</div>"
    )


def symbol_for(row: dict[str, str]) -> str:
    return str(row.get("nse_symbol") or row.get("symbol") or row.get("broker_symbol") or "-").upper()


def plan_action_badge(action: str) -> str:
    label = action or "-"
    upper = label.upper()
    if "KEEP" in upper:
        css_class = "sig-buy"
    elif "EXIT" in upper:
        css_class = "sig-sell"
    elif "TRIM" in upper or "REDUCE" in upper or "REBALANCE" in upper:
        css_class = "sig-weak-hold"
    else:
        css_class = "sig-hold"
    return f'<span class="signal-chip {css_class}">{html.escape(label)}</span>'


def row_action_class(action_tokens: str) -> str:
    upper = action_tokens.upper()
    if "KEEP_50" in upper or "NO-SELL" in upper:
        return "row-hold"
    if "EXIT" in upper or "SELL" in upper or "PRIORITY" in upper:
        return "row-sell"
    if "TRIM" in upper or "REDUCE" in upper or "REBALANCE" in upper or "REVIEW" in upper:
        return "row-weak-hold"
    return "row-hold"


def action_count_cards(counts: dict[str, Any], css_class: str = "") -> str:
    cards = []
    for action, count in sorted(counts.items(), key=lambda item: (-parse_number(item[1]) if parse_number(item[1]) is not None else 0, str(item[0]))):
        cards.append(metric(str(action), count, css_class))
    return "".join(cards)


def allocation_bar(weight: Any) -> str:
    number = parse_number(weight) or 0.0
    width = max(1.0, min(100.0, number * 4.0))
    return (
        '<span class="alloc-bar">'
        f'<span class="alloc-fill" style="width:{width:.1f}%"></span>'
        "</span>"
    )


def sector_allocation_table(portfolio: dict[str, Any]) -> str:
    rows = []
    for sector, weight in portfolio["assessment_summary"].get("top_sector_weights", []):
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(str(sector))}</strong></td>"
            f"<td>{heat_cell(weight, 'weight', fmt_pct(weight))}</td>"
            f"<td>{allocation_bar(weight)}</td>"
            "</tr>"
        )
    return (
        '<div class="tbl-wrap"><table><thead><tr><th>Sector Lens</th><th>Weight</th><th>Allocation</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def keep_50_table(portfolio: dict[str, Any]) -> str:
    body = []
    keep_rows = [row for row in portfolio["plan_rows"] if row.get("plan_action") == "KEEP_50"]
    for row in keep_rows:
        action_tokens = f"{row.get('plan_action')} {row.get('plan_bucket')} {row.get('stage')}".upper()
        body.append(
            f'<tr class="{row_action_class(action_tokens)}" data-symbol="{html.escape(symbol_for(row).lower())}" data-stage="{html.escape(row.get("stage") or "-")}" data-action="{html.escape(action_tokens)}">'
            f"<td><strong>{html.escape(symbol_for(row))}</strong><br><span>{html.escape(row.get('company_name') or '-')}</span></td>"
            f"<td>{html.escape(row.get('broker_symbol') or '-')}</td>"
            f"<td>{fmt_inr(row.get('current_value_rs'))}</td>"
            f"<td>{heat_cell(row.get('current_weight_pct'), 'weight', fmt_pct(row.get('current_weight_pct')))}</td>"
            f"<td>{heat_cell(row.get('unrealized_pl_pct'), 'return', fmt_pct(row.get('unrealized_pl_pct')))}</td>"
            f"<td>{stage_badge(row.get('stage') or '')}</td>"
            f"<td>{score_bar(row.get('technical_score'), '#059669')}</td>"
            f"<td>{score_bar(row.get('fundamental_score'), '#7c3aed')}</td>"
            f"<td>{plan_action_badge(row.get('plan_bucket') or row.get('plan_action') or '-')}</td>"
            "</tr>"
        )
    return (
        '<div class="tbl-wrap"><table><thead><tr><th>Symbol</th><th>ICICIdirect</th><th>Value</th><th>Weight</th><th>P/L</th><th>Stage</th><th>Tech</th><th>Fund</th><th>Bucket</th></tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def combined_portfolio_table(portfolio: dict[str, Any]) -> str:
    body = []
    plan_by_symbol = portfolio["plan_by_symbol"]
    rows = sorted(
        portfolio["assessment_rows"],
        key=lambda row: -(parse_number(row.get("portfolio_weight_pct")) or 0.0),
    )
    for row in rows:
        symbol = symbol_for(row)
        plan = plan_by_symbol.get(symbol, {})
        action_tokens = " ".join(
            str(value or "")
            for value in [
                plan.get("plan_action"),
                plan.get("plan_bucket"),
                row.get("primary_action"),
                row.get("cleanup_priority"),
                row.get("short_term_view"),
                row.get("medium_term_view"),
                row.get("long_term_view"),
                row.get("stage"),
            ]
        ).upper()
        view_text = " / ".join(
            value
            for value in [
                str(row.get("short_term_view") or "").strip(),
                str(row.get("medium_term_view") or "").strip(),
                str(row.get("long_term_view") or "").strip(),
            ]
            if value
        )
        body.append(
            f'<tr class="{row_action_class(action_tokens)}" data-symbol="{html.escape(symbol.lower())}" data-stage="{html.escape(row.get("stage") or "-")}" data-action="{html.escape(action_tokens)}">'
            f"<td><strong>{html.escape(symbol)}</strong><br><span>{html.escape(row.get('company_name') or '-')}</span></td>"
            f"<td>{html.escape(row.get('broker_symbol') or '-')}</td>"
            f"<td>{fmt_inr(row.get('value_at_market'))}</td>"
            f"<td>{heat_cell(row.get('portfolio_weight_pct'), 'weight', fmt_pct(row.get('portfolio_weight_pct')))}</td>"
            f"<td>{heat_cell(row.get('unrealized_pl_pct'), 'return', fmt_pct(row.get('unrealized_pl_pct')))}</td>"
            f"<td>{plan_action_badge(plan.get('plan_action') or '-')}</td>"
            f"<td>{badge(row.get('primary_action') or '-')}</td>"
            f"<td>{stage_badge(row.get('stage') or '')}</td>"
            f"<td>{score_bar(row.get('technical_score'), '#059669')}</td>"
            f"<td>{score_bar(row.get('enhanced_fund_score') or row.get('fundamental_score'), '#7c3aed')}</td>"
            f"<td>{html.escape(row.get('sector_lens') or row.get('sector') or '-')}</td>"
            f"<td><span>{html.escape(row.get('cleanup_priority') or '-')}</span><br>{html.escape(row.get('action_reason') or row.get('cleanup_reason') or '-')}</td>"
            f"<td>{html.escape(view_text or '-')}</td>"
            "</tr>"
        )
    return (
        '<div class="tbl-wrap full-table"><table><thead><tr><th>Symbol</th><th>ICICIdirect</th><th>Value</th><th>Weight</th><th>P/L</th><th>50 Plan</th><th>Assessment Action</th><th>Stage</th><th>Tech</th><th>Fund</th><th>Sector</th><th>Reason</th><th>Views</th></tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def detail_card(row: dict[str, str]) -> str:
    local = (
        f"{row.get('stage') or '-'} / {row.get('trading_signal') or '-'} / "
        f"tech {fmt_num(row.get('technical_score'))} / fund {fmt_num(row.get('fundamental_score'))}"
    )
    decision = classify_research_decision(row)
    action_tokens = f"{row['recommended_action']} {decision}".upper()
    return f"""
    <details class="stock-card" data-symbol="{html.escape(row["symbol"].lower())}" data-action="{html.escape(action_tokens)}" data-stage="{html.escape(row.get("stage") or "-")}" open>
      <summary>
        <span class="pk-sym">{html.escape(row["symbol"])}</span>
        <span class="pk-co">{html.escape(row["company_name"])}</span>
        {stage_badge(row.get("stage") or "")}
        {badge(row["recommended_action"])}
      </summary>
      <div class="stock-body">
        <div class="detail-grid">
          <div class="det-card">
            <h4>Position</h4>
            <p>ICICIdirect: <strong>{html.escape(row["broker_symbol"])}</strong></p>
            <p>Weight: <strong>{fmt_pct(row["current_weight_pct"])}</strong></p>
            <p>P/L: <strong class="{pct_class(row["unrealized_pl_pct"])}">{fmt_pct(row["unrealized_pl_pct"])}</strong></p>
          </div>
          <div class="det-card">
            <h4>Local Setup</h4>
            <p>{html.escape(local)}</p>
            <p>Technical {score_bar(row.get("technical_score"), "#059669")}</p>
            <p>Fundamental {score_bar(row.get("fundamental_score"), "#7c3aed")}</p>
          </div>
          <div class="det-card wide">
            <h4>Public Evidence</h4>
            <p>{html.escape(row["public_summary"])}</p>
          </div>
          <div class="det-card wide">
            <h4>Recommendation Narrative</h4>
            <p><strong>{html.escape(decision)}.</strong> {html.escape(row["deep_verdict"])}</p>
          </div>
        </div>
        <p class="source">{html.escape(row["source_trail"])}</p>
      </div>
    </details>
    """


def tail_table(rows: list[dict[str, str]]) -> str:
    body = []
    for row in rows:
        decision = classify_research_decision(row)
        action_tokens = f"{row['recommended_action']} {decision}".upper()
        body.append(
            f'<tr class="{action_class(row["recommended_action"])}" data-symbol="{html.escape(row["symbol"].lower())}" data-stage="{html.escape(row.get("stage") or "-")}" data-action="{html.escape(action_tokens)}">'
            f"<td><strong>{html.escape(row['symbol'])}</strong><br><span>{html.escape(row['company_name'])}</span></td>"
            f"<td>{html.escape(row['broker_symbol'])}</td>"
            f"<td>{heat_cell(row['current_weight_pct'], 'weight', fmt_pct(row['current_weight_pct']))}</td>"
            f"<td>{heat_cell(row['unrealized_pl_pct'], 'return', fmt_pct(row['unrealized_pl_pct']))}</td>"
            f"<td>{stage_badge(row.get('stage') or '')}</td>"
            f"<td>{score_bar(row.get('technical_score'), '#059669')}</td>"
            f"<td>{score_bar(row.get('fundamental_score'), '#7c3aed')}</td>"
            f"<td>{badge(decision)}</td>"
            f"<td>{html.escape(row['deep_verdict'])}</td>"
            "</tr>"
        )
    return (
        '<div class="tbl-wrap"><table><thead><tr><th>Symbol</th><th>ICICIdirect</th><th>Weight</th><th>P/L</th>'
        "<th>Stage</th><th>Tech</th><th>Fund</th><th>Decision</th><th>Rationale</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def write_html(rows: list[dict[str, str]], summary: dict[str, Any], portfolio: dict[str, Any]) -> None:
    tail_rows = [row for row in rows if row["research_stage"] == "TAIL_FIRST"]
    deep_rows = [row for row in rows if row["research_stage"] == "DEEP_RESEARCH_REMAINING"]
    by_tail_action: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in tail_rows:
        by_tail_action[row["recommended_action"]].append(row)
    assessment_summary = portfolio["assessment_summary"]
    plan_summary = portfolio["plan_summary"]

    styles = r"""
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',system-ui,sans-serif;background:#f1f5f9;color:#0f172a;font-size:14px}
    .app-bar{background:linear-gradient(135deg,#065f46,#059669);color:#fff;padding:18px 24px}
    .app-bar h1{font-size:1.45rem;font-weight:700;letter-spacing:0}
    .app-bar p{font-size:.82rem;opacity:.86;margin-top:4px;max-width:1120px;line-height:1.45}
    .container{max-width:1600px;margin:0 auto;padding:20px 16px 40px}
    .disc{background:#fff7ed;border:1px solid #fed7aa;border-left:4px solid #f97316;color:#7c2d12;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:.82rem;line-height:1.45}
    .main-nav{position:sticky;top:0;z-index:20;background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:8px 16px;display:flex;gap:8px;overflow-x:auto}
    .main-nav a{color:#475569;text-decoration:none;border:1px solid #e2e8f0;background:#fff;border-radius:6px;padding:6px 10px;font-size:.78rem;font-weight:700;white-space:nowrap}
    .main-nav a:hover{border-color:#059669;color:#047857;background:#ecfdf5}
    .summary-grid{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:20px}
    .sum-card{background:#fff;border-radius:8px;padding:14px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:150px;border-top:3px solid #059669;flex:1}
    .sum-card .sc-val{font-size:1.75rem;font-weight:700;line-height:1;color:#0f172a}
    .sum-card .sc-lbl{font-size:.75rem;color:#64748b;margin-top:6px;text-transform:uppercase;letter-spacing:.04em}
    .sum-card.sc-risk{border-top-color:#dc2626}.sum-card.sc-risk .sc-val{color:#dc2626}
    .sum-card.sc-warn{border-top-color:#d97706}.sum-card.sc-warn .sc-val{color:#d97706}
    .sum-card.sc-blue{border-top-color:#2563eb}.sum-card.sc-blue .sc-val{color:#2563eb}
    .watch-card{flex:2;min-width:320px;border-top-color:#7c3aed}
    .watch-card .sc-val{font-size:.83rem;line-height:1.45;color:#334155;font-weight:600}
    .section{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:20px;overflow:hidden}
    .sec-hdr{padding:14px 18px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
    .sec-hdr h2{font-size:1rem;font-weight:700;color:#0f172a}
    .sec-sub{font-size:.78rem;color:#64748b;line-height:1.45}
    .badge-count{background:#e2e8f0;border-radius:12px;padding:2px 10px;font-size:.8rem;font-weight:700;color:#475569}
    .toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 14px;border-bottom:1px solid #e2e8f0;background:#fafafa}
    .search-bar{padding:7px 11px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;outline:none;min-width:220px;flex:1}
    .search-bar:focus{border-color:#059669;box-shadow:0 0 0 2px rgba(5,150,105,.15)}
    .tb-btn{padding:6px 12px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;background:#fff;color:#475569;white-space:nowrap}
    .tb-btn:hover{background:#f1f5f9}
    .tb-btn.active{background:#059669;color:#fff;border-color:#059669}
    .callouts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;padding:16px 18px}
    .callout{background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #059669;border-radius:8px;padding:12px}
    .callout strong{display:block;font-size:.88rem;margin-bottom:5px;color:#0f172a}
    .callout p{font-size:.82rem;color:#475569;line-height:1.5}
    .callout.warn{border-left-color:#d97706}.callout.risk{border-left-color:#dc2626}.callout.blue{border-left-color:#2563eb}
    .tbl-wrap{overflow-x:auto}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th{background:#f8fafc;padding:8px 12px;text-align:left;font-size:.72rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid #e2e8f0;white-space:nowrap;position:sticky;top:40px;z-index:5}
    td{padding:8px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
    td span{color:#64748b;font-size:.78rem}
    tr:last-child td{border-bottom:none}
    tr:hover td{background:rgba(5,150,105,.04)!important}
    tr[hidden],.stock-card[hidden]{display:none!important}
    tr.row-hold td:first-child{border-left:3px solid #ca8a04}
    tr.row-weak-hold td:first-child{border-left:3px solid #f97316}
    tr.row-sell td:first-child{border-left:3px solid #dc2626}
    .signal-chip{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;white-space:nowrap}
    .sig-buy{background:#bbf7d0;color:#166534}
    .sig-hold{background:#fef9c3;color:#854d0e}
    .sig-weak-hold{background:#ffedd5;color:#9a3412}
    .sig-sell{background:#fee2e2;color:#991b1b}
    .stage-chip{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700;border:1px solid transparent;white-space:nowrap}
    .stage-chip.s-all{background:#e2e8f0;color:#475569}
    .stage-chip.s-1{background:#fef9c3;color:#854d0e;border-color:#ca8a04}
    .stage-chip.s-2{background:#dcfce7;color:#166534;border-color:#16a34a}
    .stage-chip.s-3{background:#ffedd5;color:#9a3412;border-color:#ea580c}
    .stage-chip.s-4{background:#fee2e2;color:#991b1b;border-color:#dc2626}
    .score-bar{display:inline-flex;align-items:center;gap:5px;min-width:92px;vertical-align:middle}
    .sb-num{font-weight:700;min-width:26px;font-size:.82rem;color:#0f172a}
    .sb-track{flex:1;height:5px;background:#e2e8f0;border-radius:3px;min-width:48px}
    .sb-fill{height:100%;border-radius:3px}
    .heat{display:inline-block;border-radius:4px;padding:2px 7px;min-width:56px;text-align:right;font-weight:700}
    .ret-pos,.score-high{background:#dcfce7;color:#166534}
    .ret-neg,.score-low{background:#fee2e2;color:#991b1b}
    .ret-flat,.score-mid{background:#fef9c3;color:#854d0e}
    .wt-high{background:#fee2e2;color:#991b1b}
    .wt-mid{background:#fef9c3;color:#854d0e}
    .wt-low{background:#e0f2fe;color:#0369a1}
    .score-na{color:#94a3b8;font-weight:700}
    .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px;padding:16px 18px}
    .stock-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}
    .stock-card summary{cursor:pointer;list-style:none;padding:12px 14px;display:grid;grid-template-columns:auto auto minmax(0,1fr) auto auto;gap:8px;align-items:center;background:#f8fafc}
    .stock-card summary::-webkit-details-marker{display:none}
    .stock-card summary::before{content:"";width:0;height:0;border-top:5px solid transparent;border-bottom:5px solid transparent;border-left:7px solid #059669;transition:transform .15s}
    .stock-card[open] summary::before{transform:rotate(90deg)}
    .pk-sym{font-size:1rem;font-weight:800;color:#0f172a}
    .pk-co{font-size:.78rem;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .stock-body{padding:14px}
    .detail-grid{display:flex;flex-wrap:wrap;gap:12px}
    .det-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:160px;flex:1}
    .det-card.wide{flex:2;min-width:260px}
    .det-card h4{font-size:.72rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}
    .det-card p{font-size:.82rem;color:#334155;line-height:1.55;margin-bottom:6px}
    .source{color:#64748b;background:#f8fafc;border-left:3px solid #2563eb;margin-top:12px;padding:8px 10px;border-radius:6px;font-size:.78rem;line-height:1.45}
    .source-list{padding:14px 18px;display:grid;gap:8px}
    .source-list p{font-size:.83rem;color:#334155;line-height:1.5}
    .alloc-bar{display:block;width:180px;max-width:100%;height:7px;background:#e2e8f0;border-radius:4px;overflow:hidden}
    .alloc-fill{display:block;height:100%;background:#059669;border-radius:4px}
    .full-table td:nth-child(12),.full-table td:nth-child(13){min-width:260px;line-height:1.45}
    .full-table td:nth-child(1){min-width:190px}
    code{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:4px;padding:1px 5px;color:#334155}
    .links a{display:inline-block;color:#047857;text-decoration:none;border:1px solid #bbf7d0;background:#f0fdf4;border-radius:6px;padding:6px 10px;margin-right:8px;margin-top:4px;font-weight:700;font-size:.78rem}
    .links a:hover{background:#dcfce7}
    @media(max-width:760px){
      .app-bar{padding:16px}.container{padding:14px 10px 28px}.main-nav{top:0;padding:8px 10px}
      .sum-card{min-width:150px;padding:12px}.sum-card .sc-val{font-size:1.35rem}
      th,td{padding:7px 9px;font-size:12px}.cards{grid-template-columns:1fr;padding:12px}.alloc-bar{width:120px}
      .stock-card summary{grid-template-columns:auto 1fr;align-items:start}.stock-card summary .signal-chip,.stock-card summary .stage-chip{justify-self:start}
      .toolbar{position:static}.search-bar{min-width:100%}
    }
    """
    script = r"""
    <script>
    function setFilter(btn){
      document.querySelectorAll('.tb-btn').forEach(function(node){ node.classList.remove('active'); });
      btn.classList.add('active');
      applyFilters();
    }
    function applyFilters(){
      var search = (document.getElementById('report-search').value || '').toLowerCase().trim();
      var active = document.querySelector('.tb-btn.active');
      var token = active ? active.dataset.filter : 'ALL';
      var visible = 0;
      document.querySelectorAll('tbody tr[data-symbol], .stock-card').forEach(function(node){
        var text = node.textContent.toLowerCase();
        var action = node.dataset.action || '';
        var stage = node.dataset.stage || '';
        var tokenMatch = token === 'ALL' || action.indexOf(token) >= 0 || stage === token;
        var searchMatch = !search || text.indexOf(search) >= 0 || (node.dataset.symbol || '').indexOf(search) >= 0;
        var show = tokenMatch && searchMatch;
        node.hidden = !show;
        if (show) visible += 1;
      });
      var counter = document.getElementById('visible-count');
      if (counter) counter.textContent = visible + ' visible rows/cards';
    }
    document.addEventListener('DOMContentLoaded', applyFilters);
    </script>
    """
    parts = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Tail First And Remaining Deep Research</title>",
        f"<style>{styles}</style></head><body>",
        "<div class=\"app-bar\"><h1>Combined Portfolio Assessment And Tail Research</h1>",
        "<p>Research-only / no order list. Combined view of the full ICICIdirect portfolio assessment, 50-stock reduction plan, tail cleanup, and deep-research watchlist using local evidence through 2026-08-07 plus cached public summaries from 2026-08-08.</p></div>",
        "<nav class=\"main-nav\"><a href=\"#overview\">Overview</a><a href=\"#portfolio\">Portfolio</a><a href=\"#plan50\">50-Stock Plan</a><a href=\"#tail\">Tail Buckets</a><a href=\"#deep\">Deep Research</a><a href=\"#full\">Full Holdings</a><a href=\"#sources\">Source Trail</a></nav>",
        "<main class=\"container\">",
        "<div class=\"disc\"><strong>Investor caution:</strong> This is a research and portfolio-review artifact only. It is not an execution ticket, order list, or tax recommendation. Check current price, liquidity, taxes, corporate actions, and account constraints before any trade.</div>",
        "<section class=\"section\" id=\"overview\"><div class=\"sec-hdr\"><h2>Executive Narrative</h2><span class=\"badge-count\">Portfolio cleanup</span></div><div class=\"callouts\">",
        f"<div class=\"callout\"><strong>Whole portfolio first.</strong><p>The assessment covers {assessment_summary.get('holding_count')} holdings with market value {fmt_inr(assessment_summary.get('total_market_value'))} and unrealized P/L {fmt_inr(assessment_summary.get('total_unrealized'))} ({fmt_pct(assessment_summary.get('total_unrealized_pct'))}).</p></div>",
        f"<div class=\"callout risk\"><strong>Tail cleanup comes first.</strong><p>{summary['tail_first_count']} small holdings can be reviewed before spending research time on larger quality names.</p></div>",
        "<div class=\"callout warn\"><strong>Not every exit is a bad-business call.</strong><p>Several names have respectable fundamentals but weak technicals, tiny sizing, or no clear role in a 50-stock book.</p></div>",
        f"<div class=\"callout blue\"><strong>Deep research protects quality.</strong><p>The remaining {summary['remaining_deep_research_count']} names should be reviewed individually before final selling decisions.</p></div>",
        "</div></section>",
        "<section class=\"section\"><div class=\"sec-hdr\"><h2>Combined Summary</h2><span id=\"visible-count\" class=\"badge-count\">-</span></div><div class=\"summary-grid\">",
        metric("Holdings", assessment_summary.get("holding_count")),
        metric("Market value", fmt_inr(assessment_summary.get("total_market_value")), "sc-blue"),
        metric("Unrealized P/L", f"{fmt_inr(assessment_summary.get('total_unrealized'))} ({fmt_pct(assessment_summary.get('total_unrealized_pct'))})"),
        metric("Top 10 weight", fmt_pct(assessment_summary.get("top_10_weight_pct")), "sc-warn"),
        metric("Keep 50 weight", fmt_pct(plan_summary.get("keep_current_weight_pct")), "sc-blue"),
        metric("Tail-first names", summary["tail_first_count"]),
        metric("Tail-first weight", summary["tail_first_weight_pct"]),
        metric("Deep-research names", summary["remaining_deep_research_count"]),
        metric("Deep-research weight", summary["remaining_deep_research_weight_pct"]),
        '<div class="sum-card watch-card"><div class="sc-val">'
        + html.escape(", ".join(summary["watchlist_after_cleanup"]))
        + '</div><div class="sc-lbl">Watchlist after cleanup</div></div>',
        "</div></section>",
        "<section class=\"section\"><div class=\"sec-hdr\"><h2>Filters</h2><span class=\"sec-sub\">Search symbol, company, rationale, or public evidence. Buttons filter both tables and deep-research cards.</span></div>",
        "<div class=\"toolbar\"><input id=\"report-search\" class=\"search-bar\" oninput=\"applyFilters()\" placeholder=\"Search symbol, company, evidence, rationale\"><button class=\"tb-btn active\" data-filter=\"ALL\" onclick=\"setFilter(this)\">All</button><button class=\"tb-btn\" data-filter=\"KEEP_50\" onclick=\"setFilter(this)\">Keep 50</button><button class=\"tb-btn\" data-filter=\"EXIT\" onclick=\"setFilter(this)\">Exit</button><button class=\"tb-btn\" data-filter=\"CLEAN\" onclick=\"setFilter(this)\">Clean exits</button><button class=\"tb-btn\" data-filter=\"WATCH\" onclick=\"setFilter(this)\">Watch</button><button class=\"tb-btn\" data-filter=\"VERIFY\" onclick=\"setFilter(this)\">Verify</button><button class=\"tb-btn\" data-filter=\"ADD\" onclick=\"setFilter(this)\">Add</button><button class=\"tb-btn\" data-filter=\"STAGE_2\" onclick=\"setFilter(this)\">Stage 2</button><button class=\"tb-btn\" data-filter=\"STAGE_4\" onclick=\"setFilter(this)\">Stage 4</button></div></section>",
        "<section class=\"section\" id=\"portfolio\"><div class=\"sec-hdr\"><h2>Portfolio Details</h2>",
        f"<span class=\"badge-count\">{assessment_summary.get('holding_count')} holdings</span><span class=\"sec-sub\">Resolved {assessment_summary.get('resolved_count')} / unresolved {assessment_summary.get('unresolved_count')}; source file {html.escape(str(assessment_summary.get('source_file') or '-'))}</span></div>",
        "<div class=\"summary-grid\">",
        metric("Cost value", fmt_inr(assessment_summary.get("total_cost"))),
        metric("Resolved", assessment_summary.get("resolved_count")),
        metric("Unresolved", assessment_summary.get("unresolved_count"), "sc-risk"),
        metric("Public deep checked", assessment_summary.get("public_research_counts", {}).get("deep_checked", 0), "sc-blue"),
        "</div><div class=\"sec-hdr\"><h2>Primary Assessment Actions</h2><span class=\"sec-sub\">Counts from the full local assessment.</span></div><div class=\"summary-grid\">",
        action_count_cards(assessment_summary.get("action_counts", {})),
        "</div><div class=\"sec-hdr\"><h2>Sector Weight Heat Map</h2><span class=\"sec-sub\">Top sector lenses by current market value.</span></div>",
        sector_allocation_table(portfolio),
        "</section>",
        "<section class=\"section\" id=\"plan50\"><div class=\"sec-hdr\"><h2>50-Stock Reduction Plan</h2>",
        f"<span class=\"badge-count\">Keep {plan_summary.get('keep_count')} / Exit {plan_summary.get('exit_count')}</span><span class=\"sec-sub\">Forced no-sell: {html.escape(', '.join(plan_summary.get('forced_no_sell', [])))}</span></div>",
        "<div class=\"summary-grid\">",
        metric("Keep current value", fmt_inr(plan_summary.get("keep_current_value_rs")), "sc-blue"),
        metric("Keep current weight", fmt_pct(plan_summary.get("keep_current_weight_pct")), "sc-blue"),
        metric("Max stock count", plan_summary.get("max_stock_count")),
        metric("Exit candidates", plan_summary.get("exit_count"), "sc-risk"),
        "</div><div class=\"sec-hdr\"><h2>Plan Action Counts</h2><span class=\"sec-sub\">Classification across all 203 holdings.</span></div><div class=\"summary-grid\">",
        action_count_cards(plan_summary.get("action_counts", {})),
        "</div><div class=\"sec-hdr\"><h2>Keep 50 Detail</h2><span class=\"sec-sub\">Current proposed 50-stock book, including owner no-sell core.</span></div>",
        keep_50_table(portfolio),
        "</section>",
        "<section class=\"section\"><div class=\"sec-hdr\"><h2>Decision Legend</h2><span class=\"badge-count\">Research rules</span></div><div class=\"callouts\">",
        "<div class=\"callout risk\"><strong>CLEAN_EXIT</strong><p>Small/no-gain position with weak technicals, weak latest financial evidence, or no portfolio role.</p></div>",
        "<div class=\"callout risk\"><strong>RESOLVE_OR_EXIT</strong><p>Corporate-action or identity gap; resolve tradability/current listing before research.</p></div>",
        "<div class=\"callout warn\"><strong>SELL_TO_RESEARCH_WATCHLIST</strong><p>Exit the small line for simplification, but keep the company on the research watchlist.</p></div>",
        "<div class=\"callout warn\"><strong>VERIFY_BEFORE_EXIT</strong><p>Not a poor business on local evidence; confirm once before selling.</p></div>",
        "</div></section>",
        "<div id=\"tail\"></div>",
    ]

    for action in ("RESOLVE_OR_EXIT", "CLEAN_EXIT", "SELL_TO_RESEARCH_WATCHLIST", "VERIFY_BEFORE_EXIT"):
        action_rows = by_tail_action.get(action, [])
        if not action_rows:
            continue
        parts.append(
            f'<section class="section"><div class="sec-hdr"><h2>{html.escape(action)}</h2>'
            f'<span class="badge-count">{len(action_rows)}</span><span class="sec-sub">Weight {fmt_weight_sum(action_rows)}</span></div>'
            f"{tail_table(action_rows)}</section>"
        )

    parts.extend(
        [
            "<section class=\"section\" id=\"deep\"><div class=\"sec-hdr\"><h2>Remaining Deep Research</h2>",
            f"<span class=\"badge-count\">{len(deep_rows)}</span><span class=\"sec-sub\">Click a stock to collapse or expand its narrative; these are not automatic sells.</span></div>",
            "<div class=\"cards\">",
            "".join(detail_card(row) for row in deep_rows),
            "</div></section>",
            "<section class=\"section\" id=\"full\"><div class=\"sec-hdr\"><h2>Full Combined Holdings Detail</h2>",
            f"<span class=\"badge-count\">{len(portfolio['assessment_rows'])}</span><span class=\"sec-sub\">Broker position, local assessment action, 50-stock plan action, stage, technical, fundamentals, sector and decision rationale in one table.</span></div>",
            combined_portfolio_table(portfolio),
            "</section>",
            "<section class=\"section\" id=\"sources\"><div class=\"sec-hdr\"><h2>Source Trail</h2><span class=\"badge-count\">Reproducible</span></div><div class=\"source-list\">",
            f"<p>Local assessment: <code>{html.escape(summary['source_assessment'])}</code></p>",
            f"<p>50-stock plan: <code>{html.escape(summary['source_50_plan'])}</code></p>",
            f"<p>Staged CSV: <code>{html.escape(summary['source_staged_csv'])}</code></p>",
            '<p class="links"><a href="equity_portfolio_assessment_20260808.html">Full Assessment HTML</a><a href="equity_portfolio_assessment_20260808.csv">Full Assessment CSV</a><a href="equity_portfolio_50_reduction_plan_20260808.csv">50 Plan CSV</a><a href="equity_tail_first_and_remaining_deep_research_20260808.md">Markdown</a><a href="equity_tail_first_and_remaining_deep_research_20260808.csv">Tail CSV</a><a href="equity_tail_first_and_remaining_deep_research_20260808.json">Combined JSON</a></p>',
            "</div></section>",
            f"{script}</main></body></html>",
        ]
    )
    OUTPUT_HTML.write_text("".join(parts), encoding="utf-8")


def write_json(rows: list[dict[str, str]], summary: dict[str, Any], portfolio: dict[str, Any]) -> None:
    payload = {
        "summary": summary,
        "portfolio_summary": portfolio["assessment_summary"],
        "plan_summary": portfolio["plan_summary"],
        "decision_framework": {
            "CLEAN_EXIT": "Small/no-gain position with weak technicals, weak latest financial evidence, or no role in the 50-stock book.",
            "RESOLVE_OR_EXIT": "Corporate-action or identity gap; resolve tradability/current listing before deeper research.",
            "SELL_TO_RESEARCH_WATCHLIST": "Exit/reduce small line for simplification, keep company on research watchlist.",
            "VERIFY_BEFORE_EXIT": "Not a poor business on local evidence; confirm once before selling.",
            "Research watch, not automatic sell": "Current public evidence is not weak enough for a blind sell.",
        },
        "combined_sources": {
            "assessment_csv": str(ASSESSMENT_CSV.relative_to(ROOT)),
            "assessment_json": str(ASSESSMENT_JSON.relative_to(ROOT)),
            "plan_csv": str(PLAN_CSV.relative_to(ROOT)),
            "plan_json": str(PLAN_JSON.relative_to(ROOT)),
            "tail_csv": str(INPUT_CSV.relative_to(ROOT)),
        },
        "portfolio_rows": portfolio["assessment_rows"],
        "plan_rows": portfolio["plan_rows"],
        "rows": rows,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    rows = read_rows()
    summary = build_summary(rows)
    portfolio = load_portfolio_bundle()
    write_markdown(rows, summary)
    write_html(rows, summary, portfolio)
    write_json(rows, summary, portfolio)
    print(
        json.dumps(
            {
                "summary": summary,
                "portfolio_summary": {
                    "holding_count": portfolio["assessment_summary"].get("holding_count"),
                    "total_market_value": portfolio["assessment_summary"].get("total_market_value"),
                    "total_unrealized_pct": portfolio["assessment_summary"].get("total_unrealized_pct"),
                    "keep_count": portfolio["plan_summary"].get("keep_count"),
                    "exit_count": portfolio["plan_summary"].get("exit_count"),
                },
                "outputs": {
                    "markdown": str(OUTPUT_MD.relative_to(ROOT)),
                    "html": str(OUTPUT_HTML.relative_to(ROOT)),
                    "json": str(OUTPUT_JSON.relative_to(ROOT)),
                    "csv": str(INPUT_CSV.relative_to(ROOT)),
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
