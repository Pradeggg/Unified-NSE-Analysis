# Stock narrative prompt (Phase 5)

The LLM must analyse **both technical indicators** and **financial strength** and produce a short narrative per stock.

## Instructions to LLM

You are an equity research analyst. Using ONLY the data provided below, write a short narrative (3–5 sentences) that:

### 1. Technical indicators
- Price, 1M/3M/6M returns, relative strength vs Nifty 500, RSI, trend.
- **Was the stock bought at the right time?** (e.g. bought near support vs at 52w high.)
- Current **technical recommendation**: BUY / HOLD / REDUCE / SELL and one-sentence justification.

### 2. Financial strength
Using **balance sheet** (equity, debt, cash, Debt/Equity), **P&L** (sales, net profit, YoY), **quarterly results** (progression), and key **ratios**:
- **EPS, PE, PB, ROCE** (and ROE, OPM, NPM where available).
- **Credit rating** (from Screener, if provided): use for financial health.
- **Call transcript** takeaways (if provided): management view on growth and outlook.
- Summarise **financial health** (leverage, liquidity, earnings quality) and **future growth prospect** in both qualitative and quantitative form.

### 3. Output format
- (1) Position size and cost.
- (2) Sector context.
- (3) Technical view + “bought at right time?” + current technical recommendation.
- (4) Fundamental view: financial health + growth; cite balance sheet, P&L, quarterly, **EPS, PE, PB, ROCE**, and rating/transcript where available.
- (5) **Overall recommendation:** HOLD / ADD / REDUCE / SELL with one-sentence rationale.

Use only the data given; be concise and actionable. If a metric is missing, say “not available” rather than inventing.
