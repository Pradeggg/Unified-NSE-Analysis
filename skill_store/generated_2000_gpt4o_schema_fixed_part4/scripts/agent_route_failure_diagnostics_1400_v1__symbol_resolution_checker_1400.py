def run(context):
    symbol_list = context.inputs['symbol_list']
    missing_symbols = []
    # Simulated resolution check
    for symbol in symbol_list:
        if symbol not in context['approved_tables'][1]:
            missing_symbols.append(symbol)
    return {'missing_symbols': missing_symbols, 'resolution_issues': []}