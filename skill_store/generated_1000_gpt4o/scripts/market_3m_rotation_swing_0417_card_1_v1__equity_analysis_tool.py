def run(context):
    equities = context.inputs['equity_data']
    analyzed = []
    for equity in equities:
        if equity['relative_strength'] > 70 and equity['trading_signal'] == 'buy':
            analyzed.append(equity)
    return {'analyzed_equities': analyzed}