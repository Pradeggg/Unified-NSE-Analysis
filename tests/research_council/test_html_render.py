from tests.research_council.test_markdown_render import _state

from terminal.research_council.reports.html_renderer import render_html, write_html_report
from terminal.research_council.states import render_html as render_state


def test_html_renderer_contains_required_static_sections_and_json():
    html = render_html(_state())

    for marker in [
        "<!doctype html>",
        "Research Dashboard",
        "LLM Research Summary",
        "Executive Summary",
        "Market State Snapshot",
        "Council Deliberation",
        "TOT Branches",
        "Plan",
        "Execution Results",
        "Critic Review",
        "Final Recommendation",
        "Source Trail",
        "What To Watch Next",
        "Not investment advice. For research and learning only.",
        'id="council-json"',
    ]:
        assert marker in html
    assert "https://" not in html
    assert "AAA" in html


def test_html_renderer_uses_dashboard_theme_and_summary_cards():
    state = _state()
    data = state.to_dict()
    data["flags"]["llm_report_summary"] = {
        "headline": "Watchlist only until confirmation improves.",
        "stance": "WATCHLIST",
        "key_takeaways": ["AAA has constructive evidence.", "F&O confirmation is missing."],
        "top_candidates": [{"symbol": "AAA", "view": "Watch", "reason": "Needs derivatives confirmation."}],
        "upgrade_triggers": ["Technical and F&O gates confirm."],
        "risk_flags": ["Missing F&O evidence."],
        "source": "llm",
    }

    html = render_html(_state().__class__.from_dict(data))

    assert ":root { color-scheme: dark;" in html
    assert '<main class="grid">' in html
    assert 'class="panel summary-panel wide"' in html
    assert 'class="kpi-grid"' in html
    assert "Watchlist only until confirmation improves." in html
    assert "AAA" in html
    assert "Missing F&amp;O evidence." in html


def test_write_html_report_creates_self_contained_html(tmp_path):
    path = write_html_report(_state(), output_dir=tmp_path)

    assert path.name == "research_1.html"
    assert path.read_text().startswith("<!doctype html>")


def test_render_state_writes_markdown_and_html_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(render_state, "REPORT_DIR", tmp_path)

    updated = render_state.run(_state())

    assert updated.flags["markdown_report_path"] == str(tmp_path / "research_1.md")
    assert updated.flags["html_report_path"] == str(tmp_path / "research_1.html")
    assert (tmp_path / "research_1.md").exists()
    assert (tmp_path / "research_1.html").exists()


def test_render_state_injects_llm_summary_into_html(tmp_path, monkeypatch):
    monkeypatch.setattr(render_state, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(
        render_state,
        "build_report_summary",
        lambda state: {
            "headline": "LLM says watchlist only.",
            "stance": "WATCHLIST",
            "key_takeaways": ["Evidence is not complete."],
            "top_candidates": [{"symbol": "AAA", "view": "Watch", "reason": "Pending confirmation."}],
            "upgrade_triggers": ["Confirm F&O."],
            "risk_flags": ["Missing F&O evidence."],
            "source": "llm",
        },
    )

    updated = render_state.run(_state())

    assert updated.flags["llm_report_summary"]["headline"] == "LLM says watchlist only."
    assert "LLM says watchlist only." in (tmp_path / "research_1.html").read_text()
