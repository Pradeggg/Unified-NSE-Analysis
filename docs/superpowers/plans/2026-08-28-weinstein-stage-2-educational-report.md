# Weinstein Stage 2 Educational Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish an evergreen Agent Adda educational guide that explains Weinstein Stage 2 in Grade 12 English with traceable historical NSE examples and annotated charts.

**Architecture:** Store researched claims and case-study choices as structured JSON, derive frozen weekly/daily chart datasets from PostgreSQL, and render a standalone HTML guide from deterministic templates. Keep source validation, chart generation, copy/readability checks, and publication as separate gates so no unresolved evidence can reach the public report.

**Tech Stack:** Python 3.14, PostgreSQL/psycopg2, pandas, Agent Adda chart tooling/lightweight-charts, standalone HTML/CSS/JavaScript, pytest, Next.js publisher.

**Spec:** `docs/superpowers/specs/2026-08-28-weinstein-stage-2-educational-report-design.md`

## Global Constraints

- All reader-facing copy is English and understandable to a Grade 12 reader.
- Original Weinstein concepts and Agent Adda additions remain visibly separate.
- Historical examples are frozen, adjusted-price educational cases and never current recommendations.
- Every factual claim and chart is tagged `Sourced`, `Indicative`, or `To Verify`; publication rejects `To Verify`.
- Every chart includes symbol, exchange, timeframe, date range, source, evidence tier, alt text, and selection-bias notice.
- Use weekly charts for the original 30-week method and daily charts only for Agent Adda confirmation.
- Include both the full research-only disclaimer and “Knowledge is the MOAT — Hold, Think, Act.”
- A real failed-breakout company may be named only with neutral chart-pattern framing.
- No notification is sent without explicit confirmation.

---

## File map

- Create `research/weinstein_stage2/source_manifest.json`: structured claims, citations, evidence tiers, and copyright-safe paraphrases.
- Create `research/weinstein_stage2/case_studies.json`: frozen symbols, windows, teaching roles, and selection reasons.
- Create `terminal/weinstein_stage2/models.py`: typed claim, case-study, chart, and report models.
- Create `terminal/weinstein_stage2/evidence.py`: manifest loading and publication-gate validation.
- Create `terminal/weinstein_stage2/data.py`: PostgreSQL EOD loading, weekly aggregation, indicators, and frozen-window extraction.
- Create `terminal/weinstein_stage2/charts.py`: numbered-marker chart payloads and self-contained chart panels.
- Create `terminal/weinstein_stage2/content.py`: Grade 12 educational copy, glossary, comparison, checklist, and disclaimer.
- Create `terminal/weinstein_stage2/render.py`: Agent Adda themed standalone HTML renderer.
- Create `terminal/weinstein_stage2/readability.py`: reading-time and Flesch-Kincaid checks.
- Create `terminal/weinstein_stage2/__init__.py`: package exports.
- Create `scripts/build_weinstein_stage2_guide.py`: deterministic build CLI.
- Create `tests/weinstein_stage2/`: focused unit, rendering, accessibility, and end-to-end tests.
- Generate `reports/education/weinstein-stage-2/`: research manifest snapshot, chart artifacts, HTML, and build audit.

---

### Task 1: Evidence model and publication gate

**Files:**
- Create: `terminal/weinstein_stage2/models.py`
- Create: `terminal/weinstein_stage2/evidence.py`
- Create: `terminal/weinstein_stage2/__init__.py`
- Create: `tests/weinstein_stage2/test_evidence.py`

**Interfaces:**
- Consumes: JSON dictionaries from the source and case-study manifests.
- Produces: `EvidenceClaim`, `CaseStudySpec`, `load_source_manifest(path)`, and `validate_publishable_claims(claims)`.

- [ ] **Step 1: Write failing evidence-gate tests**

```python
from pathlib import Path
import pytest

from terminal.weinstein_stage2.evidence import load_source_manifest, validate_publishable_claims


def test_publication_rejects_to_verify_claim(tmp_path: Path):
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        '[{"id":"w1","text":"Stage 2 follows a base.","tier":"To Verify",'
        '"source_title":"Stan Weinstein","source_url":"https://example.com/source",'
        '"source_type":"authoritative","paraphrase":true}]',
        encoding="utf-8",
    )
    claims = load_source_manifest(manifest)
    with pytest.raises(ValueError, match="To Verify"):
        validate_publishable_claims(claims)


def test_claim_requires_traceable_source(tmp_path: Path):
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        '[{"id":"w1","text":"Stage 2 follows a base.","tier":"Sourced",'
        '"source_title":"","source_url":"","source_type":"authoritative",'
        '"paraphrase":true}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source"):
        load_source_manifest(manifest)
```

- [ ] **Step 2: Run the tests and confirm the missing-package failure**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_evidence.py`

Expected: FAIL because `terminal.weinstein_stage2` does not exist.

- [ ] **Step 3: Implement the typed models and strict loader**

```python
@dataclass(frozen=True)
class EvidenceClaim:
    id: str
    text: str
    tier: Literal["Sourced", "Indicative", "To Verify"]
    source_title: str
    source_url: str
    source_type: Literal["primary", "authoritative", "nse-data", "agent-adda"]
    paraphrase: bool


def validate_publishable_claims(claims: Sequence[EvidenceClaim]) -> None:
    unresolved = [claim.id for claim in claims if claim.tier == "To Verify"]
    if unresolved:
        raise ValueError(f"To Verify claims cannot be published: {', '.join(unresolved)}")
```

The loader must reject blank IDs, text, source titles, source URLs, unsupported tiers, and non-paraphrased copyrighted prose longer than 14 words.

- [ ] **Step 4: Run evidence tests**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_evidence.py`

Expected: PASS.

- [ ] **Step 5: Commit the evidence contract**

```bash
git add terminal/weinstein_stage2 tests/weinstein_stage2/test_evidence.py
git commit -m "feat: add Stage 2 evidence publication gate"
```

---

### Task 2: Research manifest and case-study selection record

**Files:**
- Create: `research/weinstein_stage2/source_manifest.json`
- Create: `research/weinstein_stage2/case_studies.json`
- Create: `research/weinstein_stage2/README.md`
- Modify: `tests/weinstein_stage2/test_evidence.py`

**Interfaces:**
- Consumes: primary/authoritative Weinstein sources and PostgreSQL NSE history.
- Produces: publication-ready claims and exactly five frozen teaching cases consumed by Tasks 3–6.

- [ ] **Step 1: Research only primary or authoritative sources**

Record source title, author/publisher, direct URL, access date, supported claim IDs, and paraphrase notes. Include the original book attribution and authoritative material that supports the four stages, 30-week average, breakout, volume, relative strength, entry discipline, and exit discipline. Keep direct quotation below 15 words per source and prefer no quotation.

- [ ] **Step 2: Write a failing manifest-coverage test**

```python
def test_manifest_covers_original_and_agent_adda_layers():
    claims = load_source_manifest(Path("research/weinstein_stage2/source_manifest.json"))
    ids = {claim.id for claim in claims}
    assert {
        "four-stage-cycle", "thirty-week-average", "base-breakout",
        "volume-confirmation", "relative-strength", "risk-discipline",
        "agent-adda-daily-layer", "selection-bias",
    } <= ids
    validate_publishable_claims(claims)
```

- [ ] **Step 3: Run the coverage test and confirm it fails**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_evidence.py`

Expected: FAIL because the manifests are absent.

- [ ] **Step 4: Write the source and case-study manifests**

Require these exact case-study fields and value types:

```python
required_case_fields = {
    "id": str,
    "symbol": str,  # must begin with "NSE:"
    "role": str,
    "timeframe": str,  # "weekly" or "daily"
    "start_date": str,  # ISO calendar date selected from available EOD history
    "freeze_date": str,  # ISO calendar date selected from available EOD history
    "selection_reason": str,
    "neutral_company_framing": bool,
    "current_recommendation": bool,
}
```

Choose exactly one `full_cycle`, one `clean_stage2_breakout`, one `failed_breakout`, one `mature_stage2`, and one `original_vs_modern`. Populate both date fields from the queried trading history.

- [ ] **Step 5: Validate both manifests**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_evidence.py`

Expected: PASS with no `To Verify` claims.

- [ ] **Step 6: Commit the research record**

```bash
git add research/weinstein_stage2 tests/weinstein_stage2/test_evidence.py
git commit -m "docs: add Weinstein Stage 2 evidence record"
```

---

### Task 3: Frozen historical data and stage features

**Files:**
- Create: `terminal/weinstein_stage2/data.py`
- Create: `tests/weinstein_stage2/test_data.py`
- Create: `tests/weinstein_stage2/fixtures/eod_sample.csv`

**Interfaces:**
- Consumes: `CaseStudySpec` and PostgreSQL `market.equity_eod` rows through the case freeze date.
- Produces: `load_frozen_eod(spec, dsn=None) -> DataFrame`, `to_weekly(frame) -> DataFrame`, and `compute_stage_features(frame, benchmark) -> DataFrame`.

- [ ] **Step 1: Write failing no-look-ahead and weekly-indicator tests**

```python
def test_frozen_window_excludes_rows_after_freeze_date(sample_spec, fixture_frame):
    result = slice_frozen_window(fixture_frame, sample_spec)
    assert result["trade_date"].max().isoformat() == sample_spec.freeze_date


def test_weekly_features_include_30_week_average_and_volume_ratio(fixture_frame):
    weekly = compute_weekly_features(to_weekly(fixture_frame))
    assert {"sma_30w", "sma_30w_slope", "volume_ratio_10w"} <= set(weekly.columns)
    assert weekly["sma_30w"].notna().sum() > 0
```

- [ ] **Step 2: Run data tests and confirm failure**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_data.py`

Expected: FAIL because the data functions do not exist.

- [ ] **Step 3: Implement deterministic frozen-window calculations**

```python
def to_weekly(frame: pd.DataFrame) -> pd.DataFrame:
    indexed = frame.set_index("trade_date").sort_index()
    return indexed.resample("W-FRI").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
    ).dropna(subset=["close"]).reset_index()


def compute_weekly_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["sma_30w"] = out["close"].rolling(30).mean()
    out["sma_30w_slope"] = out["sma_30w"].diff(4)
    out["volume_ratio_10w"] = out["volume"] / out["volume"].rolling(10).mean()
    return out
```

Also compute benchmark-relative strength without using any row later than `freeze_date`. Fail with a clear message when fewer than 40 weekly observations exist.

- [ ] **Step 4: Run data tests**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_data.py`

Expected: PASS.

- [ ] **Step 5: Commit historical-data support**

```bash
git add terminal/weinstein_stage2/data.py tests/weinstein_stage2
git commit -m "feat: add frozen Stage 2 historical datasets"
```

---

### Task 4: Annotated educational chart panels

**Files:**
- Create: `terminal/weinstein_stage2/charts.py`
- Create: `tests/weinstein_stage2/test_charts.py`
- Reuse: `.agents/skills/tradingview-chart/scripts/open_tradingview_chart.py`

**Interfaces:**
- Consumes: frozen weekly/daily feature frames and a `CaseStudySpec`.
- Produces: `build_chart_payload(...) -> dict` and `render_chart_panel(...) -> str` containing local lightweight-charts data, numbered markers, caption legend, and metadata.

- [ ] **Step 1: Write failing chart-contract tests**

```python
def test_chart_panel_has_numbered_markers_and_accessible_metadata(case_spec, weekly_frame):
    panel = render_chart_panel(case_spec, weekly_frame, evidence_tier="Sourced")
    assert 'data-marker="1"' in panel
    assert "Historical educational case study" in panel
    assert 'role="img"' in panel
    assert "NSE:" in panel
    assert "Weekly" in panel
    assert "Sourced" in panel


def test_weekly_chart_uses_30_week_average_not_daily_indicator_stack(case_spec, weekly_frame):
    panel = render_chart_panel(case_spec, weekly_frame, evidence_tier="Sourced")
    assert "30-week moving average" in panel
    assert "Supertrend" not in panel
```

- [ ] **Step 2: Run chart tests and confirm failure**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_charts.py`

Expected: FAIL because chart rendering does not exist.

- [ ] **Step 3: Implement local chart payloads and markers**

```python
def marker(number: int, trade_date: str, price: float, label: str) -> dict[str, object]:
    return {"number": number, "time": trade_date, "price": price, "label": label}


def render_marker_legend(markers: Sequence[dict[str, object]]) -> str:
    return "".join(
        f'<li><span class="marker-number">{item["number"]}</span>{html.escape(str(item["label"]))}</li>'
        for item in markers
    )
```

Use the repository's local `lightweight-charts` implementation and locally sourced NSE data. Do not publish TradingView screenshots, logos, or remotely embedded widgets. Record in the build audit that Agent Adda chart conventions were used while chart data and rendering are local.

- [ ] **Step 4: Run chart tests and canonical chart-skill tests**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_charts.py tests/test_tradingview_chart_skill.py`

Expected: PASS.

- [ ] **Step 5: Commit chart support**

```bash
git add terminal/weinstein_stage2/charts.py tests/weinstein_stage2/test_charts.py
git commit -m "feat: add annotated Stage 2 teaching charts"
```

---

### Task 5: Educational content, glossary, and readability gate

**Files:**
- Create: `terminal/weinstein_stage2/content.py`
- Create: `terminal/weinstein_stage2/readability.py`
- Create: `tests/weinstein_stage2/test_content.py`
- Create: `tests/weinstein_stage2/test_readability.py`

**Interfaces:**
- Consumes: validated claims and case-study chart metadata.
- Produces: `build_guide_sections(...) -> list[GuideSection]`, `build_glossary() -> dict[str, str]`, `flesch_kincaid_grade(text) -> float`, and `reading_minutes(text) -> int`.

- [ ] **Step 1: Write failing separation, glossary, and readability tests**

```python
def test_original_and_agent_adda_rules_are_separate():
    sections = build_guide_sections(sample_claims(), sample_cases())
    original = next(section for section in sections if section.id == "original-method")
    modern = next(section for section in sections if section.id == "agent-adda-layer")
    assert "30-week moving average" in original.text
    assert "Supertrend" not in original.text
    assert "Supertrend" in modern.text
    assert "modern addition" in modern.text.lower()


def test_glossary_contains_every_required_term():
    glossary = build_glossary()
    assert {"moving average", "breakout", "relative strength", "volume", "invalidation", "overhead supply"} <= set(glossary)


def test_core_copy_meets_grade_twelve_target():
    text = core_text(build_guide_sections(sample_claims(), sample_cases()))
    assert flesch_kincaid_grade(text) <= 12.0
    assert 15 <= reading_minutes(text) <= 20
```

- [ ] **Step 2: Run content tests and confirm failure**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_content.py tests/weinstein_stage2/test_readability.py`

Expected: FAIL because content and readability modules do not exist.

- [ ] **Step 3: Implement deterministic copy and readability functions**

```python
def reading_minutes(text: str, words_per_minute: int = 220) -> int:
    words = re.findall(r"\b[\w'-]+\b", text)
    return max(1, math.ceil(len(words) / words_per_minute))


def flesch_kincaid_grade(text: str) -> float:
    words = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text)
    sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
    syllables = sum(count_syllables(word) for word in words)
    return 0.39 * (len(words) / max(1, len(sentences))) + 11.8 * (syllables / max(1, len(words))) - 15.59
```

Write all twelve sections in clear English. Each technical definition must appear both at first use and in the glossary. Include the selection-bias statement, neutral failed-breakout framing, full research disclaimer, and brand sign-off.

- [ ] **Step 4: Run content and readability tests**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_content.py tests/weinstein_stage2/test_readability.py`

Expected: PASS with core grade level at or below 12 and estimated reading time from 15 through 20 minutes.

- [ ] **Step 5: Commit educational content**

```bash
git add terminal/weinstein_stage2/content.py terminal/weinstein_stage2/readability.py tests/weinstein_stage2
git commit -m "feat: add accessible Stage 2 guide content"
```

---

### Task 6: Agent Adda standalone report renderer

**Files:**
- Create: `terminal/weinstein_stage2/render.py`
- Create: `tests/weinstein_stage2/test_render.py`

**Interfaces:**
- Consumes: sections, glossary, chart panels, source manifest, generation date, and review date.
- Produces: `render_guide_html(report: Stage2Guide) -> str`.

- [ ] **Step 1: Write failing rendering and accessibility tests**

```python
def test_report_has_agent_adda_structure_and_compliance(sample_report):
    page = render_guide_html(sample_report)
    assert "Weinstein Stage 2: A Simple Guide" in page
    assert 'class="sticky-contents"' in page
    assert 'class="glossary-drawer"' in page
    assert "Sourced" in page
    assert "selection bias" in page.lower()
    assert "not a SEBI-registered investment adviser" in page
    assert "Knowledge is the MOAT" in page


def test_report_is_publish_safe_and_keyboard_accessible(sample_report):
    page = render_guide_html(sample_report)
    assert "file://" not in page
    assert "To Verify" not in page
    assert "nan%" not in page.lower()
    assert '<button aria-expanded="false"' in page
    assert '<nav aria-label="Guide contents"' in page
    assert "@media print" in page
```

- [ ] **Step 2: Run renderer tests and confirm failure**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_render.py`

Expected: FAIL because the renderer does not exist.

- [ ] **Step 3: Implement the standalone renderer**

```python
def evidence_badge(tier: str) -> str:
    css = {"Sourced": "evidence-sourced", "Indicative": "evidence-indicative"}[tier]
    return f'<span class="evidence-badge {css}">{html.escape(tier)}</span>'


def render_guide_html(report: Stage2Guide) -> str:
    validate_publishable_claims(report.claims)
    return "<!doctype html>" + render_document(report)
```

Use deep navy, muted blue, emerald, amber, and risk red according to the spec. Implement sticky desktop contents, mobile jump menu, persistent desktop glossary, mobile glossary drawer, semantic headings, visible focus states, descriptive alt text, numbered marker legends, and print styles. Essential teaching and risk content must remain visible without JavaScript.

- [ ] **Step 4: Run renderer tests**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_render.py`

Expected: PASS.

- [ ] **Step 5: Commit the renderer**

```bash
git add terminal/weinstein_stage2/render.py tests/weinstein_stage2/test_render.py
git commit -m "feat: render Agent Adda Stage 2 education guide"
```

---

### Task 7: Build CLI, audit artifact, and end-to-end QA

**Files:**
- Create: `scripts/build_weinstein_stage2_guide.py`
- Create: `tests/weinstein_stage2/test_build_guide.py`
- Modify: `report_validation.py`
- Modify: `tests/test_report_validation.py`

**Interfaces:**
- Consumes: source manifest, case-study manifest, PostgreSQL DSN, and output directory.
- Produces: `reports/education/weinstein-stage-2/index.html`, `build_audit.json`, chart artifacts, and a `reports/latest/weinstein_stage2_guide.html` copy.

- [ ] **Step 1: Write a failing end-to-end build test**

```python
def test_build_writes_report_and_clean_audit(tmp_path, fixture_repository):
    result = build_guide(
        source_manifest=fixture_repository / "sources.json",
        case_manifest=fixture_repository / "cases.json",
        output_dir=tmp_path,
        data_provider=fixture_repository.provider,
    )
    html_text = result.html_path.read_text(encoding="utf-8")
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))
    assert result.html_path.is_file()
    assert len(audit["charts"]) == 5
    assert audit["unresolved_claims"] == []
    assert audit["readability_grade"] <= 12.0
    assert "Historical educational case study" in html_text
```

- [ ] **Step 2: Run the build test and confirm failure**

Run: `.venv/bin/pytest -q tests/weinstein_stage2/test_build_guide.py`

Expected: FAIL because the build CLI and validation checkpoint do not exist.

- [ ] **Step 3: Implement the build orchestration**

```python
def build_guide(source_manifest: Path, case_manifest: Path, output_dir: Path, data_provider=None) -> BuildResult:
    claims = load_source_manifest(source_manifest)
    validate_publishable_claims(claims)
    cases = load_case_studies(case_manifest)
    datasets = [load_case_dataset(case, data_provider=data_provider) for case in cases]
    charts = [render_chart_panel(case, dataset, evidence_tier="Sourced") for case, dataset in zip(cases, datasets)]
    report = assemble_stage2_guide(claims=claims, cases=cases, charts=charts)
    return write_build_outputs(report, output_dir)
```

CLI flags: `--sources`, `--cases`, `--output-dir`, `--review-date`, and `--no-open`. Default output is the dated education directory plus the latest copy.

- [ ] **Step 4: Add a `weinstein_stage2` deterministic validation checkpoint**

The checkpoint must verify minimum HTML size, title, twelve section IDs, five chart panels, all required source/date/evidence labels, glossary, selection-bias disclosure, disclaimer, brand sign-off, no `To Verify`, no local links, no visible NaN values, and grade/read-time bounds from `build_audit.json`.

- [ ] **Step 5: Run all focused tests**

Run: `.venv/bin/pytest -q tests/weinstein_stage2 tests/test_report_validation.py tests/test_tradingview_chart_skill.py`

Expected: PASS.

- [ ] **Step 6: Generate and validate the real report**

```bash
.venv/bin/python scripts/build_weinstein_stage2_guide.py --review-date 2026-08-28 --no-open
.venv/bin/python report_validation.py --checkpoint weinstein_stage2
rg -n "To Verify|file://|nan%|>nan<|undefined|REPORT GENERATION FAILED" reports/latest/weinstein_stage2_guide.html
```

Expected: build succeeds; validation has zero high findings; `rg` has no matches.

- [ ] **Step 7: Commit the build pipeline and generated research artifacts**

```bash
git add scripts/build_weinstein_stage2_guide.py terminal/weinstein_stage2 tests/weinstein_stage2 report_validation.py tests/test_report_validation.py research/weinstein_stage2 reports/education/weinstein-stage-2 reports/latest/weinstein_stage2_guide.html
git commit -m "feat: build Weinstein Stage 2 educational guide"
```

---

### Task 8: Visual review, PDF, and public publication

**Files:**
- Generate: `reports/education/weinstein-stage-2/weinstein-stage-2-guide.pdf`
- Modify via publisher: `/Users/pradeepgorai/Documents/Projects/agentadda-www/public/reports/weinstein-stage-2-guide-2026-08-28.html`
- Modify via publisher: `/Users/pradeepgorai/Documents/Projects/agentadda-www/src/content/stocks/reports/weinstein-stage-2-guide-2026-08-28.mdx`

**Interfaces:**
- Consumes: validated standalone HTML.
- Produces: print-checked PDF, public Agent Adda page, standalone public HTML, and draft announcement copy.

- [ ] **Step 1: Render desktop, mobile, and PDF views**

Use a 1440×1000 desktop viewport, a 390×844 mobile viewport, and print-to-PDF. Inspect the hero, sticky navigation, each chart and legend, original/modern comparison, glossary, checklist, sources, disclaimer, and page breaks. Record findings in `reports/education/weinstein-stage-2/visual_qa.md` with `pass` or an exact correction for each area.

- [ ] **Step 2: Fix visual defects through focused failing tests**

For each defect, add a specific assertion to `tests/weinstein_stage2/test_render.py`, run it to observe failure, make the smallest renderer/CSS change, and rerun the focused test before continuing.

- [ ] **Step 3: Run final local verification**

```bash
.venv/bin/pytest -q tests/weinstein_stage2 tests/test_report_validation.py tests/test_tradingview_chart_skill.py
.venv/bin/python report_validation.py --checkpoint weinstein_stage2
git diff --check
```

Expected: all tests pass, zero high QA findings, and no whitespace errors.

- [ ] **Step 4: Dry-run publication without notification**

```bash
.venv/bin/python scripts/push_to_www.py \
  --html reports/latest/weinstein_stage2_guide.html \
  --slug weinstein-stage-2-guide-2026-08-28 \
  --title "Weinstein Stage 2: A Simple Guide to Recognising a Strong Uptrend" \
  --excerpt "An illustrated Agent Adda learning guide to Weinstein Stage 2, historical chart examples, common traps, risk discipline, and modern confirmation tools." \
  --type deep-research \
  --tickers "" \
  --sector "Market Education" \
  --tags "Market Education,Weinstein Stage 2,Technical Analysis,Historical Case Studies" \
  --read-time "20 min read" \
  --date 2026-08-28 \
  --dry-run --no-notify
```

Expected: quality gate passes and both destination paths are correct.

- [ ] **Step 5: Publish, build, and push without notification**

Run the same publisher command without `--dry-run`, adding `--push --no-notify`, then:

```bash
cd /Users/pradeepgorai/Documents/Projects/agentadda-www
npm run build
git status --short --branch
git push origin main
```

Expected: Next.js build succeeds and `main` matches `origin/main`.

- [ ] **Step 6: Verify production URLs and metadata**

```bash
curl -sS -L -o /dev/null -w '%{http_code}\n' https://agentadda.in/stocks/reports/weinstein-stage-2-guide-2026-08-28
curl -sS -L -o /dev/null -w '%{http_code}\n' https://agentadda.in/reports/weinstein-stage-2-guide-2026-08-28.html
curl -sS -L https://agentadda.in/stocks/reports/latest.json | rg "weinstein-stage-2-guide-2026-08-28"
```

Expected: both URLs return `200` and `latest.json` contains the slug.

- [ ] **Step 7: Prepare—but do not send—announcement copy**

Create `reports/education/weinstein-stage-2/announcement.md` with one WhatsApp version and one email version. Include the public link and research-only disclaimer. Stop for explicit recipient and send approval before using any notification command.

- [ ] **Step 8: Commit final visual-QA and announcement artifacts**

```bash
git add reports/education/weinstein-stage-2/visual_qa.md reports/education/weinstein-stage-2/weinstein-stage-2-guide.pdf reports/education/weinstein-stage-2/announcement.md
git commit -m "docs: complete Stage 2 guide publication package"
```
