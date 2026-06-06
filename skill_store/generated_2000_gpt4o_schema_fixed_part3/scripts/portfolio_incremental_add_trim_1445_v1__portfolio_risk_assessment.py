def run(context):
    risk_flags = []
    for record in context['equity_data']:
        if record['rsi'] > 70 or record['trend_signal'] == 'BEARISH':
            risk_flags.append(record['symbol'])
    return risk_flags