def run(context):
    recent_data = context['recent_data']
    risk_flags = []
    for record in recent_data:
        if record['trend_signal'] < 0:
            risk_flags.append({'symbol': record['symbol'], 'risk': 'high'})
    return {'risk_flags': risk_flags}