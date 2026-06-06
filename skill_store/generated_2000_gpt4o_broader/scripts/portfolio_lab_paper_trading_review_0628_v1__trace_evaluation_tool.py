def run(context):
    signal_data = context['signal_data']
    portfolio_data = context['portfolio_data']
    valid_trades = []
    violations = []
    # Analyze paper trades against signals
    for trade in signal_data:
        if trade_matches_portfolio(trade, portfolio_data):
            valid_trades.append(trade)
        else:
            violations.append(trade)
    return valid_trades, violations