def run(context):
    return [f'NSE:{symbol}' for symbol in context['candidate_symbols']]