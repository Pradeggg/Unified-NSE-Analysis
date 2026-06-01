# NSE PostgreSQL Strategy Lab

Source: PostgreSQL `market.equity_eod` joined to `scores.stage_snapshots`.
Benchmark: `Nifty 500`.
Window: 2025-01-01 to 2026-05-29; rows: 65357; symbols: 193.
Costs: 5.0 bps slippage + 3.0 bps brokerage. Starting capital: 1000000.0.

## Leaderboard

| Rank | Strategy | Return % | Max DD % | Excess % | Profit Factor | Expectancy | Turnover % | Cost Drag % | Fills | Win Rate % |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | vcp_breakout_v1 | 40.42 | 19.66 | 39.65 | 1.32 | 742.38 | 3834.03 | 3.07 | 474 | 23.94 |
| 2 | stage2_continuation_v1 | 46.82 | 39.84 | 46.04 | 1.55 | 2532.32 | 2558.00 | 2.05 | 352 | 14.00 |
| 3 | moving_average_trend_v1 | 12.84 | 17.96 | 12.06 | 0.63 | -388.06 | 2376.94 | 1.90 | 859 | 27.84 |
| 4 | momentum_rotation_v1 | 8.35 | 19.46 | 7.57 | 1.17 | 236.88 | 2350.96 | 1.88 | 654 | 35.19 |
| 5 | darvas_box_breakout_v1 | -1.60 | 22.90 | -2.38 | 0.90 | -145.06 | 2309.36 | 1.85 | 597 | 32.20 |
| 6 | donchian_turtle_breakout_v1 | -3.33 | 29.70 | -4.11 | 0.66 | -1230.74 | 2388.64 | 1.91 | 446 | 28.77 |
| 7 | mean_reversion_uptrend_v1 | -16.05 | 22.64 | -16.83 | 0.85 | -64.64 | 18502.01 | 14.80 | 4742 | 46.26 |
| 8 | minervini_trend_template_v1 | 0.00 | 0.00 | -0.78 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0.00 |

## Notes

- Ranking sorts active strategies first, then by `rank_score`.
- `rank_score` is return minus max drawdown, with inactive strategies penalized.
- Stage values are sourced from `scores.stage_snapshots`.
