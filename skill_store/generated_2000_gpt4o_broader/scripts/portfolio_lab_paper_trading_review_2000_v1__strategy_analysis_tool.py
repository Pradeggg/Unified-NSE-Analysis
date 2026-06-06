def run(context):
    # Analyze strategy data and extract insights.
    insights = []
    for strategy in context['strategy_data']:
        # Example analysis logic, simplified
        insights.append({'symbol': strategy['symbol'], 'return': strategy['return_pct']})
    return insights