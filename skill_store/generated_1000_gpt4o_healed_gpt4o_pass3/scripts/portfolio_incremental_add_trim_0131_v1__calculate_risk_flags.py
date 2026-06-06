def run(context):
    risk_flags = []
    for record in context.get('recent_data', []):
        if record.get('trend_signal', 0) < 0:
            risk_flags.append({'symbol': record['symbol'], 'risk': 'high'})
    return {'risk_flags': risk_flags}