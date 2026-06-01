# NSE PostgreSQL Strategy Comparison - Historical Stage Snapshots

Source: PostgreSQL `market.equity_eod` joined to `scores.stage_snapshots`; benchmark: `Nifty 500`.
Window: 2025-01-01 to 2026-05-29; universe: top 200 liquid EQ symbols as of 2026-05-29.
Costs: 5 bps slippage + 3 bps brokerage per fill. Starting capital: 1,000,000.
Rows: 65,357; symbols: 193.

## Leaderboard

| Rank | Strategy | Return % | Max DD % | Nifty 500 % | Excess % | Fills | Closed Trades | Win Rate % | Realized P&L | Open |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | vcp_breakout_v1 | 40.42 | 19.66 | 0.78 | 39.65 | 474 | 188 | 23.94 | 139567.91 | 9 |
| 2 | stage2_continuation_v1 | 46.82 | 39.84 | 0.78 | 46.04 | 352 | 100 | 14.00 | 253232.41 | 12 |
| 3 | moving_average_trend_v1 | 12.84 | 17.96 | 0.78 | 12.06 | 859 | 413 | 27.84 | -160267.41 | 33 |
| 4 | momentum_rotation_v1 | 8.35 | 19.46 | 0.78 | 7.57 | 654 | 324 | 35.19 | 76747.89 | 6 |
| 5 | darvas_box_breakout_v1 | -1.60 | 22.90 | 0.78 | -2.38 | 597 | 295 | 32.20 | -42793.63 | 7 |
| 6 | donchian_turtle_breakout_v1 | -3.33 | 29.70 | 0.78 | -4.11 | 446 | 146 | 28.77 | -179688.46 | 4 |
| 7 | mean_reversion_uptrend_v1 | -16.05 | 22.64 | 0.78 | -16.83 | 4742 | 2365 | 46.26 | -152868.66 | 12 |
| 8 | minervini_trend_template_v1 | 0.00 | 0.00 | 0.78 | -0.78 | 0 | 0 | 0.00 | 0.00 | 0 |

## Notes

- Stage values are read from `scores.stage_snapshots`; missing top-200 rows after feature lookback are dropped.
- Ranking uses active strategies first, then `total_return_pct - max_drawdown_pct`.
- Existing richer May 2026 snapshots were preserved during the historical backfill.
