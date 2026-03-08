# Screen Specification: [Sector Name]

**Date:**  
**Links to:** Hypothesis memo (H2), Enhanced Research Approach Phase 3.

---

## 1. Objective

*What we want the screen to achieve (e.g. “Select quality names with positive relative strength vs sector/market”).*

---

## 2. Quality criteria

| Criterion | Definition | Source / column | Threshold (example) |
|-----------|-------------|------------------|----------------------|
| ROCE | Return on capital employed | Screener / ratios | > 15% |
| Revenue growth (YoY) | Latest fiscal or TTM | Screener / quarterly | > 10% |
| Fundamental score | Composite (earnings, sales, financial, institutional) | Our pipeline | > 70 |
| Debt/Equity | Net debt to equity | Screener / ratios | < 2 |
| *Add as needed* | | | |

**Minimum required:** e.g. “Stock must pass ROCE and fundamental score; others optional.”

---

## 3. Momentum / relative strength criteria

| Criterion | Definition | Lookback | Threshold (example) |
|-----------|-------------|----------|----------------------|
| RS vs sector index | Stock return − index return | 6M | > 0 |
| RS vs Nifty 500 | Stock return − Nifty 500 return | 3M | > 0 |
| Technical score | DMA, RSI, structure | Latest | > 70 |
| Trend | STRONG_BULLISH / BULLISH / etc. | Latest | Not BEARISH |

**Minimum required:** e.g. “RS vs Nifty Auto > 0 over 6M.”

---

## 4. Composite score (if used)

- **Formula:** e.g. `composite = 0.4 × funda_score_norm + 0.4 × technical_score_norm + 0.2 × rs_rank_norm`
- **Normalization:** e.g. All inputs scaled 0–100 (percentile rank within universe).
- **Use:** Rank universe; shortlist = top N (e.g. 15) subject to minimum liquidity.

---

## 5. Hard exclusions

- **Liquidity:** e.g. Minimum average daily value (₹ Cr) or exclude if not in Nifty 500.
- **Data:** Exclude if fundamental or price data missing for > X% of required fields.
- **Other:** e.g. Exclude if under suspension or in default (if data available).

---

## 6. Output

- **Full universe table:** All names with all metrics (for dashboard and audit).
- **Shortlist:** Names passing screen (or top N by composite); key metrics only.
- **Audit:** List of symbols excluded and reason (e.g. “ROCE < 15%”, “RS < 0”).

---

## 7. Revision log

| Date | Change |
|------|--------|
|      | Initial spec |
