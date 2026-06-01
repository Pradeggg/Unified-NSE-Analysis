# NSE PostgreSQL Strategy Comparison

Source: PostgreSQL `market.equity_eod`; benchmark: PostgreSQL `market.index_eod` / `Nifty 500`.
Window: 2025-01-01 to 2026-05-29; universe: top 200 liquid EQ symbols as of 2026-05-29.
Costs: 5 bps slippage + 3 bps brokerage per fill. Starting capital: 1,000,000.
Rows: 65,357; symbols after feature lookback filters: 193.

## Leaderboard

| Rank | Strategy | Return % | Max DD % | Nifty 500 % | Excess % | Fills | Closed Trades | Win Rate % | Realized P&L | Open |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | vcp_breakout_v1 | 31.12 | 25.98 | 0.78 | 30.34 | 601 | 238 | 23.95 | 128717.86 | 12 |
| 2 | momentum_rotation_v1 | 14.26 | 16.47 | 0.78 | 13.48 | 630 | 300 | 35.33 | -97325.32 | 30 |
| 3 | moving_average_trend_v1 | 12.84 | 17.96 | 0.78 | 12.06 | 859 | 413 | 27.84 | -160267.41 | 33 |
| 4 | stage2_continuation_v1 | 28.03 | 33.91 | 0.78 | 27.25 | 413 | 117 | 18.80 | 57804.83 | 8 |
| 5 | darvas_box_breakout_v1 | 13.62 | 24.97 | 0.78 | 12.84 | 609 | 291 | 27.84 | -133717.12 | 27 |
| 6 | donchian_turtle_breakout_v1 | 8.90 | 24.55 | 0.78 | 8.13 | 413 | 137 | 35.04 | -78245.10 | 9 |
| 7 | mean_reversion_uptrend_v1 | -17.17 | 22.99 | 0.78 | -17.95 | 4719 | 2353 | 45.52 | -163861.09 | 13 |
| 8 | minervini_trend_template_v1 | 0.00 | 0.00 | 0.78 | -0.78 | 0 | 0 | 0.00 | 0.00 | 0 |

## Readout

- `vcp_breakout_v1` is the best current candidate on this screen by the active risk-adjusted score, but drawdown is high and win rate is weak.
- `stage2_continuation_v1` has the second-best return, but the worst drawdown in this run, so it needs tighter exits or position sizing before paper deployment.
- `mean_reversion_uptrend_v1` overtrades heavily and loses money after costs; it should be quarantined or redesigned.
- `minervini_trend_template_v1` produced no trades because the strict fundamental filters did not pass on the available static fundamentals.

## Caveats

- Historical `scores.stage_snapshots` only cover May 2026, so pre-May-2026 Stage 2 was proxied from EOD trend structure: `close > SMA50 > SMA200`.
- Fundamental columns came from static `scores.fundamentals`; this is not point-in-time safe and should be replaced with dated fundamentals before relying on results.
- Ranking uses active strategies first, then `total_return_pct - max_drawdown_pct`; this is a screening score, not a final allocation model.
- Each strategy was replayed independently with the same initial capital, so results are comparable across strategies.
