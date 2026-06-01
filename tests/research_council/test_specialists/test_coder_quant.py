from __future__ import annotations

import pandas as pd

from terminal.research_council.schemas import StrategyBuildRequest, StrategyBuildResult


def test_coder_quant_builds_strategy_request_from_viable_branch():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    request = CoderQuantAgent().build_request(
        source_branch="minervini_stage2",
        hypothesis="Stage 2 breakout with volume confirmation",
        strategy_family="stage2_breakout",
        required_features=["stage", "relative_strength", "volume_ratio"],
    )

    assert isinstance(request, StrategyBuildRequest)
    assert request.source_branch == "minervini_stage2"
    assert request.strategy_family == "stage2_breakout"
    assert request.hypothesis == "Stage 2 breakout with volume confirmation"
    assert request.required_features == ["stage", "relative_strength", "volume_ratio"]
    assert request.split_policy == "train_validation_test_time_ordered"


def test_coder_quant_rejects_out_of_whitelist_family_as_untestable():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    result = CoderQuantAgent().evaluate_request(
        StrategyBuildRequest(
            source_branch="experimental",
            strategy_family="mean_reversion_ai",
            hypothesis="Use unrestricted AI mean reversion",
        )
    )

    assert isinstance(result, StrategyBuildResult)
    assert result.verdict == "UNTESTABLE"
    assert "not whitelisted" in result.limitations[0]
    assert result.metrics["trade_count"] == 0


def test_coder_quant_returns_ambiguous_when_trade_count_is_too_low():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    result = CoderQuantAgent().evaluate_request(
        StrategyBuildRequest(
            source_branch="minervini_stage2",
            strategy_family="stage2_breakout",
            hypothesis="Stage 2 breakout with volume confirmation",
        ),
        backtest_summary={
            "train": {"trade_count": 18, "return_pct": 12, "sharpe": 1.0, "win_rate": 0.55},
            "validation": {"trade_count": 9, "return_pct": 4, "sharpe": 0.8, "win_rate": 0.52},
            "test": {"trade_count": 50, "return_pct": 99, "sharpe": 5.0},
        },
    )

    assert result.verdict == "AMBIGUOUS"
    assert result.metrics["trade_count"] == 27
    assert "below 30 trades" in result.limitations
    assert "test" not in result.metrics


def test_coder_quant_supported_result_exposes_train_validation_only():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    result = CoderQuantAgent().evaluate_request(
        StrategyBuildRequest(
            source_branch="minervini_stage2",
            strategy_family="vcp_breakout",
            hypothesis="VCP breakout with volume confirmation",
        ),
        backtest_summary={
            "train": {"trade_count": 80, "return_pct": 34, "sharpe": 1.4, "win_rate": 0.58, "max_drawdown_pct": -8, "profit_factor": 1.8},
            "validation": {"trade_count": 35, "return_pct": 15, "sharpe": 0.9, "win_rate": 0.54, "max_drawdown_pct": -7, "profit_factor": 1.4},
            "test": {"trade_count": 90, "return_pct": -99, "sharpe": -5.0},
        },
    )

    assert result.verdict == "SUPPORTED"
    assert result.metrics["trade_count"] == 115
    assert set(result.metrics["splits"]) == {"train", "validation"}
    assert result.metrics["assumptions"] == [
        "time-ordered train/validation/test split",
        "test split locked until strategy commit",
        "minimum 25 bps round-trip transaction cost",
    ]
    assert "test" not in result.to_dict()["metrics"]["splits"]


def test_coder_quant_ai_proposal_compiles_to_strategy_spec():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    calls = []

    def fake_llm_call(*, system, user, schema, model=None):
        calls.append({"system": system, "user": user, "schema": schema, "model": model})
        return {
            "strategy_family": "stage2_breakout",
            "horizon_days": 10,
            "entry_rules": ["stage is Stage 2", "volume confirms breakout"],
            "exit_rules": ["close loses 50 day moving average"],
            "risk_rules": ["risk no more than 1 percent of capital"],
            "required_features": ["stage", "volume_ratio"],
            "assumptions": ["needs liquid universe"],
            "limitations": ["first pass research only"],
        }

    request = StrategyBuildRequest(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout with volume confirmation",
        allowed_horizons=[10],
    )

    spec = CoderQuantAgent(llm_call=fake_llm_call, model="test-model").propose_strategy_spec(
        request,
        evidence={"market": {"regime": "risk_on"}},
    )

    assert spec.strategy_id == "stage2"
    assert spec.horizon_days == 10
    assert spec.entry_rules == ("stage is Stage 2", "volume confirms breakout")
    assert spec.origin == "ai_coder_quant"
    assert spec.params["ai_driven"] is True
    assert spec.params["assumptions"] == ["needs liquid universe"]
    assert calls[0]["model"] == "test-model"
    assert "test split" in calls[0]["system"].lower()


def test_coder_quant_ai_proposal_blocks_test_split_request():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    def fake_llm_call(**_):
        return {
            "strategy_family": "stage2_breakout",
            "horizon_days": 10,
            "entry_rules": ["stage is Stage 2"],
            "exit_rules": ["query test split before lock"],
            "risk_rules": ["risk no more than 1 percent of capital"],
            "use_test_split": True,
        }

    request = StrategyBuildRequest(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout with volume confirmation",
        allowed_horizons=[10],
    )

    result = CoderQuantAgent(llm_call=fake_llm_call, require_ai=True).try_propose_strategy_spec(request)

    assert result["ok"] is False
    assert result["error"] == "test_split_locked"


def test_coder_quant_ai_proposal_rejects_unsafe_rules():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    def fake_llm_call(**_):
        return {
            "strategy_family": "stage2_breakout",
            "horizon_days": 10,
            "entry_rules": ["eval malicious expression"],
            "exit_rules": ["close loses 50 day moving average"],
            "risk_rules": ["risk no more than 1 percent of capital"],
        }

    request = StrategyBuildRequest(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout with volume confirmation",
        allowed_horizons=[10],
    )

    result = CoderQuantAgent(llm_call=fake_llm_call, require_ai=True).try_propose_strategy_spec(request)

    assert result["ok"] is False
    assert result["error"] == "invalid_ai_strategy_proposal"
    assert "forbidden executable content" in result["message"]


def test_coder_quant_require_ai_returns_untestable_when_llm_unavailable():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    def failing_llm_call(**_):
        raise RuntimeError("provider unavailable")

    request = StrategyBuildRequest(
        source_branch="minervini_stage2",
        strategy_family="stage2_breakout",
        hypothesis="Stage 2 breakout with volume confirmation",
    )

    output = CoderQuantAgent(llm_call=failing_llm_call, require_ai=True).try_propose_strategy_spec(request)

    assert output == {
        "ok": False,
        "error": "llm_unavailable",
        "message": "provider unavailable",
    }


def test_coder_quant_marks_runner_unsupported_strategy_untestable():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=260, freq="D"),
            "symbol": ["AAA"] * 260,
            "open": range(260),
            "high": range(1, 261),
            "low": range(260),
            "close": range(1, 261),
            "volume": [1000] * 260,
        }
    )

    output = CoderQuantAgent().run_train_validation(
        StrategyBuildRequest(
            source_branch="sector_opportunity",
            strategy_family="supertrend_continuation",
            hypothesis="Supertrend route",
        ),
        frame,
    )

    assert output["ok"] is False
    assert output["error"] == "unsupported_strategy"
    assert output["message"] == "strategy supertrend_continuation is not supported by the backtest runner"


def test_coder_quant_stage2_preserves_rolling_lookback_before_time_split(monkeypatch):
    import terminal.research_council.agents.coder_quant as coder_quant
    from backtesting.strategy_council.types import BacktestSliceResult
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    captured_validation = {}

    def fake_run_split(df, spec, *, split_name, initial_capital):
        if split_name == "validation":
            captured_validation["sma_200_non_null"] = int(df["sma_200"].notna().sum())
            captured_validation["entry_rows"] = int((df["stage"] == "Stage 2").sum())
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics={"trade_count": 1, "return_pct": 1.0, "sharpe": 1.0, "win_rate": 1.0},
            trade_count=1,
        )

    monkeypatch.setattr(coder_quant, "run_strategy_spec_on_split", fake_run_split)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=320, freq="D"),
            "symbol": ["AAA"] * 320,
            "open": [float(i) for i in range(100, 420)],
            "high": [float(i + 1) for i in range(100, 420)],
            "low": [float(i - 1) for i in range(100, 420)],
            "close": [float(i) for i in range(100, 420)],
            "volume": [1000 + i for i in range(320)],
        }
    )

    output = CoderQuantAgent().run_train_validation(
        StrategyBuildRequest(
            source_branch="sector_opportunity",
            strategy_family="stage2_breakout",
            hypothesis="Stage 2 route",
        ),
        frame,
    )

    assert output["ok"] is True
    assert captured_validation["sma_200_non_null"] > 0
    assert captured_validation["entry_rows"] > 0


def test_coder_quant_sweep_circuit_breaks_after_ai_unavailable():
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    calls = []

    def failing_llm_call(**_):
        calls.append(1)
        raise RuntimeError("provider timed out")

    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=120, freq="D"),
            "symbol": ["AAA"] * 120,
            "open": range(120),
            "high": range(1, 121),
            "low": range(120),
            "close": range(1, 121),
            "volume": [1000] * 120,
        }
    )

    output = CoderQuantAgent(llm_call=failing_llm_call, require_ai=True).sweep_train_validation(
        source_branch="sector_opportunity",
        hypothesis="Compare AI routes",
        eod_data=frame,
        strategy_families=["stage2_breakout", "vcp_breakout"],
        horizons=[5, 10],
    )

    assert len(calls) == 1
    assert output["routes_tested"] == 0
    assert output["routes_untestable"] == 4
    assert output["untestable"][0]["error"] == "llm_unavailable"
    assert [row["error"] for row in output["untestable"][1:]] == ["llm_unavailable_skipped"] * 3


def test_coder_quant_sweeps_multiple_route_options_without_test_split(monkeypatch):
    import terminal.research_council.agents.coder_quant as coder_quant
    from backtesting.strategy_council.types import BacktestSliceResult
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    called = []

    def fake_run_split(df, spec, *, split_name, initial_capital):
        called.append((spec.params["strategy_family"], spec.horizon_days, split_name))
        base = {
            ("stage2_breakout", 5, "train"): (40, 6, 0.8),
            ("stage2_breakout", 5, "validation"): (20, 4, 0.7),
            ("vcp_breakout", 10, "train"): (50, 12, 1.1),
            ("vcp_breakout", 10, "validation"): (30, 9, 1.0),
        }[(spec.params["strategy_family"], spec.horizon_days, split_name)]
        trade_count, return_pct, sharpe = base
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics={
                "trade_count": trade_count,
                "return_pct": return_pct,
                "sharpe": sharpe,
                "win_rate": 0.55,
            },
            trade_count=trade_count,
        )

    monkeypatch.setattr(coder_quant, "run_strategy_spec_on_split", fake_run_split)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=120, freq="D"),
            "symbol": ["AAA"] * 120,
            "open": range(120),
            "high": range(1, 121),
            "low": range(120),
            "close": range(1, 121),
            "volume": [1000] * 120,
        }
    )

    output = CoderQuantAgent().sweep_train_validation(
        source_branch="option_sweep",
        hypothesis="Compare breakout options",
        eod_data=frame,
        strategy_families=["stage2_breakout", "vcp_breakout", "mean_reversion_ai"],
        horizons=[5, 10],
        option_grid=[("stage2_breakout", 5), ("vcp_breakout", 10), ("mean_reversion_ai", 5)],
    )

    assert output["ok"] is True
    assert output["best"]["request"].strategy_family == "vcp_breakout"
    assert output["best"]["request"].allowed_horizons == [10]
    assert [item["request"].strategy_family for item in output["ranked_options"][:2]] == [
        "vcp_breakout",
        "stage2_breakout",
    ]
    assert output["untestable"][0]["request"].strategy_family == "mean_reversion_ai"
    assert all(split != "test" for *_prefix, split in called)
    assert all("test" not in item["result"].metrics["splits"] for item in output["ranked_options"])


def test_coder_quant_sweep_preserves_per_symbol_attribution(monkeypatch):
    import terminal.research_council.agents.coder_quant as coder_quant
    from backtesting.strategy_council.types import BacktestSliceResult
    from terminal.research_council.agents.coder_quant import CoderQuantAgent

    def fake_run_split(df, spec, *, split_name, initial_capital):
        attribution = {
            "train": {
                "AAA": {"trade_count": 12, "return_pct": 4.0},
                "BBB": {"trade_count": 8, "return_pct": -1.0},
            },
            "validation": {
                "AAA": {"trade_count": 6, "return_pct": 3.5},
                "BBB": {"trade_count": 3, "return_pct": 0.5},
            },
        }[split_name]
        return BacktestSliceResult(
            split=split_name,
            strategy_id=spec.strategy_id,
            horizon_days=spec.horizon_days,
            metrics={
                "trade_count": sum(row["trade_count"] for row in attribution.values()),
                "return_pct": sum(row["return_pct"] for row in attribution.values()),
                "sharpe": 0.8,
                "symbol_attribution": attribution,
            },
            trade_count=sum(row["trade_count"] for row in attribution.values()),
        )

    monkeypatch.setattr(coder_quant, "run_strategy_spec_on_split", fake_run_split)
    frame = pd.DataFrame(
        {
            "date": list(pd.date_range("2024-01-01", periods=120, freq="D")) * 2,
            "symbol": ["AAA"] * 120 + ["BBB"] * 120,
            "open": list(range(120)) * 2,
            "high": list(range(1, 121)) * 2,
            "low": list(range(120)) * 2,
            "close": list(range(1, 121)) * 2,
            "volume": [1000] * 240,
        }
    )

    output = CoderQuantAgent().sweep_train_validation(
        source_branch="sector_opportunity",
        hypothesis="Attribute symbols",
        eod_data=frame,
        strategy_families=["stage2_breakout"],
        horizons=[10],
    )

    attribution = output["best"]["symbol_attribution"]
    assert attribution["AAA"]["train_return_pct"] == 4.0
    assert attribution["AAA"]["validation_return_pct"] == 3.5
    assert attribution["AAA"]["total_trade_count"] == 18
    assert attribution["BBB"]["validation_return_pct"] == 0.5
