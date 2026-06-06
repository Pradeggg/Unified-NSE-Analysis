def run(context):
    holdings = context['holdings_data']
    market = context['market_data']
    # Calculate paper trading exposure based on holdings and market data
    exposure = sum([h['qty'] * m['last_price'] for h, m in zip(holdings, market) if h['symbol'] == m['symbol']])
    return {'exposure_summary': exposure}