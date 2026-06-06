def run(context):
    risk_flags = {}
    for entry in context:
        risk_flags[entry['symbol']] = 'high' if entry['stage_score'] < 50 or entry['trend_signal'] == 'negative' else 'low'
    return risk_flags