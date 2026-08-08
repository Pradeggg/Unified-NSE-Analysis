from __future__ import annotations

from tools.smallcap_daily_monitor import artifact_paths, build_monitor_summary, parse_rows


def test_monitor_summary_flags_blocked_trigger_and_no_order() -> None:
    csv_text = """symbol,company,readiness_overlay_100,trigger_state,action_bucket,latest_price,result_status
SKYGOLD,Sky Gold,65.3,TRIGGER_TOUCHED_BUT_BLOCKED,No order: trigger touched before evidence cleared,719.4,Q1 pending
GLAND,Gland Pharma,64.5,NEAR_BREAKOUT_BUT_WAIT,Refresh first,2601.0,Board event pending
RRKABEL,R R Kabel,63.4,WAIT,Retest only,2759.5,Fresh result
SYRMA,Syrma SGS,77.8,WAIT,Evidence pack / governance review,1424.7,Fresh result
"""
    rows = parse_rows(csv_text)

    summary = build_monitor_summary(rows)

    assert summary["total_symbols"] == 4
    assert summary["paper_order_allowed"] is False
    assert summary["blocked_trigger_symbols"] == ["SKYGOLD"]
    assert summary["refresh_first_symbols"] == ["GLAND"]
    assert summary["retest_only_symbols"] == ["RRKABEL"]
    assert summary["governance_review_symbols"] == ["SYRMA"]
    assert summary["top_readiness_symbols"] == ["SYRMA", "SKYGOLD", "GLAND", "RRKABEL"]


def test_monitor_summary_allows_trigger_review_only_without_blocking_action() -> None:
    csv_text = """symbol,company,readiness_overlay_100,trigger_state,action_bucket,latest_price,result_status
ABC,Alpha Beta,82.0,TRIGGER_READY_REVIEW,Trigger review,100.0,Fresh official result
XYZ,Xylon,72.0,WAIT,Watch trigger,50.0,Fresh official result
"""
    rows = parse_rows(csv_text)

    summary = build_monitor_summary(rows)

    assert summary["paper_order_allowed"] is True
    assert summary["trigger_review_symbols"] == ["ABC"]
    assert summary["blocked_trigger_symbols"] == []


def test_artifact_paths_are_dated_for_daily_runs() -> None:
    paths = artifact_paths("20260809")

    assert paths["csv"].as_posix().endswith("agent_adda_smallcap_research_update_20260809.csv")
    assert paths["md"].as_posix().endswith("2026-08-09-smallcap-portfolio-research-update.md")
    assert paths["html"].as_posix().endswith("agent_adda_smallcap_research_update_20260809.html")
