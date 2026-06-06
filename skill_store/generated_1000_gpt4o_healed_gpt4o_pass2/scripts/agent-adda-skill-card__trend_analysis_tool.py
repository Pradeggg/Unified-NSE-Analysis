def run(context):
    holdings = context.get('holdings_data', [])
    trends = context.get('trend_signals', {})
    add_candidates = [h['symbol'] for h in holdings if trends.get(h['symbol'], {}).get('trend_signal') == 'Strong Uptrend']
    trim_candidates = [h['symbol'] for h in holdings if trends.get(h['symbol'], {}).get('trend_signal') == 'Downtrend']
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}