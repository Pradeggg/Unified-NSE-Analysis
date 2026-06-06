def run(context):
    candidates = {'add': [], 'trim': []}
    for record in context['data']:
        if record['stage_score'] > 80 and record['trading_signal'] == 'BUY':
            candidates['add'].append(record['symbol'])
        elif record['trading_signal'] == 'SELL':
            candidates['trim'].append(record['symbol'])
    return candidates