def run(context):
    risk_flags = {}
    for row in context['scores.stage_snapshots']:
        if row['rsi'] > 70:
            risk_flags[row['symbol']] = 'Overbought'
        elif row['rsi'] < 30:
            risk_flags[row['symbol']] = 'Oversold'
    return risk_flags