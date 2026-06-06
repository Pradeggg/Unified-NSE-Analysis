def run(context):
    risk_flags = []
    snapshot_data = context.get('scores.stage_snapshots', [])
    for record in snapshot_data:
        if record.get('stage_score', 0) < 2:
            risk_flags.append({'symbol': record['symbol'], 'risk_reason': 'Low Stage Score'})
        elif record.get('rsi', 0) > 70:
            risk_flags.append({'symbol': record['symbol'], 'risk_reason': 'Overbought'})
    return {'risk_flags': risk_flags}