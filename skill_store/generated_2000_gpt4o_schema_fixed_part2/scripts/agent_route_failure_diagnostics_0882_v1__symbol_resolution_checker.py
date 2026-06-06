def run(context):
    # Mock resolution check; actual function would resolve symbols
    resolved_symbols = [symbol for symbol in context['symbol_list'] if symbol.startswith('NSE_')]
    return {'resolved_symbols': resolved_symbols}