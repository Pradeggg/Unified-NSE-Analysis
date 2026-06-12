import pandas as pd


def test_compute_indicator_signals_does_not_fetch_fred(monkeypatch):
    import fetch_macro_proxies as macro

    def fail_fred(*args, **kwargs):
        raise AssertionError("FRED fetch should be decommissioned")

    monkeypatch.setattr(macro, "fetch_fred_series", fail_fred)
    monkeypatch.setattr(
        macro,
        "fetch_nse_live_indices",
        lambda force=False: {
            "INDIA VIX": {"last": 13.5, "percentChange": -1.2},
            "NIFTY 50": {"last": 23100.0, "percentChange": 0.6},
        },
    )
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda self, *args, **kwargs: None)

    signals = macro.compute_indicator_signals(force=True)

    assert set(signals["indicator"]) == {"India VIX", "Nifty 50"}
    assert signals["cycle_eligible"].eq(True).all()
    assert signals["source_status"].eq("NSE_LIVE_OR_CACHE").all()


def test_load_macro_signals_marks_legacy_fred_rows_ineligible(tmp_path, monkeypatch):
    import fetch_macro_proxies as macro

    signals_csv = tmp_path / "macro_proxy_signals.csv"
    pd.DataFrame(
        [
            {"indicator": "Brent Crude", "series_id": "DCOILBRENTEU", "signal_score": -3.0},
            {"indicator": "Nifty 50", "series_id": "NIFTY 50", "signal_score": 0.5},
        ]
    ).to_csv(signals_csv, index=False)
    monkeypatch.setattr(macro, "_SIGNALS_CSV", signals_csv)

    loaded = macro.load_macro_signals()

    eligible = loaded.set_index("indicator")["cycle_eligible"].to_dict()
    assert eligible["Brent Crude"] is False
    assert eligible["Nifty 50"] is True


def test_economic_cycle_ignores_decommissioned_fred_rows():
    from economic_cycle import detect_economic_cycle_phase

    macro = pd.DataFrame(
        [
            {"indicator": "Nifty 50", "trend": "RISING", "signal_score": 0.7, "cycle_eligible": True},
            {"indicator": "Brent Crude", "trend": "RISING", "signal_score": -3.0, "cycle_eligible": False},
            {"indicator": "India CPI Index", "trend": "RISING", "signal_score": -3.0, "cycle_eligible": False},
            {"indicator": "US 10Y Treasury", "trend": "RISING", "signal_score": -3.0, "cycle_eligible": False},
        ]
    )

    cycle = detect_economic_cycle_phase(macro, market_regime="ROTATION")

    assert cycle["cycle_phase"] != "LATE_EXPANSION"
