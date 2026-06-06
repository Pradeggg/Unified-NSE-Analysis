def run(context):
    discrepancies = []
    for stock in context['inputs']:
        if stock['current_price'] is None or stock['volume'] is None:
            discrepancies.append(stock['symbol'])
    return {'discrepancies': discrepancies}