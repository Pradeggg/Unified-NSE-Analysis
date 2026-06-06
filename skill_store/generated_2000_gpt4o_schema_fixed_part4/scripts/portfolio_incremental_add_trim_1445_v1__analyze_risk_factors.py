def run(context):
    # Analyze risks based on RSI and technical indicators.
    risk_assessments = {}
    for symbol, snapshot in context['stage_snapshots'].items():
        rsi = snapshot['rsi']
        if rsi > 70:
            risk_assessments[symbol] = 'OVERBOUGHT'
        elif rsi < 30:
            risk_assessments[symbol] = 'OVERSOLD'
        else:
            risk_assessments[symbol] = 'NEUTRAL'
    return risk_assessments