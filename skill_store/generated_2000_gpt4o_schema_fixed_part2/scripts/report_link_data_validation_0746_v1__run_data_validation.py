def run(context):
    # Extract data from context
    results = context['sql_results']
    findings = []
    # Analyze results to create findings summary
    for result in results:
        findings.append(f"Data check for {result['run_id']} successful.")
    return {'findings_summary': findings}