def run(context):
    holdings = context['holdings_data']
    prices = context['market_prices']
    holdings = holdings.merge(prices, on='symbol')
    holdings['exposure'] = holdings['qty'] * holdings['close']
    return holdings[['symbol', 'exposure']]