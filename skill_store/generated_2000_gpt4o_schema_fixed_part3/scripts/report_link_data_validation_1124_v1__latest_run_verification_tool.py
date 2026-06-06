
 def run(context):
    latest_runs = context['run_data']  # Access the input data
    issues = []
    for run in latest_runs:
        if not run['symbol'] or run['score'] is None:
            issues.append({'run_id': run['run_id'], 'issue': 'Missing symbol or score'})
    return {'issues_found': issues, 'suggestions': ['Check if stock data sources are complete.']}
