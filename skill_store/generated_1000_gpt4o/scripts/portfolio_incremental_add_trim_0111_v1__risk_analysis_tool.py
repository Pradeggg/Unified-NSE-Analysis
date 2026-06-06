def run(context):
    # Example logic for risk flags
    risk_flags = []
    for holding in context['holding_details']:
        price_info = next((p for p in context['latest_prices'] if p['symbol'] == holding['symbol']), None)
        if price_info and price_info['can_slim_score'] < 4 and price_info['minervini_score'] < 4:
            risk_flags.append({'symbol': holding['symbol'], 'flag': 'high_risk'})
    return risk_flags