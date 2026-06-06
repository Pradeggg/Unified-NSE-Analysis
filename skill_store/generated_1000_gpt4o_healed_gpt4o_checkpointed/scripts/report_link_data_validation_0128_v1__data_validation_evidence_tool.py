def run(context):
    findings = []
    try:
        for run in context['report.enhanced_runs']:
            if not run['stocks_analyzed'] or not run['stocks_filtered']:
                findings.append(f"Missing data in run with ID: {run['run_id']}")
    except KeyError as e:
        findings.append(f"Key error encountered: {str(e)}")
    return findings