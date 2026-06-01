"""Self-contained HTML renderer for Research Council reports."""

from __future__ import annotations

import html
import json
from pathlib import Path

from terminal.research_council.reports.markdown_renderer import DISCLAIMER
from terminal.research_council.reports.markdown_renderer import _execution_display_status
from terminal.research_council.reports.markdown_renderer import _missing_evidence_rows
from terminal.research_council.reports.markdown_renderer import _route_sweep_rows


def render_html(state: object) -> str:
    payload = state.to_dict() if hasattr(state, "to_dict") else {}
    decision = getattr(state, "decision", None)
    pack = getattr(state, "evidence_pack", None)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>Research Council - {html.escape(getattr(state, 'run_id', 'run'))}</title>",
            "<style>",
            _css(),
            "</style>",
            "</head>",
            "<body>",
            "<header>",
            "<h1>Research Dashboard</h1>",
            f"<div class=\"sub\">Research Council · {html.escape(getattr(state, 'mode', 'unknown'))} · "
            f"{html.escape(getattr(state, 'horizon', 'unknown'))} · <b class=\"{_label_class(getattr(decision, 'final_label', None))}\">"
            f"{html.escape(getattr(decision, 'final_label', 'NO_DECISION') if decision else 'NO_DECISION')}</b> · {html.escape(DISCLAIMER)}</div>",
            "</header>",
            '<main class="grid">',
            _section("LLM Research Summary", _llm_summary(state), classes="summary-panel wide"),
            _section("Executive Summary", _executive_summary(state, decision)),
            _section("Market State Snapshot", _market_snapshot(pack)),
            _section("Final Recommendation", _final_recommendation(decision)),
            _section("Candidate Ranking", _candidate_ranking(decision), classes="wide"),
            _section("Evidence Gates", _evidence_gates(state), classes="wide"),
            _section("Candidate Score Drivers", _candidate_score_drivers(decision), classes="wide"),
            _section("Council Deliberation", _agent_findings(state)),
            _section("TOT Branches", _branches(state)),
            _section("Critic Review", _critic_reviews(state)),
            _section("Route Sweep Details", _route_sweep_details(state), classes="wide"),
            _section("Plan", _plans(state)),
            _section("Execution Results", _execution_results(state)),
            _section("Plan Review", _plan_reviews(state)),
            _section("Source Trail", _source_trail(pack)),
            _section("Missing Evidence", _missing_evidence(state)),
            _section("What To Watch Next", _watch_next(state, decision)),
            "</main>",
            f'<script id="council-json" type="application/json">{html.escape(json.dumps(payload, default=str))}</script>',
            f"<footer>{html.escape(DISCLAIMER)}</footer>",
            "</body>",
            "</html>",
        ]
    )


def write_html_report(state: object, *, output_dir: str | Path = "reports/research_council") -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    path = output_path / f"{getattr(state, 'run_id', 'research_council')}.html"
    path.write_text(render_html(state), encoding="utf-8")
    return path


def _section(title: str, body: str, *, classes: str = "") -> str:
    class_attr = f"panel {classes}".strip()
    return f'<section class="{html.escape(class_attr)}"><h2>{html.escape(title)}</h2>\n{body}\n</section>'


def _executive_summary(state: object, decision: object | None) -> str:
    if not decision:
        return "<p>No final decision available.</p>"
    return (
        '<div class="kpi-grid">'
        f'<div class="kpi"><span>Mode</span><b>{html.escape(str(getattr(state, "mode", "unknown")))}</b><em>{html.escape(getattr(state, "horizon", "unknown"))}</em></div>'
        f'<div class="kpi"><span>Decision</span><b class="{_label_class(decision.final_label)}">{html.escape(decision.final_label)}</b><em>{decision.confidence:.2f}</em></div>'
        f'<div class="kpi"><span>Risk</span><b>{html.escape(str(getattr(state, "risk_budget", "unknown")))}</b><em>{html.escape(str(getattr(state, "universe_filter", "unknown")))}</em></div>'
        "</div>"
        f'<p class="objective">{html.escape(getattr(state, "objective", "unknown"))}</p>'
    )


def _llm_summary(state: object) -> str:
    summary = (getattr(state, "flags", {}) or {}).get("llm_report_summary") or {}
    if not summary:
        return "<p>No LLM summary generated for this report.</p>"
    parts = [
        f'<p class="lede">{html.escape(_display(summary.get("headline")))}</p>',
        '<div class="summary-columns">',
        f'<div><h3>Takeaways</h3>{_simple_list(summary.get("key_takeaways") or [])}</div>',
        f'<div><h3>Top Candidates</h3>{_candidate_summary_list(summary.get("top_candidates") or [])}</div>',
        f'<div><h3>Risks / Triggers</h3>{_simple_list((summary.get("risk_flags") or []) + (summary.get("upgrade_triggers") or []))}</div>',
        "</div>",
        f'<small>Summary source: {html.escape(_display(summary.get("source")))}</small>',
    ]
    return "".join(parts)


def _market_snapshot(pack: object | None) -> str:
    if not pack:
        return "<p>Evidence pack unavailable.</p>"
    market = pack.sections.get("market", {})
    return f"<pre>{html.escape(json.dumps(market, indent=2, default=str))}</pre>"


def _agent_findings(state: object) -> str:
    findings = getattr(state, "specialist_findings", {}) or {}
    if not findings:
        return "<p>No specialist findings recorded.</p>"
    items = [
        f'<li><strong>{html.escape(finding.agent)}</strong>: <span class="{_stance_class(finding.stance)}">{html.escape(finding.stance)}</span> - {html.escape(finding.thesis)}</li>'
        for finding in findings.values()
    ]
    return "<ul>" + "".join(items) + "</ul>"


def _branches(state: object) -> str:
    branches = getattr(state, "branch_summaries", []) or []
    if not branches:
        return "<p>No branch summaries recorded.</p>"
    return "<ul>" + "".join(
        f'<li>{html.escape(branch.branch)}: <span class="{_stance_class(branch.stance)}">{html.escape(branch.stance)}</span>; candidates={html.escape(", ".join(branch.candidates) or "none")}</li>'
        for branch in branches
    ) + "</ul>"


def _candidate_ranking(decision: object | None) -> str:
    if not decision or not getattr(decision, "candidates", None):
        return "<p>No candidates ranked.</p>"
    rows = [
        "<table><thead><tr>"
        "<th>Symbol</th><th>Score</th><th>Label</th><th>Branch</th><th>Quant Verdict</th><th>Best Route</th><th>Validation Return</th><th>Symbol Contribution</th>"
        "</tr></thead><tbody>"
    ]
    for candidate in decision.candidates:
        quant = candidate.get("quant_sweep") or {}
        rows.append(
            "<tr>"
            f"<td>{html.escape(_display(candidate.get('symbol')))}</td>"
            f"<td>{html.escape(_display(candidate.get('research_score')))}</td>"
            f'<td><span class="{_label_class(decision.final_label)}">{html.escape(str(decision.final_label))}</span></td>'
            f"<td>{html.escape(_display(candidate.get('supporting_branch')))}</td>"
            f'<td><span class="{_verdict_class(quant.get("verdict"))}">{html.escape(_display(quant.get("verdict")))}</span></td>'
            f"<td>{html.escape(_quant_route(quant))}</td>"
            f"<td>{html.escape(_display(quant.get('validation_return_pct')))}</td>"
            f"<td>{html.escape(_symbol_contribution(quant))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "".join(rows)


def _candidate_score_drivers(decision: object | None) -> str:
    if not decision or not getattr(decision, "candidates", None):
        return "<p>No candidates ranked.</p>"
    items = []
    for candidate in decision.candidates:
        symbol = html.escape(str(candidate.get("symbol", "n/a")))
        drivers = html.escape(_score_driver_text(candidate.get("score_components") or {}))
        items.append(f"<li><strong>{symbol}</strong>: {drivers}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def _evidence_gates(state: object) -> str:
    findings = getattr(state, "specialist_findings", {}) or {}
    rows = [
        "<table><thead><tr><th>Gate</th><th>Status</th><th>Stance</th><th>Evidence Note</th></tr></thead><tbody>"
    ]
    count = 0
    for agent in ("technical", "fno_risk", "fundamental", "catalyst", "sector_rotation"):
        finding = findings.get(agent)
        if not finding:
            continue
        count += 1
        status = "CONFIRMED" if finding.candidates else "PENDING"
        rows.append(
            "<tr>"
            f"<td>{html.escape(agent)}</td>"
            f'<td><span class="{_status_class(status)}">{html.escape(status)}</span></td>'
            f"<td>{html.escape(_display(finding.stance))}</td>"
            f"<td>{html.escape(_display(finding.thesis))}</td>"
            "</tr>"
        )
    if not count:
        rows.append("<tr><td>n/a</td><td>PENDING</td><td>n/a</td><td>No specialist gates recorded.</td></tr>")
    rows.append("</tbody></table>")
    return "".join(rows)


def _plans(state: object) -> str:
    plans = getattr(state, "plans", []) or []
    if not plans:
        return "<p>No plan recorded.</p>"
    rows = []
    for plan in plans:
        rows.append(f"<h3>{html.escape(plan.plan_id)}</h3><ol>")
        rows.extend(f"<li>{html.escape(step.question)}</li>" for step in plan.steps)
        rows.append("</ol>")
    return "".join(rows)


def _execution_results(state: object) -> str:
    results = getattr(state, "execution_results", {}) or {}
    if not results:
        return "<p>No execution results recorded.</p>"
    rows = []
    for plan_id, by_step in results.items():
        rows.append(f"<h3>{html.escape(plan_id)}</h3><ul>")
        for result in by_step.values():
            status, error = _execution_display_status(result)
            rows.append(
                f"<li>{html.escape(result.step_id)}: {html.escape(status)}"
                f"{' - ' + html.escape(error) if error else ''}</li>"
            )
        rows.append("</ul>")
    return "".join(rows)


def _route_sweep_details(state: object) -> str:
    route_rows = _route_sweep_rows(state)
    if not route_rows:
        return "<p>No route sweep details recorded.</p>"
    rows = [
        "<table><thead><tr>"
        "<th>Route</th><th>Verdict</th><th>Validation Return</th><th>Validation Sharpe</th><th>Validation Trades</th><th>Rank/Error</th>"
        "</tr></thead><tbody>"
    ]
    for row in route_rows:
        rows.append(
            "<tr>"
            f"<td>{html.escape(row['route'])}</td>"
            f'<td><span class="{_verdict_class(row["verdict"])}">{html.escape(row["verdict"])}</span></td>'
            f"<td>{html.escape(row['validation_return'])}</td>"
            f"<td>{html.escape(row['validation_sharpe'])}</td>"
            f"<td>{html.escape(row['validation_trades'])}</td>"
            f"<td>{html.escape(row['rank_or_error'])}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "".join(rows)


def _plan_reviews(state: object) -> str:
    reviews = getattr(state, "plan_reviews", []) or []
    if not reviews:
        return "<p>No plan review recorded.</p>"
    rows = []
    for review in reviews:
        rows.append(f"<h3>{html.escape(review.plan_id)}</h3><ul>")
        rows.append(f"<li>Advance: {html.escape(str(review.advance))}</li>")
        rows.append(f"<li>Rationale: {html.escape(review.advance_rationale)}</li>")
        for verdict in review.step_verdicts:
            rows.append(
                f"<li>{html.escape(str(verdict.get('step_id', 'n/a')))}: "
                f"{html.escape(str(verdict.get('status', 'n/a')))}; "
                f"error={html.escape(str(verdict.get('error') or 'none'))}</li>"
            )
        rows.append("</ul>")
    return "".join(rows)


def _critic_reviews(state: object) -> str:
    reviews = [review for group in (getattr(state, "critic_reviews", []) or []) for review in group]
    if not reviews:
        return "<p>No critic reviews recorded.</p>"
    return "<ul>" + "".join(
        f'<li>{html.escape(review.critic)}: <span class="{_severity_class(review.severity_max)}">{html.escape(review.severity_max)}</span> - {html.escape(review.summary)}</li>'
        for review in reviews
    ) + "</ul>"


def _final_recommendation(decision: object | None) -> str:
    if not decision:
        return "<p>No final recommendation available.</p>"
    return f"<p><strong>{html.escape(decision.final_label)}</strong>: {html.escape(decision.rationale)}</p>"


def _source_trail(pack: object | None) -> str:
    if not pack or not pack.source_trail:
        return "<p>No source trail recorded.</p>"
    return "<ul>" + "".join(
        f"<li>{html.escape(entry.source)} latest={html.escape(str(entry.latest_date))} rows={html.escape(str(entry.rows))}</li>"
        for entry in pack.source_trail
    ) + "</ul>"


def _watch_next(state: object, decision: object | None) -> str:
    items = []
    if decision:
        items.extend(decision.dissent_log)
        items.extend(f"{item.scope}/{item.subject}: {item.field}" for item in decision.missing_evidence)
    if not items:
        items.append("Re-run after the next data refresh or material market move.")
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _simple_list(items: list[object]) -> str:
    if not items:
        return "<p>None recorded.</p>"
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items[:6]) + "</ul>"


def _candidate_summary_list(items: list[object]) -> str:
    if not items:
        return "<p>No candidates summarized.</p>"
    rows = []
    for item in items[:5]:
        if not isinstance(item, dict):
            rows.append(f"<li>{html.escape(str(item))}</li>")
            continue
        rows.append(
            f"<li><strong>{html.escape(_display(item.get('symbol')))}</strong>: "
            f"{html.escape(_display(item.get('view')))} - {html.escape(_display(item.get('reason')))}</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>"


def _missing_evidence(state: object) -> str:
    rows = _missing_evidence_rows(state)
    if not rows:
        return "<p>None recorded.</p>"
    return "<ul>" + "".join(
        f"<li>{html.escape(item['scope'])}/{html.escape(item['subject'])}: {html.escape(item['field'])} ({html.escape(item['severity'])})</li>"
        for item in rows
    ) + "</ul>"


def _quant_route(quant: dict) -> str:
    family = quant.get("strategy_family")
    horizon = quant.get("horizon_days")
    if family and horizon:
        return f"{family}/{horizon}d"
    return "n/a"


def _symbol_contribution(quant: dict) -> str:
    attribution = quant.get("symbol_attribution") or {}
    return_pct = attribution.get("validation_return_pct")
    trades = attribution.get("validation_trade_count")
    if return_pct is None and trades is None:
        return "n/a"
    return f"{return_pct if return_pct is not None else 'n/a'} / {trades if trades is not None else 'n/a'} trades"


def _score_driver_text(components: dict) -> str:
    if not components:
        return "no score breakdown recorded."
    fields: list[str] = []
    if components.get("sector_rank") is not None:
        fields.append(f"sector rank #{_format_number(components['sector_rank'])}")
    if components.get("sector_score") is not None:
        fields.append(f"sector score {_format_number(components['sector_score'])}")
    if components.get("supporting_agents") is not None:
        fields.append(f"agents {components['supporting_agents']}")
    if components.get("supporting_branches") is not None:
        fields.append(f"branches {components['supporting_branches']}")
    if components.get("quant_verdict"):
        fields.append(f"quant {components['quant_verdict']}")
    if components.get("quant_route_verdict") and components.get("quant_route_verdict") != components.get("quant_verdict"):
        fields.append(f"route {components['quant_route_verdict']}")
    if components.get("quant_validation_return") is not None:
        fields.append(f"validation {_format_signed_pct(components['quant_validation_return'])}")
    if components.get("quant_symbol_return") is not None:
        fields.append(f"symbol {_format_signed_pct(components['quant_symbol_return'])}")
    if components.get("risk_count") is not None:
        fields.append(f"risks {components['risk_count']}")
    return ", ".join(fields) if fields else "no score breakdown recorded."


def _format_signed_pct(value: object) -> str:
    number = _float_or_none(value)
    if number is None:
        return "n/a"
    sign = "+" if number > 0 else ""
    return f"{sign}{_format_number(number)}%"


def _format_number(value: object) -> str:
    number = _float_or_none(value)
    if number is None:
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _display(value: object) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, float):
        return _format_number(value)
    return str(value)


def _label_class(value: object) -> str:
    text = str(value or "").upper()
    if text in {"RESEARCH_LONG", "SUPPORTED"}:
        return "positive"
    if text in {"WATCHLIST", "WAIT_FOR_CONFIRMATION", "AMBIGUOUS"}:
        return "warning"
    if text in {"NO_TRADE", "REVIEW_MANUALLY", "REFUTED", "NEGATIVE_CONTRIBUTION", "UNTESTABLE"}:
        return "negative"
    return "neutral"


def _verdict_class(value: object) -> str:
    return _label_class(value)


def _status_class(value: object) -> str:
    text = str(value or "").upper()
    if text in {"CONFIRMED", "SUCCESS", "ADVANCED"}:
        return "positive"
    if text in {"PENDING", "DEGRADED", "WARN"}:
        return "warning"
    if text in {"FAILED", "BLOCK", "ERROR"}:
        return "negative"
    return "neutral"


def _severity_class(value: object) -> str:
    text = str(value or "").upper()
    if text == "INFO":
        return "neutral"
    if text == "WARN":
        return "warning"
    if text == "BLOCK":
        return "negative"
    return "neutral"


def _stance_class(value: object) -> str:
    text = str(value or "").lower()
    if any(token in text for token in ("constructive", "support", "targeted", "risk_on")):
        return "positive"
    if any(token in text for token in ("neutral", "wait", "watchlist", "unavailable", "absent")):
        return "warning"
    if any(token in text for token in ("risk_off", "reject", "block")):
        return "negative"
    return "neutral"


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _css() -> str:
    return """
:root { color-scheme: dark; --bg:#081018; --panel:#101a24; --line:#263746; --text:#e7eef5; --muted:#91a4b7; --green:#38d188; --red:#ff5f6d; --yellow:#f7c948; --cyan:#51d6ff; --mag:#d97bff; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header { padding:20px 24px 12px; border-bottom:1px solid var(--line); background:#0b141d; position:sticky; top:0; z-index:2; }
footer { padding:16px 24px; border-top:1px solid var(--line); color:var(--muted); background:#0b141d; }
h1 { margin:0; font-size:22px; letter-spacing:0; }
h2 { margin:0 0 10px; font-size:15px; color:#d8f3ff; letter-spacing:0; }
h3 { margin:10px 0 6px; font-size:13px; color:var(--cyan); letter-spacing:0; }
.sub { color:var(--muted); margin-top:4px; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; padding:16px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; overflow:auto; }
.wide { grid-column:span 3; }
.summary-panel { border-color:#1f4255; background:linear-gradient(180deg,#0f1c28,#101a24); }
.lede { font-size:18px; line-height:1.35; margin:0 0 12px; color:#f4fbff; font-weight:700; }
.summary-columns { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.kpi-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.kpi { border-top:1px solid rgba(255,255,255,.07); padding:8px 0; min-width:0; }
.kpi span, .kpi em { display:block; color:var(--muted); font-size:12px; }
.kpi b { display:block; color:var(--text); margin:3px 0; overflow-wrap:anywhere; }
.metric { display:grid; grid-template-columns:1fr auto auto; gap:10px; align-items:center; border-top:1px solid rgba(255,255,255,.07); padding:7px 0; }
.metric span, .metric em, small, p, li span { color:var(--muted); }
.metric b { color:var(--text); }
.objective { border-top:1px solid rgba(255,255,255,.07); padding-top:10px; margin:10px 0 0; }
ul, ol { margin:8px 0 0 20px; padding:0; }
li { margin:5px 0; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; border-top:1px solid rgba(255,255,255,.08); padding:8px; vertical-align:top; }
th { color:var(--muted); font-weight:700; }
pre { white-space:pre-wrap; background:#07131d; border:1px solid #1f4255; padding:12px; border-radius:6px; overflow:auto; color:#cfe7f7; }
strong { color:#f5fbff; }
.positive { color:var(--green); }
.negative { color:var(--red); }
.warning { color:var(--yellow); }
.neutral { color:var(--muted); }
@media (max-width: 900px) { .grid { grid-template-columns:1fr; } .wide { grid-column:span 1; } .summary-columns, .kpi-grid { grid-template-columns:1fr; } }
"""
