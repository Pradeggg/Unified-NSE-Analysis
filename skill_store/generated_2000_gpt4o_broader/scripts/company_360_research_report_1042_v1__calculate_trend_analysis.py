def run(context):
    # Quarantined read-only example to highlight trend analysis.
    prices = context['historical_price_data']
    return {'trend_summary': 'uptrend' if prices[-1] > prices[0] else 'downtrend'}