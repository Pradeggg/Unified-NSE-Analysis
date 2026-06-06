def run(context):
    symbol_insights = {}
    for symbol, data in context['symbol_data'].items():
        insights = analyze_trends(data, context['signal_data'])
        symbol_insights[symbol] = insights
    return symbol_insights