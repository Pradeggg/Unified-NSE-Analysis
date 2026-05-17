import unittest
from unittest.mock import patch


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class IntradayPostgresStorageTests(unittest.TestCase):
    def test_ensure_intraday_schema_creates_separate_tables_and_indexes(self):
        from terminal.intraday_storage import ensure_intraday_schema

        conn = FakeConnection()

        ensure_intraday_schema(conn)

        sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS intraday", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS intraday.quote_snapshots", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS intraday.ohlcv_bars", sql_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS intraday.futures_snapshots", sql_text)
        self.assertIn("idx_intraday_quote_symbol_time", sql_text)
        self.assertIn("idx_intraday_futures_symbol_expiry_time", sql_text)
        self.assertEqual(conn.commits, 1)

    @patch("terminal.intraday_storage.execute_values")
    def test_persist_intraday_snapshot_upserts_quote_snapshot(self, mock_execute_values):
        from terminal.intraday_storage import persist_intraday_snapshot

        conn = FakeConnection()
        snapshot = {
            "symbol": "RELIANCE",
            "last_price": 1418.0,
            "change": -17.2,
            "pct_change": -1.2,
            "day_high": 1428.0,
            "day_low": 1418.0,
            "vwap": 1421.52,
            "as_of": "11-May-2026 09:26:33",
            "source": "NSE live API (real-time)",
            "source_priority": ["NSE website live quote", "yfinance candles fallback"],
        }

        result = persist_intraday_snapshot(snapshot, conn=conn)

        self.assertTrue(result["ok"])
        self.assertEqual(result["rows_inserted"], 1)
        self.assertEqual(conn.commits, 1)
        sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS intraday", sql_text)
        self.assertEqual(mock_execute_values.call_count, 1)
        insert_sql = mock_execute_values.call_args.args[1]
        self.assertIn("INSERT INTO intraday.quote_snapshots", insert_sql)
        self.assertIn("ON CONFLICT (symbol, source, as_of)", insert_sql)

    def test_persist_intraday_snapshot_ignores_error_payloads(self):
        from terminal.intraday_storage import persist_intraday_snapshot

        result = persist_intraday_snapshot({"symbol": "DMART", "error": "NSE unavailable"}, conn=FakeConnection())

        self.assertFalse(result["ok"])
        self.assertEqual(result["rows_inserted"], 0)

    @patch("terminal.intraday_storage.execute_values")
    def test_persist_live_futures_snapshot_upserts_futures_history(self, mock_execute_values):
        from terminal.intraday_storage import persist_live_futures_snapshot

        conn = FakeConnection()
        snapshot = {
            "symbol": "NIFTY",
            "underlying": 23700.0,
            "source": "live-nse-api",
            "as_of": "13:15:00",
            "lot_size": 75,
            "futures": [
                {
                    "expiry": "2026-05-28",
                    "last_price": 23742.0,
                    "change_pct": 0.2,
                    "oi": 100000,
                    "oi_change": 5000,
                    "volume": 12000,
                }
            ],
        }

        result = persist_live_futures_snapshot(snapshot, conn=conn)

        self.assertTrue(result["ok"])
        self.assertEqual(result["rows_inserted"], 1)
        self.assertEqual(conn.commits, 1)
        insert_sql = mock_execute_values.call_args.args[1]
        self.assertIn("INSERT INTO intraday.futures_snapshots", insert_sql)
        self.assertIn("ON CONFLICT (symbol, expiry, source, as_of)", insert_sql)

    @patch("terminal.intraday_storage.execute_values")
    def test_persist_intraday_scan_result_upserts_scan_signals(self, mock_execute_values):
        from terminal.intraday_storage import persist_intraday_scan_result

        conn = FakeConnection()
        scan = {
            "interval": "15m",
            "strategies": ["ema", "volume"],
            "as_of": "2026-05-11 09:45",
            "buy_signals": [
                {
                    "symbol": "TCS",
                    "strategy": "ema",
                    "direction": "BUY",
                    "entry": 2380.0,
                    "stop": 2360.0,
                    "target": 2420.0,
                    "rr": 2.0,
                }
            ],
            "sell_signals": [],
            "watch_alerts": [],
        }

        result = persist_intraday_scan_result(scan, conn=conn)

        self.assertTrue(result["ok"])
        self.assertEqual(result["rows_inserted"], 1)
        self.assertEqual(conn.commits, 1)
        sql_text = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
        self.assertIn("CREATE TABLE IF NOT EXISTS intraday.scan_signals", sql_text)
        insert_sql = mock_execute_values.call_args.args[1]
        self.assertIn("INSERT INTO intraday.scan_signals", insert_sql)
        self.assertIn("ON CONFLICT (snapshot_ts, scan_key, symbol, strategy, direction)", insert_sql)

    def test_legacy_screener_writer_uses_intraday_schema(self):
        from terminal import intraday

        scan = {
            "interval": "15m",
            "strategies": ["ema"],
            "buy_signals": [{"symbol": "TCS", "strategy": "ema", "direction": "BUY"}],
            "sell_signals": [],
            "watch_alerts": [],
        }
        with patch.object(intraday, "persist_intraday_scan_result", return_value={"ok": True, "rows_inserted": 1}) as persist:
            inserted = intraday.write_intraday_to_pg(scan)

        persist.assert_called_once_with(scan)
        self.assertEqual(inserted, 1)


if __name__ == "__main__":
    unittest.main()
