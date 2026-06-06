def run(context):
    return sorted(context['symbol_watchlist'], key=lambda x: x['trading_signal'], reverse=True)