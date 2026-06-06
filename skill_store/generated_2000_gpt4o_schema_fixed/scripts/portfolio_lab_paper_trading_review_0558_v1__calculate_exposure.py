def run(context):
    # Example only; calculates the exposure based on holdings and market prices
    exposure = {}
    for holding in context['holdings']:
        symbol = holding['symbol']
        qty = holding['qty']
        price = next(item for item in context['eod_prices'] if item['symbol'] == symbol)['close']
        exposure[symbol] = qty * price
    return {'exposure_summary': exposure}