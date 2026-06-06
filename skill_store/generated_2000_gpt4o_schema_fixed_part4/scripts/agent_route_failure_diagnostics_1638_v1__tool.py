# Provided function 'run' reads from context. Ensure it is read-only.
def run(context):
    # Analyze data context to extract routes and potential issues
    report_entries = context['report.enhanced_runs'][:20]
    return {'summary': f'Analyzed {len(report_entries)} run entries.'}