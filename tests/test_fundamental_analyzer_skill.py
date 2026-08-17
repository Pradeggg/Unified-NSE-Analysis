from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(".agents/skills/fundamental-analyze")


def _module():
    path = ROOT / "scripts/fundamental_analyzer.py"
    spec = importlib.util.spec_from_file_location("fundamental_analyzer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _documented_example() -> dict:
    text = (ROOT / "references/input-schema.md").read_text(encoding="utf-8")
    return json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])


def test_documented_example_satisfies_the_bundled_validator():
    analyzer = _module()
    example = _documented_example()

    assert len(example["annuals"]) >= 3
    assert analyzer.validate(example) == []


def test_html_renderer_is_portable_and_includes_institutional_sections():
    analyzer = _module()
    enriched = analyzer.enrich(_documented_example())

    report = analyzer.render_html(enriched)

    assert report.startswith("<!doctype html>")
    assert "Institutional fundamental research" in report
    assert "Peer and industry context" in report
    assert "Valuation scenarios" in report
    assert "Latest quarter: Q1 FY2027" in report
    assert "Balance sheet and capital allocation" in report
    assert "Business quality:" in report
    assert "Normalized PAT" in report
    markdown = analyzer.render_markdown(enriched)
    assert "## Latest quarter: Q1 FY2027" in markdown
    assert "## Balance sheet and capital allocation" in markdown
    assert "Business quality:" in markdown
    assert "<script" not in report.lower()
    assert "http://" not in report.split("<style>", 1)[1].split("</style>", 1)[0]


def test_validator_requires_three_annuals_price_source_and_verdict():
    analyzer = _module()
    example = _documented_example()
    short = json.loads(json.dumps(example))
    short["annuals"] = short["annuals"][:2]
    no_price = json.loads(json.dumps(example))
    no_price["sources"] = [source for source in no_price["sources"] if "price" not in source.get("supports", [])]
    no_verdict = json.loads(json.dumps(example))
    no_verdict["qualitative"].pop("verdict")

    assert any("three periods" in error for error in analyzer.validate(short))
    assert any("as-of price source" in error for error in analyzer.validate(no_price))
    assert any("qualitative.verdict" in error for error in analyzer.validate(no_verdict))


def test_skill_wrappers_share_the_canonical_description():
    canonical = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    description = canonical.split("description: ", 1)[1].split("\n---", 1)[0].strip()
    for path in (
        Path(".claude/skills/fundamental-analyze/SKILL.md"),
        Path(".cursor/skills/fundamental-analyze/SKILL.md"),
    ):
        wrapper = path.read_text(encoding="utf-8")
        assert description in wrapper
        assert "../../../.agents/skills/fundamental-analyze/SKILL.md" in wrapper
