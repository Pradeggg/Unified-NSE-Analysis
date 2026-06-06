def run(context):
    # Example Python analysis
    results = []
    for row in context['signals.signal_log'].itertuples():
        if row.hit_stop:
            results.append({'symbol': row.symbol, 'outcome': 'hit_stop'})
        elif row.hit_target:
            results.append({'symbol': row.symbol, 'outcome': 'hit_target'})
    return results