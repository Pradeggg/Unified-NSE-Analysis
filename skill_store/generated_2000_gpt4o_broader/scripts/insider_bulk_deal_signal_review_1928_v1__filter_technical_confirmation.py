def run(context):
    return [symbol for symbol in context['symbol_data'] if symbol['technical_score'] > threshold]