# Agent Adda Intraday Alerts - Latest Cycle

- Time: 2026-08-28 09:59:34
- Cycle: 15
- Market: NIFTY 24,158 +0.28%, BANKNIFTY 57,461 -0.08%, VIX 10.89 -1.62%, breadth 390A/357D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok | fno_context ok | edge_memory ok: 0 | options_execution ok
- Fresh alerts: 1
- Total candidates: 1

## Trading Stance

- Stance: WAIT
- Headline: Wait for retest/confirmation; no trade-now signal.
- Action: Monitor qualified watches, but wait for trigger hold and cleaner timing.
- Reasons: Fresh alerts: 1; Alert candidates: 1; opening_drive / NO_TRADE_WINDOW; volume confirmation missing


## Sharp Movers

| Symbol | Move | Chg | LTP | Level State | Ref Level | Read | Decision |
|---|---|---:|---:|---|---:|---|---|
| n/a | none | n/a | n/a | n/a | n/a | No tracked name has crossed the sharp-move threshold. | n/a |

## Cycle Changes

- New added: none
- Removed: none
- Forming: LODHA, OIL, 360ONE, ABB, ABCAPITAL, ADANIENSOL, ADANIENT, ADANIGREEN, ADANIPORTS, ADANIPOWER, ALKEM, AMBER, AMBUJACEM
- Confirmed: SUPREMEIND
- Active: BAJAJ-AUTO
- Status changes: LODHA long active -> watch; OIL near trigger / watch -> watch

## Fresh Alerts

| Symbol | Side | Status | Decision | Options | Entry | Stop | T1 | RR |
|---|---:|---|---|---|---:|---:|---:|---:|
| BAJAJ-AUTO | LONG | long active | WATCH ONLY | Option Buy OK | 11,916 | 11,880 | 11,993 | 2.1 |

## Tracker

| Symbol | Read | Decision | Options | Score | F&O | LTP | Chg | Entry | Stop | T1/RR |
|---|---|---|---|---:|---|---:|---:|---:|---:|---:|
| SUPREMEIND | LONG near trigger / watch | WATCH ONLY | Option Buy OK | 57 | sideways PCR n/a basis n/a MP n/a | 3,705 | n/a | 3,706 | 3,679 | 3,743/1.3R |
| BAJAJ-AUTO | LONG long active | WATCH ONLY | Option Buy OK | 57 | sideways PCR n/a basis n/a MP n/a | 11,916 | n/a | 11,916 | 11,880 | 11,993/2.1R |
| LODHA | LONG watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | 1,270 | 1,262 | 1,282/1.6R |
| OIL | LONG watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | 476.28 | 474.19 | 480.29/1.9R |
| 360ONE | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| ABB | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| ABCAPITAL | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| ADANIENSOL | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| ADANIENT | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| ADANIGREEN | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | 1,308 | n/a | 1,308 | n/a | n/a |
| ADANIPORTS | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| ADANIPOWER | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| ALKEM | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| AMBER | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | n/a | n/a | n/a | n/a | n/a |
| AMBUJACEM | WATCH watch | AVOID | No Trade | 3 | sideways PCR n/a basis n/a MP n/a | 412.20 | +0.3% | 412.20 | n/a | n/a |

## Why No Trade - Top 5 Blocked

| Symbol | Side | State | Decision | LTP | Trigger | Stop | T1 | RR | Why blocked |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| SUPREMEIND | LONG | near trigger / watch | WATCH ONLY / Option Buy OK / score 57 | 3,705 | 3,706 | 3,679 | 3,743 | 1.3 | gate WATCH ONLY; needs break/hold confirmation; R:R 1.3 < min 2.0; opening_drive / WATCH_WINDOW; trigger active; RR 1.3 acceptable |
| OIL | LONG | watch | AVOID / No Trade / score 3 | n/a | 476.28 | 474.19 | 480.29 | 1.9 | gate AVOID; R:R 1.9 < min 2.0; opening_drive / NO_TRADE_WINDOW; MTF level-derived; F&O sideways; volume not confirmed |
| LODHA | LONG | watch | AVOID / No Trade / score 3 | n/a | 1,270 | 1,262 | 1,282 | 1.6 | gate AVOID; R:R 1.6 < min 2.0; opening_drive / NO_TRADE_WINDOW; MTF level-derived; F&O sideways; volume not confirmed |
| AMBUJACEM | WATCH | watch | AVOID / No Trade / score 3 | 412.20 | 412.20 | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; opening_drive / NO_TRADE_WINDOW; MTF level-derived; F&O sideways |
| 360ONE | WATCH | watch | AVOID / No Trade / score 3 | n/a | n/a | n/a | n/a | n/a | gate AVOID; watch-only / no directional trigger; no R:R / target structure; opening_drive / NO_TRADE_WINDOW; MTF level-derived; F&O sideways |

## Trade Decisions

| Symbol | Action | Options | Score | Market Regime | Reasons |
|---|---|---|---:|---|---|
| SUPREMEIND | WATCH ONLY | Option Buy OK | 57 | neutral | trigger active; RR 1.3 acceptable; scanner-confirmed; F&O sideways; volume-aware setup |
| BAJAJ-AUTO | WATCH ONLY | Option Buy OK | 57 | neutral | trigger active; RR 2.0 acceptable; scanner-confirmed; F&O sideways; volume-aware setup |
| LODHA | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| OIL | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| 360ONE | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ABB | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ABCAPITAL | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ADANIENSOL | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ADANIENT | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ADANIGREEN | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ADANIPORTS | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ADANIPOWER | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| ALKEM | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| AMBER | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |
| AMBUJACEM | AVOID | No Trade | 3 | neutral | MTF level-derived; F&O sideways; volume not confirmed |

## Trade Timing

| Symbol | Window | Timing Score | Time Bucket | Reasons |
|---|---|---:|---|---|
| SUPREMEIND | WATCH_WINDOW | 40 | opening_drive | no persisted edge; opening-drive timing; trigger active; R:R acceptable; F&O sideways |
| BAJAJ-AUTO | WATCH_WINDOW | 40 | opening_drive | no persisted edge; opening-drive timing; trigger active; R:R acceptable; F&O sideways |
| LODHA | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| OIL | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| 360ONE | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ABB | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ABCAPITAL | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ADANIENSOL | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ADANIENT | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ADANIGREEN | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ADANIPORTS | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ADANIPOWER | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| ALKEM | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| AMBER | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |
| AMBUJACEM | NO_TRADE_WINDOW | 0 | opening_drive | no persisted edge; opening-drive timing; watch-only structure; R:R weak; F&O sideways |

## Options Execution

| Symbol | Verdict | Strategy | Option | Strike | Premium | Breakeven | Exp/DTE | IV | Delta/Theta | Expected Move | OI Wall | Notes |
|---|---|---|---|---:|---:|---:|---|---:|---|---:|---|---|
| SUPREMEIND | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | option_chain; futures |
| BAJAJ-AUTO | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | option_chain; futures |
| LODHA | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| OIL | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| 360ONE | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ABB | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ABCAPITAL | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIENSOL | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIENT | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIGREEN | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIPORTS | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ADANIPOWER | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| ALKEM | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| AMBER | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |
| AMBUJACEM | NO OPTIONS TRADE | No options structure (NO OPTIONS STRATEGY) | CE | n/a | n/a | n/a | n/a | n/a | n/a / n/a | n/a | n/a | row is not LONG or SHORT |


## Edge Memory

| Symbol | Status | Role | Setup | Confidence | Persistence |
|---|---|---|---|---:|---:|
| n/a | n/a | n/a | n/a | n/a | n/a |

## F&O Context

| Symbol | Bias | PCR | Basis | Max Pain | Note |
|---|---|---:|---:|---:|---|
| SUPREMEIND | sideways | n/a | n/a | n/a |  |
| BAJAJ-AUTO | sideways | n/a | n/a | n/a |  |
| LODHA | sideways | n/a | n/a | n/a |  |
| OIL | sideways | n/a | n/a | n/a |  |
| 360ONE | sideways | n/a | n/a | n/a |  |
| ABB | sideways | n/a | n/a | n/a |  |
| ABCAPITAL | sideways | n/a | n/a | n/a |  |
| ADANIENSOL | sideways | n/a | n/a | n/a |  |
| ADANIENT | sideways | n/a | n/a | n/a |  |
| ADANIGREEN | sideways | n/a | n/a | n/a |  |
| ADANIPORTS | sideways | n/a | n/a | n/a |  |
| ADANIPOWER | sideways | n/a | n/a | n/a |  |
| ALKEM | sideways | n/a | n/a | n/a |  |
| AMBER | sideways | n/a | n/a | n/a |  |
| AMBUJACEM | sideways | n/a | n/a | n/a |  |

## Commentary

Current read from the tracker:

- SUPREMEIND: near trigger / watch; Locked setup: Above 3,706.40; T1 3,743.31, stop 3,678.72; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision WATCH ONLY (Option Buy OK, score 57)
- BAJAJ-AUTO: long active; Locked setup: Above 11,915.90; T1 11,992.77, stop 11,879.88; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision WATCH ONLY (Option Buy OK, score 57)
- LODHA: watch; Locked setup: Above 1,269.77; T1 1,281.95, stop 1,262.19; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- OIL: watch; Locked setup: Above 476.28; T1 480.29, stop 474.19; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- 360ONE: watch; Watch price n/a; no active setup; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- ABB: watch; Watch price n/a; no active setup; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- ABCAPITAL: watch; Watch price n/a; no active setup; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- ADANIENSOL: watch; Watch price n/a; no active setup; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- ADANIENT: watch; Watch price n/a; no active setup; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)
- ADANIGREEN: watch; Breakout above 1,308.30; support n/a; T1 n/a; F&O sideways (PCR n/a, basis n/a, max pain n/a); Decision AVOID (No Trade, score 3)

Cycle changes:
- New added: none
- Removed: none
- Forming: LODHA, OIL, 360ONE, ABB, ABCAPITAL, ADANIENSOL, ADANIENT, ADANIGREEN
- Confirmed: SUPREMEIND
- Active: BAJAJ-AUTO
- Status changes: LODHA long active -> watch; OIL near trigger / watch -> watch

Meaningful change:
- SUPREMEIND changed from long active to near trigger / watch
- BAJAJ-AUTO changed from near trigger / watch to long active
- LODHA changed from long active to watch
- OIL changed from near trigger / watch to watch

Best actionable names:
1. BAJAJ-AUTO long active, valid but needs follow-through.
2. SUPREMEIND near trigger / watch, valid but needs follow-through.
3. OIL watch, avoid; decision gate not satisfied.
4. LODHA watch, avoid; decision gate not satisfied.
5. 360ONE watch, avoid; decision gate not satisfied.

Watch next:
- Market context: NIFTY 24,158 +0.28%, BANKNIFTY 57,461 -0.08%, VIX 10.89 -1.62%, breadth 390A/357D
- Source health: get_live_market_overview ok | get_top_gainers_losers ok | get_nse_quotes ok: yfinance (NSE batch) | scan_symbols_intraday ok

## Email

- Status: email dispatch failed: SMTP email provider is selected but required setting(s) are missing: SMTP_PASSWORD. For Gmail, set AGENT_ADDA_EMAIL_PROVIDER=gmail, SMTP_USER=agentadda.in@gmail.com and SMTP_PASSWORD to a Google App Password. For iCloud, set AGENT_ADDA_EMAIL_PROVIDER=icloud, SMTP_USER=pgorai@icloud.com and SMTP_PASSWORD to an Apple app-specific password.
- Subject: Agent Adda Intraday F&O Alert: BAJAJ-AUTO LONG ACTIVE
