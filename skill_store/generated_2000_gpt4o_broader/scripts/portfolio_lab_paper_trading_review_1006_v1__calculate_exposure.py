def run(context):
    # Calculate the exposure based on open trades and holdings
    exposure = sum([trade['entry_high'] * trade['entry_low'] for trade in context['open_trades_today']])
    return {'calculated_exposure': exposure}