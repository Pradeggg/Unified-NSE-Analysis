def run(context):
    findings = []
    for entry in context['enhanced_runs']:
        if entry['analysis_date'] < datetime.today() - timedelta(days=1):
            findings.append({'run_id': entry['run_id'], 'issue': 'old_analysis_date'})
    return findings