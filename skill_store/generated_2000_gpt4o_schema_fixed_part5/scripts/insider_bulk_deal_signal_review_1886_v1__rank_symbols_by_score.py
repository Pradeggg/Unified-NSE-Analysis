def run(context):
    # Assume context.symbol_scores is a list of dictionaries with 'symbol' and 'score'.
    ranked = sorted(context['symbol_scores'], key=lambda x: x['score'], reverse=True)
    return {'ranked_symbols': [s['symbol'] for s in ranked[:10]]}