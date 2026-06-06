def run(context):
    run_data = context['run_data']
    stock_data = context['stock_data']
    findings = []
    if not run_data or not stock_data:
        findings.append('Missing report data for given day.')
    # Add other checks here
    return {'findings_report': findings}