def run(context):
    data = context['scores.stage_snapshots']
    risk_flags = []
    for record in data:
        risk = 'Low' if record['stage_score'] > 7 and record['trend_signal'] == 'Positive' else 'High'
        risk_flags.append({'symbol': record['symbol'], 'risk_flag': risk})
    return risk_flags