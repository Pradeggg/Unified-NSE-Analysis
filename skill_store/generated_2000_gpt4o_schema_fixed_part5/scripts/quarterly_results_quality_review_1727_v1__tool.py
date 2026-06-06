def run(context):
    # Analyze symbol data for sector-relative insights
    insights = []
    for data in context['symbol_data']:
        if data['growth_qoq_revenue_pct'] > 0 and data['trading_signal'] == 'BUY':
            insights.append(data['symbol'])
    return {'sector_relative_insight': insights}