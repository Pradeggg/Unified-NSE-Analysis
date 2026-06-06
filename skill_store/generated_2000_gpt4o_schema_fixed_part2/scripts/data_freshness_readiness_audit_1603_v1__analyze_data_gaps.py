def run(context):
    # Analyze data gaps for provided contexts
    gap_report = {}
    for source in context['data_source_statuses']:
        # Check for missing data criteria
        gap_report[source] = 'No gap' if source['status'] == 'fresh' else 'Gap found'
    return gap_report