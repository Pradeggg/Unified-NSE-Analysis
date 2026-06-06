def run(context):
    data = context['scores.stage_snapshots']
    risk_flags = []
    for record in data:
        risk = 'Low' if record.get('stage_score', 0) > 7 and record.get('trend_signal', '') == 'Positive' else 'High'
        risk_flags.append({'symbol': record.get('symbol', ''), 'risk_flag': risk})
    return risk_flags