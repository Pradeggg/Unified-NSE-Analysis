from pathlib import Path

import top_picks_report


def _row(symbol, sector="Capital Goods & Industrials", inv=60.0):
    return {
        "symbol": symbol,
        "sector": sector,
        "price": 100.0,
        "technical_score": 70.0,
        "relative_strength": 25.0,
        "enhanced_fund_score": 60.0,
        "investment_score": inv,
        "trading_signal": "BUY",
        "trend_signal": "BULLISH",
        "stance": "BULLISH",
        "stage": "STAGE_2",
        "supertrend_state": "BULLISH",
    }


def test_load_research_shortlist_items_parses_ranked_actions(tmp_path: Path):
    path = tmp_path / "swing_shortlist_deep_research.md"
    path.write_text(
        "\n".join(
            [
                "| Rank | Symbol | Fundamental class | Swing class | Research action |",
                "| --- | --- | --- | --- | --- |",
                "| 1 | POLYCAB | High-quality compounder | Stage 2 retest | Core watch |",
                "| 9 | TEJASNET | Turnaround risk | Stage 2 technical only | Deprioritize |",
            ]
        ),
        encoding="utf-8",
    )

    items = top_picks_report.load_research_shortlist_items(path)

    assert items == [
        {
            "rank": 1,
            "symbol": "POLYCAB",
            "fundamental_class": "High-quality compounder",
            "swing_class": "Stage 2 retest",
            "research_action": "Core watch",
        },
        {
            "rank": 9,
            "symbol": "TEJASNET",
            "fundamental_class": "Turnaround risk",
            "swing_class": "Stage 2 technical only",
            "research_action": "Deprioritize",
        },
    ]


def test_resolve_sector_profile_corrects_stale_sector_and_subsector():
    expectations = {
        "SCHAEFFLER": ("EV & Auto Ancillaries", "Bearings & Precision Motion"),
        "MTARTECH": ("Defence & Aerospace", "Precision Defence & Aerospace Systems"),
        "PANAMAPET": ("Chemicals & Specialty", "Specialty Petroleum Products"),
        "WALCHANNAG": ("Capital Goods & Industrials", "Heavy Engineering & Aerospace Components"),
        "CUPID": ("Pharma & Healthcare", "Medical Devices & Sexual Wellness"),
    }

    for symbol, expected in expectations.items():
        profile = top_picks_report.resolve_sector_profile(symbol, symbol, "Other")
        assert (profile["sector"], profile["sub_sector"]) == expected


def test_write_top_picks_tradingview_watchlist_outputs_upload_formats(tmp_path: Path):
    picks = [
        {"symbol": "schaeffler"},
        {"symbol": "SCHAEFFLER"},
        {"symbol": "MTARTECH.NS"},
        {"symbol": ""},
        {"symbol": None},
        {"symbol": "PANAMAPET"},
    ]

    comma_path, lines_path, dated_path = top_picks_report.write_top_picks_tradingview_watchlist(
        picks,
        "2026-06-19",
        top_picks_dir=tmp_path / "top_picks",
        latest_dir=tmp_path / "latest",
    )

    assert comma_path.name == "top_picks_tradingview.txt"
    assert lines_path.name == "top_picks_tradingview_lines.txt"
    assert dated_path.name == "Top_Investment_Picks_TradingView_20260619.txt"
    assert comma_path.read_text(encoding="utf-8") == "NSE:SCHAEFFLER,NSE:MTARTECH,NSE:PANAMAPET\n"
    assert lines_path.read_text(encoding="utf-8") == "NSE:SCHAEFFLER\nNSE:MTARTECH\nNSE:PANAMAPET\n"
    assert dated_path.read_text(encoding="utf-8") == comma_path.read_text(encoding="utf-8")


def test_build_pick_list_promotes_eligible_research_before_strategy(monkeypatch):
    monkeypatch.setattr(
        top_picks_report,
        "_load_top_sectors",
        lambda conn, snap_date, top_n=12, rrg_map=None: {
            "Capital Goods & Industrials": 80.0,
            "EV & Auto Ancillaries": 72.0,
            "PSU / CPSE": 68.0,
        },
    )
    monkeypatch.setattr(
        top_picks_report,
        "_load_vcp_picks",
        lambda conn, snap_date: [
            {
                "symbol": "POLYCAB",
                "sector": "Capital Goods & Industrials",
                "price": 100.0,
                "investment_score": 65.0,
                "vcp_score": 76.0,
                "supertrend_state": "BULLISH",
            }
        ],
    )
    monkeypatch.setattr(
        top_picks_report,
        "_load_stage2_leaders",
        lambda conn, snap_date: [
            _row("POLYCAB", inv=65.0),
            _row("SCHAEFFLER", "EV & Auto Ancillaries", inv=59.0),
            _row("TEJASNET", "IT & Technology", inv=59.0),
            _row("MTARTECH", "PSU / CPSE", inv=60.0),
        ],
    )
    monkeypatch.setattr(
        top_picks_report,
        "_portfolio_lab_best_strategy_confirmations",
        lambda: {
            "MTARTECH": {
                "strategy_id": "darvas_box_breakout_v1",
                "strategy_name": "Darvas",
                "strategy_signal": "open_position",
                "strategy_rank": 1,
                "strategy_return_pct": 10.0,
            }
        },
    )
    monkeypatch.setattr(
        top_picks_report,
        "_load_rows_for_symbols",
        lambda conn, snap_date, symbols: [_row("MTARTECH", "PSU / CPSE", inv=60.0)],
    )
    monkeypatch.setattr(
        top_picks_report,
        "load_research_shortlist_items",
        lambda: [
            {
                "rank": 1,
                "symbol": "POLYCAB",
                "fundamental_class": "High-quality compounder",
                "swing_class": "Stage 2 retest",
                "research_action": "Core watch",
            },
            {
                "rank": 2,
                "symbol": "SCHAEFFLER",
                "fundamental_class": "High-quality compounder",
                "swing_class": "Stage 2 retest",
                "research_action": "Core watch",
            },
            {
                "rank": 9,
                "symbol": "TEJASNET",
                "fundamental_class": "Turnaround risk",
                "swing_class": "Stage 2 technical only",
                "research_action": "Deprioritize",
            },
        ],
        raising=False,
    )

    picks = top_picks_report.build_pick_list(None, "2026-06-19", n=3)

    assert [p.symbol for p in picks] == ["POLYCAB", "SCHAEFFLER", "MTARTECH"]
    assert picks[0].source == "research+vcp+sector"
    assert picks[1].source == "research+sector+s2"
    assert picks[1].sector == "EV & Auto Ancillaries"
    assert picks[1].sub_sector == "Bearings & Precision Motion"
    assert picks[2].sector == "Defence & Aerospace"
    assert picks[2].sub_sector == "Precision Defence & Aerospace Systems"
    assert "TEJASNET" not in {p.symbol for p in picks}
