def run(context):
    resolved_symbols = []
    for symbol in context['symbol_data']:
        if symbol in context['approved_tables'][0]:
            resolved_symbols.append(symbol)
    return resolved_symbols