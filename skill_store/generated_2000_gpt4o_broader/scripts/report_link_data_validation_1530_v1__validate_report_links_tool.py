def run(context):
    findings = []
    for row in context['report.enhanced_filtered_stocks']:
        if row['recommendation'] is None:
            findings.append(f'Symbol {row['symbol']} missing recommendation in run {row['run_id']}')
    return findings