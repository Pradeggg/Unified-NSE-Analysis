# Assume context contains SQL results
latest_quarterly_data = {
    "symbols": context.get('symbols', []),
    "revenue_growth": context.get('revenue_growth', []),
    "pat_growth": context.get('pat_growth', []),
    "margin_changes": context.get('margin_changes', [])
}