from pathlib import Path

from terminal import reports


def _minimal_sector_rotation_md() -> str:
    return "\n".join(
        [
            "# Sector Rotation Investment Report",
            "",
            "**Generated:** 2026-06-24",
            "**Data as of:** 2026-06-24",
            "",
            "## Market Brief",
            "",
            "Yesterday's EOD market brief.",
            "",
            "## 1. Sector Rotation",
            "",
            "| Rank | Index | Sector Lens | Close | 5D | 1M | 3M | 6M | RS 1M | Base Score | Cycle Adj | Cycle-Adjusted Score |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            "| 1 | Nifty Media | Media & Entertainment | 1519.30 | 0.9% | 10.2% | 15.9% | 7.0% | 9.4% | 7.8 | 0.0 | 7.8 |",
            "",
            "## 2. Investment Candidates",
            "",
            "### Media & Entertainment",
            "",
            "| Symbol | Company | Price | Signal | Setup | Action | Score | Tech | RS | Fund | RSI | Supertrend | Pattern | Volume Ratio |",
            "|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|",
            "| NUVAMA | NUVAMA | 1736.30 | HOLD | NEUTRAL | WATCHLIST | 58.0 | 49.3 | 29.7% | 73.3 | 71.6 | BULLISH | TRENDING_OR_CHOPPY | 0.70x |",
        ]
    )


def test_sector_ric_auto_fallback_adds_live_topdown_and_tradeability(monkeypatch, tmp_path: Path):
    md = tmp_path / "sector_rotation.md"
    md.write_text(_minimal_sector_rotation_md(), encoding="utf-8")

    monkeypatch.setattr(reports, "_latest_sector_rotation_markdown", lambda: md)
    monkeypatch.setattr(
        reports,
        "_load_live_sector_topdown",
        lambda limit=3: (
            [
                {
                    "rank": 1,
                    "index": "NIFTY AUTO",
                    "sector": "EV & Auto Ancillaries",
                    "last": 27100,
                    "pct_change": 2.9,
                    "day_low": 26500,
                    "day_high": 27200,
                },
                {
                    "rank": 2,
                    "index": "NIFTY REALTY",
                    "sector": "Real Estate",
                    "last": 830,
                    "pct_change": 1.0,
                    "day_low": 820,
                    "day_high": 840,
                },
            ],
            {
                "indices": {
                    "NIFTY 50": {"pct_change": 0.6},
                    "NIFTY BANK": {"pct_change": 0.5},
                    "INDIA VIX": {"pct_change": -3.0},
                },
                "adv_dec": {"advances": 300, "declines": 440},
                "source": "test",
            },
        ),
    )
    monkeypatch.setattr(
        reports,
        "_build_pg_rotation_row",
        lambda query, topdown_rows=None: {
            "rank": "1",
            "index": "NIFTY AUTO",
            "sector": "EV & Auto Ancillaries",
            "close": "26,384.35",
            "ret_5d": "-1.3%",
            "ret_1m": "-0.3%",
            "ret_3m": "+7.6%",
            "ret_6m": "-4.2%",
            "rs_1m": "-1.2%",
            "score": "1.0",
            "live_1d": "+2.9%",
            "source": "test",
        },
    )
    monkeypatch.setattr(
        reports,
        "_load_focus_candidate_rows",
        lambda index_name, sector_name, limit=20: [
            {
                "symbol": "EXIDEIND",
                "company": "EXIDEIND",
                "price": "399.50",
                "signal": "BUY",
                "setup": "BREAKOUT_OR_RETEST",
                "action": "BREAKOUT_WATCH",
                "score": "59.5",
                "tech": "75.3",
                "rs": "+18.7%",
                "fund": "51.1",
                "rsi": "47.5",
                "supertrend": "BULLISH",
                "pattern": "INDEX_CONSTITUENT",
                "volume_ratio": "1.20x",
                "_stage": "STAGE_2",
                "_quality_growth": "Tactical/technical only",
                "_enhanced_fund_score": "51.1",
                "_earnings_quality": "52.0",
                "_sales_growth": "44.2",
                "_financial_strength": "55.2",
                "_read": "Trend and signal are aligned; needs price-volume trigger.",
            }
        ],
    )
    monkeypatch.setattr(reports, "_load_fno_eligible_symbols", lambda: {"EXIDEIND"})
    monkeypatch.setattr(reports, "_load_latest_fno_signal_map", lambda symbols: {})
    monkeypatch.setattr(reports, "_scan_intraday_tradeability", lambda symbols, no_web=False: {})
    monkeypatch.setattr(reports, "_build_ric_sections", lambda *a, **k: "## RIC Evidence Status\n\npatched")

    content, meta = reports._build_sector_specific_content("NIFTY AUTO", ric=True, max_companies=1, no_web=True)

    assert meta["sector"] == "EV & Auto Ancillaries"
    assert "## Broader Market RIC Pulse" in content
    assert "## Top 3 Strongest Sector Indices Today" in content
    assert "Focus sector selection: **NIFTY AUTO / EV & Auto Ancillaries** is live rank #1" in content
    assert "## EOD Market Brief Context" in content
    assert "## MOAT And Growth Lens" in content
    assert "## Swing, Intraday, And F&O Tradeability Funnel" in content
    assert "EXIDEIND" in content


def test_sector_ric_can_auto_focus_live_leader(monkeypatch, tmp_path: Path):
    md = tmp_path / "sector_rotation.md"
    md.write_text(_minimal_sector_rotation_md(), encoding="utf-8")
    monkeypatch.setattr(reports, "_latest_sector_rotation_markdown", lambda: md)
    monkeypatch.setattr(
        reports,
        "_load_live_sector_topdown",
        lambda limit=3: (
            [{"rank": 1, "index": "NIFTY AUTO", "sector": "EV & Auto Ancillaries", "pct_change": 3.0}],
            {"indices": {}, "source": "test"},
        ),
    )
    monkeypatch.setattr(
        reports,
        "_build_pg_rotation_row",
        lambda query, topdown_rows=None: {
            "rank": "1",
            "index": "NIFTY AUTO",
            "sector": "EV & Auto Ancillaries",
            "close": "26,384.35",
            "ret_5d": "-1.3%",
            "ret_1m": "-0.3%",
            "ret_3m": "+7.6%",
            "ret_6m": "-4.2%",
            "rs_1m": "-1.2%",
            "score": "1.0",
            "live_1d": "+3.0%",
            "source": "test",
        },
    )
    monkeypatch.setattr(reports, "_load_focus_candidate_rows", lambda *a, **k: [])
    monkeypatch.setattr(reports, "_build_ric_sections", lambda *a, **k: "## RIC Evidence Status\n\npatched")

    content, meta = reports._build_sector_specific_content("", ric=True, max_companies=1, no_web=True)

    assert meta["index"] == "NIFTY AUTO"
    assert "Focus sector selection: **NIFTY AUTO / EV & Auto Ancillaries** is live rank #1" in content


def test_sector_ric_uses_screener_fallback_for_missing_latest_results(monkeypatch):
    candidate_rows = [
        {
            "symbol": "EXIDEIND",
            "company": "EXIDEIND",
            "price": "399.50",
            "signal": "BUY",
            "setup": "BREAKOUT_OR_RETEST",
            "action": "BREAKOUT_WATCH",
            "score": "59.5",
            "tech": "75.3",
            "rs": "+18.7%",
            "fund": "51.1",
            "rsi": "47.5",
            "supertrend": "BULLISH",
            "pattern": "INDEX_CONSTITUENT",
            "volume_ratio": "2.36x",
        }
    ]

    def fake_collect(symbol: str, *, no_web: bool = False):
        screener = {
            "symbol": symbol,
            "source_url": "https://www.screener.in/company/EXIDEIND/consolidated/",
            "ratios": {"Stock P/E": "39.9", "ROCE": "8.54", "ROE": "5.97"},
            "quarterly": {
                "_headers": ["Dec 2025", "Mar 2026"],
                "Sales+": ["4,201", "4,735"],
                "Net Profit+": ["193", "217"],
                "EPS in Rs": ["2.26", "2.53"],
                "OPM %": ["10%", "10%"],
            },
            "annual_pl": {
                "_headers": ["Mar 2025", "Mar 2026"],
                "Sales+": ["17,238", "17,995"],
                "Net Profit+": ["753", "860"],
                "EPS in Rs": ["8.80", "10.05"],
                "OPM %": ["10%", "10%"],
            },
            "pros": ["Company has reduced debt."],
            "cons": ["Company has a low return on equity."],
            "shareholding": {"Promoters": "45.99%", "FIIs": "10.30%", "DIIs": "19.12%"},
            "announcements": [],
            "concalls": [],
        }
        return {
            "symbol": symbol,
            "snapshot": {},
            "technical": {},
            "screener": screener,
            "latest_results": reports._latest_with_screener_fallback(
                symbol,
                {"symbol": symbol, "status": "missing", "facts": {}},
                screener,
            ),
            "announcements": {},
            "bse_filings": {},
            "forensic": {},
            "concalls": {},
        }

    monkeypatch.setattr(reports, "_collect_symbol_ric_evidence", fake_collect)

    content = reports._build_ric_sections(
        "EV & Auto Ancillaries",
        "NIFTY AUTO",
        candidate_rows,
        max_companies=1,
        no_web=False,
    )

    assert "EXIDEIND | OK | OK | fallback" in content
    assert "Revenue 4,735 (Mar 2026) via Screener quarterly" in content
    assert "PAT 217 (Mar 2026) via Screener quarterly" in content
    assert "EPS 2.53 (Mar 2026) via Screener quarterly" in content
    assert "**Annual snapshot:** Sales 17,995; Net profit 860; EPS 10.05; OPM 10%" in content
    assert "**Quarter snapshot:** Sales 4,735; Net profit 217; EPS 2.53; OPM 10%" in content
    assert "**Shareholding:** Promoters 45.99%; FII 10.30%; DII 19.12%" in content
