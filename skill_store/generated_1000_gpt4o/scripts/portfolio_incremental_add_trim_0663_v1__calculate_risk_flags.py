def run(context):
    risk_flags = []
    for record in context.snapshot_data:
        if record['stage_score'] < 2:
            risk_flags.append({'symbol': record['symbol'], 'risk_reason': 'Low Stage Score'})
        elif record['rsi'] > 70:
            risk_flags.append({'symbol': record['symbol'], 'risk_reason': 'Overbought'})
    return {'risk_flags': risk_flags}