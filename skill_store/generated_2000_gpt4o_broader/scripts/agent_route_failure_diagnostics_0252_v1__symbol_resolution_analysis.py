def run(context):
    return [symbol for symbol in context.inputs['list_of_symbols'] if not valid_symbol(symbol)]