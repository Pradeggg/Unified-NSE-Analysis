# Agent Adda Intraday Alerts - Latest Cycle

- Time: 2026-08-03 10:10:11
- Cycle: 1
- Market: NIFTY 24,562 +0.73%, BANKNIFTY 57,788 +0.91%, VIX 11.84 +0.72%, breadth 649A/99D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok | fno_context ok | edge_memory ok: 5 | full universe rescan ok: scanned 209, tracking 15 | options_execution ok
- Fresh alerts: 3
- Total candidates: 3

## Trading Stance

- Stance: TRADE
- Headline: Trade only qualified setup(s); avoid chasing.
- Action: Use only the named trade-window candidates and respect invalidation.
- Reasons: Fresh alerts: 3; Alert candidates: 3; opening_drive / NO_TRADE_WINDOW; volume confirmation missing


## Sharp Movers

| Symbol | Move | Chg | LTP | Level State | Ref Level | Read | Decision |
|---|---|---:|---:|---|---:|---|---|
| n/a | none | n/a | n/a | n/a | n/a | No tracked name has crossed the sharp-move threshold. | n/a |

## Cycle Changes

- New added: ADANIENT, AXISBANK, BAJFINANCE, BLUESTARCO, GODREJCP, HDFCBANK, HINDALCO, ICICIBANK, IREDA, LT, MARICO, MCX, SBIN, TCS, ULTRACEMCO
- Removed: none
- Forming: TCS, SBIN, ICICIBANK, BAJFINANCE, ADANIENT, LT, AXISBANK, MCX, HDFCBANK, HINDALCO
- Confirmed: none
- Active: BLUESTARCO, IREDA, MARICO, ULTRACEMCO, GODREJCP

## Fresh Alerts

| Symbol | Side | Status | Decision | Options | Entry | Stop | T1 | RR |
|---|---:|---|---|---|---:|---:|---:|---:|
| IREDA | LONG | long active | TRADE NOW | Option Buy OK | 122.97 | 122.62 | 123.86 | 2.5 |
| BLUESTARCO | LONG | long active | TRADE NOW | Option Buy OK | 1,707 | 1,702 | 1,718 | 2.4 |
| MARICO | LONG | long active | WATCH ONLY | Prefer Futures | 877.28 | 875.00 | 882.29 | 2.2 |

## Tracker

| Symbol | Read | Decision | Options | Score | F&O | LTP | Chg | Entry | Stop | T1/RR |
|---|---|---|---|---:|---|---:|---:|---:|---:|---:|
| BLUESTARCO | LONG long active | TRADE NOW | Option Buy OK | 98 | bullish PCR 1.12 basis 19.10 MP 1,640 | 1,707 | n/a | 1,707 | 1,702 | 1,718/2.4R |
| IREDA | LONG long active | TRADE NOW | Option Buy OK | 74 | sideways PCR 1.07 basis -2.88 MP 120 | 122.97 | n/a | 122.97 | 122.62 | 123.86/2.5R |
| MARICO | LONG long active | WATCH ONLY | Prefer Futures | 62 | sideways PCR 0.67 basis 2.70 MP 900 | 877.28 | n/a | 877.28 | 875.00 | 882.29/2.2R |
| ULTRACEMCO | LONG long active | WATCH ONLY | Prefer Futures | 45 | sideways PCR 0.54 basis 19.00 MP 11,960 | 11,928 | n/a | 11,928 | 11,826 | 12,123/1.9R |
| GODREJCP | LONG long active | WATCH ONLY | Prefer Futures | 45 | sideways PCR 0.65 basis 0.10 MP 1,090 | 1,089 | n/a | 1,089 | 1,070 | 1,125/1.9R |
| TCS | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.97 basis 7.70 MP 2,440 | 2,410 | +1.9% | 2,410 | n/a | n/a |
| SBIN | WATCH watch | AVOID | No Trade | 3 | bullish PCR 0.98 basis 4.20 MP 1,040 | 1,046 | +1.8% | 1,046 | n/a | n/a |
| ICICIBANK | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.67 basis 2.80 MP 1,450 | 1,446 | +1.6% | 1,446 | n/a | n/a |
| BAJFINANCE | WATCH watch | AVOID | No Trade | 3 | bullish PCR 0.91 basis 1.10 MP 1,050 | 1,159 | +1.5% | 1,159 | n/a | n/a |
| ADANIENT | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.83 basis 9.90 MP 3,100 | 3,054 | +1.5% | 3,054 | n/a | n/a |
| LT | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.80 basis 22.80 MP 4,000 | 3,979 | +1.0% | 3,979 | n/a | n/a |
| AXISBANK | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.70 basis 6.10 MP 1,260 | 1,242 | +1.0% | 1,242 | n/a | n/a |
| MCX | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.89 basis 15.00 MP 2,800 | 2,666 | -1.0% | 2,666 | n/a | n/a |
| HDFCBANK | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.55 basis 2.10 MP 800 | 754.65 | +0.9% | 754.65 | n/a | n/a |
| HINDALCO | WATCH watch | AVOID | No Trade | 3 | sideways PCR 0.78 basis 1.90 MP 980 | 982.85 | +0.9% | 982.85 | n/a | n/a |

## Why No Trade - Top 5 Blocked

| Symbol | Side | State | Decision | LTP | Trigger | Stop | T1 | RR | Why blocked |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| ULTRACEMCO | LONG | long active | WATCH ONLY / Prefer Futures / score 45 | 11,928 | 11,928 | 11,826 | 12,123 | 1.9 | gate WATCH ONLY; R:R 1.9 < min 2.0; opening_drive / WATCH_WINDOW; trigger active; RR 1.9 acceptable; scanner-confirmed |
| GODREJCP | LONG | long active | WATCH ONLY / Prefer Futures / score 45 | 1,089 | 1,089 | 1,070 | 1,125 | 1.9 | gate WATCH ONLY; R:R 1.9 < min 2.0; opening_drive / WATCH_WINDOW; trigger active; RR 1.9 acceptable; scanner-confirmed |
| TCS | WATCH | watch | AVOID / No Trade / score 3 | 2,410 | 2,410 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; opening_drive / NO_TRADE_WINDOW; MTF level-derived; F&O sideways |
| SBIN | WATCH | watch | AVOID / No Trade / score 3 | 1,046 | 1,046 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; opening_drive / NO_TRADE_WINDOW; MTF level-derived; F&O bullish |
| ICICIBANK | WATCH | watch | AVOID / No Trade / score 3 | 1,446 | 1,446 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; opening_drive / NO_TRADE_WINDOW; MTF level-derived; F&O sideways |

## Trade Decisions

| Symbol | Action | Options | Score | Market Regime | Reasons |
|---|---|---|---:|---|---|
| BLUESTARCO | TRADE NOW | Option Buy OK | 98 | neutral | trigger active; RR 2.4 strong; scanner-confirmed; F&O bullish; volume-aware setup |
| IREDA | TRADE NOW | Option Buy OK | 74 | neutral | trigger active; RR 2.5 strong; scanner-confirmed; F&O sideways; volume-aware setup |
| MARICO | WATCH ONLY | Prefer Futures | 62 | neutral | trigger active; RR 2.2 strong; scanner-confirmed; F&O sideways; volume-aware setup |
| ULTRACEMCO | WATCH ONLY | Prefer Futures | 45 | neutral | trigger active; RR 1.9 acceptable; scanner-confirmed; F&O sideways; scanner signal |
| GODREJCP | WATCH ONLY | Prefer Futures | 45 | neutral | trigger active; RR 1.9 acceptable; scanner-confirmed; F&O sideways; scanner signal |
| TCS | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| SBIN | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O bullish; volume not confirmed |
| ICICIBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| BAJFINANCE | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O bullish; volume not confirmed |
| ADANIENT | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| LT | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| AXISBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| MCX | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| HDFCBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| HINDALCO | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |

## Trade Timing

| Symbol | Window | Timing Score | Time Bucket | Reasons |
|---|---|---:|---|---|
| BLUESTARCO | WATCH_WINDOW | 55 | opening_drive | no persisted edge; opening-drive timing; trigger active; R:R >= 2; F&O aligned bullish |
| IREDA | WATCH_WINDOW | 45 | opening_drive | no persisted edge; opening-drive timing; trigger active; R:R >= 2; F&O sideways |
| MARICO | WATCH_WINDOW | 45 | opening_drive | no persisted edge; opening-drive timing; trigger active; R:R >= 2; F&O sideways |
| ULTRACEMCO | WATCH_WINDOW | 40 | opening_drive | no persisted edge; opening-drive timing; trigger active; R:R acceptable; F&O sideways |
| GODREJCP | WATCH_WINDOW | 40 | opening_drive | no persisted edge; opening-drive timing; trigger active; R:R acceptable; F&O sideways |
| TCS | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| SBIN | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak |
| ICICIBANK | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| BAJFINANCE | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak |
| ADANIENT | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| LT | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| AXISBANK | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| MCX | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| HDFCBANK | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| HINDALCO | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |

## Options Execution

| Symbol | Verdict | Strategy | Option | Strike | Premium | Breakeven | Exp/DTE | IV | Delta/Theta | Expected Move | OI Wall | Notes |
|---|---|---|---|---:|---:|---:|---|---:|---|---:|---|---|
| BLUESTARCO | USE SPREAD | Bull Call Debit Spread (USE DEBIT SPREAD) | CE ATM | 1,700 | 65.90 | 1,766 | 2026-08-25 / 22D | 37.1 | 0.51 / -1.54 | 153.89 | CE wall 1700, 1800 | ❌ IV 37.1% is high — options are expensive to buy; ⚠️  IV rank 49% — moderate; not the cheapest |
| IREDA | USE SPREAD | Bull Call Debit Spread (USE DEBIT SPREAD) | CE ATM | 100.00 | 17.00 | 117.00 | 2026-08-25 / 22D | 38.9 | 0.98 / -0.03 | 11.43 | CE wall 120, 130 | ❌ IV 38.9% is high — options are expensive to buy; ⚠️  IV rank 53% — moderate; not the cheapest |
| MARICO | USE SPREAD | Bull Call Debit Spread (USE DEBIT SPREAD) | CE ATM | 900.00 | 19.50 | 919.50 | 2026-08-25 / 22D | 28.4 | 0.44 / -0.62 | 61.69 | CE wall 900, 960 | ❌ IV 28.4% is high — options are expensive to buy; ✅ IV rank 30% — historically cheap |
| ULTRACEMCO | USE SPREAD | Bull Call Debit Spread (USE DEBIT SPREAD) | CE ATM | 11,860 | 244.65 | 12,105 | 2026-08-25 / 22D | 20.4 | 0.53 / -6.43 | 592.47 | CE wall 11960, 12260 | ⚠️  IV 20.4% is moderate — prefer spreads to reduce cost; ✅ IV rank 12% — historically cheap |
| GODREJCP | USE SPREAD | Bull Call Debit Spread (USE DEBIT SPREAD) | CE ATM | 1,050 | 45.90 | 1,096 | 2026-08-25 / 22D | 29.3 | 0.65 / -0.77 | 77.07 | CE wall 1100, 1080 | ❌ IV 29.3% is high — options are expensive to buy; ⚠️  IV rank 32% — moderate; not the cheapest |
| TCS | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| SBIN | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ICICIBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| BAJFINANCE | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIENT | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| LT | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| AXISBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| MCX | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| HDFCBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| HINDALCO | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |


## Edge Memory

| Symbol | Status | Role | Setup | Confidence | Persistence |
|---|---|---|---|---:|---:|
| n/a | n/a | n/a | n/a | n/a | n/a |

## F&O Context

| Symbol | Bias | PCR | Basis | Max Pain | Note |
|---|---|---:|---:|---:|---|
| BLUESTARCO | bullish | 1.12 | 19.10 | 1,640 | PCR 1.12 put-heavy; fut basis +19.1; spot above max pain 1640; PE wall 1500; CE wall 1700 |
| IREDA | sideways | 1.07 | -2.88 | 120 | PCR 1.07 balanced; fut basis -2.88; spot above max pain 120; PE wall 120; CE wall 120 |
| MARICO | sideways | 0.67 | 2.70 | 900 | PCR 0.67 call-heavy; fut basis +2.7; spot below max pain 900; PE wall 800; CE wall 900 |
| ULTRACEMCO | sideways | 0.54 | 19.00 | 11,960 | PCR 0.54 call-heavy; fut basis +19; spot below max pain 11960; PE wall 10760; CE wall 11960 |
| GODREJCP | sideways | 0.65 | 0.10 | 1,090 | PCR 0.65 call-heavy; fut basis +0.1; spot below max pain 1090; PE wall 1060; CE wall 1100 |
| TCS | sideways | 0.97 | 7.70 | 2,440 | PCR 0.97 balanced; fut basis +7.7; spot below max pain 2440; PE wall 2800; CE wall 2500 |
| SBIN | bullish | 0.98 | 4.20 | 1,040 | PCR 0.98 balanced; fut basis +4.2; spot above max pain 1040; PE wall 1000; CE wall 1050 |
| ICICIBANK | sideways | 0.67 | 2.80 | 1,450 | PCR 0.67 call-heavy; fut basis +2.8; spot below max pain 1450; PE wall 1400; CE wall 1450 |
| BAJFINANCE | bullish | 0.91 | 1.10 | 1,050 | PCR 0.91 balanced; fut basis +1.1; spot above max pain 1050; PE wall 1000; CE wall 1100 |
| ADANIENT | sideways | 0.83 | 9.90 | 3,100 | PCR 0.83 balanced; fut basis +9.9; spot below max pain 3100; PE wall 3000; CE wall 3200 |
| LT | sideways | 0.80 | 22.80 | 4,000 | PCR 0.80 call-heavy; fut basis +22.8; spot below max pain 4000; PE wall 3800; CE wall 4000 |
| AXISBANK | sideways | 0.70 | 6.10 | 1,260 | PCR 0.70 call-heavy; fut basis +6.1; spot below max pain 1260; PE wall 1200; CE wall 1300 |
| MCX | sideways | 0.89 | 15.00 | 2,800 | PCR 0.89 balanced; fut basis +15; spot below max pain 2800; PE wall 2800; CE wall 2800 |
| HDFCBANK | sideways | 0.55 | 2.10 | 800 | PCR 0.55 call-heavy; fut basis +2.1; spot below max pain 800; PE wall 750; CE wall 800 |
| HINDALCO | sideways | 0.78 | 1.90 | 980 | PCR 0.78 call-heavy; fut basis +1.9; spot above max pain 980; PE wall 960; CE wall 1000 |

## Commentary

Current read from the tracker:

- BLUESTARCO: long active; Locked setup: Above 1,706.60; T1 1,718.40, stop 1,701.72; F&O bullish (PCR 1.12, basis 19.10, max pain 1,640.00); Decision TRADE NOW (Option Buy OK, score 98)
- IREDA: long active; Locked setup: Above 122.97; T1 123.86, stop 122.62; F&O sideways (PCR 1.07, basis -2.88, max pain 120.00); Decision TRADE NOW (Option Buy OK, score 74)
- MARICO: long active; Locked setup: Above 877.28; T1 882.29, stop 875.00; F&O sideways (PCR 0.67, basis 2.70, max pain 900.00); Decision WATCH ONLY (Prefer Futures, score 62)
- ULTRACEMCO: long active; Locked setup: Above 11,928.00; T1 12,123.00, stop 11,826.00; F&O sideways (PCR 0.54, basis 19.00, max pain 11,960.00); Decision WATCH ONLY (Prefer Futures, score 45)
- GODREJCP: long active; Locked setup: Above 1,089.30; T1 1,124.70, stop 1,070.40; F&O sideways (PCR 0.65, basis 0.10, max pain 1,090.00); Decision WATCH ONLY (Prefer Futures, score 45)
- TCS: watch; Breakout above 2,410.20; support n/a; T1 n/a; F&O sideways (PCR 0.97, basis 7.70, max pain 2,440.00); Decision AVOID (No Trade, score 3)
- SBIN: watch; Breakout above 1,045.60; support n/a; T1 n/a; F&O bullish (PCR 0.98, basis 4.20, max pain 1,040.00); Decision AVOID (No Trade, score 3)
- ICICIBANK: watch; Breakout above 1,446.00; support n/a; T1 n/a; F&O sideways (PCR 0.67, basis 2.80, max pain 1,450.00); Decision AVOID (No Trade, score 3)
- BAJFINANCE: watch; Breakout above 1,158.70; support n/a; T1 n/a; F&O bullish (PCR 0.91, basis 1.10, max pain 1,050.00); Decision AVOID (No Trade, score 3)
- ADANIENT: watch; Breakout above 3,053.50; support n/a; T1 n/a; F&O sideways (PCR 0.83, basis 9.90, max pain 3,100.00); Decision AVOID (No Trade, score 3)

Cycle changes:
- New added: ADANIENT, AXISBANK, BAJFINANCE, BLUESTARCO, GODREJCP, HDFCBANK, HINDALCO, ICICIBANK
- Removed: none
- Forming: TCS, SBIN, ICICIBANK, BAJFINANCE, ADANIENT, LT, AXISBANK, MCX
- Confirmed: none
- Active: BLUESTARCO, IREDA, MARICO, ULTRACEMCO, GODREJCP

Best actionable names:
1. BLUESTARCO long active, tradeable only while trigger holds.
2. IREDA long active, tradeable only while trigger holds.
3. MARICO long active, valid but needs follow-through.
4. ULTRACEMCO long active, valid but needs follow-through.
5. GODREJCP long active, valid but needs follow-through.

Watch next:
- Market context: NIFTY 24,562 +0.73%, BANKNIFTY 57,788 +0.91%, VIX 11.84 +0.72%, breadth 649A/99D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok

## Email

- Status: dry-run preview written to /Users/pgorai/Documents/Projects/Unified-NSE-Analysis/logs/_intraday_alert_preview_20260803_101012.html
- Subject: Agent Adda Intraday F&O Alert: IREDA LONG ACTIVE, BLUESTARCO LONG ACTIVE, MARICO LONG ACTIVE
