def run(context):
    discrepancies = []
    stocks = context.get('stocks', [])
    for stock in stocks:
        if stock.get('current_price') is None or stock.get('volume') is None:
            discrepancies.append(stock.get('symbol'))
    return {'discrepancies': discrepancies}