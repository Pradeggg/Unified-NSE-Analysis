def run(context):
    close_price = context['close_price']
    account_size = context['account_size']
    risk_per_trade = context['risk_per_trade']
    position_size = (account_size * risk_per_trade) / close_price
    return {'position_size': position_size}