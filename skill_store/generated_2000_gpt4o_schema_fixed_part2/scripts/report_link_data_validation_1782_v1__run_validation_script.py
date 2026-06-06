def run(context):
    # Process the report data for validation
    report_data = context['report_data']
    validation_summary = {
        'broken_links': [],
        'missing_data': []
    }
    # Identify and log validation issues
    for report in report_data:
        if not report.get('link'):
            validation_summary['broken_links'].append(report)
        if not report.get('data'): 
            validation_summary['missing_data'].append(report)
    return validation_summary