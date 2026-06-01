from __future__ import annotations

import pytest


def test_feature_write_is_restricted_to_feature_directory_and_creates_test_scaffold(tmp_path):
    from terminal.research_council.coder_sandbox import CoderSandbox

    sandbox = CoderSandbox(project_root=tmp_path)
    result = sandbox.write_feature_module(
        "vcp_tightness",
        "def compute(pack):\n    return {'tight': True}\n",
    )

    assert result.feature_path == tmp_path / "terminal/research_council/features/vcp_tightness.py"
    assert result.test_path == tmp_path / "tests/research_council/features/test_vcp_tightness.py"
    assert result.feature_path.read_text(encoding="utf-8").startswith("def compute")
    assert "vcp_tightness" in result.test_path.read_text(encoding="utf-8")


def test_strategy_spec_write_is_restricted_to_strategy_directory(tmp_path):
    from terminal.research_council.coder_sandbox import CoderSandbox

    sandbox = CoderSandbox(project_root=tmp_path)
    path = sandbox.write_strategy_spec("stage2_breakout", '{"family": "stage2_breakout"}')

    assert path == tmp_path / "terminal/research_council/strategies/stage2_breakout.json"
    assert path.read_text(encoding="utf-8") == '{"family": "stage2_breakout"}'


def test_attempt_to_write_outside_sandbox_fails(tmp_path):
    from terminal.research_council.coder_sandbox import CoderSandbox, SandboxViolation

    sandbox = CoderSandbox(project_root=tmp_path)

    with pytest.raises(SandboxViolation, match="outside sandbox"):
        sandbox.write_sandbox_file("../outside.py", "x = 1")


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE market.equity_eod",
        "DELETE FROM market.equity_eod WHERE symbol = 'ABC'",
        "UPDATE market.equity_eod SET close = 0",
        "TRUNCATE TABLE market.equity_eod",
    ],
)
def test_destructive_sql_is_blocked_without_explicit_approval(sql):
    from terminal.research_council.coder_sandbox import CoderSandbox, SandboxViolation

    with pytest.raises(SandboxViolation, match="Destructive SQL"):
        CoderSandbox().validate_sql(sql)


def test_readonly_sql_is_allowed_and_explicit_mutation_approval_is_visible():
    from terminal.research_council.coder_sandbox import CoderSandbox

    sandbox = CoderSandbox()

    assert sandbox.validate_sql("SELECT * FROM market.equity_eod LIMIT 10") is True
    assert sandbox.validate_sql("UPDATE recommendation_reports.runs SET council_status='x'", allow_mutation=True) is True


@pytest.mark.parametrize(
    "source",
    [
        "broker.place_order('BUY', symbol='RELIANCE')",
        "from kiteconnect import KiteConnect\nclient.place_order()",
        "execute_live_order(symbol='TCS')",
    ],
)
def test_live_order_and_broker_code_is_blocked(source):
    from terminal.research_council.coder_sandbox import CoderSandbox, SandboxViolation

    with pytest.raises(SandboxViolation, match="broker/live-order"):
        CoderSandbox().validate_source(source)


def test_feature_ready_requires_matching_feature_and_test_files(tmp_path):
    from terminal.research_council.coder_sandbox import CoderSandbox, SandboxViolation

    sandbox = CoderSandbox(project_root=tmp_path)

    with pytest.raises(SandboxViolation, match="test scaffold"):
        sandbox.assert_feature_ready("vcp_tightness")

    sandbox.write_feature_module("vcp_tightness", "def compute(pack):\n    return {}\n")

    assert sandbox.assert_feature_ready("vcp_tightness") is True
