def run(context):
    symbols = context['symbol_list']
    technical_scores = context['technical_scores']
    return {symbol: 'Bullish' if score > 70 else 'Neutral' for symbol, score in zip(symbols, technical_scores)}