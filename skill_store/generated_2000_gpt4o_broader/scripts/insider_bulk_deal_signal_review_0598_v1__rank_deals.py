def run(context):
    deals = context['deal_summary']
    confirmations = context['technical_confirmation']
    ranked = []
    for deal in deals:
        if any(conf['symbol'] == deal['symbol'] for conf in confirmations):
            ranked.append(deal['symbol'])
    return {'ranked_symbols': ranked}