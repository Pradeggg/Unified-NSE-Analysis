def run(context):
    results = []
    for data in context['inputs']:
        analysis = {
            'symbol': data['symbol'],
            'insider_strength': data['qty'] * data['value_cr'],
            'deal_strength': data['deal_qty'] * data['deal_price'],
            'signal_strength': data['rsi'] if data['trading_signal'] == 'Positive' else 0
        }
        results.append(analysis)
    return {'analysis_result': results}