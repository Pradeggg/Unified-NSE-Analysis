import math

import pandas as pd

from scripts.portfolio_construction import (
    Config,
    attach_eod_frame,
    cost_in_r,
    cost_pct,
    effective_concurrency,
    kelly_phi,
    recompute_net_edge,
    resimulate_signal,
    risk_per_trade,
    select_daily_book,
    setup_net_leaderboard,
)


def test_next_open_fill_recomputes_r_from_realized_entry_and_timeout():
    cfg = Config(fill_model="next_open", target_r=2.0, timeout_bars=2)
    signal = pd.Series({"close": 100.0, "stop": 95.0})
    bars = pd.DataFrame(
        [
            {"date": "2026-01-02", "open": 110.0, "high": 124.0, "low": 108.0, "close": 120.0},
            {"date": "2026-01-05", "open": 121.0, "high": 126.0, "low": 119.0, "close": 125.0},
        ]
    )

    out = resimulate_signal(signal, bars, cfg)

    assert out["valid"] is True
    assert out["entry"] == 110.0
    assert out["stop"] == 95.0
    assert out["outcome"] == "timeout"
    assert round(out["risk_pct"], 4) == round(15.0 / 110.0, 4)
    assert round(out["r_gross"], 4) == 1.0


def test_same_bar_stop_target_collision_resolves_to_stop_first():
    cfg = Config(fill_model="next_open", target_r=2.0, timeout_bars=1)
    signal = pd.Series({"close": 100.0, "stop": 95.0})
    bars = pd.DataFrame([{"date": "2026-01-02", "open": 100.0, "high": 111.0, "low": 94.0, "close": 108.0}])

    out = resimulate_signal(signal, bars, cfg)

    assert out["outcome"] == "loss"
    assert out["r_gross"] == -1.0


def test_limit_fill_uses_signal_close_only_if_next_session_trades_there():
    cfg = Config(fill_model="limit_at_signal_close", target_r=2.0, timeout_bars=1)
    signal = pd.Series({"close": 100.0, "stop": 95.0})

    filled = resimulate_signal(
        signal,
        pd.DataFrame([{"date": "2026-01-02", "open": 103.0, "high": 104.0, "low": 99.0, "close": 103.0}]),
        cfg,
    )
    missed = resimulate_signal(
        signal,
        pd.DataFrame([{"date": "2026-01-02", "open": 103.0, "high": 104.0, "low": 101.0, "close": 103.0}]),
        cfg,
    )

    assert filled["entry"] == 100.0
    assert missed["entry"] == 103.0


def test_cost_model_taxes_tight_stops_and_volume_spikes_harder():
    cfg = Config()

    liquid_cost = cost_pct(adr_pct=2.0, volume_ratio=2.0, cfg=cfg)
    spike_cost = cost_pct(adr_pct=6.0, volume_ratio=9.0, cfg=cfg)

    assert spike_cost > liquid_cost
    assert cost_in_r(2.0, 2.0, risk_pct=0.03, cfg=cfg) > cost_in_r(2.0, 2.0, risk_pct=0.08, cfg=cfg)


def test_recompute_net_edge_uses_attached_eod_frame_and_builds_leaderboard():
    cfg = Config(target_r=2.0, timeout_bars=2)
    events = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-01-01"),
                "symbol": "AAA",
                "setup": "relative_strength_breakout",
                "sector": "TEST",
                "close": 100.0,
                "stop": 95.0,
                "volume_ratio_20d": 2.0,
                "adr_pct_20": 2.0,
            },
            {
                "date": pd.Timestamp("2026-01-01"),
                "symbol": "BBB",
                "setup": "relative_strength_breakout",
                "sector": "TEST",
                "close": 100.0,
                "stop": 95.0,
                "volume_ratio_20d": 8.0,
                "adr_pct_20": 6.0,
            },
        ]
    )
    eod = pd.DataFrame(
        [
            {"date": pd.Timestamp("2026-01-02"), "symbol": "AAA", "open": 100.0, "high": 111.0, "low": 99.0, "close": 110.0},
            {"date": pd.Timestamp("2026-01-02"), "symbol": "BBB", "open": 100.0, "high": 101.0, "low": 94.0, "close": 95.0},
        ]
    )
    attach_eod_frame(eod)

    net_events = recompute_net_edge(events, engine=None, cfg=cfg)
    leaderboard = setup_net_leaderboard(net_events)

    assert list(net_events["valid"]) == [True, True]
    assert set(net_events["outcome"]) == {"target", "loss"}
    assert leaderboard.loc["relative_strength_breakout", "trades"] == 2
    assert leaderboard.loc["relative_strength_breakout", "net_expectancy_R"] < 0.5


def test_correlation_aware_sizing_and_daily_selector_dedupes_and_caps():
    cfg = Config(
        min_turnover_inr=50_000_000,
        max_positions=3,
        heat_cap=0.02,
        sector_heat_cap=0.015,
        per_name_risk_cap=0.01,
        kelly_fraction=0.5,
        factor_rho=0.5,
    )
    assert effective_concurrency(3, 0.5) == 1.5
    assert risk_per_trade(2, phi=0.10, cfg=cfg) <= cfg.per_name_risk_cap
    assert math.isclose(kelly_phi([1.0, -0.5, 1.5]), 4 / 7)

    queue = pd.DataFrame(
        [
            {"date": "2026-01-10", "symbol": "AAA", "sector": "A", "setup": "weak", "close": 100, "stop": 95, "turnover_cr_20d": 200_000_000},
            {"date": "2026-01-10", "symbol": "AAA", "sector": "A", "setup": "strong", "close": 100, "stop": 95, "turnover_cr_20d": 200_000_000},
            {"date": "2026-01-10", "symbol": "BBB", "sector": "A", "setup": "strong", "close": 100, "stop": 95, "turnover_cr_20d": 200_000_000},
            {"date": "2026-01-10", "symbol": "CCC", "sector": "B", "setup": "strong", "close": 100, "stop": 95, "turnover_cr_20d": 1_000_000},
            {"date": "2026-01-10", "symbol": "DDD", "sector": "B", "setup": "negative", "close": 100, "stop": 95, "turnover_cr_20d": 200_000_000},
        ]
    )
    net_lb = pd.DataFrame(
        {"net_expectancy_R": {"weak": 0.02, "strong": 0.12, "negative": -0.01}}
    )

    book = select_daily_book(queue, net_lb, {"strong": 0.10, "weak": 0.04}, cfg)

    assert book["symbol"].tolist() == ["AAA"]
    assert book.loc[0, "setup"] == "strong"
    assert book.attrs["total_heat"] <= cfg.heat_cap


def test_daily_selector_returns_readable_empty_book_when_no_positive_edge():
    cfg = Config()
    queue = pd.DataFrame(
        [{"date": "2026-01-10", "symbol": "AAA", "sector": "A", "setup": "negative", "turnover_cr_20d": 200_000_000}]
    )
    net_lb = pd.DataFrame({"net_expectancy_R": {"negative": -0.01}})

    book = select_daily_book(queue, net_lb, {"negative": 0.0}, cfg)

    assert book.empty
    assert list(book.columns) == [
        "symbol",
        "sector",
        "setup",
        "net_expectancy_R",
        "risk_pct_of_capital",
        "close",
        "stop",
    ]
    assert book.attrs["total_heat"] == 0.0
