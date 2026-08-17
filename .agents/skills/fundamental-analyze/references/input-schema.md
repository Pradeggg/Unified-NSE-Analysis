# Input schema

Supply one UTF-8 JSON object. Monetary values must use one consistent unit, normally INR crore. Per-share values use the reporting currency.

```json
{
  "company": {
    "name": "Elgi Equipments Limited",
    "symbol": "ELGIEQUIP",
    "exchange": "NSE",
    "currency": "INR",
    "unit": "crore",
    "scope": "consolidated",
    "as_of_date": "2026-08-14",
    "price": 610.0,
    "market_cap": 19316.0,
    "shares_crore": 31.67
  },
  "annuals": [
    {
      "period": "FY2023",
      "revenue": 3041,
      "operating_profit": 377,
      "pat": 255,
      "eps": 8.05,
      "cfo": 238,
      "capex": 70,
      "equity": 1360,
      "borrowings": 515,
      "cash": null,
      "roce_pct": 21.0,
      "roe_pct": 20.0
    },
    {
      "period": "FY2024",
      "revenue": 3288,
      "operating_profit": 452,
      "pat": 305,
      "eps": 9.63,
      "cfo": 310,
      "capex": 82,
      "equity": 1580,
      "borrowings": 548,
      "cash": null,
      "roce_pct": 21.5,
      "roe_pct": 20.8
    },
    {
      "period": "FY2025",
      "revenue": 3510,
      "operating_profit": 529,
      "pat": 350,
      "eps": 11.05,
      "cfo": 391,
      "capex": 93,
      "equity": 1866,
      "borrowings": 577,
      "cash": null,
      "roce_pct": 22.0,
      "roe_pct": 21.5
    }
  ],
  "latest_quarter": {
    "period": "Q1 FY2027",
    "comparison_period": "Q1 FY2026",
    "revenue": 1062.2,
    "comparison_revenue": 867.0,
    "operating_profit": 155.3,
    "comparison_operating_profit": 121.0,
    "pat": 103.3,
    "comparison_pat": 86.0,
    "eps": 3.26,
    "exceptional_after_tax": -5.4
  },
  "valuation_scenarios": [
    {"name": "Bear", "forward_eps": 14, "pe": 28},
    {"name": "Base", "forward_eps": 16, "pe": 35},
    {"name": "Bull", "forward_eps": 18, "pe": 42}
  ],
  "sources": [
    {
      "title": "Q1 FY2027 results",
      "url": "https://example.com/direct-filing.pdf",
      "date": "2026-08-13",
      "tier": 1,
      "supports": ["latest_quarter"]
    },
    {
      "title": "NSE quote as-of price",
      "url": "https://www.nseindia.com/get-quotes/equity?symbol=ELGIEQUIP",
      "date": "2026-08-14",
      "tier": 1,
      "supports": ["price"]
    }
  ],
  "qualitative": {
    "verdict": {
      "business_quality": "Durable industrial franchise with distribution depth",
      "financial_quality": "High returns, moderate leverage, improving cash conversion",
      "growth_durability": "Mid-teens growth possible if mix and exports hold",
      "valuation_comfort": "Base implied value near the as-of price; limited margin of safety",
      "stance": "Watch; research-only, not a personalized recommendation"
    },
    "thesis": ["Short evidence-based point"],
    "moat": [],
    "growth_drivers": [],
    "risks": [],
    "governance": [],
    "monitorables": []
  },
  "institutional": {
    "segment_analysis": ["Segment, geography, mix, and margin observation"],
    "peer_context": ["Peer comparison with like-for-like scope and dates"],
    "management_commentary": ["Claim, evidence, delivery record, and analyst interpretation"],
    "shareholding": ["Promoter, FII, DII, public, pledge, and dilution trend"],
    "red_team_questions": ["What evidence would invalidate the thesis?"]
  }
}
```

## Rules

- Sort `annuals` oldest to newest and provide at least three periods.
- `qualitative.verdict` must include non-empty `business_quality`, `financial_quality`, `growth_durability`, `valuation_comfort`, and `stance`. Stance is research-only; do not personalize a buy/sell recommendation.
- Define `capex` as positive cash spent. The tool computes free cash flow as `cfo - capex`.
- Define `exceptional_after_tax` with its PAT sign: negative for an exceptional expense, positive for exceptional income. Normalized PAT equals reported PAT minus this value.
- Scenario implied value equals `forward_eps × pe`.
- Use source tier 1 for company/exchange/regulator filings, 2 for rating agencies and established databases, and 3 for secondary reporting.
- Every URL must be direct HTTP(S). Include an as-of price source whose `supports` list contains `price` (aliases: `as_of_price`, `company.price`).
- `institutional` is optional, but use it for deep-research or shareable reports. Each field is a list; statements must remain traceable to the source list.
