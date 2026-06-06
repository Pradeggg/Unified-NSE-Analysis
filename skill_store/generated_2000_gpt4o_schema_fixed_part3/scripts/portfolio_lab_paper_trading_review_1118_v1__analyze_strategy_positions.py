def run(context):
    holdings = context['holdings_data']
    signals = context['signal_data']
    latest_prices = context['latest_ohlcv_data']
    # Strategy analysis logic here, using only inputs
    return {'analyzed_positions': [{'symbol': h['symbol'], 'action': s['signal']} for h in holdings for s in signals if h['symbol'] == s['symbol']]}