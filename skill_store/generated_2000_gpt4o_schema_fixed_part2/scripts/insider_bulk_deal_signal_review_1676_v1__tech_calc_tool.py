def run(context):
    # Basic calculation to rank symbols based on trend score
    return [{'symbol': x['symbol'], 'trend_score': x['technical_score'] * 0.8, 'risk_level': 'low' if x['technical_score'] > 50 else 'high'} for x in context]