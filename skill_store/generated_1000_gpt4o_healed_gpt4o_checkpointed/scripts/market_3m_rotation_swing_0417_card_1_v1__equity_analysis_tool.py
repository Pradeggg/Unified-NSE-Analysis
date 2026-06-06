def run(context):
    equities = context.get('equity_data', [])
    analyzed = []
    for equity in equities:
        if equity.get('relative_strength', 0) > 70 and equity.get('trading_signal', '') == 'buy':
            analyzed.append(equity)
    return {'analyzed_equities': analyzed}