def calculate_exposure(context):
    # Compute the portfolio exposure using the latest market prices
    holdings = context['portfolio.holdings']
    eod_data = context['market.equity_eod']
    exposure = {}
    for holding in holdings:
        symbol = holding['symbol']
        qty = holding['qty']
        price = next((item['close'] for item in eod_data if item['symbol'] == symbol), None)
        if price:
            exposure[symbol] = qty * price
    return exposure