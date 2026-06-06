def run(context):
    risks = []
    for index in context['index_returns']:
        if index['change_pct'] < -2:
            risks.append({'index': index['index_symbol'], 'risk': 'High volatility'})
    return {'risks': risks}