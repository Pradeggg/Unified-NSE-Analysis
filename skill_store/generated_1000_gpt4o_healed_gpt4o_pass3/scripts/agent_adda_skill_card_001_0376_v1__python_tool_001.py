def run(context):
    findings = []
    if not isinstance(context['enhanced_runs'], list) or not context['enhanced_runs']:
        raise ValueError('enhanced_runs must be a non-empty list')
    for entry in context['enhanced_runs']:
        if 'analysis_date' in entry and entry['analysis_date'] < datetime.today().date() - timedelta(days=1):
            findings.append({'run_id': entry['run_id'], 'issue': 'old_analysis_date'})
    if not findings:
        findings.append({'issue': 'No old analysis dates found'})
    return findings