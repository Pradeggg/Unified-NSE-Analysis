def run(context):
    risk_flags = []
    for entry in context:
        if entry['stage_score'] < 50 or entry['trend_signal'] == 'negative':
            risk_flags.append({'symbol': entry['symbol'], 'risk': 'high'})
        else:
            risk_flags.append({'symbol': entry['symbol'], 'risk': 'low'})
    return risk_flags