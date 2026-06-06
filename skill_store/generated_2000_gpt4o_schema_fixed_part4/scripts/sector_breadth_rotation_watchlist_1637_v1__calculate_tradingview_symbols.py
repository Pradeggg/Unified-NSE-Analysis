def run(context):
    return [symbol + '.NS' for symbol in context['candidate_symbols']]