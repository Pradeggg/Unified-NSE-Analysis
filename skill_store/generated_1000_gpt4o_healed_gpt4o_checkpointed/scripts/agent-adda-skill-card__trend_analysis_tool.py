def run(context):
    holdings = context['holdings_data']
    trends = context['trend_signals']
    add_candidates = [h['symbol'] for h in holdings if trends[h['symbol']]['trend_signal'] == 'Strong Uptrend']
    trim_candidates = [h['symbol'] for h in holdings if trends[h['symbol']]['trend_signal'] == 'Downtrend']
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}