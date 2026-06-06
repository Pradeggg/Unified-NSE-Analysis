def run(context):
    findings = []
    for run in context.get('report.enhanced_runs', []):
        if not run.get('stocks_analyzed') or not run.get('stocks_filtered'):
            findings.append(f'Missing data in run with ID: {run.get('run_id')}')
    return findings