def run(context):
    findings = []
    # Example pseudo-code for validation
    for run in context['report.enhanced_runs']:
        if not run['stocks_analyzed'] or not run['stocks_filtered']:
            findings.append(f'Missing data in run with ID: {run['run_id']}')
    return findings