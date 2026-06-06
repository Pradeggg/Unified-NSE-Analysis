def run(context):
    holdings = context['holdings']
    eod_prices = context['eod_prices']
    exposure = {}

    for symbol, holding in holdings.items():
        if symbol in eod_prices:
            market_value = holding['qty'] * eod_prices[symbol]['close']
            exposure[symbol] = {
                'market_value': market_value,
                'change_pct': eod_prices[symbol]['change_pct']
            }
    return {'exposure_summary': exposure}