def run(context):
    results = []
    for run in context['enhanced_runs']:
        for stock in context['filtered_stocks']:
            if stock['run_id'] == run['run_id']:
                results.append({
                    'run_id': run['run_id'],
                    'symbol': stock['symbol'],
                    'issue': 'Potential missing data or diagnostic tool mismatch.'
                })
    return results