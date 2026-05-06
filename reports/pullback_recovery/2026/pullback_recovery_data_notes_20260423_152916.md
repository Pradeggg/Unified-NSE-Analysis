# Pullback recovery screener — data analysis (step 1)

Generated: 2026-04-23T15:29:18

## Universe (index constituents)

| Index | Symbols |
|-------|---------|
| NIFTY MIDCAP SELECT | 25 |
| NIFTY 500 | 501 |
| NIFTY INDIA DEFENCE | 18 |
| NIFTY CPSE | 11 |
| NIFTY MICROCAP 250 | 250 |

**Union (unique symbols):** 751

## Price data coverage

- **Stock file:** `/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data/nse_sec_full_data.csv`
- **Date range (filtered universe):** `2023-01-02 00:00:00` → `2026-04-22 00:00:00`
- **Benchmark:** Nifty 500 close from `/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data/nse_index_data.csv`
- **Benchmark range:** `2019-05-20 00:00:00` → `2026-04-22 00:00:00`

## Interpretation

- **52w peak** = rolling max of *HIGH* over ~252 sessions (full-year window).
- **Drawdown filter** keeps names within **≤30%** of that rolling peak (your “not below 25–30%” band).
- **RS (pullback window)** = stock total return minus Nifty 500 total return over ~60 sessions.
- **Recovery** = rebound from the minimum *close* inside the same ~60-session window.
- **Slow pullback** = average excess return vs index on days Nifty 500 was down (higher = more resilient).
- **Fundamentals** use `organized/data/fundamental_scores_database.csv` as a **composite proxy**; live last-3-quarter audited metrics are **not** in this file — refresh from filings/Screener for diligence.

## Screen output

- Rows passing all hard filters: **76**
