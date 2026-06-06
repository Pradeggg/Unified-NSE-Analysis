def run(context):
    complete_reports = []
    incomplete_reports = []
    for report_id in context['reports']:
        # Fetch data completeness
        completeness_check = check_report_completeness(report_id, context['symbols'])
        if completeness_check:
            complete_reports.append(report_id)
        else:
            incomplete_reports.append(report_id)
    return {
        'complete_reports': complete_reports,
        'incomplete_reports': incomplete_reports
    }