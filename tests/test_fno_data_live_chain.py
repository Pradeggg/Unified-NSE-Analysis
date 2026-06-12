import pandas as pd

from terminal import fno_data


class _Response:
    status_code = 404

    def raise_for_status(self):
        raise RuntimeError("404 Client Error: Not Found")


class _Session:
    def get(self, url, timeout=20):
        return _Response()


def test_live_option_chain_404_falls_back_to_eod(monkeypatch):
    eod = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-11",
                "symbol": "MIDCPNIFTY",
                "expiry_date": "2026-06-18",
                "option_type": "CE",
                "strike": 12000,
                "oi": 100,
                "oi_change": 10,
                "volume": 20,
                "last_price": 50.0,
                "underlying": 12100.0,
            },
            {
                "trade_date": "2026-06-11",
                "symbol": "MIDCPNIFTY",
                "expiry_date": "2026-06-18",
                "option_type": "PE",
                "strike": 12000,
                "oi": 120,
                "oi_change": 12,
                "volume": 25,
                "last_price": 45.0,
                "underlying": 12100.0,
            },
        ]
    )

    monkeypatch.setattr(fno_data, "_get_nse_session", lambda force_refresh=False: _Session())
    monkeypatch.setattr(fno_data, "get_eod_option_chain", lambda symbol, expiry_date=None: eod)

    result = fno_data.fetch_live_option_chain("MIDCPNIFTY")

    assert result["source"] == "eod-fallback"
    assert result["symbol"] == "MIDCPNIFTY"
    assert result["underlying"] == 12100.0
    assert result["data"][0]["ce_oi"] == 100
    assert "error" not in result
