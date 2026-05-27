from __future__ import annotations

import pandas as pd

from backtesting.strategy_council.types import BacktestSliceResult, StrategySpec
from terminal.research_council.agents.coder_quant import CoderQuantAgent
from terminal.research_council.schemas import StrategyBuildRequest


def test_strategy_build_maps_request_to_strategy_spec():
    request = StrategyBuildRequest(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout with volume confirmation",
        allowed_horizons=[10],
    )

    spec = CoderQuantAgent().to_strategy_spec(request)

    assert isinstance(spec, StrategySpec)
    assert spec.strategy_id == "stage2"
    assert spec.horizon_days == 10
    assert spec.thesis == request.hypothesis
    assert spec.origin == "research_council"
    assert spec.params["strategy_family"] == "stage2_breakout"


def test_strategy_build_runs_train_validation_without_test_split(monkeypatch):
    import terminal.research_council.agents.coder_quant as coder_quant

    called_splits = []

    def fake_run_split(df, spec, *, split_name, initial_capital):
        called_splits.append(split_name)
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics={
                "trade_count": 40 if split_name == "train" else 35,
                "return_pct": 20 if split_name == "train" else 8,
                "sharpe": 1.2 if split_name == "train" else 0.8,
                "win_rate": 0.55,
                "max_drawdown_pct": -6,
                "profit_factor": 1.5,
            },
            trade_count=40 if split_name == "train" else 35,
        )

    monkeypatch.setattr(coder_quant, "run_strategy_spec_on_split", fake_run_split)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=120, freq="D"),
            "open": range(120),
            "high": range(1, 121),
            "low": range(120),
            "close": range(1, 121),
            "volume": [1000] * 120,
        }
    )
    request = StrategyBuildRequest(
        source_branch="minervini_stage2",
        strategy_family="vcp_breakout",
        hypothesis="VCP breakout with volume confirmation",
    )

    output = CoderQuantAgent().run_train_validation(request, frame)

    assert output["ok"] is True
    assert output["result"].verdict == "SUPPORTED"
    assert called_splits == ["train", "validation"]
    assert set(output["backtest_results"]) == {"train", "validation"}
    assert "test" not in output["result"].metrics["splits"]


def test_strategy_build_adapter_blocks_test_split_before_lock():
    from terminal.research_council.tool_adapters import strategy_build

    output = strategy_build(
        source_branch="experimental",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout",
        include_test=True,
    )

    assert output == {
        "ok": False,
        "error": "test_split_locked",
        "message": "test split is locked until strategy commit",
    }


def test_strategy_build_adapter_requires_ai_when_no_eod_data(monkeypatch):
    from terminal.research_council import tool_adapters

    def fake_llm_call(**_):
        return {
            "strategy_family": "stage2_breakout",
            "horizon_days": 10,
            "entry_rules": ["stage is Stage 2", "volume confirms breakout"],
            "exit_rules": ["close loses 50 day moving average"],
            "risk_rules": ["risk no more than 1 percent of capital"],
        }

    monkeypatch.setattr(tool_adapters, "_default_llm_call", lambda: fake_llm_call)

    output = tool_adapters.strategy_build(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout",
    )

    assert output["ok"] is True
    assert output["spec"]["origin"] == "ai_coder_quant"
    assert output["spec"]["params"]["ai_driven"] is True


def test_strategy_build_adapter_reports_unavailable_ai(monkeypatch):
    from terminal.research_council import tool_adapters

    def failing_llm_call(**_):
        raise RuntimeError("Research Council LLM overlays are not enabled yet")

    monkeypatch.setattr(tool_adapters, "_default_llm_call", lambda: failing_llm_call)

    output = tool_adapters.strategy_build(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout",
    )

    assert output["ok"] is False
    assert output["error"] == "llm_unavailable"


def test_strategy_build_adapter_can_run_option_sweep(monkeypatch):
    from terminal.research_council import tool_adapters

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def sweep_train_validation(self, **kwargs):
            captured["sweep"] = kwargs
            return {
                "ok": True,
                "best": {"rank_score": 123},
                "ranked_options": [],
                "untestable": [],
            }

    monkeypatch.setattr(tool_adapters, "CoderQuantAgent", FakeAgent, raising=False)
    output = tool_adapters.strategy_build(
        source_branch="smoke",
        hypothesis="Compare options",
        eod_data=_sample_eod_frame(),
        strategy_families=["stage2_breakout", "vcp_breakout"],
        allowed_horizons=[5, 10],
        sweep=True,
    )

    assert output["ok"] is True
    assert captured["init"]["require_ai"] is False
    assert captured["init"].get("llm_call") is None
    assert captured["sweep"]["strategy_families"] == ["stage2_breakout", "vcp_breakout"]
    assert captured["sweep"]["horizons"] == [5, 10]
    assert captured["sweep"]["source_branch"] == "smoke"


def test_strategy_build_adapter_can_opt_into_ai_designed_sweep(monkeypatch):
    from terminal.research_council import tool_adapters

    captured = {}

    def fake_llm_call(**_):
        return {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def sweep_train_validation(self, **kwargs):
            captured["sweep"] = kwargs
            return {
                "ok": True,
                "best": {"rank_score": 123},
                "ranked_options": [],
                "untestable": [],
            }

    monkeypatch.setattr(tool_adapters, "_default_llm_call", lambda: fake_llm_call)
    monkeypatch.setattr(tool_adapters, "CoderQuantAgent", FakeAgent, raising=False)
    output = tool_adapters.strategy_build(
        source_branch="smoke",
        hypothesis="Compare options",
        eod_data=_sample_eod_frame(),
        strategy_families=["stage2_breakout"],
        allowed_horizons=[5],
        sweep=True,
        ai_design=True,
    )

    assert output["ok"] is True
    assert captured["init"]["require_ai"] is True
    assert captured["init"]["llm_call"] is fake_llm_call


def test_strategy_build_adapter_loads_eod_data_for_symbol_sweep(monkeypatch):
    from terminal.research_council import tool_adapters

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def sweep_train_validation(self, **kwargs):
            captured["sweep"] = kwargs
            return {
                "ok": True,
                "best": {"rank_score": 10},
                "ranked_options": [],
                "untestable": [],
            }

    def fake_load_symbol_eod_history(symbol, **_kwargs):
        frame = _sample_eod_frame().copy()
        frame["symbol"] = symbol
        return frame, [f"loaded:{symbol}"]

    monkeypatch.setattr(tool_adapters, "CoderQuantAgent", FakeAgent, raising=False)
    monkeypatch.setattr(tool_adapters, "_load_symbol_eod_history", fake_load_symbol_eod_history)

    output = tool_adapters.strategy_build(
        source_branch="sector_opportunity",
        hypothesis="Run sector shortlist sweep",
        symbols=["BAJAJ-AUTO", "EXIDEIND"],
        sweep=True,
    )

    assert output["ok"] is True
    assert set(captured["sweep"]["eod_data"]["symbol"]) == {"BAJAJ-AUTO", "EXIDEIND"}
    assert output["symbols"] == ["BAJAJ-AUTO", "EXIDEIND"]
    assert output["eod_source_trail"] == ["BAJAJ-AUTO: loaded:BAJAJ-AUTO", "EXIDEIND: loaded:EXIDEIND"]


def test_strategy_build_persists_spec_and_train_validation_results():
    from terminal.research_council.persistence import save_strategy_build_artifacts

    conn = _FakeConnection()
    request = StrategyBuildRequest(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout with volume confirmation",
    )
    spec = CoderQuantAgent().to_strategy_spec(request)
    result = CoderQuantAgent().evaluate_request(
        request,
        backtest_summary={
            "train": {"trade_count": 40, "return_pct": 20, "sharpe": 1.2, "win_rate": 0.55},
            "validation": {"trade_count": 35, "return_pct": 8, "sharpe": 0.8, "win_rate": 0.54},
            "test": {"trade_count": 99, "return_pct": 99, "sharpe": 9},
        },
    )

    metadata = save_strategy_build_artifacts(
        run_id="run_1",
        request=request,
        spec=spec,
        result=result,
        conn=conn,
    )

    assert metadata == {"status": "saved", "spec_id": "run_1:stage2:5", "count": 2, "schema": "recommendation_reports"}
    assert conn.rows["run_1:stage2:5"]["kind"] == "strategy_spec"
    assert {row["split"] for row in conn.rows.values() if row["kind"] == "backtest_result"} == {"train", "validation"}


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        if "pg_advisory_xact_lock" in sql:
            return
        if "INSERT INTO recommendation_reports.strategy_specs" in sql:
            spec_id, run_id, strategy_family, hypothesis, body = params
            self.conn.rows[spec_id] = {
                "kind": "strategy_spec",
                "spec_id": spec_id,
                "run_id": run_id,
                "strategy_family": strategy_family,
                "hypothesis": hypothesis,
                "body": body,
            }
            return
        if "INSERT INTO recommendation_reports.backtest_results" in sql:
            result_id, spec_id, split, trade_count, win_rate, return_pct, sharpe, max_drawdown_pct, profit_factor, body = params
            self.conn.rows[result_id] = {
                "kind": "backtest_result",
                "result_id": result_id,
                "spec_id": spec_id,
                "split": split,
                "trade_count": trade_count,
                "win_rate": win_rate,
                "return_pct": return_pct,
                "sharpe": sharpe,
                "max_drawdown_pct": max_drawdown_pct,
                "profit_factor": profit_factor,
                "body": body,
            }
            return
        raise AssertionError(f"Unexpected SQL: {sql}")


class _FakeConnection:
    def __init__(self):
        self.rows = {}
        self.commits = 0

    def cursor(self, *args, **kwargs):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1


def _sample_eod_frame():
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=60, freq="D"),
            "symbol": ["AAA"] * 60,
            "open": range(60),
            "high": range(1, 61),
            "low": range(60),
            "close": range(1, 61),
            "volume": [1000] * 60,
        }
    )
