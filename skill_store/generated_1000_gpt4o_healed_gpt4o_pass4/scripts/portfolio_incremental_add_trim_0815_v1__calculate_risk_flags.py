def run(context):
    risk_flags = {}
    for entry in context:
        risk_flags[entry['symbol']] = 'high' if entry.get('stage_score', 0) < 50 or entry.get('trend_signal', '') == 'negative' else 'low'
    return risk_flags