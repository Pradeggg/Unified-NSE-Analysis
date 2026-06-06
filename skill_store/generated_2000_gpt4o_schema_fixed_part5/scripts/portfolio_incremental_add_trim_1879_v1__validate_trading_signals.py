def run(context):
    return [row for row in context['portfolio_state'] if row['trading_signal'] in ['BUY', 'STRONG_BUY']]