# Agent Adda Intraday Alerts - Latest Cycle

- Time: 2026-08-03 13:53:44
- Cycle: 1
- Market: NIFTY 24,591 +0.85%, BANKNIFTY 57,716 +0.79%, VIX 11.93 +1.48%, breadth 603A/144D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok | strategy_time_gate ok: supertrend_breakout,near_breakout_volume,vcp,volume,darvas | fno_context ok | edge_memory ok: 5 | full universe rescan ok: scanned 209, tracking 15 | options_execution ok
- Fresh alerts: 0
- Total candidates: 0

## Trading Stance

- Stance: WAIT
- Headline: Wait; do not force trades right now.
- Action: Stand aside until fresh alerts, volume confirmation, and timing improve.
- Reasons: Fresh alerts: 0; Alert candidates: 0; mid_session / NO_TRADE_WINDOW; volume confirmation missing


## Sharp Movers

| Symbol | Move | Chg | LTP | Level State | Ref Level | Read | Decision |
|---|---|---:|---:|---|---:|---|---|
| TCS | Sharp Rise | +3.0% | 2,436 | breaking resistance | 2,436 | WATCH watch | AVOID / No Trade |

## Cycle Changes

- New added: ADANIENT, AXISBANK, BAJFINANCE, BHARTIARTL, DIXON, HINDALCO, ICICIBANK, KOTAKBANK, LT, MCX, NATIONALUM, SBIN, SCHNEIDER, TATASTEEL, TCS
- Removed: none
- Forming: TCS, MCX, AXISBANK, ADANIENT, ICICIBANK, LT, HINDALCO, SBIN, BAJFINANCE, DIXON, BHARTIARTL, TATASTEEL, KOTAKBANK, SCHNEIDER
- Confirmed: none
- Active: NATIONALUM

## Fresh Alerts

No fresh alerts this cycle.

## Tracker

| Symbol | Read | Decision | Options | Score | F&O | LTP | Chg | Entry | Stop | T1/RR |
|---|---|---|---|---:|---|---:|---:|---:|---:|---:|
| NATIONALUM | LONG long active | WATCH ONLY | Option Buy OK | 57 | unknown PCR n/a basis n/a MP n/a | 365.57 | n/a | 365.57 | 363.94 | 367.75/1.3R |
| TCS | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 2,436 | +3.0% | 2,436 | n/a | n/a |
| MCX | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 2,643 | -1.8% | 2,643 | n/a | n/a |
| AXISBANK | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 1,251 | +1.8% | 1,251 | n/a | n/a |
| ADANIENT | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 3,062 | +1.7% | 3,062 | n/a | n/a |
| ICICIBANK | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 1,447 | +1.7% | 1,447 | n/a | n/a |
| LT | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 4,004 | +1.7% | 4,004 | n/a | n/a |
| HINDALCO | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 989.20 | +1.5% | 989.20 | n/a | n/a |
| SBIN | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 1,042 | +1.4% | 1,042 | n/a | n/a |
| BAJFINANCE | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 1,156 | +1.3% | 1,156 | n/a | n/a |
| DIXON | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 13,902 | -1.1% | 13,902 | n/a | n/a |
| BHARTIARTL | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 1,956 | -0.8% | 1,956 | n/a | n/a |
| TATASTEEL | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 191.00 | +0.7% | 191.00 | n/a | n/a |
| KOTAKBANK | WATCH watch | AVOID | No Trade | 3 | unknown PCR n/a basis n/a MP n/a | 392.65 | +0.6% | 392.65 | n/a | n/a |
| SCHNEIDER | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | 1,362 | +0.5% | 1,362 | n/a | n/a |

## Why No Trade - Top 5 Blocked

| Symbol | Side | State | Decision | LTP | Trigger | Stop | T1 | RR | Why blocked |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| NATIONALUM | LONG | long active | WATCH ONLY / Option Buy OK / score 57 | 365.57 | 365.57 | 363.94 | 367.75 | 1.3 | gate WATCH ONLY; R:R 1.3 < min 2.0; mid_session / NO_TRADE_WINDOW; trigger active; RR 1.3 acceptable; scanner-confirmed |
| TCS | WATCH | watch | AVOID / No Trade / score 3 | 2,436 | 2,436 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; mid_session / NO_TRADE_WINDOW; MTF level-derived; F&O unavailable |
| MCX | WATCH | watch | AVOID / No Trade / score 3 | 2,643 | 2,643 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; mid_session / NO_TRADE_WINDOW; MTF level-derived; F&O unavailable |
| AXISBANK | WATCH | watch | AVOID / No Trade / score 3 | 1,251 | 1,251 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; mid_session / NO_TRADE_WINDOW; MTF level-derived; F&O unavailable |
| ADANIENT | WATCH | watch | AVOID / No Trade / score 3 | 3,062 | 3,062 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; mid_session / NO_TRADE_WINDOW; MTF level-derived; F&O unavailable |

## Trade Decisions

| Symbol | Action | Options | Score | Market Regime | Reasons |
|---|---|---|---:|---|---|
| NATIONALUM | WATCH ONLY | Option Buy OK | 57 | neutral | trigger active; RR 1.3 acceptable; scanner-confirmed; F&O unavailable; volume-aware setup |
| TCS | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| MCX | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| AXISBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| ADANIENT | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| ICICIBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| LT | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| HINDALCO | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| SBIN | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| BAJFINANCE | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| DIXON | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| BHARTIARTL | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| TATASTEEL | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| KOTAKBANK | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O unavailable; volume not confirmed |
| SCHNEIDER | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |

## Trade Timing

| Symbol | Window | Timing Score | Time Bucket | Reasons |
|---|---|---:|---|---|
| NATIONALUM | NO_TRADE_WINDOW | 21 | mid_session | no persisted edge; mid-session lower urgency; trigger active; R:R acceptable |
| TCS | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| MCX | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| AXISBANK | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| ADANIENT | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| ICICIBANK | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| LT | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| HINDALCO | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| SBIN | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| BAJFINANCE | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| DIXON | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| BHARTIARTL | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| TATASTEEL | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| KOTAKBANK | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak |
| SCHNEIDER | NO_TRADE_WINDOW | 0 | mid_session | no persisted edge; mid-session lower urgency; watch-only structure; R:R weak; F&O sideways |

## Options Execution

| Symbol | Verdict | Strategy | Option | Strike | Premium | Breakeven | Exp/DTE | IV | Delta/Theta | Expected Move | OI Wall | Notes |
|---|---|---|---|---:|---:|---:|---|---:|---|---:|---|---|
| NATIONALUM | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | fno_context |
| TCS | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| MCX | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| AXISBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIENT | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ICICIBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| LT | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| HINDALCO | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| SBIN | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| BAJFINANCE | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| DIXON | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| BHARTIARTL | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| TATASTEEL | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| KOTAKBANK | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| SCHNEIDER | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |


## Edge Memory

| Symbol | Status | Role | Setup | Confidence | Persistence |
|---|---|---|---|---:|---:|
| n/a | n/a | n/a | n/a | n/a | n/a |

## F&O Context

| Symbol | Bias | PCR | Basis | Max Pain | Note |
|---|---|---:|---:|---:|---|
| NATIONALUM | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| TCS | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| MCX | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| AXISBANK | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| ADANIENT | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| ICICIBANK | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| LT | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| HINDALCO | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| SBIN | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| BAJFINANCE | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| DIXON | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| BHARTIARTL | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| TATASTEEL | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| KOTAKBANK | unknown | n/a | n/a | n/a | F&O provider timed out after 8s |
| SCHNEIDER | sideways | n/a | n/a | n/a |  |

## Commentary

Current read from the tracker:

- NATIONALUM: long active; Locked setup: Above 365.57; T1 367.75, stop 363.94; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision WATCH ONLY (Option Buy OK, score 57)
- TCS: watch; Breakout above 2,435.50; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- MCX: watch; Breakout above 2,642.90; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- AXISBANK: watch; Breakout above 1,251.20; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- ADANIENT: watch; Breakout above 3,061.50; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- ICICIBANK: watch; Breakout above 1,447.10; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- LT: watch; Breakout above 4,004.40; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- HINDALCO: watch; Breakout above 989.20; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- SBIN: watch; Breakout above 1,042.00; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- BAJFINANCE: watch; Breakout above 1,156.00; support n/a; T1 n/a; F&O unknown (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)

Cycle changes:
- New added: ADANIENT, AXISBANK, BAJFINANCE, BHARTIARTL, DIXON, HINDALCO, ICICIBANK, KOTAKBANK
- Removed: none
- Forming: TCS, MCX, AXISBANK, ADANIENT, ICICIBANK, LT, HINDALCO, SBIN
- Confirmed: none
- Active: NATIONALUM

Best actionable names:
1. NATIONALUM long active, valid but needs follow-through.
2. TCS watch, avoid; decision gate not satisfied.
3. MCX watch, avoid; decision gate not satisfied.
4. AXISBANK watch, avoid; decision gate not satisfied.
5. ADANIENT watch, avoid; decision gate not satisfied.

Watch next:
- Market context: NIFTY 24,591 +0.85%, BANKNIFTY 57,716 +0.79%, VIX 11.93 +1.48%, breadth 603A/144D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok
