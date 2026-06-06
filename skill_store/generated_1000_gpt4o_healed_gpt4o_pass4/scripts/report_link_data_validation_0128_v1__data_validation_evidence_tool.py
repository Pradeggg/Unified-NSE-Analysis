def run(context):
    findings = []
    for run in context.get('report.enhanced_runs', []):
        if not run.get('stocks_analyzed') or not run.get('stocks_filtered'):
            findings.append({'run_id': run.get('run_id'), 'message': 'Missing data in run.'})
    return {'findings': findings}