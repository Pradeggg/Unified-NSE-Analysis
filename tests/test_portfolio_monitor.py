"""Tests for terminal/portfolio_monitor.py

Covers:
  - Portfolio CSV parsing
  - DB snapshot loading
  - Symbol matching (_BROKER_TO_NSE map + fuzzy fallback)
  - All 6 strategy evaluators
  - Composite signal logic
  - run_intraday_view() — markdown structure + HTML file written
  - run_eod_report() — HTML file written + success flag
  - generate_preset_report("portfolio-monitor") delegation
  - daily_refresh step_portfolio_monitor exists and is callable
  - /my-portfolio command is registered in the command registry
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import terminal.portfolio_monitor as pm


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_csv(rows: list[dict], path: Path) -> None:
    """Write a minimal portfolio CSV to path."""
    fieldnames = [
        "Stock Symbol", "Company Name", "ISIN Code", "Qty",
        "Average Cost Price", "Current Market Price", "% Change over prev close",
        "Value At Cost", "Value At Market Price",
        "Realized Profit / Loss", "Unrealized Profit/Loss", "Unrealized Profit/Loss %",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


_SAMPLE_ROWS = [
    {
        "Stock Symbol": "TATSTE",
        "Company Name": "TATA STEEL LIMITED",
        "ISIN Code": "INE081A01020",
        "Qty": "100",
        "Average Cost Price": "100.00",
        "Current Market Price": "200.00",
        "% Change over prev close": "+ 1.5",
        "Value At Cost": "10000",
        "Value At Market Price": "20000",
        "Realized Profit / Loss": "5000",
        "Unrealized Profit/Loss": "10000",
        "Unrealized Profit/Loss %": "100.00",
    },
    {
        "Stock Symbol": "ITCHOT",
        "Company Name": "ITC HOTELS LIMITED",
        "ISIN Code": "INE379A01028",
        "Qty": "50",
        "Average Cost Price": "600.00",
        "Current Market Price": "150.00",
        "% Change over prev close": "- 0.5",
        "Value At Cost": "30000",
        "Value At Market Price": "7500",
        "Realized Profit / Loss": "0",
        "Unrealized Profit/Loss": "(22500)",
        "Unrealized Profit/Loss %": "(75.00)",
    },
    {
        "Stock Symbol": "HDFBAN",
        "Company Name": "HDFC BANK LIMITED",
        "ISIN Code": "INE040A01034",
        "Qty": "10",
        "Average Cost Price": "1500.00",
        "Current Market Price": "1600.00",
        "% Change over prev close": "+ 0.3",
        "Value At Cost": "15000",
        "Value At Market Price": "16000",
        "Realized Profit / Loss": "1000",
        "Unrealized Profit/Loss": "1000",
        "Unrealized Profit/Loss %": "6.67",
    },
]


def _make_db(path: Path, records: list[dict] | None = None) -> None:
    """Write a minimal stage_snapshots SQLite DB (mirrors the real 33-column schema)."""
    conn = sqlite3.connect(str(path))
    # Column order must exactly match the real sector_rotation_tracker.db schema
    # (33 cols including source_csv at position 16 and price_date at position 32).
    conn.execute("""
        CREATE TABLE stage_snapshots (
            snapshot_date TEXT NOT NULL, symbol TEXT NOT NULL,
            company_name TEXT, stage TEXT, stage_score REAL,
            price REAL, live_price REAL,
            technical_score REAL, rsi REAL,
            trading_signal TEXT, trend_signal TEXT, relative_strength REAL,
            change_1d_pct REAL, change_1w_pct REAL, change_1m_pct REAL,
            market_cap_cat TEXT, source_csv TEXT, sector TEXT,
            fundamental_score REAL, enhanced_fund_score REAL,
            earnings_quality REAL, sales_growth REAL,
            financial_strength REAL, institutional_backing REAL,
            can_slim_score REAL, minervini_score REAL, investment_score REAL,
            fund_details TEXT, narrative TEXT, stance TEXT,
            supertrend_state TEXT, supertrend_value REAL, price_date TEXT
        )
    """)
    if records is None:
        records = [
            {
                "snapshot_date": "2026-05-29",
                "symbol": "TATASTEEL",
                "company_name": "Tata Steel Limited",
                "stage": "STAGE_2", "stage_score": 0.9, "price": 190.0, "live_price": 195.0,
                "technical_score": 72.0, "rsi": 55.0, "trading_signal": "BUY",
                "trend_signal": "STRONG_BULLISH", "relative_strength": 110.0,
                "change_1d_pct": 1.5, "change_1w_pct": 3.0, "change_1m_pct": 8.0,
                "market_cap_cat": "LARGE_CAP", "sector": "Metals & Mining",
                "fundamental_score": 60.0, "enhanced_fund_score": 65.0,
                "earnings_quality": 75.0, "sales_growth": 70.0,
                "financial_strength": 60.0, "institutional_backing": 50.0,
                "can_slim_score": 18.0, "minervini_score": 14.0, "investment_score": 62.0,
                "fund_details": json.dumps({"ratios_summary": "P/E: 8", "pnl_summary": "Rev 2.1L Cr"}),
                "narrative": "Tata Steel in Stage 2 uptrend.",
                "stance": "BULLISH", "supertrend_state": "BULLISH", "supertrend_value": 180.0,
            },
            {
                "snapshot_date": "2026-05-29",
                "symbol": "ITCHOTELS",
                "company_name": "ITC Hotels Limited",
                "stage": "STAGE_4", "stage_score": 0.2, "price": 160.0, "live_price": 155.0,
                "technical_score": 25.0, "rsi": 30.0, "trading_signal": "SELL",
                "trend_signal": "BEARISH", "relative_strength": 70.0,
                "change_1d_pct": -0.5, "change_1w_pct": -3.0, "change_1m_pct": -10.0,
                "market_cap_cat": "MID_CAP", "sector": "Hotels",
                "fundamental_score": 40.0, "enhanced_fund_score": 45.0,
                "earnings_quality": 50.0, "sales_growth": 30.0,
                "financial_strength": 40.0, "institutional_backing": 20.0,
                "can_slim_score": 5.0, "minervini_score": 3.0, "investment_score": 25.0,
                "fund_details": None, "narrative": "ITC Hotels in Stage 4 decline.",
                "stance": "BEARISH", "supertrend_state": "BEARISH", "supertrend_value": 180.0,
            },
            {
                "snapshot_date": "2026-05-29",
                "symbol": "HDFCBANK",
                "company_name": "HDFC Bank Limited",
                "stage": "STAGE_4", "stage_score": 0.3, "price": 1580.0, "live_price": 1600.0,
                "technical_score": 28.0, "rsi": 38.0, "trading_signal": "HOLD",
                "trend_signal": "STRONG_BEARISH", "relative_strength": 90.0,
                "change_1d_pct": 0.3, "change_1w_pct": -1.0, "change_1m_pct": -4.0,
                "market_cap_cat": "LARGE_CAP", "sector": "Banking - Private",
                "fundamental_score": 55.0, "enhanced_fund_score": 60.0,
                "earnings_quality": 65.0, "sales_growth": 40.0,
                "financial_strength": 55.0, "institutional_backing": 70.0,
                "can_slim_score": 6.0, "minervini_score": 10.0, "investment_score": 35.0,
                "fund_details": None, "narrative": "HDFC Bank Stage 4 correcting.",
                "stance": "NEUTRAL", "supertrend_state": "BEARISH", "supertrend_value": 1700.0,
            },
        ]
    for r in records:
        conn.execute(
            "INSERT INTO stage_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [r.get(k) for k in [
                "snapshot_date","symbol","company_name","stage","stage_score",
                "price","live_price","technical_score","rsi","trading_signal",
                "trend_signal","relative_strength","change_1d_pct","change_1w_pct",
                "change_1m_pct","market_cap_cat","source_csv","sector",
                "fundamental_score","enhanced_fund_score","earnings_quality","sales_growth",
                "financial_strength","institutional_backing","can_slim_score",
                "minervini_score","investment_score","fund_details","narrative",
                "stance","supertrend_state","supertrend_value","price_date",
            ]],
        )
    conn.commit()
    conn.close()


# ── _load_portfolio ────────────────────────────────────────────────────────────

class TestLoadPortfolio:
    def test_parses_all_rows(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        _make_csv(_SAMPLE_ROWS, csv_path)
        rows = pm._load_portfolio(csv_path)
        assert len(rows) == 3

    def test_positive_upnl(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        _make_csv(_SAMPLE_ROWS, csv_path)
        rows = pm._load_portfolio(csv_path)
        tata = next(r for r in rows if r["broker"] == "TATSTE")
        assert tata["upnl_pct"] == pytest.approx(100.0)
        assert tata["upnl"] == pytest.approx(10000.0)

    def test_day_change_pct_from_broker_export(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        _make_csv(_SAMPLE_ROWS, csv_path)
        rows = pm._load_portfolio(csv_path)
        tata = next(r for r in rows if r["broker"] == "TATSTE")
        itc = next(r for r in rows if r["broker"] == "ITCHOT")
        assert tata["day_chg_pct"] == pytest.approx(1.5)
        assert itc["day_chg_pct"] == pytest.approx(-0.5)

    def test_broker_metrics_match_screen_formula(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        _make_csv(_SAMPLE_ROWS, csv_path)
        rows = pm._load_portfolio(csv_path)
        metrics = pm._portfolio_broker_metrics(rows)

        assert metrics["total_cost"] == pytest.approx(55000.0)
        assert metrics["current_value"] == pytest.approx(43500.0)
        expected_day_gain = (
            20000.0 - (20000.0 / 1.015)
            + 7500.0 - (7500.0 / 0.995)
            + 16000.0 - (16000.0 / 1.003)
        )
        assert metrics["day_gain"] == pytest.approx(expected_day_gain)
        assert metrics["absolute_return_pct"] == pytest.approx((43500.0 / 55000.0 - 1) * 100)
        assert metrics["max_gainer"]["broker"] == "TATSTE"
        assert metrics["max_loser"]["broker"] == "ITCHOT"

    def test_negative_upnl_parsed_from_parens(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        _make_csv(_SAMPLE_ROWS, csv_path)
        rows = pm._load_portfolio(csv_path)
        itc = next(r for r in rows if r["broker"] == "ITCHOT")
        assert itc["upnl_pct"] == pytest.approx(-75.0)
        assert itc["upnl"] == pytest.approx(-22500.0)

    def test_skips_empty_symbol(self, tmp_path):
        rows_with_empty = _SAMPLE_ROWS + [{
            "Stock Symbol": "", "Company Name": "EMPTY", "ISIN Code": "",
            "Qty": "0", "Average Cost Price": "0", "Current Market Price": "0",
            "% Change over prev close": "0", "Value At Cost": "0",
            "Value At Market Price": "0", "Realized Profit / Loss": "0",
            "Unrealized Profit/Loss": "0", "Unrealized Profit/Loss %": "0",
        }]
        csv_path = tmp_path / "port.csv"
        _make_csv(rows_with_empty, csv_path)
        rows = pm._load_portfolio(csv_path)
        assert len(rows) == 3  # empty symbol skipped


# ── _load_db_snapshot ──────────────────────────────────────────────────────────
# Post-migration: PG is primary. Tests patch out psycopg2 to test each path.

class TestLoadDbSnapshot:
    def test_uses_pg_when_available(self):
        """When PG is reachable, snapshot comes from PostgreSQL."""
        records, snap_date = pm._load_db_snapshot()
        # PG is live in the dev environment — should return current data
        assert snap_date not in ("N/A", ""), f"Expected a real date, got {snap_date!r}"
        assert len(records) > 0, "Expected records from PG"

    def test_falls_back_to_sqlite_when_pg_fails(self, tmp_path):
        """When PG is unavailable, SQLite fallback is used."""
        db = tmp_path / "test.db"
        _make_db(db)
        # Patch psycopg2.connect to raise so PG path is skipped
        with patch("terminal.portfolio_monitor._PG_DSN", "dbname=does_not_exist_zzz"):
            records, snap_date = pm._load_db_snapshot(db)
        assert snap_date == "2026-05-29", f"Expected SQLite fallback date, got {snap_date!r}"
        assert "TATASTEEL" in records
        assert records["TATASTEEL"]["stage"] == "STAGE_2"

    def test_empty_sqlite_fallback_returns_na(self, tmp_path):
        """When PG fails AND SQLite is empty, returns ({}, 'N/A')."""
        db = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE stage_snapshots (
                snapshot_date TEXT, symbol TEXT, company_name TEXT,
                stage TEXT, stage_score REAL, price REAL, live_price REAL,
                technical_score REAL, rsi REAL, trading_signal TEXT, trend_signal TEXT,
                relative_strength REAL, change_1d_pct REAL, change_1w_pct REAL,
                change_1m_pct REAL, market_cap_cat TEXT, source_csv TEXT, sector TEXT,
                fundamental_score REAL, enhanced_fund_score REAL,
                earnings_quality REAL, sales_growth REAL, financial_strength REAL,
                institutional_backing REAL, can_slim_score REAL, minervini_score REAL,
                investment_score REAL, fund_details TEXT, narrative TEXT,
                stance TEXT, supertrend_state TEXT, supertrend_value REAL,
                price_date TEXT
            )
        """)
        conn.commit()
        conn.close()
        with patch("terminal.portfolio_monitor._PG_DSN", "dbname=does_not_exist_zzz"):
            records, snap_date = pm._load_db_snapshot(db)
        assert records == {}
        assert snap_date == "N/A"

    def test_missing_sqlite_and_pg_fails_returns_na(self, tmp_path):
        """When PG fails AND no SQLite file, returns ({}, 'N/A')."""
        with patch("terminal.portfolio_monitor._PG_DSN", "dbname=does_not_exist_zzz"):
            records, snap_date = pm._load_db_snapshot(tmp_path / "nonexistent.db")
        assert records == {}
        assert snap_date == "N/A"


# ── Symbol matching ────────────────────────────────────────────────────────────

class TestSymbolMatching:
    def _records(self):
        return {
            "TATASTEEL": {"symbol": "TATASTEEL", "company_name": "Tata Steel Limited"},
            "HDFCBANK":  {"symbol": "HDFCBANK",  "company_name": "HDFC Bank Limited"},
        }

    def test_broker_map_direct_hit(self):
        records = self._records()
        db_norm = pm._build_db_norm(records)
        result = pm._find_match("TATSTE", "TATA STEEL LIMITED", records, db_norm)
        assert result is not None
        assert result["symbol"] == "TATASTEEL"

    def test_exact_symbol_fallback(self):
        records = {"HDFCBANK": {"symbol": "HDFCBANK", "company_name": "HDFC Bank Limited"}}
        db_norm = pm._build_db_norm(records)
        result = pm._find_match("HDFCBANK", "HDFC BANK", records, db_norm)
        assert result is not None
        assert result["symbol"] == "HDFCBANK"

    def test_fuzzy_name_match(self):
        records = {"ICICIBANK": {"symbol": "ICICIBANK", "company_name": "ICICI Bank Limited"}}
        db_norm = pm._build_db_norm(records)
        # broker code not in map, but name should fuzzy-match
        result = pm._find_match("ZZUNKNOWN", "ICICI BANK LIMITED", records, db_norm)
        assert result is not None
        assert result["symbol"] == "ICICIBANK"

    def test_no_match_returns_none(self):
        records = {"TATASTEEL": {"symbol": "TATASTEEL", "company_name": "Tata Steel Limited"}}
        db_norm = pm._build_db_norm(records)
        result = pm._find_match("ZZUNKNOWN", "COMPLETELY UNKNOWN CORP XYZ", records, db_norm)
        assert result is None

    def test_broker_map_coverage(self):
        """All entries in _BROKER_TO_NSE should be non-empty strings."""
        for broker, nse in pm._BROKER_TO_NSE.items():
            assert isinstance(broker, str) and broker
            assert isinstance(nse, str) and nse

    def test_broker_map_fixes_known_portfolio_codes(self):
        expected = {
            "ACTCON": "ACE",
            "ADOWEL": "ADOR",
            "HINREC": "HIRECT",
            "IDFC": "IDFCFIRSTB",
            "NIVBUP": "NIVABUPA",
            "RELNIP": "NAM-INDIA",
            "SCHELE": "SCHNEIDER",
            "SHRPIS": "SHRIPISTON",
        }
        for broker, symbol in expected.items():
            assert pm._BROKER_TO_NSE[broker] == symbol


# ── Strategy evaluators ────────────────────────────────────────────────────────

class TestStrategies:
    def _bullish_d(self, **kwargs):
        base = {
            "stage": "STAGE_2", "trend_sig": "STRONG_BULLISH",
            "supertrend": "BULLISH", "tech_score": 70.0, "rsi": 55.0,
            "canslim": 20.0, "minervini": 18.0,
            "efund_score": 75.0, "earn_qual": 80.0, "sales_gr": 70.0,
        }
        base.update(kwargs)
        return base

    def _bearish_d(self, **kwargs):
        base = {
            "stage": "STAGE_4", "trend_sig": "STRONG_BEARISH",
            "supertrend": "BEARISH", "tech_score": 20.0, "rsi": 25.0,
            "canslim": 3.0, "minervini": 2.0,
            "efund_score": 30.0, "earn_qual": 30.0, "sales_gr": 20.0,
        }
        base.update(kwargs)
        return base

    # Momentum
    def test_momentum_buy(self):
        sig, reason = pm._strat_momentum(self._bullish_d())
        assert sig == "BUY"

    def test_momentum_sell_stage4(self):
        sig, _ = pm._strat_momentum(self._bearish_d())
        assert sig == "SELL"

    def test_momentum_sell_bearish_supertrend(self):
        sig, _ = pm._strat_momentum(self._bullish_d(supertrend="BEARISH"))
        assert sig == "SELL"

    def test_momentum_hold_high_rsi(self):
        # RSI > 75 → HOLD caution only when BUY prerequisite is NOT fully met.
        # Here tech_score is below the 60 threshold so BUY path is skipped.
        sig, _ = pm._strat_momentum(self._bullish_d(supertrend="BULLISH", rsi=80.0, stage="STAGE_2",
                                                    trend_sig="STRONG_BULLISH", tech_score=50))
        assert sig == "HOLD"

    def test_momentum_none_no_data(self):
        sig, _ = pm._strat_momentum(None)
        assert sig is None

    # CANSLIM
    def test_canslim_strong_buy(self):
        sig, _ = pm._strat_canslim({"canslim": 20.0})
        assert sig == "BUY"

    def test_canslim_moderate_buy(self):
        sig, _ = pm._strat_canslim({"canslim": 15.0})
        assert sig == "BUY"

    def test_canslim_hold(self):
        sig, _ = pm._strat_canslim({"canslim": 12.0})
        assert sig == "HOLD"

    def test_canslim_sell(self):
        sig, _ = pm._strat_canslim({"canslim": 5.0})
        assert sig == "SELL"

    def test_canslim_none_zero(self):
        sig, _ = pm._strat_canslim({"canslim": 0})
        assert sig is None

    # Minervini
    def test_minervini_buy_full_setup(self):
        sig, _ = pm._strat_minervini({"minervini": 20.0, "stage": "STAGE_2", "supertrend": "BULLISH"})
        assert sig == "BUY"

    def test_minervini_buy_setup_forming(self):
        sig, _ = pm._strat_minervini({"minervini": 15.0, "stage": "STAGE_1", "supertrend": "BEARISH"})
        assert sig == "BUY"

    def test_minervini_sell_weak(self):
        sig, _ = pm._strat_minervini({"minervini": 4.0, "stage": "STAGE_4", "supertrend": "BEARISH"})
        assert sig == "SELL"

    # Fundamental
    def test_fundamental_buy(self):
        sig, _ = pm._strat_fundamental({"efund_score": 80.0, "earn_qual": 75.0, "sales_gr": 65.0})
        assert sig == "BUY"

    def test_fundamental_hold_decent(self):
        sig, _ = pm._strat_fundamental({"efund_score": 60.0, "earn_qual": 58.0, "sales_gr": 40.0})
        assert sig == "HOLD"

    def test_fundamental_sell_weak(self):
        sig, _ = pm._strat_fundamental({"efund_score": 30.0, "earn_qual": 30.0, "sales_gr": 20.0})
        assert sig == "SELL"

    # Value / PnL
    def _stock(self, upnl_pct):
        return {"upnl_pct": upnl_pct, "avg_cost": 100.0}

    def test_value_deep_loss_sell(self):
        sig, reason = pm._strat_value(self._stock(-35.0), None)
        assert sig == "SELL"
        assert "cut" in reason.lower()

    def test_value_loss_sell(self):
        sig, _ = pm._strat_value(self._stock(-25.0), None)
        assert sig == "SELL"

    def test_value_big_gain_hold(self):
        sig, _ = pm._strat_value(self._stock(120.0), None)
        assert sig == "HOLD"

    def test_value_moderate_gain_hold(self):
        sig, _ = pm._strat_value(self._stock(15.0), None)
        assert sig == "HOLD"

    def test_value_mild_loss_hold(self):
        sig, _ = pm._strat_value(self._stock(-10.0), None)
        assert sig == "HOLD"

    # VCP
    def test_vcp_clean_setup_buy(self):
        sig, reason = pm._strat_vcp({
            "stage": "STAGE_2", "trend_sig": "STRONG_BULLISH",
            "supertrend": "BULLISH", "minervini": 15.0, "tech_score": 59.0,
        })
        assert sig == "BUY"
        assert "VCP" in reason

    def test_vcp_forming_setup_hold(self):
        sig, reason = pm._strat_vcp({
            "stage": "STAGE_2", "trend_sig": "STRONG_BULLISH",
            "supertrend": "BULLISH", "minervini": 11.0, "tech_score": 52.0,
        })
        assert sig == "HOLD"
        assert "forming" in reason.lower()

    def test_vcp_broken_setup_sell(self):
        sig, reason = pm._strat_vcp({
            "stage": "STAGE_4", "trend_sig": "BEARISH",
            "supertrend": "BEARISH", "minervini": 7.0, "tech_score": 22.0,
        })
        assert sig == "SELL"
        assert "broken" in reason.lower()

    # RS vs NIFTY 500
    def test_rs_nifty500_outperformance_buy(self):
        sig, reason = pm._strat_rs_nifty500({"rel_str": 21.0})
        assert sig == "BUY"
        assert "outperforming" in reason.lower()

    def test_rs_nifty500_neutral_hold(self):
        sig, reason = pm._strat_rs_nifty500({"rel_str": 5.0})
        assert sig == "HOLD"
        assert "neutral" in reason.lower()

    def test_rs_nifty500_underperformance_sell(self):
        sig, reason = pm._strat_rs_nifty500({"rel_str": -12.0})
        assert sig == "SELL"
        assert "underperforming" in reason.lower()


# ── Composite signal ───────────────────────────────────────────────────────────

class TestCompositeSignal:
    def _sigs(self, **kwargs):
        """Build signals dict from {name: sig_str}."""
        return {k: (v, "reason") for k, v in kwargs.items()}

    def test_strong_buy_three_buys(self):
        sigs = self._sigs(A="BUY", B="BUY", C="BUY", D="HOLD", E="HOLD")
        comp, nb, ns, nh = pm._composite_signal(sigs)
        assert comp == "STRONG BUY"
        assert nb == 3

    def test_buy_two_buys(self):
        sigs = self._sigs(A="BUY", B="BUY", C="HOLD", D="HOLD")
        comp, nb, ns, nh = pm._composite_signal(sigs)
        assert comp == "BUY"

    def test_sell_two_sells_dominate(self):
        sigs = self._sigs(A="SELL", B="SELL", C="HOLD")
        comp, nb, ns, nh = pm._composite_signal(sigs)
        assert comp == "SELL"

    def test_sell_one_sell_no_buys(self):
        sigs = self._sigs(A="SELL", B="HOLD", C="HOLD")
        comp, nb, ns, nh = pm._composite_signal(sigs)
        assert comp == "SELL"

    def test_hold_mixed(self):
        sigs = self._sigs(A="BUY", B="SELL", C="HOLD", D="HOLD")
        comp, nb, ns, nh = pm._composite_signal(sigs)
        assert comp == "HOLD"

    def test_hold_all_holds(self):
        sigs = self._sigs(A="HOLD", B="HOLD")
        comp, nb, ns, nh = pm._composite_signal(sigs)
        assert comp == "HOLD"

    def test_none_signals_ignored(self):
        sigs = {"A": (None, "n/a"), "B": ("BUY", "ok"), "C": ("BUY", "ok")}
        comp, nb, ns, nh = pm._composite_signal(sigs)
        assert comp == "BUY"
        assert nb == 2


# ── run_intraday_view ─────────────────────────────────────────────────────────

class TestRunIntradayView:
    def _setup(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        db_path  = tmp_path / "db.sqlite"
        _make_csv(_SAMPLE_ROWS, csv_path)
        _make_db(db_path)
        return csv_path, db_path

    def test_returns_markdown_string(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        with patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"):
            out = pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)
        assert isinstance(out, str)
        assert "My Portfolio" in out

    def test_contains_kpi_table(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        with patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"):
            out = pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)
        assert "Amount Invested" in out
        assert "Current Value" in out
        assert "Day's Gain" in out
        assert "Absolute Returns" in out

    def test_contains_signal_summary(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        with patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"):
            out = pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)
        assert "Signals:" in out

    def test_html_file_written(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)
        assert html_out.exists()
        content = html_out.read_text()
        assert "<html" in content
        assert "portfolio" in content.lower()

    def test_intraday_html_has_search_filters_sort_and_visuals(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=({}, "N/A")), \
             patch.object(pm, "_is_market_hours", return_value=False):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)

        content = html_out.read_text()
        assert 'id="holdingsSearch"' in content
        assert 'id="signalFilter"' in content
        assert 'id="stageFilter"' in content
        assert 'id="sectorFilter"' in content
        assert 'id="portfolioBubbleChart"' in content
        assert 'id="portfolioHeatmap"' in content
        assert 'data-sort-key="broker"' in content
        assert "function applyPortfolioFilters" in content

    def test_intraday_heatmap_is_populated_in_static_html(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=({}, "N/A")), \
             patch.object(pm, "_is_market_hours", return_value=False):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)

        content = html_out.read_text()
        heat_counts = [
            int(value)
            for value in re.findall(
                r'<div class="heat-cell"[^>]*><span class="count">(\d+)</span>',
                content,
            )
        ]
        assert len(heat_counts) == 20
        assert sum(heat_counts) == len(_SAMPLE_ROWS)
        assert re.search(r'<span class="avg">Inv (?!--)\d+</span>', content)

    def test_intraday_html_uses_rs_vs_nifty500_not_rsi_column(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_PG_DSN", "dbname=does_not_exist_zzz"), \
             patch.object(pm, "_is_market_hours", return_value=False):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)

        content = html_out.read_text()
        assert "RS vs NIFTY 500" in content
        assert 'data-sort-key="rs_nifty500"' in content
        assert 'data-rs-nifty500="110.0000"' in content
        assert 'row.getAttribute("data-" + attrKey)' in content
        assert "VCP" in content
        assert "RS vs NIFTY 500" in content
        assert "RSI Strat." not in content
        assert '<th class="sortable" data-sort-key="rsi">RSI</th>' not in content

    def test_intraday_sort_tables_skip_generic_enhancer(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=({}, "N/A")), \
             patch.object(pm, "_is_market_hours", return_value=False):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)

        content = html_out.read_text()
        assert 'data-no-enhance="1"' in content
        assert 'if (table.dataset.noEnhance === "1") return;' in content

    def test_intraday_html_top_movers_use_broker_day_change(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=({}, "N/A")), \
             patch.object(pm, "_is_market_hours", return_value=False):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)

        content = html_out.read_text()
        assert "No data yet" not in content
        assert "<strong>TATSTE</strong>" in content
        assert "+1.5%" in content
        assert "<strong>ITCHOT</strong>" in content
        assert "-0.5%" in content

    def test_intraday_html_has_alert_zone(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=({}, "N/A")), \
             patch.object(pm, "_is_market_hours", return_value=False):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)

        content = html_out.read_text()
        assert 'id="alertZone"' in content
        assert "Alert Zone" in content
        assert "Sharp Movers" in content
        assert "Risk Alerts" in content
        assert "Watch Alerts" in content
        assert "High-Value Moves" in content
        assert 'data-alert-symbol="ITCHOT"' in content
        assert "function focusHolding" in content

    def test_html_has_auto_refresh_during_market_hours(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday_mkt.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"), \
             patch.object(pm, "_is_market_hours", return_value=True):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)
        content = html_out.read_text()
        assert 'http-equiv="refresh"' in content

    def test_html_no_auto_refresh_outside_market_hours(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        html_out = tmp_path / "intraday_closed.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"), \
             patch.object(pm, "_is_market_hours", return_value=False):
            pm.run_intraday_view(live=False, csv_path=csv_path, db_path=db_path)
        content = html_out.read_text()
        assert 'http-equiv="refresh"' not in content

    def test_filter_sell_only(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        with patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"):
            out = pm.run_intraday_view(
                filter_signal="SELL", live=False, csv_path=csv_path, db_path=db_path
            )
        # Only SELL rows should appear in the table; STRONG BUY rows absent
        assert "STRONG BUY" not in out or "Signals:" in out  # summary line may still mention it
        # All table rows must be SELL
        table_rows = [l for l in out.split("\n") if l.startswith("| **")]
        for row in table_rows:
            assert "SELL" in row

    def test_filtered_intraday_view_keeps_full_canonical_html(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        _make_csv(_SAMPLE_ROWS, csv_path)
        html_out = tmp_path / "intraday.html"

        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=({}, "N/A")), \
             patch.object(pm, "_is_market_hours", return_value=False):
            out = pm.run_intraday_view(
                filter_signal="SELL", live=False, csv_path=csv_path
            )

        table_rows = [l for l in out.split("\n") if l.startswith("| **")]
        assert len(table_rows) == 1
        assert "ITCHOT" in table_rows[0]

        content = html_out.read_text()
        assert "3 holdings" in content
        assert "<strong>TATSTE</strong>" in content
        assert "<strong>ITCHOT</strong>" in content
        assert "<strong>HDFBAN</strong>" in content

    def test_live_prices_overlaid_when_provided(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        fake_prices = {"TATASTEEL": 210.0}
        with patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "EOD_REPORT",      tmp_path / "eod.html"), \
             patch.object(pm, "_fetch_live_prices_yf", return_value=fake_prices), \
             patch.object(pm, "_is_market_hours", return_value=True):
            out = pm.run_intraday_view(live=True, csv_path=csv_path, db_path=db_path)
        # The live price for TATSTE/TATASTEEL should now show 210
        assert "210" in out

    def test_live_day_change_does_not_compare_against_fuzzy_db_symbol(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        _make_csv([
            {
                "Stock Symbol": "BAJHOL",
                "Company Name": "BAJAJ HOLDINGS & INVESTMENT",
                "ISIN Code": "INE118A01012",
                "Qty": "4",
                "Average Cost Price": "10581.58",
                "Current Market Price": "10219.00",
                "% Change over prev close": "- 0.5",
                "Value At Cost": "42326.32",
                "Value At Market Price": "40876.00",
                "Realized Profit / Loss": "0",
                "Unrealized Profit/Loss": "(1450.32)",
                "Unrealized Profit/Loss %": "(3.43)",
            }
        ], csv_path)
        wrong_fuzzy_db = {
            "BAJFINANCE": {
                "symbol": "BAJFINANCE",
                "company_name": "Bajaj Finance Limited",
                "stage": "STAGE_2",
                "price": 874.40,
                "live_price": None,
                "tech_score": 70,
                "rsi": 55,
                "trade_sig": "BUY",
                "trend_sig": "BULLISH",
                "rel_str": 90,
                "chg1d": -0.27,
                "sector": "Finance",
                "fund_score": 55,
                "efund_score": 55,
                "earn_qual": 55,
                "sales_gr": 10,
                "fin_str": 50,
                "inst_back": 50,
                "canslim": 12,
                "minervini": 10,
                "inv_score": 60,
                "fund_det": None,
                "narrative": "",
                "supertrend": "",
            }
        }
        html_out = tmp_path / "intraday.html"
        with patch.object(pm, "INTRADAY_REPORT", html_out), \
             patch.object(pm, "EOD_REPORT", tmp_path / "eod.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=(wrong_fuzzy_db, "2026-06-04")), \
             patch.object(pm, "_fetch_live_prices_yf", return_value={"BAJAJHLDNG": 10319.0}), \
             patch.object(pm, "_is_market_hours", return_value=True):
            out = pm.run_intraday_view(live=True, csv_path=csv_path)

        assert "-0.5%" in out
        assert "+1080" not in out
        content = html_out.read_text()
        assert 'data-day="-0.5000"' in content
        assert "+1080" not in content

    def test_premier_explosives_is_not_fetched_as_premier(self):
        assert pm._YF_TICKER_OVERRIDES.get("PREMIEREXP") != "PREMIER"
        assert "PREMIEREXP" in pm._YF_SKIP


# ── run_eod_report ────────────────────────────────────────────────────────────

class TestRunEodReport:
    def _setup(self, tmp_path):
        csv_path = tmp_path / "port.csv"
        db_path  = tmp_path / "db.sqlite"
        _make_csv(_SAMPLE_ROWS, csv_path)
        _make_db(db_path)
        return csv_path, db_path

    def test_returns_success(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"):
            result = pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        assert result["success"] is True
        assert result["path"] == str(eod_out)

    def test_tata_motors_demerger_broker_aliases_resolve_to_new_entities(self):
        assert pm._BROKER_TO_NSE["TATCOV"] == "TMCV"
        assert pm._BROKER_TO_NSE["TATMOT"] == "TMPV"
        assert pm._BROKER_TO_NSE["TATCOV"] != "TATAMOTORS"

    def test_tata_motors_demerger_adjusts_alert_pnl_to_combined_position(self):
        rows = [
            {
                "broker": "TMCV",
                "value_cost": 33282.35,
                "value_mkt": 39804.0,
                "upnl": 6521.65,
                "upnl_pct": 19.59,
                "rpnl": 0.0,
            },
            {
                "broker": "TMPV",
                "value_cost": 32683.0,
                "value_mkt": 13692.0,
                "upnl": -18991.0,
                "upnl_pct": -58.11,
                "rpnl": 43985.32,
            },
        ]

        pm._apply_corporate_action_adjustments(rows)

        expected_total_pct = 31515.97 / 65965.35 * 100.0
        assert rows[1]["alert_pnl_pct"] == pytest.approx(expected_total_pct)
        assert rows[1]["economic_pnl"] == pytest.approx(31515.97)
        assert rows[1]["corporate_action_group"] == "Tata Motors demerger"

    def test_llm_stock_view_lookup_and_badge(self, tmp_path):
        path = tmp_path / "llm_stock_views.json"
        path.write_text(
            json.dumps(
                {
                    "views": [
                        {
                            "symbol": "DMART",
                            "final_verdict": "MUST BUY",
                            "short_term_view": "MUST BUY",
                            "long_term_view": "HOLD",
                            "confidence": 0.82,
                            "key_reasons": ["strong trend"],
                            "risks_to_view": ["valuation"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        lookup = pm._load_llm_stock_view_lookup(path)
        view = pm._llm_view_for_row({"broker": "AVESUP", "db": {"symbol": "DMART"}}, lookup)

        assert view["final_verdict"] == "MUST BUY"
        assert "MUST BUY" in pm._llm_verdict_badge(view["final_verdict"])

    def test_eod_report_labels_llm_surface_as_ai_view(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        (tmp_path / "llm_stock_views.json").write_text(
            json.dumps(
                {
                    "views": [
                        {
                            "symbol": "TATSTE",
                            "final_verdict": "MUST BUY",
                            "short_term_view": "MUST BUY",
                            "long_term_view": "HOLD",
                            "confidence": 0.82,
                            "key_reasons": ["strong trend"],
                            "risks_to_view": ["valuation"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)

        content = eod_out.read_text(encoding="utf-8")
        assert "AI Verdict Zone" in content
        assert "<th>AI View</th>" in content
        assert "AI Stock View" in content
        assert "AI MUST BUY" in content
        assert "LLM View" not in content
        assert "LLM Verdict Zone" not in content

    def test_html_file_written(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "_PG_DSN", "dbname=does_not_exist_zzz"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        assert eod_out.exists()

    def test_html_contains_all_signal_sections(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "_PG_DSN", "dbname=does_not_exist_zzz"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        content = eod_out.read_text()
        for label in ("STRONG BUY", "BUY", "HOLD", "SELL"):
            assert label in content, f"Missing section: {label}"

    def test_html_contains_kpis(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        content = eod_out.read_text()
        assert "Invested" in content
        assert "Market Value" in content
        assert "Sector" in content

    def test_html_contains_first_class_portfolio_ledger_sections(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "_load_transactions", return_value=[{
                 "symbol": "TATSTE",
                 "purchase_date": "2025-01-01",
                 "sale_date": "2025-06-01",
                 "qty": 10.0,
                 "purchase_rate": 100.0,
                 "sale_rate": 120.0,
                 "purchase_value": 1000.0,
                 "sale_value": 1200.0,
                 "pnl": 200.0,
                 "pnl_pct": 20.0,
                 "tenure_bucket": "STCG",
             }]):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        content = eod_out.read_text()
        assert "Daily Portfolio Ledger" in content
        assert "Portfolio Status" in content
        assert "Open Positions &amp; Unrealized P&amp;L" in content
        assert "Realized P&amp;L by Current Holding" in content
        assert "Closed Transactions Ledger" in content

    def test_eod_report_uses_rs_vs_nifty500_in_visible_tables(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "_PG_DSN", "dbname=does_not_exist_zzz"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)

        content = eod_out.read_text()
        assert "RS vs NIFTY 500" in content
        assert "<th>RS vs N500</th>" in content
        assert "110.0" in content
        assert "VCP" in content
        assert "RS Strategy" in content
        assert "RSI Strat." not in content
        assert "<th>RSI</th>" not in content

    def test_html_contains_alert_zone_and_clickable_stock_details(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        content = eod_out.read_text()
        assert "Portfolio Alert Zone" in content
        assert "Exit / Reduce" in content
        assert "Add / Accumulate" in content
        assert 'class="portfolio-position-row"' in content
        assert 'class="stock-detail-row"' in content
        assert "Technical Details" in content
        assert "Fundamental Details" in content

    def test_eod_bubble_chart_has_rich_tooltips(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)

        content = eod_out.read_text()
        assert 'class="bubble-point"' in content
        assert 'data-tooltip-title=' in content
        assert 'data-tooltip-tech=' in content
        assert 'data-tooltip-fund=' in content
        assert 'data-tooltip-investment=' in content
        assert 'data-tooltip-pnl=' in content
        assert "function wireBubbleTooltips" in content
        assert "Technical Score" in content
        assert "Fundamental Score" in content
        assert "P&amp;L" in content

    def test_eod_report_omits_duplicated_legacy_views(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)

        content = eod_out.read_text()
        assert "Open Positions &amp; Unrealized P&amp;L" in content
        assert "Portfolio Alert Zone" in content
        assert "Sector Exposure" in content
        assert "Top 5 Buy Opportunities" not in content
        assert "Top 5 Sell Candidates" not in content
        assert "Signal Summary" not in content
        assert "All-Stock Heat Strip" not in content
        assert '<span class="title">STRONG BUY' not in content
        assert '<span class="title">BUY &nbsp;' not in content
        assert '<span class="title">HOLD &nbsp;' not in content
        assert '<span class="title">SELL &nbsp;' not in content

    def test_eod_report_supplements_missing_stage_fund_details_from_pg_cache(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch("terminal.portfolio_monitor._PG_DSN", "dbname=does_not_exist_zzz"):
            records, snap_date = pm._load_db_snapshot(db_path)
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"), \
             patch.object(pm, "_load_db_snapshot", return_value=(records, snap_date)), \
             patch.object(pm, "_load_latest_fundamentals_lookup", return_value={
                 "HDFCBANK": {
                     "pnl_summary": "Sales: 100 Cr (YoY +10%)",
                     "ratios_summary": "ROCE: 20; ROE: 15; P/E: 12",
                 }
             }):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        content = eod_out.read_text()
        assert "Sales: 100 Cr" in content

    def test_html_contains_strategy_explanation(self, tmp_path):
        csv_path, db_path = self._setup(tmp_path)
        eod_out = tmp_path / "eod.html"
        with patch.object(pm, "EOD_REPORT", eod_out), \
             patch.object(pm, "INTRADAY_REPORT", tmp_path / "intraday.html"):
            pm.run_eod_report(csv_path=csv_path, db_path=db_path)
        content = eod_out.read_text()
        assert "CANSLIM" in content
        assert "Minervini" in content
        assert "Momentum" in content

    def test_missing_csv_returns_failure(self, tmp_path):
        result = pm.run_eod_report(
            csv_path=tmp_path / "nonexistent.csv",
            db_path=tmp_path / "nonexistent.db",
        )
        assert result["success"] is False
        assert result["path"] is None
        assert result["note"]  # has an error message


# ── generate_preset_report delegation ────────────────────────────────────────

class TestGeneratePresetReport:
    def test_portfolio_monitor_delegates_to_module(self, tmp_path):
        from terminal.reports import generate_preset_report
        fake_result = {
            "path": str(tmp_path / "eod.html"), "success": True, "note": "ok"
        }
        with patch("terminal.portfolio_monitor.run_eod_report", return_value=fake_result):
            result = generate_preset_report("portfolio-monitor", "html")
        assert result["success"] is True
        assert result["report_type"] == "portfolio-monitor"
        assert result["format"] == "html"
        assert "My Portfolio" in result["title"]

    def test_invalid_type_still_raises(self):
        from terminal.reports import generate_preset_report
        with pytest.raises(ValueError, match="portfolio-monitor"):
            generate_preset_report("not-a-valid-type")


# ── daily_refresh integration ─────────────────────────────────────────────────

class TestDailyRefreshStep:
    def test_step_exists(self):
        import daily_refresh
        assert callable(daily_refresh.step_portfolio_monitor)

    def test_step_intraday_dry_run(self):
        import daily_refresh
        result = daily_refresh.step_portfolio_monitor(dry_run=True, intraday=True)
        assert result is True  # dry-run always returns True

    def test_step_eod_dry_run(self):
        import daily_refresh
        result = daily_refresh.step_portfolio_monitor(dry_run=True, intraday=False)
        assert result is True


# ── Command registry ──────────────────────────────────────────────────────────

class TestCommandRegistry:
    def test_my_portfolio_command_registered(self):
        import nse_agent
        registry = nse_agent._build_command_registry()
        names = registry.handler_names
        assert "my-portfolio" in names

    def test_my_portfolio_matches_slash_command(self):
        import nse_agent
        registry = nse_agent._build_command_registry()
        # Verify the match_fn fires for the expected prefixes
        handlers = {h.name: h for h in registry._handlers}
        h = handlers["my-portfolio"]
        assert h.match_fn("/my-portfolio")
        assert h.match_fn("/my-portfolio eod")
        assert h.match_fn("/my-portfolio sell")
        assert h.match_fn("/my_portfolio")          # underscore alias
        assert not h.match_fn("/scan something")
        assert not h.match_fn("/report")


# ── _is_market_hours ─────────────────────────────────────────────────────────

class TestIsMarketHours:
    def _patch_now(self, fake_naive_utc):
        """Return a context manager patching datetime.now(utc) → fake_naive_utc."""
        import datetime as _dt
        aware = _dt.datetime(
            fake_naive_utc.year, fake_naive_utc.month, fake_naive_utc.day,
            fake_naive_utc.hour, fake_naive_utc.minute, fake_naive_utc.second,
            tzinfo=_dt.timezone.utc,
        )
        mock_dt = MagicMock()
        mock_dt.datetime.now.return_value = aware
        mock_dt.timedelta = _dt.timedelta
        mock_dt.time = _dt.time
        mock_dt.timezone = _dt.timezone
        return patch("terminal.portfolio_monitor.datetime", mock_dt)

    def test_weekday_during_hours(self):
        import datetime
        # Monday 10:00 IST = 04:30 UTC
        fake_utc = datetime.datetime(2026, 6, 1, 4, 30, 0)
        with self._patch_now(fake_utc):
            assert pm._is_market_hours() is True

    def test_weekend_returns_false(self):
        import datetime
        # Saturday 10:00 IST = 04:30 UTC
        fake_utc = datetime.datetime(2026, 5, 30, 4, 30, 0)
        with self._patch_now(fake_utc):
            assert pm._is_market_hours() is False

    def test_before_open(self):
        import datetime
        # Monday 03:44 UTC = 09:14 IST — one minute before open
        fake_utc = datetime.datetime(2026, 6, 1, 3, 44, 0)
        with self._patch_now(fake_utc):
            assert pm._is_market_hours() is False


# ── HTML badge helpers ────────────────────────────────────────────────────────

class TestHtmlHelpers:
    def test_sig_badge_buy(self):
        html = pm._sig_badge("BUY")
        assert "BUY" in html
        assert "#22c55e" in html

    def test_sig_badge_sell(self):
        html = pm._sig_badge("SELL")
        assert "SELL" in html
        assert "#ef4444" in html

    def test_sig_badge_none(self):
        html = pm._sig_badge(None)
        assert "–" in html

    def test_stage_badge_stage2(self):
        html = pm._stage_badge("STAGE_2")
        assert "S2" in html
        assert "#22c55e" in html

    def test_stage_badge_stage4(self):
        html = pm._stage_badge("STAGE_4")
        assert "S4" in html
        assert "#ef4444" in html

    def test_pct_color_positive(self):
        assert pm._pct_color(25.0) == "#16a34a"

    def test_pct_color_negative(self):
        assert pm._pct_color(-25.0) == "#dc2626"
