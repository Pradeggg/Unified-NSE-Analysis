# Agent Adda Intraday Alerts - Latest Cycle

- Time: 2026-08-03 11:55:21
- Cycle: 1
- Market: NIFTY 24,599 +0.88%, BANKNIFTY 57,793 +0.92%, VIX 11.96 +1.76%, breadth 633A/116D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok | strategy_time_gate ok: supertrend_breakout,near_breakout_volume,vcp,volume,darvas | fno_context ok | edge_memory ok: 5 | full universe rescan ok: scanned 209, tracking 15 | options_execution ok
- Fresh alerts: 3
- Total candidates: 3

## Trading Stance

- Stance: TRADE
- Headline: Trade only qualified setup(s); avoid chasing.
- Action: Use only the named trade-window candidates and respect invalidation.
- Reasons: Fresh alerts: 3; Alert candidates: 3; late_morning / NO_TRADE_WINDOW; volume confirmation missing


## Sharp Movers

| Symbol | Move | Chg | LTP | Level State | Ref Level | Read | Decision |
|---|---|---:|---:|---|---:|---|---|
| TCS | Sharp Rise | +2.8% | 2,431 | breaking resistance | 2,431 | WATCH watch | AVOID / No Trade |
| SBIN | Sharp Rise | +2.1% | 1,049 | breaking resistance | 1,049 | WATCH watch | AVOID / No Trade |

## Cycle Changes

- New added: ADANIENT, AXISBANK, BAJFINANCE, BHARTIARTL, DIXON, HINDALCO, ICICIBANK, KAYNES, LT, MCX, PAYTM, SBIN, SCHNEIDER, TCS, VMM
- Removed: none
- Forming: TCS, SBIN, ADANIENT, AXISBANK, HINDALCO, BAJFINANCE, MCX, ICICIBANK, LT, BHARTIARTL, DIXON
- Confirmed: VMM, PAYTM
- Active: KAYNES, SCHNEIDER

## Fresh Alerts

| Symbol | Side | Status | Decision | Options | Entry | Stop | T1 | RR |
|---|---:|---|---|---|---:|---:|---:|---:|
| KAYNES | LONG | long active | TRADE NOW | Option Buy OK | 3,817 | 3,806 | 3,846 | 2.5 |
| SCHNEIDER | LONG | long active | TRADE NOW | Option Buy OK | 1,363 | 1,359 | 1,372 | 2.1 |
| VMM | LONG | near trigger / watch | WAIT FOR RETEST | Prefer Futures | 111.11 | 110.84 | 111.69 | 2.1 |

## Tracker

| Symbol | Read | Decision | Options | Score | F&O | LTP | Chg | Entry | Stop | T1/RR |
|---|---|---|---|---:|---|---:|---:|---:|---:|---:|
| KAYNES | LONG long active | TRADE NOW | Option Buy OK | 70 | sideways PCR 0.59 basis 21.40 MP 3,650 | 3,817 | n/a | 3,817 | 3,806 | 3,846/2.5R |
| SCHNEIDER | LONG long active | TRADE NOW | Option Buy OK | 82 | sideways PCR n/a basis n/a MP n/a | 1,364 | +0.6% | 1,363 | 1,359 | 1,372/2.1R |
| VMM | LONG near trigger / watch | WAIT FOR RETEST | Prefer Futures | 47 | sideways PCR 0.54 basis 0.58 MP 115 | 111.11 | n/a | 111.11 | 110.84 | 111.69/2.1R |
| PAYTM | LONG near trigger / watch | WAIT FOR RETEST | Option Buy OK | 45 | sideways PCR 0.60 basis 8.50 MP 1,340 | 1,424 | n/a | 1,424 | 1,414 | 1,436/1.3R |
| TCS | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.97 basis 7.70 MP 2,440 | 2,431 | +2.8% | 2,431 | n/a | n/a |
| SBIN | WATCH watch | AVOID | No Trade | 3 | bullish PCR 0.98 basis 5.60 MP 1,040 | 1,049 | +2.1% | 1,049 | n/a | n/a |
| ADANIENT | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.83 basis 9.90 MP 3,100 | 3,067 | +1.9% | 3,067 | n/a | n/a |
| AXISBANK | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.70 basis 6.10 MP 1,260 | 1,251 | +1.7% | 1,251 | n/a | n/a |
| HINDALCO | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.78 basis 1.90 MP 980 | 990.75 | +1.7% | 990.75 | n/a | n/a |
| BAJFINANCE | WATCH watch | AVOID | No Trade | 3 | bullish PCR 0.91 basis 2.10 MP 1,050 | 1,160 | +1.6% | 1,160 | n/a | n/a |
| MCX | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.89 basis 15.00 MP 2,800 | 2,650 | -1.6% | 2,650 | n/a | n/a |
| ICICIBANK | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.67 basis 2.80 MP 1,450 | 1,446 | +1.6% | 1,446 | n/a | n/a |
| LT | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.80 basis 22.80 MP 4,000 | 3,996 | +1.4% | 3,996 | n/a | n/a |
| BHARTIARTL | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.76 basis 2.50 MP 1,960 | 1,950 | -1.1% | 1,950 | n/a | n/a |
| DIXON | WATCH watch | AVOID | No Trade | 3 | bearish PCR 0.79 basis -170.00 MP 14,500 | 13,931 | -0.8% | 13,931 | n/a | n/a |

## Why No Trade - Top 5 Blocked

| Symbol | Side | State | Decision | LTP | Trigger | Stop | T1 | RR | Why blocked |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| PAYTM | LONG | near trigger / watch | WAIT FOR RETEST / Option Buy OK / score 45 | 1,424 | 1,424 | 1,414 | 1,436 | 1.3 | gate WAIT FOR RETEST; needs break/hold confirmation; R:R 1.3 < min 2.0; late_morning / NO_TRADE_WINDOW; near trigger only; RR 1.3 acceptable |
| TCS | WATCH | watch | AVOID / No Trade / score 3 | 2,431 | 2,431 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; late_morning / NO_TRADE_WINDOW; MTF level-derived; F&O sideways |
| SBIN | WATCH | watch | AVOID / No Trade / score 3 | 1,049 | 1,049 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; late_morning / NO_TRADE_WINDOW; MTF level-derived; F&O bullish |
| ADANIENT | WATCH | watch | AVOID / No Trade / score 3 | 3,067 | 3,067 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; late_morning / NO_TRADE_WINDOW; MTF level-derived; F&O sideways |
| AXISBANK | WATCH | watch | AVOID / No Trade / score 3 | 1,251 | 1,251 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; late_morning / NO_TRADE_WINDOW; MTF level-derived; F&O sideways |

## Trade Decisions

| Symbol | Action | Options | Score | Market Regime | Reasons |
|---|---|---|---:|---|---|
| KAYNES | TRADE NOW | Option Buy OK | 70 | neutral | trigger active; RR 2.5 strong; scanner-confirmed; F&O sideways; volume-aware setup |
| SCHNEIDER | TRADE NOW | Option Buy OK | 82 | neutral | trigger active; RR 2.1 strong; price momentum aligned; scanner-confirmed; F&O sideways |
| VMM | WAIT FOR RETEST | Prefer Futures | 47 | neutral | near trigger only; RR 2.1 strong; scanner-confirmed; F&O sideways; volume-aware setup |
| PAYTM | WAIT FOR RETEST | Option Buy OK | 45 | neutral | near trigger only; RR 1.3 acceptable; scanner-confirmed; F&O sideways; volume-aware setup |
| TCS | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| SBIN | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O bullish; volume not confirmed |
| ADANIENT | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| AXISBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| HINDALCO | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| BAJFINANCE | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O bullish; volume not confirmed |
| MCX | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ICICIBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| LT | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| BHARTIARTL | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| DIXON | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O bearish; volume not confirmed |

## Trade Timing

| Symbol | Window | Timing Score | Time Bucket | Reasons |
|---|---|---:|---|---|
| KAYNES | NO_TRADE_WINDOW | 36 | late_morning | no persisted edge; late-morning timing; trigger active; R:R >= 2; F&O sideways |
| SCHNEIDER | NO_TRADE_WINDOW | 36 | late_morning | no persisted edge; late-morning timing; trigger active; R:R >= 2; F&O sideways |
| VMM | NO_TRADE_WINDOW | 26 | late_morning | no persisted edge; late-morning timing; near trigger; R:R >= 2; F&O sideways |
| PAYTM | NO_TRADE_WINDOW | 21 | late_morning | no persisted edge; late-morning timing; near trigger; R:R acceptable; F&O sideways |
| TCS | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| SBIN | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak |
| ADANIENT | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| AXISBANK | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| HINDALCO | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| BAJFINANCE | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak |
| MCX | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| ICICIBANK | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| LT | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| BHARTIARTL | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak; F&O sideways |
| DIXON | NO_TRADE_WINDOW | 0 | late_morning | no persisted edge; late-morning timing; watch-only structure; R:R weak |

## Options Execution

| Symbol | Verdict | Strategy | Option | Strike | Premium | Breakeven | Exp/DTE | IV | Delta/Theta | Expected Move | OI Wall | Notes |
|---|---|---|---|---:|---:|---:|---|---:|---|---:|---|---|
| KAYNES | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE ATM | 3,600 | 233.00 | 3,833 | 2026-08-25 / 22D | 58.8 | 0.56 / -5.01 | 523.08 | CE wall 4000, 3700 | ❌ IV 58.8% is high — options are expensive to buy; ❌ IV rank 97% — expensive relative to history |
| SCHNEIDER | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | option_chain; futures |
| VMM | USE SPREAD | Bull Call Debit Spread (USE DEBIT SPREAD) | CE ATM | 100.00 | 9.22 | 109.22 | 2026-08-25 / 22D | 30.3 | 0.87 / -0.05 | 8.03 | CE wall 110, 120 | ❌ IV 30.3% is high — options are expensive to buy; ⚠️  IV rank 34% — moderate; not the cheapest |
| PAYTM | USE SPREAD | Bull Call Debit Spread (USE DEBIT SPREAD) | CE ATM | 1,340 | 47.50 | 1,388 | 2026-08-25 / 22D | 38.0 | 0.51 / -1.24 | 124.44 | CE wall 1400, 1340 | ❌ IV 38.0% is high — options are expensive to buy; ⚠️  IV rank 51% — moderate; not the cheapest |
| TCS | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| SBIN | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIENT | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| AXISBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| HINDALCO | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| BAJFINANCE | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| MCX | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ICICIBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| LT | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| BHARTIARTL | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| DIXON | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |


## Edge Memory

| Symbol | Status | Role | Setup | Confidence | Persistence |
|---|---|---|---|---:|---:|
| n/a | n/a | n/a | n/a | n/a | n/a |

## F&O Context

| Symbol | Bias | PCR | Basis | Max Pain | Note |
|---|---|---:|---:|---:|---|
| KAYNES | sideways | 0.59 | 21.40 | 3,650 | PCR 0.59 call-heavy; fut basis +21.4; spot above max pain 3650; PE wall 3200; CE wall 3600 |
| SCHNEIDER | sideways | n/a | n/a | n/a |  |
| VMM | sideways | 0.54 | 0.58 | 115 | PCR 0.54 call-heavy; fut basis +0.58; spot below max pain 115; PE wall 110; CE wall 110 |
| PAYTM | sideways | 0.60 | 8.50 | 1,340 | PCR 0.60 call-heavy; fut basis +8.5; spot above max pain 1340; PE wall 1200; CE wall 1300 |
| TCS | sideways | 0.97 | 7.70 | 2,440 | PCR 0.97 balanced; fut basis +7.7; spot below max pain 2440; PE wall 2800; CE wall 2500 |
| SBIN | bullish | 0.98 | 5.60 | 1,040 | PCR 0.98 balanced; fut basis +5.6; spot above max pain 1040; PE wall 1000; CE wall 1050 |
| ADANIENT | sideways | 0.83 | 9.90 | 3,100 | PCR 0.83 balanced; fut basis +9.9; spot below max pain 3100; PE wall 3000; CE wall 3200 |
| AXISBANK | sideways | 0.70 | 6.10 | 1,260 | PCR 0.70 call-heavy; fut basis +6.1; spot below max pain 1260; PE wall 1200; CE wall 1300 |
| HINDALCO | sideways | 0.78 | 1.90 | 980 | PCR 0.78 call-heavy; fut basis +1.9; spot above max pain 980; PE wall 960; CE wall 1000 |
| BAJFINANCE | bullish | 0.91 | 2.10 | 1,050 | PCR 0.91 balanced; fut basis +2.1; spot above max pain 1050; PE wall 1000; CE wall 1100 |
| MCX | sideways | 0.89 | 15.00 | 2,800 | PCR 0.89 balanced; fut basis +15; spot below max pain 2800; PE wall 2800; CE wall 2800 |
| ICICIBANK | sideways | 0.67 | 2.80 | 1,450 | PCR 0.67 call-heavy; fut basis +2.8; spot below max pain 1450; PE wall 1400; CE wall 1450 |
| LT | sideways | 0.80 | 22.80 | 4,000 | PCR 0.80 call-heavy; fut basis +22.8; spot below max pain 4000; PE wall 3800; CE wall 4000 |
| BHARTIARTL | sideways | 0.76 | 2.50 | 1,960 | PCR 0.76 call-heavy; fut basis +2.5; spot below max pain 1960; PE wall 1900; CE wall 2000 |
| DIXON | bearish | 0.79 | -170.00 | 14,500 | PCR 0.79 call-heavy; fut basis -170; spot below max pain 14500; PE wall 13000; CE wall 14500 |

## Commentary

Current read from the tracker:

- KAYNES: long active; Locked setup: Above 3,817.41; T1 3,845.88, stop 3,805.92; F&O sideways (PCR 0.59, basis 21.40, max pain 3,650.00); Decision TRADE NOW (Option Buy OK, score 70)
- SCHNEIDER: long active; Locked setup: Above 1,362.96; T1 1,371.81, stop 1,358.69; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision TRADE NOW (Option Buy OK, score 82)
- VMM: near trigger / watch; Locked setup: Above 111.11; T1 111.69, stop 110.84; F&O sideways (PCR 0.54, basis 0.58, max pain 115.00); Decision WAIT FOR RETEST (Prefer Futures, score 47)
- PAYTM: near trigger / watch; Locked setup: Above 1,423.50; T1 1,435.79, stop 1,414.28; F&O sideways (PCR 0.60, basis 8.50, max pain 1,340.00); Decision WAIT FOR RETEST (Option Buy OK, score 45)
- TCS: watch; Breakout above 2,430.60; support n/a; T1 n/a; F&O sideways (PCR 0.97, basis 7.70, max pain 2,440.00); Decision AVOID (No Trade, score 3)
- SBIN: watch; Breakout above 1,049.00; support n/a; T1 n/a; F&O bullish (PCR 0.98, basis 5.60, max pain 1,040.00); Decision AVOID (No Trade, score 3)
- ADANIENT: watch; Breakout above 3,067.10; support n/a; T1 n/a; F&O sideways (PCR 0.83, basis 9.90, max pain 3,100.00); Decision AVOID (No Trade, score 3)
- AXISBANK: watch; Breakout above 1,250.70; support n/a; T1 n/a; F&O sideways (PCR 0.70, basis 6.10, max pain 1,260.00); Decision AVOID (No Trade, score 3)
- HINDALCO: watch; Breakout above 990.75; support n/a; T1 n/a; F&O sideways (PCR 0.78, basis 1.90, max pain 980.00); Decision AVOID (No Trade, score 3)
- BAJFINANCE: watch; Breakout above 1,159.80; support n/a; T1 n/a; F&O bullish (PCR 0.91, basis 2.10, max pain 1,050.00); Decision AVOID (No Trade, score 3)

Cycle changes:
- New added: ADANIENT, AXISBANK, BAJFINANCE, BHARTIARTL, DIXON, HINDALCO, ICICIBANK, KAYNES
- Removed: none
- Forming: TCS, SBIN, ADANIENT, AXISBANK, HINDALCO, BAJFINANCE, MCX, ICICIBANK
- Confirmed: VMM, PAYTM
- Active: KAYNES, SCHNEIDER

Best actionable names:
1. SCHNEIDER long active, tradeable only while trigger holds.
2. KAYNES long active, tradeable only while trigger holds.
3. VMM near trigger / watch, wait for retest / confirmation.
4. PAYTM near trigger / watch, wait for retest / confirmation.
5. TCS watch, avoid; decision gate not satisfied.

Watch next:
- Market context: NIFTY 24,599 +0.88%, BANKNIFTY 57,793 +0.92%, VIX 11.96 +1.76%, breadth 633A/116D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok

## Email

- Status: dry-run preview written to /Users/pgorai/Documents/Projects/Unified-NSE-Analysis/logs/_intraday_alert_preview_20260803_115521.html
- Subject: Agent Adda Intraday F&O Alert: KAYNES LONG ACTIVE, SCHNEIDER LONG ACTIVE, VMM LONG WATCH
