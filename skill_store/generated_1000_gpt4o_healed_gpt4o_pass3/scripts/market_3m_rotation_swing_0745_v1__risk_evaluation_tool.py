def run(context):
    risks = []
    for return_data in context['index_returns']:
        if return_data['return_pct'] < -5:
            risks.append({'index': return_data['index_symbol'], 'risk': 'High volatility'})
    return risks