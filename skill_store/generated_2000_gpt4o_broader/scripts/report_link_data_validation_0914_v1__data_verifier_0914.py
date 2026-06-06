def run(context):
    runs = context['run_data']
    stocks = context['filtered_stocks_data']
    # Validation logic
    summary = {'universe_mismatch': [], 'ranking_issues': []}
    for run in runs:
        if run['universe_size'] != len(run['stocks_analyzed']):
            summary['universe_mismatch'].append(run['run_id'])
        related_stocks = [s for s in stocks if s['run_id'] == run['run_id']]
        if any(s['rank'] is None for s in related_stocks):
            summary['ranking_issues'].append(run['run_id'])
    return summary