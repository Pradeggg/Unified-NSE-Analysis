# Agent Adda SmallCap And MidCap Paper Portfolio Strategy - Rs. 4L Budget

Date: 2026-08-15
Prepared for: Mahesh Binjola
Prepared by: Pradeep Gorai
Status: Internal research and paper/model portfolio review
Total deployed capital reference: Rs. 4,00,000

## Executive Summary

This note sets the working budget for the Agent Adda SmallCap and MidCap paper/model portfolios at Rs. 4,00,000.

The operating split is equal:

| Sleeve | Allocation | Amount | Fresh-mode slots | Slot budget |
|---|---:|---:|---:|---:|
| SmallCap S2 | 50% | Rs. 2,00,000 | 9 | Rs. 22,222 |
| MidCap S1 | 50% | Rs. 2,00,000 | 15 | Rs. 13,333 |
| Combined | 100% | Rs. 4,00,000 | 24 | Risk-reviewed |

The portfolio remains research-first and paper-only. It does not approve live investment, external solicitation, pooled capital, PMS, AIF, mutual-fund activity, or regulated advisory activity.

## 1. Standard Commands

Use the default fresh-mode command for a zero-position start:

```bash
python tools/fund_daily.py --fresh --html
```

This defaults to Rs. 4,00,000 total budget, split as Rs. 2,00,000 SmallCap and Rs. 2,00,000 MidCap.

Sleeve-only starts remain available:

```bash
python tools/fund_daily.py --fresh --sc-only --budget 200000 --html
python tools/fund_daily.py --fresh --mc-only --budget 200000 --html
```

## 2. Current Fresh-Mode Output

As of the 2026-08-15 local DB-backed fresh scan:

| Sleeve | Slots filled | Estimated outlay | Idle cash |
|---|---:|---:|---:|
| SmallCap S2 | 9/9 | about Rs. 1,97,666 | about Rs. 2,334 |
| MidCap S1 | 15/15 | about Rs. 1,87,535 | about Rs. 12,465 |
| Combined | 24/24 | about Rs. 3,85,201 | about Rs. 14,799 |

SmallCap S2 selected:

| Rank | Symbol | Note |
|---:|---|---|
| 1 | RPEL | Stage 2 + high RS + fund gate |
| 2 | AJANTPHARM | Also qualifies in MidCap |
| 3 | KANPRPLA | Stage 2 + high RS + fund gate |
| 4 | DIFFNKG | Stage 2 + high RS + fund gate |
| 5 | RPTECH | Stage 2 + high RS + fund gate |
| 6 | PANAMAPET | Stage 2 + high RS + fund gate |
| 7 | EXIDEIND | Also qualifies in MidCap |
| 8 | BELRISE | Stage 2 + high RS + fund gate |
| 9 | DEEPINDS | Stage 2 + high RS + fund gate |

MidCap S1 selected:

| Rank | Symbol | Note |
|---:|---|---|
| 1 | IPCALAB | Stage 2 + fund gate |
| 2 | FLUOROCHEM | Stage 2 + fund gate |
| 3 | AJANTPHARM | Also qualifies in SmallCap |
| 5 | EXIDEIND | Also qualifies in SmallCap |
| 6 | OBEROIRLTY | Stage 2 + fund gate |
| 7 | COFORGE | Stage 2 + fund gate |
| 8 | BERGEPAINT | Stage 2 + fund gate |
| 9 | ENDURANCE | Stage 2 + fund gate |
| 10 | AUROPHARMA | Stage 2 + fund gate |
| 11 | SONACOMS | Stage 2 + fund gate |
| 12 | GODREJIND | Stage 2 + fund gate |
| 13 | FEDERALBNK | Stage 2 + fund gate |
| 14 | NYKAA | Stage 2 + fund gate |
| 15 | KALYANKJIL | Stage 2 + fund gate |
| 16 | 360ONE | Backfilled because APARINDS could not buy one share in slot |

Skipped before fill:

| Rank | Symbol | Reason |
|---:|---|---|
| 4 | APARINDS | Price around Rs. 17,225 exceeded the Rs. 13,333 MidCap slot budget, so quantity was zero |

## 3. Risk Framework On Rs. 4,00,000

| Risk Rule | Limit |
|---|---:|
| Normal risk per new trade | Rs. 2,000-3,000 |
| High-conviction max risk per trade | Rs. 4,000 |
| Total open risk cap | Rs. 24,000 |
| Sector cap | Rs. 1,00,000 |
| Single-stock cap | Rs. 40,000 |
| Minimum reward/risk | 2:1 |
| Averaging down | Not allowed |
| Chasing above trigger | Not allowed |

Position size should still be determined by stop-loss risk, not only by equal slot budget:

```text
risk_quantity      = floor(allowed_trade_risk / abs(entry_price - stop_price))
position_quantity  = floor(max_position_value / entry_price)
cash_quantity      = floor(available_cash / entry_price)
liquidity_quantity = floor(max_daily_participation_value / entry_price)

final_quantity = min(risk_quantity, position_quantity, cash_quantity, liquidity_quantity)
```

The fresh-mode slot quantity is an inception estimate. A final paper order still requires trigger, stop, filing, liquidity, governance, and risk-cap checks.

## 4. Operating Rules

1. Use Rs. 4,00,000 as the current working budget.
2. Do not use the older Rs. 3,00,000 strategy note as the active allocation reference.
3. Treat cross-qualifying names, such as AJANTPHARM and EXIDEIND, as valid only if combined exposure remains within the Rs. 40,000 single-stock cap.
4. Skip any candidate where slot budget cannot buy one share.
5. Use the next purchasable passing candidate as backfill.
6. Do not promote a fresh-mode row into paper order unless the sleeve monitor allows it and the stop/risk map is complete.
7. Keep the report wording research-only and paper-only.

## 5. Current Implementation Status

Implemented:

- `python tools/fund_daily.py --fresh --html` defaults to Rs. 4,00,000.
- SmallCap uses Rs. 2,00,000 across 9 slots.
- MidCap uses Rs. 2,00,000 across 15 slots.
- Zero-quantity fresh candidates are skipped and backfilled.
- `APARINDS` is skipped in the current MidCap list and `360ONE` is backfilled.
- Shared capital policy lives in `data/fund_capital_policy.yaml` and is read by `fund_daily.py`, `fund_lab_pnl.py`, and `fund_rebalance.py`.
- Fresh-mode quantity is the minimum of slot, stop-loss risk, single-stock cap, sector cap, and remaining sleeve cash.
- Every MidCap (and SmallCap) fresh row now carries stop, stop source, rupee risk, and the binding limit.
- Sector and single-stock caps are combined across both sleeves.

Still pending:

- A single canonical latest policy note linked from command output.

## Disclaimer

This document is for internal research and paper/model portfolio review only. It is not investment advice, not a recommendation to buy or sell securities, and not an offer or solicitation. Securities investments are subject to market risk. Past performance, paper performance, backtested performance, and model outputs do not guarantee future results.
