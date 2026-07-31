# Agent Adda Results Radar Newsletter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Build and validate a publishable Agent Adda Results Radar newsletter from a dated, reviewed Q1 FY27 evidence snapshot.

**Architecture:** Store reviewed facts and editorial classifications in one dated JSON snapshot. A pure Python module validates and enriches that snapshot, renders deterministic Markdown and self-contained HTML, and writes a stable latest alias only after validation succeeds. The build performs no live fetches, so every issue is reproducible from its evidence.

**Tech Stack:** Python 3.13, standard-library JSON/html/pathlib/shutil, pytest, embedded HTML/CSS/SVG, existing \`terminal.report_validation\`.

---

## File Structure

- Create \`terminal/results_radar_newsletter.py\`: calculations, validation, Markdown/HTML renderers, and fail-closed publisher.
- Create \`scripts/build_results_radar_newsletter.py\`: narrow CLI around the pure module.
- Create \`data/newsletters/results_radar_20260731.json\`: reviewed facts, dates, decisions, source links, and evidence gaps.
- Create \`tests/test_results_radar_newsletter.py\`: calculation, validation, rendering, artifact, and accessibility tests.
- Generate \`reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.md\`.
- Generate \`reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.html\`.
- Generate \`reports/latest/results_radar.html\`.

Do not modify \`terminal/results_analysis.py\`; this newsletter is a curated publication layer, not another ingestion path.

### Task 1: Derived metrics and fail-closed evidence validation

**Files:**
- Create: \`terminal/results_radar_newsletter.py\`
- Create: \`tests/test_results_radar_newsletter.py\`

- [ ] **Step 1: Write failing calculation tests**

~~~python
from terminal.results_radar_newsletter import enrich_company, pct_change


def test_pct_change_uses_absolute_base_and_preserves_missing_values():
    assert pct_change(30, 40) == -25.0
    assert pct_change(-5.28, -5.51) == 4.17
    assert pct_change(10, 0) is None
    assert pct_change(None, 10) is None


def test_enrich_company_calculates_growth_margin_and_ttm_pe():
    row = {
        "symbol": "ACME",
        "latest": {"revenue": 120, "pat": 30, "opm_pct": 18, "other_income": 3, "pbt": 35},
        "year_ago": {"revenue": 100, "pat": 20, "opm_pct": 15, "other_income": 2},
        "previous_quarter": {"revenue": 110, "pat": 25, "opm_pct": 17},
        "ttm_eps": 20,
        "price": {"close": 600, "date": "2026-07-30"},
    }
    result = enrich_company(row)["derived"]
    assert result["revenue_yoy_pct"] == 20.0
    assert result["pat_yoy_pct"] == 50.0
    assert result["opm_yoy_pp"] == 3.0
    assert result["pe_ttm_proxy"] == 30.0
    assert result["other_income_to_pbt_pct"] == 8.57
~~~

- [ ] **Step 2: Run tests and verify module collection fails**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py -k 'pct_change or enrich_company'\`

Expected: collection error for missing \`terminal.results_radar_newsletter\`.

- [ ] **Step 3: Implement calculations**

~~~python
from __future__ import annotations

import copy
import html
import json
import math
import shutil
from pathlib import Path
from typing import Any


ALLOWED_LABELS = {"WATCH", "WAIT PULLBACK", "NO-TRADE"}
REQUIRED_META = {
    "publication", "edition", "issue_date", "data_as_of", "price_as_of",
    "headline", "standfirst", "comparison_takeaway", "disclaimer",
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def pct_change(current: Any, base: Any) -> float | None:
    current_number, base_number = _number(current), _number(base)
    if current_number is None or base_number in (None, 0):
        return None
    return round((current_number - base_number) / abs(base_number) * 100, 2)


def point_change(current: Any, base: Any) -> float | None:
    current_number, base_number = _number(current), _number(base)
    if current_number is None or base_number is None:
        return None
    return round(current_number - base_number, 2)


def safe_ratio(numerator: Any, denominator: Any, *, scale: float = 1.0) -> float | None:
    numerator_number, denominator_number = _number(numerator), _number(denominator)
    if numerator_number is None or denominator_number in (None, 0):
        return None
    return round(numerator_number / denominator_number * scale, 2)


def enrich_company(company: dict[str, Any]) -> dict[str, Any]:
    enriched = copy.deepcopy(company)
    latest = enriched.get("latest") or {}
    year_ago = enriched.get("year_ago") or {}
    previous = enriched.get("previous_quarter") or {}
    price = enriched.get("price") or {}
    enriched["derived"] = {
        "revenue_yoy_pct": pct_change(latest.get("revenue"), year_ago.get("revenue")),
        "revenue_qoq_pct": pct_change(latest.get("revenue"), previous.get("revenue")),
        "pat_yoy_pct": pct_change(latest.get("pat"), year_ago.get("pat")),
        "pat_qoq_pct": pct_change(latest.get("pat"), previous.get("pat")),
        "opm_yoy_pp": point_change(latest.get("opm_pct"), year_ago.get("opm_pct")),
        "opm_qoq_pp": point_change(latest.get("opm_pct"), previous.get("opm_pct")),
        "other_income_to_pbt_pct": safe_ratio(latest.get("other_income"), latest.get("pbt"), scale=100),
        "pe_ttm_proxy": safe_ratio(price.get("close"), enriched.get("ttm_eps")),
    }
    return enriched
~~~

- [ ] **Step 4: Run calculation tests**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py -k 'pct_change or enrich_company'\`

Expected: \`2 passed\`.

- [ ] **Step 5: Add failing validation tests**

~~~python
import pytest

from terminal.results_radar_newsletter import validate_snapshot


def test_validate_snapshot_requires_metadata_sources_and_exact_coverage():
    validate_snapshot(sample_snapshot())

    broken = sample_snapshot()
    del broken["meta"]["price_as_of"]
    with pytest.raises(ValueError, match="price_as_of"):
        validate_snapshot(broken)

    broken = sample_snapshot()
    broken["ranked"][0]["decision"] = "BUY"
    with pytest.raises(ValueError, match="decision"):
        validate_snapshot(broken)

    broken = sample_snapshot()
    broken["ranked"][0]["sources"] = []
    with pytest.raises(ValueError, match="sources"):
        validate_snapshot(broken)
~~~

Define \`sample_snapshot()\` in the test file with seven minimal ranked rows and four excluded rows, each with unique symbols and non-empty sources.

- [ ] **Step 6: Implement validation and loading**

~~~python
def validate_snapshot(snapshot: dict[str, Any]) -> None:
    errors: list[str] = []
    meta = snapshot.get("meta") or {}
    missing_meta = sorted(REQUIRED_META - set(meta))
    if missing_meta:
        errors.append("missing metadata: " + ", ".join(missing_meta))
    ranked = snapshot.get("ranked") or []
    excluded = snapshot.get("excluded") or []
    if len(ranked) != 7:
        errors.append(f"ranked coverage must contain 7 companies, found {len(ranked)}")
    if len(excluded) != 4:
        errors.append(f"excluded coverage must contain 4 companies, found {len(excluded)}")
    symbols: set[str] = set()
    for section, rows in (("ranked", ranked), ("excluded", excluded)):
        for index, company in enumerate(rows):
            prefix = f"{section}[{index}]"
            symbol = str(company.get("symbol") or "").strip().upper()
            if not symbol:
                errors.append(f"{prefix} missing symbol")
            elif symbol in symbols:
                errors.append(f"duplicate symbol: {symbol}")
            symbols.add(symbol)
            if not company.get("company"):
                errors.append(f"{prefix} missing company")
            if not company.get("sources"):
                errors.append(f"{prefix} missing sources")
            if section == "ranked":
                if company.get("decision") not in ALLOWED_LABELS:
                    errors.append(f"{prefix} invalid decision: {company.get('decision')}")
                for field in ("basis", "period", "filing_date", "latest", "thesis", "risk"):
                    if not company.get(field):
                        errors.append(f"{prefix} missing {field}")
    if errors:
        raise ValueError("; ".join(errors))


def load_snapshot(path: str | Path) -> dict[str, Any]:
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_snapshot(snapshot)
    snapshot["ranked"] = [enrich_company(row) for row in snapshot["ranked"]]
    return snapshot
~~~

- [ ] **Step 7: Run Task 1 tests**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py -k 'pct_change or enrich_company or validate_snapshot'\`

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 1**

~~~bash
git add terminal/results_radar_newsletter.py tests/test_results_radar_newsletter.py
git commit -m "feat: add results radar evidence model"
~~~

### Task 2: Markdown newsletter renderer

**Files:**
- Modify: \`terminal/results_radar_newsletter.py\`
- Modify: \`tests/test_results_radar_newsletter.py\`

- [ ] **Step 1: Write the failing Markdown contract test**

~~~python
from terminal.results_radar_newsletter import render_markdown


def test_render_markdown_has_editorial_sections_and_labels():
    text = render_markdown(sample_snapshot())
    required = [
        "# Agent Adda Market Intelligence",
        "## The 90-second read",
        "## Result strength vs valuation discipline",
        "## Company reads",
        "## Why these names did not qualify",
        "## Methodology and source trail",
        "Research only, not investment advice",
        "WATCH", "WAIT PULLBACK", "NO-TRADE",
    ]
    assert all(marker in text for marker in required)
    assert "| Rank | Symbol | Revenue YoY | PAT YoY | OPM YoY | Decision |" in text
    assert "None%" not in text
~~~

- [ ] **Step 2: Run the Markdown test and verify it fails**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py::test_render_markdown_has_editorial_sections_and_labels\`

Expected: import failure for missing \`render_markdown\`.

- [ ] **Step 3: Implement formatting and Markdown rendering**

~~~python
def _fmt(value: Any, *, decimals: int = 1, suffix: str = "") -> str:
    number = _number(value)
    if number is None:
        return "Not available"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.{decimals}f}{suffix}"


def _money(value: Any) -> str:
    number = _number(value)
    return "Not available" if number is None else f"₹{number:,.2f} crore"


def _source_markdown(sources: list[dict[str, str]]) -> str:
    return ", ".join(
        f"[{source.get('label') or 'Source'}]({source['url']})"
        if source.get("url") else (source.get("label") or "Source")
        for source in sources
    )


def render_markdown(snapshot: dict[str, Any]) -> str:
    validate_snapshot(snapshot)
    ranked = [enrich_company(row) for row in snapshot["ranked"]]
    meta = snapshot["meta"]
    lines = [
        "# Agent Adda Market Intelligence", "",
        f"## {meta['edition']}", "",
        f"**Published:** {meta['issue_date']}  ",
        f"**Financial evidence through:** {meta['data_as_of']}  ",
        f"**Price evidence through:** {meta['price_as_of']} EOD  ",
        "**Mode:** Research only, not investment advice.", "",
        f"> **{meta['headline']}**", "", meta["standfirst"], "",
        f"> **Investor caution:** {meta['disclaimer']}", "",
        "## The 90-second read", "",
        "| Rank | Symbol | Revenue YoY | PAT YoY | OPM YoY | Decision |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for rank, company in enumerate(ranked, 1):
        metric = company["derived"]
        lines.append(
            f"| {rank} | {company['symbol']} | "
            f"{_fmt(metric['revenue_yoy_pct'], suffix='%')} | "
            f"{_fmt(metric['pat_yoy_pct'], suffix='%')} | "
            f"{_fmt(metric['opm_yoy_pp'], suffix=' pp')} | {company['decision']} |"
        )
    lines += ["", "## Result strength vs valuation discipline", "", meta["comparison_takeaway"], "",
              "| Symbol | TTM P/E proxy | Quality read | Valuation read |",
              "|---|---:|---|---|"]
    for company in ranked:
        lines.append(
            f"| {company['symbol']} | {_fmt(company['derived']['pe_ttm_proxy'])} | "
            f"{company['quality_read']} | {company['valuation_read']} |"
        )
    lines += ["", "## Company reads", ""]
    for company in ranked:
        metric = company["derived"]
        lines += [
            f"### {company['company']} ({company['symbol']}) — {company['decision']}", "",
            f"**Period and basis:** {company['period']} · {company['basis']} · filed {company['filing_date']}", "",
            f"**Result:** Revenue {_money(company['latest'].get('revenue'))}; "
            f"PAT {_money(company['latest'].get('pat'))}; "
            f"EPS {_fmt(company['latest'].get('eps'), decimals=2)}; "
            f"OPM {_fmt(company['latest'].get('opm_pct'), suffix='%')}.", "",
            f"**Growth:** Revenue {_fmt(metric['revenue_yoy_pct'], suffix='%')} YoY and "
            f"{_fmt(metric['revenue_qoq_pct'], suffix='%')} QoQ; "
            f"PAT {_fmt(metric['pat_yoy_pct'], suffix='%')} YoY and "
            f"{_fmt(metric['pat_qoq_pct'], suffix='%')} QoQ; "
            f"OPM change {_fmt(metric['opm_yoy_pp'], suffix=' pp')} YoY.", "",
            f"**Why it ranks here:** {company['thesis']}", "",
            f"**Catalyst:** {company['catalyst']}", "",
            f"**Risk / invalidation:** {company['risk']}", "",
            f"**Sources:** {_source_markdown(company['sources'])}", "",
        ]
    lines += ["## Why these names did not qualify", ""]
    for company in snapshot["excluded"]:
        lines.append(
            f"- **{company['symbol']}:** {company['reason']} "
            f"Sources: {_source_markdown(company['sources'])}"
        )
    lines += ["", "## Methodology and source trail", "", snapshot["methodology"], "",
              "### Data limitations", ""]
    lines += [f"- {item}" for item in snapshot["limitations"]]
    lines += ["", f"**Research only, not investment advice.** {meta['disclaimer']}", ""]
    return "\n".join(lines)
~~~

- [ ] **Step 4: Run Markdown tests**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py -k 'render_markdown'\`

Expected: selected tests pass.

- [ ] **Step 5: Commit Task 2**

~~~bash
git add terminal/results_radar_newsletter.py tests/test_results_radar_newsletter.py
git commit -m "feat: render results radar markdown"
~~~

### Task 3: Self-contained HTML and accessible comparison visual

**Files:**
- Modify: \`terminal/results_radar_newsletter.py\`
- Modify: \`tests/test_results_radar_newsletter.py\`

- [ ] **Step 1: Write failing HTML design tests**

~~~python
from terminal.results_radar_newsletter import render_html


def test_render_html_is_self_contained_accessible_mobile_and_print_ready():
    page = render_html(sample_snapshot())
    assert page.startswith("<!doctype html>")
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in page
    assert "@media (max-width: 760px)" in page
    assert "@media print" in page
    assert "print-color-adjust" in page
    assert '<figure aria-labelledby="strength-map-title">' in page
    assert '<table class="comparison-table">' in page
    assert "<script" not in page
    assert "fonts.googleapis.com" not in page


def test_render_html_escapes_editorial_text():
    snapshot = sample_snapshot()
    snapshot["ranked"][0]["thesis"] = '<script>alert("x")</script>'
    page = render_html(snapshot)
    assert "<script>alert" not in page
    assert "&lt;script&gt;alert" in page
~~~

- [ ] **Step 2: Run HTML tests and verify they fail**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py -k 'render_html'\`

Expected: import failure for missing \`render_html\`.

- [ ] **Step 3: Implement safe HTML helpers and the comparison SVG**

~~~python
def _h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _decision_class(decision: str) -> str:
    return {"WATCH": "watch", "WAIT PULLBACK": "wait", "NO-TRADE": "no-trade"}[decision]


def _strength_score(company: dict[str, Any]) -> float:
    metric = company["derived"]
    revenue = _number(metric.get("revenue_yoy_pct")) or 0
    pat = _number(metric.get("pat_yoy_pct")) or 0
    margin = _number(metric.get("opm_yoy_pp")) or 0
    other_income = _number(metric.get("other_income_to_pbt_pct")) or 0
    return max(0.0, min(100.0, 45 + revenue * .35 + pat * .12 + margin * 3 - other_income * .25))


def _comparison_svg(companies: list[dict[str, Any]]) -> str:
    marks: list[str] = []
    for company in companies:
        pe = _number(company["derived"].get("pe_ttm_proxy"))
        if pe is None:
            continue
        x = max(46, min(704, 46 + pe / 100 * 658))
        y = max(34, min(246, 246 - _strength_score(company) / 100 * 212))
        css = _decision_class(company["decision"])
        marks.append(
            f'<g class="map-mark {css}" transform="translate({x:.1f},{y:.1f})">'
            f'<circle r="6"></circle><text x="9" y="4">{_h(company["symbol"])}</text></g>'
        )
    return (
        '<figure aria-labelledby="strength-map-title">'
        '<figcaption id="strength-map-title"><strong>Result strength vs valuation discipline</strong>'
        '<span>Higher is stronger; farther right is a higher TTM P/E proxy.</span></figcaption>'
        '<svg class="strength-map" viewBox="0 0 760 290" role="img" '
        'aria-label="Comparison of result strength and TTM price earnings proxies">'
        '<rect x="46" y="20" width="658" height="226" rx="8"></rect>'
        '<line x1="46" y1="246" x2="704" y2="246"></line>'
        '<line x1="46" y1="20" x2="46" y2="246"></line>'
        '<text class="axis-label" x="545" y="278">Higher valuation proxy →</text>'
        '<text class="axis-label" x="-185" y="16" transform="rotate(-90)">Stronger result →</text>'
        + "".join(marks) + '</svg></figure>'
    )
~~~

- [ ] **Step 4: Implement semantic page composition**

Implement \`_ranking_row\`, \`_comparison_table\`, \`_company_card\`, and \`_limitations\` as pure builders using \`_h\`, \`_fmt\`, and \`_money\`. Each company card must show basis, filing date, result values, YoY/QoQ changes, other-income warning, price date, catalyst, risk/invalidation, decision, evidence gaps, and source links.

~~~python
def render_html(snapshot: dict[str, Any]) -> str:
    validate_snapshot(snapshot)
    ranked = [enrich_company(row) for row in snapshot["ranked"]]
    meta = snapshot["meta"]
    ranking = "".join(_ranking_row(rank, row) for rank, row in enumerate(ranked, 1))
    cards = "".join(_company_card(row) for row in ranked)
    excluded = "".join(
        f'<li><strong>{_h(row["symbol"])}</strong>: {_h(row["reason"])}</li>'
        for row in snapshot["excluded"]
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_h(meta["edition"])}</title><style>{_CSS}</style></head><body>'
        '<main class="page">'
        f'<header class="mast"><div class="brand">{_h(meta["publication"])}</div>'
        f'<div class="eyebrow">{_h(meta["edition"])} · {_h(meta["issue_date"])}</div>'
        f'<h1>{_h(meta["headline"])}</h1><p class="standfirst">{_h(meta["standfirst"])}</p>'
        f'<p class="boundary">Financial evidence: {_h(meta["data_as_of"])} · '
        f'Prices: {_h(meta["price_as_of"])} EOD</p></header>'
        '<section aria-labelledby="quick-read"><h2 id="quick-read">The 90-second read</h2>'
        f'<div class="ranking" role="table">{ranking}</div></section>'
        '<section aria-labelledby="comparison"><h2 id="comparison">'
        'Result strength vs valuation discipline</h2>'
        f'<p>{_h(meta["comparison_takeaway"])}</p>{_comparison_svg(ranked)}'
        f'{_comparison_table(ranked)}</section>'
        '<section aria-labelledby="company-reads"><h2 id="company-reads">Company reads</h2>'
        f'<div class="company-grid">{cards}</div></section>'
        '<section aria-labelledby="excluded"><h2 id="excluded">Why these names did not qualify</h2>'
        f'<ul>{excluded}</ul></section>'
        '<section aria-labelledby="method"><h2 id="method">Methodology and source trail</h2>'
        f'<p>{_h(snapshot["methodology"])}</p>{_limitations(snapshot["limitations"])}</section>'
        f'<aside class="disclaimer"><strong>Research only, not investment advice.</strong> '
        f'{_h(meta["disclaimer"])}</aside></main></body></html>'
    )
~~~

- [ ] **Step 5: Add approved color, responsive, and print CSS**

Define \`_CSS\` with: forest \`#12372d\`, green \`#1e7a5c\`, cream \`#f6f1e7\`, paper \`#fffdf8\`, ink \`#18221f\`, amber \`#a96f17\`, and brick \`#9a413c\`. Include:

~~~css
*{box-sizing:border-box}
body{margin:0;font:15px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.page{max-width:1080px;margin:auto;background:#fffdf8}
.mast{padding:42px 44px 34px;background:#12372d;color:#fff}
.mast h1{font:700 clamp(38px,7vw,72px)/.98 Georgia,serif}
section{padding:30px 44px;border-bottom:1px solid #d8ddd9}
.rank-row{display:grid;grid-template-columns:44px 1.3fr repeat(3,1fr) 1.2fr}
.company-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.watch{color:#1e7a5c}.wait{color:#a96f17}.no-trade{color:#9a413c}
@media (max-width: 760px){
  .mast,section,.disclaimer{padding-left:20px;padding-right:20px}
  .rank-row{grid-template-columns:32px 1fr}
  .company-grid{grid-template-columns:1fr}
}
@media print{
  @page{size:A4;margin:13mm}
  .page{box-shadow:none}
  .mast{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .company-card{break-inside:avoid}
  a{color:inherit;text-decoration:none}
}
~~~

Expand the production CSS only with rules required for the markup: table borders, metric grids, source notes, visible focus outlines, warning blocks, SVG axes/marks, and mobile row labels.

- [ ] **Step 6: Run HTML tests**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py -k 'render_html'\`

Expected: selected tests pass.

- [ ] **Step 7: Commit Task 3**

~~~bash
git add terminal/results_radar_newsletter.py tests/test_results_radar_newsletter.py
git commit -m "feat: render accessible results radar html"
~~~

### Task 4: Fail-closed publisher and CLI

**Files:**
- Create: \`scripts/build_results_radar_newsletter.py\`
- Modify: \`terminal/results_radar_newsletter.py\`
- Modify: \`tests/test_results_radar_newsletter.py\`

- [ ] **Step 1: Write failing publisher tests**

~~~python
import json
import pytest

from terminal.results_radar_newsletter import publish_newsletter


def test_publish_writes_dated_and_latest_after_validation(tmp_path):
    source = tmp_path / "issue.json"
    source.write_text(json.dumps(sample_snapshot()), encoding="utf-8")
    latest = tmp_path / "latest" / "results_radar.html"
    paths = publish_newsletter(source, output_root=tmp_path / "dated", latest_html=latest)
    assert paths["markdown"].name == "Agent_Adda_Results_Radar_20260731.md"
    assert paths["html"].name == "Agent_Adda_Results_Radar_20260731.html"
    assert latest.read_bytes() == paths["html"].read_bytes()


def test_publish_does_not_overwrite_latest_on_invalid_snapshot(tmp_path):
    broken = sample_snapshot()
    broken["ranked"] = []
    source = tmp_path / "issue.json"
    source.write_text(json.dumps(broken), encoding="utf-8")
    latest = tmp_path / "latest" / "results_radar.html"
    latest.parent.mkdir(parents=True)
    latest.write_text("known-good", encoding="utf-8")
    with pytest.raises(ValueError):
        publish_newsletter(source, output_root=tmp_path / "dated", latest_html=latest)
    assert latest.read_text(encoding="utf-8") == "known-good"
~~~

- [ ] **Step 2: Run publisher tests and verify they fail**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py -k 'publish'\`

Expected: import failure for missing \`publish_newsletter\`.

- [ ] **Step 3: Implement publication**

~~~python
def publish_newsletter(
    snapshot_path: str | Path,
    *,
    output_root: str | Path,
    latest_html: str | Path,
) -> dict[str, Path]:
    snapshot = load_snapshot(snapshot_path)
    issue_date = str(snapshot["meta"]["issue_date"]).replace("-", "")
    name = f"Agent_Adda_Results_Radar_{issue_date}"
    year_dir = Path(output_root) / issue_date[:4]
    year_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = year_dir / f"{name}.md"
    html_path = year_dir / f"{name}.html"
    markdown_text = render_markdown(snapshot).rstrip() + "\n"
    html_text = render_html(snapshot)
    if "not investment advice" not in html_text.lower():
        raise ValueError("HTML missing investor caution")
    if any(token in html_text for token in ("{{", "}}", "[insert]")):
        raise ValueError("HTML contains unresolved template token")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    latest_path = Path(latest_html)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(html_path, latest_path)
    return {"markdown": markdown_path, "html": html_path, "latest_html": latest_path}
~~~

- [ ] **Step 4: Create the CLI**

~~~python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from terminal.results_radar_newsletter import publish_newsletter


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Agent Adda Results Radar newsletter")
    parser.add_argument("--snapshot", default=str(ROOT / "data/newsletters/results_radar_20260731.json"))
    parser.add_argument("--output-root", default=str(ROOT / "reports/newsletters/results_radar"))
    parser.add_argument("--latest-html", default=str(ROOT / "reports/latest/results_radar.html"))
    args = parser.parse_args()
    paths = publish_newsletter(
        args.snapshot,
        output_root=args.output_root,
        latest_html=args.latest_html,
    )
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
~~~

- [ ] **Step 5: Run publisher and full focused tests**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py\`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 4**

~~~bash
git add scripts/build_results_radar_newsletter.py terminal/results_radar_newsletter.py tests/test_results_radar_newsletter.py
git commit -m "feat: publish results radar newsletter"
~~~

### Task 5: Build the reviewed 31 July evidence snapshot

**Files:**
- Create: \`data/newsletters/results_radar_20260731.json\`
- Modify: \`tests/test_results_radar_newsletter.py\`

- [ ] **Step 1: Add a failing current-issue contract test**

~~~python
from pathlib import Path

from terminal.results_radar_newsletter import load_snapshot


ISSUE = Path("data/newsletters/results_radar_20260731.json")


def test_current_issue_has_approved_symbols_and_reconciliations():
    snapshot = load_snapshot(ISSUE)
    ranked = {row["symbol"]: row for row in snapshot["ranked"]}
    excluded = {row["symbol"]: row for row in snapshot["excluded"]}
    assert list(ranked) == [
        "PAUSHAKLTD", "SILVERTUC", "LALPATHLAB", "LAURUSLABS",
        "RADICO", "LICHSGFIN", "WELCORP",
    ]
    assert set(excluded) == {"ACI", "SIYSIL", "QUICKHEAL", "MALLCOM"}
    assert ranked["PAUSHAKLTD"]["decision"] == "WATCH"
    assert ranked["LAURUSLABS"]["decision"] == "WAIT PULLBACK"
    assert ranked["WELCORP"]["decision"] == "NO-TRADE"
    assert ranked["WELCORP"]["latest"]["other_income"] == 685
    assert "NIM" in ranked["LICHSGFIN"]["evidence_gaps"]
    assert excluded["QUICKHEAL"]["latest_pat"] < 0
~~~

- [ ] **Step 2: Run the contract test and verify the snapshot is missing**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py::test_current_issue_has_approved_symbols_and_reconciliations\`

Expected: \`FileNotFoundError\`.

- [ ] **Step 3: Re-extract reviewed financial facts**

Run:

~~~bash
psql "dbname=nse_market user=nse_admin host=/tmp" -P pager=off -F $'\t' -A -c "
SELECT symbol, period_label, period_end, revenue, operating_profit, opm_pct,
       other_income, interest, pbt, pat, eps, fetched_at
FROM scores.quarterly_results
WHERE symbol IN ('PAUSHAKLTD','SILVERTUC','LALPATHLAB','LAURUSLABS','RADICO',
                 'LICHSGFIN','WELCORP','ACI','SIYSIL','QUICKHEAL','MALLCOM')
ORDER BY symbol, period_end DESC;
"
rg '"(PAUSHAKLTD|SILVERTUC|LALPATHLAB|LAURUSLABS|RADICO|LICHSGFIN|WELCORP|ACI|SIYSIL|QUICKHEAL|MALLCOM)".*2026-07-(29|30)' data/nse_sec_full_data.csv
pdftotext -layout data/filings/PAUSHAKLTD/LATEST/raw/annpdfopen.aspx - | sed -n '1,180p'
~~~

Reconcile source URLs against each \`data/filings/<SYMBOL>/LATEST/manifest.json\` or the existing result-analysis page.

- [ ] **Step 4: Create the evidence snapshot**

Use this exact top-level structure:

~~~json
{
  "meta": {
    "publication": "Agent Adda Market Intelligence",
    "edition": "Results Radar — Q1 FY27 Special Edition",
    "issue_date": "2026-07-31",
    "data_as_of": "2026-07-31 09:12 IST",
    "price_as_of": "2026-07-30",
    "headline": "Clean beats are scarce. Price discipline matters more.",
    "standfirst": "Paushak leads the newest filing batch; Dr. Lal PathLabs and Laurus Labs deliver the cleanest operating evidence, while headline profit growth at Welspun Corp needs adjustment.",
    "comparison_takeaway": "The cleanest operating acceleration sits in Laurus Labs and Dr. Lal PathLabs, but both carry demanding valuation proxies. Paushak offers the strongest fresh result-and-reaction combination, subject to liquidity and confirmation.",
    "disclaimer": "This publication is for education and general market research. It is not personalised advice, a solicitation, or a recommendation to transact. Verify all data independently and consult a SEBI-registered investment adviser before acting."
  },
  "ranked": [],
  "excluded": [],
  "methodology": "Companies are ranked using reported growth, margin direction, other-income contribution, balance-sheet and cash-conversion evidence, valuation proxy, price reaction, liquidity, and source completeness. A strong result is not treated as an automatic buy.",
  "limitations": [
    "Local equity prices and volume observations are through 30 July 2026 EOD.",
    "TTM P/E values are explicitly labelled proxies and omitted when four comparable EPS quarters are unavailable.",
    "LIC Housing Finance requires NIM, asset-quality, credit-cost, and loan-growth evidence beyond revenue and PAT.",
    "Beat or miss language is not used because a consistent sourced estimates set is unavailable."
  ]
}
~~~

Populate ranked rows in the approved order with these fields: \`symbol\`, \`company\`, \`sector\`, \`period\`, \`basis\`, \`filing_date\`, \`decision\`, \`latest\`, \`year_ago\`, \`previous_quarter\`, \`ttm_eps\`, \`price\`, \`quality_read\`, \`valuation_read\`, \`thesis\`, \`catalyst\`, \`risk\`, \`evidence_gaps\`, and \`sources\`.

Populate excluded rows with: \`symbol\`, \`company\`, \`reason\`, \`latest_pat\`, and \`sources\`.

Use JSON \`null\` for unavailable evidence. Store Paushak Q1 values as revenue \`83.55\`, PBT \`19.02\`, PAT \`15.10\`, EPS \`6.13\`, other income \`3.15\`; store prior-year revenue/PBT/PAT/EPS/other income as \`55.88\`, \`15.63\`, \`12.03\`, \`4.88\`, and \`1.88\` crore. Store Welspun Corp other income as \`685\` crore versus \`84\` crore a year earlier.

- [ ] **Step 5: Run the current-issue contract test**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py::test_current_issue_has_approved_symbols_and_reconciliations\`

Expected: \`1 passed\`.

- [ ] **Step 6: Commit Task 5**

~~~bash
git add data/newsletters/results_radar_20260731.json tests/test_results_radar_newsletter.py
git commit -m "data: add reviewed results radar evidence"
~~~

### Task 6: Generate, validate, and visually review the issue

**Files:**
- Generate: \`reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.md\`
- Generate: \`reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.html\`
- Generate: \`reports/latest/results_radar.html\`
- Modify: \`tests/test_results_radar_newsletter.py\`

- [ ] **Step 1: Run tests before generation**

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py tests/test_report_validation_links.py\`

Expected: all tests pass.

- [ ] **Step 2: Generate artifacts**

Run: \`.venv/bin/python scripts/build_results_radar_newsletter.py\`

Expected output lists the dated Markdown, dated HTML, and stable latest HTML paths.

- [ ] **Step 3: Add an artifact contract test**

~~~python
from terminal.report_validation import validate_html_report


def test_generated_results_radar_artifacts_are_publishable():
    html_path = Path("reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.html")
    markdown_path = html_path.with_suffix(".md")
    latest_path = Path("reports/latest/results_radar.html")
    assert html_path.stat().st_size > 20_000
    assert markdown_path.stat().st_size > 8_000
    assert latest_path.read_bytes() == html_path.read_bytes()
    page = html_path.read_text(encoding="utf-8")
    symbols = (
        "PAUSHAKLTD", "SILVERTUC", "LALPATHLAB", "LAURUSLABS",
        "RADICO", "LICHSGFIN", "WELCORP", "ACI", "SIYSIL", "QUICKHEAL", "MALLCOM",
    )
    assert all(symbol in page for symbol in symbols)
    assert all(token not in page for token in ("{{", "}}", "[insert]"))
    assert validate_html_report(html_path).summary()["fail"] == 0
~~~

Run: \`.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py::test_generated_results_radar_artifacts_are_publishable\`

Expected: \`1 passed\`.

- [ ] **Step 4: Run direct link validation**

~~~bash
.venv/bin/python -c "from terminal.report_validation import validate_html_report; r=validate_html_report('reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.html'); print(r.summary()); raise SystemExit(1 if r.summary()['fail'] else 0)"
~~~

Expected: summary contains \`fail: 0\`.

- [ ] **Step 5: Capture and inspect desktop and mobile screenshots**

~~~bash
npx playwright screenshot --viewport-size=1440,1200 "file://$PWD/reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.html" /tmp/results-radar-desktop.png
npx playwright screenshot --viewport-size=390,844 "file://$PWD/reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.html" /tmp/results-radar-mobile.png
~~~

Inspect both images. Confirm no clipped text, overlapping labels, horizontal page overflow, unreadable disclosures, or detached source notes. If SVG labels collide, adjust only the affected label offsets, rerun HTML tests, regenerate, and recapture both screenshots.

- [ ] **Step 6: Run final verification**

~~~bash
.venv/bin/python -m pytest -q tests/test_results_radar_newsletter.py tests/test_report_validation_links.py
git diff --check
git status --short -- terminal/results_radar_newsletter.py scripts/build_results_radar_newsletter.py tests/test_results_radar_newsletter.py data/newsletters/results_radar_20260731.json reports/newsletters/results_radar/2026 reports/latest/results_radar.html
~~~

Expected: tests pass; \`git diff --check\` is silent; scoped status lists only Results Radar files.

- [ ] **Step 7: Commit the publishable issue**

~~~bash
git add terminal/results_radar_newsletter.py scripts/build_results_radar_newsletter.py tests/test_results_radar_newsletter.py data/newsletters/results_radar_20260731.json reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.md reports/newsletters/results_radar/2026/Agent_Adda_Results_Radar_20260731.html reports/latest/results_radar.html
git commit -m "feat: publish Q1 FY27 results radar"
~~~
